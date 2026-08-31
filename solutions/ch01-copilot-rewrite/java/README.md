# Java/PostgreSQL bounded Copilot rewrite reference

**Open this if** you chose [Path 1B: bounded rewrite with GitHub Copilot](../../../challenges/ch01-copilot-rewrite/README.md)
with the Java/PostgreSQL baseline and want the executable form of a checkpoint, a worked
prompt, or a way back after a rejected slice. The full path runs 8–12 hours; this
document does not shorten it, it removes the guesswork.

This is a runnable reference slice, not a complete rewrite to copy and paste. Work
from the repository root unless a command changes directory. Replace angle-bracket
values from the participant environment; never commit those values or shell history
containing secrets.

## Where you work, and what the VM does not have

Every Azure and migration command here runs on the selected VM from Challenge 0, reached
over RDP at its public IP address. The source tree is at `C:\MicroHack\source`, extracted from a
verified archive by the provisioner. **That directory is what "the repository root" means
in this and every other workshop document.** Start each terminal with
`cd C:\MicroHack\source`.

The VM ships a deliberately small, fully pinned toolchain. Git is part of it; a Docker
daemon is not:

| You need | On the VM |
| --- | --- |
| a per-slice commit | Pinned Git for Windows is installed, and `C:\MicroHack\source` is a working tree holding one baseline commit. `git add`, `git commit`, `git status --porcelain`, and `git rev-parse HEAD` all work. |
| the commit identifying *your* rewrite | `git rev-parse HEAD`, after committing the slice. This is what the image tag, revisions, and handoff use. |
| the upstream archive provenance | the marker file `C:\MicroHack\source\.source-commit`. This is a *different* SHA from the one above: the source arrives as a verified archive, so its local baseline commit is unrelated to the upstream commit that marker names. GitHub has never seen that commit, so never substitute one for the other. |
| to publish your rewrite | `git push` to your own GitHub repository, exactly as section 4 writes it |
| a container image build | `az acr build` uploads the build context and builds inside Azure Container Registry, so no local daemon is required |

Because the build happens in the registry, section 4 checks the Dockerfile you authored
and section 5 builds it — after bootstrap has created the registry to build it in.

## Registered boundary

This document is organized in six sections; the challenge is organized in eight
checkpoints. They are not the same numbering, and both documents cross-reference in their
own. Use this map:

| Challenge checkpoint | This runbook |
| --- | --- |
| 1 characterization | §1 |
| 2 bounded plan | §2 |
| 3 diff review | §3 |
| 4 container | §4 (Dockerfile guards) |
| 5 publish | §4 (commit, push, `$SourceCommit`) |
| 6 migration | §5 (Windows source-VM migration) |
| 7 release | §5 (bootstrap, `az acr build`, cutover) |
| 8 handoff | §6 |

`copilot-rewrite-java` resolves to:

| Interface | Exact value |
| --- | --- |
| Source | `java/` |
| Dockerfile | `java/Dockerfile` |
| Database family | `postgresql-flexible` |
| Image provider | `azure-blob` |
| Tools | `github.copilot`, `github.copilot-chat` |
| Infrastructure | `infra/main.bicep` |
| Migration | `catalog-migrate` |

The pinned tools are `github.copilot@1.388.0` and
`github.copilot-chat@0.48.1`. Do not install or invoke any modernization or
migration extension for this path.

## 1. Preflight and characterization checkpoint

