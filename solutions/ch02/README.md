# Challenge 2 solution: render evidence from raw Azure captures

**Open this when** you have tried [Challenge 2](../../challenges/ch02/README.md) and are
stuck on a specific step, or when you are facilitating and need the exact commands and
their fail-closed assertions.

This is the full reference run for the load and autoscaling chapter. Every block is
copy-pasteable, and every block stops the moment something is not true, so a participant
never builds evidence on top of a silent failure.

**Prerequisite deployment.** Two inputs come from `infra/perf-testing.bicep`, a
resource-group-scope template that must be deployed before a participant starts: an
Azure Load Testing resource (`LOAD_TEST_RESOURCE_ID`, from the `loadTestResourceId`
output) and an RBAC-authorized Key Vault holding the catalog performance-test API key
(`PERFTEST_API_KEY_SECRET_URI`, `<keyVaultUri>secrets/PERFTEST-API-KEY`). Deploy it after
`infra/github-cicd.bicep`, passing that template's `identityPrincipalId` output as
`workflowIdentityPrincipalId`. The template creates the vault but deliberately not the
secret **value** — set it once with `az keyvault secret set` using an identity holding
`Key Vault Secrets Officer`. Role assignments for the workflow identity and for the load
test's own system-assigned identity are created by the template. Exact commands:
[infra/README.md → *Challenge 2 performance-test prerequisites*](../../infra/README.md).

Run from the repository root in Bash. These commands read the existing handoff,
create or update only the named Azure Load Testing test, execute that test, and
read Azure state. They do not deploy the application, create a replacement
revision, change traffic, or edit infrastructure.

This procedure consumes `shared-challenges.json` version `1.2.0`, its
`loadEvidenceProtocol`, and `load-evidence-capture.schema.json` version `1.0.0`
without reinterpretation. The renderer emits the version `1.1.0` report and
normalized observations required by that protocol.

Expect roughly 75–110 minutes end to end, of which **at least 35 minutes is waiting**:
ten minutes of quiet baseline, about ten minutes of load-engine provisioning and the
300-second run, and up to fifteen minutes waiting for replicas to fall back to one.

Use the exact commands and stop on any error:

```bash
set -euo pipefail
umask 077

for command in az curl jq sha256sum uv; do
  command -v "$command" >/dev/null ||
    { printf 'Missing required command: %s\n' "$command" >&2; exit 1; }
done

HANDOFF=evidence/modernization-contract.json
RAW=evidence/load/raw
CAPTURE=evidence/load/capture.json
mkdir -p "$RAW"

(
  cd tests/acceptance
  uv --no-config run python -m catalog_acceptance.handoff_cli \
    ../../"$HANDOFF" \
    --contracts ../../workshop/contracts \
    --repository-root ../..
)
```

## 1. Bind the exact handoff

Everything downstream is identified by the validated Challenge 1 handoff, never by a
portal search. This block also picks the database metric for the stack — Azure SQL is
database-scoped, PostgreSQL emits `cpu_percent` at the server — and refuses to continue
unless the Load Testing resource ID and Key Vault secret URI from the
`infra/perf-testing.bicep` deployment are both present and well formed. The
`${VAR:?...}` guards below are the enforcement point: export both values before running
this step.

Derive them from the prerequisite deployment rather than from the portal — `DEPLOYMENT`
is the name of the `infra/perf-testing.bicep` deployment:

```bash
: "${RESOURCE_GROUP:?export the resource group holding the perf-testing deployment}"
: "${DEPLOYMENT:?export the infra/perf-testing.bicep deployment name}"

PERF_OUTPUTS=$(az deployment group show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$DEPLOYMENT" \
  --query properties.outputs \
  --output json)

export LOAD_TEST_RESOURCE_ID=$(jq -er '.loadTestResourceId.value' <<<"$PERF_OUTPUTS")
export PERFTEST_API_KEY_SECRET_URI="$(jq -er '.keyVaultUri.value' <<<"$PERF_OUTPUTS")secrets/PERFTEST-API-KEY"
```

