<#
.SYNOPSIS
Provisions one frozen workshop stack on a Windows Server 2025 facilitator VM.

.DESCRIPTION
Installs only lock-file-pinned tools, verifies every downloaded artifact before use,
deploys the immutable application source, configures the native local database,
registers an automatic application task, and fails unless stack-specific smoke checks pass.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('dotnet', 'java')]
    [string]$Stack,

    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9a-f]{40}$')]
    [string]$SourceCommit,

    [Parameter(Mandatory)]
    [ValidatePattern('^https://github\.com/CZSK-MicroHacks/MicroHack-AppInnovation/archive/[0-9a-f]{40}\.zip$')]
    [string]$SourceArchiveUrl,

    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9a-f]{64}$')]
    [string]$SourceArchiveSha256
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root = 'C:\MicroHack'
$DownloadRoot = Join-Path $Root 'downloads'
$SourceRoot = Join-Path $Root 'source'
$ApplicationRoot = Join-Path $Root 'app'
$StatusRoot = Join-Path $Root 'status'
$SecretRoot = Join-Path $Root 'secrets'
$LogRoot = Join-Path $Root 'logs'
$LogFile = Join-Path $LogRoot "provision-$Stack.log"

foreach ($Directory in @(
        $Root,
        $DownloadRoot,
        $ApplicationRoot,
        $StatusRoot,
        $SecretRoot,
        $LogRoot
    )) {
    New-Item -ItemType Directory -Path $Directory -Force | Out-Null
}

function Write-ProvisionLog {
    param(
        [Parameter(Mandatory)]
        [string]$Message
    )

    $Line = '{0} [{1}] {2}' -f (Get-Date).ToUniversalTime().ToString('o'), $Stack, $Message
    Write-Host $Line
    Add-Content -Path $LogFile -Value $Line -Encoding UTF8
}

function Invoke-VerifiedDownload {
    param(
        [Parameter(Mandatory)]
        [uri]$Uri,

        [Parameter(Mandatory)]
        [string]$Destination,

        [Parameter(Mandatory)]
        [ValidateSet('SHA256', 'SHA512')]
        [string]$Algorithm,

        [Parameter(Mandatory)]
        [string]$ExpectedHash
    )

    if (Test-Path $Destination) {
        $ExistingHash = (Get-FileHash -Path $Destination -Algorithm $Algorithm).Hash.ToLowerInvariant()
        if ($ExistingHash -eq $ExpectedHash) {
            Write-ProvisionLog "Reusing verified download $(Split-Path $Destination -Leaf)."
            return
        }
        Remove-Item -Path $Destination -Force
    }

    $Temporary = "$Destination.download"
    Remove-Item -Path $Temporary -Force -ErrorAction SilentlyContinue
    Write-ProvisionLog "Downloading locked artifact $($Uri.AbsoluteUri)."
    Invoke-WebRequest -Uri $Uri -OutFile $Temporary -UseBasicParsing
    $ActualHash = (Get-FileHash -Path $Temporary -Algorithm $Algorithm).Hash.ToLowerInvariant()
    if ($ActualHash -ne $ExpectedHash) {
        Remove-Item -Path $Temporary -Force
        throw "Digest verification failed for $($Uri.AbsoluteUri)."
    }
    Move-Item -Path $Temporary -Destination $Destination -Force
}

function Assert-AuthenticodePublisher {
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [string]$Publisher
    )

    $Signature = Get-AuthenticodeSignature -FilePath $Path
    if ($Signature.Status -ne [Management.Automation.SignatureStatus]::Valid) {
        throw "Authenticode signature is not valid for $(Split-Path $Path -Leaf)."
    }
    if ($null -eq $Signature.SignerCertificate -or
        $Signature.SignerCertificate.Subject -notmatch [regex]::Escape($Publisher)) {
        throw "Authenticode publisher mismatch for $(Split-Path $Path -Leaf)."
    }
}

function Invoke-LockedInstaller {
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [string[]]$Arguments,

        [int[]]$AllowedExitCodes = @(0, 3010)
    )

    Write-ProvisionLog "Executing verified installer $(Split-Path $Path -Leaf)."
    $Process = Start-Process -FilePath $Path -ArgumentList $Arguments -Wait -PassThru
    if ($Process.ExitCode -notin $AllowedExitCodes) {
        throw "Installer $(Split-Path $Path -Leaf) exited with code $($Process.ExitCode)."
    }
}

