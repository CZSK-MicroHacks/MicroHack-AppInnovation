# Shared Azure Target Deployment Plan

**Status:** Validated - local and read-only Azure preflight gates passed; live P10 remains deferred

## Scope and classification

Implement P4 from `docs/RewritePlan.md` as an existing-application modernization:

- one shared Azure Container Apps compute and operations model;
- .NET 10 with Azure SQL Database;
- Java 21 with Azure Database for PostgreSQL Flexible Server 18;
- deterministic database and image migration with machine-readable evidence;
- Azure Files and Blob-backed image implementations;
- no Azure deployment, cutover, source deletion, or rollback framework in this phase.

The target is a workshop/lab environment using the smallest practical SKUs. Examples and
what-if validation use Sweden Central.

P5-P9 consume this target without creating a second architecture. P5 adds six
stack/path solution guides under one Challenge 1 rubric, P6 adds repeatable load,
OIDC CI/CD, and observability artifacts, P7/P8 add facilitator-governed Defender
and SRE exercises, and P9 reconciles the complete workshop documentation. P10 live
deployment, paid-plan enablement, incident execution, cutover, and cleanup remain
separate authorization gates.

## Frozen inputs

- Integration branch/base: `rewrite-integration` at `703a278`
- Behavior contract: `workshop/contracts/behavior-contract.json`
- Data and database contracts: `workshop/contracts/`
- Canonical corpus: `data/manifest.json`, 198 figures, 20 categories, 198 images
- Accepted .NET and Java baseline applications
- Accepted P3 dual-VM provisioning
- Toolchain contract: `workshop/toolchain.lock.json`
- Azure CLI context directory: `AZURE_CONFIG_DIR="$HOME/.azure-365"`
- Validation subscription:
  `ME-MngEnvMCAP372348-mimarusa-1`
  (`7bc68c68-f434-49ad-ab3e-b883ec39da86`)
- Tenant: `a7b1484c-f66a-496a-b1cf-35631a50396c`

## Subscription constraints

The selected subscription denies Azure SQL deployments that do not use Entra-only
authentication. Management-group policies also modify Storage shared-key/local
authentication and public-network settings for Storage and Azure SQL.

Consequences:

- Azure SQL has no SQL administrator login/password parameter or compatibility branch.
- The .NET application uses a user-assigned managed identity for Azure SQL.
- Blob storage is the default and policy-compatible image provider.
- Azure Files remains a required compatibility implementation, but an SMB mount requires a
  storage account key in the Container Apps environment. It cannot be live-approved in this
  subscription while the shared-key policy applies. Its Bicep and runtime behavior will be
  build- and what-if-validated; live validation requires a policy exemption or another
  workshop subscription.
- Data services use private networking so public-network modification policies do not break
  the default deployment.
- The existing P3 source VM is the migration runner. The target deployment creates
  bidirectional peering with that VM's participant VNet and links every target private DNS
  zone to the source VNet. It never opens a public data endpoint.

## Deployment recipe

Use standalone Bicep under `infra/`. Do not introduce `azd`, Terraform, a deployment script,
or a second target architecture.

`infra/main.bicep` is resource-group-scoped (`targetScope = 'resourceGroup'`) and creates no
resource group. The facilitator creates each participant's resource group at T-1, together with
the two P3 legacy VMs, and grants that participant `Owner` on that one group and nothing above
it. The template therefore deploys *into* that existing group and invokes the environment module
there. Its `deploysIntoTheParticipantResourceGroup` assert requires `resourceGroupName` to equal
`resourceGroup().name`, so a parameter file aimed at another participant's group fails before it
can fill the wrong group. Validation, what-if, and deployment all use `az deployment group`
against that existing group; a participant needs no rights outside it, and one participant's
failure cannot take down the room.

`infra/sre-agent.bicep` is the single deliberate exception. It is subscription-scoped because it
defines a custom role definition, which cannot be scoped below a subscription, and only the
facilitator runs it.

The deployment has two explicit stages:

1. `bootstrap` creates networking, ACR, identities, database, image storage, Log Analytics,
   Application Insights, and the Container Apps environment. It creates no Container App and
   accepts no placeholder or mutable image.
