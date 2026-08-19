# Path 1C solution: .NET and SQL Server

Run this guide on the selected .NET P3 VM from the repository root. The source
is .NET runtime `8.0.30` with SDK `8.0.424`; the accepted target is .NET runtime
`10.0.11` with SDK `10.0.400`, ASP.NET Core/EF Core `10.0.11`, Azure SQL
Database, and repository `catalog-dotnet`. SQL migration is
`sqlpackage-bacpac` with locked SqlPackage `170.4.83`.

The target packages and images are pinned in `workshop/toolchain.lock.json`:

- `Azure.Identity` `1.21.0`
- `Azure.Storage.Blobs` `12.29.1`
- `Azure.Monitor.OpenTelemetry.Exporter` `1.8.3`
- build image
  `mcr.microsoft.com/dotnet/sdk:10.0.400-azurelinux3.0-amd64@sha256:679e7b7e9d0315ad34438bee49b4fb0658c4c42a3aa08ae8557d1bd03f49c28b`
- runtime image
  `mcr.microsoft.com/dotnet/aspnet:10.0.11-azurelinux3.0-amd64@sha256:d21a49ce9556f5e50afc5a33cc45ec7a40b5739f10397368810193666e559a79`

## 1. Freeze source and IDE evidence

```powershell
$ErrorActionPreference = 'Stop'
$StartingCommit = (git rev-parse HEAD).Trim()
if ($StartingCommit -cnotmatch '^[0-9a-f]{40}$') {
  throw 'Starting commit must be an exact lowercase 40-hex SHA.'
}
if (git status --porcelain) {
  throw 'Begin modernization from a clean worktree.'
}

New-Item -ItemType Directory -Force evidence | Out-Null
$ExtensionRoot = 'C:\ProgramData\MicroHack\vscode-extensions'
$RequiredExtensions = @(
  'github.copilot@1.388.0',
  'github.copilot-chat@0.48.1',
  'vscjava.migrate-java-to-azure@1.23.26081703'
)
$InstalledExtensions = @(
  code --list-extensions --show-versions --extensions-dir $ExtensionRoot
)
$RequiredExtensions | ForEach-Object {
  if ($InstalledExtensions -notcontains $_) {
    throw "Missing locked signed extension: $_"
  }
}
$InstalledExtensions | Sort-Object |
  Set-Content -Encoding utf8 evidence\ide-extensions.txt
```

The unified `vscjava.migrate-java-to-azure@1.23.26081703` extension is the
required modernization product on this .NET VM. Do not substitute
`ms-dotnettools.vscode-dotnet-modernize` or `ms-dotnettools.upgrade-agent`.

## 2. Assess and edit the plan

Open the repository root in VS Code and start the installed GitHub Copilot
modernization IDE workflow in guided mode. Scope assessment to `dotnet/` while
allowing it to read the repository contracts and target assets.

Require findings for:

- .NET `8.0.30`/SDK `8.0.424` to .NET `10.0.11`/SDK `10.0.400`;
- ASP.NET Core and EF Core compatibility;
- ACA health/readiness, non-root container behavior, and cloud readiness;
- environment-only secrets and managed identity;
- NuGet dependency/CVE status;
- SQL Server connectivity, transactions, schema migrations, and Azure SQL
  managed-identity code preparation;
- local seed/image paths and any file logging.

Save the reviewed assessment as `evidence/assessment.md`. Generate a plan, then
edit it before approval and save it as `evidence/modernization-plan.md`. Keep
Azure SQL, `azure-blob`, managed identity, direct Azure Monitor exporters,
`dotnet/Dockerfile`, and `infra/main.bicep`. Mark database transfer as an
external native `catalog-migrate` phase.

## 3. Execute only bounded supported tasks

Use the IDE's supported .NET runtime/framework upgrade, Azure SQL
managed-identity preparation, Blob integration, containerization, IaC, and
deployment tasks only after the task preview names its file scope and validation.
For every task:

```powershell
git status --short
# Run one reviewed IDE task.
git diff --check
git diff --stat
git diff
dotnet restore dotnet\LegoCatalog.sln
dotnet test dotnet\LegoCatalog.sln --logger trx `
  --results-directory evidence