The `keyVaultUri` output already ends in `/`, so the concatenation yields a valid secret
identifier. If `az keyvault secret show --vault-name "$(jq -er '.keyVaultName.value'
<<<"$PERF_OUTPUTS")" --name PERFTEST-API-KEY` returns nothing, the one-time
`az keyvault secret set` step has not been run yet.

```bash
SLICE_ID=$(jq -er '.sliceId' "$HANDOFF")
STACK=$(jq -er '.source.stack' "$HANDOFF")
DATABASE_FAMILY=$(jq -er '.database.family' "$HANDOFF")
SOURCE_COMMIT=$(jq -er '.source.commitSha' "$HANDOFF")
IMAGE_DIGEST=$(jq -er '.containerImage.digest' "$HANDOFF")
APP_RESOURCE_ID=$(jq -er '.application.resourceId' "$HANDOFF")
APP_REVISION=$(jq -er '.application.revisionName' "$HANDOFF")
APP_URL=$(jq -er '.application.url | rtrimstr("/")' "$HANDOFF")
HEALTH_URL=$(jq -er '.application.healthUrl' "$HANDOFF")
READINESS_URL=$(jq -er '.application.readinessUrl' "$HANDOFF")
DATABASE_RESOURCE_ID=$(jq -er '.database.resourceId' "$HANDOFF")

[[ "$SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]]
[[ "$IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]]
[[ "$APP_URL" =~ ^https://[^/]+$ ]]
[[ "$HEALTH_URL" == "$APP_URL/healthz" ]]
[[ "$READINESS_URL" == "$APP_URL/readyz" ]]
CATALOG_BASE_HOST=${APP_URL#https://}

# cpu_percent is emitted at the PostgreSQL flexible-server parent, not its
# handoff database child. Azure SQL remains database-scoped.
case "$DATABASE_FAMILY:$STACK" in
  azure-sql:dotnet-sqlserver)
    DATABASE_METRIC=app_cpu_billed
    DATABASE_AGGREGATION=Total
    DATABASE_METRIC_RESOURCE_ID=$DATABASE_RESOURCE_ID
    ;;
  postgresql-flexible:java-postgresql)
    DATABASE_METRIC=cpu_percent
    DATABASE_AGGREGATION=Maximum
    [[ "$DATABASE_RESOURCE_ID" == */flexibleServers/*/databases/* ]]
    DATABASE_METRIC_RESOURCE_ID=${DATABASE_RESOURCE_ID%/databases/*}
    [[ "$DATABASE_METRIC_RESOURCE_ID" == */flexibleServers/* ]]
    ;;
  *)
    printf 'Unsupported handoff database/stack pair: %s/%s\n' \
      "$DATABASE_FAMILY" "$STACK" >&2
    exit 1
    ;;
esac

: "${LOAD_TEST_RESOURCE_ID:?Set the exact Azure Load Testing resource ID}"
: "${PERFTEST_API_KEY_SECRET_URI:?Set the Key Vault secret identifier}"
[[ "$LOAD_TEST_RESOURCE_ID" =~ ^/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[^/]+/providers/Microsoft\.LoadTestService/loadTests/[^/]+$ ]]
[[ "$PERFTEST_API_KEY_SECRET_URI" =~ ^https://[^/]+\.vault\.azure\.net/secrets/[^/]+(/[^/]+)?$ ]]

LOAD_TEST_RESOURCE_JSON=$(
  az resource show --ids "$LOAD_TEST_RESOURCE_ID" --output json
)
jq -e --arg id "$LOAD_TEST_RESOURCE_ID" '
  (.id | ascii_downcase) == ($id | ascii_downcase)
  and (.type | ascii_downcase) == "microsoft.loadtestservice/loadtests"
' <<<"$LOAD_TEST_RESOURCE_JSON" >/dev/null
LOAD_TEST_RESOURCE_NAME=$(jq -er '.name' <<<"$LOAD_TEST_RESOURCE_JSON")
LOAD_TEST_RESOURCE_GROUP=$(jq -er '.resourceGroup' <<<"$LOAD_TEST_RESOURCE_JSON")
```

This flow applies unchanged to `manual-dotnet`, `manual-java`,
`copilot-rewrite-dotnet`, `copilot-rewrite-java`,
`copilot-modernization-dotnet`, and `copilot-modernization-java`.

