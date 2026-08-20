# Workshop contracts

These files freeze the behavior shared by the .NET/SQL Server and
Java/PostgreSQL baselines and by all three modernization paths.

## Contract versions

- Seed contract: `1.0.0`
- Behavior contract: `1.1.0`
- Runtime test evidence: `1.1.0`
- Modernization handoff: `1.4.0`
- Acceptance report: `1.0.0`
- Telemetry evidence: `1.0.0`
- Toolchain lock: `1.2.0`
- Shared Azure target output: `1.2.0`
- Migration report: `1.1.0`
- Migration CLI: `1.4.0`
- Migration CLI error: `1.0.0`
- Challenge 1 path registry: `1.0.0`
- Shared Challenge 2-4 registry: `1.0.0`
- Load-test evidence: `1.0.0`
- CI/CD evidence: `1.0.0`
- Observability workbook evidence: `1.0.0`

Breaking changes require a schema-version change and coordinator approval. Runtime
implementations consume these files; they must not copy or reinterpret the rules.

`challenge-paths.json` is the complete P5 registry: two source stacks across manual,
bounded Copilot rewrite, and GitHub Copilot modernization. Every slice consumes the
same P4 Bicep, native migration command, full acceptance harness, and modernization
handoff. Manual slices use the required Azure Files compatibility reference; the
other reference slices use policy-compatible Blob storage. Path-specific evidence
supplements rather than replaces the shared handoff bundle. Modernization handoff
`1.4.0` resolves one exact registered slice and makes its stack, database, provider,
rollback runbook, and path-specific evidence executable. Migration CLI `1.4.0` binds
every transfer command to the exact source commit recorded by the protected target.

`shared-challenges.json` is the P6 producer/consumer boundary. It requires the P5
handoff `1.4.0`, assigns nonoverlapping artifacts to load/autoscaling, CI/CD/revisions,
and observability, including each stream's focused acceptance file, and freezes their
evidence schemas, examples, output paths, CLI subcommands, and focused commands as one
non-cross-wirable per-stream tuple. The CLI validates the complete P5 handoff
before consuming any P6 evidence, checks every direct and nested handoff reference before
resolution, recursively audits every consumed directory tree, resolves every referenced file
inside the repository, and rejects symlinks in any path component or discovered child, empty
files, unrelated Azure resources, and invalid observation ordering. Schema and query loading is
bound to this checkout's exact `workshop/contracts` tree, which receives the same recursive
symlink audit; callers cannot substitute a second contract directory.

Load evidence uses normalized, timestamped Azure Load Testing and Azure Monitor output.
It requires a `Microsoft.LoadTestService/loadTests` run with zero failed requests, an
immediately preceding Azure Resource Manager observation of the exact 1-3 replica and
50-concurrent-request HTTP scale rule named `http`, an observed timestamp interval equal to the
declared run duration, measured ACA scale-out from one to at least two but no
more than three replicas, `app_cpu_billed` for Azure SQL or `cpu_percent` for PostgreSQL,
checked-in load-file digests, explicit baseline/load/recovery windows, and exact
health/readiness recovery URLs. CI/CD uses separate staging and production
GitHub OIDC subjects on one observed user-assigned identity. Both federated credentials and
both role assignments bind the workflow client/principal IDs to `AcrPush` at the handoff
registry and Container Apps Contributor at the handoff Container App. An observed immutable
assignment enumeration uses the principal object ID at subscription scope with `--all`,
`--include-inherited`, no JMESPath filter, and no Graph name enrichment. Its complete result
must contain exactly those two resource-scoped assignments; broader inherited access fails. The
workflow identity, ACR, and Container App must share that enumerated subscription. An immutable
observed GitHub run binds repository, workflow path, head SHA, ref, run ID, attempt, and successful
job IDs and windows to every build, candidate, smoke, approval, promotion, and rollback observation.
The candidate endpoint is derived using the official `<APP_NAME>---<LABEL>` FQDN, and candidate
plus post-transition observations record separate exact health and readiness URLs. Client
secrets, registry admin, and broader contributor scopes are prohibited.

Observability binds the existing telemetry report and exact Application Insights and Log
Analytics resources. An `AllMetrics` diagnostic setting sends Container App metrics to
the handoff workspace's `AzureMetricsV2` table before a revision-filtered workbook runs.
`observability-queries.json` freezes executable templates and result kinds for error rate,
latency, database dependency failures, replica count, and cold starts. The validator
renders exact resource, service, commit, revision, and time-window parameters, verifies
the UTF-8 query SHA-256, and validates one query-specific typed result row. The cold-start
proxy counts only instances whose first-ever request for the exact commit and revision falls
inside the evidence window. Captured Azure Workbook `serializedData` must hash correctly;
recursive top-level and grouped panel inspection requires `KqlItem/1.0`, Logs query type,
the Log Analytics workspace resource type, absent/default cross-component resources or exactly
the handoff workspace, and exactly those five rendered queries. Nested workbook JSON and all
file JSON reject non-standard `NaN` and infinity constants. The
observed ARM `sourceId` must equal the handoff workspace, while template and query-source
hashes must match their checked-in files. The checked-in workbook template itself must
contain the five frozen query templates with the same Logs execution context, and
`queries.kql` is the exact `// query-id: <id>` plus template sequence rendered by the
contract library. Normalized numeric and boolean observations are strict, so JSON booleans
cannot satisfy counts and JSON integers cannot satisfy flags. Normalized observations use the Pydantic `1.0.0` structures in
`catalog_acceptance.models.shared_challenges`.

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
uv run pytest tests/test_contract_assets.py tests/test_p6_contracts.py
```

Validate one generated P6 evidence bundle only after its complete handoff exists:

```bash
uv run catalog-validate-challenge-evidence load \
  ../../evidence/load-test-report.json \
  --handoff ../../evidence/modernization-contract.json \
  --contracts ../../workshop/contracts \
  --repository-root ../..
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