function Add-MachinePath {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    $MachinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $Entries = @($MachinePath -split ';' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($Entries.TrimEnd('\') -notcontains $Path.TrimEnd('\')) {
        [Environment]::SetEnvironmentVariable(
            'Path',
            (($Entries + $Path) -join ';'),
            'Machine'
        )
    }
    if (($env:Path -split ';').TrimEnd('\') -notcontains $Path.TrimEnd('\')) {
        $env:Path = "$env:Path;$Path"
    }
}

function Invoke-WithRetry {
    param(
        [Parameter(Mandatory)]
        [string]$Description,

        [Parameter(Mandatory)]
        [scriptblock]$Action,

        [int]$Attempts = 60,

        [int]$DelaySeconds = 5
    )

    for ($Attempt = 1; $Attempt -le $Attempts; $Attempt++) {
        try {
            & $Action
            Write-ProvisionLog "$Description succeeded on attempt $Attempt."
            return
        }
        catch {
            if ($Attempt -eq $Attempts) {
                throw "$Description failed after $Attempts attempts: $($_.Exception.Message)"
            }
            Start-Sleep -Seconds $DelaySeconds
        }
    }
}

function Set-ProtectedAcl {
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
    Set-Acl -Path $Path -AclObject $Acl
}

function Save-ProtectedText {
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [string]$Value
    )

    [IO.File]::WriteAllText(
        $Path,
        $Value,
        (New-Object Text.UTF8Encoding($false))
    )
    Set-ProtectedAcl -Path $Path
}

function Save-ProtectedConfiguration {
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [hashtable]$Values
    )

    Save-ProtectedText -Path $Path -Value ($Values | ConvertTo-Json)
}

function Remove-ProtectedFile {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    $Length = (Get-Item -LiteralPath $Path).Length
    if ($Length -gt 0) {
        [IO.File]::WriteAllBytes($Path, (New-Object byte[] $Length))
    }
    Remove-Item -LiteralPath $Path -Force
}

function Get-ProvisioningSecrets {
    $PayloadPath = Join-Path $SecretRoot 'provisioning.json'
    if (-not (Test-Path -LiteralPath $PayloadPath)) {
        throw 'The protected provisioning payload is unavailable.'
    }
    Set-ProtectedAcl -Path $PayloadPath
    $Payload = Get-Content -LiteralPath $PayloadPath -Raw | ConvertFrom-Json
    if ([string]::IsNullOrWhiteSpace([string]$Payload.databasePassword) -or
        [string]::IsNullOrWhiteSpace([string]$Payload.performanceApiKey)) {
        throw 'The protected provisioning payload is incomplete.'
    }
    return $Payload
}

Set-ProtectedAcl -Path $SecretRoot -Directory
Set-ProtectedAcl -Path $PSCommandPath
$ProvisioningSecrets = Get-ProvisioningSecrets
$DatabasePassword = [string]$ProvisioningSecrets.databasePassword
$PerformanceApiKey = [string]$ProvisioningSecrets.performanceApiKey
$ProvisioningSecrets = $null

function Install-CommonTools {
    $Artifacts = @{
        VsCode = @{
            Version   = '1.133.0'
            Uri       = 'https://update.code.visualstudio.com/1.133.0/win32-x64/stable'
            Hash      = 'de949a8904509a7661b93ea3b25ea312749b869c242938ad082ddc72d6741c3d'
            Publisher = 'Microsoft Corporation'
        }
        AzureCli = @{
            Version   = '2.80.0'
            Uri       = 'https://azcliprod.blob.core.windows.net/msi/azure-cli-2.80.0-x64.msi'
            Hash      = 'ab9d66e7d8537401d5bd734086daf80f60a9b7fe1ace9cb78470741e7bbaccf5'
            Publisher = 'Microsoft Corporation'
        }
        Uv = @{
            Version   = '0.8.22'
            Uri       = 'https://github.com/astral-sh/uv/releases/download/0.8.22/uv-x86_64-pc-windows-msvc.zip'
            Hash      = '5049375aa2a5162f132b2c1cb992e25d42d47d934cab8c174dbe6f60973dcc12'
            Publisher = 'Astral Software Inc.'
        }
    }

    $VsCodeRoot = 'C:\Program Files\Microsoft VS Code'
    $CodeCommand = Join-Path $VsCodeRoot 'bin\code.cmd'
    $InstalledVsCodeVersion = if (Test-Path $CodeCommand) {
        (& $CodeCommand --version | Select-Object -First 1).Trim()
    }
    else {
        $null
    }
    if ($InstalledVsCodeVersion -ne $Artifacts.VsCode.Version) {
        $Installer = Join-Path $DownloadRoot 'VSCodeSetup-1.133.0.exe'
        Invoke-VerifiedDownload -Uri $Artifacts.VsCode.Uri -Destination $Installer `
            -Algorithm SHA256 -ExpectedHash $Artifacts.VsCode.Hash
        Assert-AuthenticodePublisher -Path $Installer -Publisher $Artifacts.VsCode.Publisher
        Invoke-LockedInstaller -Path $Installer -Arguments @(
            '/VERYSILENT',
            '/NORESTART',
            '/MERGETASKS=!runcode',
            "/DIR=`"$VsCodeRoot`""
        )
    }
    if (-not (Test-Path $CodeCommand)) {
        throw 'The pinned Visual Studio Code installer did not create code.cmd.'
    }
    Add-MachinePath -Path (Join-Path $VsCodeRoot 'bin')
    if ((& $CodeCommand --version | Select-Object -First 1).Trim() -ne $Artifacts.VsCode.Version) {
        throw 'Visual Studio Code version verification failed.'
    }

    $AzCommand = 'C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd'
    $InstalledAzureCliVersion = if (Test-Path $AzCommand) {
        ((& $AzCommand version --output json | ConvertFrom-Json).'azure-cli')
    }
    else {
        $null
    }
    if ($InstalledAzureCliVersion -ne $Artifacts.AzureCli.Version) {
        $Installer = Join-Path $DownloadRoot 'azure-cli-2.80.0-x64.msi'
        Invoke-VerifiedDownload -Uri $Artifacts.AzureCli.Uri -Destination $Installer `
            -Algorithm SHA256 -ExpectedHash $Artifacts.AzureCli.Hash
        Assert-AuthenticodePublisher -Path $Installer -Publisher $Artifacts.AzureCli.Publisher
        Invoke-LockedInstaller -Path 'msiexec.exe' -Arguments @(
            '/i',
            "`"$Installer`"",
            '/qn',
            '/norestart'
        )
    }
    if (-not (Test-Path $AzCommand)) {
        throw 'The pinned Azure CLI installer did not create az.cmd.'
    }
    Add-MachinePath -Path (Split-Path $AzCommand -Parent)
    $AzureCliVersion = ((& $AzCommand version --output json | ConvertFrom-Json).'azure-cli')
    if ($AzureCliVersion -ne $Artifacts.AzureCli.Version) {
        throw 'Azure CLI version verification failed.'
    }

    $UvRoot = 'C:\Program Files\uv'
    $UvCommand = Join-Path $UvRoot 'uv.exe'
    $InstalledUvVersion = if (Test-Path $UvCommand) {
        ((& $UvCommand --version) -replace '^uv\s+', '').Trim()
    }
    else {
        $null
    }
    if ($InstalledUvVersion -ne $Artifacts.Uv.Version) {
        $Archive = Join-Path $DownloadRoot 'uv-0.8.22.zip'
        $ExtractRoot = Join-Path $DownloadRoot 'uv-0.8.22'
        Invoke-VerifiedDownload -Uri $Artifacts.Uv.Uri -Destination $Archive `
            -Algorithm SHA256 -ExpectedHash $Artifacts.Uv.Hash
        Remove-Item -Path $ExtractRoot -Recurse -Force -ErrorAction SilentlyContinue
        Expand-Archive -Path $Archive -DestinationPath $ExtractRoot -Force
        $ExtractedUv = Get-ChildItem -Path $ExtractRoot -Filter uv.exe -Recurse |
            Select-Object -First 1
        if ($null -eq $ExtractedUv) {
            throw 'The verified uv archive did not contain uv.exe.'
        }
        Assert-AuthenticodePublisher -Path $ExtractedUv.FullName -Publisher $Artifacts.Uv.Publisher
        New-Item -ItemType Directory -Path $UvRoot -Force | Out-Null
        Copy-Item -Path (Join-Path $ExtractedUv.Directory.FullName '*.exe') `
            -Destination $UvRoot -Force
    }
    Add-MachinePath -Path $UvRoot
    if (((& $UvCommand --version) -replace '^uv\s+', '').Trim() -ne $Artifacts.Uv.Version) {
        throw 'uv version verification failed.'
    }

    $UvPythonRoot = 'C:\ProgramData\uv\python'
    [Environment]::SetEnvironmentVariable('UV_PYTHON_INSTALL_DIR', $UvPythonRoot, 'Machine')
    $env:UV_PYTHON_INSTALL_DIR = $UvPythonRoot
    & $UvCommand python install 3.12.10
    if ($LASTEXITCODE -ne 0) {
        throw 'uv failed to install the pinned Python 3.12.10 runtime.'
    }
    $PythonPath = (& $UvCommand python find 3.12.10).Trim()
    if (-not (Test-Path $PythonPath)) {
        throw 'uv did not resolve the pinned Python 3.12.10 runtime.'
    }

    $Extensions = @{
        'github.copilot'                   = '1.388.0'
        'github.copilot-chat'              = '0.48.1'
        'vscjava.migrate-java-to-azure'    = '1.23.26081703'
    }
    if ($Stack -eq 'dotnet') {
        $Extensions['ms-dotnettools.vscode-dotnet-modernize'] = '1.0.1161'
        $Extensions['ms-dotnettools.upgrade-agent'] = '1.1.290'
    }
    else {
        $Extensions['vscjava.vscode-java-upgrade'] = '2.1.2'
    }

    $ExtensionRoot = 'C:\ProgramData\MicroHack\vscode-extensions'
    New-Item -ItemType Directory -Path $ExtensionRoot -Force | Out-Null
    [Environment]::SetEnvironmentVariable('VSCODE_EXTENSIONS', $ExtensionRoot, 'Machine')
    foreach ($Extension in $Extensions.GetEnumerator()) {
        & $CodeCommand --install-extension "$($Extension.Key)@$($Extension.Value)" `
            --force --extensions-dir $ExtensionRoot
        if ($LASTEXITCODE -ne 0) {
            throw "Visual Studio Code failed to install $($Extension.Key)@$($Extension.Value)."
        }
    }
    $InstalledExtensions = @(
        & $CodeCommand --list-extensions --show-versions --extensions-dir $ExtensionRoot
    )
    foreach ($Extension in $Extensions.GetEnumerator()) {
        if ($InstalledExtensions -notcontains "$($Extension.Key)@$($Extension.Value)") {
            throw "Visual Studio Code extension verification failed for $($Extension.Key)."
        }
    }
}

function Install-DotNetDatabase {
    $DotNet = @{
        Uri       = 'https://download.microsoft.com/download/6141e558-e0ef-473c-8dc2-122d381f9bc8/988b5e46-33a0-4cfe-8fb1-d8b90ec1d280/dotnet-sdk-8.0.424-win-x64.exe'
        Hash      = 'e79e34bdd8cce378786aaf8846412ff5f9ba4b035ce1869e9cbff751de6da6cd'
        Publisher = 'Microsoft Corporation'
    }
    $SqlServer = @{
        Uri       = 'https://download.microsoft.com/download/3/8/d/38de7036-2433-4207-8eae-06e247e17b25/SQLEXPR_x64_ENU.exe'
        Hash      = '2e61c8bbde6021f9026c54ad9db4bbb1227e68761d4c00a6a50a2c70fe7afe05'
        Publisher = 'Microsoft Corporation'
    }
    $SqlCmd = @{
        Uri       = 'https://github.com/microsoft/go-sqlcmd/releases/download/v1.7.0/sqlcmd-amd64.msi'
        Hash      = 'c8fc4ba484d25aa5f7687c4538f8a09052d4a6f35ccf17ff38e76c44922c627d'
        Publisher = 'Microsoft Corporation'
    }
    $SqlPackage = @{
        Uri       = 'https://download.microsoft.com/download/46a13f8c-5548-42fb-b547-7e69ebc3fcca/sqlpackage-win-x64-en-170.4.83.3.zip'
        Hash      = 'f1c80c38a6c4e55fe2b8787de9119ee52313b900a05873be9d0084102344666a'
        Publisher = 'Microsoft Corporation'
    }

    $DotNetRoot = 'C:\Program Files\dotnet'
    $DotNetCommand = Join-Path $DotNetRoot 'dotnet.exe'
    $InstalledSdks = if (Test-Path $DotNetCommand) { @(& $DotNetCommand --list-sdks) } else { @() }
    if (-not ($InstalledSdks | Where-Object { $_ -match '^8\.0\.424\s' })) {
        $Installer = Join-Path $DownloadRoot 'dotnet-sdk-8.0.424-win-x64.exe'
        Invoke-VerifiedDownload -Uri $DotNet.Uri -Destination $Installer `
            -Algorithm SHA256 -ExpectedHash $DotNet.Hash
        Assert-AuthenticodePublisher -Path $Installer -Publisher $DotNet.Publisher
        Invoke-LockedInstaller -Path $Installer -Arguments @('/install', '/quiet', '/norestart')
    }
    [Environment]::SetEnvironmentVariable('DOTNET_ROOT', $DotNetRoot, 'Machine')
    Add-MachinePath -Path $DotNetRoot
    if (-not (@(& $DotNetCommand --list-sdks) | Where-Object { $_ -match '^8\.0\.424\s' })) {
        throw '.NET SDK 8.0.424 version verification failed.'
    }

    $SqlServiceName = 'MSSQL$SQLEXPRESS'
    if ($null -eq (Get-Service -Name $SqlServiceName -ErrorAction SilentlyContinue)) {
        $Installer = Join-Path $DownloadRoot 'SQLEXPR_x64_ENU-2022.2025.01.29.exe'
        Invoke-VerifiedDownload -Uri $SqlServer.Uri -Destination $Installer `
            -Algorithm SHA256 -ExpectedHash $SqlServer.Hash
        Assert-AuthenticodePublisher -Path $Installer -Publisher $SqlServer.Publisher
        $SetupConfiguration = Join-Path $SecretRoot 'sqlserver-setup.ini'
        try {
            Save-ProtectedText -Path $SetupConfiguration -Value @"
[OPTIONS]
ACTION="Install"
FEATURES=SQLENGINE
QUIET="True"
SUPPRESSPRIVACYSTATEMENTNOTICE="True"
INSTANCENAME="SQLEXPRESS"
SECURITYMODE="SQL"
SAPWD="$DatabasePassword"
SQLSVCACCOUNT="NT AUTHORITY\NETWORK SERVICE"
TCPENABLED="1"
NPENABLED="0"
BROWSERSVCSTARTUPTYPE="Automatic"
IACCEPTSQLSERVERLICENSETERMS="True"
"@
            Invoke-LockedInstaller -Path $Installer -Arguments @(
                "/ConfigurationFile=`"$SetupConfiguration`""
            )
        }
        finally {
            Remove-ProtectedFile -Path $SetupConfiguration
        }
    }
    Set-Service -Name $SqlServiceName -StartupType Automatic
    Start-Service -Name $SqlServiceName

    $InstanceRegistry = Get-ItemProperty `
        'HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL'
    $InstanceId = $InstanceRegistry.SQLEXPRESS
    if ([string]::IsNullOrWhiteSpace($InstanceId)) {
        throw 'SQL Server Express instance registration is missing.'
    }
    $IpAllPath = "HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\$InstanceId\MSSQLServer\SuperSocketNetLib\Tcp\IPAll"
    $TcpProperties = Get-ItemProperty -Path $IpAllPath
    $RestartSql = $false
    if (-not [string]::IsNullOrEmpty($TcpProperties.TcpDynamicPorts)) {
        Set-ItemProperty -Path $IpAllPath -Name TcpDynamicPorts -Value ''
        $RestartSql = $true
    }
    if ($TcpProperties.TcpPort -ne '1433') {
        Set-ItemProperty -Path $IpAllPath -Name TcpPort -Value '1433'
        $RestartSql = $true
    }
    if ($RestartSql) {
        Restart-Service -Name $SqlServiceName -Force
    }
    Invoke-WithRetry -Description 'SQL Server Express readiness' -Action {
        if ((Get-Service -Name $SqlServiceName).Status -ne 'Running') {
            throw 'SQL Server Express is not running.'
        }
        $Client = New-Object Net.Sockets.TcpClient
        try {
            $Client.Connect('localhost', 1433)
        }
        finally {
            $Client.Dispose()
        }
    }

    $SqlCmdCommand = 'C:\Program Files\sqlcmd\sqlcmd.exe'
    if (-not (Test-Path $SqlCmdCommand)) {
        $Installer = Join-Path $DownloadRoot 'sqlcmd-1.7.0-amd64.msi'
        Invoke-VerifiedDownload -Uri $SqlCmd.Uri -Destination $Installer `
            -Algorithm SHA256 -ExpectedHash $SqlCmd.Hash
        Assert-AuthenticodePublisher -Path $Installer -Publisher $SqlCmd.Publisher
        Invoke-LockedInstaller -Path 'msiexec.exe' -Arguments @(
            '/i',
            "`"$Installer`"",
            '/qn',
            '/norestart'
        )
    }
    if (-not (Test-Path $SqlCmdCommand)) {
        $SqlCmdCommand = (
            Get-ChildItem -Path 'C:\Program Files' -Filter sqlcmd.exe -Recurse |
                Select-Object -First 1
        ).FullName
    }
    if ([string]::IsNullOrWhiteSpace($SqlCmdCommand) -or -not (Test-Path $SqlCmdCommand)) {
        throw 'The pinned go-sqlcmd client was not found after installation.'
    }
    if ((& $SqlCmdCommand --version 2>&1) -notmatch '1\.7\.0') {
        throw 'go-sqlcmd version verification failed.'
    }

    $SqlPackageRoot = 'C:\Program Files\SqlPackage'
    $SqlPackageCommand = Join-Path $SqlPackageRoot 'SqlPackage.exe'
    $SqlPackageVersion = if (Test-Path $SqlPackageCommand) {
        (& $SqlPackageCommand /Version 2>&1 | Select-Object -First 1)
    }
    if ($SqlPackageVersion -notmatch '^170\.4\.83\.3$') {
        $Archive = Join-Path $DownloadRoot 'sqlpackage-win-x64-en-170.4.83.3.zip'
        Invoke-VerifiedDownload -Uri $SqlPackage.Uri -Destination $Archive `
            -Algorithm SHA256 -ExpectedHash $SqlPackage.Hash
        $SqlPackageStaging = "$SqlPackageRoot.staging"
        Remove-Item -LiteralPath $SqlPackageStaging -Recurse -Force `
            -ErrorAction SilentlyContinue
        Expand-Archive -LiteralPath $Archive -DestinationPath $SqlPackageStaging -Force
        $StagedSqlPackage = Join-Path $SqlPackageStaging 'SqlPackage.exe'
        if (-not (Test-Path -LiteralPath $StagedSqlPackage -PathType Leaf)) {
            throw 'The pinned SqlPackage archive did not contain SqlPackage.exe.'
        }
        Assert-AuthenticodePublisher -Path $StagedSqlPackage `
            -Publisher $SqlPackage.Publisher
        if ((& $StagedSqlPackage /Version 2>&1 | Select-Object -First 1) -notmatch
            '^170\.4\.83\.3$') {
            throw 'SqlPackage staged version verification failed.'
        }
        Install-StagedDirectory -StagingPath $SqlPackageStaging `
            -DestinationPath $SqlPackageRoot
    }
    Add-MachinePath -Path $SqlPackageRoot
    if ((& $SqlPackageCommand /Version 2>&1 | Select-Object -First 1) -notmatch
        '^170\.4\.83\.3$') {
        throw 'SqlPackage version verification failed.'
    }

    $env:SQLCMDPASSWORD = $DatabasePassword
    $SqlIdentity = (
        & $SqlCmdCommand -S 'localhost,1433' -U sa -h -1 -W `
            -Q "SET NOCOUNT ON; SELECT CONCAT(SERVERPROPERTY('ProductMajorVersion'), '|', SERVERPROPERTY('Edition'));" |
            Where-Object { $_ -match '^\s*16\|.*Express' } |
            Select-Object -First 1
    )
    if ([string]::IsNullOrWhiteSpace($SqlIdentity)) {
        throw 'The local database is not SQL Server 2022 Express.'
    }

    $EscapedPassword = $DatabasePassword.Replace("'", "''")
    $SqlInput = Join-Path $SecretRoot 'sqlserver-login.sql'
    try {
        Save-ProtectedText -Path $SqlInput -Value @"
IF DB_ID(N'LegoCatalog') IS NULL CREATE DATABASE [LegoCatalog];
IF NOT EXISTS (SELECT 1 FROM sys.sql_logins WHERE name = N'catalog')
    CREATE LOGIN [catalog] WITH PASSWORD = N'$EscapedPassword', CHECK_POLICY = ON;
ELSE
    ALTER LOGIN [catalog] WITH PASSWORD = N'$EscapedPassword';
USE [LegoCatalog];
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'catalog')
BEGIN
    CREATE USER [catalog] FOR LOGIN [catalog];
    ALTER ROLE [db_owner] ADD MEMBER [catalog];
