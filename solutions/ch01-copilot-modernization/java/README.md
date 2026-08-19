# Path 1C solution: Java and PostgreSQL

Run this guide on the selected Java P3 VM from the repository root. The source
is Microsoft OpenJDK `17.0.20+8` with Spring Boot `3.5.16`; the accepted target
is Microsoft OpenJDK `21.0.12+8`, Spring Boot `4.0.7`, PostgreSQL Flexible
Server `18`, and repository `catalog-java`. PostgreSQL migration is
`pg-dump-restore` with native client `18.6`.

The target dependencies and images are pinned in
`workshop/toolchain.lock.json`:

- Maven Wrapper `3.3.4` and checksum-pinned Maven `3.9.16`
- `com.azure:azure-identity:1.18.4`
- `com.azure:azure-identity-extensions:1.2.9`
- `com.azure:azure-storage-blob:12.35.1`
- `com.azure:azure-monitor-opentelemetry-autoconfigure:1.6.0`
- `io.opentelemetry:opentelemetry-api:1.58.0`
- build/runtime image
  `mcr.microsoft.com/openjdk/jdk:21-azurelinux@sha256:06ec8d4b09883cb695aa37e3ae85d1188f124b6dbcfeff97eeb09a926f7c389f`

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

The unified `vscjava.migrate-java-to-azure@1.23.26081703` package is the
required modernization product. `vscjava.vscode-java-upgrade` is not a
substitute for Path 1C.

## 2. Assess and edit the plan

Open the repository root in VS Code and start the installed GitHub Copilot
modernization IDE workflow in guided mode. Scope changes to `java/` while
allowing read-only access to contracts and target assets.

Require findings for:

- Microsoft OpenJDK `17.0.20+8` to `21.0.12+8`;
- Spring Boot `3.5.16` to `4.0.7`, Maven, JPA, Flyway, and test compatibility;
- ACA health/readiness, non-root container behavior, and cloud readiness;
- environment-only secrets and managed identity;
- Maven dependency/CVE status;
- PostgreSQL connectivity, schema ownership, transactions, and managed-identity
  JDBC preparation;
- local seed/image paths and file logging.

Save the human-reviewed assessment as `evidence/assessment.md`. Generate a plan,
edit it before approval, and save it as
`evidence/modernization-plan.md`. Preserve PostgreSQL Flexible Server,
`azure-blob`, managed identity, direct Azure Monitor export,
`java/Dockerfile`, and `infra/main.bicep`. The plan must identify database
transfer as a separate native `catalog-migrate` phase.

## 3. Execute only bounded supported tasks

Use only preflighted supported Java runtime/framework upgrade, managed identity
for database code preparation, Blob integration, file-logging modernization,
containerization, IaC, and deployment tasks that match the repository finding.
The predefined local-file-to-Azure-Files task is not valid for catalog images
because this path's frozen provider is Blob.

For each approved task:

```powershell
git status --short
# Run one reviewed IDE task.
git diff --check
git diff --stat
git diff
Push-Location java
.\mvnw test
.\mvnw package
Pop-Location
```

Record every task in `evidence/task-results.json` with supported capability,
scope, human decision, changed files, validation command/exit code, and artifact
paths. Record exact runtime/framework/dependency versions, build/test results,
CVE results, and unresolved findings in
`evidence/build-test-cve-summary.md`.

Expected final artifacts include `java/pom.xml`, Flyway migration
`java/src/main/resources/db/migration/V1__contract_baseline.sql`,
managed-identity JDBC configuration, `AzureBlobImageStore`, and direct Azure
Monitor autoconfiguration. Generated output is evidence, not proof of behavior.

Stop and replan if a task changes files outside its preview, changes the
database family, selects Azure Files, writes a password, weakens TLS, changes a
frozen contract, introduces an unpinned dependency, replaces immutable images,
skips tests, or cannot map to a supported task.

After all modernization tasks are accepted, commit the complete reviewed delta
and recapture its identity. Do not use `$StartingCommit` for any build,
migration, deployment, or evidence:

```powershell
New-Item -ItemType Directory -Force evidence\runtime-tests | Out-Null
Copy-Item java\target\surefire-reports\*.xml evidence\runtime-tests\
Remove-Item -Recurse -Force java\target
git add -- java evidence\assessment.md evidence\modernization-plan.md `
  evidence\task-results.json evidence\build-test-cve-summary.md `
  evidence\ide-extensions.txt evidence\runtime-tests
git commit -m 'Accept Java Copilot modernization tasks'
if (git status --porcelain) {
  throw 'Accepted modernization changes must be committed and the worktree clean.'
}
$SourceCommit = (git rev-parse HEAD).Trim()
if ($SourceCommit -cnotmatch '^[0-9a-f]{40}$') {
  throw 'Final source commit must be an exact lowercase full 40-hex SHA.'
}
```

