# Lego Catalog (.NET/SQL Server baseline)

The supported legacy baseline is a .NET 8 Blazor Server monolith backed by SQL
Server 2022 Express. It preserves the workshop UI while implementing shared contract
`1.0.0` for catalog browsing, search, category filtering, details, local images,
transactional import, health, bounded performance work, and OpenTelemetry.

The baseline intentionally contains no Dockerfile or student-facing cloud IaC.

## Prerequisites

- .NET SDK 8.0.424
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
| `CATALOG_IMAGES_PATH` | No | Canonical image directory |
| `CATALOG_SEED_PATH` | No | Canonical `catalog.json` path |
| `CATALOG_STARTUP_IMPORT_ENABLED` | No | `true` by default; applies the idempotent seed import |
| `PERFTEST_API_KEY` | Yes | Non-default key for `GET /perftest/catalog` |
| `PERFTEST_WORK_FACTOR` | No | Integer from 1 through 25; defaults to 10 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | Standard OTLP endpoint |
| `OTEL_SERVICE_VERSION` | No | Deployed commit or immutable image version |
| `DEPLOYMENT_ENVIRONMENT` | No | Must be `lab`; defaults to `lab` |
| `CONTAINER_APP_REVISION` | No | Revision resource attribute; defaults to `local` |

No database password or performance API key is committed. Azure SQL hosts use
encrypted certificate-validated connections; local SQL Server uses the local
development trust mode.

## Run on the workshop VM

Create the database and grant the selected identity migration and data permissions,
then run from `dotnet/`:

```powershell
$env:PERFTEST_API_KEY = '<non-default-local-key>'
$env:CATALOG_SEED_PATH = (Resolve-Path ..\data\catalog.json)
$env:CATALOG_IMAGES_PATH = (Resolve-Path ..\data\images)
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

The native suite includes the exact degraded-state and cross-runtime conformance test
names consumed by the shared handoff validator. To run implementation-neutral HTTP and
database acceptance:

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