END;
"@
        & $SqlCmdCommand -S 'localhost,1433' -U sa -b -i $SqlInput | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw 'SQL Server database and login provisioning failed.'
        }
    }
    finally {
        Remove-ProtectedFile -Path $SqlInput
    }

    return @{
        DotNetCommand = $DotNetCommand
        SqlCmdCommand = $SqlCmdCommand
    }
}

function Install-JavaDatabase {
    $Java = @{
        Uri       = 'https://aka.ms/download-jdk/microsoft-jdk-17.0.20-windows-x64.msi#winget'
        Hash      = '96115e7ba251f476544e38f4b214562b57b609618d64533dff1104bb74d328fc'
        Publisher = 'Microsoft Corporation'
    }
    $PostgreSql = @{
        Uri       = 'https://get.enterprisedb.com/postgresql/postgresql-18.6-1-windows-x64.exe'
        Hash      = 'cae561e98d09f3f4a1a95759249240f86f66d71dcf33d14b6f7be894078401d1'
        Publisher = 'EnterpriseDB Corporation'
    }
    $Maven = @{
        Uri  = 'https://archive.apache.org/dist/maven/maven-3/3.9.16/binaries/apache-maven-3.9.16-bin.zip'
        Hash = 'ed41650d42485cfc243fad22158caf9cbb5dc408ce7a09ddb94dd42a019de929ca43065bfa450612cf12bf78b5cafa3884b96c090de326ff590448c933454af3'
    }

    $JavaRoot = 'C:\Program Files\Microsoft\jdk-17.0.20.8-hotspot'
    $JavaCommand = Join-Path $JavaRoot 'bin\java.exe'
    $InstalledJava = if (Test-Path $JavaCommand) { (& $JavaCommand -version 2>&1) -join "`n" } else { '' }
    if ($InstalledJava -notmatch 'build 17\.0\.20\+8') {
        $Installer = Join-Path $DownloadRoot 'microsoft-jdk-17.0.20-windows-x64.msi'
        Invoke-VerifiedDownload -Uri $Java.Uri -Destination $Installer `
            -Algorithm SHA256 -ExpectedHash $Java.Hash
        Assert-AuthenticodePublisher -Path $Installer -Publisher $Java.Publisher
        Invoke-LockedInstaller -Path 'msiexec.exe' -Arguments @(
            '/i',
            "`"$Installer`"",
            '/qn',
            '/norestart',
            'ADDLOCAL=FeatureMain,FeatureEnvironment,FeatureJarFileRunWith,FeatureJavaHome'
        )
        $JavaCommand = (
            Get-ChildItem -Path 'C:\Program Files\Microsoft' -Filter java.exe -Recurse |
                Where-Object { $_.FullName -match 'jdk-17\.0\.20' } |
                Select-Object -First 1
        ).FullName
        $JavaRoot = Split-Path (Split-Path $JavaCommand -Parent) -Parent
    }
    if ([string]::IsNullOrWhiteSpace($JavaCommand) -or -not (Test-Path $JavaCommand)) {
        throw 'Microsoft OpenJDK 17.0.20+8 was not found after installation.'
    }
    [Environment]::SetEnvironmentVariable('JAVA_HOME', $JavaRoot, 'Machine')
    $env:JAVA_HOME = $JavaRoot
    Add-MachinePath -Path (Join-Path $JavaRoot 'bin')
    if (((& $JavaCommand -version 2>&1) -join "`n") -notmatch 'build 17\.0\.20\+8') {
        throw 'Microsoft OpenJDK version verification failed.'
    }

    $PostgreSqlRoot = 'C:\Program Files\PostgreSQL\18'
    $PsqlCommand = Join-Path $PostgreSqlRoot 'bin\psql.exe'
    $PostgreSqlService = 'postgresql-x64-18'
    if ($null -eq (Get-Service -Name $PostgreSqlService -ErrorAction SilentlyContinue)) {
        $Installer = Join-Path $DownloadRoot 'postgresql-18.6-1-windows-x64.exe'
        Invoke-VerifiedDownload -Uri $PostgreSql.Uri -Destination $Installer `
            -Algorithm SHA256 -ExpectedHash $PostgreSql.Hash
        Assert-AuthenticodePublisher -Path $Installer -Publisher $PostgreSql.Publisher
        $SetupOptions = Join-Path $SecretRoot 'postgresql-setup.conf'
        try {
            Save-ProtectedText -Path $SetupOptions -Value @"
mode=unattended
unattendedmodeui=none
prefix=$PostgreSqlRoot
datadir=$PostgreSqlRoot\data
serverport=5432
servicename=$PostgreSqlService
superaccount=postgres
superpassword=$DatabasePassword
"@
            Invoke-LockedInstaller -Path $Installer -Arguments @(
                '--optionfile',
                "`"$SetupOptions`""
            )
        }
        finally {
            Remove-ProtectedFile -Path $SetupOptions
        }
    }
    Set-Service -Name $PostgreSqlService -StartupType Automatic
    Start-Service -Name $PostgreSqlService
    if (-not (Test-Path $PsqlCommand)) {
        throw 'The PostgreSQL 18.6 psql client was not found after installation.'
    }
    if ((& $PsqlCommand --version) -notmatch '18\.6') {
        throw 'PostgreSQL client version verification failed.'
    }

    $env:PGPASSWORD = $DatabasePassword
    Invoke-WithRetry -Description 'PostgreSQL readiness' -Action {
        & $PsqlCommand -h localhost -p 5432 -U postgres -d postgres -v ON_ERROR_STOP=1 `
            -tAc 'SELECT 1' | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw 'PostgreSQL is not accepting local connections.'
        }
        $PostgreSqlVersion = (
            & $PsqlCommand -h localhost -p 5432 -U postgres -d postgres -tAc `
                'SHOW server_version'
        ).Trim()
        if ($PostgreSqlVersion -notmatch '^18\.6(?:\s|$)') {
            throw "The local PostgreSQL server version is $PostgreSqlVersion instead of 18.6."
        }
    }
    $EscapedPassword = $DatabasePassword.Replace("'", "''")
    $RoleExists = (& $PsqlCommand -h localhost -p 5432 -U postgres -d postgres -tAc `
            "SELECT 1 FROM pg_roles WHERE rolname = 'catalog'").Trim()
    $RoleInput = Join-Path $SecretRoot 'postgresql-role.sql'
    try {
        $RoleSql = if ($RoleExists -ne '1') {
            "CREATE ROLE catalog LOGIN PASSWORD '$EscapedPassword';"
        }
        else {
            "ALTER ROLE catalog PASSWORD '$EscapedPassword';"
        }
        Save-ProtectedText -Path $RoleInput -Value $RoleSql
        & $PsqlCommand -h localhost -p 5432 -U postgres -d postgres -v ON_ERROR_STOP=1 `
            -f $RoleInput | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw 'PostgreSQL application role provisioning failed.'
        }
    }
    finally {
        Remove-ProtectedFile -Path $RoleInput
        $RoleSql = $null
    }
    $DatabaseExists = (& $PsqlCommand -h localhost -p 5432 -U postgres -d postgres -tAc `
            "SELECT 1 FROM pg_database WHERE datname = 'catalog'").Trim()
    if ($DatabaseExists -ne '1') {
        & $PsqlCommand -h localhost -p 5432 -U postgres -d postgres -v ON_ERROR_STOP=1 `
            -c 'CREATE DATABASE catalog OWNER catalog' | Out-Null
    }
    else {
        & $PsqlCommand -h localhost -p 5432 -U postgres -d postgres -v ON_ERROR_STOP=1 `
            -c 'ALTER DATABASE catalog OWNER TO catalog' | Out-Null
    }
    if ($LASTEXITCODE -ne 0) {
        throw 'PostgreSQL application database provisioning failed.'
    }

    $MavenArchive = Join-Path $DownloadRoot 'apache-maven-3.9.16-bin.zip'
    $MavenRoot = 'C:\Program Files\Apache\maven-3.9.16'
    Invoke-VerifiedDownload -Uri $Maven.Uri -Destination $MavenArchive `
        -Algorithm SHA512 -ExpectedHash $Maven.Hash
    if (-not (Test-Path (Join-Path $MavenRoot 'bin\mvn.cmd'))) {
        $MavenExtract = Join-Path $DownloadRoot 'maven-3.9.16'
        Remove-Item -Path $MavenExtract -Recurse -Force -ErrorAction SilentlyContinue
        Expand-Archive -Path $MavenArchive -DestinationPath $MavenExtract -Force
        $ExtractedMaven = Get-ChildItem -Path $MavenExtract -Directory |
            Where-Object { Test-Path (Join-Path $_.FullName 'bin\mvn.cmd') } |
            Select-Object -First 1
        if ($null -eq $ExtractedMaven) {
            throw 'The verified Maven archive did not contain mvn.cmd.'
        }
        New-Item -ItemType Directory -Path (Split-Path $MavenRoot -Parent) -Force | Out-Null
        Remove-Item -Path $MavenRoot -Recurse -Force -ErrorAction SilentlyContinue
        Move-Item -Path $ExtractedMaven.FullName -Destination $MavenRoot
    }
    [Environment]::SetEnvironmentVariable('MAVEN_HOME', $MavenRoot, 'Machine')
    Add-MachinePath -Path (Join-Path $MavenRoot 'bin')
    if ((& (Join-Path $MavenRoot 'bin\mvn.cmd') --version | Select-Object -First 1) -notmatch '3\.9\.16') {
        throw 'Apache Maven version verification failed.'
    }

    return @{
        JavaCommand = $JavaCommand
        PsqlCommand = $PsqlCommand
        MavenRoot   = $MavenRoot
    }
}

