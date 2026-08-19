# Manual Java to PostgreSQL Flexible Server modernization

This runbook implements registry slice `manual-java`. Run repository commands from the
repository root unless a step explicitly changes directory. Azure and migration commands
run on the existing Java P3 source VM so the frozen topology guard can verify the host.

## Preconditions and protected inputs

The source VM must contain the exact repository commit, checked-in Maven Wrapper and lock
files, provisioned PostgreSQL 18.6 client tools, and an authenticated isolated facilitator
profile. A facilitator must prepare protected Bicep parameter files outside the
repository:

- bootstrap: `deploymentStage=bootstrap`, `stack=java-postgresql`,
  `imageProvider=azure-files`, `postgresqlAuthentication=password-secret`, exact source
  VM/VNet IDs, `applicationRevisionRole=""`, exact source commit, and secure
  administrator input;
- baseline/release: the same topology and database mode, the same immutable image digest,
  `applicationRevisionRole=baseline` or `release`, and secure database/performance inputs.

The facilitator injects `MIGRATION_SOURCE_DATABASE_PASSWORD`,
`MIGRATION_TARGET_ADMINISTRATOR_PASSWORD`,
`MIGRATION_TARGET_APPLICATION_PASSWORD`, and `PERFTEST_API_KEY` into the current process
without printing them. Never place them in arguments, evidence, transcripts, or source.

```powershell
$env:AZURE_CONFIG_DIR = Join-Path $HOME '.azure-365'
$SourceCommit = (git rev-parse HEAD).Trim()
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$DatabaseArtifact = 'C:\protected\manual-java\catalog.dump'
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
`render-handoff`; this slice uses `postgresql`.

## 1. Characterize the source

Run the Maven Wrapper suite and local full acceptance before changing the target:

```powershell
cd java
.\mvnw.cmd test
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
az deployment sub what-if `
  --location swedencentral `
  --template-file infra\main.bicep `
  --parameters '@C:\protected\manual-java-bootstrap.json'
```

Record the reviewed what-if, private endpoints, reciprocal source/target peering, private
DNS links, PostgreSQL Flexible Server, Azure Files share, ACR, observability, and absent
bootstrap Container App in `evidence/iac-review.md`. After explicit approval:

```powershell
$TargetJson = az deployment sub create `
  --name "manual-java-bootstrap-$($SourceCommit.Substring(0,12))" `
  --location swedencentral `
  --template-file infra\main.bicep `
  --parameters '@C:\protected\manual-java-bootstrap.json' `
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

The frozen CLI invokes the pinned PostgreSQL 18.6 `pg_dump`/`pg_restore`. Passwords are
environment-only. Run from `tests/acceptance`:

```powershell
cd tests\acceptance
uv --no-config run catalog-migrate postgresql export `
  --source-host $env:CATALOG_DATABASE_HOST `
  --source-port $env:CATALOG_DATABASE_PORT `
  --source-database $env:CATALOG_DATABASE_NAME `
  --source-username $env:CATALOG_DATABASE_USERNAME `
  --target-output ..\..\evidence\azure-target-output.json `
  --artifact $DatabaseArtifact

$Target = Get-Content ..\..\evidence\azure-target-output.json -Raw |
  ConvertFrom-Json
$DatabaseId = $Target.database.resourceId
$ImagesId = $Target.images.resourceId

uv --no-config run catalog-migrate postgresql import `
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
  --stack java-postgresql `
  --source-commit $SourceCommit `
  --database-artifact $DatabaseArtifact `
  --target-output ..\..\evidence\azure-target-output.json `
  --output ..\..\evidence\migration-report.json