2. `application` consumes an immutable repository, 40-character commit tag,
   `sha256:<64 hex>` digest, and an explicit `baseline` or `release` revision role. It creates
   or updates the Container App and emits its URL, revision role, revision, and complete
   handoff inputs.

The required order is bootstrap, database/image migration and exact verification from the
source VM, a healthy baseline application deployment, a release application deployment, live
acceptance/telemetry capture against the release, and handoff rendering. The baseline and
release deploy the same verified immutable image and use deterministic
`baseline-<commit-prefix>` and `release-<commit-prefix>` revision suffixes. This creates a
distinct retained revision without inventing a second artifact or generalized rollback system.
Import, image copy, and migration verification reject application-stage output. Handoff
rendering accepts only a release-role application output and the exact healthy baseline
revision as its rollback target.

Conditional resources and outputs use guarded ternaries so bootstrap never dereferences an
absent Container App.

## Architecture

### Shared modules

The Bicep module graph will contain:

- deterministic naming derived from the participant resource group the template deploys into;
- VNet, Container Apps infrastructure subnet, private-endpoint/delegated data subnets, and
  private DNS;
- typed source VM/VNet inputs, bidirectional source-to-target VNet peering, and source-VNet
  links to every target private DNS zone;
- Basic ACR with admin access disabled;
- one user-assigned workload identity for ACR pull, Blob read, and database authentication;
- Log Analytics and workspace-based Application Insights;
- direct Azure Monitor OpenTelemetry exporters for traces, metrics, and logs. Container Apps'
  managed Application Insights destination is not used because it does not accept metrics;
- external image storage selected by `azure-blob` or `azure-files`;
- a conditionally deployed Container App with HTTPS-only external ingress, exact liveness and
  readiness probes, single-revision mode, and bounded scaling;
- database-specific Azure SQL and PostgreSQL modules.

### Workshop defaults

- ACA container: 0.5 CPU, 1 GiB, minimum 1 replica, maximum 3 replicas
- ACR: Basic
- Storage: Standard LRS
- Azure SQL: General Purpose serverless, smallest validated capacity, auto-pause enabled
- PostgreSQL: Burstable `Standard_B1ms`, 32 GiB storage, PostgreSQL 18
- Log Analytics: `PerGB2018`, 30-day retention
- All resource names and outputs distinguish `dotnet` and `java`

Regional SKU availability remains a what-if/preflight gate rather than a fallback that
silently selects a larger SKU.

## Security and identity matrix

| Track | Database mode | Image mode | Secret handling |
| --- | --- | --- | --- |
| .NET / Azure SQL | User-assigned managed identity only; Entra-only server administration | Blob with managed identity, or Azure Files compatibility mount | No SQL password exists |
| Java / PostgreSQL | `password-secret` compatibility mode or managed identity/Entra mode | Blob with managed identity, or Azure Files compatibility mount | Password mode accepts secure deployment parameters and stores only the application password as an ACA secret |

Additional controls:

- ACR pulls always use managed identity.
- Blob data access uses least-privilege data-plane RBAC.
- Azure SQL has `azureADOnlyAuthentication: true` unconditionally.
- Database administrator identity metadata is non-secret input; no administrator credentials
  are emitted.
- PostgreSQL administrator and application passwords are separate secure parameters in
  compatibility mode and have no defaults.
- PostgreSQL also provisions the facilitator's signed-in Microsoft Entra user as the
  non-secret Entra administrator. Managed-identity mode uses that exact Azure CLI principal
  and an `oss-rdbms` access token to create the workload identity database principal; the
  password administrator remains limited to restore and local-role work.
- Container images are referenced by digest; `latest` and branch-derived tags are rejected.
- Before application deployment and again before handoff rendering, the facilitator resolves
  the exact `<repository>:<40-hex commit>` ACR manifest and requires its digest to equal the
  supplied image digest.
- Storage public access and anonymous Blob access are disabled.
- Application ingress is HTTPS-only.
- Bicep outputs, migration reports, logs, and modernization contracts contain no secrets.

## Runtime changes

The shared target requires bounded runtime adaptations rather than compatibility wrappers:

- Add an image-provider selector to both applications.
- Preserve the existing local filesystem provider unchanged for VM/local execution and Azure
  Files mounts.
