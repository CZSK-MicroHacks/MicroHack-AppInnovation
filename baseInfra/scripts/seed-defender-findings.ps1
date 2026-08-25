<#
.SYNOPSIS
Captures the pre-warmed deterministic Microsoft Defender for Cloud snapshot that Challenge 5
grades against.

.DESCRIPTION
Queries the facilitator golden environment for the four seed signals named by the frozen
Defender contract - image vulnerability assessment, recommendations, Secure Score, and
Microsoft cloud security benchmark controls - using exactly the scopes, resource paths, and
API versions that contract freezes. Each response is written verbatim into a digest-bound
query envelope under evidence/defender/foundation, and the run is summarized in
evidence/defender/foundation/seed-snapshot.json.

Every signal is verified or the run throws: the pinned Azure CLI must be installed, the
Defender contract must be the expected frozen version, all four responses must be non-empty,
the recommendations must cover the .NET VM, the Java VM, the container app, the container
registry, and the database server while containing at least the contracted number of
unhealthy findings, and the image assessment must contain a subassessment bound to the exact
handoff repository and immutable digest. A snapshot is therefore either complete and
deterministic or it does not exist, so grading never waits for a new live recommendation.

Run this against the golden environment at least 24 hours after the Defender plans were
enabled. Nothing here enables a plan, changes a resource, or prints a credential.
#>

#Requires -Version 7.0

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9a-fA-F-]{36}$')]
    [string]$SubscriptionId,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$HandoffPath,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$LegacyVmCoveragePath,

    [ValidateNotNullOrEmpty()]
    [string]$RepositoryRoot = (Join-Path $PSScriptRoot '..' '..')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Root = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$ContractPath = Join-Path $Root 'workshop/contracts/defender.json'
$ToolchainLockPath = Join-Path $Root 'workshop/toolchain.lock.json'
$SeedDirectory = 'evidence/defender/foundation'
$SnapshotFile = "$SeedDirectory/seed-snapshot.json"
$ArmEndpoint = 'https://management.azure.com'
$SnapshotSchemaVersion = '1.0.0'
$EnvelopeSchemaVersion = '1.0.0'
$DefenderContractVersion = '1.1.0'
$TimestampFormat = 'yyyy-MM-ddTHH:mm:ssZ'

function Write-ProvisionLog {
    param(
        [Parameter(Mandatory)]
        [string]$Message
    )

    Write-Host ('{0} [defender-seed] {1}' -f (Get-Date).ToUniversalTime().ToString('o'), $Message)
}

function Invoke-AzureCliJson {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $Output = & az @Arguments --only-show-errors --output json
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed: az $($Arguments -join ' ')"
    }
    return $Output | ConvertFrom-Json
}

function Get-JsonValue {
    <#
    Strict mode turns a missing property into a terminating error, so every optional or
    caller-validated field in an Azure response is read through this lookup instead.
    #>
    param(
        [Parameter(Mandatory)]
        [AllowNull()]
        [object]$InputObject,

        [Parameter(Mandatory)]
        [string]$Name
    )

    if ($null -eq $InputObject) {
        return $null
    }
    $Property = $InputObject.PSObject.Properties[$Name]
    if ($null -eq $Property) {
        return $null
    }
    return $Property.Value
}

function Get-RequiredJsonValue {
    param(
        [Parameter(Mandatory)]
        [AllowNull()]
        [object]$InputObject,

        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [string]$Description
    )

    $Value = Get-JsonValue -InputObject $InputObject -Name $Name
    if ($null -eq $Value -or ($Value -is [string] -and [string]::IsNullOrWhiteSpace($Value))) {
        throw "$Description is missing $Name."
    }
    return $Value
}

function Read-JsonFile {
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [string]$Description
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Description was not found at $Path."
    }
    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}

