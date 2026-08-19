# Workshop contracts

These files freeze the behavior shared by the .NET/SQL Server and
Java/PostgreSQL baselines and by all three modernization paths.

## Contract versions

- Seed contract: `1.0.0`
- Behavior contract: `1.1.0`
- Runtime test evidence: `1.1.0`
- Modernization handoff: `1.3.0`
- Acceptance report: `1.0.0`
- Telemetry evidence: `1.0.0`
- Toolchain lock: `1.2.0`
- Shared Azure target output: `1.2.0`
- Migration report: `1.1.0`
- Migration CLI: `1.3.0`
- Migration CLI error: `1.0.0`
- Challenge 1 path registry: `1.0.0`

Breaking changes require a schema-version change and coordinator approval. Runtime
implementations consume these files; they must not copy or reinterpret the rules.

`challenge-paths.json` is the complete P5 registry: two source stacks across manual,
bounded Copilot rewrite, and GitHub Copilot modernization. Every slice consumes the
same P4 Bicep, native migration command, full acceptance harness, and modernization
handoff. Manual slices use the required Azure Files compatibility reference; the
other reference slices use policy-compatible Blob storage. Path-specific evidence
supplements rather than replaces the shared handoff bundle. Modernization handoff
`1.3.0` makes that path-to-image-provider relationship executable.

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
target, the release-role application-stage Azure target output, and linked migration evidence. Azure
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
per-platform container digests, P4 Azure SDK packages, the self-contained signed Windows
SqlPackage archive, and digest-pinned application build/runtime images. Accepted
provisioning and container builds consume this lock, verify downloads, and use immutable
source and image references.

`azure-target-output.schema.json` defines both clean bootstrap output, where application,
image, and revision-role values are null, and complete baseline/release application output.
It freezes Sweden Central, typed target resources, the exact P3 source VM/VNet migration
runner, database principals, the ACA default-domain relationship, and role/commit-derived
revision identity. `migration-report.schema.json` binds a verified database artifact,
external image corpus, and exact source-VM/private-network execution path to the same target.
`migration-cli-contract.json` freezes the seven `catalog-migrate` command names, exact
arguments, command/engine-specific results, exit codes, mode-specific environment-only
secret rules, bootstrap-before-application sequencing, source-VM execution over peered
private networks, exact database/image verification, target-output-bound workload identity
and PostgreSQL principals, protected transient SqlPackage response-file transport, removal
of the imported SQL Server `catalog`/`db_owner` principal, explicit target confirmation,
the baseline-then-release revision sequence, a distinct retained rollback revision, typed
JSON failures, and refusal to delete resources. PostgreSQL managed-identity bootstrap is fixed to
the declared facilitator Entra administrator, the required `$HOME/.azure-365` Azure CLI
context, transient `oss-rdbms` token authentication, and principal creation on the `postgres`
database. Handoff migration mechanism/version values are stack-specific and must match the
migration report and locked tools. Handoff rendering also requires the selected Challenge 1
path and a nonempty repository-contained Markdown rollback runbook; neither value is inferred
or patched after generation.

See `tests/acceptance/README.md` for live application and database verification.