- Add Blob readers to both runtimes using the workload identity. They accept only the frozen
  canonical lowercase UUID PNG key and return the same bytes/404 behavior as the local store.
- Add Azure SQL managed-identity connection support to .NET while preserving local
  integrated and explicit username/password modes.
- Add PostgreSQL managed-identity support to Java while preserving password mode.
- Preserve local OTLP export. In ACA, use the locked Azure Monitor exporter in each runtime
  for all three signals and pass the Application Insights connection string only through an
  ACA secret reference.
- Add pinned, non-root, multi-stage Linux/amd64 Dockerfiles. The canonical seed JSON is
  included read-only; deployed applications disable startup import after migration.
- Keep routes, health semantics, telemetry identity, database schema, and corpus behavior
  unchanged.

New SDK and container dependencies must be version- and digest-pinned in the toolchain
contract before implementation is delegated.

## Contract foundation

The coordinator will freeze and test these contracts before starting the P4 child:

1. Bump the modernization handoff schema for the P4 authentication/provider constraints:
   Azure SQL requires managed identity; Blob requires managed identity; Azure Files requires
   the ACA volume secret boundary.
2. Add a shared Azure target-output schema and examples for both `bootstrap` and
   `application` stages. It covers resource IDs, host names, identity IDs, provider mode,
   image reference, observability IDs, target database principals, the ACA environment
   default domain, exact source VM/VNet migration runner, and guarded optional application
   outputs. Application URLs are derived from the declared Container App/environment and
   revision suffixes from the source commit.
3. Add a migration-report schema and SQL/PostgreSQL examples. It covers source/target
   identity, exact source-VM/VNet/peering/DNS execution path, pinned tool/version, artifact
   hash, ordered migration history, row counts, image count/bytes/hash, and terminal status.
4. Freeze the migration CLI surface and JSON output:
   - `catalog-migrate sql export`
   - `catalog-migrate sql import`
   - `catalog-migrate postgresql export`
   - `catalog-migrate postgresql import`
   - `catalog-migrate images copy`
   - `catalog-migrate verify`
   - `catalog-migrate render-handoff`
   Transfer and verification commands consume the validated target-output document and
   require its exact immutable source commit. Mutating commands also require exact target
   confirmation and use exact argument lists plus command/engine-specific result schemas.
   PostgreSQL import derives authentication and both non-secret principal names from target
   output; administrator and application password boundaries remain distinct and application
   passwords are required only in `password-secret` mode. Mutating and verification commands
   require bootstrap output. `render-handoff` requires application output plus the exact
   selected modernization path, a nonempty repository-contained Markdown rollback runbook,
   its exact registry-required path evidence, and an explicit distinct retained rollback
   revision.
5. Add SqlPackage and all Azure SDK/base-image dependencies to
   `workshop/toolchain.lock.json` with integrity metadata.
6. Extend acceptance tests so producer outputs, migration reports, and the modernization
   handoff agree on stack, resources, auth modes, corpus counts, and hashes.

Contracts are frozen only after their tests pass. A child must stop rather than alter these
interfaces or add a local workaround.

## Migration and verification

Use the existing `uv`-managed acceptance package for the migration CLI so schema validation,
canonical hashing, and database verification remain shared.

Run it on the exact source VM declared by target output. That VM reaches target private
endpoints only through the deployment-created bidirectional VNet peering and resolves them
through the target private DNS zones linked to its P3 VNet.

Before any source read or target connection, the CLI must retrieve the current VM resource ID
from Azure Instance Metadata Service and match it to target output. It then proves that the
VM's live NIC subnet belongs to the declared source VNet, both peerings are provisioned and
`Connected` with reciprocal remote-VNet IDs, and every private-DNS link is provisioned,
registration-disabled, and linked to that source VNet. Resource-ID shape or provisioning state
alone is not sufficient evidence.

### SQL Server Express to Azure SQL

1. Prove the source metadata, migrations, constraints, indexes, and corpus match the exact
   database and seed contracts.
2. Export a BACPAC with pinned SqlPackage from the read-only source.
3. Hash and record the artifact.
4. Require an empty, explicitly named target database.
5. Import with Entra authentication from the facilitator's Azure CLI context.
6. Create the Container App managed identity as a contained database user and grant only the
   application roles.
