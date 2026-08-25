# Manual Java to PostgreSQL Flexible Server modernization

**Open this if** you chose [Path 1A: modernize it by hand](../../../challenges/ch01-manual/README.md)
with the Java/PostgreSQL baseline and want the complete executable form of a step, you
are stuck, or you are out of time. Working through it end to end takes 5–8 hours — the
same as the challenge, because this *is* the challenge with every command filled in.

Read the challenge first if you have not. This runbook gives you the answers; the
challenge is where the learning is.

This runbook implements registry slice `manual-java`. Run repository commands from the
repository root unless a step explicitly changes directory. Azure and migration commands
run on the existing Java legacy source VM from Challenge 0 so the frozen topology guard
can verify the host.

## Where you work

Every command here runs on the selected VM from Challenge 0, reached over Azure Bastion.
The source tree is at `C:\MicroHack\source`, extracted from a verified archive by the
provisioner. **That directory is what "the repository root" means in this and every other
workshop document.** Start each terminal with:

```powershell
cd C:\MicroHack\source
```

The VM ships a deliberately small, fully pinned toolchain. Pinned Git for Windows is part
of it, so `C:\MicroHack\source` is a real working tree: because the source arrives as a
verified archive rather than a clone, the provisioner initializes a repository there and
makes one baseline commit. There is **no Docker daemon**. Three things this runbook needs,
and where each comes from:

| You need | Use this on the VM |
| --- | --- |
| the commit that identifies your work | `git rev-parse HEAD`, taken after [Publish your work to GitHub](#publish-your-work-to-github) below. Every `--source-commit` argument, image tag, and revision suffix here carries it, and Challenge 3 checks the application source out of your repository at exactly this SHA. |
| the upstream archive this VM was built from | the marker file `C:\MicroHack\source\.source-commit`, written by the provisioner when it extracts the source archive. It is provenance only: GitHub has never seen that commit, so nothing here builds, deploys, or reports with it. |
| a container image build | the remote `az acr` build used in step 5 — it uploads the build context and builds inside Azure Container Registry, so no local daemon is required |

## Preconditions and protected inputs

The source VM must contain the exact repository commit, checked-in Maven Wrapper and lock
files, provisioned PostgreSQL 18.6 client tools, and an authenticated isolated facilitator
profile. It must also already contain the three protected parameter files this slice
deploys with, under `C:\protected\`:

| File | What it selects |
| --- | --- |
| `manual-java-bootstrap.json` | `deploymentStage=bootstrap`, `applicationRevisionRole=""` |
| `manual-java-baseline.json` | `deploymentStage=application`, `applicationRevisionRole=baseline` |
| `manual-java-release.json` | `deploymentStage=application`, `applicationRevisionRole=release` |

You do not write these. The facilitator's provisioning wrote them on this VM before the
workshop started, because they carry the only values that were knowable then: your
`resourceGroupName` and `teamName`, the exact `migrationSourceVmResourceId` and
`migrationSourceVirtualNetworkResourceId`, `facilitatorPrincipalName` and
`facilitatorPrincipalObjectId`, the `performanceApiKey` the application stage asserts on,
and this slice's fixed `stack=java-postgresql`/`imageProvider=azure-files` and
`postgresqlAuthentication` selection. Each is a standard ARM parameter document. They are
inputs; never copy one into the repository.

Two parameters are deliberately **absent** from them: `sourceCommit` and `imageDigest`.
Neither exists until you publish and build, and a placeholder that satisfied the
template's format assert would silently deploy the wrong source. You pass both on the
command line instead, and every deployment below does — a later `--parameters` overrides
the file. The PostgreSQL administrator and application passwords stay on the interactive
protected prompt, never on a command line.

Every one of the three files sets `resourceGroupName` to your own resource group.
`infra/main.bicep` asserts that `resourceGroupName` equals the group it is deployed into,
so a file naming anywhere else is refused before a single resource is touched.

The facilitator makes `PERFTEST_API_KEY` available only in the process that needs it.
Acquire each database password through the protected prompt immediately before its one
permitted command. Never place secrets in arguments, evidence, transcripts, or source.

### Publish your work to GitHub

Challenge 3 checks the application source out of **your own** GitHub repository at the
commit the handoff records, and builds `java/Dockerfile` from that checkout. A commit
that exists only on this VM satisfies neither, so publish before you record any identity.
Author `java/Dockerfile` first — step 5 states exactly what it must contain — then run
this from `C:\MicroHack\source`:

```powershell
git add --all
git commit -m 'Complete manual modernization slice manual-java'
if (git status --porcelain) {
  throw 'commit everything before recording the source commit'
}
$ParticipantRepositoryUrl = '<facilitator-provided-https-url-of-your-repository>'
if ((git remote) -contains 'origin') {
  git remote set-url origin $ParticipantRepositoryUrl
}
else {
  git remote add origin $ParticipantRepositoryUrl
}
git push --set-upstream origin workshop
if ($LASTEXITCODE -ne 0) { throw 'publishing the workshop branch failed' }
$SourceCommit = (git rev-parse HEAD).Trim()
if ($SourceCommit -cnotmatch '^[0-9a-f]{40}$') {
  throw 'the published source commit must be an exact lowercase 40-hex SHA'
}
```

The first push opens a browser sign-in through Git Credential Manager. Sign in as the
account that owns the repository; the credential is reused by every later push. Re-running
the block is safe — `git remote set-url` replaces an existing `origin` rather than failing.

`$SourceCommit` is now the pushed commit. It is what the handoff records as
`source.commitSha`, what Challenge 3 checks out, and what every `--source-commit`
argument, image tag, and revision suffix below carries. Every deployment below adds it as
`--parameters sourceCommit=$SourceCommit`, because the protected files cannot carry a
commit that did not exist when they were written, and step 3 fails closed if the deployed
target reports anything else.

The block below also reads `$ResourceGroup` out of the protected bootstrap parameters,
which already carry `resourceGroupName`. You deploy into the resource group you already
own — the one the facilitator created before the workshop, holding your two legacy VMs.
`infra\main.bicep` is resource-group scoped, does not create a resource group, and asserts
that its `resourceGroupName` matches the group it is deployed into. Nothing on this path
deploys at subscription scope, which is what keeps your rights to Owner on that one group.

```powershell
$env:AZURE_CONFIG_DIR = Join-Path $HOME '.azure-365'
$ResourceGroup = (Get-Content 'C:\protected\manual-java-bootstrap.json' -Raw |
  ConvertFrom-Json).parameters.resourceGroupName.value
if ($ResourceGroup -cnotmatch '^rg-user[0-9]{3}$') {
  throw 'the protected parameters must name your participant resource group'
}
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
# The export writes this file, so it cannot live under C:\protected: that folder holds the
# facilitator-supplied parameters and grants you read only. This is the same
# participant-writable location every path uses.
$DatabaseArtifact = 'C:\ProgramData\MicroHack\migration\catalog.dump'
New-Item -ItemType Directory -Force (Split-Path $DatabaseArtifact) | Out-Null
function Read-ProtectedValue {
  param([string]$Prompt)

  $SecureValue = Read-Host $Prompt -AsSecureString
  $Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
  try {
    $Value = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer)
  }
  finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer)
    $SecureValue.Dispose()
  }
  if ([string]::IsNullOrWhiteSpace($Value)) { throw "$Prompt is required" }
  return $Value
}
if ($SourceCommit -notmatch '^[0-9a-f]{40}$') { throw 'immutable source commit required' }
$Smoke = Get-Content 'C:\MicroHack\status\java-smoke.json' -Raw | ConvertFrom-Json
if ($Smoke.stack -cne 'java' -or $Smoke.figures -ne 198 -or $Smoke.categories -ne 20) {
  throw 'the provisioned application did not pass its baseline smoke checks'
}
New-Item -ItemType Directory -Force evidence, evidence\transient, evidence\telemetry |
  Out-Null
