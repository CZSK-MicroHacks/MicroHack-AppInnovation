# Path 1C solution: Java and PostgreSQL

**Open this if** you chose [Path 1C: GitHub Copilot modernization](../../../challenges/ch01-copilot-modernization/README.md)
with the Java/PostgreSQL baseline and want the exact command for a step, the precise
ordering of commit → clean-tree check → source-commit recapture, or a way to finish when
time runs short. End to end this is a 5–7 hour path.

Run this guide on the selected Java legacy VM from the repository root. The source
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

## Where you work, and what the VM does not have

Every command here runs on the selected VM from Challenge 0, reached over Azure Bastion.
The source tree is at `C:\MicroHack\source`, extracted from a verified archive by the
provisioner. **That directory is what "the repository root" means in this and every other
workshop document.** Start each terminal with `cd C:\MicroHack\source`.

The VM ships a deliberately small, fully pinned toolchain. Pinned Git for Windows is part
of it, so `C:\MicroHack\source` is a real working tree: because the source arrives as a
verified archive rather than a clone, the provisioner initializes a repository there and
makes one baseline commit. There is **no Docker daemon**:

| You need | On the VM |
| --- | --- |
| the exact 40-character upstream source commit | the marker file `C:\MicroHack\source\.source-commit`, written by the provisioner when it extracts the source archive. Quote it as archive provenance and nothing else — GitHub has never seen that commit. |
| a container image build | `az acr build`, used in step 4, uploads the build context and builds inside Azure Container Registry, so no local daemon is required |
| to commit accepted modernization tasks | `git add` and `git commit` in `C:\MicroHack\source`, exactly as steps 1 and 3 write them |
| to publish them | `git push` to your own GitHub repository, exactly as step 3 writes it |