7. Verify exact migration history, tables, columns, constraints, indexes, 198 figures, and
   20 categories against the database contract.

### PostgreSQL to Flexible Server

1. Prove the source metadata, migrations, constraints, indexes, and corpus match the exact
   database and seed contracts.
2. Export a custom-format archive with pinned `pg_dump` 18.6.
3. Hash and record the artifact.
4. Require an empty, explicitly named target database.
5. Restore with pinned `pg_restore` 18.6 using the local password administrator.
6. In managed-identity mode, verify the configured Entra administrator matches the
   facilitator signed in through `AZURE_CONFIG_DIR="$HOME/.azure-365"`, obtain an ephemeral
   `oss-rdbms` token, connect to the `postgres` database, and invoke
   `pg_catalog.pgaadauth_create_principal_with_oid` for the workload identity with both
   `isAdmin=false` and `isMfa=false`. In password mode, create the local application role
   with the separate application password.
7. Grant the application principal only the required database privileges.
8. Verify exact migration history, tables, columns, constraints, indexes, 198 figures, and
   20 categories against the database contract.

This bootstrap follows the official Flexible Server requirements that only a Microsoft
Entra administrator can enable Entra database principals and that
`pgaadauth_create_principal*` runs against the `postgres` database:
<https://learn.microsoft.com/azure/postgresql/security/security-entra-configure> and
<https://learn.microsoft.com/azure/postgresql/security/security-manage-entra-users>.

### Images

Copy only canonical manifest members to the selected share or Blob container. Download and
hash the actual target bytes, then verify exact names, count, aggregate bytes, and set hash
against `data/manifest.json`; reject corrupt, extra, or missing objects. Never trust uploader
metadata as target proof.

### Safety boundaries

- Export is source-read-only.
- Import refuses a non-empty target and requires the exact target resource ID/name twice.
- The CLI never creates or deletes Azure resources.
- No source database, VM database, image directory, storage container/share, resource group,
  or migration artifact is deleted.
- Credentials and tokens are environment-only and never command arguments or report fields.
- Every child process receives a minimal allowlisted environment. All `MIGRATION_*` values are
  stripped first, undeclared migration credentials are rejected, and emitted errors redact
  every injected secret.
- Every CLI failure, including argument parsing, malformed corpus input, and filesystem
  errors, emits exactly one frozen JSON error document and frozen exit code.
- P4 adds no generalized rollback machinery. Source backups remain intact and ACA revision
  rollback stays the existing handoff boundary. The first application deployment establishes
  a healthy `baseline` revision; the second deploys the same verified image as `release`.
  Handoff rendering verifies that the supplied baseline rollback revision belongs to the
  declared Container App, exactly matches the deterministic baseline name, exists, is healthy,
  is retained/inactive, contains one container using the same digest-qualified image as the
  release, and differs from the release revision.

## Implementation ownership

After the coordinator contract commit passes:

- Start one P4 child from that exact commit.
- The child owns only `infra/**`, the P4-bounded runtime/Docker files explicitly named in its
  prompt, the migration CLI implementation, and directly related component READMEs.
- The child may not change `workshop/contracts/**`, shared acceptance expectations,
  `docs/RewritePlan.md`, P3 infrastructure, or unrelated challenges.
- The child must return a new commit, exact changed files, exact command results, and risks.
- The coordinator immediately integrates the slice, runs cross-layer gates, verifies actual
  Bicep/migration output against the frozen schemas, and performs one focused final review.

No additional child is justified because database auth, storage provider selection, runtime
configuration, migration evidence, and Bicep outputs are one producer/consumer protocol.

## P8 Azure SRE Agent extension

P8 remains a standalone Bicep preparation against the selected modernization handoff. It
creates one dedicated agent resource group, one user-assigned action/knowledge identity,
one Log Analytics workspace, one workspace-based Application Insights component, one
`Microsoft.App/agents@2026-01-01` resource, and exactly two telemetry connectors. It also
creates the frozen custom Container App traffic role and the ten exact role assignments
needed by the two agent identities, facilitator, and participant.