cd tests\acceptance
uv --no-config sync --frozen
uv --no-config run catalog-migrate --help
cd ..\..
```

Expected: the CLI exposes only `sql`, `postgresql`, `images`, `verify`, and
`render-handoff`; this slice uses `postgresql`.

## 1. Characterize the source

Run the Maven Wrapper suite and local full acceptance before changing the target:

```powershell
cd java
.\mvnw.cmd test
if ($LASTEXITCODE -ne 0) { throw 'release native tests failed' }
cd ..

cd tests\acceptance
uv --no-config run python -m catalog_acceptance `
  --profile full `
  --base-url $env:CATALOG_BASE_URL `
  --database-kind postgresql `
  --database-host $env:CATALOG_DATABASE_HOST `
  --database-port $env:CATALOG_DATABASE_PORT `
  --database-name $env:CATALOG_DATABASE_NAME `
  --database-username $env:CATALOG_DATABASE_USERNAME `
  --database-ssl-mode disable `
  --database-target local `
  --source-commit $SourceCommit `
  --output ..\..\evidence\transient\source-acceptance-report.json
cd ..\..
```

Write `evidence/baseline-backup.md` with the commit, source VM/VNet IDs, timestamps,
Surefire and acceptance results, manifest counts/hashes, configuration variable names
with values redacted, and restore owner. The backup is not complete until step 3 creates
and verifies the PostgreSQL custom archive and integrity sidecar.

**Stop:** any native or full-acceptance failure is a source defect. Resolve it before
creating or mutating a target.

