# Path 1A: manual modernization

Modernize one P3 catalog stack without code-generation or modernization extensions:

| Slice | Source | Managed database | Solution |
| --- | --- | --- | --- |
| `manual-dotnet` | `dotnet/` | Azure SQL Database | [Runbook](../../solutions/ch01-manual/dotnet/README.md) |
| `manual-java` | `java/` | Azure Database for PostgreSQL Flexible Server | [Runbook](../../solutions/ch01-manual/java/README.md) |

The frozen source of truth is
[`workshop/contracts/challenge-paths.json`](../../workshop/contracts/challenge-paths.json).
Use the shared P4 implementation in `infra/`, the selected stack's existing Dockerfile,
and `tests/acceptance`; do not create another application, migration tool, or IaC path.

## Preconditions

- Work from one immutable, lowercase 40-character source commit. Do not use a branch,
  `latest`, or another mutable reference as evidence.
- Use only the checked-in lock files, wrapper, contracts, Bicep, Dockerfiles, and
  acceptance package. Keep Azure CLI isolated with
  `AZURE_CONFIG_DIR="$HOME/.azure-365"`.
- Run `catalog-migrate` on the selected P3 source VM. The command verifies that VM's
  resource identity, source VNet, peering, private DNS links, and target relationships.
- Supply database passwords, tokens, and the performance key only through the documented
  environment variables or protected deployment parameter files outside the repository.
  Never put a secret in an argument, evidence document, terminal transcript, or commit.
- Obtain facilitator approval before every deployment, target mutation, identity
  assignment, traffic change, or cleanup action.

Stop if the registry, migration CLI contract `1.3.0`, modernization handoff schema
`1.3.0`, target output, or `infra/main.bicep` would need to change. This slice consumes
those interfaces; it does not reinterpret them.

## Required progression

1. **Characterize and protect the source.** Record the exact commit, source VM and VNet
   resource IDs, application configuration names without values, native test results,
   local full-acceptance result, corpus counts, and a restorable database export. Keep the
   source database and `data/images/` intact. Write the checkpoint to
   `evidence/baseline-backup.md`.
2. **Review and bootstrap the shared target.** Build `infra/main.bicep`, run a
   subscription-scope what-if, and review private networking, managed database,
   `imageProvider=azure-files`, ACR, observability, and the absence of a bootstrap
   Container App. Record the review in `evidence/iac-review.md`, then deploy only with an
   approved protected parameter file. Save the emitted bootstrap output as
   `evidence/azure-target-output.json`.
3. **Migrate with the native P4 CLI.** Use the selected `catalog-migrate sql ...` or
   `catalog-migrate postgresql ...` export/import commands, followed by
   `catalog-migrate images copy` and `catalog-migrate verify`. Imports and image copy
   must repeat the exact target resource ID in both confirmation arguments and include
   `--execute`. They must refuse a nonempty target.
4. **Verify the migration exactly.** `evidence/migration-report.json` must prove the
   schema, migration history, constraints, indexes, complete figure/category corpus,
   image count, image bytes, image-set hash, TLS, least-privilege application principal,
   and the source-VM execution topology. Row counts alone are not proof.
5. **Prove application/database separation on the VM.** Reconfigure the still-running
   source-VM application to the managed database, disable startup import, and run full
   acceptance while compute remains the VM. Record application resource, managed
   database resource, identity, commit, acceptance result, and timestamps in
   `evidence/managed-database-separation.json`. Do not build or deploy ACA until this
   checkpoint passes.
6. **Build the existing non-root container.** Use `dotnet/Dockerfile` or
   `java/Dockerfile` from the repository root. Confirm its numeric non-root user,
   read-only seed, port `8080`, health check, pinned base-image digest, and external
   `/app/images` path. Save the ACR build result and manifest digest in
   `evidence/container-build.json`.
7. **Use Azure Files compatibility mode.** Copy the canonical source images with
   `catalog-migrate images copy`. The unchanged local image provider reads the ACA
   Azure Files mount; do not add an adapter or alternate provider.
8. **Deploy one immutable digest twice.** Resolve the commit tag to an ACR
   `sha256:` digest, then deploy the shared Bicep application stage first as `baseline`
   and then as `release`, using the same digest. Retain the healthy baseline revision
   inactive for rollback. Never deploy by tag.
9. **Run complete release verification.** Produce the native TRX or Surefire JUnit
   artifact and `evidence/runtime-test-report.json`, run
   `python -m catalog_acceptance --profile full` to
   `evidence/acceptance-report.json`, and collect normalized Azure Monitor resource,
   trace, metric, and log results referenced by `evidence/telemetry-report.json`.
   Assessment, a healthy response, or a deployment success does not prove behavior.
10. **Write and validate rollback.** `evidence/rollback-runbook.md` must name the
    retained baseline revision and immutable digest, approval gate, the Container Apps
    single-revision activation command, health/readiness and full-acceptance checks,
    abort conditions, and forward-recovery procedure. Do not use weighted traffic:
    `activeRevisionsMode` is `Single`, so activating the retained prior revision
    deactivates the current revision. Preserve both databases, exports, images, and
    evidence.
11. **Render the handoff.** Run
    `catalog-migrate render-handoff --path manual --rollback-runbook evidence/rollback-runbook.md`
    with every required argument, write `evidence/modernization-contract.json`, then
    validate the handoff with `python -m catalog_acceptance.handoff_cli`.

## Evidence contract

The manual slice is complete only when all registry paths are nonempty and validated:

- Shared: `evidence/azure-target-output.json`, `evidence/migration-report.json`,
  `evidence/acceptance-report.json`, `evidence/runtime-test-report.json`,
  `evidence/telemetry-report.json`, `evidence/modernization-contract.json`, and
  `evidence/rollback-runbook.md`.
- Manual path: `evidence/baseline-backup.md`,
  `evidence/managed-database-separation.json`, `evidence/container-build.json`, and
  `evidence/iac-review.md`.

Keep raw native tests and normalized telemetry query results at the repository-relative
paths named by their evidence documents. Generated migration archives and deployment
parameter files are transient protected artifacts, not repository evidence.

## Stop and rejoin boundary

On any nonzero command, failed schema validation, topology mismatch, nonempty target,
digest mismatch, skipped full-acceptance check, missing telemetry signal, or unhealthy
rollback revision, stop before the next mutation. Preserve the JSON failure document and
current evidence, correct the failed prerequisite without deleting source data, and rerun
that checkpoint. Rejoin the common workshop only after handoff validation passes against
`workshop/contracts` and the release still passes health, readiness, native tests, full
acceptance, and telemetry verification.
