# Manual .NET to Azure SQL modernization

This runbook implements registry slice `manual-dotnet`. Run repository commands from the
repository root unless a step explicitly changes directory. Azure and migration commands
run on the existing .NET P3 source VM so the frozen topology guard can verify the host.

## Preconditions and protected inputs

The source VM must contain the exact repository commit, the provisioned locked tools, and
an authenticated isolated facilitator profile. A facilitator must prepare these protected
files outside the repository:

- a bootstrap parameter file for `infra/main.bicep` with `deploymentStage=bootstrap`,
  `stack=dotnet-sqlserver`, `imageProvider=azure-files`, the exact source VM/VNet IDs,
  `applicationRevisionRole=""`, and the exact source commit;
- baseline and release application parameter files with the same values, the same
  immutable image digest, `applicationRevisionRole=baseline` or `release`, and secure
  application inputs.

The facilitator injects `MIGRATION_SOURCE_DATABASE_PASSWORD`, `PERFTEST_API_KEY`, and
other documented secret environment variables into the current process without printing
them. Do not continue if a secret appears in command history or a checked-in file.

```powershell
$env:AZURE_CONFIG_DIR = Join-Path $HOME '.azure-365'
$SourceCommit = (git rev-parse HEAD).Trim()
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$DatabaseArtifact = 'C:\protected\manual-dotnet\catalog.bacpac'
if ($SourceCommit -notmatch '^[0-9a-f]{40}$') { throw 'immutable source commit required' }
if (git status --porcelain) { throw 'source worktree must be clean' }
New-Item -ItemType Directory -Force evidence, evidence\transient, evidence\telemetry |
  Out-Null
cd tests\acceptance
uv --no-config sync --frozen
uv --no-config run catalog-migrate --help
cd ..\..
```

Expected: the CLI exposes only `sql`, `postgresql`, `images`, `verify`, and
`render-handoff`; this slice uses `sql`.

## 1. Characterize the source

Run the native suite and the local full acceptance profile before changing the target.
The application and SQL Server remain on the VM for this checkpoint.

```powershell
dotnet test dotnet\LegoCatalog.sln --logger trx --results-directory evidence

cd tests\acceptance
uv --no-config run python -m catalog_acceptance `
  --profile full `
  --base-url $env:CATALOG_BASE_URL `
  --database-kind sqlserver `
  --database-host $env:CATALOG_DATABASE_HOST `
  --database-name $env:CATALOG_DATABASE_NAME `
  --database-username $env:CATALOG_DATABASE_USERNAME `
  --database-target local `
  --source-commit $SourceCommit `
  --output ..\..\evidence\transient\source-acceptance-report.json
cd ..\..
```

Write `evidence/baseline-backup.md` with the commit, source VM/VNet IDs, timestamps,
native and acceptance results, canonical manifest counts/hashes, configuration variable
names with values redacted, and restore owner. Do not claim a successful backup until the
export in step 3 and its integrity sidecar are readable.

**Stop:** any native or full-acceptance failure is a source defect, not a modernization
success. Resolve it before creating or mutating a target.

## 2. Review and bootstrap Azure SQL

Build and review the shared P4 IaC. The protected files are inputs; never copy them into
the repository.

```powershell
az bicep version
az bicep build --file infra\main.bicep
Get-ChildItem infra\modules\*.bicep | ForEach-Object {
  az bicep build --file $_.FullName
}
az deployment sub what-if `
  --location swedencentral `
  --template-file infra\main.bicep `
  --parameters '@C:\protected\manual-dotnet-bootstrap.json'
```

Record the reviewed what-if, private endpoints, source/target peering, private DNS links,
Entra-only Azure SQL, Azure Files share, ACR, observability, and absent bootstrap
Container App in `evidence/iac-review.md`. After explicit approval:

