#!/usr/bin/env pwsh
<#
.SYNOPSIS
Guided facilitator TEST deployment of the MicroHack base infrastructure.

.DESCRIPTION
Walks through the documented provisioning sequence end to end: collects the Terraform
inputs interactively, pins and verifies the immutable source archive, runs the capacity
preflight, then init/validate/plan/apply, and finally reports how to reach each
provisioned environment.

This script targets a facilitator dry run, not a workshop delivery. The differences are
deliberate:

  * Terraform state is written to a local file on this computer instead of the encrypted
    remote backend required for a real cohort.
  * Entra participant users default to disabled, so nobody signs in to Azure.
  * The VM administrator password defaults to a weak, well-known test value.

State still contains generated database passwords and performance API keys, so treat the
state file as a secret even for a test run. For a delivery real participants sign in to,
follow docs/Facilitator.md instead.

.PARAMETER VarFile
Name of the git-ignored tfvars file generated inside baseInfra/terraform.

.PARAMETER StatePath
Absolute path of the local Terraform state file. Defaults to a per-user directory outside
the repository.

.PARAMETER SkipPreflight
Skips the capacity and cost preflight. The blocking capacity_preflight_confirmed input
must then be acknowledged manually at the prompt.

.EXAMPLE
./baseInfra/scripts/facilitator-test-deploy.ps1

.EXAMPLE
./baseInfra/scripts/facilitator-test-deploy.ps1 -VarFile test.tfvars -SkipPreflight
#>

[CmdletBinding()]
param(
    [ValidateNotNullOrEmpty()]
    [string]$VarFile = 'local.tfvars',

    [string]$StatePath,

    [switch]$SkipPreflight
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# Pinned by providers.tf as an exact requirement; a mismatch fails at init with a less
# obvious message than the check below.
$RequiredTerraformVersion = '1.13.3'
$SourceRepository = 'CZSK-MicroHacks/MicroHack-AppInnovation'

# Verified end to end and recorded in docs/Facilitator.md as a known-good starting point.
$KnownGoodCommit = 'b1846d144b3084d50a689dcfcfe084b54fa16f53'

$DefaultVmSize = 'Standard_D2as_v5'
$DefaultVmVcpus = 2
$DefaultOsDiskSizeGb = 127
$DefaultAdminUsername = 'azureuser'
$SuggestedTestPassword = 'MicroHack!Test2026'

#region helpers

function Write-Step {
    param([Parameter(Mandatory)][string]$Message)

    Write-Host ''
    Write-Host "== $Message" -ForegroundColor Cyan
}

function Write-Detail {
    param([Parameter(Mandatory)][string]$Message)

    Write-Host "   $Message" -ForegroundColor DarkGray
}

function Assert-Tool {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$InstallHint
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "'$Name' was not found on PATH. $InstallHint"
    }
}

function Invoke-Native {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$Arguments,
        [string]$FailureMessage
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        $message = if ($FailureMessage) {
            $FailureMessage
        }
        else {
            "$FilePath $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
        }
        throw $message
    }
}

function Invoke-NativeJson {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$Arguments,
        [string]$FailureMessage
    )

    $raw = & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        $message = if ($FailureMessage) {
            $FailureMessage
        }
        else {
            "$FilePath $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
        }
        throw $message
    }
    return ($raw | ConvertFrom-Json)
}

function Read-WithDefault {
    param(
        [Parameter(Mandatory)][string]$Prompt,
        [string]$Default,
        [scriptblock]$Validate,
        [string]$ValidationMessage = 'That value is not valid.'
    )

    while ($true) {
        $suffix = if ([string]::IsNullOrWhiteSpace($Default)) { '' } else { " [$Default]" }
        $answer = Read-Host "$Prompt$suffix"
        if ([string]::IsNullOrWhiteSpace($answer)) { $answer = $Default }
        if ([string]::IsNullOrWhiteSpace($answer)) {
            Write-Warning 'A value is required.'
            continue
        }

        $answer = $answer.Trim()
        if ($Validate -and -not (& $Validate $answer)) {
            Write-Warning $ValidationMessage
            continue
        }
        return $answer
    }
}

