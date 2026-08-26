# Challenge 4 solution: one handoff-bound workbook

**Open this when** you have attempted [Challenge 4](../../challenges/ch04/README.md) and
need the exact deployment, capture, and normalization commands — or when you are
facilitating and need the per-query row contract at hand.

This solution preserves the target's direct Azure Monitor exporter and adds only two Azure
resources: one workbook and one `AllMetrics` diagnostic setting on the existing Container
App. Azure diagnostic-settings metric export flattens dimensions, so the replica panel
uses app-total `AzureMetrics` data. It does not claim revision-level scale evidence;
Challenge 2 owns that proof.

## 1. Confirm the modernization evidence chain

Everything here is identified by the Challenge 1 handoff. Validate
`evidence/modernization-contract.json` before proceeding. Copy values from the
validated document, not from portal search results:

```bash
cd tests/acceptance
uv --no-config run python -m catalog_acceptance.handoff_cli \
  ../../evidence/modernization-contract.json \
  --contracts ../../workshop/contracts \
  --repository-root ../..
cd ../..
```

Confirm that the handoff's `evidence.telemetryReport` is
`evidence/telemetry-report.json` and that its referenced normalized resources, traces,
metrics, and logs are still present. The report's service name, namespace, environment,
version/source commit, instance, and ACA revision must match the handoff.

The validated handoff proves that these resources share
`application.resourceGroup`:

- `application.resourceId`;
- `observability.applicationInsightsResourceId`;
- `observability.logAnalyticsWorkspaceResourceId`.

Stop if they do not. Do not work around a cross-resource-group handoff.

## 2. Select one immutable window

The window is the single most common cause of a failed capture: every panel must return a
real row inside it. The Challenge 2 load run is usually the best choice, because it
contains request volume, replica movement, and new instances in one bounded period.

Choose explicit UTC `QUERY_START_TIME` and `QUERY_END_TIME` values that enclose exercised
HTTP failures, database dependency failures, Container App replica activity, and at least
one first request for an exact revision instance. Do not use `ago()` or a moving workbook
time picker. The same values must appear in Bicep parameters, every normalized query
observation, and `evidence/observability-report.json`.

## 3. Deploy to the handoff resource group

Review `infra/observability-workbook.bicep`. Its existing resources are same-scope
declarations, and its assertions require all supplied IDs to resolve to the current
subscription and resource group. Deploy the resource-group template to the handoff's
exact `application.resourceGroup`:

```bash
HANDOFF=evidence/modernization-contract.json
HANDOFF_APPLICATION_RESOURCE_GROUP=$(jq -er '.application.resourceGroup' "$HANDOFF")
CONTAINER_APP_RESOURCE_ID=$(jq -er '.application.resourceId' "$HANDOFF")
APPLICATION_INSIGHTS_RESOURCE_ID=$(jq -er '.observability.applicationInsightsResourceId' "$HANDOFF")
LOG_ANALYTICS_WORKSPACE_RESOURCE_ID=$(jq -er '.observability.logAnalyticsWorkspaceResourceId' "$HANDOFF")
SERVICE_NAME=$(jq -er '.observability.serviceName' "$HANDOFF")
SOURCE_COMMIT=$(jq -er '.observability.serviceVersion' "$HANDOFF")
REVISION_NAME=$(jq -er '.observability.revision' "$HANDOFF")

# The window you fixed in step 2. Nothing can derive these for you.
: "${QUERY_START_TIME:?export the inclusive UTC window start, e.g. 2025-01-01T10:00:00Z}"
: "${QUERY_END_TIME:?export the inclusive UTC window end, e.g. 2025-01-01T10:30:00Z}"

WORKBOOK_DEPLOYMENT=$(az deployment group create \
  --resource-group "$HANDOFF_APPLICATION_RESOURCE_GROUP" \
  --template-file infra/observability-workbook.bicep \
  --parameters \
    applicationInsightsResourceId="$APPLICATION_INSIGHTS_RESOURCE_ID" \
    logAnalyticsWorkspaceResourceId="$LOG_ANALYTICS_WORKSPACE_RESOURCE_ID" \
    containerAppResourceId="$CONTAINER_APP_RESOURCE_ID" \
    serviceName="$SERVICE_NAME" \
    sourceCommit="$SOURCE_COMMIT" \
    revisionName="$REVISION_NAME" \
    queryStartTime="$QUERY_START_TIME" \
    queryEndTime="$QUERY_END_TIME" \
  --output json)

WORKBOOK_RESOURCE_ID=$(jq -er '.properties.outputs.workbookResourceId.value' \
  <<<"$WORKBOOK_DEPLOYMENT")
```