**Executable proof (bash — the VM's shell is PowerShell; see [If a command will not run here](#if-a-command-will-not-run-here))**

```bash
set -euo pipefail
test "$(git rev-parse --show-toplevel)" = "$PWD"
test -z "$(git status --porcelain)"
installed_extensions="$(code --list-extensions --show-versions)"
grep -Fxq 'github.copilot@1.388.0' <<<"$installed_extensions"
grep -Fxq 'github.copilot-chat@0.48.1' <<<"$installed_extensions"
mkdir -p evidence .workshop-tmp
./java/mvnw -f java/pom.xml test
cp -R java/target/surefire-reports .workshop-tmp/java-characterization
cd tests/acceptance
uv --no-config run pytest -q tests/test_contract_assets.py \
  --deselect tests/test_contract_assets.py::test_reference_tree_differs_from_legacy_only_where_the_workshop_teaches
cd ../..
```

The deselected test is a repository-authoring guard, not a participant gate. It asserts that
`java/` and `solutions/reference/java/` differ only in the nine files the *modernization*
path edits, and that the only files the reference adds are its declared additions —
`Dockerfile` among them. Both assertions are incompatible with this path by construction: a
bounded rewrite edits files outside that set, and checkpoint 4 has you author
`java/Dockerfile`, which removes it from the reference's declared additions. Deselect it here
and keep running everything else, which is what actually characterizes your application.

Start the unchanged application and disposable PostgreSQL using `java/README.md`,
then run full shared acceptance against that baseline. Record the exact application
command, database target, Surefire result, acceptance report, and known failures in
`evidence/characterization.md`. The characterization and acceptance suites are the
behavioral oracle.

**Expected checkpoint**

- native tests and contract assets pass;
- the baseline routes, PostgreSQL schema, import transaction, image keys, degraded
  states, configuration, errors, and telemetry are documented;
- no implementation file has changed.

## 2. Human-reviewed bounded plan

Write `evidence/bounded-plan.md` before asking for code. A suitable sequence is:

1. domain identity, text validation, Flyway ownership, and PostgreSQL schema;
2. transactional import and query behavior;
3. local/Blob image abstraction and image-key security;
4. external configuration, managed identity, health, readiness, and bounded
   performance;
5. telemetry, then the non-root container image you author in checkpoint 4.

For every slice, list exact files, tests, exclusions, and how to return to the last
passing commit. A human must approve the plan and must review schema, security,
dependencies, configuration, errors, and each generated diff.

**Suggested prompt, not proof**

> Read `workshop/contracts`, `tests/acceptance`, the current Java tests, and — once
> checkpoint 4 has authored it — `java/Dockerfile`. The baseline ships no Dockerfile,
> so omit it on the earlier slices. Propose only the next bounded slice. Preserve PostgreSQL
> Flexible Server, one application container, Blob images, ACA readiness, external
> configuration, routes, failure behavior, and telemetry. Do not edit frozen
> interfaces or add services. Name exact tests and wait for approval before
> generating a diff.

## 3. Slice loop

Ask for and accept one generated diff at a time.

**Suggested prompt, not proof**

> Implement only approved slice `<slice-name>`. Keep changes inside the listed Java
> files. Add or update focused tests for the characterized behavior. Do not change
> database family, infrastructure, migration, deployment topology, or unrelated
> dependencies. Surface configuration and errors explicitly.

**Executable proof after every generated diff (bash — the VM's shell is PowerShell; see [If a command will not run here](#if-a-command-will-not-run-here))**

```bash
set -euo pipefail
: "${SLICE_NAME:?Name the slice you just approved, e.g. SLICE_NAME=pricing-rules}"
: "${CATALOG_BASE_URL:?Set the modernized catalog base URL, e.g. CATALOG_BASE_URL=http://localhost:8080}"
: "${PERFTEST_API_KEY:?Set the facilitator-supplied performance API key; do not echo it or commit it}"
git diff -- java
./java/mvnw -f java/pom.xml test
rm -rf .workshop-tmp/java-$SLICE_NAME
mkdir -p .workshop-tmp/java-$SLICE_NAME
cp -R java/target/surefire-reports .workshop-tmp/java-$SLICE_NAME/
cd tests/acceptance
uv --no-config run pytest -q tests/test_contract_assets.py \
  --deselect tests/test_contract_assets.py::test_reference_tree_differs_from_legacy_only_where_the_workshop_teaches
uv --no-config run python -m catalog_acceptance \
  --profile smoke \
  --base-url "$CATALOG_BASE_URL" \
  --performance-api-key "$PERFTEST_API_KEY" \
  --output "../../.workshop-tmp/java-$SLICE_NAME-acceptance.json"
cd ../..
git diff --check
git add -- java
git diff --cached --check
git commit -m "Complete bounded Java rewrite slice $SLICE_NAME"
```

Record the human decision and command result in
`evidence/review-checklist.md`. The application must be running for the shared live
smoke profile. Run the full profile instead when a slice changes schema, persistence,
import, or database failure behavior. Static contract tests and documentation
vocabulary never substitute for live behavior. Reject the diff rather than patching
around a contract failure, and do not call a slice accepted until its passing diff is
committed.

**Stop and replan** if a slice changes Flyway-owned schema without explicit review,
weakens canonical image-key checks, adds credentials to source, adds a broad catch,
changes one-container topology, requires a frozen-interface edit, introduces an
unreviewed dependency, or fails characterization/acceptance. Return to the last
passing slice, update `bounded-plan.md`, and obtain approval again.

## 4. Committed source and container checkpoint

Every accepted rewrite slice must already be committed. Fail before deriving source
identity if tracked, staged, or untracked implementation bytes remain. The lowercase
full 40-hex commit produced here is the single identity used by the image tag,
Container Apps revisions, migration report, runtime evidence, and handoff.

**Executable proof (PowerShell)**

```powershell
$DockerfilePath = 'java\Dockerfile'
if (-not (Test-Path $DockerfilePath)) {
    throw 'Author java/Dockerfile before the container checkpoint.'
}
$Dockerfile = Get-Content -Path $DockerfilePath -Raw
if ($Dockerfile -notmatch '(?m)^\s*USER\s+(?!root\s*$)\S+') {
    throw 'The runtime stage must declare a non-root USER.'
}
if ($Dockerfile -notmatch '(?m)^\s*EXPOSE\s+8080\s*$') {
    throw 'The runtime stage must expose 8080.'
}

$Dirty = git status --porcelain -- java data
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not [string]::IsNullOrWhiteSpace(($Dirty -join "`n"))) {
    throw 'Commit every accepted slice and clean the implementation tree first.'
}

if (git status --porcelain) {
    git add --all
    git commit -m 'Commit the rewritten catalog and its review evidence'
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

$SourceCommitLines = git rev-parse HEAD
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$SourceCommit = ($SourceCommitLines -join '').Trim()
if ($SourceCommit -cnotmatch '^[0-9a-f]{40}$') {
    throw 'SOURCE_COMMIT must be a lowercase full 40-hex commit.'
}
```

The Dockerfile guards run first on purpose. `$SourceCommit` is the commit Challenge 3 checks
out and builds `java/Dockerfile` from, so a commit published without it is unusable: you
would have to author the file, commit, push, and re-derive `$SourceCommit` before any command
that consumes it. Failing before the push costs nothing; failing after it costs the whole
publish.

The first push opens a browser sign-in through Git Credential Manager. Sign in as the
account that owns the repository; the credential is reused by every later push. Re-running
the block is safe — `git remote set-url` replaces an existing `origin` rather than failing.
The dirty check above already refuses uncommitted implementation bytes, so the conditional
commit only ever picks up review evidence written in the previous sections.

`$SourceCommit` is therefore a commit that exists on GitHub. The handoff records it, and
Challenge 3 checks the application source out of your repository at exactly this SHA and
builds `java/Dockerfile` from that checkout. A commit that never left this VM would fail
that checkout, so do not continue until the push succeeds.

The image itself is built in section 5, once bootstrap has created the registry to
build it in. Deferring the build is what lets this path run on the provisioned VM,
which has no Docker daemon: `az acr build` uploads this context and builds it inside
Azure Container Registry. The two guards above are the daemon-free equivalent of
inspecting the built image's user and exposed port, and they fail here — before any
Azure resource exists — rather than after a five-minute remote build.

## 5. Shared-target bootstrap, native migration, and ordered cutover

Use protected parameter documents outside the repository. They supply every required
value from `infra/main.bicep`, including secure values, source VM/VNet resource IDs,
facilitator identity, and the fixed `java-postgresql`/`azure-blob` selection. Prefer
managed-identity application authentication; if the approved scenario selects
`password-secret`, keep the application password only in protected parameters and
the exact migration environment variable. The following participant commands are
PowerShell-native; this reference does not claim they were run.

You do not write those documents. The facilitator's provisioning wrote them on this VM
before the workshop started, as `C:\protected\copilot-rewrite-java-bootstrap.json`,
`...-baseline.json`, and `...-release.json` — one per deployment stage. They carry the
only values that were knowable then: your `resourceGroupName` and `teamName`, the exact
`migrationSourceVmResourceId` and `migrationSourceVirtualNetworkResourceId`,
`facilitatorPrincipalName` and `facilitatorPrincipalObjectId`, and the
`performanceApiKey` the application stage asserts on. `sourceCommit` and `imageDigest`
are deliberately absent, because neither exists until you publish and build; every
deployment below passes them explicitly, and a later `--parameters` overrides the file.

Every one of those documents must set `resourceGroupName` to your own resource group.
`infra/main.bicep` asserts that `resourceGroupName` equals the group it is deployed into,
so a file naming anywhere else is refused before a single resource is touched.

### Bootstrap and immutable ACR publication

Run bootstrap from the committed repository root with the isolated facilitator
profile. Every state-changing command has an immediate exit guard. `$ResourceGroup` comes
from the protected bootstrap parameters, which already carry `resourceGroupName`. You
deploy into the resource group you already own — the one the facilitator created before
the workshop, holding your two legacy VMs. `infra/main.bicep` is resource-group scoped,
does not create a resource group, and asserts that its `resourceGroupName` matches the
group it is deployed into. Nothing on this path deploys at subscription scope, which is
what keeps your rights to Owner on that one group.

```powershell
$env:AZURE_CONFIG_DIR = Join-Path $HOME '.azure-365'
$ResourceGroup = (Get-Content 'C:\protected\copilot-rewrite-java-bootstrap.json' -Raw |
  ConvertFrom-Json).parameters.resourceGroupName.value
if ($ResourceGroup -cnotmatch '^rg-user[0-9]{3}$') {
  throw 'the protected parameters must name your participant resource group'
}
New-Item -ItemType Directory -Force evidence | Out-Null
$BootstrapLines = az deployment group create `
  --name "ch01-java-bootstrap-$($SourceCommit.Substring(0, 12))" `
  --resource-group $ResourceGroup `
  --template-file infra/main.bicep `
  --parameters "@C:\protected\copilot-rewrite-java-bootstrap.json" `
  --parameters deploymentStage=bootstrap stack=java-postgresql `
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

$PublishedTag = "$LoginServer/catalog-java:$SourceCommit"
az acr build `
  --registry $RegistryName `
  --subscription $SubscriptionId `
  --image "catalog-java:$SourceCommit" `
  --file java\Dockerfile `
  --platform linux/amd64 `
  .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$ImageDigestLines = az acr manifest show-metadata `
  --registry $RegistryName `
  --name "catalog-java:$SourceCommit" `
  --subscription $SubscriptionId `
  --query digest `
  --output tsv
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$ImageDigest = ($ImageDigestLines -join '').Trim()
if ($ImageDigest -cnotmatch '^sha256:[0-9a-f]{64}$') {
    throw 'ACR did not return an immutable sha256 manifest digest.'
}
$ImageReference = "$LoginServer/catalog-java@$ImageDigest"
```

The commit tag locates registry evidence only. Application deployments receive
`ImageDigest` and therefore resolve to `ImageReference`; never deploy `latest`, the
commit tag, or another mutable reference.

### Windows source-VM migration

On the exact Windows legacy source VM declared in
`target-output.network.migrationSourceVmResourceId`, first verify the checkout and
derive source identity. Only after that clean check, confirm the bootstrap target output
your step-5 deployment wrote to `evidence\azure-target-output.json` is still present. Run all native
transfer there, not from Linux, macOS, Cloud Shell, or the application. Supply
each password only through the protected prompt immediately before the command that
permits it. Managed-identity mode forbids
`MIGRATION_TARGET_APPLICATION_PASSWORD`; password-secret mode requires that value for
import and verification but clears it between those commands.

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

$Dirty = git status --porcelain -- java data
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
$DatabaseArtifact = 'C:\ProgramData\MicroHack\migration\catalog.dump'
New-Item -ItemType Directory -Force (Join-Path $RepositoryRoot 'evidence') | Out-Null
New-Item -ItemType Directory -Force (Split-Path $DatabaseArtifact) | Out-Null
if (-not (Test-Path -LiteralPath $TargetOutput)) {
  throw "The bootstrap deployment output is missing. Re-run step 5 before migrating."
}
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
    'Source PostgreSQL database password'
  uv --no-config run catalog-migrate postgresql export `
    --source-host $env:CATALOG_DATABASE_HOST `
    --source-port 5432 `
    --source-database $env:CATALOG_DATABASE_NAME `
    --source-username $env:CATALOG_DATABASE_USERNAME `
    --source-commit $SourceCommit `
    --target-output $TargetOutput `
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
  if ($Target.database.authentication -eq 'password-secret') {
    $env:MIGRATION_TARGET_APPLICATION_PASSWORD = Read-ProtectedValue `
      'Target PostgreSQL application password'
  }
  elseif ($Target.database.authentication -ne 'managed-identity') {
    throw 'Unsupported PostgreSQL target authentication mode.'
  }
  uv --no-config run catalog-migrate postgresql import `
    --artifact $DatabaseArtifact `
    --source-commit $SourceCommit `
    --target-output $TargetOutput `
    --target-resource-id $TargetDatabaseResourceId `
    --confirm-target-resource-id $TargetDatabaseResourceId `
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
  --source-directory $ImageDirectory `
  --source-commit $SourceCommit `
  --target-output $TargetOutput `
  --target-resource-id $TargetImageResourceId `
  --confirm-target-resource-id $TargetImageResourceId `
  --execute
if ($LASTEXITCODE -ne 0) { throw 'image copy failed' }

$VerifyExit = 0
try {
  if ($Target.database.authentication -eq 'password-secret') {
    $env:MIGRATION_TARGET_APPLICATION_PASSWORD = Read-ProtectedValue `
      'Target PostgreSQL application password for verification'
  }
  uv --no-config run catalog-migrate verify `
    --stack java-postgresql `
    --source-commit $SourceCommit `
    --database-artifact $DatabaseArtifact `
    --target-output $TargetOutput `
    --output $MigrationReport
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

The CLI is the only data-transfer path. It must refuse a nonempty target, verify Blob
bytes and PostgreSQL contents, bind the workload principal from target output, and
leave the source and artifact available for rollback.

### Baseline then release

Return the verified migration evidence to the facilitator checkout. Deploy baseline
first and release second with the same digest. The release deployment output replaces
the bootstrap document before handoff. The retained baseline is verified only after
release has made it inactive.

```powershell
az deployment group create `
  --name "ch01-java-baseline-$($SourceCommit.Substring(0, 12))" `
  --resource-group $ResourceGroup `
  --template-file infra/main.bicep `
  --parameters "@C:\protected\copilot-rewrite-java-baseline.json" `
  --parameters deploymentStage=application applicationRevisionRole=baseline `
    stack=java-postgresql imageProvider=azure-blob `
    sourceCommit=$SourceCommit imageDigest=$ImageDigest `
  --output none
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$ReleaseLines = az deployment group create `
  --name "ch01-java-release-$($SourceCommit.Substring(0, 12))" `
  --resource-group $ResourceGroup `
  --template-file infra/main.bicep `
  --parameters "@C:\protected\copilot-rewrite-java-release.json" `
  --parameters deploymentStage=application applicationRevisionRole=release `
    stack=java-postgresql imageProvider=azure-blob `
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

Run the native suite after the final diff and retain the native Surefire JUnit XML
under `evidence/`. Create `evidence/runtime-test-report.json` by copying the
`java-postgresql` object from
`workshop/contracts/runtime-test-evidence.template.json` and editing only
`sourceCommit`, `artifact`, and `command`; the fourteen real test identities are
already correct in the template, so do not retype them. A bounded rewrite that
preserves test display names and class or method identities satisfies the frozen
mapping unchanged. Validate against
`workshop/contracts/runtime-test-evidence.schema.json`. Run full shared
acceptance against the release and write
`evidence/acceptance-report.json`. Collect real trace, metric, log, and resource
query results into `evidence/telemetry-report.json`; never synthesize telemetry.

**Do not hand-author the telemetry files.** Record what you observed into a capture
manifest and let the renderer normalize it:

```powershell
uv run python -m catalog_acceptance.telemetry_evidence_cli `
  --capture evidence/telemetry-capture.json `
  --output evidence/telemetry-report.json