function Read-YesNo {
    param(
        [Parameter(Mandatory)][string]$Prompt,
        [bool]$Default = $false
    )

    $hint = if ($Default) { 'Y/n' } else { 'y/N' }
    while ($true) {
        $answer = Read-Host "$Prompt [$hint]"
        if ([string]::IsNullOrWhiteSpace($answer)) { return $Default }
        switch ($answer.Trim().ToLowerInvariant()) {
            'y' { return $true }
            'yes' { return $true }
            'n' { return $false }
            'no' { return $false }
            default { Write-Warning "Answer y or n." }
        }
    }
}

function Test-WindowsPasswordComplexity {
    param([Parameter(Mandatory)][string]$Password)

    if ($Password.Length -lt 12 -or $Password.Length -gt 123) { return $false }

    $classes = @(
        [bool]($Password -cmatch '[a-z]'),
        [bool]($Password -cmatch '[A-Z]'),
        [bool]($Password -match '[0-9]'),
        [bool]($Password -match '[^a-zA-Z0-9]')
    )
    return (@($classes | Where-Object { $_ }).Count -ge 3)
}

function Protect-LocalPath {
    <#
    .SYNOPSIS
    Restricts a directory to the current user on a best-effort basis.
    #>
    param([Parameter(Mandatory)][string]$Path)

    try {
        if ($IsWindows) {
            $account = "$env:USERDOMAIN\$env:USERNAME"
            & icacls $Path /inheritance:r /grant:r "${account}:(OI)(CI)F" | Out-Null
        }
        else {
            & chmod 700 $Path
        }
    }
    catch {
        Write-Warning "Could not restrict permissions on $Path : $($_.Exception.Message)"
    }
}

function ConvertTo-HclString {
    param([Parameter(Mandatory)][AllowEmptyString()][string]$Value)

    return '"' + ($Value -replace '\\', '\\' -replace '"', '\"') + '"'
}

function ConvertTo-HclList {
    param([Parameter(Mandatory)][AllowEmptyCollection()][string[]]$Values)

    if ($Values.Count -eq 0) { return '[]' }
    return '[' + (($Values | ForEach-Object { ConvertTo-HclString $_ }) -join ', ') + ']'
}

#endregion helpers

#region 1. tooling

Write-Host ''
Write-Host 'MicroHack base infrastructure - facilitator TEST deployment' -ForegroundColor Green
Write-Host 'Local Terraform state, no Entra users by default, throwaway VM password.' -ForegroundColor DarkGray

Write-Step '1/9 Checking tooling'

if ($PSVersionTable.PSVersion.Major -lt 7) {
    throw "PowerShell 7 or newer is required; this session is $($PSVersionTable.PSVersion)."
}

Assert-Tool -Name 'az' -InstallHint 'Install the Azure CLI 2.80 or newer.'
Assert-Tool -Name 'terraform' -InstallHint "Install Terraform $RequiredTerraformVersion."
Assert-Tool -Name 'git' -InstallHint 'Install git.'

$terraformVersion = (Invoke-NativeJson -FilePath 'terraform' -Arguments @('version', '-json')).terraform_version
if ($terraformVersion -ne $RequiredTerraformVersion) {
    throw "Terraform $RequiredTerraformVersion is required by providers.tf but $terraformVersion is on PATH."
}
Write-Detail "terraform $terraformVersion"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$terraformDir = Join-Path $repoRoot 'baseInfra/terraform'
if (-not (Test-Path (Join-Path $terraformDir 'main.tf'))) {
    throw "Could not locate baseInfra/terraform from script location $PSScriptRoot."
}
Write-Detail "repository root $repoRoot"

#endregion

#region 2. azure context

Write-Step '2/9 Reading the Azure CLI session'

