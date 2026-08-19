# Java/PostgreSQL bounded Copilot rewrite reference

This is a runnable reference slice, not a complete rewrite to copy and paste. Work
from the repository root unless a command changes directory. Replace angle-bracket
values from the participant environment; never commit those values or shell history
containing secrets.

## Registered boundary

`copilot-rewrite-java` resolves to:

| Interface | Exact value |
| --- | --- |
| Source | `java/` |
| Dockerfile | `java/Dockerfile` |
| Database family | `postgresql-flexible` |
| Image provider | `azure-blob` |
| Tools | `github.copilot`, `github.copilot-chat` |
| Infrastructure | `infra/main.bicep` |
| Migration | `catalog-migrate` |

The pinned tools are `github.copilot@1.388.0` and
`github.copilot-chat@0.48.1`. Do not install or invoke any modernization or
migration extension for this path.

## 1. Preflight and characterization checkpoint

**Executable proof**

```bash
test "$(git rev-parse --show-toplevel)" = "$PWD"
git status --short
code --list-extensions --show-versions \
  | grep -E '^(github\.copilot@1\.388\.0|github\.copilot-chat@0\.48\.1)$'
mkdir -p evidence .workshop-tmp
./java/mvnw -f java/pom.xml test
cp -R java/target/surefire-reports .workshop-tmp/java-characterization
cd tests/acceptance
UV_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple \
  uv --no-config run pytest -q tests/test_contract_assets.py
cd ../..
```

Start the unchanged application and disposable PostgreSQL using `java/README.md`,
then run full shared acceptance against that baseline. Record the exact application
command, database target, Surefire result, acceptance report, and known failures in
`evidence/characterization.md`. The characterization and acceptance suites are the
behavioral oracle.

**Expected checkpoint**

- native tests and contract assets pass;
- the baseline routes, PostgreSQL schema, import transaction, image keys, degraded
  states, configuration, errors, and telemetry are documented;
- no implementation file has changed.

## 2. Human-reviewed bounded plan

Write `evidence/bounded-plan.md` before asking for code. A suitable sequence is:

1. domain identity, text validation, Flyway ownership, and PostgreSQL schema;
2. transactional import and query behavior;
3. local/Blob image abstraction and image-key security;
4. external configuration, managed identity, health, readiness, and bounded
   performance;
5. telemetry and the existing non-root Container Apps image.

For every slice, list exact files, tests, exclusions, and how to return to the last
passing commit. A human must approve the plan and must review schema, security,
dependencies, configuration, errors, and each generated diff.

**Suggested prompt, not proof**

> Read `workshop/contracts`, `tests/acceptance`, the current Java tests, and
> `java/Dockerfile`. Propose only the next bounded slice. Preserve PostgreSQL
> Flexible Server, one application container, Blob images, ACA readiness, external
> configuration, routes, failure behavior, and telemetry. Do not edit frozen
> interfaces or add services. Name exact tests and wait for approval before
> generating a diff.

## 3. Slice loop

Ask for and accept one generated diff at a time.

**Suggested prompt, not proof**

> Implement only approved slice `<slice-name>`. Keep changes inside the listed Java
> files. Add or update focused tests for the characterized behavior. Do not change
> database family, infrastructure, migration, deployment topology, or unrelated
> dependencies. Surface configuration and errors explicitly.

**Executable proof after every generated diff**

```bash
git diff -- java
./java/mvnw -f java/pom.xml test
rm -rf .workshop-tmp/java-<slice-name>
mkdir -p .workshop-tmp/java-<slice-name>
cp -R java/target/surefire-reports .workshop-tmp/java-<slice-name>/
cd tests/acceptance
UV_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple \
  uv --no-config run pytest -q tests/test_contract_assets.py
cd ../..
git diff --check
```

Record the human decision and command result in
`evidence/review-checklist.md`. Reject the diff rather than patching around a
contract failure.

**Stop and replan** if a slice changes Flyway-owned schema without explicit review,
weakens canonical image-key checks, adds credentials to source, adds a broad catch,
changes one-container topology, requires a frozen-interface edit, introduces an
unreviewed dependency, or fails characterization/acceptance. Return to the last
passing slice, update `bounded-plan.md`, and obtain approval again.

## 4. Container and immutable registry checkpoint

Build the checked-in Dockerfile; do not generate a parallel container definition.

**Executable proof**

```bash
SOURCE_COMMIT="$(git rev-parse HEAD)"
test "$(printf '%s' "$SOURCE_COMMIT" | grep -E '^[0-9a-f]{40}$')"
docker buildx build --platform linux/amd64 --load \
  -f java/Dockerfile \
  -t "catalog-java:$SOURCE_COMMIT" .
docker image inspect "catalog-java:$SOURCE_COMMIT" \
  --format '{{json .Config.User}} {{json .Config.ExposedPorts}}'
```

After facilitator-approved authentication, publish the same commit-tagged image to
the P4 ACR. The tag is used only to locate evidence. Resolve the registry digest
with the exact frozen command:

```bash
IMAGE_DIGEST="$(
  AZURE_CONFIG_DIR="$HOME/.azure-365" az acr manifest show-metadata \
    --registry "<registryName>" \
    --name "catalog-java:$SOURCE_COMMIT" \
    --subscription "<subscriptionId>" \
    --query digest \
    --output tsv
)"
test "$(printf '%s' "$IMAGE_DIGEST" | grep -E '^sha256:[0-9a-f]{64}$')"
IMAGE_REFERENCE="<loginServer>/catalog-java@$IMAGE_DIGEST"
printf '%s\n' "$IMAGE_REFERENCE"
```

Only `IMAGE_REFERENCE`, which is immutable, may reach the application deployment.
Do not deploy `latest`, the commit tag, or any other mutable reference.