```powershell
$TargetJson = az deployment sub create `
  --name "manual-dotnet-bootstrap-$($SourceCommit.Substring(0,12))" `
  --location swedencentral `
  --template-file infra\main.bicep `
  --parameters '@C:\protected\manual-dotnet-bootstrap.json' `
  --query properties.outputs.targetOutput.value `
  --output json
if ($LASTEXITCODE -ne 0) { throw 'bootstrap deployment failed' }
[IO.File]::WriteAllText(
  (Join-Path (Get-Location) 'evidence\azure-target-output.json'),
  ($TargetJson -join "`n") + "`n",
  $Utf8NoBom)

$Target = Get-Content evidence\azure-target-output.json -Raw | ConvertFrom-Json
if ($Target.deploymentStage -ne 'bootstrap' -or
    $Target.stack -ne 'dotnet-sqlserver' -or
    $Target.database.family -ne 'azure-sql' -or
    $Target.images.provider -ne 'azure-files' -or
    $null -ne $Target.application) {
  throw 'bootstrap target differs from the frozen manual slice'
}
```

**Stop:** do not alter the contract or bypass a topology mismatch. Bootstrap must not
create ACA.

## 3. Export, import, copy images, and verify

Run the frozen CLI from `tests/acceptance`. The source password is environment-only.
The export is read-only and creates a BACPAC plus integrity sidecar.

```powershell
cd tests\acceptance
uv --no-config run catalog-migrate sql export `
  --source-server $env:CATALOG_DATABASE_HOST `
  --source-database $env:CATALOG_DATABASE_NAME `
  --source-username $env:CATALOG_DATABASE_USERNAME `
  --target-output ..\..\evidence\azure-target-output.json `
  --artifact $DatabaseArtifact

$Target = Get-Content ..\..\evidence\azure-target-output.json -Raw |
  ConvertFrom-Json
$DatabaseId = $Target.database.resourceId
$ImagesId = $Target.images.resourceId

uv --no-config run catalog-migrate sql import `
  --artifact $DatabaseArtifact `
  --target-output ..\..\evidence\azure-target-output.json `
  --target-resource-id $DatabaseId `
  --confirm-target-resource-id $DatabaseId `
  --execute

uv --no-config run catalog-migrate images copy `
  --source-directory ..\..\data\images `
  --target-output ..\..\evidence\azure-target-output.json `
  --target-resource-id $ImagesId `
  --confirm-target-resource-id $ImagesId `
  --execute

uv --no-config run catalog-migrate verify `
  --stack dotnet-sqlserver `
  --source-commit $SourceCommit `
  --database-artifact $DatabaseArtifact `
  --target-output ..\..\evidence\azure-target-output.json `
  --output ..\..\evidence\migration-report.json
cd ..\..
```

Append the BACPAC and sidecar paths, sizes, hashes, creation time, and tested restore
owner to `evidence/baseline-backup.md`; never include the password. Expected:
`evidence/migration-report.json` validates the exact corpus, schema, migration history,
least-privilege managed identity, Azure Files bytes/hash, TLS, and source-VM topology.

**Stop:** exit codes `2` through `5`, a nonempty-target refusal, or a failed verification
ends the migration attempt. Do not delete either database or rerun import into a
nonempty target.

## 4. Prove VM application/database separation

Temporarily attach the target workload identity to the source VM after approval. This
keeps compute on the VM while the application uses Azure SQL.

```powershell
$Target = Get-Content evidence\azure-target-output.json -Raw | ConvertFrom-Json
az vm identity assign `
  --ids $Target.network.migrationSourceVmResourceId `
  --identities $Target.workloadIdentity.resourceId | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'temporary source VM identity assignment failed' }

$env:CATALOG_DATABASE_HOST = $Target.database.server
$env:CATALOG_DATABASE_NAME = $Target.database.database
$env:CATALOG_DATABASE_AUTHENTICATION = 'managed-identity'
$env:AZURE_CLIENT_ID = $Target.workloadIdentity.clientId
$env:CATALOG_DATABASE_SSL_MODE = 'require'
$env:CATALOG_STARTUP_IMPORT_ENABLED = 'false'
Remove-Item Env:CATALOG_DATABASE_USERNAME -ErrorAction SilentlyContinue
Remove-Item Env:CATALOG_DATABASE_PASSWORD -ErrorAction SilentlyContinue
dotnet run --project dotnet\src\LegoCatalog.App\LegoCatalog.App.csproj
```