function Install-SourceArchive {
    $Archive = Join-Path $DownloadRoot "source-$SourceCommit.zip"
    Invoke-VerifiedDownload -Uri $SourceArchiveUrl -Destination $Archive `
        -Algorithm SHA256 -ExpectedHash $SourceArchiveSha256

    $Staging = Join-Path $Root "source-$SourceCommit.staging"
    Remove-Item -Path $Staging -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $Staging -Force | Out-Null
    Expand-Archive -Path $Archive -DestinationPath $Staging -Force
    $ArchiveRoot = Get-ChildItem -Path $Staging -Directory | Select-Object -First 1
    if ($null -eq $ArchiveRoot -or
        -not (Test-Path (Join-Path $ArchiveRoot.FullName 'data\manifest.json')) -or
        -not (Test-Path (Join-Path $ArchiveRoot.FullName 'dotnet')) -or
        -not (Test-Path (Join-Path $ArchiveRoot.FullName 'java'))) {
        throw 'The verified source archive is missing required frozen application content.'
    }

    $Previous = Join-Path $Root 'source.previous'
    Remove-Item -Path $Previous -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $SourceRoot) {
        Move-Item -Path $SourceRoot -Destination $Previous
    }
    try {
        Move-Item -Path $ArchiveRoot.FullName -Destination $SourceRoot
        $CommitMarker = Join-Path $SourceRoot '.source-commit'
        Set-Content -Path $CommitMarker -Value $SourceCommit -Encoding ASCII
        Remove-Item -Path $Previous -Recurse -Force -ErrorAction SilentlyContinue
    }
    catch {
        Remove-Item -Path $SourceRoot -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path $Previous) {
            Move-Item -Path $Previous -Destination $SourceRoot
        }
        throw
    }
    finally {
        Remove-Item -Path $Staging -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Assert-CanonicalData {
    $ManifestPath = Join-Path $SourceRoot 'data\manifest.json'
    $CatalogPath = Join-Path $SourceRoot 'data\catalog.json'
    $CategoriesPath = Join-Path $SourceRoot 'data\categories.json'
    $ImagesPath = Join-Path $SourceRoot 'data\images'
    $Manifest = Get-Content -Path $ManifestPath -Raw | ConvertFrom-Json
    $Catalog = @(Get-Content -Path $CatalogPath -Raw | ConvertFrom-Json)
    $Categories = @(Get-Content -Path $CategoriesPath -Raw | ConvertFrom-Json)
    $Images = @(Get-ChildItem -Path $ImagesPath -File -Filter '*.png')

    if ($Manifest.counts.figures -ne 198 -or
        $Manifest.counts.categories -ne 20 -or
        $Manifest.counts.images -ne 198 -or
        $Catalog.Count -ne 198 -or
        $Categories.Count -ne 20 -or
        $Images.Count -ne 198) {
        throw 'Canonical data does not contain 198 figures, 20 categories, and 198 images.'
    }
    if ((Get-FileHash -Path $CatalogPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne
        $Manifest.hashes.catalogSha256) {
        throw 'Canonical catalog digest does not match data/manifest.json.'
    }
    if ((Get-FileHash -Path $CategoriesPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne
        $Manifest.hashes.categoriesSha256) {
        throw 'Canonical category digest does not match data/manifest.json.'
    }
}

function ConvertFrom-WindowsCommandLine {
    param(
        [Parameter(Mandatory)]
        [string]$CommandLine
    )

    if ($null -eq ('MicroHack.NativeCommandLine' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;

namespace MicroHack
{
    public static class NativeCommandLine
    {
        [DllImport("shell32.dll", SetLastError = true)]
        private static extern IntPtr CommandLineToArgvW(
            [MarshalAs(UnmanagedType.LPWStr)] string commandLine,
            out int argumentCount
        );

        [DllImport("kernel32.dll")]
        private static extern IntPtr LocalFree(IntPtr memory);

        public static string[] Split(string commandLine)
        {
            int argumentCount;
            IntPtr argumentVector = CommandLineToArgvW(commandLine, out argumentCount);
            if (argumentVector == IntPtr.Zero)
            {
                throw new Win32Exception(Marshal.GetLastWin32Error());
            }

            try
            {
                string[] arguments = new string[argumentCount];
                for (int index = 0; index < argumentCount; index++)
                {
                    IntPtr argument = Marshal.ReadIntPtr(
                        argumentVector,
                        index * IntPtr.Size
                    );
                    arguments[index] = Marshal.PtrToStringUni(argument);
                }
                return arguments;
            }
            finally
            {
                LocalFree(argumentVector);
            }
        }
    }
}
'@ | Out-Null
    }

    return [MicroHack.NativeCommandLine]::Split($CommandLine)
}

function Get-StackApplicationProcesses {
    $Executable = if ($Stack -eq 'dotnet') { 'dotnet.exe' } else { 'java.exe' }
    $ApplicationArgument = if ($Stack -eq 'dotnet') {
        'C:\MicroHack\app\dotnet\LegoCatalog.App.dll'
    }
    else {
        'C:\MicroHack\app\java\catalog-java.jar'
    }

    return @(
        Get-CimInstance -ClassName Win32_Process -Filter "Name = '$Executable'" |
            Where-Object {
                if ([string]::IsNullOrWhiteSpace($_.CommandLine)) {
                    $false
                }
                else {
                    $Arguments = @(ConvertFrom-WindowsCommandLine -CommandLine $_.CommandLine)
                    if ($Stack -eq 'dotnet') {
                        $Arguments.Count -ge 2 -and $Arguments[1].Equals(
                            $ApplicationArgument,
                            [StringComparison]::OrdinalIgnoreCase
                        )
                    }
                    else {
                        $Arguments.Count -ge 3 -and
                            $Arguments[1].Equals(
                                '-jar',
                                [StringComparison]::OrdinalIgnoreCase
                            ) -and
                            $Arguments[2].Equals(
                                $ApplicationArgument,
                                [StringComparison]::OrdinalIgnoreCase
                            )
                    }
                }
            }
    )
}

function Stop-ApplicationTask {
    $TaskName = "MicroHack-$Stack"
    $Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -ne $Existing) {
        Write-ProvisionLog "Disabling $TaskName before replacing source or application output."
        Disable-ScheduledTask -TaskName $TaskName | Out-Null
        $Current = Get-ScheduledTask -TaskName $TaskName
        if ($Current.State -eq 'Running') {
            Stop-ScheduledTask -TaskName $TaskName
        }
    }

    for ($Attempt = 1; $Attempt -le 60; $Attempt++) {
        $Processes = @(Get-StackApplicationProcesses)
        if ($Processes.Count -eq 0) {
            return
        }
        foreach ($Process in $Processes) {
            Stop-Process -Id $Process.ProcessId -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 1
    }

    throw "$TaskName or its exact stack application process did not stop within 60 seconds."
}

function Install-StagedDirectory {
    param(
        [Parameter(Mandatory)]
        [string]$StagingPath,

        [Parameter(Mandatory)]
        [string]$DestinationPath
    )

    $PreviousPath = "$DestinationPath.previous"
    if (-not (Test-Path -LiteralPath $StagingPath -PathType Container)) {
        throw "Staged application directory is missing: $StagingPath"
    }
    if (-not (Test-Path -LiteralPath $DestinationPath) -and
        (Test-Path -LiteralPath $PreviousPath -PathType Container)) {
        Move-Item -LiteralPath $PreviousPath -Destination $DestinationPath
    }
    if ((Test-Path -LiteralPath $DestinationPath) -and
        -not (Test-Path -LiteralPath $DestinationPath -PathType Container)) {
        throw "Current application path is not a directory: $DestinationPath"
    }

    if (Test-Path -LiteralPath $DestinationPath -PathType Container) {
        Remove-Item -Path $PreviousPath -Recurse -Force -ErrorAction SilentlyContinue
        Move-Item -LiteralPath $DestinationPath -Destination $PreviousPath
    }
    try {
        Move-Item -LiteralPath $StagingPath -Destination $DestinationPath
        Remove-Item -Path $PreviousPath -Recurse -Force -ErrorAction SilentlyContinue
    }
    catch {
        Remove-Item -Path $DestinationPath -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath $PreviousPath) {
            Move-Item -LiteralPath $PreviousPath -Destination $DestinationPath
        }
        throw
    }
}

function Register-ApplicationTask {
    param(
        [Parameter(Mandatory)]
        [string]$ScriptPath
    )

    $TaskName = "MicroHack-$Stack"
    $Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -ne $Existing -and $Existing.State -eq 'Running') {
        throw "$TaskName must be stopped before task registration."
    }
    $Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument (
        "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$ScriptPath`""
    )
    $Trigger = New-ScheduledTaskTrigger -AtStartup
    $Principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount `
        -RunLevel Highest
    $Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 5 `
        -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
        -Principal $Principal -Settings $Settings -Force | Out-Null
    Enable-ScheduledTask -TaskName $TaskName | Out-Null
    Start-ScheduledTask -TaskName $TaskName
}