cd ..\..
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
$env:CATALOG_DATABASE_PASSWORD = $env:MIGRATION_TARGET_APPLICATION_PASSWORD
$env:CATALOG_DATABASE_AUTHENTICATION = 'password-secret'
$env:CATALOG_DATABASE_SSL_MODE = 'require'
$env:CATALOG_STARTUP_IMPORT_ENABLED = 'false'
$env:DEPLOYMENT_ENVIRONMENT = 'lab'
$env:CONTAINER_APP_REVISION = 'source-vm-managed-database'
cd java
.\mvnw.cmd spring-boot:run
```

In a second source-VM terminal, run full acceptance against the VM URL and managed
database:

```powershell
$SourceCommit = (git rev-parse HEAD).Trim()
if ($SourceCommit -notmatch '^[0-9a-f]{40}$') {
  throw 'immutable source commit required in the acceptance terminal'
}
$Target = Get-Content evidence\azure-target-output.json -Raw | ConvertFrom-Json
$env:CATALOG_BASE_URL = 'http://localhost:8080'
$env:CATALOG_DATABASE_KIND = 'postgresql'
$env:CATALOG_DATABASE_HOST = $Target.database.server
$env:CATALOG_DATABASE_PORT = '5432'
$env:CATALOG_DATABASE_NAME = $Target.database.database
$env:CATALOG_DATABASE_USERNAME = $Target.database.applicationPrincipal.name
$env:CATALOG_DATABASE_PASSWORD = $env:MIGRATION_TARGET_APPLICATION_PASSWORD
$env:CATALOG_DATABASE_SSL_MODE = 'require'
$env:CATALOG_DATABASE_TARGET = 'managed'
cd tests\acceptance
uv --no-config run python -m catalog_acceptance `
  --profile full `
  --source-commit $SourceCommit `
  --output ..\..\evidence\transient\vm-managed-acceptance.json
$AcceptanceExit = $LASTEXITCODE
cd ..\..
if ($AcceptanceExit -ne 0) { throw 'VM/managed-database acceptance failed' }
```

Create `evidence/managed-database-separation.json` from the actual source VM resource ID,
PostgreSQL resource ID, application role name, commit, VM URL, acceptance report
path/result, and timestamps. Configuration or assessment output alone is not proof.

**Stop:** stop the VM application and do not build or deploy ACA unless this full
acceptance checkpoint passed.

## 5. Build and resolve the immutable ACR digest

`java/Dockerfile` uses a digest-pinned Microsoft OpenJDK image, numeric non-root user
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

The facilitator places `$ImageDigest` in both protected application parameter files and
keeps the database application password in secure Bicep input. After successful what-if
and explicit approval:

```powershell
$BaselineTargetJson = az deployment sub create `
  --name "manual-java-baseline-$($SourceCommit.Substring(0,12))" `
  --location swedencentral `
  --template-file infra\main.bicep `
  --parameters '@C:\protected\manual-java-baseline.json' `
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

$ReleaseTargetJson = az deployment sub create `
  --name "manual-java-release-$($SourceCommit.Substring(0,12))" `
  --location swedencentral `
  --template-file infra\main.bicep `
  --parameters '@C:\protected\manual-java-release.json' `
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
cd java
.\mvnw.cmd test
cd ..

$env:CATALOG_BASE_URL = $Target.application.url
$env:CATALOG_DATABASE_KIND = 'postgresql'
$env:CATALOG_DATABASE_HOST = $Target.database.server
$env:CATALOG_DATABASE_PORT = '5432'
$env:CATALOG_DATABASE_NAME = $Target.database.database
$env:CATALOG_DATABASE_USERNAME = $Target.database.applicationPrincipal.name
$env:CATALOG_DATABASE_PASSWORD = $env:MIGRATION_TARGET_APPLICATION_PASSWORD
$env:CATALOG_DATABASE_SSL_MODE = 'require'
$env:CATALOG_DATABASE_TARGET = 'managed'
cd tests\acceptance
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
  --output ..\..\evidence\acceptance-report.json
cd ..\..
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

After validation, remove only transient local material and clear secrets:

```powershell
Remove-Item evidence\transient -Recurse -Force
Remove-Item Env:MIGRATION_SOURCE_DATABASE_PASSWORD -ErrorAction SilentlyContinue
Remove-Item Env:MIGRATION_TARGET_ADMINISTRATOR_PASSWORD -ErrorAction SilentlyContinue
Remove-Item Env:MIGRATION_TARGET_APPLICATION_PASSWORD -ErrorAction SilentlyContinue
Remove-Item Env:CATALOG_DATABASE_PASSWORD -ErrorAction SilentlyContinue
Remove-Item Env:PERFTEST_API_KEY -ErrorAction SilentlyContinue
```

Keep every registry evidence path, referenced raw test artifact, and the protected
database archive/sidecar until the facilitator's retention boundary. Rejoin the common
workshop only when handoff validation exits `0`, release health/readiness pass, and the
retained baseline remains a valid rollback target.
