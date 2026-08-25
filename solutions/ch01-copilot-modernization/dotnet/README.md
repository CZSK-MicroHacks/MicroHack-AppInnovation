# Path 1C solution: .NET and SQL Server

**Open this if** you chose [Path 1C: GitHub Copilot modernization](../../../challenges/ch01-copilot-modernization/README.md)
with the .NET/SQL Server baseline and want the exact command for a step, the precise
ordering of commit → clean-tree check → source-commit recapture, or a way to finish when
time runs short. End to end this is a 5–7 hour path.

Run this guide on the selected .NET legacy VM from the repository root. The source
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
dotnet test dotnet\LegoCatalog.sln `
  --logger "trx;LogFileName=dotnet-modernization.trx" `
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

After all modernization tasks are accepted, commit the complete reviewed delta,
publish it to your own GitHub repository, and recapture its identity.
Do not use `$StartingCommit` for any build, migration, deployment, or evidence:

```powershell
git add -- dotnet evidence\assessment.md evidence\modernization-plan.md `
  evidence\task-results.json evidence\build-test-cve-summary.md `
  evidence\ide-extensions.txt
git add --force -- evidence\dotnet-modernization.trx
git commit -m 'Accept .NET Copilot modernization tasks'
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

`evidence\dotnet-modernization.trx` is forced because the repository ignores `*.trx`, and
Challenge 3 has to be able to read the run it reports on.

The first push opens a browser sign-in through Git Credential Manager. Sign in as the
account that owns the repository; the credential is reused by every later push. Re-running
the block is safe — `git remote set-url` replaces an existing `origin` rather than failing.

`$SourceCommit` is now a commit that exists on GitHub. The handoff records it, and
Challenge 3 checks the application source out of your repository at exactly this SHA and
builds `dotnet/Dockerfile` from that checkout. A commit that never left this VM would fail
that checkout, so do not continue until the push succeeds.

Create `evidence/runtime-test-report.json` for the native TRX by following
`workshop/contracts/runtime-test-evidence.schema.json`. It must reference the
TRX containing all fourteen exact frozen test identities and bind
`sourceCommit` to `$SourceCommit`.

## 4. Build the immutable container

Use the Dockerfile you authored at the repository root. Build it **in Azure Container
Registry** with `az acr build`: the provisioned VM has no Docker daemon, and `az acr
build` uploads the context and builds inside the registry, so none is needed.

```powershell
$RegistryName = $Target.containerRegistry.resourceId.Split('/')[-1]
$BuildJson = az acr build `
  --registry $RegistryName `
  --image "catalog-dotnet:$SourceCommit" `
  --file dotnet\Dockerfile `
  . --output json
if ($LASTEXITCODE -ne 0) { throw 'ACR build failed' }
```

If `$Target` is not yet loaded in this shell, read it first from
`evidence\azure-target-output.json` as shown in step 5.

Review that the image is non-root, listens on `8080`, and takes database,
Blob, and telemetry configuration from the environment. A supported IDE
containerization task may prepare or review these changes, but
`dotnet/Dockerfile` and its locked digests are the accepted artifact.

The build publishes exactly `catalog-dotnet:$SourceCommit`. Never use `latest`. Do not
continue until the registry returns an immutable digest.

## 5. Native SQL and Blob cutover

The extension does not perform database cutover. Run the frozen migration CLI
on this legacy source VM over the approved private migration path. The bootstrap
output must already exist at `evidence/azure-target-output.json`.

```powershell
$TargetOutput = (Resolve-Path evidence\azure-target-output.json).Path
$Target = Get-Content $TargetOutput -Raw | ConvertFrom-Json
if ($Target.deploymentStage -ne 'bootstrap' -or
    $Target.stack -ne 'dotnet-sqlserver' -or
    $Target.images.provider -ne 'azure-blob' -or
    $Target.sourceCommit -cne $SourceCommit) {
  throw 'Wrong bootstrap target for the .NET modernization slice.'
}
$DatabaseResourceId = $Target.database.resourceId
$ImageResourceId = $Target.images.resourceId
$Artifact = 'C:\ProgramData\MicroHack\migration\catalog.bacpac'
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
    'Source SQL Server database password'
  uv --no-config run catalog-migrate sql export `
    --source-server '.\SQLEXPRESS' `
    --source-database 'LegoCatalog' `
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
if ($ExportExit -ne 0) { throw 'SQL export failed' }

uv --no-config run catalog-migrate sql import `
  --artifact $Artifact `
  --source-commit $SourceCommit `
  --target-output $TargetOutput `
  --target-resource-id $DatabaseResourceId `
  --confirm-target-resource-id $DatabaseResourceId `
  --execute
$ImportExit = $LASTEXITCODE
if ($ImportExit -ne 0) { throw 'SQL import failed' }

uv --no-config run catalog-migrate images copy `
  --source-directory (Resolve-Path ..\..\data\images) `
  --source-commit $SourceCommit `
  --target-output $TargetOutput `
  --target-resource-id $ImageResourceId `
  --confirm-target-resource-id $ImageResourceId `
  --execute
$ImageCopyExit = $LASTEXITCODE
if ($ImageCopyExit -ne 0) { throw 'image copy failed' }

uv --no-config run catalog-migrate verify `
  --stack dotnet-sqlserver `
  --source-commit $SourceCommit `
  --database-artifact $Artifact `
  --target-output $TargetOutput `
  --output (Join-Path (Resolve-Path ..\..).Path 'evidence\migration-report.json')