function Save-JsonFile {
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [object]$Value
    )

    New-Item -ItemType Directory -Path (Split-Path $Path -Parent) -Force | Out-Null
    # Depth covers nested Azure Resource Manager documents, which ConvertTo-Json otherwise
    # replaces with a type name; the encoding is BOM-free so the recorded digest is portable.
    [IO.File]::WriteAllText(
        $Path,
        (ConvertTo-Json -InputObject $Value -Depth 100),
        (New-Object Text.UTF8Encoding($false))
    )
    return (Get-FileHash -Path $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Test-SameResourceId {
    param(
        [Parameter(Mandatory)]
        [AllowNull()]
        [object]$Left,

        [Parameter(Mandatory)]
        [string]$Right
    )

    if ($Left -isnot [string]) {
        return $false
    }
    return $Left.TrimEnd('/') -eq $Right.TrimEnd('/')
}

function Assert-PinnedAzureCli {
    param(
        [Parameter(Mandatory)]
        [string]$ExpectedVersion
    )

    $Installed = Get-JsonValue -InputObject (Invoke-AzureCliJson -Arguments @('version')) -Name 'azure-cli'
    if ($Installed -ne $ExpectedVersion) {
        throw "Azure CLI $ExpectedVersion is pinned by workshop/toolchain.lock.json but $Installed is installed."
    }
    Write-ProvisionLog "Verified pinned Azure CLI $ExpectedVersion."
}

function Get-DatabaseServerResourceId {
    <#
    Defender assesses network posture on the parent server, not on the database child that the
    handoff names, so the server ID is derived and cross-checked against the declared family.
    #>
    param(
        [Parameter(Mandatory)]
        [object]$Database
    )

    $ResourceId = ([string](Get-RequiredJsonValue -InputObject $Database -Name 'resourceId' -Description 'The handoff database')).TrimEnd('/')
    $Family = [string](Get-RequiredJsonValue -InputObject $Database -Name 'family' -Description 'The handoff database')
    $Marker = '/databases/'
    $Index = $ResourceId.LastIndexOf($Marker, [StringComparison]::OrdinalIgnoreCase)
    if ($Index -lt 0) {
        throw 'The handoff database resource ID is not a database child.'
    }
    $ServerId = $ResourceId.Substring(0, $Index)
    $ExpectedProvider = if ($Family -eq 'azure-sql') {
        '/providers/Microsoft.Sql/servers/'
    }
    else {
        '/providers/Microsoft.DBforPostgreSQL/flexibleServers/'
    }
    if ($ServerId.IndexOf($ExpectedProvider, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
        throw "The handoff database family $Family disagrees with its resource ID."
    }
    return $ServerId
}

function Get-LegacyVmResourceId {
    param(
        [Parameter(Mandatory)]
        [object]$Coverage,

        [Parameter(Mandatory)]
        [ValidateSet('dotnet', 'java')]
        [string]$Workload
    )

    $Machine = @(
        (Get-RequiredJsonValue -InputObject $Coverage -Name 'virtualMachines' -Description 'The two-VM coverage artifact') |
            Where-Object { (Get-JsonValue -InputObject $_ -Name 'workload') -eq $Workload }
    )
    if ($Machine.Count -ne 1) {
        throw "The two-VM coverage artifact does not describe exactly one $Workload virtual machine."
    }
    return [string](Get-RequiredJsonValue `
            -InputObject (Get-JsonValue -InputObject $Machine[0] -Name 'request') `
            -Name 'resourceId' `
            -Description "The $Workload coverage request")
}

function Invoke-DefenderQuery {
    <#
    Issues one frozen Defender read and preserves the request and its verbatim response
    together, because the snapshot is only deterministic evidence if its provenance travels
    with it.
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Operation,

        [Parameter(Mandatory)]
        [string]$ScopeResourceId,

        [Parameter(Mandatory)]
        [object]$QueryContract,

        [Parameter(Mandatory)]
        [string]$FileName
    )

    $ResourcePath = [string](Get-RequiredJsonValue -InputObject $QueryContract -Name 'resourcePath' -Description "The frozen $Operation contract")
    $ApiVersion = [string](Get-RequiredJsonValue -InputObject $QueryContract -Name 'apiVersion' -Description "The frozen $Operation contract")
    $Method = [string](Get-RequiredJsonValue -InputObject $QueryContract -Name 'method' -Description "The frozen $Operation contract")
    if ($Method -ne 'GET') {
        throw "The frozen $Operation contract is not a GET query."
    }

    $QueriedAt = (Get-Date).ToUniversalTime().ToString($TimestampFormat)
    Write-ProvisionLog "Querying $Operation at $ScopeResourceId."
    $Response = Invoke-AzureCliJson -Arguments @(
        'rest',
        '--method',
        'get',
        '--url',
        ('{0}{1}/{2}?api-version={3}' -f $ArmEndpoint, $ScopeResourceId.TrimEnd('/'), $ResourcePath, $ApiVersion),
        '--subscription',
        $SubscriptionId
    )

    $Value = Get-JsonValue -InputObject $Response -Name 'value'
    # An absent, null, or empty value array all mean the same thing: Defender has not produced
    # this signal yet, and a snapshot missing any signal is not deterministic evidence.
    $Records = @()
    if ($null -ne $Value) {
        $Records = @($Value)
    }
    if ($Records.Count -eq 0) {
        throw "The $Operation response contains no records; let the golden environment finish scanning and re-capture."
    }

    $RelativeFile = "$SeedDirectory/$FileName"
    $Sha256 = Save-JsonFile -Path (Join-Path $Root $RelativeFile) -Value ([ordered]@{
            schemaVersion = $EnvelopeSchemaVersion
            request       = [ordered]@{
                method          = 'GET'
                operation       = $Operation
                scopeResourceId = $ScopeResourceId
                resourcePath    = $ResourcePath
                apiVersion      = $ApiVersion
                queriedAt       = $QueriedAt
            }
            response      = $Response
        })
    Write-ProvisionLog "Captured $($Records.Count) $Operation records into $RelativeFile."

    return [pscustomobject]@{
        Operation       = $Operation
        File            = $RelativeFile
        Sha256          = $Sha256
        QueriedAt       = $QueriedAt
        ScopeResourceId = $ScopeResourceId
        ApiVersion      = $ApiVersion
        Records         = $Records
        Response        = $Response
    }
}

function New-QueryArtifactReference {
    param(
        [Parameter(Mandatory)]
        [object]$Artifact
    )

    return [ordered]@{
        file            = $Artifact.File
        sha256          = $Artifact.Sha256
        queriedAt       = $Artifact.QueriedAt
        scopeResourceId = $Artifact.ScopeResourceId
        apiVersion      = $Artifact.ApiVersion
    }
}

function Assert-RecommendationCoverage {
    param(
        [Parameter(Mandatory)]
        [object]$Artifact,

        [Parameter(Mandatory)]
        [Collections.IDictionary]$ExpectedResources,

        [Parameter(Mandatory)]
        [int]$MinimumUnhealthy
    )

    $Covered = @{}
    $Unhealthy = 0
    foreach ($Record in $Artifact.Records) {
        $Properties = Get-JsonValue -InputObject $Record -Name 'properties'
        $Status = Get-JsonValue -InputObject (Get-JsonValue -InputObject $Properties -Name 'status') -Name 'code'
        if ($Status -eq 'Unhealthy') {
            $Unhealthy++
        }
        $ResourceId = Get-JsonValue `
            -InputObject (Get-JsonValue -InputObject $Properties -Name 'resourceDetails') `
            -Name 'id'
        foreach ($Label in @($ExpectedResources.Keys)) {
            if (Test-SameResourceId -Left $ResourceId -Right $ExpectedResources[$Label]) {
                $Covered[$Label] = $true
                break
            }
        }
    }

    $Missing = @(@($ExpectedResources.Keys) | Where-Object { -not $Covered.ContainsKey($_) })
    if ($Missing.Count -gt 0) {
        $Paged = if ($null -eq (Get-JsonValue -InputObject $Artifact.Response -Name 'nextLink')) {
            'Add the missing resource kind to the golden environment and re-capture.'
        }
        else {
            'The response is paged, so the missing resource may be beyond the first page; re-capture once the golden environment is smaller or the finding has surfaced.'
        }
        throw "The pre-warmed recommendations omit required resource context: $($Missing -join ', '). $Paged Never hand-edit the snapshot."
    }
    if ($Unhealthy -lt $MinimumUnhealthy) {
        throw "The pre-warmed recommendations contain $Unhealthy unhealthy findings but $MinimumUnhealthy are required."
    }
    Write-ProvisionLog "Recommendations cover every required resource; unhealthy findings: $Unhealthy."
    return $Unhealthy
}

function Assert-SecureScoreRecord {
    param(
        [Parameter(Mandatory)]
        [object]$Artifact
    )

    $Expected = "/subscriptions/$SubscriptionId/providers/Microsoft.Security/secureScores/ascScore"
    $Scores = @(
        $Artifact.Records | Where-Object {
            (Get-JsonValue -InputObject $_ -Name 'name') -eq 'ascScore' -and
            (Test-SameResourceId -Left (Get-JsonValue -InputObject $_ -Name 'id') -Right $Expected)
        }
    )
    if ($Scores.Count -ne 1) {
        throw 'The pre-warmed Secure Score response does not contain the subscription ascScore record.'
    }
}

function Assert-ImageAssessmentDigest {
    <#
    A completed image assessment is only meaningful when a subassessment names the exact
    handoff repository and immutable digest; anything else would let a tag-shaped or unrelated
    finding pose as the graded one.
    #>
    param(
        [Parameter(Mandatory)]
        [object]$Artifact,

        [Parameter(Mandatory)]
        [string]$Repository,

        [Parameter(Mandatory)]
        [string]$Digest
    )

    $Bound = @(
        $Artifact.Records | Where-Object {
            $Details = Get-JsonValue `
                -InputObject (Get-JsonValue -InputObject $_ -Name 'properties') `
                -Name 'artifactDetails'
            (Get-JsonValue -InputObject $Details -Name 'repositoryName') -eq $Repository -and
            (Get-JsonValue -InputObject $Details -Name 'digest') -eq $Digest
        }
    )
    if ($Bound.Count -lt 1) {
        throw "The pre-warmed image assessment has no subassessment for $Repository at $Digest; the scan is still pending."
    }
    Write-ProvisionLog "Image assessment is completed; subassessments bound to the handoff digest: $($Bound.Count)."
    return $Bound.Count
}

$Toolchain = Read-JsonFile -Path $ToolchainLockPath -Description 'The pinned toolchain lock'
Assert-PinnedAzureCli -ExpectedVersion ([string](Get-RequiredJsonValue `
            -InputObject (Get-RequiredJsonValue `
                -InputObject (Get-RequiredJsonValue -InputObject $Toolchain -Name 'tools' -Description 'The pinned toolchain lock') `
                -Name 'azureCli' `
                -Description 'The pinned toolchain lock') `
            -Name 'version' `
            -Description 'The pinned Azure CLI entry'))

$Contract = Read-JsonFile -Path $ContractPath -Description 'The frozen Defender contract'
$ContractVersion = [string](Get-RequiredJsonValue -InputObject $Contract -Name 'schemaVersion' -Description 'The frozen Defender contract')
if ($ContractVersion -ne $DefenderContractVersion) {
    throw "The frozen Defender contract is version $ContractVersion but $DefenderContractVersion is required."
}
$SeedContract = Get-RequiredJsonValue `
    -InputObject (Get-RequiredJsonValue -InputObject $Contract -Name 'foundation' -Description 'The frozen Defender contract') `
    -Name 'seedSnapshot' `
    -Description 'The frozen Defender foundation contract'
$QueryContracts = Get-RequiredJsonValue `
    -InputObject (Get-RequiredJsonValue -InputObject $Contract -Name 'evidence' -Description 'The frozen Defender contract') `
    -Name 'queryContracts' `
    -Description 'The frozen Defender evidence contract'

$Account = Invoke-AzureCliJson -Arguments @('account', 'show', '--subscription', $SubscriptionId)
if (-not (Test-SameResourceId -Left (Get-JsonValue -InputObject $Account -Name 'id') -Right $SubscriptionId)) {
    throw "The Azure CLI resolved a different subscription than $SubscriptionId."
}

$Handoff = Read-JsonFile -Path $HandoffPath -Description 'The golden handoff'
$Coverage = Read-JsonFile -Path $LegacyVmCoveragePath -Description 'The two-VM coverage artifact'
$ContainerImage = Get-RequiredJsonValue -InputObject $Handoff -Name 'containerImage' -Description 'The golden handoff'
$RegistryResourceId = [string](Get-RequiredJsonValue -InputObject $ContainerImage -Name 'registryResourceId' -Description 'The handoff container image')
$Repository = [string](Get-RequiredJsonValue -InputObject $ContainerImage -Name 'repository' -Description 'The handoff container image')
$Digest = [string](Get-RequiredJsonValue -InputObject $ContainerImage -Name 'digest' -Description 'The handoff container image')
if ($Digest -notmatch '^sha256:[0-9a-f]{64}$') {
    throw 'The handoff container image is not bound to an immutable sha256 digest.'
}

$SubscriptionScope = "/subscriptions/$SubscriptionId"
$ExpectedResources = [ordered]@{
    'dotnet-vm'          = Get-LegacyVmResourceId -Coverage $Coverage -Workload 'dotnet'
    'java-vm'            = Get-LegacyVmResourceId -Coverage $Coverage -Workload 'java'
    'container-app'      = [string](Get-RequiredJsonValue `
            -InputObject (Get-RequiredJsonValue -InputObject $Handoff -Name 'application' -Description 'The golden handoff') `
            -Name 'resourceId' `
            -Description 'The handoff application')
    'container-registry' = $RegistryResourceId
    'database'           = Get-DatabaseServerResourceId -Database (Get-RequiredJsonValue -InputObject $Handoff -Name 'database' -Description 'The golden handoff')
}

# The contract owns the coverage list, so drift between it and this script fails here rather
# than producing a snapshot that the participant validator later rejects.
$ContractedCoverage = @(Get-RequiredJsonValue -InputObject $SeedContract -Name 'recommendationResourceCoverage' -Description 'The frozen seed snapshot contract')
if (@(Compare-Object -ReferenceObject ($ContractedCoverage | Sort-Object) -DifferenceObject (@($ExpectedResources.Keys) | Sort-Object)).Count -gt 0) {
    throw "The frozen seed snapshot contract requires coverage of $($ContractedCoverage -join ', ')."
}
foreach ($Label in @($ExpectedResources.Keys)) {
    if ($ExpectedResources[$Label] -notlike "$SubscriptionScope/*") {
        throw "The $Label resource is outside subscription $SubscriptionId."
    }
}

$Recommendations = Invoke-DefenderQuery `
    -Operation 'subscription-recommendations' `
    -ScopeResourceId $SubscriptionScope `
    -QueryContract (Get-RequiredJsonValue -InputObject $QueryContracts -Name 'recommendations' -Description 'The frozen Defender evidence contract') `
    -FileName 'seed-recommendations.json'
$SecureScore = Invoke-DefenderQuery `
    -Operation 'subscription-secure-score' `
    -ScopeResourceId $SubscriptionScope `
    -QueryContract (Get-RequiredJsonValue -InputObject $QueryContracts -Name 'secureScore' -Description 'The frozen Defender evidence contract') `
    -FileName 'seed-secure-score.json'
$Mcsb = Invoke-DefenderQuery `
    -Operation 'subscription-mcsb-controls' `
    -ScopeResourceId $SubscriptionScope `
    -QueryContract (Get-RequiredJsonValue -InputObject $QueryContracts -Name 'mcsb' -Description 'The frozen Defender evidence contract') `
    -FileName 'seed-mcsb.json'
$ImageAssessment = Invoke-DefenderQuery `
    -Operation 'registry-image-subassessments' `
    -ScopeResourceId $RegistryResourceId `
    -QueryContract (Get-RequiredJsonValue -InputObject $QueryContracts -Name 'imageAssessment' -Description 'The frozen Defender evidence contract') `
    -FileName 'seed-image-assessment.json'

$UnhealthyCount = Assert-RecommendationCoverage `
    -Artifact $Recommendations `
    -ExpectedResources $ExpectedResources `
    -MinimumUnhealthy ([int](Get-RequiredJsonValue -InputObject $SeedContract -Name 'minimumUnhealthyRecommendations' -Description 'The frozen seed snapshot contract'))
Assert-SecureScoreRecord -Artifact $SecureScore
$ImageFindingCount = Assert-ImageAssessmentDigest -Artifact $ImageAssessment -Repository $Repository -Digest $Digest

$Artifacts = @($Recommendations, $SecureScore, $Mcsb, $ImageAssessment)
# The snapshot timestamp has to be strictly later than every query it summarizes, otherwise
# the evidence validator cannot prove the context was pre-warmed rather than captured live.
$LatestQueriedAt = ($Artifacts.QueriedAt | Sort-Object | Select-Object -Last 1)
$CapturedAt = (Get-Date).ToUniversalTime().ToString($TimestampFormat)
while ($CapturedAt -le $LatestQueriedAt) {
    Start-Sleep -Seconds 1
    $CapturedAt = (Get-Date).ToUniversalTime().ToString($TimestampFormat)
}

$Snapshot = [ordered]@{
    schemaVersion   = $SnapshotSchemaVersion
    capturedAt      = $CapturedAt
    subscriptionId  = $SubscriptionId
    recommendations = New-QueryArtifactReference -Artifact $Recommendations
    secureScore     = New-QueryArtifactReference -Artifact $SecureScore
    mcsb            = New-QueryArtifactReference -Artifact $Mcsb
    imageAssessment = [ordered]@{
        file               = $ImageAssessment.File
        sha256             = $ImageAssessment.Sha256
        queriedAt          = $ImageAssessment.QueriedAt
        status             = 'completed'
        digest             = $Digest
        registryResourceId = $ImageAssessment.ScopeResourceId
        apiVersion         = $ImageAssessment.ApiVersion
    }
}
$SnapshotSha256 = Save-JsonFile -Path (Join-Path $Root $SnapshotFile) -Value $Snapshot
Write-ProvisionLog "Wrote $SnapshotFile with digest $SnapshotSha256."

[pscustomobject]@{
    snapshot        = $SnapshotFile
    sha256          = $SnapshotSha256
    capturedAt      = $CapturedAt
    subscriptionId  = $SubscriptionId
    requiredSignals = @(Get-RequiredJsonValue -InputObject $SeedContract -Name 'requiredNonEmptySignals' -Description 'The frozen seed snapshot contract')
    recordCounts    = [pscustomobject]@{
        recommendations = $Recommendations.Records.Count
        secureScore     = $SecureScore.Records.Count
        mcsb            = $Mcsb.Records.Count
        imageAssessment = $ImageAssessment.Records.Count
    }
    unhealthyCount  = $UnhealthyCount
    imageFindings   = $ImageFindingCount
    coverage        = @($ExpectedResources.Keys)
    files           = @($Artifacts.File)
} | ConvertTo-Json -Depth 5