## 2. Capture the scale configuration and a quiet baseline

Record what the target's scale rule actually is at the moment you observe it, then stay
off the app for ten minutes. The `etag` is what ties the recorded configuration to the
live resource; the ten minutes are what give Azure Monitor a one-replica data point to
compare the spike against.

Capture the raw Container App ARM response, including its `etag`. Do not extract
or normalize it.

```bash
SCALE_OBSERVED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
az rest \
  --method get \
  --url "https://management.azure.com${APP_RESOURCE_ID}?api-version=2024-03-01" \
  --output json >"$RAW/container-app.json"

jq -e --arg id "$APP_RESOURCE_ID" --arg revision "$APP_REVISION" '
  .id == $id
  and .type == "Microsoft.App/containerApps"
  and .properties.latestReadyRevisionName == $revision
  and .properties.provisioningState == "Succeeded"
  and .properties.template.scale.minReplicas == 1
  and .properties.template.scale.maxReplicas == 3
  and (.properties.template.scale.rules | length) == 1
  and .properties.template.scale.rules[0].name == "http"
  and .properties.template.scale.rules[0].http.metadata.concurrentRequests
    == "50"
  and (.etag | type == "string" and length > 0)
' "$RAW/container-app.json" >/dev/null

BASELINE_START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
sleep 600
```

The scale observation must be no more than 15 minutes before
`BASELINE_START`. The ten-minute baseline allows Azure Monitor to record the
required one-replica point before load.

## 3. Run the bounded JMeter test

This is the ~10-minute wait. Azure provisions a load engine, runs the plan for exactly
300 seconds, and deprovisions; the poll loop below is fail-closed on any status other
than the known in-flight set.

The JMX has one HTTPS `GET /perftest/catalog` sampler, 80 users, a 300-second
scheduler, HTTP `200` assertion, stop-on-sample-error behavior, and both
redirect modes disabled. The hostname comes from `CATALOG_BASE_HOST`; the API
key comes only from Azure Load Testing `GetSecret`.

```bash
TEST_ID=catalog-autoscaling
TEST_RUN_ID="catalog-autoscaling-$(date -u +%Y%m%dT%H%M%SZ)"

TEST_DEFINITION_JSON=$(
  az load test create \
    --load-test-resource "$LOAD_TEST_RESOURCE_NAME" \
    --resource-group "$LOAD_TEST_RESOURCE_GROUP" \
    --test-id "$TEST_ID" \
    --load-test-config-file tests/load/load-test.yaml \
    --env "CATALOG_BASE_HOST=$CATALOG_BASE_HOST" \
    --secret "PERFTEST_API_KEY=$PERFTEST_API_KEY_SECRET_URI" \
    --output json
)
jq -e --arg testId "$TEST_ID" '.testId == $testId' \
  <<<"$TEST_DEFINITION_JSON" >/dev/null

TEST_RUN_START_JSON=$(
  az load test-run create \
    --load-test-resource "$LOAD_TEST_RESOURCE_NAME" \
    --resource-group "$LOAD_TEST_RESOURCE_GROUP" \
    --test-id "$TEST_ID" \
    --test-run-id "$TEST_RUN_ID" \
    --display-name "$TEST_RUN_ID" \
    --description "Bounded catalog autoscaling evidence" \
    --output json
)
jq -e --arg testId "$TEST_ID" --arg runId "$TEST_RUN_ID" '
  .testId == $testId and .testRunId == $runId
' <<<"$TEST_RUN_START_JSON" >/dev/null

while :; do
  az load test-run show \
    --load-test-resource "$LOAD_TEST_RESOURCE_NAME" \
    --resource-group "$LOAD_TEST_RESOURCE_GROUP" \
    --test-run-id "$TEST_RUN_ID" \
    --output json >"$RAW/test-run.json"
  RUN_STATUS=$(jq -er '.status' "$RAW/test-run.json")
  case "$RUN_STATUS" in
    DONE) break ;;
    ACCEPTED|PROVISIONING|CONFIGURING|EXECUTING|DEPROVISIONING) sleep 15 ;;
    *)
      printf 'Azure Load Testing run stopped in status: %s\n' \
        "$RUN_STATUS" >&2
      exit 1
      ;;
  esac
done

jq -e --arg testId "$TEST_ID" --arg runId "$TEST_RUN_ID" '
  .testId == $testId
  and .testRunId == $runId
  and .status == "DONE"
  and .duration == 300000
  and .virtualUsers == 80
  and .testRunStatistics.Total.sampleCount > 0
  and .testRunStatistics.Total.errorCount == 0
' "$RAW/test-run.json" >/dev/null

LOAD_START=$(jq -er '.executionStartDateTime' "$RAW/test-run.json")
LOAD_END=$(jq -er '.executionEndDateTime' "$RAW/test-run.json")
```

