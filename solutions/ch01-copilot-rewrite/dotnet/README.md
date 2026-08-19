# .NET/Azure SQL bounded Copilot rewrite reference

This is a runnable reference slice, not a complete rewrite to copy and paste. Work
from the repository root unless a command changes directory. Replace angle-bracket
values from the participant environment; never commit those values or shell history
containing secrets.

## Registered boundary

`copilot-rewrite-dotnet` resolves to:

| Interface | Exact value |
| --- | --- |
| Source | `dotnet/` |
| Dockerfile | `dotnet/Dockerfile` |
| Database family | `azure-sql` |
| Image provider | `azure-blob` |
| Tools | `github.copilot`, `github.copilot-chat` |
| Infrastructure | `infra/main.bicep` |
| Migration | `catalog-migrate` |

The pinned tools are `github.copilot@1.388.0` and
`github.copilot-chat@0.48.1`. Do not install or invoke any modernization or
migration extension for this path.

## 1. Preflight and characterization checkpoint

**Executable proof**

```bash
set -euo pipefail
test "$(git rev-parse --show-toplevel)" = "$PWD"
test -z "$(git status --porcelain)"
installed_extensions="$(code --list-extensions --show-versions)"
grep -Fxq 'github.copilot@1.388.0' <<<"$installed_extensions"
grep -Fxq 'github.copilot-chat@0.48.1' <<<"$installed_extensions"
mkdir -p evidence .workshop-tmp
dotnet restore dotnet/LegoCatalog.sln
dotnet test dotnet/LegoCatalog.sln \
  --logger "trx;LogFileName=characterization.trx" \
  --results-directory "$PWD/.workshop-tmp/dotnet-characterization"
cd tests/acceptance
UV_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple \
  uv --no-config run pytest -q tests/test_contract_assets.py
cd ../..
```

Start the unchanged application and its disposable local SQL Server using the
instructions in `dotnet/README.md`, then run full shared acceptance against that
baseline. Record the exact application command, database target, native TRX result,
acceptance report, and known failures in `evidence/characterization.md`. The
characterization and acceptance suites are the behavioral oracle.

**Expected checkpoint**

- native tests and contract assets pass;
- the baseline routes, SQL schema, import transaction, image keys, degraded states,
  configuration, errors, and telemetry are documented;
- no implementation file has changed.

## 2. Human-reviewed bounded plan

Write `evidence/bounded-plan.md` before asking for code. A suitable sequence is:

1. domain identity, text validation, and Azure SQL schema;
2. transactional import and query behavior;
3. local/Blob image abstraction and image-key security;
4. external configuration, managed identity, health, readiness, and bounded
   performance;
5. telemetry and the existing non-root Container Apps image.

For every slice, list exact files, tests, exclusions, and how to return to the last
passing commit. A human must approve the plan and must review schema, security,
dependencies, configuration, errors, and each generated diff.

**Suggested prompt, not proof**

> Read `workshop/contracts`, `tests/acceptance`, the current .NET tests, and
> `dotnet/Dockerfile`. Propose only the next bounded slice. Preserve Azure SQL, one
> application container, Blob images, ACA readiness, external configuration, routes,
> failure behavior, and telemetry. Do not edit frozen interfaces or add services.
> Name exact tests and wait for approval before generating a diff.

## 3. Slice loop

Ask for and accept one generated diff at a time.

**Suggested prompt, not proof**

> Implement only approved slice `<slice-name>`. Keep changes inside the listed .NET
> files. Add or update focused tests for the characterized behavior. Do not change
> database family, infrastructure, migration, deployment topology, or unrelated
> dependencies. Surface configuration and errors explicitly.

**Executable proof after every generated diff**

