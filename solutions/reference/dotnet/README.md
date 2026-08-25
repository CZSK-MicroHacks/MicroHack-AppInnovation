# Lego Catalog (.NET/SQL Server target)

The modernized target is a .NET 10.0.11 Blazor Server monolith backed by local SQL
Server 2022 or Azure SQL Database. It preserves the workshop UI while implementing shared contract
`1.1.0` for catalog browsing, search, category filtering, details, local images,
transactional import, health, bounded performance work, and OpenTelemetry.

## Workshop position

Challenge 0 compares the pre-warmed .NET 8/SQL Server VM with the Java/PostgreSQL
baseline. Selecting `dotnet-sqlserver` makes this directory the application source for
exactly one [Challenge 1 path](../../../challenges/ch01/README.md). Every path targets the
same `infra/main.bicep` deployment and must publish a valid modernization handoff before
the shared operational chapters.

## Prerequisites

- .NET SDK 10.0.400
- SQL Server 2022 Express or another SQL Server 2022 instance
- Canonical `data/catalog.json` and `data/images/`

## Configuration

Environment variables override the non-secret local defaults in `appsettings.json`.

| Variable | Required | Purpose |
| --- | --- | --- |
| `CATALOG_DATABASE_HOST` | No | SQL Server host or named instance; defaults to `.\SQLEXPRESS` |
| `CATALOG_DATABASE_PORT` | No | TCP port when the host is not a named instance |
| `CATALOG_DATABASE_NAME` | No | Database name; defaults to `LegoCatalog` |
| `CATALOG_DATABASE_USERNAME` | Together with password | SQL login; omit both username and password for Windows integrated security |
| `CATALOG_DATABASE_PASSWORD` | Together with username | SQL login secret supplied outside source control |
| `CATALOG_DATABASE_AUTHENTICATION` | No | `local` (default) or `managed-identity`; Azure SQL managed identity forbids username/password |
| `AZURE_CLIENT_ID` | Azure target | User-assigned workload identity client ID |
| `CATALOG_IMAGES_PATH` | No | Canonical image directory |
| `CATALOG_IMAGE_PROVIDER` | No | `local` (default) or `azure-blob` |
| `CATALOG_BLOB_SERVICE_ENDPOINT` | Blob provider | HTTPS storage service endpoint |
| `CATALOG_BLOB_CONTAINER` | Blob provider | Canonical image container |
| `CATALOG_SEED_PATH` | No | Canonical `catalog.json` path |
| `CATALOG_STARTUP_IMPORT_ENABLED` | No | `true` by default; applies the idempotent seed import |
| `PERFTEST_API_KEY` | Yes | Non-default key for `GET /perftest/catalog` |
| `PERFTEST_WORK_FACTOR` | No | Integer from 1 through 25; defaults to 10 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | Standard OTLP endpoint |
| `OTEL_SERVICE_VERSION` | Yes | Deployed commit or immutable image version; no fallback |
| `DEPLOYMENT_ENVIRONMENT` | Yes | Must be `lab`; no fallback |
| `CONTAINER_APP_REVISION` | Yes | Revision resource attribute; no fallback |

No database password or performance API key is committed. Azure SQL managed identity uses
encrypted certificate-validated connections; local SQL Server uses the local
development trust mode.

The Blob provider authenticates with the user-assigned managed identity and reads only
canonical lowercase UUID PNG keys. Azure Files remains compatible with the unchanged
local provider by mounting the share at `CATALOG_IMAGES_PATH`.

Telemetry identity has no defaults. `OTEL_SERVICE_VERSION`, `CONTAINER_APP_REVISION`, and
`DEPLOYMENT_ENVIRONMENT` must be supplied, otherwise startup fails. Later challenges assert
that the running revision reports its true source commit, so a placeholder identity would
silently break that evidence chain.

## Run on the workshop VM

Create the database and grant the selected identity migration and data permissions,
then run from `dotnet/`:

```powershell
$env:PERFTEST_API_KEY = '<non-default-local-key>'
$env:CATALOG_SEED_PATH = (Resolve-Path ..\data\catalog.json)
$env:CATALOG_IMAGES_PATH = (Resolve-Path ..\data\images)
$env:DEPLOYMENT_ENVIRONMENT = 'lab'
$env:OTEL_SERVICE_VERSION = (git rev-parse HEAD)
$env:CONTAINER_APP_REVISION = 'local-vm'
dotnet run --project src\LegoCatalog.App\LegoCatalog.App.csproj
```

