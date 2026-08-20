# Challenge 4 solution: one handoff-bound workbook

This solution preserves the P4/P5 direct Azure Monitor exporter and adds only two Azure
resources: one workbook and one `AllMetrics` diagnostic setting on the existing Container
App. Azure diagnostic-settings metric export flattens dimensions, so the replica panel
uses app-total `AzureMetrics` data. It does not claim revision-level scale evidence;
Challenge 2 owns that proof.

## 1. Confirm the P5 evidence chain

Validate `evidence/modernization-contract.json` before proceeding. Copy values from the
validated document, not from portal search results:

```bash
cd tests/acceptance
UV_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple \
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
az deployment group create \
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
    queryEndTime="$QUERY_END_TIME"
```

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
printf '%s' "$ARM_SERIALIZED_DATA" | shasum -a 256
```

Do not pretty-print, parse/re-serialize, trim, or newline-terminate `serializedData` before
hashing it.

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
and exactly one typed row:

| Query | Required row |
| --- | --- |
| `error-rate` | `timestamp`, float `value`, integer `totalRequests`, integer `failedRequests` |
| `latency` | `timestamp`, positive float `value` |
| `database-dependency-failures` | `timestamp`, positive integer `value` |
| `replica-count` | `timestamp`, positive integer app-total peak `value` |
| `cold-starts` | `timestamp`, positive integer `value` |

An empty result is a failed evidence capture. Exercise the exact app/revision as
appropriate and choose a valid immutable window; never fabricate or coerce a zero result.

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
UV_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple \
  uv --no-config run catalog-validate-challenge-evidence observability \
  ../../evidence/observability-report.json \
  --handoff ../../evidence/modernization-contract.json \
  --contracts ../../workshop/contracts \
  --repository-root ../..
```

Then run the focused repository check:

```bash
UV_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple \
  uv --no-config run pytest -q tests/test_p6_observability_challenge.py
```