```

Update `evidence/task-results.json` after each task with its name, supported
capability, files changed, human decision, command, exit code, and artifact
paths. Update `evidence/build-test-cve-summary.md` with the exact SDK/runtime,
test result, dependency/CVE result, and unresolved findings.

Expected final application artifacts include
`dotnet/src/LegoCatalog.App/LegoCatalog.App.csproj`, the EF migration under
`dotnet/src/LegoCatalog.App/Data/Migrations/`, managed-identity SQL
configuration, `AzureBlobImageStore`, and direct Azure Monitor exporters.
Assessment or task success is not behavioral proof.

Stop and replan if a task changes files outside its preview, changes Azure SQL
to another database family, adds SQL credentials to source, chooses Azure
Files, weakens TLS, changes a frozen contract, replaces immutable image
references, skips tests, or reports an unsupported transformation.

After all modernization tasks are accepted, commit the complete reviewed delta
and recapture its identity. Do not use `$StartingCommit` for any build,
migration, deployment, or evidence:

```powershell
git add -- dotnet evidence\assessment.md evidence\modernization-plan.md `
  evidence\task-results.json evidence\build-test-cve-summary.md
git commit -m 'Accept .NET Copilot modernization tasks'
if (git status --porcelain) {
  throw 'Accepted modernization changes must be committed and the worktree clean.'
}
$SourceCommit = (git rev-parse HEAD).Trim()
if ($SourceCommit -cnotmatch '^[0-9a-f]{40}$') {
  throw 'Final source commit must be an exact lowercase full 40-hex SHA.'
}
```

Create `evidence/runtime-test-report.json` for the native TRX by following
`workshop/contracts/runtime-test-evidence.schema.json`. It must reference the
TRX containing all fourteen exact frozen test identities and bind
`sourceCommit` to `$SourceCommit`.

## 4. Build the immutable container

Use the frozen Dockerfile from the repository root:

```powershell
docker buildx build --platform linux/amd64 --load `
  --file dotnet/Dockerfile `
  --tag "catalog-dotnet:$SourceCommit" .
```

Review that the image is non-root, listens on `8080`, and takes database,
Blob, and telemetry configuration from the environment. A supported IDE
containerization task may prepare or review these changes, but
`dotnet/Dockerfile` and its locked digests are the accepted artifact.

Use the facilitator-approved ACR workflow to publish exactly
`catalog-dotnet:$SourceCommit`. Never use `latest`. Do not continue until the
registry returns an immutable digest.

## 5. Native SQL and Blob cutover

The extension does not perform database cutover. Run the frozen migration CLI
on this P3 source VM over the approved private migration path. The bootstrap
output must already exist at `evidence/azure-target-output.json`.

```powershell
$TargetOutput = (Resolve-Path evidence\azure-target-output.json).Path
$Target = Get-Content $TargetOutput -Raw | ConvertFrom-Json
if ($Target.deploymentStage -ne 'bootstrap' -or
    $Target.stack -ne 'dotnet-sqlserver' -or
    $Target.images.provider -ne 'azure-blob') {
  throw 'Wrong bootstrap target for the .NET modernization slice.'
}
$DatabaseResourceId = $Target.database.resourceId
$ImageResourceId = $Target.images.resourceId
$Artifact = 'C:\ProgramData\MicroHack\migration\catalog.bacpac'
New-Item -ItemType Directory -Force (Split-Path $Artifact) | Out-Null

Push-Location tests\acceptance
$env:MIGRATION_SOURCE_DATABASE_PASSWORD = '<source-sql-password>'
uv --no-config run catalog-migrate sql export `
  --source-server '.\SQLEXPRESS' `
  --source-database 'LegoCatalog' `
  --source-username 'catalog' `
  --target-output $TargetOutput `
  --artifact $Artifact
$ExportExit = $LASTEXITCODE
Remove-Item Env:MIGRATION_SOURCE_DATABASE_PASSWORD
if ($ExportExit -ne 0) { exit $ExportExit }