## 2. Review and bootstrap PostgreSQL Flexible Server

```powershell
az bicep version
az bicep build --file infra\main.bicep
Get-ChildItem infra\modules\*.bicep | ForEach-Object {
  az bicep build --file $_.FullName
}
az deployment group what-if `
  --resource-group $ResourceGroup `
  --template-file infra\main.bicep `
  --parameters '@C:\protected\manual-java-bootstrap.json' `
  --parameters sourceCommit=$SourceCommit
```

Record the reviewed what-if, private endpoints, reciprocal source/target peering, private
DNS links, PostgreSQL Flexible Server, Azure Files share, ACR, observability, and absent
bootstrap Container App in `evidence/iac-review.md`. After explicit approval:

```powershell
$TargetJson = az deployment group create `
  --name "manual-java-bootstrap-$($SourceCommit.Substring(0,12))" `
  --resource-group $ResourceGroup `
  --template-file infra\main.bicep `
  --parameters '@C:\protected\manual-java-bootstrap.json' `
  --parameters sourceCommit=$SourceCommit `
  --query properties.outputs.targetOutput.value `
  --output json
if ($LASTEXITCODE -ne 0) { throw 'bootstrap deployment failed' }
[IO.File]::WriteAllText(
  (Join-Path (Get-Location) 'evidence\azure-target-output.json'),
  ($TargetJson -join "`n") + "`n",
  $Utf8NoBom)

