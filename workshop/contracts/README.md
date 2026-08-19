# Workshop contracts

These files freeze the behavior shared by the .NET/SQL Server and
Java/PostgreSQL baselines and by all three modernization paths.

## Contract versions

- Seed contract: `1.0.0`
- Behavior contract: `1.1.0`
- Runtime test evidence: `1.1.0`
- Modernization handoff: `1.1.0`
- Acceptance report: `1.0.0`
- Telemetry evidence: `1.0.0`
- Toolchain lock: `1.0.0`
- Shared Azure target output: `1.0.0`
- Migration report and CLI: `1.0.0`

Breaking changes require a schema-version change and coordinator approval. Runtime
implementations consume these files; they must not copy or reinterpret the rules.

## Canonical identity and image digest

Figure IDs are canonical lowercase UUID strings. An image storage key is exactly
`<productId>.png`.

`data/manifest.json` computes `imageSetSha256` by sorting PNG filenames and hashing
the UTF-8 concatenation of one line per image:

```text
<filename>\t<byte-count>\t<file-sha256>\n
```

The acceptance suite recomputes all three corpus hashes and validates every catalog
record, category, filename, and image before testing an application.

## Validate

From `tests/acceptance/`:

```bash
uv sync
uv run pytest tests/test_contract_assets.py
```

`modernization-contract.schema.json` requires managed-resource IDs, dependency
authentication modes, immutable image identity, image verification, complete
OpenTelemetry resource attributes, the repository-relative IaC location, a rollback
target, the application-stage Azure target output, and linked migration evidence. Azure
SQL is Entra-only, Blob uses managed identity, and Azure Files uses the Container Apps
volume-secret boundary. A handoff is valid only when its referenced acceptance report is
a full passing report, all required runtime failure-state tests pass, and its target
output, migration, telemetry, database, image, URL, stack, commit, and revision values
agree:

```bash
uv run python -m catalog_acceptance.handoff_cli \
  path/to/modernization-contract.json \
  --contracts ../../workshop/contracts \
  --repository-root ../..
```

`workshop/toolchain.lock.json` is schema-validated and pins host compatibility,
runtimes, databases, clients, containers, CLIs, IDE extensions, and installer integrity
sources. It includes the exact Windows Server image, Windows installer URLs and hashes,
per-platform container digests, P4 Azure SDK packages, SqlPackage, and digest-pinned
application build/runtime images. Accepted provisioning and container builds consume
this lock, verify downloads, and use immutable source and image references.

`azure-target-output.schema.json` defines both clean bootstrap output, where application
and image values are null, and complete application output. It freezes Sweden Central,
typed same-scope resources, database principals, the ACA default-domain relationship, and
commit-derived revision identity. `migration-report.schema.json` binds a verified database
artifact and external image corpus to the same target.
`migration-cli-contract.json` freezes the seven `catalog-migrate` command names, exact
arguments, command/engine-specific results, exit codes, mode-specific environment-only
secret rules, target-output-bound workload identity and PostgreSQL principals, explicit
target confirmation, and refusal to delete resources. PostgreSQL managed-identity bootstrap
is fixed to the declared facilitator Entra administrator, the required `$HOME/.azure-365`
Azure CLI context, transient `oss-rdbms` token authentication, and principal creation on the
`postgres` database. Handoff migration mechanism/version values are stack-specific and must
match the migration report and locked tools.

See `tests/acceptance/README.md` for live application and database verification.