function Publish-DotNetApplication {
    param(
        [Parameter(Mandatory)]
        [string]$DotNetCommand,

        [Parameter(Mandatory)]
        [string]$SqlCmdCommand
    )

    $Project = Join-Path $SourceRoot 'dotnet\src\LegoCatalog.App\LegoCatalog.App.csproj'
    $DotNetSource = Join-Path $SourceRoot 'dotnet'
    @{
        sdk = @{
            version     = '8.0.424'
            rollForward = 'disable'
        }
    } | ConvertTo-Json -Depth 3 | Set-Content `
        -Path (Join-Path $DotNetSource 'global.json') -Encoding UTF8
    $PublishRoot = Join-Path $ApplicationRoot 'dotnet'
    $PublishStaging = "$PublishRoot.staging"
    Remove-Item -Path $PublishStaging -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $PublishStaging -Force | Out-Null
    Push-Location $DotNetSource
    try {
        & $DotNetCommand publish $Project --configuration Release --output $PublishStaging
        if ($LASTEXITCODE -ne 0) {
            throw '.NET application publish failed.'
        }
    }
    finally {
        Pop-Location
    }
    if (-not (Test-Path (Join-Path $PublishStaging 'LegoCatalog.App.dll'))) {
        throw '.NET staged publish is missing LegoCatalog.App.dll.'
    }
    Install-StagedDirectory -StagingPath $PublishStaging -DestinationPath $PublishRoot

    $ConfigurationPath = Join-Path $SecretRoot 'dotnet.json'
    Save-ProtectedConfiguration -Path $ConfigurationPath -Values @{
        DatabasePassword = $DatabasePassword
        PerformanceApiKey = $PerformanceApiKey
    }
    $StartScript = Join-Path $Root 'start-dotnet.ps1'
    @'
$ErrorActionPreference = 'Stop'

function Invoke-BoundedNativeProbe {
    param(
        [Parameter(Mandatory)]
        [string]$FilePath,

        [Parameter(Mandatory)]
        [string[]]$ArgumentList,

        [Parameter(Mandatory)]
        [int]$TimeoutMilliseconds,

        [Parameter(Mandatory)]
        [string]$Description
    )

    $Process = $null
    try {
        $Process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList `
            -WindowStyle Hidden -PassThru
        if (-not $Process.WaitForExit($TimeoutMilliseconds)) {
            $ProcessId = $Process.Id
            Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
            $Process.WaitForExit(5000) | Out-Null
            throw "$Description exceeded its process deadline."
        }
        if ($Process.ExitCode -ne 0) {
            throw "$Description exited with code $($Process.ExitCode)."
        }
    }
    finally {
        if ($null -ne $Process) {
            if (-not $Process.HasExited) {
                Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
            }
            $Process.Dispose()
        }
    }
}

