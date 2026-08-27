### 2026-08-27 (Challenge 1 - manual .NET control arm)
- Added the manual-path `dotnet/Dockerfile` with digest-pinned .NET 8 build/runtime images,
  numeric non-root user `1654`, read-only canonical seed, port `8080`, health check, and
  external `/app/images` boundary.
- Documented local image build and inspection commands in `dotnet/README.md`.
- Generated schema-bound native runtime evidence from the passing 42-test TRX artifact.
- Kept the exercise at the authorized no-deploy boundary and recorded measured local
  timings, ambiguities, immutable baseline provenance, and the subscription public-IP
  policy limitation in `evidence/manual-dotnet-control-feedback.md`.

### 2025-08-28 (Infrastructure - network redesign with Bastion)
- Adjusted per-user VNet to /22 CIDR with dedicated `vms` /24 and `AzureBastionSubnet` /26.
- Removed public IP from VM NIC; Standard Public IP now attached to Azure Bastion (Basic SKU) for secure RDP.
- Replaced permissive NSG rules with single rule allowing RDP only from VirtualNetwork (Bastion access path).
- Added Bastion host deployment and set Public IP SKU to Standard to satisfy Bastion requirements.
### 2025-08-28 (Infrastructure - inline Public IP)
- Removed separate `pip.bicep` module; inlined Public IP resource into `workload.bicep` (Standard SKU Static) simplifying module graph.
- Updated Bastion host to reference inlined `publicIp` resource id directly.
- README updated (removed module reference, clarified NSG restriction & subnet layout).
### 2025-08-28 (Infrastructure - VM provisioning script)
- Added `baseInfra/scripts/setup.ps1` headless provisioning script (Git, .NET SDK, SQL Express, clone repo, publish app, create Windows Service, firewall rule, env vars). Intended for later Custom Script Extension integration.
### 2025-08-28 (Infrastructure - provisioning script simplification)
- Removed parameters from `setup.ps1`; replaced with top-of-file configuration block for simpler manual tweaking during early testing phase.
### 2025-08-28 (Infrastructure - Git install fallback)
- Enhanced `setup.ps1` Git installation: tries winget, then Chocolatey, then direct silent installer download (pinned version) for Windows Server environments lacking winget.
### 2025-08-28 (Infrastructure - .NET install robustness)
- Improved .NET SDK detection & installation in `setup.ps1` (graceful failure handling, removed invalid -Verbose switch, added PATH refresh and post-install verification).
### 2025-08-28 (Infrastructure - SQL Express arg quoting fix)
- Corrected quoting for `/SQLSVCACCOUNT` in SQL Express silent install args to avoid PowerShell parser error; added log echo of arguments.
### 2025-08-28 (Infrastructure - SQL Express installer robustness)
- Added multi-URL download strategy, bootstrap detection, two-step media download, improved silent install args & timeout loop in `setup.ps1`.
### 2025-08-28 (Infrastructure - SQL Express bootstrap simplification)
- Removed two-step ACTION=Download path; bootstrap now invoked directly with install args and exit code checked.
### 2025-08-28 (Infrastructure - SQL Express extraction install)
- Adjusted `setup.ps1` to always self-extract installer then run inner setup.exe with minimal supported flags (resolving unrecognized settings errors).
### 2025-08-28 (Infrastructure - SQL Express multi-strategy)
- Replaced extraction approach with tiered install (winget -> Chocolatey -> manual bootstrap) plus extended polling.
### 2025-08-28 (Infrastructure - provisioning simplification - Chocolatey baseline)
- Simplified `setup.ps1` by ensuring Chocolatey is installed first, then using it uniformly for Git, .NET SDK, and SQL Server Express (removed multi-strategy logic & manual bootstrap fallback to reduce complexity on Server images lacking winget).
### 2025-08-28 (Infrastructure - service creation diagnostics)
- Added verbose diagnostics & error handling around Windows Service creation in `setup.ps1` (captures sc.exe output, validates existence, fails fast if missing).
### 2025-08-28 (Infrastructure - service creation fallback & self-contained option)
- Added fallback using `New-Service` if `sc.exe create` doesn't materialize service; introduced optional self-contained publish mode to simplify service binPath.
### 2025-08-28 (Infrastructure - pin .NET SDK 8.0.0)
- Modified provisioning script to install exact .NET 8.0.0 (SDK 8.0.100) via dotnet-install script instead of major version heuristic.
### 2025-08-28 (Infrastructure - switch .NET pin to Chocolatey)
- Adjusted provisioning script to use Chocolatey for pinned .NET 8.0 SDK installation (tries multiple package IDs, removes dotnet-install script usage as per requirement).
### 2025-08-28 (Infrastructure - exact .NET SDK 8.0.413 pin)
- Updated provisioning script to require and install only .NET SDK 8.0.413 via Chocolatey (fails fast if not available or mismatched).
### 2025-08-28 (Infrastructure - simplify .NET 8.0.413 install)
- Reduced .NET SDK install logic to a single Chocolatey install attempt (removed multi-package loop, added concise validation).
### 2025-08-28 (Infrastructure - simplify runtime startup)
- Removed service / publish / env var configuration from provisioning script; added startup scheduled task executing `dotnet run` in repo directory for auto-start after reboot.
### 2025-08-28 (Infrastructure - desktop shortcut & browser launch)
- Replaced scheduled task approach with creation of desktop shortcut invoking `start-app.ps1`.
- `start-app.ps1` now sets ASPNETCORE_URLS to http://localhost:5000, starts the app in background, and opens default browser to that URL after short delay.
### 2025-08-28 (Infrastructure - VM Custom Script Extension)
- Added Custom Script Extension to `workload.bicep` executing `setup.ps1` from GitHub URL during VM provisioning (installs dependencies, creates desktop shortcut & browser launch script).
### 2025-08-29 (Infrastructure - NAT Gateway)
### 2025-08-29 (App / Infra - DB creation responsibility shift)
- Removed unconditional `EnsureCreated()` database creation from application startup (now guarded and only creates tables if DB reachable; no CREATE DATABASE attempt).
- Added `SKIP_DB_INIT` env var gate (default '0'); infra/script now pre-creates database aligning with Azure SQL model where database is provisioned separately.
- Updated `setup.ps1` to add config variables for `$DatabaseName`, optional SQL login creation, and to idempotently create the database via `sqlcmd`.
- Rationale: principle of least privilege & forward compatibility with Azure SQL where server-level CREATE DATABASE may not be permitted to app principal.
### 2025-08-29 (Infrastructure - sqlcmd handling simplification)
- Simplified `Ensure-SqlCmd` to probe only two observed install locations and perform a single winget install attempt, removing multi-fallback complexity for clarity on Server 2025 hosts.
### 2025-08-29 (Infrastructure - sqlcmd robustness follow-up)
- Enhanced `Ensure-SqlCmd` to: verify execution (`sqlcmd -?`), persist discovered directory to Machine PATH, and fall back to classic `Microsoft.SQLServer.CommandLineTools` if modern package present but non-functional.
### 2025-08-29 (Infrastructure - setup.ps1 winget removal & simplification)
- Rewrote provisioning script to eliminate `winget` dependency (not available during Custom Script Extension under SYSTEM) using direct downloads:
	- .NET SDK via `dotnet-install.ps1` channel 8.0
	- SQL Server 2022 Express bootstrap with silent arguments enabling mixed mode + TCP 1433
	- Modern `sqlcmd` (go-sqlcmd) GitHub release zip (pinned version 1.7.0)
