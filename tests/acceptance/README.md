# Catalog acceptance harness

This Python/pytest harness grades both baseline applications and every modernization
path against contract `1.1.0`. It validates the checked-in corpus before making live
requests.

## Contract tests

```bash
cd tests/acceptance
uv sync
uv run pytest tests/test_contract_assets.py
```

If an incompatible user-level `uv.toml` prevents `uv` from starting, preserve that file and
run the same gate as `uv --no-config run pytest tests/test_contract_assets.py`.

## Live HTTP verification

Set the application URL and the same non-default API key configured in the runtime:

```bash
export CATALOG_BASE_URL="http://localhost:5000"
export PERFTEST_API_KEY="<runtime-secret>"
export CATALOG_ACCEPTANCE_PROFILE="smoke"
uv run pytest tests/test_live_application.py
```

The smoke profile is useful during development but cannot be attached to a
modernization handoff. A full run requires database verification and emits the
schema-validated JSON evidence consumed by the handoff:

```bash
uv run python -m catalog_acceptance \
  --profile full \
  --base-url "$CATALOG_BASE_URL" \
  --performance-api-key "$PERFTEST_API_KEY" \
  --output evidence/acceptance-report.json
```

Full evidence requires all 198 image routes, database verification, duplicate import,
mixed valid/empty-slug atomicity, and no skipped required check. `--sample-images` and
`--skip-import` are smoke-only development options and are rejected by the full
profile. The full command exits nonzero when its live or database settings are absent;
the optional pytest live test may skip only for local development.

## Database verification

Database verification uses the native client already installed with each baseline:
`sqlcmd` for SQL Server/Azure SQL and `psql` for PostgreSQL. Credentials are passed
only through the clients' password environment variables.

For SQL Server or Azure SQL:

```bash
export CATALOG_DATABASE_KIND="sqlserver"
export CATALOG_DATABASE_HOST="sql-example.database.windows.net"
export CATALOG_DATABASE_NAME="catalog"
export CATALOG_DATABASE_USERNAME="<user>"
export CATALOG_DATABASE_PASSWORD="<password>"
export CATALOG_ACCEPTANCE_PROFILE="full"
uv run pytest tests/test_live_application.py
```

For PostgreSQL:

```bash
export CATALOG_DATABASE_KIND="postgresql"
export CATALOG_DATABASE_HOST="psql-example.postgres.database.azure.com"
export CATALOG_DATABASE_NAME="catalog"
export CATALOG_DATABASE_USERNAME="<user>"
export CATALOG_DATABASE_PASSWORD="<password>"
export CATALOG_DATABASE_SSL_MODE="require"
export CATALOG_DATABASE_TARGET="managed"
export CATALOG_ACCEPTANCE_PROFILE="full"
uv run pytest tests/test_live_application.py
```

The database check compares every figure ID, filename, and category with
`data/manifest.json`, including names, descriptions, slugs, timestamps, schema metadata,
constraints, indexes, migration history, and server-reported TLS; row counts alone are
not sufficient. Set `CATALOG_DATABASE_TARGET=local` only for a local baseline. A
modernization handoff requires `managed`.

## Modernization handoff verification

Validate a handoff and all referenced evidence before a downstream challenge consumes
it:

```bash
uv run python -m catalog_acceptance.handoff_cli \
  ../../evidence/modernization-contract.json \
  --contracts ../../workshop/contracts \
  --repository-root ../..
```

The command fails if the acceptance report is not a full passing run or if the source
stack, database family, corpus counts, image verification, application URL, service
identity, environment, version, or revision differs across the bundle.

All paths declared by a handoff are repository-root-relative. Runtime evidence must be
native TRX or Surefire JUnit XML containing all fourteen frozen tests under their exact
class-qualified native identities. Telemetry evidence must include normalized non-empty
query-result JSON for every named trace, metric, log, and resource attribute. Native
tests prove each rejected document adds exactly one counter unit; exported counter
measurements are validated as positive integral aggregates and may exceed one.

## Bounded target migration

Install the package and inspect the exact seven-command surface:

```bash
cd tests/acceptance
uv sync
uv run catalog-migrate --help
uv run catalog-migrate sql export --help
uv run catalog-migrate sql import --help
uv run catalog-migrate postgresql export --help
uv run catalog-migrate postgresql import --help
uv run catalog-migrate images copy --help
uv run catalog-migrate verify --help
uv run catalog-migrate render-handoff --help
```

The commands and arguments are frozen by
`workshop/contracts/migration-cli-contract.json`. Database and application
passwords are accepted only through the command-specific `MIGRATION_*`
environment variables. Every Azure CLI child process uses
`AZURE_CONFIG_DIR="$HOME/.azure-365"`.

Exports are source-read-only and create a BACPAC or PostgreSQL custom archive
plus a non-secret integrity sidecar. Imports and image copy require the target
resource ID from the application-stage target output, the same value in
`--confirm-target-resource-id`, and `--execute`. They refuse nonempty targets.
The CLI never creates or deletes Azure resources.

PostgreSQL restore always uses
`MIGRATION_TARGET_ADMINISTRATOR_PASSWORD`. Password mode separately requires
`MIGRATION_TARGET_APPLICATION_PASSWORD`; managed-identity mode forbids that
variable and verifies the facilitator's isolated Azure CLI identity before
creating the workload principal.

After database import and image copy, produce the report and handoff:

```bash
uv run catalog-migrate verify \
  --stack java-postgresql \
  --source-commit 0000000000000000000000000000000000000000 \
  --database-artifact /protected/catalog.dump \
  --target-output ../../evidence/azure-target-output.json \
  --output ../../evidence/migration-report.json

uv run catalog-migrate render-handoff \
  --target-output ../../evidence/azure-target-output.json \
  --migration-report ../../evidence/migration-report.json \
  --acceptance-report ../../evidence/acceptance-report.json \
  --telemetry-report ../../evidence/telemetry-report.json \
  --runtime-test-report ../../evidence/runtime-test-report.json \
  --output ../../evidence/modernization-contract.json
```