uv --no-config run catalog-migrate sql import `
  --artifact $Artifact `
  --target-output $TargetOutput `
  --target-resource-id $DatabaseResourceId `
  --confirm-target-resource-id $DatabaseResourceId `
  --execute
$ImportExit = $LASTEXITCODE
if ($ImportExit -ne 0) { exit $ImportExit }

uv --no-config run catalog-migrate images copy `
  --source-directory (Resolve-Path ..\..\data\images) `
  --target-output $TargetOutput `
  --target-resource-id $ImageResourceId `
  --confirm-target-resource-id $ImageResourceId `
  --execute
$ImageCopyExit = $LASTEXITCODE
if ($ImageCopyExit -ne 0) { exit $ImageCopyExit }

uv --no-config run catalog-migrate verify `
  --stack dotnet-sqlserver `
  --source-commit $SourceCommit `
  --database-artifact $Artifact `
  --target-output $TargetOutput `
  --output (Join-Path (Resolve-Path ..\..).Path 'evidence\migration-report.json')
$VerifyExit = $LASTEXITCODE
if ($VerifyExit -ne 0) { exit $VerifyExit }
Pop-Location
```

Do not claim the extension exported, imported, verified, or cut over the
database. `catalog-migrate sql import` removes the imported legacy
`catalog`/`db_owner` principal before the managed application principal is
created and verification requires it to remain absent.

## 6. Deploy baseline and release

Use only reviewed `infra/main.bicep` application-stage deployments. Deploy the
same `catalog-dotnet@$ImageDigest` first with
`applicationRevisionRole=baseline`, then with
`applicationRevisionRole=release`. Supply secrets through protected
facilitator inputs, never command literals or tracked parameter files.

Before either application-stage deployment, capture exact registry evidence:

```powershell
$SubscriptionId = $Target.resourceGroup.resourceId.Split('/')[2]
$RegistryName = $Target.containerRegistry.resourceId.Split('/')[-1]
$ImageDigest = (
  az acr manifest show-metadata `
    --registry $RegistryName `
    --name "catalog-dotnet:$SourceCommit" `
    --subscription $SubscriptionId `
    --query digest `
    --output tsv
).Trim()
if ($ImageDigest -notmatch '^sha256:[0-9a-f]{64}$') {
  throw 'ACR did not return an immutable manifest digest.'
}
[ordered]@{
  repository = 'catalog-dotnet'
  tag = $SourceCommit
  digest = $ImageDigest
} | ConvertTo-Json | Set-Content -Encoding utf8 `
  evidence\container-registry.json
```

After release deployment, replace `evidence/azure-target-output.json` with the
release-role application-stage output. Verify the retained rollback revision
with the frozen query:

```powershell
$ReleaseTarget = Get-Content evidence\azure-target-output.json -Raw |
  ConvertFrom-Json
$ReleaseRevision = $ReleaseTarget.application.revisionName
if ($ReleaseTarget.deploymentStage -ne 'application' -or
    $ReleaseTarget.applicationRevisionRole -ne 'release' -or
    $ReleaseTarget.sourceCommit -ne $SourceCommit -or
    $ReleaseTarget.containerImage.digest -ne $ImageDigest -or
    $ReleaseRevision -ne (
      '{0}--release-{1}' -f $ReleaseTarget.application.containerAppName,
      $SourceCommit.Substring(0, 12)
    )) {
  throw 'Release output does not bind the final commit, digest, and revision.'
}
$RollbackRevision = '{0}--baseline-{1}' -f `
  $ReleaseTarget.application.containerAppName, $SourceCommit.Substring(0, 12)
az containerapp revision show `
  --resource-group $ReleaseTarget.resourceGroup.name `
  --name $ReleaseTarget.application.containerAppName `
  --revision $RollbackRevision `
  --subscription $SubscriptionId `
  --query '{active:properties.active,health:properties.healthState,error:properties.provisioningError,images:properties.template.containers[].image}' `
  --output json | Set-Content -Encoding utf8 evidence\rollback-revision.json