- Structured into numbered steps with concise helper functions (Step / Retry / Wait-For) for clarity.
- Moved configuration constants to a single block at top; removed previous multifallback logic and legacy variable section.
- Database & login provisioning now performed using SA credential established at install, then tested with application login.
- Start script generation unchanged in behavior (updated to use new config variables).
### 2025-08-29 (Infrastructure - persist .NET PATH)
- Updated `setup.ps1` to append `C:\Program Files\dotnet` to Machine PATH and set `DOTNET_ROOT` so `dotnet` CLI is available after VM reboot (fixes post-restart 'dotnet not found' issue under new sessions / scheduled tasks).
### 2025-08-29 (Infrastructure - delayed app auto-start)
- Added `start-app-delayed.ps1` wrapper (60s sleep) and updated scheduled task in `setup.ps1` to invoke it, mitigating race where first logon occurs before user profile & PATH (with dotnet) are fully initialized.
### 2025-08-29 (Infrastructure - WSL enablement)
- `setup.ps1` now always enables `Microsoft-Windows-Subsystem-Linux` and `VirtualMachinePlatform` (idempotent) and schedules a reboot (60s) only if features were newly enabled. Prepares for dev tooling (e.g., Rancher Desktop) requiring WSL.
### 2025-08-29 (Infrastructure - dev tools post-logon installer)
- Added Step 8 creating one-time scheduled task `DevToolsInstallOnce` plus `C:\dev-tools-install.ps1` to install VS Code, Azure CLI, Rancher Desktop, and SSMS via winget on first interactive logon; task self-unregisters after success and writes marker file.
### 2025-08-29 (Infrastructure - simplify startup & dev tools execution)
- Removed scheduled tasks (auto-start & dev tools). Retained plain scripts `C:\start-app.ps1` and `C:\dev-tools-install.ps1` for manual execution. Eliminated delayed wrapper. DISM 3010 exit code now treated as success requiring reboot.
### 2025-08-30 (Infrastructure - dev tools script update)
- Added Git (`Git.Git`) installation to `C:\dev-tools-install.ps1` script.
### 2025-09-01 (Challenge 01 - Azure SQL serverless template)
- Added `solutions/ch01/bicep/main.bicep` to deploy Azure SQL logical server + single serverless database (General Purpose tier) with auto-pause 60 minutes and max 2 vCores (implicit min 0.5).
- Implemented unique server naming via `uniqueString(resourceGroup().id)` and firewall rule parameterizing application public IP.
- Included example parameters file `main.bicepparam` and README with deployment instructions & rationale for omitted explicit `minCapacity`.
### 2025-09-01 (Challenge 01 - Bicep fixes & lint cleanup)
- Replaced incorrect `securestring` ARM-style type with Bicep secure decorator (`@secure() param administratorLoginPassword string`).
- Simplified child database resource syntax using `parent` property; removed unnecessary `dependsOn` and updated output to still surface names (no functional change).
- Addressed linter warnings: removed quotes around tag key `workload` (left quotes for `managed-by` which contains a hyphen) and eliminated `use-parent-property` & `no-unnecessary-dependson` warnings.
- Left API version at preview per original template (only warning-level diagnostics); consider moving to latest stable typed version in future hardening pass.
### 2025-09-01 (App - Dockerfile for Blazor Server)
- Added multi-stage Linux Dockerfile (`dotnet/Dockerfile`) targeting .NET 8 (SDK -> aspnet runtime).
- Uses Debian-based images (not Alpine) to avoid additional native dependency installs for `Microsoft.Data.SqlClient`.
- Sets default `ASPNETCORE_URLS=http://0.0.0.0:8080`, exposes 8080, and creates non-root `appuser`.
- README updated with build/run instructions including volume mounts for images & seed catalog.
### 2025-09-01 (App - Dockerfile publish fix)
- Removed `--no-restore` from publish to prevent intermittent `NETSDK1064` (missing analyzer package) during layered build; publish now performs final restore ensuring completeness.
### 2025-09-01 (Challenge 01 - Add Azure Container Registry)
- Extended `solutions/ch01/bicep/main.bicep` to provision Azure Container Registry with unique name (`acr${uniqueString(resourceGroup().id)}`) and configurable SKU (Basic default; allowed Standard/Premium).
- Added outputs for registry name & login server; disabled admin user (prefer AAD) and documented usage in README.
- Updated parameter file and Bicep README to reflect new `acrSku` parameter and combined scope (SQL + ACR).
### 2025-09-01 (Challenge 01 - Allow Azure services firewall rule)
- Added `AllowAzureServices` firewall rule (0.0.0.0 start/end) to SQL server in `solutions/ch01/bicep/main.bicep` to permit connections from Azure services when app lacks fixed outbound IP.
### 2025-09-01 (Challenge 01 - Container Apps deployment)
- Extended `solutions/ch01/bicep/main.bicep` with Azure Container Apps managed environment (consumption workload profile) and a mutable ACR application tag that was removed by the reproducibility rewrite.
- Added storage account + two Azure Files shares (seed + images) mounted at `/mnt/seed` and `/mnt/images`; env vars `IMAGE_ROOT_PATH` and `SEED_DATA_PATH` updated accordingly.
- Implemented secret for `SQL_CONNECTION_STRING` and AcrPull role assignment via system-assigned identity.
- Configured HTTP ingress (external) on port 8080 and HTTP-based autoscale 0..3 replicas (concurrentRequests=50 threshold).
### 2025-09-01 (Challenge 01 - Container Apps deployment fix)
- Fixed Bicep compile issues: replaced fractional CPU (0.5) with integer 1 due to Bicep numeric literal limitation; added explanatory comment.
- Adjusted role assignment resource name to exclude runtime principalId (now deterministic GUID using ACR id + app name) resolving BCP120.
### 2025-09-01 (Challenge 01 - ACR image pull hardening)
- Switched Container App from system-assigned to user-assigned managed identity for ACR pulls following official guidance (pre-create identity, grant AcrPull before app deploy) to avoid cold-start race where image pull occurs before role assignment propagates.
- Added `userAssignedIdentityName` parameter & identity resource, updated role assignment to use identity principalId, configured container registry block with identity resource ID.
- Exposed identity resource ID in outputs for diagnostics.
### 2025-09-03 (CI/CD - Simple GitHub Actions workflow)
- Added `.github/workflows/simple.yaml` triggering on `push` to `main` affecting `dotnet/**` and manual `workflow_dispatch`.
- Implements OIDC Azure login (id-token permission) using repository variables (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`).
- Builds Docker image from `dotnet/Dockerfile` tagging only with workflow run ID (`<GITHUB_RUN_ID>`), no `latest` tag to enforce explicit version pinning, pushes to ACR `${{ vars.ACR_NAME }}` under repository `lego-catalog/app`.
- Updates Azure Container App `lego-catalog-app` in resource group `${{ vars.RESOURCE_GROUP_NAME }}` with new image and sets `IMAGE_VERSION` env var.
- Notes: placeholder disabled docker/login-action kept for future direct push optimization; relies on `az acr login` after Azure CLI OIDC auth.
### 2025-09-03 (CI/CD - GitHub Actions Managed Identity in Bicep)
- Extended `solutions/ch03/bicep/main.bicep` with GitHub Actions user-assigned managed identity + federated identity credential (issuer `token.actions.githubusercontent.com`).
- Added parameters: `githubOrg`, `githubRepo`, `githubBranch`, `githubActionsIdentityName` (defaults set to repository details and `main`).
- Added Contributor role assignment for identity at resource group scope (guid derived) enabling infrastructure + container app updates.
- Outputs now include `ghActionsIdentityClientId` / principal & resource IDs for populating GitHub repository variables (`AZURE_CLIENT_ID`).
- Updated Bicep README documenting new parameters, outputs, and setup instructions for OIDC.
### 2025-09-03 (Container Apps - Enable multiple revisions)
- Changed `activeRevisionsMode` from `Single` to `Multiple` in `solutions/ch03/bicep/main.bicep` to support advanced deployment workflow (parallel revisions, manual promotion / traffic splitting).
- Added inline comment explaining rationale; groundwork for upcoming multi-step GitHub Actions pipeline (blue/green or canary style) described in challenge README.
### 2025-09-03 (CI/CD - Multi-environment GitHub federation)
- Added two additional federated identity credentials to GitHub Actions managed identity for environments `staging` and `production` (subjects `repo:<org>/<repo>:environment:staging|production`).
- Allows using GitHub Environments with protection rules & approvals while reusing the same Azure Managed Identity.
- Updated README (ch03) with instructions on referencing environment-based OIDC in workflows.
### 2025-09-03 (CI/CD - Multi-revision staged promotion workflow)
- Refactored `.github/workflows/simple.yaml` into two jobs: `build_and_stage` (environment: staging) and `promote_production` (environment: production with approval).
- Staging job builds & pushes image (tag = run id), creates new revision, forces 0% traffic to new revision (old stays 100%) and exports revision names.
- Production job (after manual approval) shifts traffic to new revision (100%) and deactivates previous revision to reduce drift.
- Supports blue/green style promotion using Azure Container Apps multiple revisions mode and GitHub Environments gating.
### 2025-09-03 (CI/CD - Production cleanup enhancement)
- Updated production promotion step to deactivate all previously active revisions (not just the immediately prior one) after shifting traffic to the new revision.
- Ensures a single active revision remains, simplifying rollback logic and reducing resource usage.
### 2025-09-03 (App - OpenTelemetry instrumentation)
- Added OpenTelemetry packages (core, hosting, OTLP exporter, AspNetCore, SqlClient, Http, Runtime, Process instrumentations).
- Configured `Program.cs` with resource builder (service name fallback `lego-catalog`), tracing, metrics, logging, and OTLP exporter via `.UseOtlpExporter()` (env driven, no hard-coded endpoints).
- Introduced custom `ActivitySource` + `Meter` and counter `lego.perf_endpoint.invocations` plus a small internal activity segment for `/perftest/catalog` post-processing.
- Updated README with comprehensive OTEL_* environment variable documentation and quick start collector example.
- Chose secure defaults: do not emit full SQL text; rely on sampling env vars if set; query redaction remains enabled unless experimental disable variable applied.
### 2025-09-03 (Challenge 04 - OpenTelemetry Collector + App Insights wiring)
- Extended `solutions/ch04/bicep/main.bicep` with optional monitoring stack controlled by `enableOtel` (default true).
- Added Log Analytics workspace + workspace-based Application Insights component (web kind) when enabled.
- Injected `appInsightsConfiguration.connectionString` and `openTelemetryConfiguration` (traces + logs destinations = `appInsights`) into Container Apps managed environment using preview API version supporting OTEL.
- Added new parameters: `enableOtel`, `logAnalyticsWorkspaceName`, `appInsightsName`, `logAnalyticsRetentionInDays` (with validation range 30-730 days).
- Updated parameter file with defaults & commented override examples; README (ch04) documents usage, validation steps, and notes on metrics limitation.
- Exposed outputs for connection string and resource names (or 'disabled' sentinel) to aid testing and GitHub workflows.
### 2025-09-03 (Infrastructure - RG tagging for security exemption)
- Added `SecurityControl=ignore` tag to per-user resource group in `baseInfra/bicep/userInfra.bicep` to satisfy security scanning exemption requirement.
### 2025-09-08 (Dev Experience - VS Code Dev Container)
- Added `.devcontainer/` with `Dockerfile` (base `mcr.microsoft.com/devcontainers/dotnet:1-8.0-bookworm`) installing Azure CLI, azd, and upgrading Bicep CLI.
- Included Docker CLI & mounted host Docker socket for building/testing container images inside the dev container.
- Added `devcontainer.json` configuring extensions: C# (`ms-dotnettools.csharp`), Bicep, Docker, GitHub Copilot + Chat; sets default solution and restores on open.
- Created workspace file `MicroHack-AppInnovation.code-workspace` with recommended extensions & solution focus.
- Rationale: consistent Linux environment across contributors (macOS/Windows hosts) with pinned .NET 8 toolchain & Azure CLIs, enabling infra (Bicep) + app (Container Apps) workflows.
- Notes: `postCreateCommand` surfaces versions for quick diagnostics; Docker group membership enables image build via host daemon; telemetry disabled for reproducibility.
### 2025-09-08 (Dev Experience - Dev Container .NET roll-forward fix)
- Removed `DOTNET_ROLL_FORWARD=disable` (set to `LatestPatch`) in `.devcontainer/Dockerfile` to allow patch roll-forward (previous setting caused runtime error when app built for 8.0.0 but only 8.0.19 present).
- Rationale: default behavior (LatestPatch) ensures security updates & avoids manual pin churn while keeping major/minor stable.
- No code changes required in application; rebuild dev container to apply (`Rebuild Container`).
### 2025-09-08 (Dev Experience - SQL Server Express sidecar)
- Updated `devcontainer.json` `postCreateCommand` to launch a persistent `microhack-sql` container (`mcr.microsoft.com/mssql/server:2022-latest`, `MSSQL_PID=Express`).
- Added `MSSQL_SA_PASSWORD` env var (a literal placeholder value at the time) and described port 1433 as available for host access.
- Data persisted in named Docker volume `microhack-sql-data`; startup idempotent (skips if container already exists).
- Rationale: sidecar container avoids complexity of running SQL Server service inside main dev container (no systemd), keeps image lean, and mirrors production external DB topology.

> **Correction appended 2026-02.** Two statements in the entry above were wrong or had
> gone stale, so the entry was edited in place rather than left to mislead; this note
> records what changed and why.
>
> * The literal placeholder password was removed from this line. It was a well-known
>   sample string rather than a real secret, but a password-shaped literal in a
>   repository is copied far more often than it is read, and it contradicted the fix
>   below. `.devcontainer/devcontainer.json:43` now reads
>   `"MSSQL_SA_PASSWORD": "${localEnv:MSSQL_SA_PASSWORD}"`, so the value comes from the
>   contributor's own host and is never committed.
> * The claim that port 1433 was "mapped for host access" did not match
>   `devcontainer.json`, which performs no such mapping. The wording now describes only
>   what the configuration actually did.
>
> Nothing in this repository reads `MSSQL_SA_PASSWORD`; it is a convenience passthrough
> for a SQL Server sibling container, which is why an unset value warns at container
> create time instead of failing the build.
## Implementation Log
### YYYY-MM-DD Split setup script into modular stages
Refactored `baseInfra/scripts/setup.ps1` into an orchestration-only script. Added modular scripts:
* `SQL_install.ps1` – installs & configures SQL Server (static TCP 1433 + firewall), installs `sqlcmd`, provisions DB/login.
* `App_install.ps1` – installs .NET SDK if needed, downloads source, creates start script using static port connection string.
* `Dev_install_initial.ps1` – enables WSL + VirtualMachinePlatform, creates reboot sentinel if needed.
* `Dev_install_post_reboot.ps1` – installs developer tooling after reboot, then cleans up scheduled task & sentinel.

Introduced status tracking file `C:\install_status.txt` with stages: `sql`, `app`, `dev`, `devpost` each set to `pending|running|failed|success`. Orchestrator is idempotent and skips completed stages.


### 2025-08-27
Initial implementation of Python data generator (`main.py`):
- Uses Azure OpenAI `AzureOpenAI` client & Responses API for structured text (categories/items) and image generation.
- Batch size default reduced to 20 per new requirement.
- Model now returns `imagePrompt`; no local heuristic assembly.
- Pydantic models for categories, generated items, and catalog items; basic validation (prefix + forbidden tokens).
- Simple resume logic (loads existing `catalog.json` if `--resume`).
- Concurrency for image generation via asyncio semaphore.
- Idempotent category generation unless `--force-categories`.

Future improvements (not yet implemented):
- Robust retry/backoff logic (current version relies on implicit SDK behavior only)
- Enhanced schema / banned token scanning & logging
- Partial save of images progress & failed images list
- More granular error handling & exponential backoff for rate limits

#### Later on 2025-08-27 (same day)
Adjustments & troubleshooting:
- Removed unsupported `response_format` / `modalities` parameters after SDK errors; switched to `responses.parse` with `text_format` using Pydantic models for structured outputs.
- Migrated from deprecated Pydantic v1 `@validator` to v2 `@field_validator` to remove deprecation warnings.
- Multiple failed attempts to generate images via Responses API (direct modalities, then tool invocation) resulted in HTTP 400; pivoted to dedicated `images.generate` API which succeeded for the majority of items.
- Added retry loop (simple exponential backoff) around image generation; still basic and could classify errors better.
- Generated full set target of 200 catalog entries; only 198 images produced (2 failures) during first pass.
- Implemented maintenance utility `prune_missing_images.py` to detect & optionally prune catalog entries whose images are missing. Ran with `--prune` producing backup `catalog.json.bak` and pruned catalog now at 198 entries.
- Environment cleanup: removed unused IMAGE_SIZE env var; batch size kept default 20 in code (note: earlier `.env` still had BATCH_SIZE=50; code path prefers explicit CLI or default constant).
- Logging still minimal; future improvement to record failed image requests with reason codes.

Next potential enhancements:
- Add `--repair-missing-images` workflow to attempt regeneration before pruning.
- Persist a `failed_images.json` with error metadata for audit.
- Align `.env` BATCH_SIZE with default or read it explicitly to avoid confusion.
- Add simple tests under `tests/` for: category generation shape; item batch shape; missing image pruning logic.

### 2025-08-27 (later)
Added initial .NET Blazor Server application (`dotnet/`):
- net9.0 Blazor Server app with EF Core SqlServer; automatic `EnsureCreated` on startup.
- Environment variable overrides (`SQL_CONNECTION_STRING`, `SEED_DATA_PATH`, `IMAGE_ROOT_PATH`, `SKIP_STARTUP_IMPORT`).
- Repository + service layer (`FigureRepository`, `CategoryRepository`, `FigureCatalogService`).
- Startup hosted service to import seed data when DB empty.
- Import page (`/Import`) implemented as Razor Page for file upload of `catalog.json` (idempotent insert-only for new figure IDs).
- Static image serving endpoint `/images/{file}` backed by configurable root path.
- Basic UI: list, search, category filter, detail view.
- README with run instructions.

Deferred (documented for future): blob image store, telemetry.

#### 2025-08-27 (decision: keep simplicity)
- Reverted migration setup back to `EnsureCreated` to avoid external tooling steps.
- Removed Tools package & design-time factory; migrations deferred until schema changes justify complexity.

#### 2025-08-27 (import simplification)
- Removed manual Import page and button; startup import now always runs (idempotent) without SKIP/FORCE flags.
- Startup service logs only total parsed + newly added.

### 2025-08-27 (UI modernization pass)
- Replaced simplistic top bar with sticky header, navigation using `NavLink`, GitHub link, and theme toggle.
- Later same day: removed brand/logo & navigation links (single-page app) keeping only theme toggle + GitHub link in compact header.
- Added dark/light theme with persisted preference via localStorage and CSS custom properties.
- Introduced modern card grid with hover elevation, skeleton loading placeholders, responsive layout, and accessible keyboard interaction.
- Enhanced figure detail page layout (two-column responsive) and badge styles.
- Added Inter font, gradient brand text, refined buttons (primary/ghost) and toolbar styling.
- Implemented reset filters, improved empty state, and focus navigation (updated selector to `h1,h2,h3`).
- Updated CSS with light mode fallback, reduced-motion support, and improved scrollbar styling.
 - Removed obsolete Import navigation (automatic startup import only) and associated Razor Page.

### 2025-08-27 (Infrastructure - initial Bicep modules)
- Added base `bicep/` templates: `main.bicep` (subscription loop), `userInfra.bicep` (RG + pip per user), `pip.bicep` (Public IP resource group module).
- Implemented initial naming convention (later revised) `userNNN-rg` / `userNNN-pip` with zero-padded indices starting at 1.
- Added Deployment Stack CLI instructions to `baseInfra/README.md` for create/update, what-if, listing, and destroy operations.
- Chose `westeurope` default location (adjustable via parameter).
- Future: extend module to include VNET + VM + initialization scripts.

### 2025-08-27 (Infrastructure - naming revision & fix)
- Updated naming to CAF-style prefix ordering: `rg-userNNN`, `pip-userNNN`.
- Fixed Bicep BCP144 error by indexing module collection in output comprehension.

### 2025-08-27 (Infrastructure - per-user network + VM)
- Extended `userInfra.bicep` to provision VNet, Subnet, NSG (RDP/HTTP/HTTPS), NIC, and Windows Server 2022 VM per user.
- Added parameters for admin credentials, VM size, accelerated networking, and optional custom CIDRs.
- Updated `main.bicep` to pass secure admin credentials and fixed loop off-by-one (range now 1..n inclusive).
- README updated with new resource list & CLI examples including credentials.

### 2025-08-28 (Infrastructure - module refactor & lint fixes)
- Introduced `workload.bicep` (resource group scope) containing PIP, NSG, VNet, NIC, VM.
- Simplified `userInfra.bicep` to only create RG and call workload module.
- Addressed Bicep scope errors (BCP037/BCP139) and removed unnecessary dependsOn warnings.
- Updated README to document new module list.
### 2025-09-16 (Infrastructure - multi-script Custom Script Extension)
- Updated `baseInfra/bicep/workload.bicep` Custom Script Extension to download all modular provisioning scripts (`setup.ps1` orchestrator plus stage scripts: `SQL_install.ps1`, `App_install.ps1`, `Dev_install_initial.ps1`, `Dev_install_post_reboot.ps1`).
- Rationale: ensures orchestrator has local copies for idempotent stage execution and post-reboot scheduled task without needing additional network fetches beyond initial extension run.
- Implemented via new variables listing each raw GitHub URL and aggregated `provisioningScriptFiles` array passed to `fileUris`.
### 2025-09-16 (Dev Tools - system-wide VS Code)
- Modified `Dev_install_post_reboot.ps1` to install Visual Studio Code with `--scope machine` via winget.
- Added fallback to direct system installer download if winget machine-scope install returns non-zero exit code or throws.
- Rationale: original per-user install failed when script ran under SYSTEM before a user profile existed.
### 2025-09-19 (Infrastructure - Terraform azapi translation)
- Added Terraform implementation (`baseInfra/terraform`) mirroring Bicep per-user environment deployment using `azapi_resource` for all Azure resource types.
- Root module loops `n` user environments via `for_each` on range; each environment module provisions RG, Public IPs, NAT Gateway, NSG, VNet + subnets, NIC, Bastion, Windows VM, and Custom Script Extension applying existing provisioning scripts.
- Implemented rich variable descriptions per project guidance; outputs aggregate resource group, VM, and VNet names.
- Chose `azapi` exclusively for resources (still declaring `azurerm` provider to satisfy auth & data lookups) to meet requirement of using azapi instead of azurerm resources.
- Included sample `config.auto.tfvars` with placeholder password and guidance to override securely.
### 2025-09-19 (Infrastructure - Terraform module refactor)
- Split `modules/user_environment/main.tf` into multiple focused files: `variables.tf`, `locals.tf`, `main.tf` (RG only), `networking.tf`, `bastion.tf`, `vm.tf`, and `outputs.tf`.
- Rationale: improve readability, enable targeted future changes (e.g., swapping VM image or network rules) without touching unrelated logical sections.
- No functional changes; resource names, dependencies, and outputs remain identical for state continuity.
### 2025-09-19 (Infrastructure - Terraform variable simplification)
- Removed variables: `enable_accelerated_networking`, `override_vnet_address_space`, `override_subnet_prefix` to enforce consistent environment layout and reduce input surface.
- CIDR derivation now always `10.<index>.0.0/22` (VNet) with fixed `vms` `/24` and Bastion `/26`; accelerated networking hardcoded `false` for predictable provisioning across sizes.
- Updated root module, module interface, locals, and networking configuration accordingly; cleaned `config.auto.tfvars`.
### 2025-09-19 (Infrastructure - Terraform docs & outputs cleanup)
- Updated Terraform README to remove deprecated variables and clarify fixed CIDR scheme.
- Corrected root `outputs.tf` to reference `module.user_environment` (previously `module.user`).
- Added historical note explaining removal of override & acceleration variables.
### 2025-09-19 (Infrastructure - Terraform module providers declaration)
- Added `providers.tf` inside `modules/user_environment` declaring required providers (`azapi`, `azurerm`) for clearer module boundaries and potential future reuse.
- Left actual provider configuration only in root to avoid duplicate auth blocks per Terraform best practice.
### 2025-09-19 (Infrastructure - Terraform Entra user automation)
- Added `manage_entra_users` flag plus `entra_user_domain` and `entra_user_password` variables.
- Created `modules/entra_user` to provision one Entra ID user per environment (UPN pattern `labuserNNN@domain`).
- Added conditional Owner role assignment in `user_environment` module when a user object id supplied.
- Root outputs extended with user principal names and object IDs.
- README updated describing optional user provisioning and RBAC behavior.
### 2025-09-19 (Infrastructure - Terraform module variable docs)
- Added rich multiline descriptions to variables in `modules/user_environment/variables.tf` and `modules/entra_user/variables.tf` for clarity and parity with root variable documentation.
### 2025-09-19 (Infrastructure - Entra user naming alignment)
- Updated Entra user module to use `userNNN` (was `labuserNNN`) to match Azure resource naming convention (rg-userNNN, vm-userNNN, etc.).
### 2025-09-19 (Infrastructure - Role assignment naming fix)
- Replaced invalid `uuid()` usage with `uuidv5()` deterministic GUID for Owner role assignment resource in `user_environment` (rbac.tf) to ensure idempotent apply.
### 2025-09-19 (Infrastructure - Role assignment count fix)
- Introduced `create_role_assignment` explicit boolean to avoid unknown count evaluation.
- Updated rbac resource to use this flag instead of checking nullable ID directly and added lifecycle precondition validating presence of user object id.
### 2025-09-19 (Infrastructure - VM system-assigned managed identity)
- Enabled system-assigned managed identity on workshop VM (azapi VM body identity type SystemAssigned).
- Added Owner role assignment targeting VM identity principal for per-user resource group (separate from optional user Owner assignment).
- Updated Terraform README to reflect identity & RBAC change.
### 2025-09-19 (Infrastructure - RBAC refactor constants)
- Consolidated repeated Owner role GUID usage into locals (`owner_role_definition_id`, `role_assignment_ns`) in `rbac.tf` for maintainability.
- Updated uuidv5 calls to reference namespace local instead of duplicating GUID string.
### 2025-09-19 (Docs - README proofreading & consistency pass)
- Root `README.md`: grammar fixes (cloud leverage sentence, "you're interested" correction, clarified challenge 5 description, consistent environment variable terminology, tightened tips section wording).
- `solutions/ch01/README.md`: corrected numerous typos (appsetings/appsettings, yu/you), improved step wording, clarified Docker and ACR steps, rewrote bonus section for clarity.
- `solutions/ch02/README.md`: fixed misspellings (compes→comes, Lucost→Locust, Seoptember→September), restructured explanation of Load Testing vs Playwright, clarified metric interpretation.
- `solutions/ch03/README.md`: improved pipeline narrative, fixed grammar (int→at, paralel→parallel), standardized prompts and environment variable guidance.
- `solutions/ch04/README.md`: fixed phrasing (ready so send→ready to send), clarified OpenTelemetry Collector integration steps.
- `dataGenerator/README.md`: corrected "Fotorealistic" to "Photorealistic", added missing TARGET_COUNT variable, normalized numbering (sequential sections), improved educational disclaimer, adjusted JSON example.
- `solutions/ch04/bicep/README.md`: added duplication placeholder note recommending future monitoring-specific content.
- Minor consistency adjustments (use of “frontend”, “OpenTelemetry”, clarified non-vendor instrumentation approach).
### 2025-09-19 (Docs - Challenge 5 descriptions)
- Added detailed `challenges/ch05-enterprise/README.md` outlining enterprise security hardening focus (network isolation, private endpoints, WAF / Front Door, Entra ID auth, Managed Identity, CMK encryption, governance, observability) plus flexible deliverables.
- Added comprehensive `challenges/ch05-innovation/README.md` describing optional AI enhancement tracks (RAG chatbot, semantic search, translations, image generation, personalization) with architectural guidance and grounding best practices.
- Updated root `README.md` challenge listing with concise summaries for both flavors.
### 2025-09-20 (GitHub provisioning helper - interactive auth & env)
- Added `python-dotenv` dependency and `.env.sample` to `baseInfra/github`.
- Replaced placeholder `main.py` with implementation that:
	* Loads `.env` (token + desired org name)
	* Prompts for `GITHUB_TOKEN` if missing
	* Authenticates via PyGitHub and lists existing organizations
	* Documents limitation that free org creation must be manual (web flow) – no API call attempted
- Expanded `baseInfra/github/README.md` with usage instructions, token scope guidance, and limitation note.
- Future (not yet implemented): org member invites, repo templating, Azure billing linkage.
### 2025-09-20 (GitHub provisioning helper - switch to gh CLI auth)
- Refactored `baseInfra/github/main.py` to remove PAT prompting and rely exclusively on GitHub CLI (`gh auth token`).
- Updated `.env.sample` to drop `GITHUB_TOKEN` (now only `ORG_NAME`).
- Revised `baseInfra/github/README.md` to document gh-only authentication workflow and required setup steps.
- Rationale: simpler UX, no local secret storage, leverages existing secure token handling by GitHub CLI.
### 2025-09-20 (GitHub provisioning helper - gh status flag fix)
- Removed unsupported `--exit-code` flag from `gh auth status` invocation and replaced with output parsing fallback.
### 2025-09-20 (GitHub org access checker simplification)
- Simplified `baseInfra/github/main.py` to only validate access to `ORG_NAME` using GitHub CLI token.
- Removed listing of organizations and token validation verbosity; output now single-line `OK <org>` or error.
- Updated README to reflect new purpose and exit codes (0=success,1=config/auth,2=no access).
### 2025-09-20 (GitHub repo copy & template scaffolding)
- Added env vars `SOURCE_REPO`, `TARGET_REPO_NAME`, `MAKE_TEMPLATE` plus sample values.
- Extended `main.py` to create a new repository in target org (idempotent) and optionally flag it as template.
- Current limitation: repository content is not auto-copied; script notes manual steps to push source contents.
- README updated with usage and manual content population instructions.
### 2025-09-20 (GitHub repo copy simplification)
- Removed `TARGET_REPO_NAME` and `MAKE_TEMPLATE` options; destination name now always matches source repo name and repository is always marked as template.
- Updated `.env.sample`, README, and logic in `main.py` accordingly.
### 2025-09-20 (GitHub repo content synchronization)
- Added GitPython dependency and implemented automatic content sync: when copying a public `SOURCE_REPO`, if the destination org repo is newly created or empty (no branches), script clones source (full history) and pushes only the default branch to destination, then marks repo as template.
- Idempotent reruns: skip sync if destination already has branches; still enforce template flag.
- README updated to describe automated sync and provide manual mirror instructions for all refs.
### 2025-09-20 (GitHub helper README simplification)
- Rewrote `baseInfra/github/README.md` into a concise 5-step quick guide (create org, install/login gh CLI, configure `.env`, install deps, run). Removed verbose explanations to streamline onboarding.
### 2025-09-20 (GitHub helper user provisioning)
- Added `users.yaml.sample` and support for `USERS_FILE` env var (default `users.yaml`).
- Script now:
	* Invites users (by login or email) with role member/admin via GitHub CLI API calls.
	* Creates per-user repos named `<login>-<templateRepo>` when `SOURCE_REPO` provided, copying template content (default branch history).
	* Skips existing members/repos; resilient to partial failures.
- Added PyYAML dependency for parsing.
### 2025-09-20 (GitHub helper refactor & output normalization)
- Refactored `main.py` into smaller functions: `_ensure_org_template_repo`, `_handle_users_file`, `_invite`, `print_step`, `print_ok`.
- Standardized all progress output to "Action ... ✔" lines; removed ad-hoc NOTE messages.
- Added explicit step messages for template marking, content sync, per-user repo creation, and invitations.
### 2025-09-21 (GitHub helper - switch invitations to PyGithub)
- Replaced `gh api` subprocess-based invitation flow with direct PyGithub `Organization.create_invitation` calls (login -> invitee_id, email -> email param).
- Added heuristic handling for HTTP 422 responses: treat messages indicating existing membership or pending invite as success (idempotent reruns).
- Distinguish 403 (insufficient privileges / missing admin:org scope) from other errors in output.
- Simplifies code (no subprocess parsing) and unifies error handling via `GithubException`.
### 2025-09-21 (GitHub helper - enforce handle-only invites)
- Removed email-only invitation path; each users.yaml entry must supply `login`.
- Skips and logs entries missing login (`Skipping entry (login missing)`).
- Simplifies per-user repo logic (no unknown-login branch) and invitation helper signature.
### 2025-09-21 (GitHub helper - private per-user repos & access control)
- Modified per-user repository creation to force `private=True` regardless of template visibility, meeting requirement that only the user and org admins can access.
- Added explicit collaborator grant (`push` permission) for the owning user after repo creation and content sync to ensure access even if future default org base permissions are restricted.
- Output now includes a step line: `Granting access to <login> on <repo>` with success check mark; failures surface HTTP status for troubleshooting.
### 2025-09-21 (GitHub helper - per-user logging delimiter & counters)
- Added delimiter line `---` before each user block plus header `Processing <login> (<n> remaining)` to make multi-user runs easier to scan.
- Remaining count reflects only entries with a valid `login` key (skips invalid entries) for accurate progress reporting.
- Maintains consistent step/checkmark output style for new header lines (idempotent reruns unaffected).
### 2025-09-21 (GitHub helper - switch to template snapshot generation for user repos)
- Replaced clone/push history-preserving approach with GitHub server-side template generation (`/generate` endpoint) for per-user repositories.
- Significantly faster for many users; does not retain original commit history (intentional per requirement to only need a snapshot).
- Added helper `_generate_from_template` for low-level POST; reused existing collaborator grant step post-generation.
### 2025-09-21 (GitHub helper - README Azure billing note)
- Added explicit README section describing manual-only Azure subscription billing linkage steps and optional `.env` identifiers (`AZURE_SUBSCRIPTION_ID`, `AZURE_TENANT_ID`).
- Clarified per-user repo creation now uses snapshot (no history) from template.
### 2025-09-21 (GitHub helper - Copilot seat assignment)
- Added support for assigning GitHub Copilot Business seats to users flagged with `copilot: true` in `users.yaml`.
- Bulk assigns after processing all users via POST `/orgs/{org}/copilot/billing/selected_users` (treats 422 as idempotent success; surfaces 403 privilege errors).
- Requires token scopes/permissions capable of managing Copilot billing (e.g., manage_billing:copilot or sufficient org admin rights with appropriate fine-grained token).
### 2025-09-21 (GitHub helper - per-user Copilot seat assignment refinement)
- Changed seat assignment from bulk post-loop to immediate per-user invocation for faster feedback and clearer error correlation.
- Introduced `_assign_copilot_seat` wrapper (reuses bulk endpoint with single username) maintaining idempotent 422 handling.
- Removed accumulation list logic; each `copilot: true` user now emits its own assignment step.
### 2025-09-21 (GitHub helper - Copilot diagnostics & verification)
- Added pre-flight subscription status check (`_copilot_preflight`) printing plan, seat mode, and public code policy.
- Enhanced 422 handling with message snippet instead of silent success assumption.
- Added post-assignment verification (`_verify_copilot_seat`) to confirm active seat or report pending state.
- Provides clearer reasons when assignments are skipped (e.g., not enabled, wrong seat mode, billing/policy issues).
### 2025-09-22 (GitHub helper - remove Copilot automation)
- Removed all Copilot-related logic (pre-flight subscription check, seat assignment, verification).
- Rationale: organization will manage Copilot features & seats manually; API endpoints for advanced features not publicly supported/stable.
- Simplified `_handle_users_file` to only perform invitations and per-user repository provisioning.
- Removed helper functions `_assign_copilot_seats`, `_assign_copilot_seat`, `_copilot_preflight`, `_verify_copilot_seat` and associated output paths.
### 2025-09-22 (GitHub helper - Codespaces policy enablement)
- Added `_ensure_codespaces_all` to attempt setting organization Codespaces permissions to allow all members & repositories.
- Best-effort: logs non-fatal error (e.g., 404 if endpoint unavailable for plan or preview not enabled) and continues.
- Rationale: streamline workshop setup so every invited member can open Codespaces without manual org settings adjustment.
### 2025-09-22 (GitHub helper - simplify user list format)
- Simplified `users.yaml` and sample to plain list of GitHub usernames (removed `is_admin`, `copilot`).
- Updated parsing to accept either new string list or legacy dict entries (backward compatible).
- Invitation now always uses role `direct_member`; admin elevation handled manually if needed.
### 2025-09-22 (GitHub helper - Codespaces policy graceful handling)
- Adjusted `_ensure_codespaces_all` to treat 404 as non-fatal with "endpoint not available (skipping)" message.
- Added `SKIP_CODESPACES_POLICY` env var gate (values 1/true/yes) to bypass policy attempt entirely.
- Rationale: avoid noisy ERROR output for orgs/plans without the endpoint while keeping idempotent setup.
### 2025-09-22 (GitHub helper - Codespaces endpoint correction)
- Replaced undocumented `/codespaces/permissions` usage with documented `PUT /orgs/{org}/codespaces/access` for visibility management.
- Added `CODESPACES_INCLUDE_OUTSIDE` env var to toggle inclusion of outside collaborators (`all_members_and_outside_collaborators`).
- Endpoint unavailability (404), insufficient permission (403), or validation (422) now reported as neutral skip lines.
### 2025-09-22 (GitHub helper - Codespaces policy removal & run summary)
- Removed `_ensure_codespaces_all` invocation and function after decision to manage Codespaces visibility manually outside automation (reduced moving parts, avoided misleading 404 skips on orgs without feature enabled).
- Added end-of-run summary block with delimiter `---` reporting counts: invited, already members, per-user repos created, repos skipped.
- Rationale: focus script strictly on deterministic idempotent provisioning (org access check, template repo, user invites, per-user repos) and improve operator feedback while keeping output concise.
### 2025-09-24 (Infrastructure - Terraform subscription parameterization)
- Replaced hard-coded subscription GUID in `providers.tf` with new `subscription_id` variable.
- Added `subscription_id` entry to `config.auto.tfvars` for default workshop usage; value can now be overridden via `TF_VAR_subscription_id` env var or CLI flag without editing provider file.
- Updated variable documentation (`variables.tf`) explaining fallback behavior if omitted and rationale (portability & reproducibility across environments).
- No impact to state: provider configuration change only; resources remain bound to same subscription when value unchanged.
### 2025-09-24 (Infrastructure - Multi-region distribution)
- Removed single `location` variable in favor of required `locations` list.
- Implemented round-robin mapping of user index -> region `(i-1) % len(locations)` in root `main.tf` (`user_location_map`).
- Updated `config.auto.tfvars` sample to include two regions and documentation in Terraform README (variables table + new Region Distribution section with example).
- Validation enforces at least one non-empty region; changing assigned region for existing index forces full environment recreation (expected behavior noted in docs).
### 2025-09-24 (Infrastructure - Revert VNet race mitigation change)
- Reverted two-phase VNet + separate subnet resources back to original single azapi VNet resource with inline subnet definitions.
- Reason: separate subnet resources introduced update/idempotency complications; opting to keep simpler inline model despite occasional transient 404 previously under investigation.
- NIC subnet reference restored to string interpolation form (`.../subnets/vms`).

### 2026-08-18 (Rewrite - product gates and contract foundation)
- Created the `rewrite-integration` branch from commit `93887ab` and retained `docs/RewritePlan.md` as the implementation source of truth.
- Verified the selected workshop subscription permits modern ARM resources. Its deny policy targets only classic resource types; the signed-in facilitator has subscription Owner access.
- Confirmed `Microsoft.App/agents` is registered for Azure SRE Agent, Sweden Central is supported, and the subscription has 100 regional vCPUs available there.
- With facilitator approval, enabled the Defender CSPM `ServerlessContainers` component while preserving all other Defender extensions. Initial posture results can take up to 24 hours.
- Pinned the Windows 11 Enterprise `26100.7456.251206` workshop matrix in `workshop/toolchain.lock.json`: .NET runtime 8.0.30/SDK 8.0.424 through runtime 10.0.11/SDK 10.0.400; Microsoft OpenJDK 17.0.20+8/Spring Boot 3.5.16 through OpenJDK 21.0.12/Spring Boot 4.0.7; Maven 3.9.16/Wrapper 3.3.4; VS Code 1.133.0; Azure CLI 2.80.0; `uv` 0.8.22; exact installer hashes, container digests, and Copilot modernization/tooling extension versions.
- Added versioned schemas for catalog seed data, the seed manifest, modernization handoff, and acceptance evidence.
- Froze lowercase UUID identity, `<productId>.png` storage keys, Unicode-aware category slug normalization, case-insensitive name-only search, route/status behavior, transactional insert-new import, bounded performance work, health/readiness semantics, configuration names, and telemetry resource names in `workshop/contracts/`.
- Added `data/manifest.json` for the verified corpus: 198 figures, 20 categories, 198 images, 323,011,386 image bytes, source-file hashes, deterministic image-set hash, and per-category counts.
- Added sanitized valid/invalid fixtures, including valid Unicode punctuation, without copying production credentials or deployment data.
- Added the Python 3.12/uv/Pydantic/pytest acceptance harness. Its exact ordered 22-check full profile verifies the complete rendered and API result sets, all image bytes and MIME types, path traversal rejection, transactional import behavior, dependency failures, bounded performance behavior, and protected cleanup. Native `sqlcmd` and `psql` verification compares complete rows, schema, constraints, indexes, migration history, and TLS state rather than counts alone.
- Bound modernization handoffs to the canonical manifest, release commit/image/revision, managed resource IDs, parsed TRX/JUnit runtime tests, parsed telemetry query results, non-empty mechanism-appropriate IaC, and rollback evidence.
- Contract validation passes 20 tests with one optional live-environment skip. The offline `uv` lock check and both module entry points pass, the full acceptance command fails closed without required live inputs, and the focused contract/decomposition review approved the frozen foundation.

### 2026-08-18 (Rewrite - .NET/SQL Server vertical slice)
- Rebuilt the existing .NET 8 Blazor Server baseline around the frozen contract while retaining its catalog visual experience and SQL Server monolith boundary.
- Replaced the string identity and `EnsureCreated` schema with canonical `Guid` identity and EF migration `202608180001_ContractBaseline`, including exact named keys, constraints, indexes, lengths, timestamp types, and migration history.
- Standardized non-secret `CATALOG_*`, `PERFTEST_*`, and OpenTelemetry configuration; removed committed/default API and database secrets; added bounded startup validation and secure Azure SQL connection behavior.
- Consolidated `/import` into one route with a Blazor upload form and JSON POST endpoint. Imports now validate the complete schema and Unicode slug rules before one transaction publishes new categories and figures; duplicate IDs are skipped deterministically.
- Added stable HTML identity attributes, canonical UUID ordering, case-insensitive name-only search, slug/display-name category filtering, direct detail 404 behavior, byte-exact safe image serving, process liveness, database/import readiness, and bounded SQL Server performance work with controlled 401/503/504 JSON responses.
- Added standard resource identity, custom catalog spans, metrics, and structured logs on OpenTelemetry 1.17.0 after removing vulnerable 1.12.0 packages. The standard database operation histogram records seconds as required by the OpenTelemetry semantic convention.
- Added a .NET contract test project with exact TRX test names for health outages, import failure, performance dependency/timeout behavior, API keys, work-factor bounds, cross-runtime normalization/identity vectors, image security, and telemetry names.
- Live SQL Server CU26 validation exposed engine-specific UUID ordering and check-expression canonicalization assumptions. The shared verifier now sorts normalized rows and the SQL Server constraint contract records the actual metadata form; downstream work remained stopped while the foundation was corrected.
- Live PostgreSQL 18 validation exposed its new catalog representation of `NOT NULL` constraints as information-schema `CHECK` rows. Nullability remains verified from column metadata, while the constraint verifier now selects only true `pg_constraint.contype='c'` checks; the pinned PostgreSQL 18.6 image matches the unchanged seven-row explicit constraint contract.
- The baseline migration deliberately targets a fresh database. Pre-rewrite `EnsureCreated` databases use incompatible string identity and have no migration history, so replacing them requires an explicit facilitator-approved backup/recreate/reseed rather than an unrequested compatibility adapter.
- The pinned .NET 8.0.424 build passes with no warnings, 21 native tests pass, the resolved dependency graph has no known vulnerable packages, and the full shared profile passes all 22 checks against 198 figures, 20 categories, 198 byte-verified images, transactional import/reset, and native SQL Server schema evidence. A controlled SQL outage leaves liveness healthy, returns the exact readiness and performance 503 bodies, and recovers readiness after restart.

### 2026-08-18 (Rewrite - Java/PostgreSQL baseline)
- Added one intentionally monolithic Spring Boot 3.5.16 application for Microsoft OpenJDK 17 with Thymeleaf UI, PostgreSQL persistence, Flyway migration `V1__contract_baseline.sql`, JPA schema validation, safe local images, bounded authenticated performance work, and independent liveness/readiness.
- Imports use token-exact JSON parsing to reject malformed roots, values, duplicate fields or product IDs, trailing content, and normalization failures before one transaction publishes new categories and figures. Startup and upload imports share the same validated producer path.
- Tomcat passes encoded separators to the application only so a highest-precedence original-target filter can return the frozen 404 response. The filter rejects raw, encoded, double-encoded, and normalized aliases before route dispatch, including aliases into existing health and performance routes.
- OpenTelemetry uses one auto-configured SDK and resource identity for traces, metrics, and logs. The production Logback bridge exports structured HTTP, database, import, query, performance, and distinct exception records through standard OTLP configuration.
- Pinned Maven Wrapper 3.3.4 to checksum-verified Maven 3.9.16 and overrode pgJDBC to fixed version 42.7.12 after vulnerability validation identified the managed 42.7.11 release.
- Coordinator integration validation passes 24 native tests, the executable JAR build, 20 shared contract tests with one optional live skip, and all 22 live checks against pinned PostgreSQL 18.6 with 198 figures, 20 categories, and 198 images. Seven malicious route aliases return 404, the exact outage responses and recovery pass, and Trivy reports no HIGH or CRITICAL findings.

### 2026-08-18 (Rewrite - cross-runtime contract refreeze)
- Stopped downstream work after cross-layer review found divergent edge behavior, then refroze the shared baseline before changing either producer.
- Category normalization now iterates Unicode scalars and removes all `Mn`, `Mc`, and `Me` marks. Stored text uses Unicode code-point minimums, UTF-16 code-unit database maxima, nonblank values, and a 64-character normalized slug maximum.
- Added cross-runtime text boundary vectors covering supplementary characters, every exact minimum and maximum, blank values, and NFKD slug expansion. Native evidence now requires exact normalization and text-validation conformance test names in addition to the ten health/performance tests.
- Tightened live acceptance for canonical lowercase detail IDs, literal `%` and `_` combined search, and exact raw request-target aliases into existing health and performance routes.
- Database evidence now excludes disabled, untrusted, unenforced, or unvalidated keys, constraints, and indexes. Telemetry evidence now carries exact metric units and measurements, one rejected unit per rejected document, and matched `/figure/{id}` route-template values with final status across traces, metrics, and logs.
- Shared validation passes 23 tests with one optional live-environment skip; the offline uv lock and diff checks pass. The focused contract/decomposition review approved the replanned producer obligations.

### 2026-08-18 (Rewrite - .NET refreeze compliance)
- Updated .NET slug normalization to iterate Unicode runes and remove `Mn`, `Mc`, and `Me` marks, then made import validation distinguish code-point minimums from UTF-16 storage maxima, reject blank/null members, and cap normalized slugs at 64 characters.
- Import telemetry now starts before parsing, records one rejected unit per rejected document, and reports query/performance durations in seconds. SQL Server search now escapes `%`, `_`, the escape character, and bracket syntax before `LIKE`.
- Added original-request-target rejection before routing so raw, encoded, and double-encoded aliases cannot normalize into health or performance routes. Canonical requests continue through the existing matched-route/final-status telemetry path.
- Added exact native normalization/text conformance evidence, supplementary-boundary cases, rejected-document metric assertions, route-template log assertions, and raw-target tests.
- Validation passes 32 native tests, Release publish, shared 23+1 optional skip, full SQL Server acceptance 22/22 over 198 figures/20 categories/198 images, exact outage/recovery, and a clean dependency vulnerability scan. Focused review approved the corrected slice.

### 2026-08-18 (Rewrite - Java refreeze compliance)
- Aligned Java with the refrozen Unicode scalar, UTF-16 storage, canonical UUID, literal search, seconds-based metric, matched-route, and one-rejected-document contracts without changing the shared interfaces.
- Moved import completion telemetry outside the proxied transaction so it emits only after commit. Parse, validation, persistence, and commit-time conflicts each emit exactly one rejected document and no false completion.
- Preserved committed HTTP response status across propagated failures while using 500 only when the response is still uncommitted. The SERVER span, duration metric, and structured request log now report the same actual wire status.
- Validation passes 29 native tests, executable JAR packaging, full PostgreSQL acceptance 22/22 over 198 figures/20 categories/198 images, exact outage/recovery, and a zero HIGH/CRITICAL Trivy scan.

### 2026-08-18 (Rewrite - baseline evidence finalization)
- Replanned the coupled baseline after definitive review found that display names alone could bind unrelated native tests, committed-response failures could report synthetic statuses, the live invalid import did not exercise empty-slug normalization, and exported counter aggregates were incorrectly required to equal one.
- Bumped the behavior and runtime-evidence contracts to `1.1.0`. Runtime evidence now binds all fourteen requirements to stack-specific class-qualified identities parsed from TRX test definitions or Surefire JUnit `classname` values.
- Added a mixed valid-prefix/empty-slug fixture and made the unchanged 22-check full profile prove HTTP 400 plus unchanged complete database state. Both native parsers consume the same fixture, and Java additionally verifies atomicity against PostgreSQL.
- Native SDK tests prove each rejected document adds exactly one counter unit, while handoff validation accepts only positive integral exported aggregates. HTTP telemetry now records the actual wire status: committed responses retain their status, and uncommitted propagated failures become 500.
- Final integrated validation passes 24 shared tests with one optional live skip and the offline lock, 32 .NET tests, 29 Java tests, real fully qualified TRX/Surefire evidence validation, both package/publish gates, both full live 22/22 profiles, exact outage/recovery for both databases, and clean .NET/Java vulnerability scans.

### 2026-08-18 (Rewrite - facilitator dual-VM provisioning)
- Replaced the single mutable workstation resource with independent keyed `dotnet` and `java` Windows Server 2025 VM, NIC, extension, managed identity, generated database password, and performance-key resources in every existing participant resource group. Bastion, VNet, VM subnet, NSG, NAT Gateway, and outbound public IP remain shared. Managed-identity role-assignment names derive from the current principal ID so VM replacement creates a new immutable assignment instead of attempting a forbidden principal update.
- Pinned the exact Windows Server image and default application commit from `workshop/toolchain.lock.json`. Source overrides require a lowercase full Git SHA and a reviewed archive SHA-256; the VM extension no longer downloads raw branch scripts because the local provisioner is embedded as custom data. The extension copies Azure's decoded `.bin` custom data to a `.ps1` path for Windows PowerShell 5.1, and a Terraform replacement trigger prevents invalid in-place custom-data updates when the provisioner changes.
- Consolidated legacy installer scripts into one idempotent stack-aware provisioner. It digest-checks every locked download, enforces declared Authenticode publishers, installs exact VS Code/Azure CLI/uv/Python and stack toolchains, uses generated protected credentials, publishes the matching application, and registers automatic startup tasks.
- Preserved SQL Server Express 2022 plus .NET SDK 8.0.424 on the dotnet VM and added PostgreSQL 18.6-1 plus Microsoft OpenJDK 17.0.20+8 on the java VM. The Java build invokes the frozen Maven Wrapper after seeding its cache from the lock-file Maven archive and SHA-512.
- Added fail-closed local smoke gates for `/healthz`, `/readyz`, a canonical lowercase UUID PNG, the 198-figure/20-category/198-image manifest, and native `sqlcmd` or `psql` row counts. Successful runs write stack-specific JSON markers; database creation, migration/import, source extraction, scheduled-task registration, and installer checks are restart-safe.
- Removed committed/default passwords and weak shared database values. Terraform generates database/performance values per participant and stack and sends them only through extension `protectedSettings`; facilitator passwords remain sensitive inputs. Documentation now calls out that all such values still reside in Terraform state.
- Added a facilitator quota/cost preflight that validates doubled regional, VM-family, VM-count, Premium-disk capacity and estimates both Windows VM and Premium OS-disk cost before the Terraform resource precondition can be acknowledged.
- Made required ACA/SRE Agent, ACR, Azure SQL, PostgreSQL, Monitor, and Defender registrations explicit and corrected the subscription-wide boundary to `prevent_destroy = true`, with state-detach guidance for participant cleanup.

### 2026-08-18 (Rewrite - facilitator provisioning state-machine hardening)
- Removed generated credentials from the Custom Script Extension process command. Each VM now receives an ACL-restricted custom-data payload that is persisted only under `C:\MicroHack\secrets`; the executable script is scrubbed and `CustomData.bin` is overwritten/removed after bootstrap. SQL Server and PostgreSQL installers consume protected response files, database clients use `SQLCMDPASSWORD`/`PGPASSWORD`, and password-changing SQL uses protected temporary input files removed in `finally`.
- Made source reuse fail closed: every run verifies the cached/downloaded immutable archive digest, extracts a fresh clean tree, validates frozen content, and swaps the source directory atomically rather than trusting `.source-commit`.
- Added an explicit stop phase before source/output mutation. It stops the matching scheduled task, identifies only the exact stack command line if a child remains, waits boundedly, then publishes/packages to staging and atomically swaps the completed application directory.
- Added native SQL Server/PostgreSQL readiness loops to the generated startup scripts so reboot startup fails visibly after five minutes instead of leaving a permanently unready one-shot application process.
- Required at least one uppercase, lowercase, numeric, and approved special character in every generated database password while preserving the existing 32-character per-stack secret boundary.

### 2026-08-18 (Rewrite - facilitator provisioning final hardening)
- Split VM custom data into a non-executable versioned data bundle. The secret-free encoded CSE bootstrap reads that bundle, writes an ACL-restricted payload and clean provisioner, clears the original custom-data file, and only then launches a new PowerShell process. The provisioner consumes only the protected payload file, so script-block logging never processes secret-bearing source.
- Disabled the exact stack task before stopping it so a Ready task between retries cannot relaunch during mutation. Re-registration explicitly enables the task before start.
- Replaced command-line substring matching with Windows `CommandLineToArgvW` tokenization. Only the generated dotnet DLL argument or the Java `-jar` plus exact JAR argument qualifies for exact-PID termination.
- Made staged output swaps recover an interrupted `.previous` directory before cleanup and retain rollback until the new staged directory is installed successfully.
- Added a five-minute absolute startup deadline, native SQL login/query and PostgreSQL connect/statement timeouts, ten-second child-process ceilings, and exact-PID hung-client termination. Sanitized terminal failures are durably appended to the documented stack app log before Task Scheduler retries.
- Final review rejected embedding the full bootstrap as `-EncodedCommand`: its 14,330-character rendered command exceeded the Windows `cmd.exe` 8,191-character limit. The approved replanning keeps the maintained bootstrap file but embeds `base64gzip` bytes in a compact secret-free .NET decompression wrapper. Terraform constructs the entire CSE command in one local and enforces a 7,800-character precondition; both exact stack commands retain launch headroom.
- The VM replacement/extension force hash now covers the bootstrap digest, provisioner digest, custom-data format, and gzip transport version. No provider, resource, or download was added.

### 2026-08-19 (Rewrite - shared Azure target contract freeze)
- Approved the P4 preparation plan for a workshop-sized Sweden Central target using subscription-scope standalone Bicep and explicit `bootstrap` and `application` stages. Bootstrap has no placeholder Container App or mutable image; application requires a full commit tag and image digest.
- Reconciled the selected subscription policies with the target matrix. Azure SQL is Entra-only with workload managed identity, Blob is the policy-compatible default, and Azure Files remains an SMB compatibility mode whose live validation requires a shared-key exemption or another subscription.
- Bumped the modernization handoff to `1.1.0`. The handoff now requires application-stage Azure target output and a passing migration report; schema and validator checks bind stack, immutable release, resource IDs, database/image authentication, observability, migration history, corpus counts, and image hashes across those producers.
- Added strict target-output schemas/examples for clean bootstrap and complete application stages, plus SQL Server/SqlPackage and PostgreSQL/`pg_dump` migration-report schemas/examples.
- Froze the seven-command `catalog-migrate` interface, exact exit codes, environment-only secret handling, read-only source boundary, non-empty-target rejection, explicit target confirmation, and prohibition on resource deletion.
- Refroze the toolchain with repository-verified Azure SDK packages, SqlPackage `170.4.83`, and exact linux/amd64 manifest digests for .NET SDK 10.0.400, ASP.NET 10.0.11, and Microsoft OpenJDK 21.0.12+8. The Java JDBC path uses stable `azure-identity-extensions` rather than the older preview PostgreSQL provider.
- The contract-gate review corrected the Java artifact-to-hash mapping, bound every migration subcommand to exact arguments, secrets, and result schemas, added target-output-driven application principal provisioning, required both export/import tool versions from the lock, and validated every emitted Azure resource type and common scope. The handoff IaC path now points at the approved shared `infra/` root.
- The final contract/decomposition review exposed four remaining example-only assumptions. The executable contracts now require Sweden Central/Bicep/`infra`, derive PostgreSQL authentication and principals from target output with mode-specific secret rules, bind every operation result to its engine, artifact, tool version, and typed target, and prove ACA URLs plus commit-derived revisions belong to the declared Container App environment.
- A subsequent managed-identity feasibility review triggered replanning rather than another local workaround. PostgreSQL target output now separates the password restore administrator from the facilitator Entra administrator. Managed-identity import verifies the exact `$HOME/.azure-365` signed-in user, acquires only a transient `oss-rdbms` token, and creates the non-admin, non-MFA workload service principal via `pgaadauth_create_principal_with_oid` on `postgres`. The handoff now freezes `sqlpackage-bacpac`/`170.4.83` or `pg-dump-restore`/`18.6` and validates that provenance against migration evidence.
- The first P4 implementation child correctly stopped before editing when the container lock contradicted the target runtimes. The coordinator replaced the source-runtime application image entries with registry-verified target images: .NET SDK 10.0.400, ASP.NET 10.0.11, and Microsoft OpenJDK 21.0.12+8. Each linux/amd64 digest was labeled, pulled by digest, and executed to prove its reported runtime before the contract was refrozen. The focused contract-correction review found no substantive issue in the exact lock, schema, or executable acceptance mapping.
- The cohesive P4 implementation commit was not integrated after the mandatory coordinator review found producer/consumer failures despite two child corrective rounds. Replanning froze the user-selected connectivity model: execute `catalog-migrate` on each existing P3 source VM, create bidirectional peering to the target VNet, and link all target private DNS zones to the source VNet without public data endpoints. The corrective contract also restores bootstrap-before-application sequencing, requires exact resource relationships and database contracts, hashes downloaded target image bytes, isolates every child-process secret, emits JSON for all CLI failures, verifies the ACR commit tag against its digest, and requires a distinct retained healthy rollback revision. Because ACA's managed Application Insights destination officially rejects metrics, the target telemetry path now uses locked direct Azure Monitor OpenTelemetry exporters for traces, metrics, and logs while preserving local OTLP export.
- Refroze target output at `1.2.0`, migration report at `1.1.0`, and the migration CLI and toolchain lock at `1.2.0`. Target output now carries the exact source VM/VNet, bidirectional peerings, private-DNS links, and an explicit baseline/release application revision role; migration evidence records the same execution path and the handoff validator requires it to match the release target.
- Defined the minimal first-deployment rollback boundary: deploy the verified immutable image once as a healthy deterministic baseline revision and again as the release revision, retain the baseline, and accept only release output plus that distinct healthy baseline during handoff rendering. This introduces no second artifact or generalized rollback protocol.
- Added a typed migration error schema with stable exit-code mappings, one-line redacted messages, no extra traceback fields, and contract tests for malformed failures. Azure release verification now binds every CLI call to the target subscription, and toolchain integrity now includes direct Azure Monitor exporters for all three telemetry signals.
- The focused refreeze review closed four final producer/consumer gaps before commit. Migration now proves the current host through IMDS and records live subnet, reciprocal peering, and private-DNS-link observations; rollback verifies the deterministic baseline name and its digest-qualified image; Java locks OpenTelemetry core 1.58.0 with instrumentation 2.24.0-alpha to match Azure Monitor autoconfigure 1.6.0; and the breaking handoff semantics are versioned as `1.2.0`.

### 2026-08-19 (Rewrite - P4 migration transport and network refreeze)
- Executable SqlPackage inspection disproved the assumed `SQLPACKAGE_SOURCEPASSWORD` input, and the NuGet tool required a runtime newer than the P3 VM. Refroze the toolchain on the exact self-contained Windows SqlPackage 170.4.83.3 archive, SHA-256, and Microsoft publisher. The .NET source VM now installs and verifies that archive without adding another runtime.
- Refroze SQL export password transport as an ACL-restricted transient response file. Its value originates only in the declared migration environment, never appears in argv or the SqlPackage child environment, is overwritten and removed in `finally`, and child failures redact complete secret values before one-line truncation.
- Added transactional removal of the imported legacy SQL Server `catalog` user and `db_owner` membership before workload-identity creation, plus target verification that rejects any retained legacy principal.
- Added the required OAuth `--backup-intent` to Azure Files list, download, and upload commands while keeping Blob commands unchanged.
- Replaced the overlapping fixed `10.42.0.0/16` target network with stack-specific `172.20.0.0/16` (.NET) and `172.21.0.0/16` (Java) ranges, preserving deterministic subnet layouts and the frozen source-VM peering model.
- Corrective cross-layer review added local SQL Express certificate trust to SqlPackage export, bound migration-report commit identity to bootstrap output, changed PostgreSQL grant verification to require all eight table privileges independently, and made complete database verification reject unexpected application-schema tables.
- The second corrective review found that full acceptance still assumed SQL authentication for the Entra-only Azure SQL target. Acceptance settings, full database verification, import-state comparisons, and fixture cleanup now accept only `SQLCMDACCESS_TOKEN` with `sqlcmd -G` for managed Azure SQL while preserving password authentication for local SQL Server and PostgreSQL.
- Final integration gates pass after the refreeze: 85 acceptance tests with one expected live skip, offline lock validation, 35 .NET tests, pinned-Java-21 tests/package, Terraform and PowerShell validation, Bicep compilation and six read-only what-if scenarios, both linux/amd64 builds with zero HIGH/CRITICAL Trivy findings, and 22/22 disposable full checks for each stack. The separate final secret/destructive-boundary review found no substantive issue, and all disposable containers, images, network, volume, build output, caches, and generated package metadata were removed.

### 2026-08-19 (Rewrite - P5 path contract freeze)
- Froze one six-slice Challenge 1 registry for manual, bounded standard-Copilot rewrite, and GitHub Copilot modernization across .NET/SQL Server and Java/PostgreSQL. Every slice reuses the accepted P4 Bicep, Dockerfile, native database/image migration, full acceptance, telemetry, handoff, and rollback evidence instead of copying target implementation.
- Refroze the modernization path wording on the workshop-pinned `vscjava.migrate-java-to-azure` extension. Assessment and reviewed plan/task results are evidence; database schema/data transfer remains the explicit SqlPackage or pg_dump/pg_restore `catalog-migrate` step and is never attributed to the extension.
- The first focused P5 contract review found that handoffs could pair the manual path with Blob storage or a Copilot path with Azure Files. Modernization handoff `1.3.0` and migration CLI `1.3.0` now require an explicit path and repository rollback runbook, reject cross-path image-provider drift, and preserve the selected values in the schema-validated handoff.
- The final contract gate found that the unified modernization extension was still installed only on the Java P3 VM. Its current signed Marketplace package explicitly supports .NET and Java, so the exact locked extension is now common to both VM stacks; the existing stack-specific upgrade companions remain available without becoming part of the P5 handoff contract.
- Replaced the legacy single-stack Challenge 1 page with the shared six-combination selection/rejoin gate. Removed the obsolete `solutions/ch01` Dockerfile and public-network/password/mutable-tag Bicep reference so the three frozen path directories are the only active Challenge 1 solution surfaces.
- Manual-path integration required a coordinator replan after two corrective review rounds: the VM/database separation proof now treats the second terminal as a new security boundary, prompts for required values through `SecureString`, converts them only into process-local environment variables, and clears them immediately after acceptance.
- Standard-Copilot rewrite integration also crossed the two-round review boundary and moved to coordinator ownership. The refrozen workflow now validates protected target/source identity before transfer, drives `catalog-migrate` with one permitted secret set per command, uses the schema-defined top-level resource-group binding, and makes every bounded slice fail before commit on any native, contract, live-acceptance, or diff error.
- Copilot-modernization integration moved to coordinator ownership after its second review found that generated IDE and native-test evidence was omitted from the accepted commit. Both stack guides now stage every pre-identity evidence artifact; the .NET guide also gives its TRX a deterministic name before the clean-worktree source identity is recaptured.

### 2026-08-19 (Rewrite - P5 cross-layer protocol refreeze)
- Replanned P5 after integrated review found that transfer commands could consume stale source identity, handoff production could select incomplete evidence, and documentation workflows could preserve secrets or success-shaped artifacts after native failures.
- Bumped the migration CLI and modernization handoff to `1.4.0`. Every export, import, image copy, and verification operation now binds the lowercase full source commit to the selected target output. Handoff production and independent validation resolve one exact registered slice and require its canonical shared evidence, rollback runbook, and four ordered nonempty regular path-evidence files.
- Refroze all six path guides on fail-closed execution: each native command has an immediate exit guard, migration secrets exist only for their declared command, every location change unwinds in `finally`, standard-Copilot preflight fails on either independently pinned extension, and handoff render/validation failures cannot be masked.
- Acceptance now removes the exact prior report before native tests, token acquisition, or protected prompts and fails if removal cannot complete. Executable tests inject native, token, prompt, transfer, acceptance, render, and validation failures to prove no stale evidence, secret, or working-directory state survives.
- The focused integrated contract and P5 gate passes 87 tests; the full acceptance gate passes 132 tests with one expected live skip; the offline lock resolves 23 packages; and all 60 active P5 PowerShell fenced blocks parse with PowerShell 7.5.4. The final secret, path-containment, and destructive-boundary review found no substantive issue. No Azure operation or frozen deployment topology changed during this refreeze.

### 2026-08-20 (Rewrite - P6 shared challenge contract freeze)
- Froze one P6 registry that consumes modernization handoff `1.4.0` and assigns disjoint implementation ownership to load/autoscaling, CI/CD/revisions, and observability, including one pre-created focused acceptance file per stream. Each producer has exact student/solution paths, checked-in artifacts, an evidence schema/example, and a common machine-readable validation command.
- Added versioned Pydantic observation models and `catalog-validate-challenge-evidence`. The validator first executes the complete modernization-handoff validator, then schema-validates the selected P6 bundle, rejects empty or repository-escaping references and symlinks in every path component, and compares normalized observations to exact handoff resources, identities, attempts, and windows. The registry separately freezes coordinator-owned no-touch interfaces and three disjoint child file sets.
- Load evidence now requires a successful Azure Load Testing result with zero failed requests, the exact load resource and handoff URL/revision, SHA-256-bound YAML/JMeter inputs, explicit baseline/load/recovery windows, measured ACA `Replicas` scale-out above baseline within the configured 1-3 bounds, the handoff database's exact `app_cpu_billed`/`Total` or `cpu_percent`/`Maximum` signal above baseline, and exact health/readiness recovery URLs.
- CI/CD evidence now records separate staging and production OIDC subjects on one observed user-assigned identity, both federated-credential resources with GitHub issuer/audience, and exact role assignments tied to the same principal. Build, candidate, smoke, approval, promotion, rollback, retained healthy revisions, and post-transition health/readiness observations bind one workflow run/attempt, the handoff stack/commit, the immutable image, and a commit-derived candidate revision. AcrPush remains limited to the handoff ACR and Container Apps Contributor to the handoff Container App.
- Observability evidence now binds the handoff telemetry report, Application Insights component, Log Analytics workspace, service identity, source commit, and revision. It requires an observed Container App `AllMetrics` diagnostic setting into the handoff workspace's `AzureMetricsV2` table before workbook deployment. A separate frozen query contract renders and hashes exact resource-, service-, version-, revision-, and time-bound KQL for real error rate, latency, database dependency failures, replica count, and first-request-per-instance cold-start evidence; query-specific models validate one typed row inside the declared window.
- Focused schema, ownership, validator, and negative-mutation tests prove unrelated resources/runs, changed load artifacts, self-attested scale-out, stack/commit/candidate divergence, role assignments for another principal, replayed workflow attempts, pre-approval promotion, stale report captures, arbitrary queries, zero-only or out-of-window results, and final/intermediate/top-level symlinks fail. No P6 Azure resource, workflow run, load test, role assignment, traffic state, or deployment changed during the freeze.
- The final re-review tightened five remaining provenance gaps: direct and nested P5 handoff references now receive component-wise symlink checks before the authoritative validator resolves them; load evidence includes a recent ARM observation of the exact ACA 1-3 replica rule named `http` with `concurrentRequests` 50; every CI observation inherits one immutable GitHub repository/workflow/head/ref/run/attempt identity plus its successful job windows; deployed workbook `serializedData` is hashed and parsed to require exactly the five frozen rendered queries while checked-in source hashes are verified; and cold-start KQL counts only instances whose first request for the exact commit and revision falls inside the evidence window.
- A subsequent final review triggered the mandatory greater-than-two-round replan, so the candidate remained uncommitted and fan-out stayed blocked. The refreeze now uses one provenance design rather than more local exceptions: every consumed directory tree is recursively symlink-audited before existing validators glob it; cloud observations require exact provider resource types; candidate and post-transition probes use separately derived health/readiness URLs; and deployed workbook parsing recursively covers grouped panels while validating `KqlItem/1.0`, Logs query type, Log Analytics workspace resource type, and the observed ARM `sourceId`.
- The replanned review then closed type and source-provenance edge cases without changing the design: workbook `queryType` requires an actual integer zero, every normalized numeric/boolean field uses Pydantic strict types, and regressions reject `false` as query type, `true` as a replica/query value, and `1` as an enabled flag. The registry schema now fixes each challenge's complete ID/path/schema/example/output/CLI/test tuple rather than validating entries independently. The checked-in workbook template and deterministic `queries.kql` source are parsed against frozen query templates before the independently captured deployed workbook is accepted.
- The next freeze review found a producer/consumer divergence and two remaining false-success paths, triggering another coordinator replan rather than fan-out. P6 now consumes the authoritative P4 rule name `http` directly from `infra/modules/environment.bicep`; role-assignment observations prove their resource IDs are nested under the declared ACR or Container App scope; and JSON parsing plus every normalized Pydantic model reject `NaN`, `Infinity`, and `-Infinity`.
- The replanned focused gate passes 88 contract, provenance, strict-type, and challenge tests. Fan-out and commit remain blocked until this complete candidate receives the mandatory freeze review.
- That freeze review rejected five remaining shared-validator gaps, so the coordinator replanned again rather than distributing corrective work. Contract and query inputs are now bound to the checkout's exact recursively symlink-audited `workshop/contracts` tree; nested workbook JSON uses the same non-finite-number rejection as file JSON; each workbook panel rejects cross-component resources outside the handoff workspace; and declared load duration must equal the observed start/completion interval.
- CI identity evidence now records an unfiltered subscription-level principal assignment enumeration with `--all` and inherited roles included. The complete normalized result contains exactly two assignments, both for the workflow principal and both nested under the declared ACR or Container App scope; any broader inherited assignment fails.
- The corrected focused gate passes 94 tests. Commit and all three implementation children remain blocked pending a new approval from the single freeze reviewer.
- The first focused re-review confirmed those five corrections and found two final identity gaps. The refreeze now requires the workflow UAMI, ACR, and Container App to share the enumerated subscription and records immutable GitHub job IDs for staging and production in addition to names and windows.
- Negative regressions reject cross-subscription assignment evidence and same-name/same-window job replay under a different job ID. The focused gate now passes 96 tests; commit and fan-out remain blocked pending the corrective review verdict.
- The second corrective review found no substantive issue and approved the P6 contract and three-stream decomposition for freeze and fan-out. The exact schemas, models, examples, query templates, ownership boundaries, and executable gates are now the immutable implementation inputs.

### 2026-08-20 (Rewrite - P6 observability producer refreeze)
- Paused all P6 integration when focused review rejected the observability child: its cross-resource-group diagnostic-setting declaration would trigger BCP139, and the frozen replica query expected a revision dimension that the declared Azure Monitor producer cannot preserve.
- Refroze the truthful producer/consumer boundary from official Azure Monitor behavior. Container App `AllMetrics` diagnostic settings write flattened platform metrics to `AzureMetrics`; DCR metric export can preserve dimensions in `AzureMetricsV2`, but Container Apps is not a supported DCR metric-export source.
- Bumped the shared registry, observability query contract, observability evidence, and normalized observability observations to `1.1.0`. Load and CI/CD evidence remain `1.0.0`. The replica panel now selects the peak `Total` at the `Replicas` metric's `PT1M` grain, contains no revision placeholder or `Dimension` filter, and no longer inherits Challenge 2's per-revision maximum-of-three assertion. Focused review rejected the first `max(Maximum)` correction because it could report only the largest contributing revision; the exact query and regression now prohibit that substitution.
- Preserved revision-level proof where it is producible: the four Application Insights panels remain bound to service, source commit, revision, and window, while Challenge 2 remains authoritative for the exact revision's ARM scale rule and measured 1 -> at least 2 -> 1 behavior.
- Froze observability deployment at the handoff Container App resource group, already proven common to the handoff telemetry resources, so the implementation can use same-scope existing resources and a valid diagnostic-setting extension resource.
- Added regressions that reject `AzureMetricsV2`, `Dimension["revisionName"]`, and single-revision `Maximum` as substitutes for the diagnostic-setting replica query. The corrected contract and asset gate passes 96 tests; no child implementation was integrated and no Azure operation occurred during the refreeze.

### 2026-08-20 (Rewrite - P6 raw evidence protocol refreeze)
- Stopped P6 fan-out after focused load and CI/CD reviews exposed producer gaps rather than adding guide-only workarounds. Load evidence and normalized load observations now use `1.1.0`; CI/CD evidence and observations use `1.1.0`; the shared registry uses `1.2.0` while preserving the existing `loadSignals` consumer shape and placing new producer rules under `loadEvidenceProtocol`.
- Added a versioned raw load-capture manifest, sanitized Azure Load Testing, Container App, replica, Azure SQL, and PostgreSQL response fixtures, and the deterministic `catalog-render-load-evidence` producer. The producer enforces canonical non-overlapping paths, digest and symlink boundaries, strict JSON and frozen-schema validation, both database-family signal mappings, and one report plus five normalized observations. The common validator re-renders that bundle from raw captures and rejects manual normalized edits.
- Corrected load lifecycle truth: a one-replica point must precede the run, scale-out to two or three must occur during the observed 300-second run, and the final point must prove recovery to one afterward. Missing metric values, delayed scale-out, changed artifacts, and output/input collisions fail closed.
- Separated the CI workflow control commit from `handoff.source.commitSha`. Validation now hashes the exact handoff Git blob at `workflow.headSha`, while application checkout, image tag, digest resolution, and candidate suffix remain bound to the handoff source commit.
- Moved exhaustive role enumeration to a post-run facilitator session with Reader-equivalent assignment-read permission and the CLI-valid `--all --include-inherited` command without `--scope`. Raw Azure responses retain full role-definition ARM IDs, normalize only terminal GUIDs, and must contain exactly AcrPush at the ACR plus Container Apps Contributor at the app.
- Refroze GitHub ordering as staging completion, protected-environment approval, production job start, promotion, and rollback. Digest-bound raw revision lists establish each traffic state, and a shell rollback trap must be armed before promotion so failures cannot bypass restoration.
- The focused contract, asset, renderer, schema, and negative gate passes 117 tests. The full acceptance gate passes 222 tests with one expected live skip and one known stale observability scaffold; no base will be declared frozen until the observability owner returns a registry-`1.2.0` implementation commit and that full gate is green. No Azure or GitHub mutation occurred.
- The observability owner recreated the accepted implementation from the reviewed protocol commit and changed only its owned registry consumer to `1.2.0`; focused review found no substantive issue. Integrated observability keeps observability contract `1.1.0`, flattened `AzureMetrics` app-total semantics, same-resource-group Bicep, and the exact five deterministic panels. The integrated focused gate passes 112 tests, the full gate passes 228 tests with one expected live skip, the offline lock resolves 23 packages, and the Bicep compiler succeeds with only the repository-expected experimental-assert warning.
- Integrated the corrected load and CI/CD child commits after focused reviews found no substantive issues. The combined P6 gate reached 249 passing tests with one expected live skip; actionlint, offline lock validation, native load-asset parsing, and both Bicep compilers passed.
- The required integrated P6 review then found three producer/consumer defects and triggered another coordinator replan before P7: published commands mixed working-directory-relative paths with repository-root-relative CLIs, PostgreSQL `cpu_percent` was incorrectly bound to the handoff database child instead of its flexible-server parent, and missing `sliceId` could escape the renderer's JSON failure boundary.
- Refroze one path convention in which every P6 evidence, handoff, output, and contract argument is repository-root-relative and only `--repository-root ../..` depends on the documented `tests/acceptance` working directory. Both CLI entry points now resolve inputs once, and acceptance executes the exact published renderer and validator command strings.
- Kept the load evidence shape and version unchanged because registry `1.2.0` already declares PostgreSQL metrics at `Microsoft.DBforPostgreSQL/flexibleServers`. The renderer and common validator now derive that exact parent from the handoff's flexible-server database child, while Azure SQL remains database-scoped. A malformed handoff now fails through the JSON CLI boundary.
- Co-landed all six challenge/solution command corrections and the load PostgreSQL capture/test correction so no intermediate commit publishes an unusable CLI or failing consumer. The final corrective review found no substantive issue; the complete P6 gate passes 148 tests and the full acceptance suite passes 252 tests with one expected live skip.

### 2026-08-20 (Rewrite - P7 Defender foundation refreeze)
- Stopped Terraform and guide fan-out when contract review found that the selected migration VM did not prove Defender for Servers coverage for both retained .NET and Java VMs, and optional asynchronous Defender responses could not provide deterministic workshop evidence.
- Refroze `VirtualMachines` at subscription-enforced Standard/P2 and added one digest-bound ARM coverage envelope that derives the participant suffix from the handoff source VM and proves both retained sibling VMs exist with successful provisioning.
- Separated live query-attempt evidence from a mandatory pre-warmed seed snapshot. The seed snapshot uses distinct immutable artifacts, precedes current query evidence, covers both VMs, the Container App, ACR, and database with recommendations, and requires nonempty Secure Score, MCSB, image-assessment, and unhealthy-recommendation context.
- Extended cleanup restoration to preserve and independently verify each prior pricing `enforce` value in addition to tier, subplan, and extensions. The existing bounded Resource Graph inventory and post-restoration cost query remain unchanged.
- Added exact schemas, sanitized fixtures, deterministic report fields, and false-success tests for missing or substituted VMs, unenforced P2, incomplete or all-healthy seed evidence, empty required signals, chronology and artifact reuse, and failed `enforce` restoration. The focused P7 suite passes 54 tests and the P6/P7 contract compatibility gate passes 162 tests; implementation fan-out remains blocked pending the final freeze review.
- The first final freeze review found four remaining protocol gaps and triggered another coordinator replan: nested image/MCSB request paths were not preserved, inner seed queries could predate Defender enablement, equal timestamps could impersonate later cleanup verification, and argparse failures escaped the JSON CLI boundary.
- Refroze every Defender query on an exact `resourcePath`. The image producer uses the documented ACR assessment `c0b7cfc6-3172-465a-b378-53c7ff2cc0d5`; MCSB uses the exact `Microsoft-cloud-security-benchmark/regulatoryComplianceControls` path. Current and seed responses are bound back to those requested collection IDs.
- Seed query timestamps and the aggregate snapshot must now occur strictly after observed paid-plan enablement and in strict order before current query evidence. Completed cleanup, post-cleanup inventory, restored pricing, and Cost Management verification also require strict later timestamps.
- Replaced argparse text exits with a raising parser handled by the existing machine-readable failure boundary. New regressions cover wrong nested paths, wrong assessment/standard response IDs, pre-enablement inner seed evidence, every cleanup equality boundary, and invalid renderer/validator arguments. The corrected focused P7 suite passes 61 tests; fan-out remains blocked pending corrective review.
- Corrective review then rejected the attack-path producer: Defender exposes attack paths through Azure Resource Graph, not a direct `Microsoft.Security/attackPaths` GET. It also found that attack-path time was omitted from the seed/current chronology boundary.
- Replaced that producer with a dedicated digest-bound Resource Graph POST envelope at `Microsoft.ResourceGraph/resources` using API `2022-10-01`, one exact subscription list, the documented `securityresources` attack-path query, object-array output, complete count/total/truncation semantics, and direct response-ID/type/subscription binding. Empty results remain valid, but fabricated, paginated, incomplete, or cross-subscription results fail.
- Added attack paths to the strict current-query chronology and regressions for malformed KQL, wrong subscription selection, incomplete results, cross-subscription records, Resource Graph pagination/truncation shape, and attack-path evidence at the seed timestamp. The focused P7 suite now passes 67 tests; fan-out remains blocked pending another corrective freeze review.
- A subsequent freeze review found that the cleanup fixture could not be produced by its declared `Resources`/`PolicyResources` query: DCR associations belong to `InsightResources`, Defender pricings belong to `SecurityResources`, and Defender auto-provisioning/settings are exposed through dedicated ARM list APIs rather than supported ARG tables.
- Refroze cleanup as one digest-bound composite inventory. Its complete ARG response uses the exact Resource Graph endpoint and authoritative four-table/type mapping; exact subscription ARM GET envelopes capture `autoProvisioningSettings` at `2017-08-01-preview` and `settings` at `2021-06-01`. Every request is path/API/subscription/time bound, every list rejects pagination, and every returned ARM ID must belong to the requested collection.
- The bounded ARG projection now preserves `identity` and `location` with properties so policy-assignment state cannot change invisibly. The sanitized fixture exercises all seven resource types, including a non-null policy identity; regressions cover omitted or substituted producers, malformed list state, wrong response collections, pagination, chronology, and top-level identity drift. The focused P7 suite passes 74 tests, the full acceptance suite passes 326 tests with one expected live skip, and the corrective review declared the contract safe to freeze.

### 2026-08-20 (Rewrite - P7 Defender implementation)
- Integrated the facilitator Terraform foundation behind default-false paid-plan and explicit-authorization gates. It consumes the frozen pricing and budget contract directly, preserves participant resource-group Owner access, adds deterministic resource-group-only Security Reader access, and leaves the Serverless Containers switch as an Owner-only manual preflight.
- Added the Challenge 5 participant and solution guides for both retained VMs, both database families, deterministic pre-warmed examples, live query provenance, and the composite cleanup/restoration lifecycle. The solution captures ACR role assignments from the native ARM list endpoint at the exact ACR scope and principal instead of reshaping flattened Azure CLI output.
- The pre-review cross-layer gate passed 92 focused Defender tests and 344 full acceptance tests with one expected live-application skip. Terraform formatting and validation and the offline lock check also passed. No Azure plan/apply, Defender mutation, live query, cleanup, push, or other cloud operation occurred.
- The initial integrated safety review then found three false-success and teardown boundaries: the common renderer did not reject paginated role assignments, Terraform could issue an unsupported subscription-pricing DELETE, and paid pricing did not wait for a valid budget.
- Preserved the frozen Defender contract version because the published producer already required a complete role-assignment response. The common renderer now enforces that rule, subscription pricing is protected from destroy and detached only after authorized restoration, budget starts enforce Azure's current-month-through-twelve-month first-of-month window, and all paid pricing depends on successful budget creation.
- The corrected gate passes 94 focused Defender tests and 346 full acceptance tests with one expected live-application skip. Terraform formatting and validation, the offline lock check, diff checks, and the final corrective safety review pass.

### 2026-08-20 (Rewrite - P8 Azure SRE Agent contract replan)
- Froze the P8 boundary on `Microsoft.App/agents` and child connectors at `2026-01-01`, a dedicated agent resource group, dual identities, exact built-in and custom roles, and one Review-mode traffic rollback. Response-plan filters remain portal-owned because no documented ARM payload was available; OBO, autonomous execution, participant approval, secret/image changes, broad write roles, and generalized rollback are prohibited.
- The initial contract candidate added seven digest-bound source artifacts, deterministic rendering, independent validation, and sanitized examples, but the required freeze review rejected six false-success paths. Portal preflight was not independently source-bound, RBAC omitted its Resource Graph request body and inherited access, the Activity Log omitted the facilitator seed write, alert-to-agent causality was incomplete, cleanup did not prove facilitator authorization and workload survival, and P8 did not replay the complete P6 validators.
- Replanned the evidence protocol around one separate facilitator portal export bound to the exact agent Application Insights resource. RBAC now preserves the exact subscription-scoped Resource Graph POST and complete response plus inherited effective-access output. Incident evidence proves failure before alert, alert-bound audit correlation, review before facilitator approval, exactly the seed and UAMI writes, and raw Container App states that differ only in ingress traffic.
- Cleanup now binds authorization to the facilitator principal, verifies agent and dedicated resource-group deletion, proves both managed identities have no direct or inherited access, performs one successful ARM GET for every protected P5/P6 resource, and only then queries Cost Management. Independent P8 validation replays both shared P6 validators against the referenced CI/CD and observability evidence.
- The corrected sanitized artifact chain and canonical report are fully rehashed. Forty-eight focused false-success tests pass, and the P5-through-P8 contract gate passes 243 tests. Infrastructure and Challenge 6 guide implementation remain blocked until the mandatory corrective contract review approves this candidate.
- The mandatory corrective review found that the incident could still propose the frozen rollback without proving the plan-required investigation. The refrozen protocol now requires complete ACA deployment history, revision- and source-bound request failures and exceptions, SqlClient or JDBC dependency failures, and selected-database availability before the AgentResponse. The response and final assessment must reproduce an evidence-supported hypothesis, two rejected alternatives, blast radius, and verification plan for either .NET/Azure SQL or Java/PostgreSQL.
- A final chronology review found that the first investigation capture could share the audit-snapshot timestamp. The validator now requires the investigation to start strictly after the alert-bound `IncidentActivitySnapshot`, with an equality-boundary regression. The approved freeze passes 59 focused P8 tests, 276 expanded P5-through-P8 tests, and 405 full acceptance tests with one expected live-application skip; P8 implementation may now consume these interfaces without reinterpretation.

### 2026-08-20 (Rewrite - P8 Azure SRE Agent vertical slice)
- Added a subscription-scoped SRE Agent Bicep entry point with small modules for existing handoff metadata, the dedicated agent foundation, and participant-scope RBAC. It consumes registry `1.1.0`, creates one isolated agent resource group, UAMI, workspace-based agent Application Insights, dual-identity `Microsoft.App/agents@2026-01-01`, and exactly two system-identity telemetry connectors.
- Applied the exact frozen role surface: three participant-resource-group reader roles for each managed identity, the UAMI-only subscription Monitoring Contributor exception, one custom role assignable at the participant resource group and assigned only at the exact Container App, and facilitator/participant SRE roles only at the agent. The response plan remains portal-owned; the template adds no Autonomous mode, OBO, broad write role, model/agent-space configuration, policy, DCR, script, or cleanup automation.
- Added the facilitator component guide, bounded runbook, Challenge 6 participant guide, and cross-stack solution. They cover native foundation/RBAC evidence, rejected Review-mode preflight, same-digest harmless bad revision, complete investigation, evidence-backed alternatives, facilitator approval, traffic-only recovery, exact audit/Activity Log producers, protected cleanup, and deterministic render/validation.
- Focused review found three producer/consumer defects: operational tags made the live agent GET differ from the exact frozen tag shape, and the preflight and incident audit examples referenced unrendered query variables. The agent now carries only its hidden Application Insights link, and both guides render every exact registry placeholder before querying the dedicated agent component. The corrective review approved the changes; 68 focused P8 tests and the Bicep build pass.
- The final integrated review exposed a real source-plan conflict and six remaining false-success or producer gaps. Official Azure SRE Agent documentation requires subscription Monitoring Contributor for Azure Monitor alert ingestion; with explicit coordinator approval, P8 now permits only that UAMI exception. Registry `1.1.0` also freezes the official Application Insights resource-query API `2018-04-20`. Incident capture `1.1.0` replaces hand-written recovery status with non-redirected curl transfer evidence, revision-list examples use the ARM producer, connectors are parent-bound, the retained database host is handoff-bound, and Cost Management rows derive the post-deletion billing result. The corrected focused contract and vertical gate passes 100 tests.
- Corrective integration review then exposed three producer/consumer failures that required a protocol refreeze rather than another guide patch: creating the drill revision inside the incident added an unaccounted Container App write, revision traffic evidence remained flattened instead of preserving native ARM nesting, and cleanup omitted the exact Cost Management body/native response envelope.
- Registry `1.2.0` now requires the drill revision to be created at zero traffic before `incidentStart`; only the facilitator traffic seed and approved UAMI rollback occur in-window. Incident capture `1.2.0` preserves request/response envelopes from `Microsoft.App/containerApps/revisions@2025-01-01` and reads `value[].properties.trafficWeight`. Cleanup capture `1.1.0` freezes the custom daily `UsageQuantity` query, Azure SRE Agent meter filter/grouping, native `properties.columns`/`properties.rows`, and null `properties.nextLink`.
- Sanitized fixtures, schemas, capture digests, the canonical report, guides, Bicep contract assertion, and false-success tests were regenerated together. The corrective contract review then found a missing zero-traffic creation assertion, a guide/validator Activity Log URL-encoding mismatch, missing before/after Container App envelopes, and an overstatement of Azure RBAC field-level isolation.
- The validator now proves the drill revision's creation snapshot had zero traffic; guides generate byte-for-byte Activity Log request evidence and timestamped native Container App envelopes. The plan and all safety guides explicitly state that exact-resource `containerApps/write` is not JSON-field-scoped and that Review-mode command inspection, facilitator approval, and before/after state comparison enforce traffic-only behavior without adding an executor service. The focused P8 gate passes 79 tests, the final corrective review reports no blocking finding, and the full acceptance gate passes 425 tests with one expected live-application skip. Bicep compilation, Bash/JSON validation, offline lock resolution, and diff checks also pass.

### 2026-08-21 (Rewrite - P9 reconciliation and local P10 validation)
- Added the missing Challenge 0 participant/solution pair. Its executable checks bind both pre-warmed stack markers to one facilitator-provided immutable commit, the frozen behavior contract, exact `198/20/198` corpus, stack-derived VM names, and one machine-readable selection. Exactly one active guide contains the approved deallocation command, and it can target only the validated unselected VM.
- Replaced the obsolete root and architecture documents with the two-baseline by three-path matrix, golden rejoin, required Challenge 0-6 sequence, optional Challenge 7 tracks, facilitator go/no-go matrix, current cross-stack Azure design, and contract-first troubleshooting workflow. Reconciled base infrastructure, shared target, .NET, Java, challenge, solution, and acceptance navigation; all active local guide links now resolve.
- Moved enterprise and innovation content to `ch07-*`. Enterprise now owns private networking, identity, Key Vault, WAF, customer-managed keys, policy, and governance without duplicating Challenge 5. Innovation now defines one grounded Azure AI Search/model contract with .NET and Java adapters, managed identity, citation validation, responsible-AI evaluation, and an optional React `assistant-ui` frontend.
- Removed the root duplicate `config.tfvars.example`, both obsolete challenge-local Bicep/workflow/documentation trees, and the unreferenced script that removed locks and every resource group in the current subscription. Authoritative deployment remains `infra/`; participant cleanup remains exact-state and protected-resource aware.
- Focused review corrected a wrong behavior-contract version, unbound stack-to-VM choices, stale actionable Bicep guides, an overbroad managed-identity statement, parallel deallocation shortcuts, fail-open token-only tests, and unbound VM source provenance. Reaching the review-round limit triggered a coordinator replan: P9 now treats deallocation as one canonical producer across every active guide and tests the complete command block plus repository-wide occurrence count.
- Local P10 validation passes: 7 focused P9 tests; 432 full acceptance tests with one expected live-application skip; 35 .NET tests; pinned OpenJDK 21 Maven test/package; Terraform formatting/init/validation; all authoritative Bicep and parameter builds; both GitHub workflows; six Challenge 0 PowerShell blocks; offline lock resolution; and diff checks. Both linux/amd64 images build as non-root and Trivy reports zero fixable HIGH/CRITICAL findings. High-confidence secret signatures are absent.
- The host exposed only a Java 8 JRE, so Java validation used the exact digest-pinned Microsoft OpenJDK 21 build image. Testcontainers then used Docker Desktop's documented sibling-container socket/host override; no dependency, source, or test behavior changed. Generated virtual environments, caches, Terraform initialization, native build output, Java target output, and temporary images were removed.
- Completed the read-only Azure deployment-plan preflight against the enabled default workshop subscription. All 11 Bicep files lint and compile with zero errors, and all six sanitized .NET/Java Blob/Azure Files scenarios return `Succeeded` from subscription validation and a complete create-only what-if.
- Inspected applicable policy assignments and the inherited `Block Azure RM Resource Creation` definition. That deny targets only classic resource types, the prepared target contains none, and every ARM validation/preview completed without a policy denial or exemption.
- Verified the exact RBAC surface through source review, 100 focused acceptance tests, built-in role-definition resolution, and the facilitator's existing subscription `Owner` prerequisite. Workload, migration, CI, participant, Defender, and SRE identities remain bound to the frozen scopes; the one subscription-wide SRE Monitoring Contributor assignment is the previously approved exception.
- Only Azure account, policy, role-definition/effective-access, template-validation, and what-if reads occurred. No deployment, VM power change, role assignment, paid-plan mutation, load run, GitHub workflow, SRE incident, traffic change, resource deletion, push, or other live mutation occurred. The disposable-subscription P10 matrix remains an explicit authorization gate.

### 2026-08-22 (Workshop experience pass - legacy baseline restored, participant narrative rebuilt)

- A five-dimension review of the delivered workshop (quality, didactics, selling power, delivery operability, and plan conformance) scored the repository 3-4 out of 10 on every dimension. All five reviews converged independently on the same root cause, so the corrective work began there rather than with the individual findings.
- **Root cause: the repository contained no legacy baseline.** The root guide promised participants start on .NET 8 and JDK 17, but `dotnet/` and `java/` at HEAD were already .NET 10, Spring Boot 4.0.7, and JDK 21 — the modernized target. The legacy code existed only at the pinned VM source commit, which was 37 commits stale and whose tree contains no `infra/`, no `catalog-migrate`, and only four of the twelve challenge folders. No single tree held both the legacy application and the workshop assets, so the central exercise could not be performed as written.
- The provisioned VMs confirmed the defect independently. `workshop/toolchain.lock.json` freezes `sourceSdk` 8.0.424 with `rollForward: disable` and `sourceRuntime` 17.0.20+8, so a participant VM could not build the tree that HEAD shipped. The lock was correct throughout; the application code had drifted away from it.
- **Architecture decision.** The workshop premise is that only legacy applications exist and participants perform the modernization themselves. New or finished code therefore belongs exclusively under `solutions/`. The modernized tree moved to `solutions/reference/`, and `dotnet/` and `java/` were restored to the legacy baseline from the pinned commit. Five contract-test path references were repointed to `solutions/reference/`, and the two moved stack guides had their relative links corrected for the added directory depth.
- The restoration made several previously false documents true without editing them: the architecture document's ".NET 8 + SQL Server 2022 VM" and "Java 17 + PostgreSQL 18" rows, and both Challenge 1 solution headers, now match the code they describe. No toolchain lock change was required.
- Because the modernized tree no longer sits at the paths participants build in, the Dockerfiles left with it. That is intentional: authoring the container image is the Challenge 1 exercise, not a file to copy.
- **Narrative rebuild.** The root guide previously opened with a facilitator go/no-go matrix and never stated what the workshop was for. It now opens with the business situation, the before/after target, and four measurable outcomes, followed by the path decision aid and chapter map; the go/no-go matrix is retained in full under a facilitator heading, because the repository gate asserts its presence. A wrap-up chapter was added to collect every chapter's measurement into one before/after scorecard, which no chapter previously did.
- The troubleshooting guide was reorganized around a symptom index, since it was previously navigable only by someone who already knew which layer had failed. It now also records that the participant VMs deliberately have neither `git` nor `docker`, and that the commit identity comes from `C:\MicroHack\source\.source-commit`.
- A stale package-proxy prefix on the shared gate command was removed from the root guide; the endpoint returns HTTP 401 and the suite resolves correctly without it.

### 2026-08-22 (Toolchain pass - Git pinned onto the VMs, image builds standardized on ACR)

- The experience review left one unresolved blocker: both GitHub Copilot Challenge 1 paths are built on a commit-per-accepted-change method, and acceptance assertions freeze `git add`, `git commit`, `git status --porcelain`, and `git rev-parse HEAD` — but the VM had no Git. Every affected guide papered over this by telling participants to "confirm with your facilitator how your table gets a Git-capable working copy", which named a prerequisite nobody owned and which no facilitator document explained how to provide. Two of the twelve chapters were therefore not runnable as written.
- **Decision: pin Git rather than remove the Git-based method.** The original objection to Git was never that participants do not need it; it was that adding it would introduce an unpinned installer outside the frozen lock. That argues for pinning it, exactly as VS Code, Azure CLI, uv, SqlPackage, and PostgreSQL already are. Git for Windows 2.55.0.windows.5 was added to `workshop/toolchain.lock.json`, with its SHA-256 verified by downloading the published installer and its Authenticode subject read out of the binary's certificate table rather than assumed — the signer is `Johannes Schindelin`, not Microsoft, so asserting the usual publisher would have failed on the VM.
- The provisioner installs it through the same verified-download, publisher-assertion, locked-installer, PATH, and verify-or-throw sequence as every other pinned tool.
- **A signed archive is not a repository, so installing Git alone would not have been enough.** The source arrives as a zip, so it carries no history and `git rev-parse HEAD` would still have failed. Provisioning now calls `Initialize-SourceRepository`, which runs `git init` in `C:\MicroHack\source` and makes one baseline commit.
- **This creates two distinct SHAs, and conflating them is the most likely support question of a delivery.** `git rev-parse HEAD` identifies the participant's own work and is what image tags, revisions, and handoffs bind to. `.source-commit` records which upstream archive was provisioned and is provenance only. A local commit cannot reproduce an upstream commit SHA, so these are unrelated values by construction. Every Challenge 1 guide now states the distinction where a participant will meet it, and the facilitator guide leads with it.
- That distinction exposed a real inconsistency in the manual path: its first terminal derived the identity from `.source-commit` while its second re-derived it with `git rev-parse HEAD`. While the tree had no history this was invisible; with a baseline commit the two terminals would have disagreed about which source was deployed. The first correction — making both terminals read the archive marker — was wrong and was reversed in the next pass; see the publish-bridge entry below for why.
- **Image builds standardized on `az acr build`.** The bounded-rewrite guides still used `docker buildx build`, `docker tag`, and `docker push`, which cannot run on a VM with no Docker daemon. They now build server-side in the registry. Because the registry does not exist until bootstrap, the build moved after it, and the container checkpoint that preceded it became a daemon-free check of the authored Dockerfile's non-root `USER` and `EXPOSE 8080` — failing before any Azure resource is created rather than after a remote build. The `docker build`/`docker push` steps in the two GitHub Actions workflows were deliberately left alone: those run on `ubuntu-latest`, where a daemon is present and the local build is correct.
- Two guards were added so this cannot silently regress: one binds the provisioner to the frozen Git pin, requiring the locked version, URL, hash, and publisher to appear in the script and requiring the repository initialization; the other parses the provisioner with the PowerShell parser, turning a syntax error from an opaque VM extension failure into a local test failure.
- A broken internal package-proxy prefix was removed from thirteen participant-facing command blocks across six files. The endpoint returns HTTP 401, so every one of those commands would have failed as printed.

### 2026-08-23 (Second review pass - least privilege, re-provisioning safety, and the publish bridge)

A second round of independent reviews scored the workshop 5-7 out of 10 across quality,
didactics, delivery, selling, and plan conformance. Four of the blockers they found were
regressions introduced by the previous pass, which is the strongest argument for keeping
the review adversarial rather than confirmatory.

- **Participants were being asked to deploy at subscription scope, which they cannot do.**
  `infra/main.bicep` was `targetScope = 'subscription'` and created the participant's
  resource group. The confirmed topology is the opposite: the facilitator provisions
  everything at T-1, each participant receives one resource group containing their two
  legacy VMs, and the participant is granted Owner on that resource group and nothing
  above it. The first Azure command of Challenge 1 would therefore have returned
  `AuthorizationFailed` for every participant simultaneously. The template is now
  `targetScope = 'resourceGroup'`, creates no resource group, and asserts that the
  `resourceGroupName` parameter matches the group it is deployed into, so a mismatched
  parameter file fails at compile time instead of producing resources in the wrong place.
  `baseInfra/terraform` already built exactly this topology, so the template was the only
  thing out of step. `infra/sre-agent.bicep` remains subscription-scoped on purpose: it
  defines a custom role, which cannot be scoped lower, and it is facilitator-only work.
- **The reversed manual-path decision.** The previous pass concluded that the manual path
  "changes no code and commits nothing". That was wrong: the manual path authors a
  Dockerfile, and Challenge 3's workflow checks the source out *from GitHub* at
  `handoff.source.commitSha` and builds `application-source/<stack>/Dockerfile`. A commit
  that exists only on the VM cannot satisfy that, and a local `git init` commit can never
  reproduce an upstream SHA. Every Challenge 1 path must therefore commit **and push** its
  work to the participant's own GitHub repository, and record `git rev-parse HEAD`. The
  acceptance assertion was inverted accordingly.
- **Nothing in the repository pushed anything to GitHub.** Searching `challenges/`,
  `solutions/`, and `docs/` for `git push` or `git remote` returned zero hits, so the chain
  from Challenge 1 to Challenge 3 was severed for all three paths, not just the manual one.
  The evidence file matters here too: the workflow reads `HANDOFF_FILE` from the committed
  control commit, so `evidence/` must stay tracked. Gitignoring it was proposed as a fix
  and rejected for that reason.
- **Re-provisioning silently destroyed participant work.** `Install-SourceArchive`
  unconditionally replaced `C:\MicroHack\source`. A facilitator re-running provisioning to
  fix one broken VM would have deleted the morning's commits on every other VM in the
  room. It now returns early when the tree is already a repository at the requested source
  commit, and the previous tree is kept rather than removed.
- **The provisioner installed a shell the guides depend on but never put it on PATH.** Only
  `Git\cmd` was added, so `bash`, `curl`, and the coreutils shipped with Git for Windows
  were unreachable; `jq` appeared nowhere in the lock at all despite being used in
  participant-facing commands. `Git\usr\bin` is now on the machine PATH and jq 1.7.1 is
  pinned. jq ships **unsigned** — established by parsing the PE security directory and
  finding an empty certificate table, not by assumption — so the lock schema gained a
  `windowsBinary` definition that pins by hash alone, rather than forcing a
  `signaturePublisher` that does not exist.
- `global.json` is written into the source tree after the baseline commit, so every
  participant on a .NET Copilot path began with a dirty worktree and failed the first
  `git status --porcelain` gate. It is now ignored.
- `baseInfra/terraform` defaulted `source_commit` to a stale pin whose tree lacks `infra/`
  and the workshop tooling. A facilitator who forgot the variable would have provisioned a
  room full of quietly wrong VMs. The default is removed and that specific commit is
  rejected by a validation rule, so the failure is loud and immediate.
- `infra/perf-testing.bicep` required a workflow identity principal that does not exist
  until Challenge 3, while Challenge 2 needs the template — a dependency cycle introduced
  by the previous pass. The parameter now defaults to empty and the two workflow role
  assignments are conditional.
- Git Credential Manager is now installed with Git, so the first `git push` authenticates
  through a browser sign-in instead of stranding participants at a credential prompt.
- **Guards, so these cannot regress quietly.** New assertions bind the legacy trees to the
  frozen lock (derived from `toolchain.lock.json` rather than hard-coded, so the guard
  cannot drift from the pin it protects), require jq and Git Bash on PATH, require
  `global.json` to be ignored, require the stale-archive and re-provisioning guards, and
  require terraform to demand an explicit `source_commit`. The legacy-tree guard was
  negative-tested by flipping the target framework and confirming the failure before
  reverting.
- **The rejoin path named a directory that did not exist.** The day-of checklist pointed
  facilitators at `workshop/golden/<stack>/modernization-contract.json`, and
  `workshop/golden/` was nowhere in the repository. `workshop/golden/` now exists with a
  guide that states plainly why a working golden handoff cannot be checked in — every
  field is a live Azure resource ID, an image digest, or a commit SHA, so a committed one
  is either a fabrication that fails validation or a pointer at deleted resources — and
  gives the T-4 budget, the build procedure, the exact `handoff_cli` command that must
  exit `0`, and the requirement to keep the facilitator environment alive until the
  workshop ends. The rendered contracts are gitignored because they are delivery-specific.
- **A repository-wide link guard now exists.** The previous check covered `challenges/`,
  `solutions/`, and nine navigation documents, but not `docs/` or `workshop/` — which is
  precisely how the dangling `workshop/golden/` reference reached a facilitator checklist.
  Every relative Markdown link in the repository is now resolved, and the guard was
  negative-tested by introducing a broken link and confirming the failure.
- A companion guard asserts the participant template stays resource-group-scoped and that
  no document deploys `infra/main.bicep` at subscription scope, so the
  `AuthorizationFailed` failure mode cannot return quietly.
- **Challenge 6's recovery clock could not be computed.** The chapter handed participants
  a jq expression over `$DETECTED_AT` and `$RECOVERED_AT` without ever assigning either,
  so the workshop's headline MTTR number was unobtainable in the one chapter that claims
  to measure it. Task 6 now names the exact source of each timestamp — the
  `IncidentActivitySnapshot` audit row and the alert's
  `properties.essentials.resolvedDateTime` — and Task 7 assigns them behind `:?` guards.
  Verified by execution: filled it prints `minutesToRecovery: 13`, blank it names the
  missing value instead of printing a number nobody could defend.
- **The facilitator guide was 649 lines with no usable surface during delivery.** A
  108-line `docs/DayOfCard.md` now carries the pre-09:00 go/no-go, the clock with its two
  poll points, a checkpoint-to-artifact ladder built only from files shared by all three
  Challenge 1 paths, and the cut levers. It also records that the manual path writes no
  shared evidence between steps 4 and 9, so at 14:45 the facilitator asks which step
  someone is on rather than reading a directory that cannot have changed.
- The guide now opens with who holds which rights and when: the facilitator is subscription
  Owner from T-15 through T-1 and teardown, participants hold Owner on one resource group
  and nothing above it, and every subscription-scope action completes before anyone
  arrives. That section exists because the previous text implied participants needed the
  same rights the facilitator does, which is how a room of twenty ends up with twenty
  subscription Owners.
- **The publish bridge.** All six runbooks and all four Challenge 1 chapters now commit,
  set `origin` idempotently, and `git push --set-upstream origin workshop` before any
  identity is recorded, and `$SourceCommit` is read *after* the push so it is provably a
  commit that exists on GitHub. The `workshop` branch is not invented by the guides: the
  provisioner already creates it with `git init --initial-branch=workshop`, so the push
  target and the local branch agree by construction.
- The handoff needs a **second** commit, and this is a constraint rather than a
  preference: the workflow asserts `GITHUB_SHA != SOURCE_COMMIT` and requires the source
  commit to be an ancestor of the control commit. Each runbook therefore pushes the source,
  then records the handoff and pushes that as a later commit, after transient cleanup so
  nothing temporary ships.
- Publishing exposed a latent defect worth recording: `evidence\*.trx` is matched by
  `*.trx` in `.gitignore`, so the single `git add --` in the modernization runbooks errored
  and staged nothing. It is now a plain add plus an explicit `git add --force` for the
  test-results file that the clean-tree gate depends on.
- **A prerequisite that no facilitator document owned.** Every runbook asks for a
  "facilitator-provided HTTPS URL", and nothing in the facilitator guide or the day-of card
  said to provide one. Both now carry it, together with a T-1 instruction to perform a real
  test push from a provisioned VM — which is the only way to discover before the room
  arrives that Git Credential Manager's browser sign-in is reachable and that organization
  SSO or device policy does not block it. A guard asserts the participant text and the
  facilitator text stay in agreement, and specifically rejects the previous claim that work
  reaches GitHub "not from the VM", which the bridge made false.

### Round 4 — protected parameters, and the CI runtime the pipeline never declared

- **The protected parameter files had no producer.** All six Challenge 1 runbooks deploy
  with `--parameters '@C:\protected\<path>-<stack>-<stage>.json'`, and nothing anywhere
  created that file — Challenge 1 could not start on any path. The provisioner now writes
  the nine files at T-1, because the three values the template hard-asserts
  (`resourceGroupName`, `performanceApiKey`, `facilitatorPrincipalObjectId`) are all
  facilitator-time facts that no participant can supply.
- **`sourceCommit` and `imageDigest` are deliberately absent from those files.** They are
  passed by the participant as `--parameters key=value` overrides after the file. Writing a
  placeholder that satisfied the template's format assert would let a forgotten override
  deploy the wrong source *silently*; omitting them makes the same mistake fail loudly at
  deploy time. This is not a workaround — `az deployment group create --help` states that
  "parameters are evaluated in order" and explicitly recommends supplying the parameters
  file first and then overriding selectively with `KEY=VALUE`. Note the same help warns
  that a `.bicepparam` file permits `--parameters` only once; the runbooks use ARM JSON, so
  the pattern is available to them. `infra/parameters/*.bicepparam` remain
  facilitator-facing examples and are not used by any participant command.
- **CI declared one .NET runtime but has to serve two.** `catalog-dotnet.yml` requested
  only SDK `10.0.400`, the modernized target. But the handoff contract's `runtimeVersion`
  and `frameworkVersion` are free-form strings describing the *source*, and no contract
  field pins a target framework — so only the copilot-modernization path retargets to
  `net10.0`, while the manual and copilot-rewrite paths legitimately hand off `net8.0`.
  The job passed only because the hosted runner happens to preinstall `8.0.424` too. It now
  declares both SDKs, each still exactly pinned.
- This was verified by reproducing the failure rather than reasoning about it: running the
  `net8.0` suite with only a newer ASP.NET Core runtime present aborts with "You must
  install or update .NET to run this application", and forcing roll-forward instead
  produces seven `PipeWriter … does not implement PipeWriter.UnflushedBytes` errors with
  **zero** assertion failures — a version-pairing artifact, not an application defect. Both
  symptoms are recorded in `docs/CommonErrors.md`.
- A first attempt at this fix was wrong and was reverted: pinning CI *down* to the VM's
  `8.0.424` looked like consistency but would have broken the modernization path, whose
  runbook states an accepted target of .NET `10.0.11`/SDK `10.0.400` and builds from
  `mcr.microsoft.com/dotnet/sdk:10.0.400`. The lock file distinguishes `sourceSdk` from
  `targetSdk` precisely because both are real. Java needs no equivalent change: Maven
  builds with `maven.compiler.release=17` run correctly on the pinned JDK 21.
- **The shell changes at Challenge 2 and nothing said so.** Challenge 1 puts the
  participant in PowerShell; Challenges 2–6 are bash. Unstated, that is expensive rather
  than cosmetic, because PowerShell aliases `curl` to `Invoke-WebRequest`, so a block
  ending in `curl -s … | jq` fails as if the *application* were broken. Every chapter with
  a bash block now states where it runs, and a guard rejects a bash-continuation block in
  any chapter that mandates PowerShell — the handoff validation command in Challenge 1,
  which all three paths must run, was exactly that.

- **`C:\protected` was unreadable by the participant who has to read it.** Introducing the
  parameter-file producer created a second-order defect the producing agent flagged but did
  not own. The folder reuses `Set-ProtectedAcl`, which disables inheritance and grants only
  SYSTEM and Administrators. The VM's admin account is *custom* — `admin_username` defaults
  to `azureuser` and the variable explicitly forbids reserved names — so it is not the
  RID-500 Administrator that Windows Server exempts from Admin Approval Mode. UAC therefore
  hands an ordinary PowerShell a filtered token, and the first
  `az deployment group create --parameters '@C:\protected\…json'` of Challenge 1 dies on
  `Access is denied`. Only `docs/Facilitator.md` mentioned elevation; no participant
  document did, and the participant works in VS Code's integrated terminal, which is not
  elevated.

  Fixed by granting the admin account **Read** on `C:\protected` and its nine files, via a
  new opt-in `-ReadPrincipal` parameter threaded through `Set-ProtectedAcl`,
  `Save-ProtectedText` and `Save-ProtectedConfiguration`. The account name travels from
  terraform as a validated `adminUsername` payload field rather than being guessed from
  `$env:USERNAME`, which would resolve to SYSTEM at provisioning time. This grants no
  capability the participant lacked — a local administrator can elevate and read the folder
  anyway — it only removes a UAC papercut from the middle of the first challenge.

  Two deliberate boundaries. The grant is opt-in, so the database passwords under
  `C:\MicroHack\secrets` keep the administrators-only ACL; a guard asserts that
  `Set-ProtectedAcl -Path $SecretRoot` is called *without* `-ReadPrincipal`, so widening
  the helper's default would fail. And the ACE is skipped when the principal already has a
  grant, so a name colliding with a built-in cannot silently *downgrade* Administrators
  from FullControl to Read. The T-1 check in `docs/Facilitator.md` now runs **non-elevated**
  on purpose: verifying it from an elevated shell proves nothing about the session
  Challenge 1 actually deploys from.

- **A guard of mine broke for the right reason and was rewritten, not relaxed.**
  `test_challenge_path_registry_is_complete` asserted the app-modernization VS Code
  extension was installed for both stacks by splitting the provisioner on the *first*
  `if ($Stack -eq 'dotnet')` and searching the prefix. The parameter-file producer added an
  earlier, unrelated `$TargetStack = if ($Stack -eq 'dotnet')`, moving the split boundary
  and failing a test whose invariant still held. The marker was a fragile proxy for "the
  unconditional extension list", so the guard now anchors on the `$Extensions = @{ … }`
  literal itself and additionally asserts the extension is *not* re-declared inside either
  arm of the branch. Both forms were mutation-tested: demoting the extension into the
  dotnet-only arm now fails the guard, which the old form would not have caught.

### Round 5 — closing the plateau

Round 4 scored 8/8/9/8/8, with three dimensions flat against round 3. A flat score is a
different signal from a low one: the remaining findings were not hard, they were simply
never picked up, so this round was about clearing the backlog rather than redesigning
anything.

- **The `sourceCommit` override finally reached the participant-facing chapters.** Round 4
  raised this as blocking, and it was: `--parameters sourceCommit=` appeared 8 times in
  `solutions/` and **0 times** in `challenges/`. The runbook a participant follows silently
  omitted the flag that pins a deployment to the commit it was built from, and
  `challenges/ch01-manual/README.md` actively claimed the opposite. All four Challenge 1
  chapters now pass the override, carry a symptom-table row for the mismatch, and route to
  a new entry in `docs/Troubleshooting.md`.

- **Bicep now compiles with zero warnings, and the one banner that remains is documented.**
  `infra/bicepconfig.json` enables the `assertions` experimental feature, which prints a
  banner on every build. The tempting fix — deleting the flag — would have broken three
  real `assert` statements in `infra/github-cicd.bicep` that validate resource-ID shapes.
  The flag is load-bearing, so it stays and `infra/README.md` now tells the reader the
  banner is expected rather than leaving them to wonder whether the build is broken.

- **`runs-on: ubuntu-latest` became `ubuntu-24.04`.** This had been open for four rounds. A
  workshop whose entire premise is that a pinned toolchain makes upgrades boring cannot
  itself float its CI runner.

- **A guard of mine was too narrow, and mutation testing is the only reason I know.**
  `test_acceptance_suite_blocks_are_self_contained` was written to catch code blocks that
  invoke the acceptance suite without first `cd`-ing into it. It matched on the literal
  `pytest` — but the suite is invoked through its seven console scripts far more often than
  through pytest, so deleting a `cd` from a `catalog-validate-challenge-evidence` block
  sailed straight past it.

  Widening it exposed two further wrong assumptions. The repo has **three** separate uv
  projects (`tests/acceptance`, `dataGenerator`, `baseInfra/github`), so "any block running
  `uv` must be in the suite" is false and produced 36 phantom offenders. And the guard only
  recognised `cd tests/acceptance`, while the PowerShell runbooks correctly use
  `cd tests\acceptance` or `Push-Location tests\acceptance`. The final guard reads the
  script names from `[project.scripts]` at test time so it cannot drift, accepts both path
  separators and both cwd idioms, and ignores non-executable fences such as `mermaid`.
  It then caught a genuine eleventh offender at `challenges/ch02/README.md`.

  The failure mode this protects against is worse than a confusing error message: because
  there are three uv projects, running a suite command from the repository root does not
  fail cleanly — uv resolves a *different* project and reports a missing script, which
  points the reader away from the actual mistake.

- **Six selling claims were corrected rather than defended.** The largest was an unsourced
  "a week per application" figure that implied a ~40x productivity multiple and had
  survived four rounds. `docs/Demo.md` was also showing the upgrade running *backwards*, to
  .NET 8, in a demo whose entire point is the move to .NET 10.

### Round 5b — the findings the critics could not have made

Round 5 came back 9/8/9/9/9. Rather than wait for round 6, I ran my own sweeps against
classes of defect nobody had checked, and the two most valuable findings of the round came
from there rather than from any report.

- **A template the workshop tells participants to deploy had no runnable command.**
  Comparing each `infra/*.bicep`'s required parameters against every `--template-file`
  invocation in the docs showed `github-cicd.bicep` was described in prose in
  `solutions/ch03/README.md` — *"Deploy `infra/github-cicd.bicep` at resource-group scope
  with the exact ACR and Container App resource IDs"* — and nowhere shown as a command. It
  was the only template in the repo in that state, and it asserts the shape of all three
  IDs it receives, so a reader's invented invocation fails at deploy time rather than at
  review time. The solution now reads the three values out of the validated handoff with
  `jq` instead of asking anyone to retype them.

  The same sweep found `infra/README.md`'s own what-if example omitting the required
  `sourceCommit`, so the command in the infrastructure README could not have run either.

- **Two of my own detectors were wrong before the repo was.** The first pass of the
  parameter sweep reported that both copilot-rewrite solutions deployed `main.bicep` six
  times without pinning `sourceCommit` — the exact class round 4 had called blocking. It
  was a false positive: those runbooks use the grouped `--parameters a=1 b=2` form, so the
  assignment is mid-line, and my line-anchored regex could not see it. A second false
  positive flagged `docs/Facilitator.md` for a block that is deliberately schematic. Both
  detectors were corrected before anything was changed. **The repository was right and I
  was wrong, twice, in the same sweep** — which is the argument for verifying a finding
  against the file before acting on it, including one's own.

- **Reference runbooks now run as printed.** Six `<placeholder>` values survived in the
  Java and .NET copilot paths, four of them at the database cutover — the least
  recoverable point in Challenge 1 — while the line directly above them read the password
  from the protected store. All six now derive from the same sources the clean manual path
  already used: `$env:CATALOG_DATABASE_*` for source connection fields, and
  `$ReleaseTarget.database.applicationPrincipal.name` for the post-migration verifier.

  Where a value is genuinely the reader's to choose — a rewrite slice name, a run ID — the
  block now uses the repository's existing `: "${VAR:?explanation}"` idiom so it fails with
  a sentence instead of a syntax error. The guard that enforces this permits exactly two
  kinds of placeholder: a value only the facilitator can know, and a secret the reader must
  choose. **Printing a literal secret would be the worse bug**, so the guard must not push
  anyone toward one.

- **The demo's closing beat now runs cold.** `docs/Demo.md`'s honesty table promised the
  scorecard step ran from checked-in data; it read three files from the empty `evidence/`
  directory and died on the first. Two fixtures were added under
  `workshop/contracts/fixtures/wrapup/`, built from the exact field shapes the Challenge 0
  and Challenge 6 producers emit, and the step now reproduces its four documented lines
  byte for byte. The guard asserts the printed figures still match the fixtures that
  produce them, and that the fixture's `minutesToRecovery` agrees with its own timestamps.

- **A fix of mine broke an existing test, for a good reason.** Replacing `<slice-name>`
  with a required variable broke `test_rewrite_slice_blocks_fail_before_commit`, which
  *executes* that block in a sandbox to prove it refuses to commit after a failure. The
  harness substituted the placeholder textually. The test was right to fail — it now
  supplies `SLICE_NAME` the way a participant would, and still proves the same property.

One process note. The delivery critic reported that the repository changed underneath its
round-5 review, and correctly withheld a flaky-test finding it had traced to my edits
rather than to the suite. Reviews from here run against a frozen tree.

## Round 6 — the phase vocabulary, and a regression I caused myself

Scores entering this round were quality 7, didactics 9, selling 10, delivery 9,
conformance 9. Quality had *dropped two points*, and the cause was a fix of mine.

- **`$env:CATALOG_*` never existed in a participant's shell.** Round 5 added runbook steps
  that read `$env:CATALOG_DATABASE_HOST` and friends. Those assignments live inside the
  here-string that becomes the application's scheduled-task start script, so they are
  process-scope for the app and invisible to every other session. Ninety-six reads across
  the runbooks were reading nothing. `Set-CatalogEnvironmentForParticipants` now persists
  the non-secret values at Machine scope immediately before the task is registered, for
  both stacks, with the database password deliberately excluded. This also closed a latent
  bug in `solutions/ch01-manual/dotnet/README.md`, which read a variable it never set.

- **Two of my own verification tools were lying to me.** The PowerShell parse check passed
  a `[ref]` to an undeclared variable, threw, and printed `PARSE OK` regardless. The
  provisioner write-detector matched `-Path` *inside* `Join-Path`, so it resolved the wrong
  file. Both were corrected before the findings they produced were trusted. A guard that
  cannot fail is worse than no guard, because it is counted as evidence.

- **Unbound shell variables in three deployment blocks.** The delivery critic found one
  `$GITHUB_REPOSITORY` with nothing behind it. Generalising the check to *every* expansion
  in a deployment block found nine more, including a block in `solutions/ch02/README.md`
  whose own prose claimed it had guards it did not have.

- **Build-phase codes were reader-visible everywhere.** `P5`, `P6`, `P8` name the order
  this repository was built in and mean nothing to a participant. They had reached fifteen
  test filenames, the contract guides, Bicep parameter descriptions, and — worst — the
  error strings the evidence validators print at a participant. All are now named by
  challenge or component. The guard that keeps them out has to be careful: Azure ships
  real identifiers of the same shape, so Defender for Servers Plan 2 and the Premium SSD
  disk tiers are allowed *per file and per token*, and a genuine phase code in one of those
  same files still fails.

- **The golden-handoff validation command could never have exited `0`.** The validator
  resolves evidence relative to `--repository-root`, and the path registry requires the
  contract at `evidence/modernization-contract.json`. `workshop/golden/README.md` pointed
  the root at this repository, which made the path `workshop/golden/…` and matched no
  slice. A golden bundle is its own validation root. `.gitignore` had already anticipated
  the correct layout; the documented command had not. `golden-dryrun` now walks the same
  checks in T-4 order and stops at the first defect instead of emitting a schema error set.

- **An agent corrected my citation, and was right.** The Defender seeding work was
  dispatched against `docs/RewritePlan.md:607-643`, which is the SRE Agent section. The
  Defender requirements are at 572–603. The agent implemented the correct section and said
  so rather than building what it was told.

- **The SRE response plan stays out of Bicep, with evidence.** No ARM resource type exists:
  the published spec has four PUT-able paths and none is a response plan, and the Bicep
  type index rejects every candidate name with `BCP081`. The repository's own contract had
  already recorded `responsePlanConfiguredInIaC: false`, and the acceptance suite asserts
  it. The template now carries the citations rather than the appearance of an omission.

- **Least privilege, once more.** `backend.hcl.example` asked for Storage Blob Data *Owner*
  where the facilitator command grants *Contributor*. Contributor already covers the blob
  leases Terraform uses for state locking; Owner only adds RBAC management. The example was
  the outlier.

- **The .NET app validated three settings by defaulting them.** `CatalogRuntimeOptions`
  read `DEPLOYMENT_ENVIRONMENT`, `OTEL_SERVICE_VERSION` and `CONTAINER_APP_REVISION` with
  `?? "lab"`, `?? "1.0.0"` and `?? "local"`. A misconfigured deployment therefore started
  and lied about which environment and which revision it was, which is precisely the
  signal the observability challenge depends on. All three are now required, matching the
  Java implementation that already used `require(...)`. The test fixtures that this broke
  were repaired by supplying the values, not by restoring the fallbacks.

- **Five behavior tests, mirrored into both trees.** The legacy and reference test suites
  were already byte-identical in six of eight files; the deltas are Azure-only exclusions,
  not a deliberately thinner legacy suite. So the new tests belong in both. They exercise
  the real repository, importer, DbContext and HTTP pipeline against in-memory SQLite —
  logic, not SQL Server's collation engine, and the code says so.

- **A guard that binds the two halves of the environment together.** Persisting `CATALOG_*`
  at Machine scope only helps if the values match what the application actually runs with.
  The new guard requires every key present in both places to agree, and requires the
  participant-facing `CATALOG_BASE_URL` to carry the same port the provisioner's own smoke
  test calls. Both halves were mutation-tested.

- **Committing the work exposed a guard that had been scanning half the repository.**
  `test_no_build_phase_codes_reach_a_reader` enumerated files with `git ls-files`, which
  lists the index. While the rewrite sat uncommitted, 121 files — the entire
  `solutions/reference/` tree among them — were invisible to it, and it reported green the
  whole time. The moment the tree was committed it failed immediately on `docs/CostEstimate.md`.
  A guard that only sees committed work is weakest exactly when the risk is highest, so it
  now lists untracked-but-not-ignored files too, and that widening was proved by planting a
  leak in an uncommitted file. The offending matches were genuine Azure identifiers —
  Premium SSD tier `P10`, Defender for Servers plans `P1` and `P2` — and were allowlisted
  per file and per token rather than by loosening the pattern.

- **Generated packaging metadata was tracked.** `.gitignore` covered `__pycache__/` but not
  `*.egg-info/`, so six files that `uv` rewrites on every editable install were committed.
  Each facilitator would have inherited a dirty working tree they did not cause. The
  directory is untracked, the ignore rule is in place, and a guard now fails if any
  generated Python metadata is tracked — it was verified against the live defect, failing
  before the fix and passing after.

## Round 7 — the phase-code guard was reading a sixth of the repository

Written after the fact, in round 8, because round 7 was fixed and never recorded. It is
reconstructed **only from what the tree can prove**, and the tree proves less than a
contemporaneous entry would have. `HEAD` is a single commit, `af03efe`, "harden the workshop
across six audit rounds": everything after round 6 is uncommitted working tree, so `git` can
separate round 7 from round 8 in *content* but not by *commit*. Where a fact was not
recoverable, it is absent rather than reconstructed — including the review scores, which no
artifact carries. What is below is diffable against `af03efe` today.

- **A guard whose docstring described a scope it did not have.** At the end of round 6,
  `test_no_build_phase_codes_reach_a_reader` listed its candidates with
  `git ls-files --cached --others --exclude-standard` followed by a six-extension pathspec:
  `*.md *.py *.json *.ps1 *.bicep *.tf`. That pathspec is the defect. Measured against
  today's tree, it lists **293 files where the unfiltered listing gives 737**, and of the 444
  it hides, **241 are readable text the guard never opened** — among them *every* `.java` and
  `.cs` file in the repository, plus the `.razor` and `.cshtml` views and the `.bicepparam`
  files. Round 6's own entry records that phase codes had leaked into "test filenames" and
  "the error strings the evidence validators print". Those are precisely the files the
  pathspec excluded. The guard reported green on the leak it was written to catch.

- **Two smaller faults in the same six lines.** The listing was split with `.stdout.split()`,
  which splits on whitespace and so corrupts any path containing a space; it is now `-z` with
  a NUL split. And the guard had no floor at all — nothing asserted that it had looked at
  anything. `PHASE_CODE_SCAN_FLOOR = 450` was added, against **530 decodable files** at the
  time. Its comment records why the floor is a floor and not `> 0`: an earlier truncation of
  this same guard scanned only the git index and *still* saw 172 files, so a non-empty check
  would have passed on it. A guard that cannot report its own reach is a guard you are
  trusting for its intentions.

- **A precision the round-8 rewrite of that docstring gets slightly wrong.** It says the guard
  "used to carry" two restrictions, "index-only listing, and a six-extension pathspec". Only
  the pathspec was present at `af03efe`; the listing there already had `--cached --others
  --exclude-standard`, and round 6's docstring already argued for it. The index-only state is
  real — the scan-floor comment preserves its 172-file measurement — but it predates `HEAD`
  and was repaired before round 7 began. Left as a note rather than silently corrected in a
  file this entry does not own.

## Round 8 — the guards that were scanning a fraction of the repository

Numbered for the review round this work precedes. The round-7 entry above it was written
during this round, from the tree rather than from memory.

- **Two guards were green on a scope they had quietly outgrown.** The variable guard only
  inspected bash blocks containing the literal string `az deployment`; the placeholder guard
  only looked inside four glob patterns. Both now enumerate every tracked Markdown file with
  `git ls-files`, which takes the variable guard from three blocks to **154 bash blocks,
  scanned across all 58 tracked Markdown files**. Twenty-two unbound variables and three
  unlabelled placeholders were sitting in the difference. Five of them were live defects that
  seven rounds of critics had not found — not because the critics missed them, but because
  nothing had ever looked there. Enumerating from `git ls-files` rather than from a glob list
  also means the scope cannot go stale when a directory is added or renamed, which is how the
  four globs decayed in the first place.

- **The trigger was the defect, not the threshold.** The first widening kept a trigger and
  merely loosened it, from `az deployment` to any block running `az`. That model died on
  `solutions/ch04/README.md`, where `ARM_SERIALIZED_DATA` is expanded in a block containing
  nothing but `jq`, `printf` and `shasum`. Unbound there, it hashes the empty string and
  prints a digest that can never match the workbook — and the Azure CLI is nowhere near it. A
  guard whose trigger names a *tool* is asserting that only that tool can fail. Both triggers
  are gone. The contract is now one sentence each: every bash block binds or guards every
  variable it expands, and every placeholder in a runnable block names who supplies the value.

- **Stripping single-quoted spans with a regex misreads shell quoting.** `'[^']*'` cannot see
  the `'\''` close-escape-reopen idiom, so it mis-aligns and reads the *following*
  double-quoted span as unquoted. That produced a confident and wrong finding against
  `workshop/sre-agent/README.md`, where `$principal` is a jq `--arg` name inside a
  single-quoted program and not a shell expansion at all. It was proved a false positive by
  binding `principal` to a sentinel in a real shell and observing that the sentinel never
  reached the output — evidence, rather than a reading of the line. The extractor now walks
  the string tracking quote state, which also subsumes the hand-written special case for the
  correctly escaped `\$filter` OData parameter in `solutions/ch06-sre-agent/README.md`.

- **A placeholder detector's character class is a list of the spellings you already thought
  of.** `<[a-z][a-z0-9-]*>` could not match an uppercase letter, a dot, a pipe, a slash or a
  space, so it was structurally blind to `<identityResourceId>`,
  `<path-to-ch00-selection.json>` and `<dotnet-sqlserver|java-postgresql>` while looking
  rigorous. `solutions/ch00/README.md` had two conventions on adjacent lines and the guard saw
  only the compliant one. Admitting spaces surfaced two more that were whole English sentences
  in angle brackets, one of them in this repository's own facilitator runbook. The convention
  is now uniform across every Markdown file: a placeholder starts with `facilitator-`, `your-`
  or `owner-`, or ends in `key`, `password`, `secret`, `token` or `user`. One holdout was kept
  deliberately — `<dotnet-sqlserver|java-postgresql>` enumerates the two legal values instead
  of asking for an unknown one, which documents more than a conforming name would, so the
  guard now recognises pipe-separated choices as a category rather than demanding a rename.

- **The last allowlist was removed rather than justified.** `.azure/deployment-plan.md` was
  briefly exempted as a machine-generated record of decisions. It is not one: it already
  carries a substantive accuracy correction from an earlier round, and a document we fix when
  it is wrong is maintained, not frozen. Its two unbound variables were guarded and its
  placeholders renamed like everything else. Neither guard now holds an exemption of any kind,
  which is a far easier property to defend than a carve-out with a rationale attached to it.

- **Bind where a real source exists; guard only where none does.** A guard stops a wrong run,
  but a binding removes the chance of one. `WORKBOOK_RESOURCE_ID` now comes from the
  `workbookResourceId` output at `infra/observability-workbook.bicep:105`,
  `WORKFLOW_IDENTITY_PRINCIPAL_ID` from `infra/github-cicd.bicep:107`, `KEY_VAULT_NAME` from
  `infra/perf-testing.bicep:101`, and every identifier in `docs/Demo.md` from the
  `evidence/cicd-report.json` the demo has already produced — so nothing is typed on stage,
  where an empty `--name ""` is the most expensive failure available. Binding `infra/README.md`
  closed a documentation defect nobody had noticed: the prose claimed the block passed the
  template's `identityPrincipalId` output, and the block did not. Where no source exists the
  house idiom `: "${VAR:?…}"` is used, and for `PERFTEST_API_KEY` a guard is the deliberate
  choice — defaulting a secret is how you come to ship one.

- **Three unguarded variables were feeding a query time window.** `BAD_REVISION`,
  `INVESTIGATION_END` and `INCIDENT_END` in `solutions/ch06-sre-agent/README.md` are consumed
  as `--arg end "$…"`. Unset, they do not fail: they query an unbounded window and return
  evidence that looks plausible and is wrong, in the one chapter whose entire subject is an
  agent reasoning from evidence. A crash would have been kinder. All three are now guarded
  beside their three existing siblings, in the block that first consumes each, with messages
  that point at the drill capture rather than merely reporting the variable as missing.

- **Blocks labelled "illustrative" were guarded too.** `docs/Demo.md` and the reproduce-it
  shape in `docs/Facilitator.md` are prose-marked as examples, which is an argument for
  leaving them unbound only until you remember that a fenced block is an offer to run it.
  Both documents are executed live, and nothing stops a reader pasting. They were bound from
  real sources rather than guarded, because the values existed.

- **The T-4 rehearsal has coverage instead of a name.** `golden-dryrun` is the step that
  decides whether there is a rejoin path at 15:15 for the half of the room that will not
  finish Challenge 1, and its behaviour was asserted nowhere. `test_migration_handoff.py` now
  exercises it end to end. Building those tests surfaced an ordering fact worth keeping:
  `stack-match` cannot be reached by editing the contract's stack field, because the schema
  check ahead of it catches the resulting `sliceId` disagreement first. The defect that step
  actually exists for is a correct contract filed in the wrong stack directory.

- **A document told the facilitator that a shipped command does not exist.** The rehearsal
  section opened with "there is no dry-run harness" while the T-1 smoke table, in the same
  document, required `golden-dryrun` to exit `0`. Whichever a facilitator read first, the
  other was wrong, and the one who read the rehearsal first would hand-time a rehearsal a
  command validates for them. The false clause is gone and the two places are cross-linked;
  the true half — that nothing automates the timings, the transcript, or the inherited 1–2 day
  estimate — was kept, because the harness validates the *bundle* and does not time the *cut*.

- **A T-1 probe for the one directory nobody provisions.** Every Challenge 1 path writes its
  database export under `C:\ProgramData\MicroHack\migration`. The first read of this looked
  like a missing `mkdir`; it is not — all **six** path documents create it themselves. The
  real exposure is the ACL: `provision-vm.ps1` brings `C:\ProgramData\MicroHack` into being as
  SYSTEM, as a side effect of creating `vscode-extensions`, and never places an ACE on it, so
  whether a non-elevated participant may add a subfolder under it is inherited-ACE behaviour
  no delivery has tested. The new row tests it from the session a participant actually has,
  and says what a failure means, because a facilitator who reads `Access is denied` there will
  otherwise go looking for a typo in a runbook that is correct.

- **A prerequisite row that could not be executed from the row.** Chapter 5's entry described
  a captured, validated, distributed seed snapshot without naming the tool that captures it.
  It now names `seed-defender-findings.ps1`, its owner, the artifact that proves it worked,
  and the two conditions that gate it — the 24-hour plan wait and the golden handoff it binds
  to, which is precisely why that row straddles T-5 and T-4.

- **The Load Testing multiplicity, decided rather than hedged.** `docs/Facilitator.md` had
  asked the facilitator to "budget one Load Testing resource per participant unless you decide
  to share one". The workshop now budgets **thirty, one per participant, never shared**, and
  the reason recorded is contention rather than cost: Challenge 2 puts the whole room under
  load inside the same 35-minute window, so a shared resource serialises the one chapter whose
  subject *is* autoscaling under load. A hedge in a blocker table is a decision deferred onto
  someone with less context and less time.

- **The UNVERIFIED billing period, resolved instead of relabelled.** The decision multiplied a
  known unknown by thirty: `$10.00 per resource` with no stated period is the difference
  between $300 once and $300 every month, on a row a facilitator hands to a budget owner. The
  Retail Prices API cannot settle it — `unitOfMeasure` is `1`. Microsoft's own pricing page
  can, and does: `$10.00 per month includes 50 Virtual User Hours (VUH) per month`, with an
  FAQ entry stating the fee applies to a resource "active during any part of a month". The
  live page has since dropped both the row and the FAQ entry, so the citation is to the dated
  snapshot that still carries them, and two independent facts were checked to confirm it still
  describes current billing: the archived regional spread matches today's API exactly
  ($10.00, $12.50 in `usgov-virginia`), and the `JMeter Virtual User Included Usage` meter is
  still live at $0.00/hour — an included-usage meter cannot mean anything without the fee that
  buys the inclusion. What remains genuinely open is stated as such, with the one-minute Cost
  Analysis check that closes it and the meter ID to filter on.

- **The consequence mattered more than the number.** "Any part of a month" is not prorated, so
  a Friday-to-Wednesday delivery that crosses a month end is billed twice — $600.00 for five
  days. That turned a pricing footnote into a scheduling constraint, and it is now stated in
  the blocker row, the cohort table, and the worked example, whose subtotal is given both ways
  (≈ $2,579 within one month, ≈ $2,879 across two). A new **Pricing page** provenance label
  was added to the document's legend so that a figure sourced from the pricing page rather
  than the Retail API is auditable as such instead of being quietly promoted to "Retail API".

- **A dead schema rule grew back after the first one was deleted.** Round 7's didactics review
  asked for a `$defs`-reachability assertion "so the next dead region fails instead of
  surviving". The dead `$defs/challenge` in `shared-challenges.schema.json` was deleted; the
  assertion was not added. By this round `defender-cleanup.schema.json` had grown a *new*
  unreferenced `$defs/resourceId` — a rule that reads like a constraint in review and does
  nothing in the validator. It is deleted, the reachability guard exists, and it was
  mutation-tested by planting a dead rule and confirming the failure. Independently
  re-measured here: **41 contract schemas, 236 `$defs` entries, 0 unreachable.** Deleting the
  instance without asserting the class is how the class regrows, which is the same lesson as
  the guard triggers above, arriving from a different direction.

- **Negative result: no `required` names a property the schema never defines.** Checked across
  all 41 contract schemas. Every hit sits inside `if`/`then`/`allOf` composition, where the
  shapes come from the parent schema — correct JSON Schema, not a dead rule. Recorded as a
  negative because an audit that only lists what was broken says nothing about coverage. One
  caveat on the count: a naive sibling-only detector reports 24 hits here and a
  composition-aware one reports 8, and the difference is entirely detector naivety, not
  disagreement about the tree. Worth knowing before someone re-runs this and thinks the number
  moved. The naive pass did surface one shape worth a look on its own terms —
  `database-contract.schema.json` `properties/common` carries `required` with no `properties`
  and no `additionalProperties: false`, so its four keys are required to exist and then not
  validated at all. That is legal and it does something, so it is not this defect class; it is
  reported, not silently folded in.

- **Negative result: no runbook command points at a file that does not exist.** The only
  candidates are six references to `dotnet/Dockerfile` and `java/Dockerfile`, neither of which
  is in the tree. Both are correct by design: the participant authors them during Challenge 1,
  and the prose says so in those words — "the `Dockerfile` you authored". A guard for this
  class would have to understand which files a runbook *creates* before it can judge which it
  wrongly assumes, which is why the check was run by hand and recorded rather than automated.

## Round 8 closure — four defects the critics named, and the one that cost the point

Round 8 scored **didactics 10, delivery 10, conformance 10, quality 9, selling 9**. Selling
filed a 10 and then withdrew it in an addendum after running a control the review had
missed. This entry closes the selling and delivery gaps.

- **Introducing a variable and converting only some of its uses.** `docs/Demo.md` step 4 was
  changed this round to bind `CICD=evidence/cicd-report.json` and read `"$CICD"` — but only
  in two of its three `jq` blocks. The third, at `:240`, kept the literal path, while `:244`
  still told the facilitator that the example file is "substituted for the path above". The
  step therefore had *two* substitution mechanisms and one instruction describing half of
  them. Reproduced before fixing: with `CICD=workshop/contracts/cicd-evidence.example.json`
  the first two blocks resolve `rg-mh-example` / `ca-mh-example` and the third exits `2` with
  `jq: error: Could not open file evidence/cicd-report.json` — the rollback beat dies
  two-thirds through, on the one demo the agenda is built around. `:240` now reads `' "$CICD"`
  and `:243-245` names `CICD=` as the single substitution point for the whole step. Verified
  by running all three blocks end to end: the third prints the documented `45 min` / `2 min`
  byte-identically, `EXIT=0`. Steps 3 and 6, the two declared cold-runnable, were re-run and
  are unregressed. Swept the rest of the document for the same shape: `CICD` is the only
  variable `Demo.md` declares, and steps 1, 3 and 6 hard-code their paths with a matching
  literal-path substitution instruction, so the blast radius really was that one step.

- **A column that reconciled by neither route a reader has.** `docs/CostEstimate.md:231`
  claimed a `× 30` base subtotal of **$2,017.23** while its five visible rows sum to
  **$2,016.90** and 30 × the displayed **$67.24** gives **$2,017.20**. The true derivation is
  30 × the unrounded **$67.2409** — an operand that appeared nowhere in the document. The
  arithmetic was never wrong; it was unreproducible from the page, in the one document whose
  whole method is "here is the meter, re-derive it". Deliberately **not** re-derived: the
  totals are right, and a numeric rewrite is the worst place to risk a fresh second-order
  defect. Two changes, no figure moved. The row's Basis cell — blank until now — carries the
  missing operand, and one sentence after the provenance legend states that subtotals come
  from unrounded values *and* that anything wider than rounding shows its arithmetic in the
  row. The disclaimer alone would have been worse than nothing: it converts "sloppy" into
  "unverifiable by design". The promise is what makes it honest, and the Basis cell is that
  promise kept. The two remaining gaps are genuine single pennies. A fourth cell was checked
  and left alone: `**Modernized subtotal**` at **$261.72** against 15 × ($12.89 + $4.56) =
  $261.75, on the reasoning that it reconciles as 15 × an unrounded $17.448, is
  rounding-scale across 30 items, and has no visible column to sum. **That reasoning was
  reconsidered in round 9 and rejected.** "No visible column to sum" is the author's view of
  the table, not the reader's — the row is labelled *50/50 split*, which instructs a reader to
  multiply the two figures printed directly above it, and the sentence this same round added
  to the legend had already promised the arithmetic in the row. Worse, the reconciliation
  itself did not hold: no consistent reading of the two rows *as printed* yields $17.448.
  The closest is rounded non-database .NET lines ($1.94/day → $3.4354) plus 16 active
  vCore-hours ($9.48) = $12.9154, with Java at 42.5 h = $4.5333, summing to $17.4487 — which
  would require the .NET row to print $12.92, not the $12.89 it carried at the time (that row
  is now $12.90). And the $4.56 was a 42.75 h window inside a worked example that states
  42.5 h everywhere else. Both figures moved in round 9 —
  see [Round 9 closure](#round-9-closure--the-standard-we-set-and-the-four-rows-that-broke-it).

- **The last untestable-here property is now asserted at provisioning time.**
  `baseInfra/scripts/provision-vm.ps1` never created `C:\ProgramData\MicroHack\migration`.
  All six Challenge 1 runbooks create it with `New-Item -Force`, so the directory was never
  missing — what was untested was whether a *non-elevated* participant may add a subfolder
  under a `C:\ProgramData\MicroHack` that provisioning creates as SYSTEM, as a side effect of
  the `vscode-extensions` folder. That is inherited-ACE behaviour no delivery has exercised.
  `New-MigrationExportDirectory` now creates the directory and calls the existing
  `Set-ProtectedAcl` with `-ReadPrincipal $AdminUsername`, the same idiom already proven for
  `C:\protected`. The one extension needed: `Read` was hard-coded as the principal's right,
  so the helper gained a `[ValidateSet('Read','Modify')] $PrincipalRights` defaulting to
  `Read`. Defaulting rather than switching is deliberate — the guard on this helper exists
  precisely to keep the database passwords under `$SecretRoot` administrators-only, so the
  grant stays opt-in per call site and no existing call site changed. Verified by executing
  the real function with only its two Windows-only calls shadowed: `C:\protected` still
  yields `SYSTEM=FullControl; Administrators=FullControl; azureuser=Read`, the migration
  directory yields `azureuser=Modify`, `$SecretRoot` yields no principal ACE at all, and
  `-PrincipalRights FullControl` is rejected by the ValidateSet. `FileSystemRights.Modify`
  was confirmed to carry `CreateFiles` and `CreateDirectories` — the participant must be able
  to *write* the export, not merely read it.

- **A detection row that named the remedy class but not the remedy.** The T-1 probe at
  `docs/Facilitator.md:783` told a facilitator that `Access is denied` means "an ACL fix on
  the parent directory", which is a diagnosis, not a command — leaving them holding a
  permissions problem across thirty VMs at T-1 with nothing to paste. The row now reads as
  confirmation of a property provisioning asserts, carries an `az vm run-command invoke` /
  `icacls ... /grant azureuser:(OI)(CI)M` remedy that fixes the ACL in place, and points at
  [Reset one participant](Facilitator.md#reset-one-participant) so nobody reaches for a
  re-image — which replaces both VMs for every participant. It also now says **leave the
  directory** after removing the probe: the previous row told facilitators to delete it,
  which would discard the very ACE that makes it work.

- **The best safety story in the repository was invisible.** The acceptance harness's
  destructive-delete boundary — the only thing separating "delete the fixture" from "delete a
  participant's work" — was a string literal in `catalog_acceptance/database.py`, while
  `behavior-contract.json` (`ownedProductIdPrefix`) and `database-contract.json`
  (`acceptanceFixtureProductIdPrefix`) each declared the same boundary and nothing read
  either. It is now bound by a mutation-tested guard, and both the selling and didactics
  critics independently observed that participants would never see it: a grep across
  `challenges/`, `docs/` and `README.md` returned nothing. Five lines now close
  `challenges/ch01/README.md`'s **The concept**, which is where the section's own thesis
  lives — extending it from *the handoff must be true* to *a declaration nothing reads is
  decoration*. Told there it costs thirty seconds and lands as competence rather than
  apology; told in `docs/` it is documentation nobody opens. Deliberately placed once rather
  than in both the concept and the debrief — two homes for one artifact is exactly how
  `ownedProductIdPrefix` and `acceptanceFixtureProductIdPrefix` happened.

- **The cost fix was validated against the guard the critic asked for, both ways.** The
  acceptance suite had already grown
  `test_every_money_total_reconciles_with_the_rows_a_reader_can_see`, which allows a gap
  wider than a cent per summed row only where the row shows its arithmetic. It passes with
  the Basis cell, and reverting that one cell reproduces exactly the finding —
  `'**Base subtotal**' column 2 claims $2,017.23, the 5 rows above it total $2,016.90 (off by
  $0.33), and the row shows no arithmetic`. A fix that cannot be made to fail has not been
  shown to be the thing that passed.

- **The empty directory had a rot surface after all, and it was wrong.** `workshop/golden/`
  ships only a README and two `.gitkeep`s, because a golden handoff is made of live resource
  IDs and a checked-in one would be either a fabrication or a pointer at deleted resources.
  The quality critic scored that honestly and said its remaining point needed a live T-4
  rehearsal. But if the directory is empty by design, the README is the only thing that *can*
  rot — and a facilitator follows it for one to two days against a real subscription before
  anything checks their work. Two of its claims were machine-checkable. One was false: it said
  `workshop/golden/*/modernization-contract.json` was ignored by Git, and Git does not ignore
  that path. The real rule, `.gitignore:62`, ignores `workshop/golden/*/evidence/` — wider than
  the sentence, so the rendered bundle was always protected and nothing could have leaked. The
  sentence was still wrong, in a paragraph whose entire subject is not publishing somebody
  else's live resource IDs, and it had been wrong for eight rounds of review. It is now bound:
  the guard regex-parses *every* "is ignored by Git" claim out of the prose and asserts Git
  agrees, so the next wrong sentence fails instead of sitting there.

- **A guard that was correct only because someone guessed the right directory name.** The
  mirror guard compared the legacy and reference trees by walking the filesystem and filtering
  out a hand-written set of build directories — `bin`, `obj`, `target`, `.venv`, `__pycache__`,
  `.git`. Running the Java suite for the first time dropped a hundred class files into
  `solutions/reference/java/target/` and the guard passed, but only because `target` happened
  to be on the list. That is the same **detector character class** failure the audit has hit
  repeatedly: a hand-maintained list standing in for something the tooling already knows.
  `_files_under()` now enumerates with `git ls-files --cached --others --exclude-standard`,
  which honours every `.gitignore` in the tree including the nested one at
  `solutions/reference/java/.gitignore:1`, and the hand-written set is deleted.

- **Both application trees are now proven, and the Java one is proven to be load-bearing.**
  `.NET` was already 45/45. Java had never been run — the machine's default JDK is 1.8 — so a
  scratch Temurin JDK 21 was used with the repo's own `mvnw`: **35/35, BUILD SUCCESS**, with
  `PostgreSqlIntegrationTest` excluded because Testcontainers needs a Docker daemon this
  machine does not have (`Could not find a valid Docker environment` — an environment limit,
  reported rather than hidden). Passing tests only prove the tests ran, so the modernization
  was then reverted: `CatalogRuntimeOptions.require()` was changed from failing startup on a
  missing telemetry identity variable back to the legacy silent `"unknown"` default. Exactly
  three tests failed, all in `RuntimeIdentityConfigurationTest`, while that class's own
  positive control `suppliedRuntimeIdentityVariablesReachTheOptions` stayed green — which is
  what makes the three failures attributable to the revert rather than to drift.

- **A rule was named, measured, and deliberately not enforced.** The conformance critic
  observed that binding one constant does not establish the general rule that every constant in
  `workshop/contracts/*.json` must be read rather than retyped. Enforcing it was attempted and
  abandoned on evidence: at value level there are 703 shared strings across the contracts and
  198 machine-like values shared across 28 data contract files, which no hand-maintained
  allowlist survives; at file level the check comes back clean — 69 contract files, 449
  candidate readers, none unreferenced and none named only in prose. So the generalization does
  not reduce to reachability, and the value-level form is not mechanisable at acceptable
  precision. Recorded as a review obligation rather than shipped as an over-fitted guard, on the
  principle that a guard which mostly reports noise trains people to ignore it.

## Round 9 closure — the standard we set, and the four rows that broke it

Round 8 closed the `$2,017.23` base subtotal by adding a sentence to the provenance legend of
`docs/CostEstimate.md:18-20`: subtotals come from unrounded values, and *where the gap is
larger than rounding explains, the row's Basis cell gives the arithmetic that reproduces it.*
That sentence is a standard, and four rows in the same document did not meet it. A
second-order defect created by our own fix is still our defect, and this entry closes it.

- **The row that a skeptic checks first.** `Modernized workload, .NET / Azure SQL` printed
  **$12.89** with a Basis reading only "Derived over the ~42.5 h from Monday 15:30". The
  obvious route fails loudly: $6.67/day × 42.5/24 = **$11.81**, an 8.4% gap on the row that
  carries the document's most quoted claim — *.NET runs roughly 30% more than the legacy VM*.
  The figure is right and the route is not obvious, which is the worst combination: the
  database line does not pro-rate, because the daily table charges Azure SQL an allowance of
  8 active vCore-hours per day rather than a rate per wall-clock hour. The window covers two
  working days' worth of that allowance. Non-database lines are ($6.67 − $4.74) × 42.5/24 =
  **$3.4177**; the allowance is $4.74 ÷ 8 = **$0.5925** per active vCore-hour, and 16 of them
  is **$9.48**; the sum is **$12.8977**. And that is where the round turned on itself: the
  derivation written to justify **$12.89** does not produce it — $12.8977 rounds to **$12.90**.
  The row now prints $12.90. **The act of making the row reproducible is what exposed that it
  was not**, which is the lesson worth keeping from this round. A figure nobody can re-derive
  is not "probably fine"; it is unfalsified, and the difference only becomes visible when
  somebody finally does the arithmetic and writes it down. Holding the figure and letting the
  cell read `= $12.8977 ≈ $12.89` was the first instinct and it was wrong — the `≈` would have
  been absorbing a rounding that goes the other way, on the row that is the load-bearing
  evidence for the *~30% more than the legacy VM* claim, which is precisely the miniature of
  the defect this round exists to remove. A reader who follows the cell must land where the
  row says they land.

- **A row that was simply wrong, by a quarter of an hour.** `Modernized workload, Java /
  PostgreSQL` printed **$4.56**. Burstable PostgreSQL has no auto-pause and bills the whole
  window, so there is no allowance subtlety to hide behind: $2.56 × 42.5/24 = **$4.5333**.
  Working backwards, $4.56 is $2.56 × **42.75**/24 — a 42.75 h window in a worked example
  that derives 42.5 h from its own clock times (Friday 17:00 → Wednesday 10:00 is 113 h;
  Monday 15:30 is 70.5 h into it; 113 − 70.5 = 42.5). The document is self-consistent on 42.5
  everywhere else, so the row is now **$4.53**. Writing a Basis cell that asserted 42.5 h
  beside a figure that needs 42.75 h would have been worse than leaving the cell blank.

- **Two blank subtotals, both of which a reader is instructed to reproduce.** `Modernized
  subtotal, 50/50 split` claimed **$261.72**; the label tells a reader to take fifteen of each
  stack, and 15 × ($12.89 + $4.56) is $261.75. It is now **$261.45** = 15 × ($12.90 + $4.53),
  which matches the convention the cohort table two sections above already uses — its
  `$138.45` is 15 × the displayed $6.67 and $2.56, not 15 × the unrounded $6.6712 and $2.5574.
  `Azure subtotal` carried **≈ $2,579** with no working at all, the headline of the whole
  example: $2,017.23 + $261.45 + $300.00 = **$2,578.68**, so the headline is unchanged and now
  shows its terms. Everything downstream still holds without edit — ≈ $2,879 across a month
  end ($2,878.68), the $2,750–$2,950 delivery range ($2,785.06 with a shared SRE agent,
  $2,887.14 with one per team), and $92–$98 per participant ($92.84–$96.24). The comparison
  prose at `:190-194` needed no edit either: *~30% more* ($6.67 ÷ $5.13 = 1.300), *$1.54 per
  day more* and *$2.57 per day less* are all built on the **per-day** table, not on the
  window figures that moved.

- **A fifth row the widened guard found that the review had not.** `Total, after the Challenge
  0 deallocation` claimed **$11.72** against a Basis of pure prose — "One VM's compute stops;
  its disk keeps billing" — which is a reason, not an arithmetic. It follows the total above
  it rather than a column of its own, so a reader has nothing to add: it now reads
  $16.14 − 24 h @ $0.184 = $16.14 − $4.42 = **$11.72**, with the explanation kept after it. The
  guard had been widened twice while this work was in flight — from *is the Basis cell
  non-empty*, to *does its arithmetic land on the figure beside it*, to *does it restate that
  figure* — and it is a strictly better guard for it: the round-8 fix would have passed a cell
  reading "derived". Every Basis cell touched this round is therefore written to end on its own
  number, and all five were mutation-checked against the live guard. Blanking each reproduces
  its original offender; reducing one back to prose reproduces the prose rejection; a cell that
  states its inputs but never lands on the total is rejected; and the critic's mutation — move
  the figure to $9,999.99 and leave the Basis intact — is caught with *"its own stated basis
  does not arrive at that figure"*, which is the failure mode the non-empty check could not see.

- **The round-8 reasoning that let the subtotal stand is corrected above rather than
  deleted.** It argued the row was safe because it "has no visible column to sum". That is the
  author's view of the table wearing the reader's clothes; a row labelled *50/50 split* names
  its own operands. The claimed reconciliation was also not reproducible: no consistent
  reading of the two rows as printed yields the $17.448 it invoked.

- **Three known residuals, swept for deliberately and deliberately left.** Recorded here so a
  future reader finds them already-known rather than newly-discovered. *(a)* The two `Cohort of
  30` base figures are a penny above the meters — 30 × the unrounded $16.1375 is $484.13,
  printed $484.14, and $351.66 is internally consistent with it as $484.14 − $132.48. *(b)* The
  two Defender database rows, **~$34.83** each, are reproducible only from the **monthly**
  $15.00 meter (15 × 113 h × $15.00/730 = $34.83); the *hourly* meter their own Basis cells
  name, $0.020161, gives $34.17. Both rows already carry an UNVERIFIED proration caveat, and
  re-deriving an already-UNVERIFIED number is not an improvement — it dresses an unconfirmed
  figure in the clothes of a derived one. *(c)* The teardown table's idle months, ~$28.59 and
  ~$43.12, differ by exactly PostgreSQL's monthly compute (730 h × $0.0199 = $14.53) and so are
  consistent with each other, but their shared $24.21 base does not decompose from the printed
  meters — ACR $5.00 plus two private endpoints at $14.60 leaves **$4.61 unattributed**. Both
  are prefixed `~` in a table that has no Basis column, which is the honest form for an
  estimate, but the operand is missing.

- **The residual that was closed instead of carried.** This entry first held a fourth item —
  the .NET row printing $12.89 against a derivation of $12.8977 — as sub-cent drift not worth
  republishing a quoted figure over. That reasoning was rejected in review for the same reason
  the round-8 reasoning was: it is the author's tolerance, not the reader's experience. A
  reader who follows the Basis cell arrives at $12.90 and finds $12.89 beside it, which is
  exactly the moment this round was convened to eliminate. Two other cells do sit a hair under
  a half-cent ($5.085 → $5.08, $27.685 → $27.68), but those are the lower cent that IEEE-754
  rounding also produces, so they were never precedent for this one. The row is now $12.90 and
  the drift is gone rather than documented — the general rule being that a residual you can
  close by moving a number is not a residual, it is a defect with a note attached.

## Round 10 closure — the label that was wrong while the number was right

- **Two critics said the .NET window row spans three calendar days, and they were right.**
  The Basis cell justified its 16 active vCore-hours as "the 8 h/day allowance on the two
  days the window covers", and the window — Monday 15:30 to Wednesday 10:00 — covers three:
  Monday's tail, all of Tuesday, Wednesday's morning. The label was the kind of sentence a
  customer contradicts with a calendar. So the question was whether 16 survives a correct
  label or whether the figure has to move to 24.
- **[The agenda](Agenda.md#the-schedule) settles it at 16, and it is a label fix rather than
  a figure move.** The agenda is a *two-day* agenda. Day 1 ends `15:45–17:00 | Challenge 2 —
  load and autoscaling`, which is inside the window and is the most database-active block in
  the workshop; day 2 runs `09:00–09:15 | Day 2 kickoff` through `16:40–17:00 | Closing
  debrief`, a full eight hours. **Wednesday has no blocks at all** — the agenda ends at 17:00
  on day 2 and the worked example tears down at 10:00 Wednesday — so with `autoPauseDelay: 60`
  the database pauses an hour after Tuesday's close and Wednesday accrues nothing. Two days
  carry the allowance, one does not: 2 × 8 = 16, and $12.90 stands unmoved.
- **The soft spot is stated in the prose rather than buried in the cell.** Monday takes a
  whole day's allowance while only 1.5 h of Monday falls inside the window. That is
  defensible — the database is built and exercised during Challenge 1's own blocks
  (`10:45–12:30`, `13:15–15:15`), before the window opens — but it is the assumption in the
  row most worth arguing with, so the document now names it *and* prices the alternative:
  charge Monday only its in-window 1.5 h and the row is $9.05 rather than $12.90. A reader
  who disagrees with us can now see exactly what their disagreement is worth.
- **The 264-character Basis cell became a pointer and a paragraph.** Didactics measured every
  cell and found exactly one outlier — line 236 at 264 characters and nine operators, against
  67 for the next worst. The cell now reads `Derived over the ~42.5 h window; see below` and
  the derivation moved beneath the table in the shape already used for the month-end note,
  leading with the point rather than the arithmetic: *Azure SQL is the one line that does not
  scale with wall-clock time.* Line 235 was left exactly as it was, on didactics' instruction.
- **Four smaller corrections, each of which was a figure contradicting its own page.** The
  modernized daily `Total` had a blank Basis while printing $6.67 above a column that visibly
  sums to $6.68; it now shows the unrounded rows reconstructed from the meter table,
  $0.6912 + $4.7354 + $0.1666 + $0.48 + $0.598 = $6.6712. The Defender SQL row said "hourly
  instance meter" but its figure only comes from the **monthly** one — 15 × 113 × $15.00 ÷ 730
  = $34.83, where the hourly meter gives $34.17 — so the clause now names the meter it
  actually used. The delivery total omitted the same-month qualifier that the two rows feeding
  it both carry, which is load-bearing because a straddle lands at $3,085–$3,190, outside the
  stated band; the qualifier and the straddle band are now both there. And the teardown
  warning claimed $11,000–$15,000 against its own table's $11,771.55–$15,801.15 — a bullet
  that *understated* the risk it exists to raise — now $11,800–$15,800 with the addition shown.
- **The guard was rewritten mid-round and it changed what counts as evidence.** It no longer
  accepts a Basis that restates its answer; the cell must contain an expression with an
  operator that *evaluates* to the figure beside it, so `15 × ($99.99 + $4.53) = $261.45` now
  fails where it once passed. This is the third widening in two rounds, and each one has found
  something real: blankness, then prose, now answers acting as their own evidence.
- **Known residuals, unchanged and still known.** The `Cohort of 30` $484.14 is a penny above
  30 × $16.1375; the teardown table's ~$28.59 and ~$43.12 share a $24.21 base that leaves
  $4.61 unattributed. Both are marked `~` or carry their own caveat, and re-deriving an
  estimate does not make it a measurement.

## Round 11 closure — the prose move that made the load-bearing row unguarded

- **Moving the derivation into prose was right, and it silently removed the guard.** Round 10
  reduced line 236's Basis to `Derived over the ~42.5 h window; see below` on didactics'
  finding, and the prose beneath the table is a genuine improvement — *Azure SQL is the one
  line that does not scale with wall-clock time* is a sentence a reader can repeat. But the
  money guard only evaluates a cell that contains arithmetic, so a pointer cell is a cell it
  never checks. The critic proved the cost: changing $12.90 to $99.90 passed the whole suite.
  The single most load-bearing figure in the document had become the only one nothing verified.
- **Landing arithmetic bought the coverage back without touching the prose.** The cell now
  reads `$3.4177 + $9.48 = $12.8977 ≈ $12.90; derived below` — 49 characters against the 264
  didactics objected to, and still under line 251's 67, so the density finding stays satisfied.
  The full explanation stays where round 10 put it. The cell's only new job is to *land on the
  figure* so a machine can check it. Mutating $12.90 → $99.90 now fails, as does garbling the
  operand $3.4177, as does reverting the cell to its round-10 pointer form.
- **The audit for other thinned rows found one, and it was a figure I had got wrong.** Line 168's
  Basis, written in round 10, read `... = $6.6712 ≈ $6.67 (Java $12.787 ≈ $2.56)`. The Java
  total is $2.5574, not $12.787 — I had written five times the figure into a cell whose stated
  purpose was to make the figure reproducible. Nothing caught it: the guard evaluates one value
  per `=`/`≈` segment, and $12.787 sat inside a segment opening with $6.67, so it was never
  read. It now derives Java from the .NET total by the one row that differs,
  $6.6712 − $4.7354 + $0.6216 = $2.5574 ≈ $2.56, which the guard does evaluate — mutating either
  the Java figure or that operand now fails.
- **This is the round-9 lesson recurring in a new form.** There, writing the derivation exposed
  that $12.89 should have been $12.90. Here, the act of restoring machine-checkable arithmetic
  exposed a bad figure that had survived two critics and a 10/10 score, because it was in the
  one position the checker cannot see. A Basis cell is not evidence because it looks like
  arithmetic; it is evidence only where something reads it.
- **The teardown band now rounds outward.** Round 10's $11,800–$15,800 rounded the low bound
  *up* and the high bound *down* against a table producing $11,771.55–$15,801.15 — the two
  directions that flatter the claim, in a bullet whose entire purpose is to be believed. It is
  now $11,700–$15,900, with the reason stated in the bullet, and the duplicate claim in
  [Facilitator.md](Facilitator.md) moved with it.
- **Known residuals, still known and still unchanged.** The `Cohort of 30` $484.14 penny; the
  teardown table's $4.61 unattributed base. And a blind spot worth naming: line 168's column is
  summable with a $0.01 gap against a $0.05 tolerance, so the guard reaches its Basis only
  through the row-level check — the roughly thirty plain `Derived` rows elsewhere state no
  arithmetic at all and are unverified by design, since arming every one of them is the uniform
  refactor didactics warned against.

## Round 12–13 closure — pinning the rows, and the seventh failure mode

- **The money guard now checks every non-money cell in a row, not only the last one.** It
  previously read the trailing Basis cell alone, so the Quantity column of the base
  infrastructure table — `2 × 24 h @ $0.184` and its four neighbours — came under check for
  the first time.
- **Operand mutation survival fell 47% → 12% → 8% across the round.** The battery of 13
  mutation classes is at 13/13 caught.
- **Four defects were found in the guard rather than in the documents.** `@` was never parsed;
  a cell was accepted if *any* one of its segments landed; a final `≈ $X` restatement was
  compared against nothing; and widening the tokenizer twice invented values no document
  stated — word-internal hyphens read as minus signs, and adjacent numbers welded into one.
- **A seventh failure mode was identified: over-detection.** The first fix for the restatement
  gap rejected five *legitimate* writing patterns. A guard that fails on a correct document is
  how a team learns to disable the guard, so the fix was narrowed to distinguish `≈` — which
  means "the same quantity, rounded", and must therefore agree with what precedes it — from
  `=`, which may introduce a separately labelled quantity such as a stated alternative.
- **The rows that show checkable arithmetic are now pinned by name, not counted.** A count
  cannot notice one row being thinned into prose while another is added; `EVALUABLE_BASIS_ROWS`
  fixes the identity of all 17.
- **Two documentation changes closed the selling critic's last findings.** The base
  infrastructure table now states what it is for — one participant's environment for one day,
  and the table every later figure is multiplied out from — rather than arriving unlabelled.
  And the $16.14 → $11.72 drop is framed as the argument it makes rather than the subtraction
  it is: $4.42 ÷ $16.14 = 27% off the daily bill, earned by one command the participant runs.
- **Challenge 0 did not tell the participant what the deallocation saves.** Step 7 said only
  that the unselected VM "costs money for two days". It now names the figure at the point of
  the work, which is the only place the lesson can land.
- **The framing sentence added for S12-N1 named the wrong mechanism, and was corrected.** It
  said the later tables are this one "multiplied out — by participants, by hours, by days",
  which invites the arithmetic $16.14 × 113/24 × 30 = $2,279.78 against a stated base subtotal
  of $2,017.23 — a 13.0% gap, in the one sentence whose job is to invite the reader to check.
  The cohort figures are not the table multiplied but the table *split*, because of the
  Challenge 0 deallocation described eight lines below: 65.5 h with both VMs running, then
  47.5 h with one. The sentence now names that split, which reproduces to
  65.5 × $0.67240 + 47.5 × $0.48840 = $67.2409 per participant and $2,017.23 across 30.
- **Challenge 0 got the figure but not the concept, and now gets both.** Step 7 stated the
  saving but not what makes it safe: deallocating is not deleting, the compute stops and the
  disk keeps billing, and that is exactly why the VM can be started again. That clause lived
  only in the cost document, which nobody reads while they are running the command.
- **S12-M2 — the wrap-up scorecard's cost row now carries a direction caveat.** Its four
  caveats covered method, definition, counting and estimation, but not direction, so a manager
  handed "+30%" had nothing telling them the increase is the expected outcome. The caveat now
  says which way the figure moves and why, and travels with the row.
- **S12-N2 — the blank Basis at `CostEstimate.md`'s `Total, both VMs running` is deliberate and
  stays.** A Basis cell exists so a reader can check a figure the page cannot otherwise show
  its work for; here the column immediately above visibly sums to exactly $16.14
  (8.83 + 1.43 + 4.56 + 1.08 + 0.24), so a Basis would restate the addition the reader has
  just done. Verified.
- **S11-N1 — fabricated-but-consistent operands are undetectable in principle, and were not
  chased.** A basis whose arithmetic is internally consistent but whose input rate was invented
  cannot be distinguished from a correct one without an external price source. The guard's
  limit is stated here rather than hidden.
- **Stated next step for whoever delivers this first.** Every figure in the cost document is a
  list price under a stated assumption. The step from correct to excellent is one delivered
  cohort's actual invoice printed beside the estimate.
- **The last finding of the audit was over-detection again — the seventh failure mode, a second
  time.** A guard asserted the prose phrase `facilitator authorizes` against raw markdown, so
  re-wrapping a correct paragraph failed the suite while the warning it was checking for was
  still present and still correct. A check that fails on a correct document teaches a team to
  delete the check.
- **Fixed at the source and swept.** The Challenge 0 guard now matches prose against a
  whitespace-normalised copy of the document, while continuing to match commands such as
  `az vm deallocate` exactly — a command split across a newline is broken code, not re-wrapped
  prose. The sweep found **22 prose assertions matched against raw text**: 7 were already
  normalised at their source and were left alone, and 15 were hardened.
- **Proved in both directions rather than asserted.** Re-wrapping a phrase mid-sentence now
  passes, and removing or altering the phrase is still caught — verified on
  `challenges/ch00/README.md` and independently on `workshop/sre-agent/README.md`. Gate after
  the sweep: 516 passed, 1 skipped.
- **A probe artefact worth recording, because it nearly produced a false conclusion.** The first
  attempt to prove the sweep reported both mutations as MISSED. The guards were fine; the probe
  was searching the wrong files and replacing a phrase that was not contiguous in the text it
  was editing, so it silently changed nothing and the suite passed for the wrong reason. **A
  mutation probe that reports a clean pass without first proving its own edit landed is
  indistinguishable from a guard that does not work.** This is the same lesson as the earlier
  precise-anchor finding, and it recurred anyway.