In a second source-VM terminal, obtain the short-lived SQL access token and prompt for
the canonical performance key without echoing it. Process-scoped variables from the
application terminal are deliberately not reused:

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

$env:AZURE_CONFIG_DIR = Join-Path $HOME '.azure-365'
$SourceCommit = (git rev-parse HEAD).Trim()
if ($SourceCommit -notmatch '^[0-9a-f]{40}$') {
  throw 'immutable source commit required in the acceptance terminal'
}
$env:PERFTEST_API_KEY = Read-ProtectedValue 'Performance API key'
$env:SQLCMDACCESS_TOKEN = (
  az account get-access-token --resource https://database.windows.net/ `
    --query accessToken --output tsv
).Trim()
$Target = Get-Content evidence\azure-target-output.json -Raw | ConvertFrom-Json
$env:CATALOG_BASE_URL = 'http://localhost:5000'
$env:CATALOG_DATABASE_KIND = 'sqlserver'
$env:CATALOG_DATABASE_HOST = $Target.database.server
$env:CATALOG_DATABASE_NAME = $Target.database.database
$env:CATALOG_DATABASE_SSL_MODE = 'require'
$env:CATALOG_DATABASE_TARGET = 'managed'
$env:CATALOG_SOURCE_COMMIT = $SourceCommit
cd tests\acceptance
uv --no-config run python -m catalog_acceptance `
  --profile full `
  --source-commit $SourceCommit `
  --output ..\..\evidence\transient\vm-managed-acceptance.json
$AcceptanceExit = $LASTEXITCODE
Remove-Item Env:SQLCMDACCESS_TOKEN
Remove-Item Env:PERFTEST_API_KEY
cd ..\..
if ($AcceptanceExit -ne 0) { throw 'VM/managed-database acceptance failed' }
```

Create `evidence/managed-database-separation.json` from the actual source VM resource ID,
Azure SQL resource ID, workload identity resource ID, commit, VM application URL,
acceptance report path/result, and start/completion timestamps. This evidence proves
behavior only because the full report passed; the target assessment alone does not.

Stop the VM application and detach only the added target identity after approval:

```powershell
az vm identity remove `
  --ids $Target.network.migrationSourceVmResourceId `
  --identities $Target.workloadIdentity.resourceId | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'temporary source VM identity removal failed' }
```

**Stop:** do not containerize or deploy ACA unless the VM application passed full
acceptance against Azure SQL.

## 5. Build and resolve the immutable ACR digest

The checked-in `dotnet/Dockerfile` uses digest-pinned build/runtime images and numeric
non-root user `1654`. Build from the repository root and tag only with the full commit.

```powershell
$Target = Get-Content evidence\azure-target-output.json -Raw | ConvertFrom-Json
$AcrName = ($Target.containerRegistry.resourceId -split '/')[-1]
$Repository = 'catalog-dotnet'
$BuildJson = az acr build `
  --registry $AcrName `
  --image "${Repository}:$SourceCommit" `
  --file dotnet\Dockerfile `
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

Record the Dockerfile path, commit tag, resolved digest, non-root user, port, health
check, read-only seed, and `/app/images` Azure Files mount expectation in
`evidence/container-build.json`. Preserve the original ACR build fields.

## 6. Deploy baseline and release by the same digest

The facilitator places `$ImageDigest` in both protected application parameter files.
Run what-if for each and verify the image is
`$Target.containerRegistry.loginServer/catalog-dotnet@$ImageDigest`.
After approval, deploy baseline and then release:

```powershell
$BaselineTargetJson = az deployment sub create `
  --name "manual-dotnet-baseline-$($SourceCommit.Substring(0,12))" `
  --location swedencentral `
  --template-file infra\main.bicep `
  --parameters '@C:\protected\manual-dotnet-baseline.json' `
  --query properties.outputs.targetOutput.value `
  --output json
