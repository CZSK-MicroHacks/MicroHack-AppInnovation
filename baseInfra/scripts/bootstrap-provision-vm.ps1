<#
.SYNOPSIS
Separates protected VM custom data before launching the facilitator provisioner.

.DESCRIPTION
Reads the custom-data bundle as data, writes the secret payload and clean provisioner
with SYSTEM/Administrators-only ACLs, removes the original bundle, and only then launches
Windows PowerShell against the clean provisioner. Subsequent extension runs reuse the
protected local files because Azure custom data is immutable.
#>

function Set-BootstrapAcl {
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [switch]$Directory
    )

    $Acl = if ($Directory) {
        New-Object Security.AccessControl.DirectorySecurity
    }
    else {
        New-Object Security.AccessControl.FileSecurity
    }
    $Acl.SetAccessRuleProtection($true, $false)
    foreach ($Identity in @('NT AUTHORITY\SYSTEM', 'BUILTIN\Administrators')) {
        if ($Directory) {
            $Rule = New-Object Security.AccessControl.FileSystemAccessRule(
                $Identity,
                'FullControl',
                'ContainerInherit,ObjectInherit',
                'None',
                'Allow'
            )
        }
        else {
            $Rule = New-Object Security.AccessControl.FileSystemAccessRule(
                $Identity,
                'FullControl',
                'Allow'
            )
        }
        $Acl.AddAccessRule($Rule)
    }
    Set-Acl -LiteralPath $Path -AclObject $Acl
}

function Remove-BootstrapFile {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    # The guest agent sets ReadOnly on CustomData.bin; Windows enforces it ahead of the DACL.
    Set-ItemProperty -LiteralPath $Path -Name IsReadOnly -Value $false
    $Length = (Get-Item -LiteralPath $Path).Length
    if ($Length -gt 0) {
        [IO.File]::WriteAllBytes($Path, (New-Object byte[] $Length))
    }
    Remove-Item -LiteralPath $Path -Force
}

function Invoke-ProvisioningBootstrap {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [ValidateSet('dotnet', 'java')]
        [string]$Stack,

        [Parameter(Mandatory)]
        [ValidatePattern('^[0-9a-f]{40}$')]
        [string]$SourceCommit,

        [Parameter(Mandatory)]
        [ValidatePattern('^[0-9a-f]{64}$')]
        [string]$SourceArchiveSha256
    )

    $CustomDataPath = 'C:\AzureData\CustomData.bin'
    $ProvisionerPath = 'C:\AzureData\provision-vm.ps1'
    $SecretRoot = 'C:\MicroHack\secrets'
    $PayloadPath = Join-Path $SecretRoot 'provisioning.json'
    $BundleHeader = "MICROHACK_CUSTOM_DATA_V2`n"
    $ProvisionerMarker = "`nMICROHACK_PROVISIONER_START`n"
    $SourceArchiveUrl = "https://github.com/CZSK-MicroHacks/MicroHack-AppInnovation/archive/$SourceCommit.zip"

    New-Item -ItemType Directory -Path $SecretRoot -Force | Out-Null
    Set-BootstrapAcl -Path $SecretRoot -Directory

    if (Test-Path -LiteralPath $CustomDataPath) {
        $Bundle = [IO.File]::ReadAllText($CustomDataPath)
        if (-not $Bundle.StartsWith($BundleHeader, [StringComparison]::Ordinal)) {
            throw 'VM custom data does not contain the expected provisioning bundle header.'
        }
        $MarkerIndex = $Bundle.IndexOf(
            $ProvisionerMarker,
            $BundleHeader.Length,
            [StringComparison]::Ordinal
        )
        if ($MarkerIndex -lt 0) {
            throw 'VM custom data does not contain the provisioner boundary.'
        }

        $PayloadBase64 = $Bundle.Substring(
            $BundleHeader.Length,
            $MarkerIndex - $BundleHeader.Length
        )
        $ProvisionerText = $Bundle.Substring($MarkerIndex + $ProvisionerMarker.Length)
        $PayloadBytes = [Convert]::FromBase64String($PayloadBase64)
        if ($PayloadBytes.Length -eq 0 -or [string]::IsNullOrWhiteSpace($ProvisionerText)) {
            throw 'VM custom data contains an empty payload or provisioner.'
        }

        [IO.File]::WriteAllBytes($PayloadPath, $PayloadBytes)
        Set-BootstrapAcl -Path $PayloadPath
        [IO.File]::WriteAllText(
            $ProvisionerPath,
            $ProvisionerText,
            (New-Object Text.UTF8Encoding($false))
        )
        Set-BootstrapAcl -Path $ProvisionerPath

        $PayloadBytes = $null
        $PayloadBase64 = $null
        $Bundle = $null
        Remove-BootstrapFile -Path $CustomDataPath
    }

    if (-not (Test-Path -LiteralPath $PayloadPath) -or
        -not (Test-Path -LiteralPath $ProvisionerPath)) {
        throw 'Protected provisioning files are unavailable after bootstrap.'
    }
    Set-BootstrapAcl -Path $PayloadPath
    Set-BootstrapAcl -Path $ProvisionerPath

    & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass `
        -File $ProvisionerPath `
        -Stack $Stack `
        -SourceCommit $SourceCommit `
        -SourceArchiveUrl $SourceArchiveUrl `
        -SourceArchiveSha256 $SourceArchiveSha256
    if ($LASTEXITCODE -ne 0) {
        throw "The clean facilitator provisioner exited with code $LASTEXITCODE."
    }
}
