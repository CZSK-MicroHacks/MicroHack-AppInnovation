# Shared Azure Target Deployment Plan

**Status:** Approved - corrective contract refreeze in progress

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

`infra/main.bicep` is subscription-scoped. It creates the named resource group and invokes a
resource-group-scoped environment module. This permits a clean subscription what-if without
pre-creating a validation resource group.

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

- resource group and deterministic naming;
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
   Mutating commands consume the validated target-output document, require exact target
   confirmation, and use exact argument lists plus command/engine-specific result schemas.
   PostgreSQL import derives authentication and both non-secret principal names from target
   output; administrator and application password boundaries remain distinct and application
   passwords are required only in `password-secret` mode. Mutating and verification commands
   require bootstrap output. `render-handoff` requires application output plus an explicit,
   distinct retained rollback revision.
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

Build every module and parameter file, then run subscription-scope what-if in Sweden Central
for:

- .NET bootstrap with Blob;
- .NET application with Blob and an immutable synthetic image contract;
- Java bootstrap with Blob in managed-identity mode;
- Java application with Blob in password-secret mode using ephemeral secure inputs;
- both Azure Files compatibility variants, recording the selected subscription's policy
  limitation rather than claiming a live pass.

What-if command shape:

```bash
AZURE_CONFIG_DIR="$HOME/.azure-365" az deployment sub what-if \
  --location swedencentral \
  --template-file infra/main.bicep \
  --parameters @<scenario-parameter-file>
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

## Execution checklist

- [x] Analyze existing applications, contracts, IaC, policies, and package surfaces.
- [x] Select region and workshop/cost profile.
- [x] Select standalone Bicep and the two-stage deployment model.
- [x] Resolve Azure SQL authentication as Entra-only.
- [x] Define Blob default and Azure Files policy boundary.
- [x] Obtain approval for this plan.
- [x] Freeze and commit the executable contract foundation.
- [x] Review the contract/decomposition gate.
- [ ] Start the single P4 implementation child from the exact contract commit.
- [ ] Integrate and run cross-layer validation.
- [ ] Update implementation logs and confirmed-error guidance.
- [ ] Set this plan to `Ready for Validation`.
- [ ] Invoke the `azure-validate` skill.

## Approval and deferred actions

Approval authorizes local source changes, dependency restoration, tests, Docker builds,
Bicep builds, and Azure what-if only.

It does not authorize Azure resource creation, image pushes, database or image migration,
cutover, deletion, destruction, protected-provider changes, commits to remote branches, or
Git pushes. Those remain explicit later approvals.