Every identity above comes from the validated handoff, so a stale portal copy cannot
enter the deployment. `jq -er` fails on a missing or null field rather than passing an
empty string that Bicep would reject with a less obvious message. The
`.observability.serviceVersion` field is the same 40-hex commit as `.source.commitSha`;
the handoff validator asserts they agree.

`WORKBOOK_RESOURCE_ID` comes from the deployment that just created the workbook — the
`workbookResourceId` output of `infra/observability-workbook.bicep` — so the ID you
capture in step 4 is necessarily the resource this step produced. Do not read it from the
portal: the workbook name is a `guid()` derived from the workspace ID, so a hand-copied ID
is both unmemorable and unverifiable. The same `jq -er` applies, and step 4 consumes the
binding made here.

The deployment creates only the workbook and `all-metrics-to-workspace` diagnostic
setting. It does not create a DCR, alternate pipeline, Application Insights component,
workspace, Container App, or revision. Capture actual deployment timestamps.

## 4. Capture deployment truth

Save unmodified responses separately before normalization:

```bash
mkdir -p evidence/observability/raw
az monitor diagnostic-settings show \
  --name all-metrics-to-workspace \
  --resource "$CONTAINER_APP_RESOURCE_ID" \
  > evidence/observability/raw/metrics-export-arm.json
az resource show \
  --ids "$WORKBOOK_RESOURCE_ID" \
  --api-version 2023-06-01 \
  > evidence/observability/raw/workbook-arm.json
```

Use frozen observability evidence shape `1.1.0`:

- The report's `metricsExport` records the exact Container App/workspace IDs, setting name,
  `AllMetrics`, `destinationTable: "AzureMetrics"`,
  `scope: "container-app-total"`, `dimensionHandling: "flattened"`, deployment time, and
  normalized result path.
- `evidence/observability/metrics-export.json` records the exact resources, diagnostic
  setting, `AllMetrics`, `AzureMetrics`, enabled state, and observed time.
- `evidence/observability/workbook.json` records the workbook resource ID, exact
  Application Insights and workspace IDs, ARM `sourceId`, API version `2023-06-01`,
  source commit, revision, checked-in file hashes, exact ARM `serializedData`, its hash,
  deployment time, and capture time.
- Report assertions use
  `applicationTelemetryRevisionFilterApplied: true`; the old
  `revisionFilterApplied` field is invalid.

Hash bytes exactly as checked in and hash the exact serialized string returned by ARM:

```bash
shasum -a 256 workshop/observability/workbook.json
shasum -a 256 workshop/observability/queries.kql
ARM_SERIALIZED_DATA=$(jq -er '.properties.serializedData' \
  evidence/observability/raw/workbook-arm.json)
printf '%s' "$ARM_SERIALIZED_DATA" | shasum -a 256
```

Do not pretty-print, parse/re-serialize, trim, or newline-terminate `serializedData` before
hashing it. `jq -er` emits the string value itself rather than a re-encoded object, and the
command substitution strips only the single trailing newline `jq` adds — which is why the
hash is taken through `printf '%s'` and not by piping `jq` straight into `shasum`.

## 5. Run and normalize the exact queries

Render each frozen template by replacing only its declared placeholders:

- `__START_TIME__` and `__END_TIME__`;
- `__APPLICATION_INSIGHTS_RESOURCE_ID__`;
- `__CONTAINER_APP_RESOURCE_ID__`;
- `__SERVICE_NAME__`;
- `__SOURCE_COMMIT__`;
- `__REVISION_NAME__`.

Run all five rendered queries against the handoff Log Analytics workspace. Preserve the
exact rendered query text and SHA-256 in both the panel declaration and normalized result.