```

The baseline must be healthy, inactive, distinct from release, contain one
container, and reference the same digest.

## 7. Full acceptance, telemetry, and handoff

Run full acceptance from `tests/acceptance`. Azure SQL is Entra-only, so use a
transient token in `SQLCMDACCESS_TOKEN`, not SQL username/password:

```powershell
Push-Location tests\acceptance
$env:AZURE_CONFIG_DIR = Join-Path $HOME '.azure-365'
$env:SQLCMDACCESS_TOKEN = (
  az account get-access-token `
    --resource https://database.windows.net/ `
    --query accessToken --output tsv
).Trim()
$env:CATALOG_DATABASE_KIND = 'sqlserver'
$env:CATALOG_DATABASE_HOST = $ReleaseTarget.database.server
$env:CATALOG_DATABASE_NAME = $ReleaseTarget.database.database
$env:CATALOG_DATABASE_SSL_MODE = 'require'
$env:CATALOG_DATABASE_TARGET = 'managed'
$env:PERFTEST_API_KEY = '<runtime-performance-api-key>'
uv --no-config run python -m catalog_acceptance `
  --profile full `
  --base-url $ReleaseTarget.application.url `
  --source-commit $SourceCommit `
  --image-digest $ImageDigest `
  --revision-name $ReleaseRevision `
  --output ..\..\evidence\acceptance-report.json
$AcceptanceExit = $LASTEXITCODE
Remove-Item Env:SQLCMDACCESS_TOKEN
Remove-Item Env:PERFTEST_API_KEY
if ($AcceptanceExit -ne 0) { exit $AcceptanceExit }
Pop-Location
```

Exercise normal, import, performance, and controlled failure paths. Query Azure
Monitor and write normalized nonempty results to
`evidence/telemetry/resources.json`, `traces.json`, `metrics.json`, and
`logs.json`. Build `evidence/telemetry-report.json` exactly from
`workshop/contracts/telemetry-evidence.schema.json`; use service
`mh-catalog-dotnet`, the source commit as `service.version`, and the release
revision. Empty query output fails the handoff.

Write `evidence/rollback-runbook.md` with exact subscription, resource group,
Container App, release revision, baseline revision, immutable digest, traffic
inspection, baseline activation, traffic shift, release deactivation,
health/readiness/full-acceptance verification, and escalation. Database rollback
is not automatic: if native import verification fails, stop before application
deployment and keep the source database authoritative; never delete resources
through `catalog-migrate`.

Render and validate handoff `1.3.0`:

```powershell
Push-Location tests\acceptance
uv --no-config run catalog-migrate render-handoff `
  --target-output ..\..\evidence\azure-target-output.json `
  --migration-report ..\..\evidence\migration-report.json `
  --acceptance-report ..\..\evidence\acceptance-report.json `
  --telemetry-report ..\..\evidence\telemetry-report.json `
  --runtime-test-report ..\..\evidence\runtime-test-report.json `
  --path copilot-modernization `
  --rollback-revision $RollbackRevision `
  --rollback-runbook ..\..\evidence\rollback-runbook.md `
  --output ..\..\evidence\modernization-contract.json

uv --no-config run python -m catalog_acceptance.handoff_cli `
  ..\..\evidence\modernization-contract.json `
  --contracts ..\..\workshop\contracts `
  --repository-root ..\..
Pop-Location
```

## 8. Clean transient files and rejoin

Remove only local transients after evidence is secured:

```powershell
Remove-Item Env:MIGRATION_SOURCE_DATABASE_PASSWORD -ErrorAction SilentlyContinue
Remove-Item Env:SQLCMDACCESS_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:PERFTEST_API_KEY -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force dotnet\src\LegoCatalog.App\bin, `
  dotnet\src\LegoCatalog.App\obj, dotnet\tests\LegoCatalog.App.Tests\bin, `
  dotnet\tests\LegoCatalog.App.Tests\obj -ErrorAction SilentlyContinue
Remove-Item -Force $Artifact -ErrorAction SilentlyContinue
git status --short
```

Keep the exact required evidence, reviewed source changes, and frozen target
assets. Rejoin the shared workshop only after the handoff validator succeeds;
downstream challenges consume `evidence/modernization-contract.json`, not IDE
assessment or task output.

## Optional appendix

The preview Modernize CLI is optional and not required for this solution. It
cannot replace the signed IDE workflow, native build/tests, `catalog-migrate`,
full acceptance, telemetry proof, or handoff validation.