Create `evidence/runtime-test-report.json` for the preserved Surefire XML under
`evidence/runtime-tests/` by following
`workshop/contracts/runtime-test-evidence.schema.json`. It must bind all
fourteen exact frozen test identities to `$SourceCommit`.

## 4. Build the immutable container

From the repository root:

```powershell
docker buildx build --platform linux/amd64 --load `
  --file java/Dockerfile `
  --tag "catalog-java:$SourceCommit" .
```

Review that the image runs as numeric user `10001`, listens on `8080`, and
externalizes database, Blob, and telemetry configuration. A supported IDE task
may prepare or review containerization, but the accepted artifact is the frozen
digest-pinned `java/Dockerfile`.

Publish exactly `catalog-java:$SourceCommit` through the
facilitator-approved ACR workflow. Never use `latest` or another mutable tag.

## 5. Native PostgreSQL and Blob cutover

The extension does not perform database cutover. Run all native commands on this
P3 source VM over the approved private migration path. The bootstrap output must
already exist at `evidence/azure-target-output.json`.

```powershell
$TargetOutput = (Resolve-Path evidence\azure-target-output.json).Path
$Target = Get-Content $TargetOutput -Raw | ConvertFrom-Json
if ($Target.deploymentStage -ne 'bootstrap' -or
    $Target.stack -ne 'java-postgresql' -or
    $Target.images.provider -ne 'azure-blob') {
  throw 'Wrong bootstrap target for the Java modernization slice.'
}
$DatabaseResourceId = $Target.database.resourceId
$ImageResourceId = $Target.images.resourceId
$Artifact = 'C:\ProgramData\MicroHack\migration\catalog.dump'
New-Item -ItemType Directory -Force (Split-Path $Artifact) | Out-Null

Push-Location tests\acceptance
$env:MIGRATION_SOURCE_DATABASE_PASSWORD = '<source-postgresql-password>'
uv --no-config run catalog-migrate postgresql export `
  --source-host 'localhost' `
  --source-port 5432 `
  --source-database 'catalog' `
  --source-username 'catalog' `
  --target-output $TargetOutput `
  --artifact $Artifact
$ExportExit = $LASTEXITCODE
Remove-Item Env:MIGRATION_SOURCE_DATABASE_PASSWORD
if ($ExportExit -ne 0) { exit $ExportExit }

$env:MIGRATION_TARGET_ADMINISTRATOR_PASSWORD = '<target-admin-password>'
if ($Target.database.authentication -eq 'password-secret') {
  $env:MIGRATION_TARGET_APPLICATION_PASSWORD = '<target-app-password>'
} else {
  Remove-Item Env:MIGRATION_TARGET_APPLICATION_PASSWORD `
    -ErrorAction SilentlyContinue
}
uv --no-config run catalog-migrate postgresql import `
  --artifact $Artifact `
  --target-output $TargetOutput `
  --target-resource-id $DatabaseResourceId `
  --confirm-target-resource-id $DatabaseResourceId `
  --execute
$ImportExit = $LASTEXITCODE
Remove-Item Env:MIGRATION_TARGET_ADMINISTRATOR_PASSWORD
Remove-Item Env:MIGRATION_TARGET_APPLICATION_PASSWORD `
  -ErrorAction SilentlyContinue
if ($ImportExit -ne 0) { exit $ImportExit }

uv --no-config run catalog-migrate images copy `
  --source-directory (Resolve-Path ..\..\data\images) `
  --target-output $TargetOutput `
  --target-resource-id $ImageResourceId `
  --confirm-target-resource-id $ImageResourceId `
  --execute
$ImageCopyExit = $LASTEXITCODE
if ($ImageCopyExit -ne 0) { exit $ImageCopyExit }

if ($Target.database.authentication -eq 'password-secret') {
  $env:MIGRATION_TARGET_APPLICATION_PASSWORD = '<target-app-password>'
} else {
  Remove-Item Env:MIGRATION_TARGET_APPLICATION_PASSWORD `
    -ErrorAction SilentlyContinue
}
uv --no-config run catalog-migrate verify `
  --stack java-postgresql `
  --source-commit $SourceCommit `
  --database-artifact $Artifact `
  --target-output $TargetOutput `
  --output (Join-Path (Resolve-Path ..\..).Path 'evidence\migration-report.json')
$VerifyExit = $LASTEXITCODE
Remove-Item Env:MIGRATION_TARGET_APPLICATION_PASSWORD `
  -ErrorAction SilentlyContinue