The two `git rev-parse HEAD` readings in steps 1 and 3 are both your own commits:
`$StartingCommit` is the baseline before you change anything, and `$SourceCommit` is the
pushed commit holding your reviewed modernization delta. Neither is the `.source-commit`
marker, so never substitute one for the other. See
[If a command will not run here](#if-a-command-will-not-run-here) at the end.

## 1. Freeze source and IDE evidence

```powershell
$ErrorActionPreference = 'Stop'
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

After all modernization tasks are accepted, commit the complete reviewed delta,
publish it to your own GitHub repository, and recapture its identity.
Do not use `$StartingCommit` for any build, migration, deployment, or evidence:

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
$ParticipantRepositoryUrl = '<facilitator-provided-https-url-of-your-repository>'
if ((git remote) -contains 'origin') {
  git remote set-url origin $ParticipantRepositoryUrl
}
else {
  git remote add origin $ParticipantRepositoryUrl
}
git push --set-upstream origin workshop
if ($LASTEXITCODE -ne 0) { throw 'Publishing the workshop branch failed.' }
$SourceCommit = (git rev-parse HEAD).Trim()
if ($SourceCommit -cnotmatch '^[0-9a-f]{40}$') {
  throw 'Final source commit must be an exact lowercase full 40-hex SHA.'
}
```

The first push opens a browser sign-in through Git Credential Manager. Sign in as the
account that owns the repository; the credential is reused by every later push. Re-running
the block is safe — `git remote set-url` replaces an existing `origin` rather than failing.

`$SourceCommit` is now a commit that exists on GitHub. The handoff records it, and
Challenge 3 checks the application source out of your repository at exactly this SHA and
builds `java/Dockerfile` from that checkout. A commit that never left this VM would fail
that checkout, so do not continue until the push succeeds.

Copy the `java-postgresql` object from
`workshop/contracts/runtime-test-evidence.template.json` to
`evidence/runtime-test-report.json` and edit only three fields: `sourceCommit` to
`$SourceCommit`, `artifact` to the preserved Surefire XML under
`evidence/runtime-tests/`, and `command` to the command you ran. The fourteen frozen
test identities are already correct in the template, so do not retype them. Validate
the result against `workshop/contracts/runtime-test-evidence.schema.json`.

This step needs no Azure resources, so you can produce and validate it before you
deploy; a failure here then costs minutes instead of surfacing after a migration.

## 4. Build the immutable container

From the repository root. Build it **in Azure Container Registry** with `az acr build`:
the provisioned VM has no Docker daemon, and `az acr build` uploads the context and
builds inside the registry, so none is needed.

```powershell
$RegistryName = $Target.containerRegistry.resourceId.Split('/')[-1]
$BuildJson = az acr build `
  --registry $RegistryName `
  --image "catalog-java:$SourceCommit" `
  --file java\Dockerfile `
  . --output json
if ($LASTEXITCODE -ne 0) { throw 'ACR build failed' }
```

If `$Target` is not yet loaded in this shell, read it first from
`evidence\azure-target-output.json` as shown in step 5.

Review that the image runs as numeric user `10001`, listens on `8080`, and
externalizes database, Blob, and telemetry configuration. A supported IDE task
may prepare or review containerization, but the accepted artifact is the
digest-pinned `java/Dockerfile` you authored.

The build publishes exactly `catalog-java:$SourceCommit`. Never use `latest` or another
mutable tag.

## 5. Native PostgreSQL and Blob cutover

The extension does not perform database cutover. Run all native commands on this
legacy source VM over the approved private migration path. The bootstrap output must
already exist at `evidence/azure-target-output.json`.

```powershell
$TargetOutput = (Resolve-Path evidence\azure-target-output.json).Path
$Target = Get-Content $TargetOutput -Raw | ConvertFrom-Json
if ($Target.deploymentStage -ne 'bootstrap' -or
    $Target.stack -ne 'java-postgresql' -or
    $Target.images.provider -ne 'azure-blob' -or
    $Target.sourceCommit -cne $SourceCommit) {
  throw 'Wrong bootstrap target for the Java modernization slice.'
}
$DatabaseResourceId = $Target.database.resourceId
$ImageResourceId = $Target.images.resourceId
$Artifact = 'C:\ProgramData\MicroHack\migration\catalog.dump'
New-Item -ItemType Directory -Force (Split-Path $Artifact) | Out-Null

Push-Location tests\acceptance
try {
$ExportExit = 0
try {
  Remove-Item Env:MIGRATION_TARGET_ADMINISTRATOR_PASSWORD `
    -ErrorAction SilentlyContinue
  Remove-Item Env:MIGRATION_TARGET_APPLICATION_PASSWORD `
    -ErrorAction SilentlyContinue
  $env:MIGRATION_SOURCE_DATABASE_PASSWORD = Read-ProtectedValue `
    'Source PostgreSQL database password'
  uv --no-config run catalog-migrate postgresql export `
    --source-host 'localhost' `
    --source-port 5432 `
    --source-database 'catalog' `
    --source-username 'catalog' `
    --source-commit $SourceCommit `
    --target-output $TargetOutput `
    --artifact $Artifact
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
  if ($Target.database.authentication -eq 'password-secret') {
    $env:MIGRATION_TARGET_APPLICATION_PASSWORD = Read-ProtectedValue `
      'Target PostgreSQL application password'
  } else {
    Remove-Item Env:MIGRATION_TARGET_APPLICATION_PASSWORD `
      -ErrorAction SilentlyContinue
  }
  uv --no-config run catalog-migrate postgresql import `
    --artifact $Artifact `
    --source-commit $SourceCommit `
    --target-output $TargetOutput `
    --target-resource-id $DatabaseResourceId `
    --confirm-target-resource-id $DatabaseResourceId `
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
  --source-directory (Resolve-Path ..\..\data\images) `
  --source-commit $SourceCommit `
  --target-output $TargetOutput `
  --target-resource-id $ImageResourceId `
  --confirm-target-resource-id $ImageResourceId `
  --execute
$ImageCopyExit = $LASTEXITCODE
if ($ImageCopyExit -ne 0) { throw 'image copy failed' }

$VerifyExit = 0
try {
  if ($Target.database.authentication -eq 'password-secret') {
    $env:MIGRATION_TARGET_APPLICATION_PASSWORD = Read-ProtectedValue `
      'Target PostgreSQL application password for verification'
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
}
finally {
  Remove-Item Env:MIGRATION_TARGET_APPLICATION_PASSWORD `
    -ErrorAction SilentlyContinue
}
if ($VerifyExit -ne 0) { throw 'migration verification failed' }
}
finally { Pop-Location }
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
`catalog-java@$ImageDigest` first as `baseline`, then as `release` — the two
protected application parameter files already select those roles. Supply the
PostgreSQL administrator secret and any mode-specific application secret only
through protected facilitator inputs.

`infra/main.bicep` is resource-group scoped. Deploy it with `az deployment group create`
into the resource group you already own — the one the facilitator created before the
workshop, holding your two legacy VMs. The template does not create a resource group and
nothing on this path deploys at subscription scope, which is what keeps your rights to
Owner on that one group. Take the `--resource-group` value from the `resourceGroupName`
already carried by the protected parameters file, rather than typing a name twice:

```powershell
$ResourceGroup = (Get-Content 'C:\protected\copilot-modernization-java-bootstrap.json' -Raw |
  ConvertFrom-Json).parameters.resourceGroupName.value
if ($ResourceGroup -cnotmatch '^rg-user[0-9]{3}$') {
  throw 'the protected parameters must name your participant resource group'
}
```

Those `C:\protected\*.json` documents are not yours to write. The facilitator's
provisioning wrote `copilot-modernization-java-bootstrap.json`,
`copilot-modernization-java-baseline.json`, and
`copilot-modernization-java-release.json` on this VM before the workshop started, one
per deployment stage. Each is a standard ARM parameter document carrying the values only
the facilitator knew then: your `resourceGroupName` and `teamName`, the exact
`migrationSourceVmResourceId` and `migrationSourceVirtualNetworkResourceId`,
`facilitatorPrincipalName` and `facilitatorPrincipalObjectId`, and the `performanceApiKey`
the application stage asserts on.

Every protected parameter document must set `resourceGroupName` to your own resource
group. `infra/main.bicep` asserts that `resourceGroupName` equals the group it is deployed
into, so a file naming anywhere else is refused before a single resource is touched.

`sourceCommit` and `imageDigest` are deliberately absent from all three files: neither
value existed when they were written, and a placeholder that satisfied the template's
format assert would silently deploy the wrong source. Both deployments below pass them
explicitly, where a later `--parameters` overrides the file.

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

Deploy baseline first, then release. Both carry the same immutable digest; only the
protected file, the deployment name, and therefore the revision role differ:

```powershell
az deployment group create `
  --name "copilot-modernization-java-baseline-$($SourceCommit.Substring(0, 12))" `
  --resource-group $ResourceGroup `
  --template-file infra\main.bicep `
  --parameters '@C:\protected\copilot-modernization-java-baseline.json' `
  --parameters sourceCommit=$SourceCommit imageDigest=$ImageDigest `
  --output none
if ($LASTEXITCODE -ne 0) { throw 'baseline deployment failed' }

$ReleaseLines = az deployment group create `
  --name "copilot-modernization-java-release-$($SourceCommit.Substring(0, 12))" `
  --resource-group $ResourceGroup `
  --template-file infra\main.bicep `
  --parameters '@C:\protected\copilot-modernization-java-release.json' `
  --parameters sourceCommit=$SourceCommit imageDigest=$ImageDigest `
  --query properties.outputs.targetOutput.value `
  --output json
if ($LASTEXITCODE -ne 0) { throw 'release deployment failed' }
[System.IO.File]::WriteAllText(
  (Join-Path $PWD 'evidence\azure-target-output.json'),
  ($ReleaseLines -join [Environment]::NewLine),
  [System.Text.UTF8Encoding]::new($false)
)
```

That write replaces the bootstrap document at `evidence/azure-target-output.json` with the
release-role application-stage output. Verify it, and the retained rollback, with the
frozen query:

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
$AcceptanceReport = Join-Path (Get-Location) `
  'evidence\acceptance-report.json'
if (Test-Path -LiteralPath $AcceptanceReport) {
  Remove-Item -LiteralPath $AcceptanceReport -Force -ErrorAction Stop
}
if (Test-Path -LiteralPath $AcceptanceReport) {
  throw 'stale acceptance report could not be removed'
}

Push-Location tests\acceptance
try {
$env:CATALOG_DATABASE_KIND = 'postgresql'
$env:CATALOG_DATABASE_HOST = $ReleaseTarget.database.server
$env:CATALOG_DATABASE_NAME = $ReleaseTarget.database.database
$env:CATALOG_DATABASE_USERNAME = $ReleaseTarget.database.applicationPrincipal.name
$env:CATALOG_DATABASE_SSL_MODE = 'require'
$env:CATALOG_DATABASE_TARGET = 'managed'
$AcceptanceExit = 0
try {
  $env:CATALOG_DATABASE_PASSWORD = Read-ProtectedValue `
    'Acceptance verifier database password'
  $env:PERFTEST_API_KEY = Read-ProtectedValue 'Runtime performance API key'
  uv --no-config run python -m catalog_acceptance `
    --profile full `
    --base-url $ReleaseTarget.application.url `
    --source-commit $SourceCommit `
    --image-digest $ImageDigest `
    --revision-name $ReleaseRevision `
    --output $AcceptanceReport
  $AcceptanceExit = $LASTEXITCODE
}
finally {
  Remove-Item Env:PERFTEST_API_KEY -ErrorAction SilentlyContinue
  Remove-Item Env:CATALOG_DATABASE_PASSWORD -ErrorAction SilentlyContinue
}
if ($AcceptanceExit -ne 0) { throw 'full acceptance failed' }
}
finally { Pop-Location }
```

**Do not hand-author the telemetry files.** Record what you observed into a capture
manifest and let the renderer normalize it:

```powershell
uv run python -m catalog_acceptance.telemetry_evidence_cli `
  --capture evidence/telemetry-capture.json `
  --output evidence/telemetry-report.json
```

The capture manifest holds `workspaceId`, `capturedAt`, `service`
(`mh-catalog-java`), `resourceAttributes`, and one entry per query
(`resources`, `traces`, `metrics`, `logs`) carrying the `query` text and, per signal,
its `recordCount`, `observedAttributes`, and `measurements` or `observations`. The
renderer supplies each metric `unit` from the behavior contract, stamps provenance into
every result file, writes all four `evidence/telemetry/*.json` plus the report, and
**reports every unmet requirement at once** instead of one per handoff attempt. It will
not invent a signal you did not capture.

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

Render and validate handoff `1.4.0`:

```powershell
Push-Location tests\acceptance
try {
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
if ($LASTEXITCODE -ne 0) { throw 'handoff rendering failed' }

uv --no-config run python -m catalog_acceptance.handoff_cli `
  ..\..\evidence\modernization-contract.json `
  --contracts ..\..\workshop\contracts `
  --repository-root ..\..
if ($LASTEXITCODE -ne 0) { throw 'handoff validation failed' }
}
finally { Pop-Location }
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

The handoff itself is not yet on GitHub. Challenge 3 reads
`evidence/modernization-contract.json` from the commit it dispatches, and that commit must
be a **later** commit than the source commit it builds. Publish the validated evidence as
one follow-up commit, after the transients above are gone so nothing transient ships:

```powershell
git add --all
git commit -m 'Record the validated modernization handoff'
if (git status --porcelain) {
  throw 'The handoff evidence must be committed before Challenge 3 runs.'
}
git push origin workshop
if ($LASTEXITCODE -ne 0) { throw 'Publishing the handoff evidence failed.' }
if ((git rev-parse HEAD).Trim() -ceq $SourceCommit) {
  throw 'The handoff commit must be later than the published source commit.'
}
```

Challenge 3 dispatches its workflow from this evidence commit, reads the handoff there,
and checks the application source out separately at `$SourceCommit`.

Retain the required evidence, reviewed source delta, and frozen target assets.
Rejoin only after handoff validation succeeds. Downstream challenges consume
`evidence/modernization-contract.json`; assessment, plan, and task output do not
prove runtime behavior.

## Optional appendix

The preview Modernize CLI is optional and not required. It cannot replace the
signed IDE workflow, native Maven tests, `catalog-migrate`, full acceptance,
telemetry evidence, or handoff validation.

## If a command will not run here

| Symptom | Cause | What to do |
| --- | --- | --- |
| `git` is not recognized | Git for Windows is pinned and installed at `C:\Program Files\Git\cmd\git.exe`, but a shell opened before provisioning finished does not have it on `PATH`. | Open a new terminal and `cd C:\MicroHack\source` again, or call the full path once to confirm the install. |
| `git rev-parse HEAD` does not match `.source-commit` | Expected. The working tree is a local repository initialized over the extracted archive, so its commits are unrelated to the published upstream commit. | Use `git rev-parse HEAD` for the commit holding your work, which is what every build, deployment, and evidence file here is keyed to. Use `.source-commit` only when a step asks for upstream archive provenance. |
| `docker` is not recognized | The provisioned VM has no Docker daemon. | Step 4 already uses `az acr build`, which needs none. If any generated task proposes a local `docker build`, reject it and replan — that is exactly the kind of preflight mismatch step 3 asks you to record. |

---

**Challenge:** [Path 1C: GitHub Copilot modernization](../../../challenges/ch01-copilot-modernization/README.md) ·
**Other stack:** [Copilot modernization .NET](../dotnet/README.md) ·
**Modernized target:** [Reference implementation](../../reference/README.md) ·
**Next:** [Challenge 2: load and autoscaling](../../../challenges/ch02/README.md)