The process applies EF migration `202608180001_ContractBaseline`, imports only new
seed records in one transaction, and listens on the URL printed by Kestrel.

### Legacy database reset boundary

Databases created by the pre-rewrite `EnsureCreated` model have incompatible string
identity and no migration history. The rewrite intentionally does not add an adoption
adapter. Before updating an existing workshop VM, a facilitator must back up any
non-canonical data, explicitly authorize deletion of that legacy database, recreate an
empty database, and let the contract migration reseed it from `data/catalog.json`.

## Test

```powershell
dotnet restore LegoCatalog.sln
dotnet test LegoCatalog.sln --logger trx --results-directory evidence
```

## Build the target container

From the repository root, on a workstation with a Docker daemon. This reference tree is read on your own machine, never on the workshop VM: the VM has no daemon, and every command participants run there uses `az acr build` instead.

```bash
docker buildx build --platform linux/amd64 --load \
  -f dotnet/Dockerfile -t mh-dotnet:p4 .
```

The image is non-root, listens on port `8080`, contains the canonical seed JSON
read-only, and expects database secrets and external image configuration at runtime.
Set `CATALOG_STARTUP_IMPORT_ENABLED=false` after the migration report has passed.

The native suite includes all fourteen degraded-state, conformance, and telemetry tests
under the exact class-qualified identities consumed by the shared handoff validator. To
run implementation-neutral HTTP and database acceptance:

```powershell
cd ..\tests\acceptance
$env:CATALOG_BASE_URL = 'http://localhost:5000'
$env:PERFTEST_API_KEY = '<same-runtime-key>'
$env:CATALOG_DATABASE_KIND = 'sqlserver'
$env:CATALOG_DATABASE_HOST = 'localhost'
$env:CATALOG_DATABASE_NAME = 'LegoCatalog'
$env:CATALOG_DATABASE_USERNAME = '<test-verifier-user>'
$env:CATALOG_DATABASE_PASSWORD = '<test-verifier-password>'
uv run python -m catalog_acceptance --profile full `
  --base-url $env:CATALOG_BASE_URL `
  --performance-api-key $env:PERFTEST_API_KEY `
  --database-kind sqlserver `
  --database-host $env:CATALOG_DATABASE_HOST `
  --database-name $env:CATALOG_DATABASE_NAME `
  --database-username $env:CATALOG_DATABASE_USERNAME `
  --database-password $env:CATALOG_DATABASE_PASSWORD
```

Use a disposable database for full acceptance because it publishes and then removes
only reserved fixture IDs under `10000000-0000-4000-8000-`.

## Stable routes

| Route | Behavior |
| --- | --- |
| `GET /` | Product-ID-ordered catalog; `search` is a case-insensitive literal name-only search and `category` accepts slug or display name |
| `GET /figure/{id}` | Server-rendered detail or 404 |
| `GET /images/{filename}` | Canonical UUID PNG bytes or 404; traversal is rejected |
| `GET /import` | Upload form |
| `POST /import` | Complete-document validation and transactional insert-new publication |
| `GET /healthz` | Process liveness only |
| `GET /readyz` | SQL connectivity plus startup migration/import state |
| `GET /perftest/catalog` | API-key-protected bounded SQL work and stable JSON DTOs |

## OpenTelemetry

The app exports only when an OTLP endpoint is configured. It emits standard ASP.NET
Core, HTTP, SQL Client, and runtime telemetry plus `catalog.import`,
`catalog.query`, and `catalog.performance` spans and their corresponding metrics and
structured logs. Resource identity is fixed to:

- `service.name=mh-catalog-dotnet`
- `service.namespace=app-innovation`
- `deployment.environment=lab`
- configured service version, instance ID, and revision

## Troubleshooting

- A healthy `/healthz` with a 503 `/readyz` means SQL Server is unavailable or startup
  migration/import failed; inspect the structured startup log.
- Startup import rejects the complete document before writing if any identity,
  filename, category slug, nonblank text, Unicode code-point minimum, UTF-16 storage
  maximum, or unknown-field rule fails.
- Image 404 responses require an exact lowercase `<productId>.png` key and an existing
  file beneath `CATALOG_IMAGES_PATH`.
- The app fails startup when `PERFTEST_API_KEY` or a bounded work factor is invalid.

For cross-layer diagnosis, authorization boundaries, and evidence failures, use the
repository [troubleshooting guide](../../../docs/Troubleshooting.md).