Do not use request time or polling time in place of the Azure engine timestamps.
Any redirect remains a 3xx response and fails the HTTP `200` assertion.

## 4. Capture exact database and revision-filtered replica metrics

Two series matter here and they answer two different questions: the database metric
answers "did the extra replicas reach the data tier?", and the revision-filtered
`Replicas` series answers "did this revision — not some neighbour — add and release
capacity?". Getting the `revisionName` filter wrong is the single most common way to
produce a series that looks right and proves nothing.

Capture the database window through the observed run end:

```bash
az monitor metrics list \
  --resource "$DATABASE_METRIC_RESOURCE_ID" \
  --metric "$DATABASE_METRIC" \
  --aggregation "$DATABASE_AGGREGATION" \
  --interval PT1M \
  --start-time "$BASELINE_START" \
  --end-time "$LOAD_END" \
  --output json >"$RAW/database.json"
```

Poll only to observe recovery; every Azure command remains fail-closed. The
canonical replica response must use `Maximum`, `PT1M`, and exactly one time
series filtered to the handoff revision.

```bash
LOAD_END_EPOCH=$(jq -er '
  .executionEndDateTime
  | sub("\\.[0-9]+Z$"; "Z")
  | fromdateiso8601
' "$RAW/test-run.json")
RECOVERY_DEADLINE=$(( LOAD_END_EPOCH + 900 ))
while (( $(date +%s) <= RECOVERY_DEADLINE )); do
  CANDIDATE_END=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  az monitor metrics list \
    --resource "$APP_RESOURCE_ID" \
    --metric Replicas \
    --aggregation Maximum \
    --interval PT1M \
    --filter "revisionName eq '$APP_REVISION'" \
    --start-time "$BASELINE_START" \
    --end-time "$CANDIDATE_END" \
    --output json >"$RAW/replicas.json"
  if jq -e '
    .interval == "PT1M"
    and (.value | length) == 1
    and (.value[0].timeseries | length) == 1
    and .value[0].timeseries[0].metadatavalues[0].name.value
      == "revisionName"
    and [
      .value[0].timeseries[0].data[]
      | select(.maximum != null)
    ][-1].maximum == 1
  ' "$RAW/replicas.json" >/dev/null; then
    break
  fi
  sleep 30
done

(( $(date +%s) <= RECOVERY_DEADLINE )) ||
  { printf 'Replicas did not recover to one within 900 seconds\n' >&2; exit 1; }

HEALTH_STATUS=$(curl --silent --show-error --output /dev/null \
  --write-out '%{http_code}' "$HEALTH_URL")
READINESS_STATUS=$(curl --silent --show-error --output /dev/null \
  --write-out '%{http_code}' "$READINESS_URL")
[[ "$HEALTH_STATUS" == 200 ]]
[[ "$READINESS_STATUS" == 200 ]]

RECOVERY_OBSERVED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
RECOVERY_OBSERVED_EPOCH=$(jq -nr --arg value "$RECOVERY_OBSERVED_AT" '
  $value | fromdateiso8601
')
(( RECOVERY_OBSERVED_EPOCH <= RECOVERY_DEADLINE )) ||
  { printf 'Recovery was observed more than 900 seconds after load\n' >&2; exit 1; }
az monitor metrics list \
  --resource "$APP_RESOURCE_ID" \
  --metric Replicas \
  --aggregation Maximum \
  --interval PT1M \
  --filter "revisionName eq '$APP_REVISION'" \
  --start-time "$BASELINE_START" \
  --end-time "$RECOVERY_OBSERVED_AT" \
  --output json >"$RAW/replicas.json"

jq -e --arg revision "$APP_REVISION" '
  .interval == "PT1M"
  and (.value | length) == 1
  and (.value[0].timeseries | length) == 1
  and .value[0].timeseries[0].metadatavalues == [{
    name: {
      value: "revisionName",
      localizedValue:
        .value[0].timeseries[0].metadatavalues[0].name.localizedValue
    },
    value: $revision
  }]
  and [
    .value[0].timeseries[0].data[]
    | select(.maximum != null)
  ][-1].maximum == 1
' "$RAW/replicas.json" >/dev/null
```