$Target = Get-Content evidence\azure-target-output.json -Raw | ConvertFrom-Json
if ($Target.deploymentStage -ne 'bootstrap' -or
    $Target.stack -ne 'java-postgresql' -or
    $Target.database.family -ne 'postgresql-flexible' -or
    $Target.database.authentication -ne 'password-secret' -or
    $Target.images.provider -ne 'azure-files' -or
    $null -ne $Target.application) {
  throw 'bootstrap target differs from the frozen manual slice'
}
```

**Stop:** do not alter the contract or bypass topology validation. Bootstrap must not
create ACA.

## 3. Export, import, copy images, and verify

The frozen CLI invokes the pinned PostgreSQL 18.6 `pg_dump`/`pg_restore`. Each password is
environment-only and is cleared before the next command. Run from `tests/acceptance`:

```powershell
Push-Location tests\acceptance
try {
$Target = Get-Content ..\..\evidence\azure-target-output.json -Raw |
  ConvertFrom-Json
if ($Target.sourceCommit -cne $SourceCommit) {
  throw 'bootstrap target source commit differs from this checkout'
}
$DatabaseId = $Target.database.resourceId
$ImagesId = $Target.images.resourceId

$ExportExit = 0
try {
  Remove-Item Env:MIGRATION_TARGET_ADMINISTRATOR_PASSWORD `
    -ErrorAction SilentlyContinue
  Remove-Item Env:MIGRATION_TARGET_APPLICATION_PASSWORD `
    -ErrorAction SilentlyContinue
  $env:MIGRATION_SOURCE_DATABASE_PASSWORD = Read-ProtectedValue `
    'Source PostgreSQL database password'
  uv --no-config run catalog-migrate postgresql export `
    --source-host $env:CATALOG_DATABASE_HOST `
    --source-port $env:CATALOG_DATABASE_PORT `
    --source-database $env:CATALOG_DATABASE_NAME `
    --source-username $env:CATALOG_DATABASE_USERNAME `
    --source-commit $SourceCommit `
    --target-output ..\..\evidence\azure-target-output.json `
    --artifact $DatabaseArtifact
  $ExportExit = $LASTEXITCODE
}
finally {
  Remove-Item Env:MIGRATION_SOURCE_DATABASE_PASSWORD `
    -ErrorAction SilentlyContinue
}
if ($ExportExit -ne 0) { throw 'PostgreSQL export failed' }

$ImportExit = 0
try {
  $env:MIGRATION_TARGET_ADMINISTRATOR_PASSWORD = Read-ProtectedValue `
    'Target PostgreSQL administrator password'
  $env:MIGRATION_TARGET_APPLICATION_PASSWORD = Read-ProtectedValue `
    'Target PostgreSQL application password'
  uv --no-config run catalog-migrate postgresql import `
    --artifact $DatabaseArtifact `
    --source-commit $SourceCommit `
    --target-output ..\..\evidence\azure-target-output.json `
    --target-resource-id $DatabaseId `
    --confirm-target-resource-id $DatabaseId `
    --execute
  $ImportExit = $LASTEXITCODE
}
finally {
  Remove-Item Env:MIGRATION_TARGET_ADMINISTRATOR_PASSWORD `
    -ErrorAction SilentlyContinue
  Remove-Item Env:MIGRATION_TARGET_APPLICATION_PASSWORD `
    -ErrorAction SilentlyContinue
}
if ($ImportExit -ne 0) { throw 'PostgreSQL import failed' }

uv --no-config run catalog-migrate images copy `
  --source-directory ..\..\data\images `
  --source-commit $SourceCommit `
  --target-output ..\..\evidence\azure-target-output.json `
  --target-resource-id $ImagesId `
  --confirm-target-resource-id $ImagesId `
  --execute
if ($LASTEXITCODE -ne 0) { throw 'image copy failed' }

$VerifyExit = 0
try {
  $env:MIGRATION_TARGET_APPLICATION_PASSWORD = Read-ProtectedValue `
    'Target PostgreSQL application password for verification'
  uv --no-config run catalog-migrate verify `
    --stack java-postgresql `
    --source-commit $SourceCommit `
    --database-artifact $DatabaseArtifact `
    --target-output ..\..\evidence\azure-target-output.json `
    --output ..\..\evidence\migration-report.json
  $VerifyExit = $LASTEXITCODE
}
finally {
  Remove-Item Env:MIGRATION_TARGET_APPLICATION_PASSWORD `
    -ErrorAction SilentlyContinue
}
if ($VerifyExit -ne 0) { throw 'migration verification failed' }
}
finally { Pop-Location }
```

Append the archive/sidecar paths, sizes, hashes, creation time, and tested restore owner
to `evidence/baseline-backup.md`; never include passwords. Expected:
`evidence/migration-report.json` validates schema, Flyway history, constraints, indexes,
complete corpus, application-role grants, Azure Files bytes/hash, TLS, and source-VM
topology.

**Stop:** exit codes `2` through `5`, a nonempty-target refusal, or a failed verification
ends the attempt. Do not delete either database or rerun restore into a nonempty target.

## 4. Prove VM application/database separation

Keep compute on the source VM and point the application to the migrated managed database.
The protected application-role password remains environment-only:

```powershell
$Target = Get-Content evidence\azure-target-output.json -Raw | ConvertFrom-Json
$env:CATALOG_DATABASE_HOST = $Target.database.server
$env:CATALOG_DATABASE_PORT = '5432'
$env:CATALOG_DATABASE_NAME = $Target.database.database
$env:CATALOG_DATABASE_USERNAME = $Target.database.applicationPrincipal.name
$env:CATALOG_DATABASE_PASSWORD = Read-ProtectedValue 'Application database password'
$env:CATALOG_DATABASE_AUTHENTICATION = 'password-secret'
$env:CATALOG_DATABASE_SSL_MODE = 'require'
$env:CATALOG_STARTUP_IMPORT_ENABLED = 'false'
$env:DEPLOYMENT_ENVIRONMENT = 'lab'
$env:CONTAINER_APP_REVISION = 'source-vm-managed-database'
cd java
.\mvnw.cmd spring-boot:run
```

In a second source-VM terminal, prompt independently for the application-role password
and canonical performance key without echoing either value. Process-scoped variables
from the application terminal are deliberately not reused:

> Both terminals must name the same source commit. This one reads it back with
> `git rev-parse HEAD`, which returns the commit you published in *Publish your work to
> GitHub*. This runbook changes no code after that point, so the two terminals agree by
> construction. Do not substitute the `.source-commit` marker here: that is archive
> provenance, and Challenge 3 cannot check it out.

```powershell
function Read-ProtectedValue {
  param([string]$Prompt)

  $SecureValue = Read-Host $Prompt -AsSecureString
  $Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
  try {
    $Value = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer)
  }
  finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer)
    $SecureValue.Dispose()
  }
  if ([string]::IsNullOrWhiteSpace($Value)) { throw "$Prompt is required" }
  return $Value
}

$SourceCommit = (git rev-parse HEAD).Trim()
if ($SourceCommit -notmatch '^[0-9a-f]{40}$') {
  throw 'immutable source commit required in the acceptance terminal'
}
$Target = Get-Content evidence\azure-target-output.json -Raw | ConvertFrom-Json
$env:CATALOG_DATABASE_PASSWORD = Read-ProtectedValue 'Application database password'
$env:PERFTEST_API_KEY = Read-ProtectedValue 'Performance API key'
$env:CATALOG_BASE_URL = 'http://localhost:8080'
$env:CATALOG_DATABASE_KIND = 'postgresql'
$env:CATALOG_DATABASE_HOST = $Target.database.server
$env:CATALOG_DATABASE_PORT = '5432'
$env:CATALOG_DATABASE_NAME = $Target.database.database
$env:CATALOG_DATABASE_USERNAME = $Target.database.applicationPrincipal.name
$env:CATALOG_DATABASE_SSL_MODE = 'require'
$env:CATALOG_DATABASE_TARGET = 'managed'
cd tests\acceptance
uv --no-config run python -m catalog_acceptance `
  --profile full `
  --source-commit $SourceCommit `
  --output ..\..\evidence\transient\vm-managed-acceptance.json
$AcceptanceExit = $LASTEXITCODE
Remove-Item Env:CATALOG_DATABASE_PASSWORD
Remove-Item Env:PERFTEST_API_KEY
cd ..\..
if ($AcceptanceExit -ne 0) { throw 'VM/managed-database acceptance failed' }
```