$Configuration = Get-Content 'C:\MicroHack\secrets\dotnet.json' -Raw | ConvertFrom-Json
$DatabaseReady = $false
$LastDatabaseError = 'SQL Server readiness was not attempted.'
$ReadinessDeadline = [DateTime]::UtcNow.AddMinutes(5)
while (-not $DatabaseReady -and [DateTime]::UtcNow -lt $ReadinessDeadline) {
    try {
        if ((Get-Service -Name 'MSSQL$SQLEXPRESS').Status -ne 'Running') {
            throw 'SQL Server Express service is not running.'
        }
        $RemainingMilliseconds = [int][Math]::Max(
            1,
            [Math]::Min(
                10000,
                ($ReadinessDeadline - [DateTime]::UtcNow).TotalMilliseconds
            )
        )
        $env:SQLCMDPASSWORD = $Configuration.DatabasePassword
        Invoke-BoundedNativeProbe -FilePath '__SQLCMD_COMMAND__' -ArgumentList @(
            '-S',
            'localhost,1433',
            '-U',
            'catalog',
            '-d',
            'LegoCatalog',
            '-b',
            '-l',
            '5',
            '-t',
            '5',
            '-Q',
            '"SET NOCOUNT ON; SELECT 1;"'
        ) -TimeoutMilliseconds $RemainingMilliseconds -Description 'sqlcmd readiness probe'
        $DatabaseReady = $true
    }
    catch {
        $LastDatabaseError = $_.Exception.Message -replace '[\r\n]+', ' '
    }
    finally {
        $env:SQLCMDPASSWORD = $null
    }
    if (-not $DatabaseReady) {
        $SleepMilliseconds = [int][Math]::Max(
            0,
            [Math]::Min(
                5000,
                ($ReadinessDeadline - [DateTime]::UtcNow).TotalMilliseconds
            )
        )
        if ($SleepMilliseconds -gt 0) {
            Start-Sleep -Milliseconds $SleepMilliseconds
        }
    }
}
if (-not $DatabaseReady) {
    $Failure = '{0} [dotnet] SQL Server readiness failed after five minutes: {1}' -f `
        [DateTime]::UtcNow.ToString('o'), $LastDatabaseError
    Add-Content -LiteralPath 'C:\MicroHack\logs\dotnet-app.log' -Value $Failure -Encoding UTF8
    throw $Failure
}
$env:CATALOG_DATABASE_HOST = 'localhost'
$env:CATALOG_DATABASE_PORT = '1433'
$env:CATALOG_DATABASE_NAME = 'LegoCatalog'
$env:CATALOG_DATABASE_USERNAME = 'catalog'
$env:CATALOG_DATABASE_PASSWORD = $Configuration.DatabasePassword
$env:CATALOG_IMAGES_PATH = 'C:\MicroHack\source\data\images'
$env:CATALOG_SEED_PATH = 'C:\MicroHack\source\data\catalog.json'
$env:CATALOG_STARTUP_IMPORT_ENABLED = 'true'
$env:PERFTEST_API_KEY = $Configuration.PerformanceApiKey
$env:PERFTEST_WORK_FACTOR = '10'
$env:OTEL_SERVICE_VERSION = '__SOURCE_COMMIT__'
$env:DEPLOYMENT_ENVIRONMENT = 'lab'
$env:CONTAINER_APP_REVISION = 'facilitator-vm'
$env:ASPNETCORE_URLS = 'http://0.0.0.0:5000'
& 'C:\Program Files\dotnet\dotnet.exe' 'C:\MicroHack\app\dotnet\LegoCatalog.App.dll' `
    *>> 'C:\MicroHack\logs\dotnet-app.log'
exit $LASTEXITCODE
'@.Replace('__SOURCE_COMMIT__', $SourceCommit).Replace('__SQLCMD_COMMAND__', $SqlCmdCommand) |
        Set-Content -Path $StartScript -Encoding UTF8
    Register-ApplicationTask -ScriptPath $StartScript
}