The Bicep consumes `workshop/contracts/sre-agent.json` version `1.2.0`. Review/Low mode,
the user-assigned action identity, participant-resource-group knowledge scope, Stable
upgrade channel, Azure Monitor incident type, connector names/types, and all role IDs and
actions are contract-owned. The only subscription-wide role is the user-assigned
identity's Monitoring Contributor assignment required by the Azure Monitor alert scanner
and explicitly approved for this plan. The Azure Monitor response plan remains a separate
facilitator portal operation because the frozen contract prohibits an undocumented IaC
payload. The exact-resource `containerApps/write` action is not JSON-field-scoped; Review
approval and before/after state validation enforce that only traffic changes. No autonomous
mode, OBO, broad role, secret/image mutation, DCR, policy, deployment script, or generalized
rollback is introduced.

Preparation uses the already confirmed workshop context:

- subscription `ME-MngEnvMCAP372348-mimarusa-1`
  (`7bc68c68-f434-49ad-ab3e-b883ec39da86`);
- Sweden Central, where `Microsoft.App/agents` availability was preflighted;
- one isolated P8 foundation per participant/team;
- four fixed agent units per deployed agent; stopping does not end billing, deletion does;
- local Bicep build and acceptance tests only in this phase. No resource deployment,
  incident execution, role mutation, or deletion is authorized.

| Resource type | Number prepared per team | Capacity result |
| --- | ---: | --- |
| `Microsoft.App/agents` | 1 | Provider and region availability confirmed; live creation deferred to P10 |
| `Microsoft.App/agents/connectors` | 2 | Child resources of the one agent |
| `Microsoft.ManagedIdentity/userAssignedIdentities` | 1 | No regional compute quota |
| `Microsoft.OperationalInsights/workspaces` | 1 | Existing workshop service limit is sufficient for one isolated workspace |
| `Microsoft.Insights/components` | 1 | Existing workshop service limit is sufficient for one isolated component |
| `Microsoft.Authorization/roleDefinitions` | 1 | Deterministic subscription role definition, assignable only at the participant resource group |
| `Microsoft.Authorization/roleAssignments` | 10 | Exact frozen scopes; no Owner, Contributor, or User Access Administrator assignment |

## Validation

### Contract and runtime gates

```bash
cd tests/acceptance
uv run pytest -q
uv lock --check --offline

cd ../../dotnet
dotnet test LegoCatalog.sln

cd ../java
OTEL_SDK_DISABLED=true ./mvnw -q test
./mvnw -q package -DskipTests
```

Run targeted Blob/provider and managed-identity configuration tests in the same native test
invocations after those tests exist.

### Container gates

These gates run on a validation workstation with a Docker daemon, never on a workshop VM.
The VM has no daemon, and every command participants run there uses `az acr build`
instead; `--load` and the `trivy image` scans below both require the image to be present
in a local daemon.

```bash
docker buildx build --platform linux/amd64 --load -f dotnet/Dockerfile -t mh-dotnet:p4 .
docker buildx build --platform linux/amd64 --load -f java/Dockerfile -t mh-java:p4 .
trivy image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 --ignore-unfixed mh-dotnet:p4
trivy image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 --ignore-unfixed mh-java:p4
```

Run each image against its pinned disposable local database and execute the full shared
acceptance profile, outage/recovery checks, canonical/noncanonical image probes, and
manifest verification for both local/Azure-Files-compatible and Blob-emulator/provider
tests.

### Bicep gates

Every Azure CLI command uses the selected profile:

```bash
export AZURE_CONFIG_DIR="$HOME/.azure-365"
az bicep install --version v0.43.8
az bicep version
az bicep build --file infra/main.bicep
```

Build every module and parameter file, then run resource-group what-if in Sweden Central
for:

- .NET bootstrap with Blob;
- .NET application with Blob and an immutable synthetic image contract;
- Java bootstrap with Blob in managed-identity mode;
- Java application with Blob in password-secret mode using ephemeral secure inputs;
- both Azure Files compatibility variants, recording the selected subscription's policy
  limitation rather than claiming a live pass.

What-if command shape:

```bash
: "${RESOURCE_GROUP:?set to the resource group this what-if was run against}"
AZURE_CONFIG_DIR="$HOME/.azure-365" az deployment group what-if \
  --resource-group "$RESOURCE_GROUP" \
  --template-file infra/main.bicep \
  --parameters @<your-scenario-parameter-file>
```

No `az deployment ... create`, `azd`, `terraform apply`, image push, database import, or
resource mutation is authorized by this plan.

### Integration gates

- Validate rendered Bicep outputs against the target-output schema.
- Validate SQL and PostgreSQL dry-run reports against the migration schema.
- Prove every bootstrap command rejects application output and handoff rendering rejects
  bootstrap output.
- Prove exact target resource-ID/name/principal relationships before any connection or
  mutation, exact source/target database contracts, actual target image bytes, ACR
  commit-tag/digest equality, and a distinct retained rollback revision.
- Validate complete handoff fixtures through `catalog_acceptance.handoff`.
- Scan for mutable image refs, source-code secrets, SQL administrator credentials,
  unguarded conditional-resource outputs, and secret-bearing command lines.
- Run `git diff --check` and verify no temporary reports, BACPACs, dumps, images, credentials,
  or generated Bicep JSON remain tracked or untracked.

### All validation checks pass

#### Bicep validation steps

- [x] 1. Bicep compilation
- [x] 2. Resource-group template validation
- [x] 3. Six-scenario what-if preview
- [x] 4. Azure authentication and context
- [x] 5. Bicep linting
- [x] 6. Azure Policy validation

#### Repository integration steps

- [x] Full shared acceptance and offline dependency lock
- [x] .NET native test/build
- [x] Java native test/package on the pinned JDK
- [x] Terraform format, initialization, and static validation
- [x] GitHub Actions validation
- [x] PowerShell guide-block parsing
- [x] linux/amd64 image builds and vulnerability scans
- [x] Static secret-signature and generated-artifact checks
- [x] Static Bicep/Terraform role-assignment verification

## Section 7: Validation Proof

Validation completed on 2026-08-21 with read-only Azure operations against the selected
workshop subscription. No deployment command is part of this validation.

### Azure context and toolchain

- `AZURE_CONFIG_DIR="$HOME/.azure-365" az account show` confirmed the enabled default
  subscription `ME-MngEnvMCAP372348-mimarusa-1`
  (`7bc68c68-f434-49ad-ab3e-b883ec39da86`) in tenant
  `a7b1484c-f66a-496a-b1cf-35631a50396c`.
- `az version --query '"azure-cli"' --output tsv` returned `2.80.0`.
- `az bicep version` returned `0.43.8`.
- Read-only effective-access inspection confirmed the signed-in facilitator has `Owner` on the
  validation subscription itself, which is what the facilitator-only SRE template requires.

### Bicep and ARM validation

All 11 files under `infra/**/*.bicep` passed both:

```bash
AZURE_CONFIG_DIR="$HOME/.azure-365" az bicep lint --file <your-bicep-file>
AZURE_CONFIG_DIR="$HOME/.azure-365" az bicep build --file <your-bicep-file> --stdout
```

The commands produced zero errors. The only diagnostics were the repository-known
experimental-assert warning, newer-CLI notice, two conservative BCP334 minimum-name
warnings, and safe-access suggestions.

Each saved sanitized scenario then passed both ARM validation and what-if against an existing
resource group:

```bash
: "${RESOURCE_GROUP:?set to the resource group these gates were run against}"
AZURE_CONFIG_DIR="$HOME/.azure-365" az deployment group validate \
  --resource-group "$RESOURCE_GROUP" \
  --template-file infra/main.bicep \
  --parameters @<your-scenario-parameter-file>

AZURE_CONFIG_DIR="$HOME/.azure-365" az deployment group what-if \
  --resource-group "$RESOURCE_GROUP" \
  --template-file infra/main.bicep \
  --parameters @<your-scenario-parameter-file> \
  --result-format ResourceIdOnly \
  --no-pretty-print
```