```bash
set -euo pipefail
git diff -- dotnet
dotnet test dotnet/LegoCatalog.sln \
  --logger "trx;LogFileName=<slice-name>.trx" \
  --results-directory "$PWD/.workshop-tmp/dotnet-<slice-name>"
cd tests/acceptance
UV_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple \
  uv --no-config run pytest -q tests/test_contract_assets.py
UV_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple \
  uv --no-config run python -m catalog_acceptance \
  --profile smoke \
  --base-url "$CATALOG_BASE_URL" \
  --performance-api-key "$PERFTEST_API_KEY" \
  --output "../../.workshop-tmp/dotnet-<slice-name>-acceptance.json"
cd ../..
git diff --check
git add -- dotnet
git diff --cached --check
git commit -m "Complete bounded .NET rewrite slice <slice-name>"
```

Record the human decision and command result in
`evidence/review-checklist.md`. The application must be running for the shared live
smoke profile. Run the full profile instead when a slice changes schema, persistence,
import, or database failure behavior. Static contract tests and documentation
vocabulary never substitute for live behavior. Reject the diff rather than patching
around a contract failure, and do not call a slice accepted until its passing diff is
committed.

**Stop and replan** if a slice changes the SQL schema without explicit review,
weakens canonical image-key checks, adds credentials to source, adds a broad catch,
changes one-container topology, requires a frozen-interface edit, introduces an
unreviewed package, or fails characterization/acceptance. Return to the last passing
slice, update `bounded-plan.md`, and obtain approval again.

## 4. Committed source and container checkpoint

Every accepted rewrite slice must already be committed. Fail before deriving source
identity if tracked, staged, or untracked implementation bytes remain. The lowercase
full 40-hex commit produced here is the single identity used by the image tag,
Container Apps revisions, migration report, runtime evidence, and handoff.

**Executable proof (PowerShell)**

```powershell
$Dirty = git status --porcelain -- dotnet data
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not [string]::IsNullOrWhiteSpace(($Dirty -join "`n"))) {
    throw 'Commit every accepted slice and clean the implementation tree first.'
}

$SourceCommitLines = git rev-parse HEAD
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$SourceCommit = ($SourceCommitLines -join '').Trim()
if ($SourceCommit -cnotmatch '^[0-9a-f]{40}$') {
    throw 'SOURCE_COMMIT must be a lowercase full 40-hex commit.'
}

docker buildx build --platform linux/amd64 --load `
  -f dotnet/Dockerfile `
  -t "catalog-dotnet:$SourceCommit" .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

docker image inspect "catalog-dotnet:$SourceCommit" `
  --format '{{json .Config.User}} {{json .Config.ExposedPorts}}'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

## 5. P4 bootstrap, native migration, and ordered cutover

Use protected parameter documents outside the repository. They supply every required
value from `infra/main.bicep`, including secure values, source VM/VNet resource IDs,
facilitator identity, and the fixed `dotnet-sqlserver`/`azure-blob` selection. The
following participant commands are PowerShell-native; this reference does not claim
they were run.

### Bootstrap and immutable ACR publication

Run bootstrap from the committed repository root with the isolated facilitator
profile. Every state-changing command has an immediate exit guard.

```powershell
$env:AZURE_CONFIG_DIR = Join-Path $HOME '.azure-365'
New-Item -ItemType Directory -Force evidence | Out-Null
$BootstrapLines = az deployment sub create `
  --name "p5-dotnet-bootstrap-$($SourceCommit.Substring(0, 12))" `
  --location swedencentral `
  --template-file infra/main.bicep `
  --parameters "@C:\protected\p5-dotnet-bootstrap.json" `
  --parameters deploymentStage=bootstrap stack=dotnet-sqlserver `
    imageProvider=azure-blob sourceCommit=$SourceCommit `
  --query properties.outputs.targetOutput.value `
  --output json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$BootstrapOutput = $BootstrapLines -join [Environment]::NewLine
[System.IO.File]::WriteAllText(
  (Join-Path $PWD 'evidence\azure-target-output.json'),
  $BootstrapOutput,
  [System.Text.UTF8Encoding]::new($false)
)