$VerifyExit = $LASTEXITCODE
if ($VerifyExit -ne 0) { throw 'migration verification failed' }
}
finally { Pop-Location }
```

Do not claim the extension exported, imported, verified, or cut over the
database. `catalog-migrate sql import` removes the imported legacy
`catalog`/`db_owner` principal before the managed application principal is
created and verification requires it to remain absent.

## 6. Deploy baseline and release

Use only reviewed `infra/main.bicep` application-stage deployments. Deploy the
same `catalog-dotnet@$ImageDigest` first with
`applicationRevisionRole=baseline`, then with
`applicationRevisionRole=release` — the two protected application parameter
files already select those roles. Supply secrets through protected
facilitator inputs, never command literals or tracked parameter files.

`infra/main.bicep` is resource-group scoped. Deploy it with `az deployment group create`
into the resource group you already own — the one the facilitator created before the
workshop, holding your two legacy VMs. The template does not create a resource group and
nothing on this path deploys at subscription scope, which is what keeps your rights to
Owner on that one group. Take the `--resource-group` value from the `resourceGroupName`
already carried by the protected parameters file, rather than typing a name twice:

```powershell
$ResourceGroup = (Get-Content 'C:\protected\copilot-modernization-dotnet-bootstrap.json' -Raw |
  ConvertFrom-Json).parameters.resourceGroupName.value
if ($ResourceGroup -cnotmatch '^rg-user[0-9]{3}$') {
  throw 'the protected parameters must name your participant resource group'
}
```

Those `C:\protected\*.json` documents are not yours to write. The facilitator's
provisioning wrote `copilot-modernization-dotnet-bootstrap.json`,
`copilot-modernization-dotnet-baseline.json`, and
`copilot-modernization-dotnet-release.json` on this VM before the workshop started, one
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

Deploy baseline first, then release. Both carry the same immutable digest; only the
protected file, the deployment name, and therefore the revision role differ:

```powershell
az deployment group create `
  --name "copilot-modernization-dotnet-baseline-$($SourceCommit.Substring(0, 12))" `
  --resource-group $ResourceGroup `
  --template-file infra\main.bicep `
  --parameters '@C:\protected\copilot-modernization-dotnet-baseline.json' `
  --parameters sourceCommit=$SourceCommit imageDigest=$ImageDigest `
  --output none
if ($LASTEXITCODE -ne 0) { throw 'baseline deployment failed' }

$ReleaseLines = az deployment group create `
  --name "copilot-modernization-dotnet-release-$($SourceCommit.Substring(0, 12))" `
  --resource-group $ResourceGroup `
  --template-file infra\main.bicep `
  --parameters '@C:\protected\copilot-modernization-dotnet-release.json' `
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
release-role application-stage output. Verify it, and the retained rollback revision, with
the frozen query:

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
$env:AZURE_CONFIG_DIR = Join-Path $HOME '.azure-365'
$SqlAccessToken = (
  az account get-access-token `
    --resource https://database.windows.net/ `
    --query accessToken --output tsv
).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($SqlAccessToken)) {
    throw 'Azure SQL access-token acquisition failed'
}
$env:CATALOG_DATABASE_KIND = 'sqlserver'
$env:CATALOG_DATABASE_HOST = $ReleaseTarget.database.server
$env:CATALOG_DATABASE_NAME = $ReleaseTarget.database.database
$env:CATALOG_DATABASE_SSL_MODE = 'require'
$env:CATALOG_DATABASE_TARGET = 'managed'
$AcceptanceExit = 0
try {
  $env:SQLCMDACCESS_TOKEN = $SqlAccessToken
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
  Remove-Item Env:SQLCMDACCESS_TOKEN -ErrorAction SilentlyContinue
  Remove-Item Env:PERFTEST_API_KEY -ErrorAction SilentlyContinue
  $SqlAccessToken = $null
}
if ($AcceptanceExit -ne 0) { throw 'full acceptance failed' }
}
finally { Pop-Location }
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

Keep the exact required evidence, reviewed source changes, and frozen target
assets. Rejoin the shared workshop only after the handoff validator succeeds;
downstream challenges consume `evidence/modernization-contract.json`, not IDE
assessment or task output.

## Optional appendix

The preview Modernize CLI is optional and not required for this solution. It
cannot replace the signed IDE workflow, native build/tests, `catalog-migrate`,
full acceptance, telemetry proof, or handoff validation.

## If a command will not run here

| Symptom | Cause | What to do |
| --- | --- | --- |
| `git` is not recognized | Git for Windows is pinned and installed at `C:\Program Files\Git\cmd\git.exe`, but a shell opened before provisioning finished does not have it on `PATH`. | Open a new terminal and `cd C:\MicroHack\source` again, or call the full path once to confirm the install. |
| `git rev-parse HEAD` does not match `.source-commit` | Expected. The working tree is a local repository initialized over the extracted archive, so its commits are unrelated to the published upstream commit. | Use `git rev-parse HEAD` for the commit holding your work, which is what every build, deployment, and evidence file here is keyed to. Use `.source-commit` only when a step asks for upstream archive provenance. |
| `docker` is not recognized | The provisioned VM has no Docker daemon. | Step 4 already uses `az acr build`, which needs none. If any generated task proposes a local `docker build`, reject it and replan — that is exactly the kind of preflight mismatch step 3 asks you to record. |

---

**Challenge:** [Path 1C: GitHub Copilot modernization](../../../challenges/ch01-copilot-modernization/README.md) ·
**Other stack:** [Copilot modernization Java](../java/README.md) ·
**Modernized target:** [Reference implementation](../../reference/README.md) ·
**Next:** [Challenge 2: load and autoscaling](../../../challenges/ch02/README.md)