Create `evidence/managed-database-separation.json` from the actual source VM resource ID,
PostgreSQL resource ID, application role name, commit, VM URL, acceptance report
path/result, and timestamps. Configuration or assessment output alone is not proof.

**Stop:** stop the VM application and do not build or deploy ACA unless this full
acceptance checkpoint passed.

## 5. Build and resolve the immutable ACR digest

The `java/Dockerfile` you author uses a digest-pinned Microsoft OpenJDK image, numeric
non-root user
`10001`, read-only seed, port `8080`, health check, and external `/app/images` path.

```powershell
$Target = Get-Content evidence\azure-target-output.json -Raw | ConvertFrom-Json
$AcrName = ($Target.containerRegistry.resourceId -split '/')[-1]
$Repository = 'catalog-java'
$BuildJson = az acr build `
  --registry $AcrName `
  --image "${Repository}:$SourceCommit" `
  --file java\Dockerfile `
  . --output json
if ($LASTEXITCODE -ne 0) { throw 'ACR build failed' }
[IO.File]::WriteAllText(
  (Join-Path (Get-Location) 'evidence\container-build.json'),
  ($BuildJson -join "`n") + "`n",
  $Utf8NoBom)

$ImageDigest = (
  az acr manifest show-metadata `
    --registry $AcrName `
    --name "${Repository}:$SourceCommit" `
    --query digest `
    --output tsv
).Trim()
if ($ImageDigest -notmatch '^sha256:[0-9a-f]{64}$') {
  throw 'ACR did not return an immutable digest'
}
```

Record the Dockerfile, full commit tag, resolved digest, non-root user, port, health
check, read-only seed, and Azure Files mount expectation in
`evidence/container-build.json`, preserving the original build result fields.

## 6. Deploy baseline and release by the same digest

Both protected application files already carry everything except the two values that did
not exist when they were written, so each deployment below adds
`sourceCommit=$SourceCommit` and `imageDigest=$ImageDigest`; the database application
password stays in secure Bicep input. After successful what-if and explicit approval:

```powershell
$BaselineTargetJson = az deployment group create `
  --name "manual-java-baseline-$($SourceCommit.Substring(0,12))" `
  --resource-group $ResourceGroup `
  --template-file infra\main.bicep `
  --parameters '@C:\protected\manual-java-baseline.json' `
  --parameters sourceCommit=$SourceCommit imageDigest=$ImageDigest `
  --query properties.outputs.targetOutput.value `
  --output json
if ($LASTEXITCODE -ne 0) { throw 'baseline deployment failed' }
$BaselineTarget = ($BaselineTargetJson -join "`n") | ConvertFrom-Json
$BaselineRevision = "$($BaselineTarget.application.containerAppName)--baseline-$($SourceCommit.Substring(0,12))"
$ExpectedImage = "$($BaselineTarget.containerRegistry.loginServer)/catalog-java@$ImageDigest"
if ($BaselineTarget.deploymentStage -ne 'application' -or
    $BaselineTarget.applicationRevisionRole -ne 'baseline' -or
    $BaselineTarget.application.revisionName -ne $BaselineRevision -or
    $BaselineTarget.containerImage.digest -ne $ImageDigest) {
  throw 'baseline output differs from the approved application stage'
}
$BaselineStateJson = az containerapp revision show `
  --resource-group $BaselineTarget.resourceGroup.name `
  --name $BaselineTarget.application.containerAppName `
  --revision $BaselineRevision `
  --query '{active:properties.active,health:properties.healthState,error:properties.provisioningError,images:properties.template.containers[].image}' `
  --output json
if ($LASTEXITCODE -ne 0) { throw 'baseline revision lookup failed' }
$BaselineState = ($BaselineStateJson -join "`n") | ConvertFrom-Json
if (-not $BaselineState.active -or
    $BaselineState.health -ne 'Healthy' -or
    $BaselineState.images.Count -ne 1 -or
    $BaselineState.images[0] -ne $ExpectedImage) {
  throw 'baseline revision is not the healthy active immutable target'
}
$BaselineHealth = Invoke-WebRequest -UseBasicParsing `
  -Uri $BaselineTarget.application.healthUrl -TimeoutSec 30
$BaselineReadiness = Invoke-WebRequest -UseBasicParsing `
  -Uri $BaselineTarget.application.readinessUrl -TimeoutSec 30