The renderer—not shell logic—proves one replica immediately before load,
two-to-three during `LOAD_START..LOAD_END`, final one after load, all values
within `1..3`, and database peak above baseline. Therefore a scale-out occurring
only after `LOAD_END` fails.

## 5. Hash raw inputs into the canonical capture manifest

The manifest is the join between "what Azure said" and "what the report claims". Hash the
exact four raw Azure responses and both checked-in assets:

```bash
sha256_file() {
  sha256sum "$1" | awk '{print $1}'
}

TEST_RUN_SHA=$(sha256_file "$RAW/test-run.json")
CONTAINER_APP_SHA=$(sha256_file "$RAW/container-app.json")
REPLICAS_SHA=$(sha256_file "$RAW/replicas.json")
DATABASE_SHA=$(sha256_file "$RAW/database.json")
CONFIGURATION_SHA=$(sha256_file tests/load/load-test.yaml)
JMETER_SHA=$(sha256_file tests/load/catalog-load.jmx)
CAPTURED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
REPLICA_END=$(jq -er '.timespan | split("/")[1]' "$RAW/replicas.json")
DATABASE_END=$(jq -er '.timespan | split("/")[1]' "$RAW/database.json")

jq -n \
  --arg capturedAt "$CAPTURED_AT" \
  --arg baselineStart "$BASELINE_START" \
  --arg testRunFile "evidence/load/raw/test-run.json" \
  --arg testRunSha "$TEST_RUN_SHA" \
  --arg loadTestResourceId "$LOAD_TEST_RESOURCE_ID" \
  --arg scaleFile "evidence/load/raw/container-app.json" \
  --arg scaleSha "$CONTAINER_APP_SHA" \
  --arg scaleObservedAt "$SCALE_OBSERVED_AT" \
  --arg replicasFile "evidence/load/raw/replicas.json" \
  --arg replicasSha "$REPLICAS_SHA" \
  --arg appResourceId "$APP_RESOURCE_ID" \
  --arg replicaEnd "$REPLICA_END" \
  --arg revision "$APP_REVISION" \
  --arg databaseFile "evidence/load/raw/database.json" \
  --arg databaseSha "$DATABASE_SHA" \
  --arg databaseResourceId "$DATABASE_METRIC_RESOURCE_ID" \
  --arg databaseMetric "$DATABASE_METRIC" \
  --arg databaseAggregation "$DATABASE_AGGREGATION" \
  --arg databaseEnd "$DATABASE_END" \
  --arg recoveryObservedAt "$RECOVERY_OBSERVED_AT" \
  --arg healthUrl "$HEALTH_URL" \
  --arg readinessUrl "$READINESS_URL" \
  --arg configurationSha "$CONFIGURATION_SHA" \
  --arg jmeterSha "$JMETER_SHA" '
  {
    schemaVersion: "1.0.0",
    capturedAt: $capturedAt,
    baselineStart: $baselineStart,
    testRun: {
      file: $testRunFile,
      sha256: $testRunSha,
      resourceId: $loadTestResourceId
    },
    scaleConfiguration: {
      file: $scaleFile,
      sha256: $scaleSha,
      observedAt: $scaleObservedAt
    },
    replicas: {
      file: $replicasFile,
      sha256: $replicasSha,
      resourceId: $appResourceId,
      metricName: "Replicas",
      aggregation: "Maximum",
      interval: "PT1M",
      start: $baselineStart,
      end: $replicaEnd,
      revisionName: $revision
    },
    databaseSignal: {
      file: $databaseFile,
      sha256: $databaseSha,
      resourceId: $databaseResourceId,
      metricName: $databaseMetric,
      aggregation: $databaseAggregation,
      interval: "PT1M",
      start: $baselineStart,
      end: $databaseEnd
    },
    recovery: {
      observedAt: $recoveryObservedAt,
      healthUrl: $healthUrl,
      healthStatus: 200,
      readinessUrl: $readinessUrl,
      readinessStatus: 200
    },
    artifacts: {
      configurationFile: "tests/load/load-test.yaml",
      configurationSha256: $configurationSha,
      jmeterFile: "tests/load/catalog-load.jmx",
      jmeterSha256: $jmeterSha
    }
  }
' >"$CAPTURE"
```