$account = Invoke-NativeJson -FilePath 'az' -Arguments @('account', 'show', '-o', 'json') `
    -FailureMessage 'No active Azure CLI session. Run "az login" and "az account set --subscription <id>" first.'

$subscriptionId = $account.id
Write-Detail "subscription  $($account.name) ($subscriptionId)"
Write-Detail "signed in as  $($account.user.name)"

$facilitatorName = $null
$facilitatorObjectId = $null
try {
    $signedInUser = Invoke-NativeJson -FilePath 'az' -Arguments @('ad', 'signed-in-user', 'show', '-o', 'json')
    $facilitatorName = $signedInUser.userPrincipalName
    $facilitatorObjectId = $signedInUser.id
}
catch {
    Write-Warning 'Could not read the signed-in user from Microsoft Graph (common for service principals).'
}

if (-not $facilitatorName) {
    $facilitatorName = Read-WithDefault -Prompt 'Facilitator principal name' -Default $account.user.name
}
if (-not $facilitatorObjectId) {
    $facilitatorObjectId = Read-WithDefault -Prompt 'Facilitator principal object ID (GUID)' `
        -Validate { param($v) $v -match '^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$' } `
        -ValidationMessage 'Enter a GUID, for example 00000000-0000-0000-0000-000000000000.'
}

Write-Detail "facilitator   $facilitatorName ($facilitatorObjectId)"

if (-not (Read-YesNo -Prompt 'Deploy into this subscription as this identity?' -Default $true)) {
    Write-Host 'Run "az account set --subscription <id>" or "az login", then start again.' -ForegroundColor Yellow
    return
}

#endregion

#region 3. inputs

Write-Step '3/9 Collecting deployment inputs'

$participantCount = [int](Read-WithDefault -Prompt 'Number of participant environments' -Default '2' `
        -Validate { param($v) $v -match '^\d+$' -and [int]$v -ge 1 -and [int]$v -le 254 } `
        -ValidationMessage 'Enter a whole number from 1 through 254.')

$locationsInput = Read-WithDefault -Prompt 'Azure regions (comma separated)' -Default 'swedencentral' `
    -Validate {
    param($v)
    $parsed = @($v -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    $parsed.Count -gt 0 -and $parsed.Count -eq (@($parsed | Sort-Object -Unique)).Count
} -ValidationMessage 'Provide at least one region; duplicates are rejected by Terraform.'
$locations = @($locationsInput -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })

Write-Host ''
Write-Host '   The VM password is stored in Terraform state and on the VMs. This default is a' -ForegroundColor DarkGray
Write-Host '   throwaway value for facilitator testing only - never reuse it for a real cohort.' -ForegroundColor DarkGray
$adminPassword = Read-WithDefault -Prompt 'VM administrator password' -Default $SuggestedTestPassword `
    -Validate { param($v) Test-WindowsPasswordComplexity -Password $v } `
    -ValidationMessage 'Windows requires 12-123 characters with at least three of: lowercase, uppercase, digit, symbol.'

$manageEntraUsers = Read-YesNo -Prompt 'Create Entra ID participant users (not needed for a test run)?' -Default $false
$entraUserDomain = ''
if ($manageEntraUsers) {
    $defaultDomain = if ($facilitatorName -match '@(.+)$') { $Matches[1] } else { '' }
    $entraUserDomain = Read-WithDefault -Prompt 'Entra ID domain for participant UPNs' -Default $defaultDomain
}

# Defaults below match config.tfvars.example and cover almost every test run.
$adminUsername = $DefaultAdminUsername
$vmSize = $DefaultVmSize
$vmVcpus = $DefaultVmVcpus
$osDiskSizeGb = $DefaultOsDiskSizeGb
$manageSubProviders = $true
$rdpSourcePrefixes = @()