if ($BaselineHealth.StatusCode -ne 200 -or $BaselineReadiness.StatusCode -ne 200) {
  throw 'baseline health or readiness failed'
}

$ReleaseTargetJson = az deployment group create `
  --name "manual-java-release-$($SourceCommit.Substring(0,12))" `
  --resource-group $ResourceGroup `
  --template-file infra\main.bicep `
  --parameters '@C:\protected\manual-java-release.json' `
  --parameters sourceCommit=$SourceCommit imageDigest=$ImageDigest `
  --query properties.outputs.targetOutput.value `
  --output json
if ($LASTEXITCODE -ne 0) { throw 'release deployment failed' }
[IO.File]::WriteAllText(
  (Join-Path (Get-Location) 'evidence\azure-target-output.json'),
  ($ReleaseTargetJson -join "`n") + "`n",
  $Utf8NoBom)

$Target = Get-Content evidence\azure-target-output.json -Raw | ConvertFrom-Json
if ($Target.deploymentStage -ne 'application' -or
    $Target.applicationRevisionRole -ne 'release' -or
    $Target.containerImage.digest -ne $ImageDigest) {
  throw 'release output differs from the approved application stage'
}
$RollbackRevision = $BaselineRevision
$ReleaseStateJson = az containerapp revision show `
  --resource-group $Target.resourceGroup.name `
  --name $Target.application.containerAppName `
  --revision $Target.application.revisionName `
  --query '{active:properties.active,health:properties.healthState,error:properties.provisioningError,images:properties.template.containers[].image}' `
  --output json
if ($LASTEXITCODE -ne 0) { throw 'release revision lookup failed' }
$ReleaseState = ($ReleaseStateJson -join "`n") | ConvertFrom-Json
if (-not $ReleaseState.active -or
    $ReleaseState.health -ne 'Healthy' -or
    $ReleaseState.images.Count -ne 1 -or
    $ReleaseState.images[0] -ne $ExpectedImage) {
  throw 'release revision is not the healthy active immutable target'
}
$RollbackStateJson = az containerapp revision show `
  --resource-group $Target.resourceGroup.name `
  --name $Target.application.containerAppName `
  --revision $RollbackRevision `
  --query '{active:properties.active,health:properties.healthState,error:properties.provisioningError,images:properties.template.containers[].image}' `
  --output json
if ($LASTEXITCODE -ne 0) { throw 'retained baseline lookup failed' }
$RollbackState = ($RollbackStateJson -join "`n") | ConvertFrom-Json
if ($RollbackState.active -or
    $RollbackState.health -ne 'Healthy' -or
    $RollbackState.images.Count -ne 1 -or
    $RollbackState.images[0] -ne $ExpectedImage) {
  throw 'retained baseline is not the healthy inactive immutable rollback target'
}
$ReleaseHealth = Invoke-WebRequest -UseBasicParsing `
  -Uri $Target.application.healthUrl -TimeoutSec 30
$ReleaseReadiness = Invoke-WebRequest -UseBasicParsing `
  -Uri $Target.application.readinessUrl -TimeoutSec 30