The error-rate, latency, database-dependency-failures, and cold-starts queries are
Application Insights queries filtered to the exact service, source commit, and revision.
The replica query is different by design: diagnostic-setting dimension flattening means
it filters the exact Container App in `AzureMetrics`, selects `Replicas` at `PT1M`,
reduces `Total` to the peak one-minute value, and contains no revision filter.

Each result file includes the common identity/window fields required by the shared model
and exactly one typed row, and each row is an answer to a question the legacy VM could
not answer at all:

| Query | Required row | What the row tells you |
| --- | --- | --- |
| `error-rate` | `timestamp`, float `value`, integer `totalRequests`, integer `failedRequests` | The failure percentage for one build on one revision |
| `latency` | `timestamp`, positive float `value` | p95 response time — the tail, not the average |
| `database-dependency-failures` | `timestamp`, positive integer `value` | Whether the fault was downstream of the app |
| `replica-count` | `timestamp`, positive integer app-total peak `value` | How much capacity was actually running |
| `cold-starts` | `timestamp`, positive integer `value` | How many instances began serving inside the window |

An empty result is a failed evidence capture. Exercise the exact app/revision as
appropriate and choose a valid immutable window; never fabricate or coerce a zero result.

Before assembling the bundle, look at the same data in the portal — the participants get
far more out of the chapter if they see it rather than only serialize it. **Application
Insights → Application map** shows the catalog and its database as separate nodes with
the call count and dependency latency on the edge:

![Application Insights application map showing the catalog Container App node with two instances connected to a separate MSSQL database node, annotated with call counts and average dependency duration](../../images/ch04-map.png)

**Application Insights → Performance** shows the same requests as 50th/95th/99th
percentiles, an operation-level duration table, and individual sample traces:

![Application Insights performance view showing percentile selectors, a per-operation average duration and count table, a duration distribution histogram, and a list of sample requests](../../images/ch04-perf.png)

## 6. Assemble and validate the live report

Use `workshop/contracts/observability-evidence.example.json` only as a field map. It is
synthetic structure, not evidence. Replace every example value with captured truth,
retain raw responses under `evidence/observability/raw/`, and ensure:

```text
diagnostic observedAt
  <= workbook deployedAt
  <= workbook capturedAt
  <= query window start
  <  query window end
  <= each query capturedAt
  <= report capturedAt
```

From `tests/acceptance`, run the common failure-closed validator:

```bash
cd tests/acceptance
uv --no-config run catalog-validate-challenge-evidence observability \
  evidence/observability-report.json \
  --handoff evidence/modernization-contract.json \
  --contracts workshop/contracts \
  --repository-root ../..
cd ../..
```

Then run the focused repository check:

```bash
cd tests/acceptance
uv --no-config run pytest -q tests/test_ch04_observability_challenge.py
```

## If it goes wrong

| Symptom | Cause | Fix |
| --- | --- | --- |
| `replica-count` returns nothing | Platform metrics were not yet flowing, or the window starts before the diagnostic setting existed | Wait a few minutes after deployment and choose a window that begins after the setting was created |
| An Application Insights panel returns nothing | The window contains no failure, or no instance first served inside it | Re-select the window around the Challenge 2 load run; never coerce an empty result into a row |
| `serializedDataSha256` does not match | The ARM string was pretty-printed, re-serialized, trimmed, or newline-terminated before hashing | Hash the exact returned string with `printf '%s'` |
| Deployment fails a resource-ID assertion | The template was deployed outside `application.resourceGroup` | Deploy to the handoff resource group; do not work around a cross-resource-group handoff |
| The validator rejects timestamp ordering | Times were back-filled or copied from the example | Re-record the real observation times in the documented order |

The broader diagnostic workflow is in
[the troubleshooting guide](../../docs/Troubleshooting.md).

## What a completed capture shows

Five panels, five answers, all bound to one service, one source commit, and one revision:
failure percentage, p95 latency, database dependency failures, peak replicas, and cold
starts. The legacy baseline for every one of those is a single text file on a Windows
server. This is also the telemetry Challenge 6's agent correlates during the incident
drill — without it, there is nothing to diagnose from.

---

**Back to** [Challenge 4: find out why it broke](../../challenges/ch04/README.md)
**Previous solution:** [Challenge 3 solution](../ch03/README.md) ·
**Next solution:** [Challenge 5 solution](../ch05-defender/README.md)