$Bootstrap = $BootstrapOutput | ConvertFrom-Json
$SubscriptionId = ($Bootstrap.containerRegistry.resourceId -split '/')[2]
$RegistryName = ($Bootstrap.containerRegistry.resourceId -split '/')[-1]
$LoginServer = $Bootstrap.containerRegistry.loginServer

az acr login --name $RegistryName --subscription $SubscriptionId
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$PublishedTag = "$LoginServer/catalog-dotnet:$SourceCommit"
docker tag "catalog-dotnet:$SourceCommit" $PublishedTag
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
docker push $PublishedTag
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$ImageDigestLines = az acr manifest show-metadata `
  --registry $RegistryName `
  --name "catalog-dotnet:$SourceCommit" `
  --subscription $SubscriptionId `
  --query digest `
  --output tsv
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$ImageDigest = ($ImageDigestLines -join '').Trim()
if ($ImageDigest -cnotmatch '^sha256:[0-9a-f]{64}$') {
    throw 'ACR did not return an immutable sha256 manifest digest.'
}
$ImageReference = "$LoginServer/catalog-dotnet@$ImageDigest"
```

The commit tag locates registry evidence only. Application deployments receive
`ImageDigest` and therefore resolve to `ImageReference`; never deploy `latest`, the
commit tag, or another mutable reference.

### Windows P3 source-VM migration

On the exact Windows P3 source VM declared in
`target-output.network.migrationSourceVmResourceId`, first verify the checkout and
derive source identity. Only after that clean check, copy the bootstrap target output
from `C:\protected\azure-target-output.json` into the checkout. Run all native
transfer there, not from Linux, macOS, Cloud Shell, or the application. Supply
the source password only through the protected prompt. The command sequence clears it
before invoking any command that forbids migration secrets.

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

$Dirty = git status --porcelain -- dotnet data
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not [string]::IsNullOrWhiteSpace(($Dirty -join "`n"))) {
    throw 'The Windows source-VM checkout must match committed SOURCE_COMMIT bytes.'
}
$SourceCommitLines = git rev-parse HEAD
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$SourceCommit = ($SourceCommitLines -join '').Trim()
if ($SourceCommit -cnotmatch '^[0-9a-f]{40}$') {
    throw 'SOURCE_COMMIT must be a lowercase full 40-hex commit.'
}

$RepositoryRoot = (Resolve-Path .).Path
$TargetOutput = Join-Path $RepositoryRoot 'evidence\azure-target-output.json'
$MigrationReport = Join-Path $RepositoryRoot 'evidence\migration-report.json'
$ImageDirectory = Join-Path $RepositoryRoot 'data\images'
$DatabaseArtifact = 'C:\protected\catalog.bacpac'
New-Item -ItemType Directory -Force (Join-Path $RepositoryRoot 'evidence') | Out-Null
Copy-Item 'C:\protected\azure-target-output.json' $TargetOutput
$Target = Get-Content $TargetOutput -Raw | ConvertFrom-Json
if ($Target.sourceCommit -cne $SourceCommit) {
  throw 'The protected bootstrap target does not match this source commit.'
}
$TargetDatabaseResourceId = $Target.database.resourceId
$TargetImageResourceId = $Target.images.resourceId