```

The manifest's shape is checked against
`workshop/contracts/telemetry-evidence-capture.schema.json`, and a complete worked
manifest ships as `telemetry-evidence-capture.example.json` — copy it and replace the
observations with your own.

The capture manifest holds `workspaceId`, `capturedAt`, `service`
(`mh-catalog-java`), `resourceAttributes`, and one entry per query
(`resources`, `traces`, `metrics`, `logs`) carrying the `query` text and, per signal,
its `recordCount`, `observedAttributes`, and `measurements` or `observations`. The
renderer supplies each metric `unit` from the behavior contract, stamps provenance into
every result file, writes all four `evidence/telemetry/*.json` plus the report, and
**reports every unmet requirement at once** instead of one per handoff attempt. It will
not invent a signal you did not capture.

Complete:

- `evidence/decision-log.md` with accepted/rejected design choices and an explicit
  `## Architecture delta` section listing changed boundaries and confirming
  PostgreSQL Flexible Server, one application container, Blob images, ACA readiness,
  external configuration, native `catalog-migrate`, and shared-target Bicep remain
  preserved;
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
validate, the handoff reports path `copilot-rewrite`, database family
`postgresql-flexible`, Blob verification, one digest-pinned image, and a distinct
retained rollback revision.

## Cleanup and rejoin

Remove only local transient artifacts after evidence has been copied (bash):

```bash
rm -rf .workshop-tmp
git status --short
```

The handoff itself is not yet on GitHub. Challenge 3 reads
`evidence/modernization-contract.json` from the commit it dispatches, and that commit must
be a **later** commit than the source commit it builds. Publish the validated evidence as
one follow-up commit, after the transient directory is gone so nothing transient ships:

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

Do not remove `evidence/`, migration artifacts, or the retained baseline revision.
Rejoin the shared workshop at the next challenge only after handoff validation passes
and a human signs `review-checklist.md`, `decision-log.md`, and the rollback runbook.

## If a command will not run here

| Symptom | Cause | What to do |
| --- | --- | --- |
| `git rev-parse HEAD` returns a SHA that is not the upstream archive commit | Expected. The source arrives as a verified archive, not a clone, so provisioning seeds `C:\MicroHack\source` with its own baseline commit. | That is correct and intended: `git rev-parse HEAD` identifies *your* rewrite, is the commit section 4 pushes to your GitHub repository, and is what the image tag, revisions, and handoff bind to. Upstream archive provenance is `C:\MicroHack\source\.source-commit`. Never substitute one for the other. |
| `docker` is not recognized | The provisioned VM has no Docker daemon. | Build with `az acr build --registry <acr> --image "<repo>:$SourceCommit" --file <stack>\Dockerfile . ` — it uploads the context, builds in the registry, and publishes the tag in one step. Resolve the digest afterwards with `az acr manifest show-metadata`, exactly as the cutover section already does. |
| `set -euo pipefail` fails | The executable-proof blocks are bash; PowerShell is the VM's shell. | Translate them one line at a time. The guards they express — fail fast, clean tree, pinned extensions — still apply. |

---

**Challenge:** [Path 1B: bounded rewrite with GitHub Copilot](../../../challenges/ch01-copilot-rewrite/README.md) ·
**Other stack:** [Copilot rewrite .NET](../dotnet/README.md) ·
**Modernized target:** [Reference implementation](../../reference/README.md) ·
**Next:** [Challenge 2: load and autoscaling](../../../challenges/ch02/README.md)