function Publish-JavaApplication {
    param(
        [Parameter(Mandatory)]
        [hashtable]$JavaTools
    )

    $JavaSource = Join-Path $SourceRoot 'java'
    $MavenProperties = Get-Content `
        (Join-Path $JavaSource '.mvn\wrapper\maven-wrapper.properties') -Raw |
        ConvertFrom-StringData
    if ($MavenProperties.distributionUrl -notmatch '/apache-maven/3\.9\.16/' -or
        $MavenProperties.distributionSha256Sum -ne
        '5af3b743dd8b876b5c45da33b676251e5f1687712644abb4ee519ca56e1d89ce') {
        throw 'The frozen Maven Wrapper distribution contract is not present.'
    }

    $MavenUserHome = 'C:\ProgramData\MicroHack\m2'
    $DistributionName = 'apache-maven-3.9.16'
    $UrlBytes = [byte[]][char[]]$MavenProperties.distributionUrl
    $UrlHash = (
        [Security.Cryptography.SHA256]::Create().ComputeHash($UrlBytes) |
            ForEach-Object { $_.ToString('x2') }
    ) -join ''
    $WrapperHome = Join-Path $MavenUserHome "wrapper\dists\$DistributionName\$UrlHash"
    if (-not (Test-Path (Join-Path $WrapperHome 'bin\mvn.cmd'))) {
        New-Item -ItemType Directory -Path $WrapperHome -Force | Out-Null
        Copy-Item -Path (Join-Path $JavaTools.MavenRoot '*') -Destination $WrapperHome `
            -Recurse -Force
    }

    $env:JAVA_HOME = Split-Path (Split-Path $JavaTools.JavaCommand -Parent) -Parent
    $env:MAVEN_USER_HOME = $MavenUserHome
    Push-Location $JavaSource
    try {
        & '.\mvnw.cmd' -DskipTests package
        if ($LASTEXITCODE -ne 0) {
            throw 'Java application Maven Wrapper package failed.'
        }
    }
    finally {
        Pop-Location
    }

    $Jar = Get-ChildItem -Path (Join-Path $JavaSource 'target') `
        -Filter 'catalog-java-*.jar' -File |
        Where-Object { $_.Name -notmatch '\.original$' } |
        Select-Object -First 1
    if ($null -eq $Jar) {
        throw 'The Java package did not produce the expected application JAR.'
    }
    $PublishRoot = Join-Path $ApplicationRoot 'java'
    $PublishStaging = "$PublishRoot.staging"
    Remove-Item -Path $PublishStaging -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $PublishStaging -Force | Out-Null
    Copy-Item -Path $Jar.FullName `
        -Destination (Join-Path $PublishStaging 'catalog-java.jar') -Force
    if (-not (Test-Path (Join-Path $PublishStaging 'catalog-java.jar'))) {
        throw 'Java staged publish is missing catalog-java.jar.'
    }
    Install-StagedDirectory -StagingPath $PublishStaging -DestinationPath $PublishRoot

    $ConfigurationPath = Join-Path $SecretRoot 'java.json'
    Save-ProtectedConfiguration -Path $ConfigurationPath -Values @{
        DatabasePassword = $DatabasePassword
        PerformanceApiKey = $PerformanceApiKey
    }
    $StartScript = Join-Path $Root 'start-java.ps1'
    @'
$ErrorActionPreference = 'Stop'