| Scenario | ARM validation | What-if changes | Role assignments |
| --- | --- | ---: | ---: |
| .NET bootstrap / Blob | `Succeeded` | 27 creates | 3 |
| .NET application / Blob | `Succeeded` | 28 creates | 3 |
| .NET application / Azure Files | `Succeeded` | 28 creates | 2 |
| Java bootstrap / Blob managed identity | `Succeeded` | 26 creates | 3 |
| Java application / Blob password secret | `Succeeded` | 27 creates | 3 |
| Java application / Azure Files managed identity | `Succeeded` | 27 creates | 2 |

The Azure Files rows prove template and ARM-policy compatibility only. They do not override
the live SMB/shared-key limitation documented in **Subscription constraints**.

### Azure Policy proof

Read-only assignment inspection found five enforced tenant-root assignments and six
subscription Defender assignments. The inherited `Block Azure RM Resource Creation`
definition was inspected directly: it denies only the listed
`Microsoft.ClassicCompute`, `Microsoft.ClassicStorage`, `Microsoft.ClassicNetwork`, and
`Microsoft.MarketplaceApps/classicDevServices` resource types. The target creates none of
those types. All six ARM validations and previews completed without a policy denial; no
exception or policy change was requested.

### Static RBAC proof

The focused cross-layer role gate passed:

```bash
cd tests/acceptance
uv --no-config run pytest -q \
  tests/test_azure_implementation_contract.py \
  tests/test_ch03_cicd_challenge.py \
  tests/test_ch05_defender_foundation.py \
  tests/test_ch06_sre_agent_contracts.py \
  tests/test_ch06_sre_agent_challenge.py
```

Result: `100 passed in 9.78s`. Read-only `az role definition list --name <role-id>`
lookups also resolved every frozen identifier to the expected built-in role.

- The workload identity receives `AcrPull` only at the exact registry. Blob mode additionally
  grants it `Storage Blob Data Reader` only at the exact container; Azure Files mode uses the
  bounded ACA volume-secret boundary and grants no workload storage role.
- The facilitator migration principal receives `Storage Blob Data Contributor` at the exact
  Blob container or `Storage File Data Privileged Contributor` at the exact file share.
- The GitHub identity receives `AcrPush` at the exact registry and
  `Container Apps Contributor` at the exact Container App, with only the two frozen
  environment subjects.
- Terraform grants generated participants `Owner` and `Security Reader` only at their
  resource group and grants each source VM identity `Owner` only at that same group.
  It creates no facilitator assignment; the facilitator's existing subscription `Owner`
  access is a prerequisite.
- The SRE template preserves the exact reader roles at the participant resource group,
  the traffic custom role only at the exact Container App, human roles only at the exact
  agent, and the single approved user-assigned-identity `Monitoring Contributor`
  subscription exception.

`Validated` means the prepared templates, policy surface, role definitions, and repository
gates are ready for an explicitly authorized deployment. It is not evidence for live P10
deployment, migration, paid-plan, load, incident, traffic, or cleanup exercises.

## Execution checklist

- [x] Analyze existing applications, contracts, IaC, policies, and package surfaces.
- [x] Select region and workshop/cost profile.
- [x] Select standalone Bicep and the two-stage deployment model.
- [x] Resolve Azure SQL authentication as Entra-only.
- [x] Define Blob default and Azure Files policy boundary.
- [x] Obtain approval for this plan.
- [x] Freeze and commit the executable contract foundation.
- [x] Review the contract/decomposition gate.
- [x] Integrate and validate P4 through P7.
- [x] Freeze and approve the P8 executable contract foundation.
- [x] Build the coordinator-owned P8 vertical slice.
- [x] Complete the focused P8 implementation and corrective reviews.
- [x] Integrate and validate the P8 vertical slice.
- [x] Reconcile P9 chapters, documentation, optional tracks, and stale assets.
- [x] Complete local P10 acceptance, native, IaC, workflow, container, and safety gates.
- [x] Update implementation logs and confirmed-error guidance.
- [x] Set this plan to `Ready for Validation`.
- [x] Invoke the `azure-validate` skill.

## Approval and deferred actions

Approval authorizes local source changes, dependency restoration, tests, Docker builds,
Bicep builds, and Azure what-if only.

It does not authorize Azure resource creation, image pushes, database or image migration,
cutover, deletion, destruction, protected-provider changes, commits to remote branches, or
Git pushes. Those remain explicit later approvals.