Push-Location tests\acceptance
try {
$ExportExit = 0
try {
  Remove-Item Env:MIGRATION_TARGET_ADMINISTRATOR_PASSWORD `
    -ErrorAction SilentlyContinue
  Remove-Item Env:MIGRATION_TARGET_APPLICATION_PASSWORD `
    -ErrorAction SilentlyContinue
  $env:MIGRATION_SOURCE_DATABASE_PASSWORD = Read-ProtectedValue `
    'Source SQL Server database password'
  uv --no-config run catalog-migrate sql export `
    --source-server '<source-sql-server>' `
    --source-database '<source-database>' `
    --source-username '<source-user>' `
    --source-commit $SourceCommit `
    --target-output $TargetOutput `
    --artifact $DatabaseArtifact
  $ExportExit = $LASTEXITCODE
}
finally {
  Remove-Item Env:MIGRATION_SOURCE_DATABASE_PASSWORD `
    -ErrorAction SilentlyContinue
}
if ($ExportExit -ne 0) { throw 'SQL export failed' }

uv --no-config run catalog-migrate sql import `
  --artifact $DatabaseArtifact `
  --source-commit $SourceCommit `
  --target-output $TargetOutput `
  --target-resource-id $TargetDatabaseResourceId `
  --confirm-target-resource-id $TargetDatabaseResourceId `
  --execute
if ($LASTEXITCODE -ne 0) { throw 'SQL import failed' }

uv --no-config run catalog-migrate images copy `
  --source-directory $ImageDirectory `
  --source-commit $SourceCommit `
  --target-output $TargetOutput `
  --target-resource-id $TargetImageResourceId `
  --confirm-target-resource-id $TargetImageResourceId `
  --execute
if ($LASTEXITCODE -ne 0) { throw 'image copy failed' }

uv --no-config run catalog-migrate verify `
  --stack dotnet-sqlserver `
  --source-commit $SourceCommit `
  --database-artifact $DatabaseArtifact `
  --target-output $TargetOutput `
  --output $MigrationReport
if ($LASTEXITCODE -ne 0) { throw 'migration verification failed' }
}
finally { Pop-Location }
```

The CLI is the only data-transfer path. It must refuse a nonempty target, verify Blob
bytes and Azure SQL contents, remove the imported legacy privileged principal, and
leave the source and artifact available for rollback.

### Baseline then release

Return the verified migration evidence to the facilitator checkout. Deploy baseline
first and release second with the same digest. The release deployment output replaces
the bootstrap document before handoff. The retained baseline is verified only after
release has made it inactive.

```powershell
az deployment sub create `
  --name "p5-dotnet-baseline-$($SourceCommit.Substring(0, 12))" `
  --location swedencentral `
  --template-file infra/main.bicep `
  --parameters "@C:\protected\p5-dotnet-application.json" `
  --parameters deploymentStage=application applicationRevisionRole=baseline `
    stack=dotnet-sqlserver imageProvider=azure-blob `
    sourceCommit=$SourceCommit imageDigest=$ImageDigest `
  --output none
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$ReleaseLines = az deployment sub create `
  --name "p5-dotnet-release-$($SourceCommit.Substring(0, 12))" `
  --location swedencentral `
  --template-file infra/main.bicep `
  --parameters "@C:\protected\p5-dotnet-application.json" `
  --parameters deploymentStage=application applicationRevisionRole=release `
    stack=dotnet-sqlserver imageProvider=azure-blob `
    sourceCommit=$SourceCommit imageDigest=$ImageDigest `
  --query properties.outputs.targetOutput.value `
  --output json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$ReleaseOutput = $ReleaseLines -join [Environment]::NewLine
[System.IO.File]::WriteAllText(
  (Join-Path $PWD 'evidence\azure-target-output.json'),
  $ReleaseOutput,
  [System.Text.UTF8Encoding]::new($false)
)

$Release = $ReleaseOutput | ConvertFrom-Json
$ContainerAppName = $Release.application.containerAppName
$ResourceGroup = $Release.resourceGroup.name
$BaselineRevision = "$ContainerAppName--baseline-$($SourceCommit.Substring(0, 12))"
$BaselineLines = az containerapp revision show `
  --resource-group $ResourceGroup `
  --name $ContainerAppName `
  --revision $BaselineRevision `
  --subscription $SubscriptionId `
  --query '{active:properties.active,health:properties.healthState,error:properties.provisioningError,images:properties.template.containers[].image}' `
  --output json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$BaselineJson = $BaselineLines -join [Environment]::NewLine
[System.IO.File]::WriteAllText(
  (Join-Path $PWD 'evidence\baseline-revision.json'),
  $BaselineJson,
  [System.Text.UTF8Encoding]::new($false)
)
$Baseline = $BaselineJson | ConvertFrom-Json
if (
  $Baseline.active -ne $false -or
  $Baseline.health -ne 'Healthy' -or
  @($Baseline.images).Count -ne 1 -or
  @($Baseline.images)[0] -ne $ImageReference
) {
    throw 'The retained baseline revision failed immutable rollback verification.'
}
```

At this checkpoint, `evidence\azure-target-output.json` is the application-stage
release output and describes exactly one application container at
`$ImageReference`.

## 6. Full evidence and handoff checkpoint

Run the native suite after the final diff and retain its TRX under `evidence/`.
Create `evidence/runtime-test-report.json` against
`workshop/contracts/runtime-test-evidence.schema.json`; it must reference that
native TRX and its fourteen real passing test identities. Run full shared acceptance
against the release and write
`evidence/acceptance-report.json`. Collect real trace, metric, log, and resource
query results into `evidence/telemetry-report.json`; never synthesize telemetry.

Complete:

- `evidence/decision-log.md` with accepted/rejected design choices and an explicit
  `## Architecture delta` section listing changed boundaries and confirming Azure
  SQL, one application container, Blob images, ACA readiness, external
  configuration, native `catalog-migrate`, and P4 Bicep remain preserved;
- `evidence/rollback-runbook.md` with prerequisites, exact retained baseline
  revision, traffic restoration, database/artifact boundaries, verification, and
  escalation;
- all registry-required shared and path evidence.

The frozen protocol is
`catalog-migrate render-handoff --path copilot-rewrite --rollback-runbook <path>`.

**Executable proof**

```powershell
$RepositoryRoot = (Resolve-Path .).Path
Push-Location tests\acceptance
try {
uv --no-config run catalog-migrate render-handoff `
  --target-output (Join-Path $RepositoryRoot 'evidence\azure-target-output.json') `
  --migration-report (Join-Path $RepositoryRoot 'evidence\migration-report.json') `
  --acceptance-report (Join-Path $RepositoryRoot 'evidence\acceptance-report.json') `
  --telemetry-report (Join-Path $RepositoryRoot 'evidence\telemetry-report.json') `
  --runtime-test-report (Join-Path $RepositoryRoot 'evidence\runtime-test-report.json') `
  --path copilot-rewrite `
  --rollback-revision $BaselineRevision `
  --rollback-runbook (Join-Path $RepositoryRoot 'evidence\rollback-runbook.md') `
  --output (Join-Path $RepositoryRoot 'evidence\modernization-contract.json')
if ($LASTEXITCODE -ne 0) { throw 'handoff rendering failed' }

uv --no-config run python -m catalog_acceptance.handoff_cli `
  (Join-Path $RepositoryRoot 'evidence\modernization-contract.json') `
  --contracts (Join-Path $RepositoryRoot 'workshop\contracts') `
  --repository-root $RepositoryRoot
if ($LASTEXITCODE -ne 0) { throw 'handoff validation failed' }
}
finally { Pop-Location }
```

**Expected checkpoint**

Full acceptance passes with no required skips, native runtime and telemetry evidence
validate, the handoff reports path `copilot-rewrite`, database family `azure-sql`,
Blob verification, one digest-pinned image, and a distinct retained rollback
revision.

## Cleanup and rejoin

Remove only local transient artifacts after evidence has been copied:

```bash
rm -rf .workshop-tmp
git status --short
```

Do not remove `evidence/`, migration artifacts, or the retained baseline revision.
Rejoin the shared workshop at the next challenge only after handoff validation passes
and a human signs `review-checklist.md`, `decision-log.md`, and the rollback runbook.