if ($VerifyExit -ne 0) { exit $VerifyExit }
Pop-Location
```

For managed-identity mode, `catalog-migrate postgresql import` requires the
isolated `$HOME/.azure-365` facilitator identity, a transient `oss-rdbms`
token, and no `MIGRATION_TARGET_APPLICATION_PASSWORD`. For password-secret mode
that application password is scoped separately to import and verification. It
is cleared immediately after each command, so image copy and handoff receive no
migration secret. Never attribute export, restore, principal creation,
verification, or schema/data cutover to the extension.

## 6. Deploy baseline and release

Use reviewed `infra/main.bicep` application-stage deployments. Deploy the same
`catalog-java@$ImageDigest` first as `baseline`, then as `release`. Supply the
PostgreSQL administrator secret and any mode-specific application secret only
through protected facilitator inputs.

Capture exact registry evidence before deployment:

```powershell
$SubscriptionId = $Target.resourceGroup.resourceId.Split('/')[2]
$RegistryName = $Target.containerRegistry.resourceId.Split('/')[-1]
$ImageDigest = (
  az acr manifest show-metadata `
    --registry $RegistryName `
    --name "catalog-java:$SourceCommit" `
    --subscription $SubscriptionId `
    --query digest `
    --output tsv
).Trim()
if ($ImageDigest -notmatch '^sha256:[0-9a-f]{64}$') {
  throw 'ACR did not return an immutable manifest digest.'
}
[ordered]@{
  repository = 'catalog-java'
  tag = $SourceCommit
  digest = $ImageDigest
} | ConvertTo-Json | Set-Content -Encoding utf8 `
  evidence\container-registry.json
```

After release deployment, replace `evidence/azure-target-output.json` with the
release-role application-stage output and verify the retained rollback:

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

The baseline must be healthy, inactive, distinct, single-container, and on the
same digest as release.

## 7. Full acceptance, telemetry, and handoff

Run full managed-target acceptance:

```powershell
Push-Location tests\acceptance
$env:CATALOG_DATABASE_KIND = 'postgresql'
$env:CATALOG_DATABASE_HOST = $ReleaseTarget.database.server
$env:CATALOG_DATABASE_NAME = $ReleaseTarget.database.database
$env:CATALOG_DATABASE_USERNAME = '<acceptance-verifier>'
$env:CATALOG_DATABASE_PASSWORD = '<acceptance-verifier-password>'
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
Remove-Item Env:PERFTEST_API_KEY
Remove-Item Env:CATALOG_DATABASE_PASSWORD
if ($AcceptanceExit -ne 0) { exit $AcceptanceExit }
Pop-Location
```

Exercise normal, import, performance, and controlled failure paths. Query Azure
Monitor and store normalized nonempty results in
`evidence/telemetry/resources.json`, `traces.json`, `metrics.json`, and
`logs.json`. Build `evidence/telemetry-report.json` against
`workshop/contracts/telemetry-evidence.schema.json` with service
`mh-catalog-java`, `$SourceCommit` as `service.version`, and the release
revision. Empty signal evidence is a failure.

Write `evidence/rollback-runbook.md` with exact subscription, resource group,
Container App, release and baseline revisions, immutable digest, inspection,
activation, traffic shift, release deactivation, health/readiness/full
acceptance, and escalation steps. Database rollback is never implicit. If
native restore or verification fails, stop before deployment and retain the
source database as authority. `catalog-migrate` supports no resource deletion.

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

```powershell
Remove-Item Env:MIGRATION_SOURCE_DATABASE_PASSWORD -ErrorAction SilentlyContinue
Remove-Item Env:MIGRATION_TARGET_ADMINISTRATOR_PASSWORD `
  -ErrorAction SilentlyContinue
Remove-Item Env:MIGRATION_TARGET_APPLICATION_PASSWORD `
  -ErrorAction SilentlyContinue
Remove-Item Env:CATALOG_DATABASE_PASSWORD -ErrorAction SilentlyContinue
Remove-Item Env:PERFTEST_API_KEY -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force java\target -ErrorAction SilentlyContinue
Remove-Item -Force $Artifact -ErrorAction SilentlyContinue
git status --short
```

Retain the required evidence, reviewed source delta, and frozen target assets.
Rejoin only after handoff validation succeeds. Downstream challenges consume
`evidence/modernization-contract.json`; assessment, plan, and task output do not
prove runtime behavior.

## Optional appendix

The preview Modernize CLI is optional and not required. It cannot replace the
signed IDE workflow, native Maven tests, `catalog-migrate`, full acceptance,
telemetry evidence, or handoff validation.