function Invoke-BoundedNativeProbe {
    param(
        [Parameter(Mandatory)]
        [string]$FilePath,

        [Parameter(Mandatory)]
        [string[]]$ArgumentList,

        [Parameter(Mandatory)]
        [int]$TimeoutMilliseconds,

        [Parameter(Mandatory)]
        [string]$Description
    )

    $Process = $null
    try {
        $Process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList `
            -WindowStyle Hidden -PassThru
        if (-not $Process.WaitForExit($TimeoutMilliseconds)) {
            $ProcessId = $Process.Id
            Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
            $Process.WaitForExit(5000) | Out-Null
            throw "$Description exceeded its process deadline."
        }
        if ($Process.ExitCode -ne 0) {
            throw "$Description exited with code $($Process.ExitCode)."
        }
    }
    finally {
        if ($null -ne $Process) {
            if (-not $Process.HasExited) {
                Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
            }
            $Process.Dispose()
        }
    }
}

$Configuration = Get-Content 'C:\MicroHack\secrets\java.json' -Raw | ConvertFrom-Json
$DatabaseReady = $false
$LastDatabaseError = 'PostgreSQL readiness was not attempted.'
$ReadinessDeadline = [DateTime]::UtcNow.AddMinutes(5)
while (-not $DatabaseReady -and [DateTime]::UtcNow -lt $ReadinessDeadline) {
    try {
        if ((Get-Service -Name 'postgresql-x64-18').Status -ne 'Running') {
            throw 'PostgreSQL service is not running.'
        }
        $RemainingMilliseconds = [int][Math]::Max(
            1,
            [Math]::Min(
                10000,
                ($ReadinessDeadline - [DateTime]::UtcNow).TotalMilliseconds
            )
        )
        $env:PGPASSWORD = $Configuration.DatabasePassword
        $env:PGCONNECT_TIMEOUT = '5'
        $env:PGOPTIONS = '-c statement_timeout=5000'
        Invoke-BoundedNativeProbe `
            -FilePath 'C:\Program Files\PostgreSQL\18\bin\psql.exe' `
            -ArgumentList @(
            '-h',
            'localhost',
            '-p',
            '5432',
            '-U',
            'catalog',
            '-d',
            'catalog',
            '-w',
            '-v',
            'ON_ERROR_STOP=1',
            '-tAc',
            '"SELECT 1;"'
        ) -TimeoutMilliseconds $RemainingMilliseconds -Description 'psql readiness probe'
        $DatabaseReady = $true
    }
    catch {
        $LastDatabaseError = $_.Exception.Message -replace '[\r\n]+', ' '
    }
    finally {
        $env:PGPASSWORD = $null
        $env:PGCONNECT_TIMEOUT = $null
        $env:PGOPTIONS = $null
    }
    if (-not $DatabaseReady) {
        $SleepMilliseconds = [int][Math]::Max(
            0,
            [Math]::Min(
                5000,
                ($ReadinessDeadline - [DateTime]::UtcNow).TotalMilliseconds
            )
        )
        if ($SleepMilliseconds -gt 0) {
            Start-Sleep -Milliseconds $SleepMilliseconds
        }
    }
}
if (-not $DatabaseReady) {
    $Failure = '{0} [java] PostgreSQL readiness failed after five minutes: {1}' -f `
        [DateTime]::UtcNow.ToString('o'), $LastDatabaseError
    Add-Content -LiteralPath 'C:\MicroHack\logs\java-app.log' -Value $Failure -Encoding UTF8
    throw $Failure
}
$env:CATALOG_DATABASE_HOST = 'localhost'
$env:CATALOG_DATABASE_PORT = '5432'
$env:CATALOG_DATABASE_NAME = 'catalog'
$env:CATALOG_DATABASE_USERNAME = 'catalog'
$env:CATALOG_DATABASE_PASSWORD = $Configuration.DatabasePassword
$env:CATALOG_DATABASE_SSL_MODE = 'disable'
$env:CATALOG_IMAGES_PATH = 'C:\MicroHack\source\data\images'
$env:CATALOG_SEED_PATH = 'C:\MicroHack\source\data\catalog.json'
$env:CATALOG_STARTUP_IMPORT_ENABLED = 'true'
$env:PERFTEST_API_KEY = $Configuration.PerformanceApiKey
$env:PERFTEST_WORK_FACTOR = '10'
$env:OTEL_EXPORTER_OTLP_ENDPOINT = 'http://localhost:4317'
$env:OTEL_SERVICE_VERSION = '__SOURCE_COMMIT__'
$env:DEPLOYMENT_ENVIRONMENT = 'lab'
$env:CONTAINER_APP_REVISION = 'facilitator-vm'
$env:OTEL_SDK_DISABLED = 'true'
& '__JAVA_COMMAND__' -jar 'C:\MicroHack\app\java\catalog-java.jar' `
    *>> 'C:\MicroHack\logs\java-app.log'
exit $LASTEXITCODE
'@.Replace('__SOURCE_COMMIT__', $SourceCommit).Replace('__JAVA_COMMAND__', $JavaTools.JavaCommand) |
        Set-Content -Path $StartScript -Encoding UTF8
    Register-ApplicationTask -ScriptPath $StartScript
}

function Invoke-StackSmokeCheck {
    param(
        [Parameter(Mandatory)]
        [string]$NativeClient
    )

    $Port = if ($Stack -eq 'dotnet') { 5000 } else { 8080 }
    $BaseUrl = "http://localhost:$Port"
    Invoke-WithRetry -Description "$Stack liveness" -Action {
        $Response = Invoke-WebRequest -Uri "$BaseUrl/healthz" -UseBasicParsing
        if ($Response.StatusCode -ne 200) {
            throw "Unexpected /healthz status $($Response.StatusCode)."
        }
    } -Attempts 120
    Invoke-WithRetry -Description "$Stack readiness" -Action {
        $Response = Invoke-WebRequest -Uri "$BaseUrl/readyz" -UseBasicParsing
        if ($Response.StatusCode -ne 200) {
            throw "Unexpected /readyz status $($Response.StatusCode)."
        }
    } -Attempts 120

    $Catalog = @(Get-Content (Join-Path $SourceRoot 'data\catalog.json') -Raw | ConvertFrom-Json)
    $ImageName = [string]$Catalog[0].filename
    if ($ImageName -cnotmatch '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.png$') {
        throw 'The canonical smoke image is not a lowercase UUID PNG path.'
    }
    $ImageProbe = Join-Path $env:TEMP "$Stack-canonical-image.png"
    $ImageResponse = Invoke-WebRequest -Uri "$BaseUrl/images/$ImageName" `
        -OutFile $ImageProbe -PassThru -UseBasicParsing
    if ($ImageResponse.StatusCode -ne 200 -or
        $ImageResponse.Headers.'Content-Type' -notmatch '^image/png' -or
        (Get-Item $ImageProbe).Length -le 0) {
        throw 'Canonical image smoke check failed.'
    }
    Remove-Item -Path $ImageProbe -Force

    if ($Stack -eq 'dotnet') {
        $env:SQLCMDPASSWORD = $DatabasePassword
        $FigureCount = (
            & $NativeClient -S 'localhost,1433' -U catalog `
                -d LegoCatalog -h -1 -W -Q 'SET NOCOUNT ON; SELECT COUNT(*) FROM Figures;' |
                Where-Object { $_ -match '^\s*\d+\s*$' } |
                Select-Object -First 1
        ).Trim()
        $CategoryCount = (
            & $NativeClient -S 'localhost,1433' -U catalog `
                -d LegoCatalog -h -1 -W -Q 'SET NOCOUNT ON; SELECT COUNT(*) FROM Categories;' |
                Where-Object { $_ -match '^\s*\d+\s*$' } |
                Select-Object -First 1
        ).Trim()
    }
    else {
        $env:PGPASSWORD = $DatabasePassword
        $FigureCount = (
            & $NativeClient -h localhost -p 5432 -U catalog -d catalog -tAc `
                'SELECT COUNT(*) FROM figures'
        ).Trim()
        $CategoryCount = (
            & $NativeClient -h localhost -p 5432 -U catalog -d catalog -tAc `
                'SELECT COUNT(*) FROM categories'
        ).Trim()
    }
    if ($FigureCount -ne '198' -or $CategoryCount -ne '20') {
        throw "Native database smoke check returned $FigureCount figures and $CategoryCount categories."
    }

    @{
        stack          = $Stack
        sourceCommit   = $SourceCommit
        healthRoute    = '/healthz'
        readinessRoute = '/readyz'
        canonicalImage = "/images/$ImageName"
        figures        = 198
        categories     = 20
        images         = 198
        verifiedAtUtc  = (Get-Date).ToUniversalTime().ToString('o')
    } | ConvertTo-Json | Set-Content -Path (Join-Path $StatusRoot "$Stack-smoke.json") `
        -Encoding UTF8
}

try {
    Write-ProvisionLog "Starting idempotent provisioning for source commit $SourceCommit."
    Stop-ApplicationTask
    Install-CommonTools
    Install-SourceArchive
    Assert-CanonicalData

    if ($Stack -eq 'dotnet') {
        $Tools = Install-DotNetDatabase
        Publish-DotNetApplication -DotNetCommand $Tools.DotNetCommand `
            -SqlCmdCommand $Tools.SqlCmdCommand
        Invoke-StackSmokeCheck -NativeClient $Tools.SqlCmdCommand
    }
    else {
        $Tools = Install-JavaDatabase
        Publish-JavaApplication -JavaTools $Tools
        Invoke-StackSmokeCheck -NativeClient $Tools.PsqlCommand
    }

    Write-ProvisionLog 'Provisioning and all local smoke checks completed successfully.'
}
finally {
    $DatabasePassword = $null
    $PerformanceApiKey = $null
    $env:SQLCMDPASSWORD = $null
    $env:PGPASSWORD = $null
}