## 5. P4 Bicep and native data transfer checkpoint

Use protected parameter documents outside the repository. They supply every required
value from `infra/main.bicep`, including secure values, source VM/VNet resource IDs,
facilitator identity, lowercase source commit, and the fixed
`java-postgresql`/`azure-blob` selection. Prefer managed-identity application
authentication; if the approved scenario selects `password-secret`, keep the
application password only in protected parameters and the exact migration
environment variable. The following commands are participant deployment steps; this
reference does not claim they were run.

**Executable proof**

```bash
AZURE_CONFIG_DIR="$HOME/.azure-365" az deployment sub create \
  --name "p5-java-bootstrap-$SOURCE_COMMIT" \
  --location swedencentral \
  --template-file infra/main.bicep \
  --parameters @/protected/p5-java-bootstrap.json \
  --query properties.outputs.targetOutput.value \
  --output json > evidence/azure-target-output.json

TARGET_DATABASE_RESOURCE_ID="$(
  python -c 'import json; print(json.load(open("evidence/azure-target-output.json"))["database"]["resourceId"])'
)"
TARGET_IMAGE_RESOURCE_ID="$(
  python -c 'import json; print(json.load(open("evidence/azure-target-output.json"))["images"]["resourceId"])'
)"
```

Run migration on the exact source VM declared by the bootstrap target output. Keep
passwords only in the command-specific `MIGRATION_*` environment variables.
Managed-identity mode requires `MIGRATION_TARGET_ADMINISTRATOR_PASSWORD` and forbids
`MIGRATION_TARGET_APPLICATION_PASSWORD`.

```bash
cd tests/acceptance
uv --no-config run catalog-migrate postgresql export \
  --source-host "<source-postgresql-host>" \
  --source-port 5432 \
  --source-database "<source-database>" \
  --source-username "<source-user>" \
  --target-output ../../evidence/azure-target-output.json \
  --artifact /protected/catalog.dump

uv --no-config run catalog-migrate postgresql import \
  --artifact /protected/catalog.dump \
  --target-output ../../evidence/azure-target-output.json \
  --target-resource-id "$TARGET_DATABASE_RESOURCE_ID" \
  --confirm-target-resource-id "$TARGET_DATABASE_RESOURCE_ID" \
  --execute

uv --no-config run catalog-migrate images copy \
  --source-directory ../../data/images \
  --target-output ../../evidence/azure-target-output.json \
  --target-resource-id "$TARGET_IMAGE_RESOURCE_ID" \
  --confirm-target-resource-id "$TARGET_IMAGE_RESOURCE_ID" \
  --execute

uv --no-config run catalog-migrate verify \
  --stack java-postgresql \
  --source-commit "$SOURCE_COMMIT" \
  --database-artifact /protected/catalog.dump \
  --target-output ../../evidence/azure-target-output.json \
  --output ../../evidence/migration-report.json
cd ../..
```

The CLI is the only data-transfer path. It must refuse a nonempty target, verify Blob
bytes and PostgreSQL contents, bind the workload principal from target output, and
leave the source and artifact available for rollback.

Deploy `baseline` and then `release` with the same `IMAGE_DIGEST` through
`infra/main.bicep`. Keep the healthy baseline revision inactive and retained. Capture
the release deployment's `targetOutput` as
`evidence/azure-target-output.json`; it must describe one application container and
the digest reference, not a tag.

## 6. Full evidence and handoff checkpoint

Run the native suite after the final diff and retain the native Surefire JUnit XML
under `evidence/`. Create `evidence/runtime-test-report.json` against
`workshop/contracts/runtime-test-evidence.schema.json`; it must reference those
native reports and their fourteen real passing test identities. Run full shared
acceptance against the release and write
`evidence/acceptance-report.json`. Collect real trace, metric, log, and resource
query results into `evidence/telemetry-report.json`; never synthesize telemetry.

Complete:

- `evidence/decision-log.md` with accepted/rejected design choices;
- `evidence/rollback-runbook.md` with prerequisites, exact retained baseline
  revision, traffic restoration, database/artifact boundaries, verification, and
  escalation;
- all registry-required shared and path evidence.

The frozen protocol is
`catalog-migrate render-handoff --path copilot-rewrite --rollback-runbook <path>`.

**Executable proof**

```bash
cd tests/acceptance
uv --no-config run catalog-migrate render-handoff \
  --target-output ../../evidence/azure-target-output.json \
  --migration-report ../../evidence/migration-report.json \
  --acceptance-report ../../evidence/acceptance-report.json \
  --telemetry-report ../../evidence/telemetry-report.json \
  --runtime-test-report ../../evidence/runtime-test-report.json \
  --path copilot-rewrite \
  --rollback-revision "<containerAppName>--baseline-${SOURCE_COMMIT:0:12}" \
  --rollback-runbook ../../evidence/rollback-runbook.md \
  --output ../../evidence/modernization-contract.json

uv --no-config run python -m catalog_acceptance.handoff_cli \
  ../../evidence/modernization-contract.json \
  --contracts ../../workshop/contracts \
  --repository-root ../..
cd ../..
```

**Expected checkpoint**

Full acceptance passes with no required skips, native runtime and telemetry evidence
validate, the handoff reports path `copilot-rewrite`, database family
`postgresql-flexible`, Blob verification, one digest-pinned image, and a distinct
retained rollback revision.

## Cleanup and rejoin

Remove only local transient artifacts after evidence has been copied:

```bash
rm -rf .workshop-tmp
git status --short
```

Do not remove `evidence/`, migration artifacts, or the retained baseline revision.
Rejoin the shared workshop at the next challenge only after handoff validation passes
and a human signs `review-checklist.md`, `decision-log.md`, and the rollback runbook.