if ($ReleaseHealth.StatusCode -ne 200 -or $ReleaseReadiness.StatusCode -ne 200) {
  throw 'release health or readiness failed'
}
```

Expected: the release target output names the full commit tag/digest and the distinct
baseline revision is `Healthy`, inactive, and contains the same digest reference.

## 7. Release evidence and rollback

Run native tests and preserve the Surefire JUnit XML. Create
`evidence/runtime-test-report.json` with the real artifact path and fourteen identities
from `workshop/contracts/runtime-test-evidence.schema.json`.

```powershell
$AcceptanceReport = Join-Path (Get-Location) `
  'evidence\acceptance-report.json'
if (Test-Path -LiteralPath $AcceptanceReport) {
  Remove-Item -LiteralPath $AcceptanceReport -Force -ErrorAction Stop
}
if (Test-Path -LiteralPath $AcceptanceReport) {
  throw 'stale acceptance report could not be removed'
}

Push-Location java
try {
  .\mvnw.cmd test
  if ($LASTEXITCODE -ne 0) { throw 'release native tests failed' }
}
finally { Pop-Location }

$env:CATALOG_BASE_URL = $Target.application.url
$env:CATALOG_DATABASE_KIND = 'postgresql'
$env:CATALOG_DATABASE_HOST = $Target.database.server
$env:CATALOG_DATABASE_PORT = '5432'
$env:CATALOG_DATABASE_NAME = $Target.database.database
$env:CATALOG_DATABASE_USERNAME = $Target.database.applicationPrincipal.name
$env:CATALOG_DATABASE_SSL_MODE = 'require'
$env:CATALOG_DATABASE_TARGET = 'managed'
Push-Location tests\acceptance
try {
  $AcceptanceExit = 0
  try {
    Remove-Item Env:MIGRATION_TARGET_APPLICATION_PASSWORD `
      -ErrorAction SilentlyContinue
    $env:CATALOG_DATABASE_PASSWORD = Read-ProtectedValue `
      'Acceptance verifier database password'
    $env:PERFTEST_API_KEY = Read-ProtectedValue 'Runtime performance API key'
    uv --no-config run python -m catalog_acceptance `
      --profile full `
      --base-url $env:CATALOG_BASE_URL `
      --database-kind postgresql `
      --database-host $env:CATALOG_DATABASE_HOST `
      --database-port $env:CATALOG_DATABASE_PORT `
      --database-name $env:CATALOG_DATABASE_NAME `
      --database-username $env:CATALOG_DATABASE_USERNAME `
      --database-ssl-mode require `
      --database-target managed `
      --source-commit $SourceCommit `
      --image-digest $ImageDigest `
      --revision-name $Target.application.revisionName `
      --output $AcceptanceReport
    $AcceptanceExit = $LASTEXITCODE
  }
  finally {
    Remove-Item Env:CATALOG_DATABASE_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:PERFTEST_API_KEY -ErrorAction SilentlyContinue
  }
  if ($AcceptanceExit -ne 0) { throw 'release full acceptance failed' }
}
finally { Pop-Location }
```

Exercise successful, rejected-import, dependency-failure, and performance paths. Query
the Application Insights resource with the four KQL queries in
`workshop/contracts/telemetry-evidence.example.json`; normalize actual nonempty results
to `evidence/telemetry/resources.json`, `traces.json`, `metrics.json`, and `logs.json`
against `workshop/contracts/telemetry-query-result.schema.json`. Write
`evidence/telemetry-report.json` with service `mh-catalog-java`, the exact release
commit/revision resource attributes, actual query strings/result paths, and all expected
signal names. Never copy example observations or treat assessment as runtime proof.

```powershell
$TelemetryTemplate = Get-Content `
  workshop\contracts\telemetry-evidence.example.json -Raw | ConvertFrom-Json
$TelemetryTemplate.queries.psobject.Properties | ForEach-Object {
  $QueryId = $_.Name
  $RawResult = az monitor app-insights query `
    --app $Target.observability.applicationInsightsResourceId `
    --analytics-query $_.Value.query `
    --output json
  if ($LASTEXITCODE -ne 0) { throw "telemetry query failed: $QueryId" }
  [IO.File]::WriteAllText(
    (Join-Path (Get-Location) "evidence\transient\telemetry-$QueryId.raw.json"),
    ($RawResult -join "`n") + "`n",
    $Utf8NoBom)
}
```

Write `evidence/rollback-runbook.md` with approval, exact baseline revision/digest,
release abort conditions, health/readiness and full-acceptance checks, and forward
recovery. The shared target uses single revision mode; activate the retained prior
revision rather than assigning traffic weights. Record this procedure during a healthy
release but execute it only after rollback approval; normal handoff validation requires
the retained baseline to remain inactive:

```powershell
$RollbackStateJson = az containerapp revision show `
  --resource-group $Target.resourceGroup.name `
  --name $Target.application.containerAppName `
  --revision $RollbackRevision `
  --query '{active:properties.active,health:properties.healthState,error:properties.provisioningError,images:properties.template.containers[].image}' `
  --output json
if ($LASTEXITCODE -ne 0) { throw 'rollback revision lookup failed' }
$RollbackState = ($RollbackStateJson -join "`n") | ConvertFrom-Json
if ($RollbackState.active -or
    $RollbackState.health -ne 'Healthy' -or
    $RollbackState.images.Count -ne 1 -or
    $RollbackState.images[0] -ne $ExpectedImage) {
  throw 'rollback revision is not the retained healthy inactive immutable baseline'
}
az containerapp revision activate `
  --resource-group $Target.resourceGroup.name `
  --name $Target.application.containerAppName `
  --revision $RollbackRevision
if ($LASTEXITCODE -ne 0) { throw 'rollback revision activation failed' }
$ActivatedStateJson = az containerapp revision show `
  --resource-group $Target.resourceGroup.name `
  --name $Target.application.containerAppName `
  --revision $RollbackRevision `
  --query '{active:properties.active,health:properties.healthState,error:properties.provisioningError,images:properties.template.containers[].image}' `
  --output json