if (Read-YesNo -Prompt 'Customise advanced settings (VM size, disk, providers, RDP source)?' -Default $false) {
    $adminUsername = Read-WithDefault -Prompt 'VM administrator username' -Default $DefaultAdminUsername

    $vmSize = Read-WithDefault -Prompt 'VM size' -Default $DefaultVmSize
    $vmVcpus = [int](Read-WithDefault -Prompt 'vCPUs exposed by that size (footprint maths only)' -Default "$DefaultVmVcpus" `
            -Validate { param($v) $v -match '^\d+$' -and [int]$v -ge 1 } `
            -ValidationMessage 'Enter a positive whole number.')

    $osDiskSizeGb = [int](Read-WithDefault -Prompt 'OS disk size in GiB' -Default "$DefaultOsDiskSizeGb" `
            -Validate { param($v) $v -match '^\d+$' -and [int]$v -ge 127 } `
            -ValidationMessage 'The pinned Windows image needs at least 127 GiB.')

    $manageSubProviders = Read-YesNo -Prompt 'Register subscription resource providers (needs Owner)?' -Default $true

    Write-Host ''
    Write-Host '   Leave blank to ship no inbound rule and use Just-in-Time VM access. Tenant' -ForegroundColor DarkGray
    Write-Host '   governance deletes unscoped 3389 rules, so never answer "Internet".' -ForegroundColor DarkGray
    $rdpInput = Read-Host '   RDP source CIDR, e.g. 203.0.113.10/32 (blank = none)'
    if (-not [string]::IsNullOrWhiteSpace($rdpInput)) {
        $rdpSourcePrefixes = @($rdpInput -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
        if ($rdpSourcePrefixes | Where-Object { $_.ToLowerInvariant() -eq 'internet' }) {
            throw 'An "Internet" RDP source is rejected by Terraform and removed by tenant governance.'
        }
    }
}

$footprintVms = $participantCount * 2
Write-Host ''
Write-Detail "footprint: $footprintVms VMs, $($footprintVms * $vmVcpus) vCPUs, $footprintVms Premium OS disks, $footprintVms public IPs"

#endregion

#region 4. source pin

Write-Step '4/9 Pinning and verifying the source archive'

Write-Host '   [1] Known-good verified commit (recommended for a test run)' -ForegroundColor DarkGray
Write-Host '   [2] Current local HEAD (must already be pushed to GitHub)' -ForegroundColor DarkGray
Write-Host '   [3] Enter a commit SHA' -ForegroundColor DarkGray

$pinChoice = Read-WithDefault -Prompt 'Source commit' -Default '1' `
    -Validate { param($v) $v -in @('1', '2', '3') } -ValidationMessage 'Choose 1, 2 or 3.'

$sourceCommit = $null
switch ($pinChoice) {
    '1' { $sourceCommit = $KnownGoodCommit }
    '2' {
        Push-Location $repoRoot
        try { $sourceCommit = (& git rev-parse HEAD).Trim() } finally { Pop-Location }
    }
    '3' {
        $sourceCommit = Read-WithDefault -Prompt 'Commit SHA (40 lowercase hex)' `
            -Validate { param($v) $v -match '^[0-9a-f]{40}$' } `
            -ValidationMessage 'Terraform only accepts a full lowercase 40-hex commit ID.'
    }
}

if ($sourceCommit -notmatch '^[0-9a-f]{40}$') {
    throw "Resolved source commit '$sourceCommit' is not a full lowercase 40-hex commit ID."
}
Write-Detail "commit $sourceCommit"

$archivePath = Join-Path ([System.IO.Path]::GetTempPath()) "microhack-$sourceCommit.zip"
$archiveUrl = "https://github.com/$SourceRepository/archive/$sourceCommit.zip"

try {
    Write-Detail "downloading $archiveUrl"
    Invoke-WebRequest -Uri $archiveUrl -OutFile $archivePath

    $sourceArchiveSha256 = (Get-FileHash -Path $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()

    # The provisioner refuses an archive that is not a workshop tree; failing here is much
    # cheaper than failing inside the Custom Script Extension 30 minutes into an apply.
    if (-not ('System.IO.Compression.ZipFile' -as [type])) {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
    }
    $zip = [System.IO.Compression.ZipFile]::OpenRead($archivePath)
    try {
        $entries = @($zip.Entries | ForEach-Object { $_.FullName -replace '^[^/]+/', '' })
    }
    finally {
        $zip.Dispose()
    }

    $missing = @()
    foreach ($marker in @('data/manifest.json', 'dotnet/', 'java/', 'challenges/ch01/')) {
        $found = if ($marker.EndsWith('/')) {
            [bool]($entries | Where-Object { $_.StartsWith($marker) } | Select-Object -First 1)
        }
        else {
            $entries -contains $marker
        }
        if (-not $found) { $missing += $marker }
    }
    if ($missing.Count -gt 0) {
        throw "Archive for $sourceCommit is missing $($missing -join ', '). Pin a published workshop commit."
    }
}
finally {
    if (Test-Path $archivePath) { Remove-Item $archivePath -Force }
}

Write-Detail "sha256 $sourceArchiveSha256"
Write-Detail 'archive contains data/manifest.json, dotnet/, java/, challenges/ch01/'

#endregion

#region 5. local state backend

Write-Step '5/9 Configuring local Terraform state'

if (-not $StatePath) {
    $defaultStateDir = Join-Path $HOME '.microhack/baseinfra-test'
    $StatePath = Join-Path $defaultStateDir 'terraform.tfstate'
}

$StatePath = [System.IO.Path]::GetFullPath($StatePath)
$stateDir = Split-Path -Parent $StatePath

$overridePath = Join-Path $terraformDir 'backend_override.tf'
$keepExistingOverride = $false

if (Test-Path $overridePath) {
    $existing = Get-Content $overridePath -Raw
    $existingPath = if ($existing -match 'path\s*=\s*"([^"]+)"') { $Matches[1] } else { '(unparsed)' }
    if ($existingPath -ne ($StatePath -replace '\\', '/')) {
        Write-Warning "backend_override.tf already points state at: $existingPath"
        Write-Warning 'That state may describe live resources. Overwriting it does not delete them, but this run will stop tracking them.'
        if (-not (Read-YesNo -Prompt "Repoint Terraform state to $StatePath ?" -Default $false)) {
            $StatePath = [System.IO.Path]::GetFullPath($existingPath)
            $stateDir = Split-Path -Parent $StatePath
            # The file already says what this run needs, and it may carry facilitator notes.
            $keepExistingOverride = $true
            Write-Detail "keeping existing backend_override.tf and state path $StatePath"
        }
    }
    else {
        $keepExistingOverride = $true
    }
}

if (-not (Test-Path $stateDir)) {
    New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
}
Protect-LocalPath -Path $stateDir

if (-not $keepExistingOverride) {
    # providers.tf declares a partial azurerm backend for real deliveries. A *_override.tf file
    # replaces that block, which is how a test run keeps state on this computer.
    $hclStatePath = $StatePath -replace '\\', '/'
    @"
// Generated by baseInfra/scripts/facilitator-test-deploy.ps1 for a facilitator TEST run.
// It replaces the azurerm backend in providers.tf so state stays on this computer.
// State still holds generated database passwords and performance API keys - keep it private.
// A real cohort must use the encrypted remote backend described in docs/Facilitator.md.
terraform {
  backend "local" {
    path = "$hclStatePath"
  }
}
"@ | Set-Content -Path $overridePath -Encoding utf8
}

Write-Detail "state file $StatePath"

#endregion

#region 6. tfvars

Write-Step '6/9 Writing Terraform variables'

$varFilePath = if ([System.IO.Path]::IsPathRooted($VarFile)) { $VarFile } else { Join-Path $terraformDir $VarFile }

if (Test-Path $varFilePath) {
    $backupPath = "$varFilePath.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Write-Warning "$varFilePath already exists."
    if (-not (Read-YesNo -Prompt "Overwrite it (a backup is kept at $(Split-Path -Leaf $backupPath))?" -Default $true)) {
        throw 'Aborted so the existing tfvars file is preserved. Re-run with -VarFile <name>.'
    }
    Copy-Item -Path $varFilePath -Destination $backupPath -Force
    Write-Detail "backed up to $backupPath"
}

# capacity_preflight_confirmed is written after the preflight in step 7.
$tfvars = @"
# Generated by baseInfra/scripts/facilitator-test-deploy.ps1 on $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss').
# Facilitator TEST run. Git-ignored: never commit this file.
# admin_password is deliberately absent - it is passed through TF_VAR_admin_password.

n         = $participantCount
locations = $(ConvertTo-HclList $locations)

subscription_id = $(ConvertTo-HclString $subscriptionId)

admin_username  = $(ConvertTo-HclString $adminUsername)
vm_size         = $(ConvertTo-HclString $vmSize)
vm_vcpus        = $vmVcpus
os_disk_size_gb = $osDiskSizeGb

source_commit         = $(ConvertTo-HclString $sourceCommit)
source_archive_sha256 = $(ConvertTo-HclString $sourceArchiveSha256)

facilitator_principal_name      = $(ConvertTo-HclString $facilitatorName)
facilitator_principal_object_id = $(ConvertTo-HclString $facilitatorObjectId)

manage_entra_users = $($manageEntraUsers.ToString().ToLowerInvariant())
entra_user_domain  = $(ConvertTo-HclString $entraUserDomain)

manage_azure_resources = true
manage_sub_providers   = $($manageSubProviders.ToString().ToLowerInvariant())

rdp_source_address_prefixes = $(ConvertTo-HclList $rdpSourcePrefixes)

capacity_preflight_confirmed = CAPACITY_PLACEHOLDER

enable_defender_foundation      = false
defender_facilitator_authorized = false
"@

#endregion

#region 7. preflight

Write-Step '7/9 Capacity and cost preflight'

$preflightConfirmed = $false

if ($SkipPreflight) {
    Write-Warning 'Preflight skipped by -SkipPreflight.'
}
else {
    $defaultCeiling = $participantCount * 400
    $costCeiling = [decimal](Read-WithDefault -Prompt 'Maximum estimated monthly cost in USD' -Default "$defaultCeiling" `
            -Validate { param($v) $v -match '^\d+(\.\d+)?$' -and [decimal]$v -ge 0.01 } `
            -ValidationMessage 'Enter a positive number.')

    $abortRequested = $false
    while (-not $preflightConfirmed -and -not $abortRequested) {
        try {
            & (Join-Path $PSScriptRoot 'preflight-capacity.ps1') `
                -SubscriptionId $subscriptionId `
                -Locations $locations `
                -ParticipantCount $participantCount `
                -VmSize $vmSize `
                -OsDiskSizeGiB $osDiskSizeGb `
                -MaximumEstimatedMonthlyCostUsd $costCeiling
            $preflightConfirmed = $true
            Write-Host '   Preflight passed.' -ForegroundColor Green
        }
        catch {
            Write-Warning "Preflight failed: $($_.Exception.Message)"

            # The quota and retail-price calls are network chatty, so a transient TLS or
            # throttling failure here says nothing about actual capacity. Offer a retry
            # rather than discarding the inputs collected so far.
            $choice = (Read-WithDefault -Prompt 'Choose [r]etry, [c]ontinue without preflight, [a]bort' -Default 'r' `
                    -Validate { param($v) $v.ToLowerInvariant() -in @('r', 'c', 'a') } `
                    -ValidationMessage 'Answer r, c or a.').ToLowerInvariant()

            if ($choice -eq 'a') {
                $abortRequested = $true
            }
            elseif ($choice -eq 'c') {
                break
            }
            # 'r' falls through so the loop runs the preflight again.
        }
    }

    if ($abortRequested) {
        Write-Host 'Nothing was deployed.' -ForegroundColor Yellow
        return
    }
}

if (-not $preflightConfirmed) {
    Write-Host ''
    Write-Host '   Terraform refuses to create any resource until capacity_preflight_confirmed is true.' -ForegroundColor DarkGray
    $preflightConfirmed = Read-YesNo -Prompt 'Confirm you have verified quota and cost manually?' -Default $false
    if (-not $preflightConfirmed) {
        Write-Host 'Nothing was deployed. Run the preflight, then start again.' -ForegroundColor Yellow
        return
    }
}

$tfvars = $tfvars -replace 'CAPACITY_PLACEHOLDER', 'true'
$tfvars | Set-Content -Path $varFilePath -Encoding utf8
Write-Detail "wrote $varFilePath"

#endregion

#region 8-9. init, plan, apply, report

Write-Step '8/9 Running Terraform'

# Keeping the password out of the tfvars file is the documented pattern; it is still
# written to state, which is why the state directory is locked down above.
$env:TF_VAR_admin_password = $adminPassword

Push-Location $terraformDir
try {
    Write-Host ''
    Write-Host '-- terraform init' -ForegroundColor Yellow
    Invoke-Native -FilePath 'terraform' -Arguments @('init', '-reconfigure', '-input=false')

    Write-Host ''
    Write-Host '-- terraform validate' -ForegroundColor Yellow
    Invoke-Native -FilePath 'terraform' -Arguments @('validate')

    Write-Host ''
    Write-Host '-- terraform plan' -ForegroundColor Yellow
    Invoke-Native -FilePath 'terraform' -Arguments @('plan', "-var-file=$VarFile", '-out=tfplan', '-input=false')

    Write-Host ''
    Write-Host 'Review the plan above: resource counts, regions, and any replacements.' -ForegroundColor Yellow
    if (-not (Read-YesNo -Prompt 'Apply this plan?' -Default $false)) {
        Write-Host 'Nothing was applied. The saved plan is at baseInfra/terraform/tfplan.' -ForegroundColor Yellow
        return
    }

    Write-Host ''
    Write-Host "-- terraform apply (provisioning $footprintVms VMs; typically 20-40 minutes)" -ForegroundColor Yellow
    Invoke-Native -FilePath 'terraform' -Arguments @('apply', '-input=false', 'tfplan')

    Write-Step '9/9 Deployment report'

    $outputs = Invoke-NativeJson -FilePath 'terraform' -Arguments @('output', '-json')

    $access = $outputs.legacy_vm_access_by_environment.value
    $regions = $outputs.region_assignment.value
    $indices = @($access.PSObject.Properties.Name | Sort-Object { [int]$_ })

    $rows = foreach ($index in $indices) {
        $entry = $access.$index
        [pscustomobject]@{
            Participant = $index
            ResourceGroup = 'rg-user{0:D3}' -f [int]$index
            Region        = $regions.$index
            DotnetRdp     = $entry.dotnet.rdp_address
            JavaRdp       = $entry.java.rdp_address
        }
    }

    Write-Host ''
    $rows | Format-Table -AutoSize | Out-String | Write-Host

    $footprint = $outputs.deployment_footprint.value
    Write-Host "Footprint: $($footprint.virtual_machines) VMs, $($footprint.regional_vcpus) vCPUs, $($footprint.os_disks) OS disks ($($footprint.os_disk_gib) GiB)."
    Write-Host ''
    Write-Host 'Sign in to each VM over RDP with:' -ForegroundColor Green
    Write-Host "  username  $adminUsername"
    Write-Host "  password  $adminPassword"

    if ($rdpSourcePrefixes.Count -eq 0) {
        Write-Host ''
        Write-Host 'The NSG ships with no inbound rule. Request Just-in-Time VM access in the portal' -ForegroundColor Yellow
        Write-Host 'before connecting, or re-run with an RDP source CIDR under advanced settings.' -ForegroundColor Yellow
    }

    Write-Host ''
    Write-Host 'Inside each VM, the legacy app is at http://localhost:5000 (.NET) or http://localhost:8080 (Java).'
    Write-Host 'Provisioning status: C:\MicroHack\status\*-smoke.json and C:\MicroHack\logs\*.log'

    if ($manageEntraUsers) {
        Write-Host ''
        if (Read-YesNo -Prompt 'Print the generated Entra participant credentials now?' -Default $false) {
            & terraform output -json entra_user_credentials | ConvertFrom-Json | Format-List | Out-String | Write-Host
        }
        else {
            Write-Host 'Read them later with: terraform output -json entra_user_credentials' -ForegroundColor DarkGray
        }
    }

    Write-Host ''
    Write-Host 'When you are finished testing, tear the environment down:' -ForegroundColor Cyan
    Write-Host "  cd $terraformDir"
    Write-Host '  $env:TF_VAR_admin_password = ''<the password above>'''
    if ($manageSubProviders) {
        Write-Host "  terraform state rm 'module.resource_providers[0]'   # keep subscription providers registered"
    }
    Write-Host "  terraform destroy -var-file=$VarFile"
    Write-Host ''
    Write-Host "State file: $StatePath" -ForegroundColor DarkGray
    Write-Host 'It holds generated secrets - delete it only after the destroy succeeds.' -ForegroundColor DarkGray
}
finally {
    Pop-Location
    Remove-Item Env:\TF_VAR_admin_password -ErrorAction SilentlyContinue
}

#endregion