`workshop/contracts/load-evidence-capture.example.json` and the raw fixtures are
sanitized structure and are not live proof. Never copy their identifiers or
hashes into a live manifest.

## 6. Render, then validate

Do not manually write or modify the report or normalized observations. Run the
frozen renderer and then the common validator:

```bash
(
  cd tests/acceptance
  uv --no-config run catalog-render-load-evidence \
    --capture evidence/load/capture.json \
    --handoff evidence/modernization-contract.json \
    --output evidence/load-test-report.json \
    --repository-root ../..

  uv --no-config run catalog-validate-challenge-evidence load \
    evidence/load-test-report.json \
    --handoff evidence/modernization-contract.json \
    --contracts workshop/contracts \
    --repository-root ../..
)
```

The renderer deterministically writes `evidence/load-test-report.json` version
`1.1.0` plus `test-run.json`, `scale-configuration.json`, `replicas.json`,
`database.json`, and `recovery.json` under `evidence/load/`. The validator
re-renders from the digest-bound raw captures, so manual normalized evidence,
changed raw data, or changed assets fail closed.

## If it goes wrong

| Symptom | Cause | Fix |
| --- | --- | --- |
| `LOAD_TEST_RESOURCE_ID` or `PERFTEST_API_KEY_SECRET_URI` is unset, or `az resource show` cannot find the resource | `infra/perf-testing.bicep` has not been deployed to this resource group | Deploy it and set the `PERFTEST-API-KEY` secret value, then re-run step 1. See [infra/README.md](../../infra/README.md) |
| `az load test create --secret` cannot resolve the secret | The load test's system-assigned identity lacks `Key Vault Secrets User`, or the secret value was never set | Redeploy `infra/perf-testing.bicep` (it creates that role assignment) and confirm `az keyvault secret show --name PERFTEST-API-KEY` returns a value |
| The run ends with `errorCount` above zero | The sampler received a 3xx or 4xx — usually a wrong or unreadable `x-api-key` | Confirm the Key Vault secret holds the catalog performance-test key and the Load Testing identity can read it. Redirects are intentionally not followed, so a 3xx fails the `200` assertion |
| The replica jq assertion fails on time-series length | The metric query was issued without the `revisionName` filter, or against the wrong resource | Re-issue with `--filter "revisionName eq '$APP_REVISION'"` against `APP_RESOURCE_ID` |
| Replicas never return to one inside 900 seconds | The recovery poll started before the engine finished deprovisioning, or traffic is still arriving | Confirm the run is `DONE` and nothing else is calling the app, then re-run the recovery loop |
| The validator reports digest drift | A raw file was re-captured, reformatted, or pretty-printed after hashing | Re-hash the exact bytes now on disk and re-render; never hand-edit normalized evidence |

The broader diagnostic workflow is in
[the troubleshooting guide](../../docs/Troubleshooting.md).

## What a completed run shows

`evidence/load-test-report.json` now carries the chapter's headline numbers: replicas
moving `1 → 2` or `3` and back to `1`, zero errors across 80 virtual users for 300
seconds, and a database peak above its own pre-load baseline. Those are the figures to
read aloud in the debrief — they are the first quantitative answer the retailer has ever
had to "what happens when it gets busy?".

---

**Back to** [Challenge 2: make the catalog survive a traffic spike](../../challenges/ch02/README.md)
**Next solution:** [Challenge 3 solution](../ch03/README.md)
