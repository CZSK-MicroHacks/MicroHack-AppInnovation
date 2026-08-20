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
- Added `MSSQL_SA_PASSWORD` env var (placeholder `YourStrong!Passw0rd!` – recommend override via local customization) and mapped port 1433 for host access.
- Data persisted in named Docker volume `microhack-sql-data`; startup idempotent (skips if container already exists).
- Rationale: sidecar container avoids complexity of running SQL Server service inside main dev container (no systemd), keeps image lean, and mirrors production external DB topology.
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