if ($LASTEXITCODE -ne 0) { throw 'baseline deployment failed' }
$BaselineTarget = ($BaselineTargetJson -join "`n") | ConvertFrom-Json
$BaselineRevision = "$($BaselineTarget.application.containerAppName)--baseline-$($SourceCommit.Substring(0,12))"
$ExpectedImage = "$($BaselineTarget.containerRegistry.loginServer)/catalog-dotnet@$ImageDigest"
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

$ReleaseTargetJson = az deployment sub create `
  --name "manual-dotnet-release-$($SourceCommit.Substring(0,12))" `
  --location swedencentral `
  --template-file infra\main.bicep `
  --parameters '@C:\protected\manual-dotnet-release.json' `
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

Expected: release output names the full commit tag and digest; the distinct baseline
revision is `Healthy`, inactive, and contains exactly the same digest reference.

## 7. Release evidence and rollback

Run the native suite again and retain its TRX. Create
`evidence/runtime-test-report.json` with the actual artifact path and the fourteen test
identities defined by `workshop/contracts/runtime-test-evidence.schema.json`.

```powershell
dotnet test dotnet\LegoCatalog.sln --logger trx --results-directory evidence

$env:CATALOG_BASE_URL = $Target.application.url
$env:CATALOG_SOURCE_COMMIT = $SourceCommit
$env:CATALOG_IMAGE_DIGEST = $ImageDigest
$env:CATALOG_REVISION_NAME = $Target.application.revisionName
# Inject PERFTEST_API_KEY and SQLCMDACCESS_TOKEN into this process only.
cd tests\acceptance
uv --no-config run python -m catalog_acceptance `
  --profile full `
  --base-url $env:CATALOG_BASE_URL `
  --database-kind sqlserver `
  --database-host $Target.database.server `
  --database-name $Target.database.database `
  --database-ssl-mode require `
  --database-target managed `
  --source-commit $SourceCommit `
  --image-digest $ImageDigest `
  --revision-name $Target.application.revisionName `
  --output ..\..\evidence\acceptance-report.json
cd ..\..
```

Exercise successful, rejected-import, dependency-failure, and performance paths. Query
the Application Insights resource with the four KQL queries in
`workshop/contracts/telemetry-evidence.example.json`; normalize the real nonempty results
to `evidence/telemetry/resources.json`, `traces.json`, `metrics.json`, and `logs.json`
using `workshop/contracts/telemetry-query-result.schema.json`. Write
`evidence/telemetry-report.json` with service `mh-catalog-dotnet`, the exact release
commit/revision resource attributes, those query strings/result paths, and all expected
signal names. Do not copy example observations or infer behavior from configuration.

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

Write `evidence/rollback-runbook.md` with facilitator approval, the exact baseline
revision/digest, release abort conditions, health/readiness and full-acceptance checks,
and forward recovery. The shared target uses single revision mode; activate the retained
prior revision rather than assigning traffic weights. Record this procedure during a
healthy release but execute it only after rollback approval; normal handoff validation
requires the retained baseline to remain inactive:

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

Rollback never deletes or rewinds the managed database, migration archive, Azure Files,
ACR manifest, source data, or evidence. Abort rollback if baseline is absent, active,
unhealthy, or has a different digest.

## 8. Render, validate, clean, and rejoin

```powershell
cd tests\acceptance
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

uv --no-config run python -m catalog_acceptance.handoff_cli `
  ..\..\evidence\modernization-contract.json `
  --contracts ..\..\workshop\contracts `
  --repository-root ..\..
cd ..\..
```

After validation, remove only local transient material and clear secret variables:

```powershell
Remove-Item evidence\transient -Recurse -Force
Remove-Item Env:MIGRATION_SOURCE_DATABASE_PASSWORD -ErrorAction SilentlyContinue
Remove-Item Env:PERFTEST_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:SQLCMDACCESS_TOKEN -ErrorAction SilentlyContinue
```

Keep every registry evidence path, referenced raw test artifact, and the protected
database archive/sidecar until the facilitator's retention boundary. Rejoin the common
workshop only when handoff validation exits `0`, the release is healthy/ready, and the
retained baseline remains a valid rollback target.
