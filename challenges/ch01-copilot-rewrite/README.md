# Path 1B: bounded rewrite with standard GitHub Copilot

Use the pinned standard GitHub Copilot tools to rewrite one small, reviewed slice at a
time while the existing characterization and acceptance tests remain the behavioral
oracle. This path is not an open-ended redesign and does not use a modernization or
migration extension.

## Frozen path

Choose exactly one registered slice in
`workshop/contracts/challenge-paths.json`:

| Slice | Source | Database family | Image provider | Solution |
| --- | --- | --- | --- | --- |
| `copilot-rewrite-dotnet` | `dotnet/` | `azure-sql` | `azure-blob` | [Guide](../../solutions/ch01-copilot-rewrite/dotnet/README.md) |
| `copilot-rewrite-java` | `java/` | `postgresql-flexible` | `azure-blob` | [Guide](../../solutions/ch01-copilot-rewrite/java/README.md) |

The only assisted-development tools are `github.copilot` and
`github.copilot-chat`, at the versions pinned by `workshop/toolchain.lock.json`.
Treat the registry, its schema, modernization handoff 1.3.0, migration CLI 1.3.0,
`infra/main.bicep`, the selected stack Dockerfile, and `tests/acceptance` as
read-only interfaces.

## Required target

The completed rewrite must preserve all of these boundaries:

- one application container and no extra application services;
- the selected database family, hosted as a separate managed database;
- the `azure-blob` image provider with workload-identity access;
- Container Apps liveness and readiness behavior;
- externalized runtime configuration and secrets supplied outside source control;
- the frozen routes, data identity, import transaction, error behavior, security
  behavior, and OpenTelemetry signals.

Characterization and acceptance results decide whether behavior is preserved.
Copilot output, a successful compile, screenshots, and prompt transcripts are not
proof.

## Evidence and checkpoints

Create `evidence/` at the repository root. Preserve the shared evidence required by
the registry plus:

- `evidence/characterization.md`
- `evidence/bounded-plan.md`
- `evidence/review-checklist.md`
- `evidence/decision-log.md`

Use these checkpoints in order:

1. **Characterization checkpoint**: run the native suite and shared acceptance
   against the unchanged source. Record commands, results, known failures, routes,
   schema, configuration, and dependency behavior in `characterization.md`.
2. **Bounded-plan checkpoint**: write a human-reviewed plan in `bounded-plan.md`.
   Every slice must name its files, behavior, tests, exclusions, and rollback. The
   plan must explicitly preserve the database family, single-container boundary,
   Blob provider, and frozen infrastructure and migration contracts.
3. **Diff-review checkpoints**: ask Copilot for one slice only. A human reviews the
   schema, security, dependencies, configuration, error handling, and every
   generated diff before accepting it. Record the review in `review-checklist.md`,
   then run the relevant native tests and shared acceptance tests.
4. **Container checkpoint**: build the existing stack Dockerfile from the repository
   root. Prove non-root execution, port `8080`, `/healthz`, `/readyz`, external
   configuration, and exactly one application container.
5. **Migration checkpoint**: use only native `catalog-migrate` export, import,
   image-copy, and verify commands. Retain the source and migration artifact. Do not
   add application-managed data transfer.
6. **Release checkpoint**: deploy only through the frozen P4
   `infra/main.bicep` stages. Resolve the source-commit tag through the registry
   evidence command and deploy `<loginServer>/<repository>@<digest>`, never a tag.
7. **Handoff checkpoint**: complete native runtime evidence, full acceptance,
   telemetry evidence, `decision-log.md`, and `rollback-runbook.md`. Render and
   validate modernization handoff 1.3.0.

Run tests after every accepted slice. A failing or skipped required test is not a
checkpoint.

## Suggested prompts

Prompts guide the assistant; they are not executable proof and are never graded for
wording.

> Read the frozen contracts and current tests. Propose one bounded slice only. List
> exact files, behavior preserved, tests to run, and explicit exclusions. Do not
> edit infrastructure, migration tooling, contracts, or unrelated architecture.

> For this slice, first explain the existing schema, security, configuration, error,
> and dependency behavior. Then propose the smallest diff that preserves it. Do not
> generate code until I approve the plan.

> Review this generated diff against characterization and acceptance. Identify any
> behavior change, secret exposure, mutable image reference, new service boundary,
> database-family change, or swallowed error. Recommend rejection if uncertain.

## Stop and replan

Stop the current slice, discard only its unaccepted generated diff, and return to the
last passing checkpoint when any of these occurs:

- a frozen contract, shared test, P4 Bicep file, or migration command would need to
  change;
- the proposed design adds a service, container, database technology, or
  application-managed transfer path;
- a diff introduces a secret, mutable deployment reference, broad exception
  handling, undocumented configuration, or an unreviewed dependency;
- native or shared acceptance behavior changes, required telemetry is absent, or the
  test failure cannot be explained within the approved slice.

Update `bounded-plan.md` and obtain human approval before continuing.

## Cleanup

Remove only local transient build, test, and prompt-scratch artifacts after their
accepted results have been copied into `evidence/`. Keep migration artifacts,
required evidence, and the retained rollback revision. Confirm the repository diff
contains only the approved rewrite slice before rejoining.

## Rejoin the workshop

Rejoin the shared path only after both the native suite and full acceptance pass and
all required evidence is present. The final command protocol is
`catalog-migrate render-handoff --path copilot-rewrite --rollback-runbook <path>`;
use the stack guide for its complete executable form. Validate
`evidence/modernization-contract.json` with
`python -m catalog_acceptance.handoff_cli` before handing it to the next challenge.