if ($LASTEXITCODE -ne 0) { throw 'activated rollback revision lookup failed' }
$ActivatedState = ($ActivatedStateJson -join "`n") | ConvertFrom-Json
if (-not $ActivatedState.active -or
    $ActivatedState.health -ne 'Healthy' -or
    $ActivatedState.images.Count -ne 1 -or
    $ActivatedState.images[0] -ne $ExpectedImage) {
  throw 'rollback revision did not become the healthy active immutable revision'
}
$ReleaseAfterRollbackJson = az containerapp revision show `
  --resource-group $Target.resourceGroup.name `
  --name $Target.application.containerAppName `
  --revision $Target.application.revisionName `
  --query '{active:properties.active,health:properties.healthState}' `
  --output json
if ($LASTEXITCODE -ne 0) { throw 'superseded release revision lookup failed' }
$ReleaseAfterRollback = ($ReleaseAfterRollbackJson -join "`n") | ConvertFrom-Json
if ($ReleaseAfterRollback.active) {
  throw 'single revision mode did not deactivate the superseded release'
}
$RollbackHealth = Invoke-WebRequest -UseBasicParsing `
  -Uri $Target.application.healthUrl -TimeoutSec 30
$RollbackReadiness = Invoke-WebRequest -UseBasicParsing `
  -Uri $Target.application.readinessUrl -TimeoutSec 30
if ($RollbackHealth.StatusCode -ne 200 -or $RollbackReadiness.StatusCode -ne 200) {
  throw 'activated rollback revision failed health or readiness'
}
```

Rollback preserves both databases, migration archive, Azure Files, ACR manifest, source
data, and evidence. Abort if baseline is missing, active, unhealthy, or uses another
digest.

## 8. Render, validate, clean, and rejoin

```powershell
Push-Location tests\acceptance
try {
uv --no-config run catalog-migrate render-handoff `
  --target-output ..\..\evidence\azure-target-output.json `
  --migration-report ..\..\evidence\migration-report.json `
  --acceptance-report ..\..\evidence\acceptance-report.json `
  --telemetry-report ..\..\evidence\telemetry-report.json `
  --runtime-test-report ..\..\evidence\runtime-test-report.json `
  --path manual `
  --rollback-revision $RollbackRevision `
  --rollback-runbook ..\..\evidence\rollback-runbook.md `
  --output ..\..\evidence\modernization-contract.json
if ($LASTEXITCODE -ne 0) { throw 'handoff rendering failed' }

uv --no-config run python -m catalog_acceptance.handoff_cli `
  ..\..\evidence\modernization-contract.json `
  --contracts ..\..\workshop\contracts `
  --repository-root ..\..
if ($LASTEXITCODE -ne 0) { throw 'handoff validation failed' }
}
finally { Pop-Location }
```

After validation, remove only transient local material and clear secrets:

```powershell
Remove-Item evidence\transient -Recurse -Force
Remove-Item Env:MIGRATION_SOURCE_DATABASE_PASSWORD -ErrorAction SilentlyContinue
Remove-Item Env:MIGRATION_TARGET_ADMINISTRATOR_PASSWORD -ErrorAction SilentlyContinue
Remove-Item Env:MIGRATION_TARGET_APPLICATION_PASSWORD -ErrorAction SilentlyContinue
Remove-Item Env:CATALOG_DATABASE_PASSWORD -ErrorAction SilentlyContinue
Remove-Item Env:PERFTEST_API_KEY -ErrorAction SilentlyContinue
```

The handoff itself is not yet on GitHub. Challenge 3 reads
`evidence/modernization-contract.json` from the commit it dispatches, and that commit must
be a **later** commit than the source commit it builds. Publish the validated evidence as
one follow-up commit, after the transient directory is gone so nothing transient ships:

```powershell
git add --all
git commit -m 'Record the validated modernization handoff'
if (git status --porcelain) {
  throw 'the handoff evidence must be committed before Challenge 3 runs'
}
git push origin workshop
if ($LASTEXITCODE -ne 0) { throw 'publishing the handoff evidence failed' }
if ((git rev-parse HEAD).Trim() -ceq $SourceCommit) {
  throw 'the handoff commit must be later than the published source commit'
}
```

Challenge 3 dispatches its workflow from this evidence commit, reads the handoff there,
and checks the application source out separately at `$SourceCommit`.

Keep every registry evidence path, referenced raw test artifact, and the protected
database archive/sidecar until the facilitator's retention boundary. Rejoin the common
workshop only when handoff validation exits `0`, release health/readiness pass, and the
retained baseline remains a valid rollback target.

---

**Challenge:** [Path 1A: modernize it by hand](../../../challenges/ch01-manual/README.md) ·
**Other stack:** [Manual .NET](../dotnet/README.md) ·
**Modernized target:** [Reference implementation](../../reference/README.md) ·
**Next:** [Challenge 2: load and autoscaling](../../../challenges/ch02/README.md)
