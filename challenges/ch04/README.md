# Challenge 4: prove handoff-bound observability

## Goal

Deploy one Azure Workbook over the Application Insights component and Log Analytics
workspace already recorded by the completed P5 modernization handoff. Export the existing
Container App's `AllMetrics` category to that workspace and prove:

1. revision-filtered HTTP error rate;
2. revision-filtered HTTP latency;
3. revision-filtered database dependency failures;
4. the Container App's peak one-minute total replica count;
5. revision-filtered cold starts.

The diagnostic-setting export flattens metric dimensions. Therefore the replica panel is
Container App total, not revision scoped. Challenge 2 remains authoritative for
revision-level scale proof.

Do not add another telemetry stack, Data Collection Rule, compatibility adapter, or
alternate metrics pipeline. Do not change application instrumentation, replace P4/P5
resources, or deploy another Application Insights component or workspace.

## Authoritative inputs

Start only after P5 produced a validator-clean `evidence/modernization-contract.json` and
its complete `evidence/telemetry-report.json` bundle. Treat these handoff values as
immutable:

- `source.commitSha`;
- `application.resourceId`, `application.resourceGroup`,
  `application.containerAppName`, and `application.revisionName`;
- `observability.applicationInsightsResourceId`;
- `observability.logAnalyticsWorkspaceResourceId`;
- `observability.serviceName`, `observability.serviceNamespace`,
  `observability.environment`, and `observability.serviceVersion`;
- `evidence.telemetryReport`.

The validated P4/P5 handoff proves that the Container App, Application Insights component,
and Log Analytics workspace share `application.resourceGroup`. Deploy the Challenge 4
resource-group template to that exact resource group. The template fails if any supplied
resource ID is outside the current subscription/resource group.

The telemetry report and every normalized result file it references must remain present.
Challenge 4 does not replace the P5 proof of traces, metrics, logs, service identity,
source commit, or revision identity.

## Required implementation

- `workshop/observability/queries.kql` is the deterministic `// query-id` rendering of
  frozen `workshop/contracts/observability-queries.json` version `1.1.0`. Do not edit or
  reinterpret a query.
- `workshop/observability/workbook.json` is a `Notebook/1.0` template containing exactly
  the five named `KqlItem/1.0` Logs panels. Each panel uses integer `queryType: 0`,
  resource type `microsoft.operationalinsights/workspaces`, and no unrelated
  cross-component resource.
- `infra/observability-workbook.bicep` consumes the existing same-resource-group P4/P5
  resources and deploys only one workbook plus the existing Container App's
  `all-metrics-to-workspace` diagnostic setting. The setting exports `AllMetrics` to the
  handoff workspace's `AzureMetrics` table. Workbook `sourceId` is that exact workspace.

The four Application Insights panels bind `_ResourceId`, `AppRoleName`, `AppVersion`,
the exact `azure.containerapps.revision.name` property, and explicit timestamps. The
replica query intentionally has no revision filter: it reads `AzureMetrics`, binds the
exact handoff Container App `_ResourceId`, filters `MetricName == "Replicas"` and
`TimeGrain == "PT1M"`, then returns the peak `Total`. The cold-start query first finds
each exact commit/revision `AppRoleInstance`'s first request through the window end, then
filters those first requests into the evidence window.

## Evidence to submit

Use `workshop/contracts/observability-evidence.example.json` only to understand the frozen
`1.1.0` structure. Its IDs, timestamps, hashes, and rows are synthetic; it is never live
evidence.

Create `evidence/observability-report.json` plus every normalized result file it
references. The bundle must bind:

- the complete P5 handoff and telemetry report;
- the exact Application Insights component, Log Analytics workspace, Container App,
  service name, namespace, environment, source commit, and revision;
- the diagnostic-setting deployment time, workbook deployment/capture time, query window,
  query capture times, and final report capture time in their actual order;
- `metricsExport.destinationTable: "AzureMetrics"`,
  `metricsExport.scope: "container-app-total"`, and
  `metricsExport.dimensionHandling: "flattened"`;
- SHA-256 hashes of the checked-in workbook template (`templateSha256`) and KQL file
  (`queriesSha256`);
- exact ARM-captured workbook `serializedData`, `serializedDataSha256`, API version, and
  `sourceId`;
- the exact rendered query and `querySha256` for each panel;
- one typed, positive row per query;
- `assertions.applicationTelemetryRevisionFilterApplied: true` for the four Application
  Insights panels, without claiming that the replica panel is revision filtered.

Each normalized query observation includes its two Azure resource IDs, source commit,
revision, service name, exact query text/hash, window, capture time, and rows. Error rate
rows contain `timestamp`, floating-point `value`, `totalRequests`, and `failedRequests`.
Latency rows contain a positive floating-point `value`. Database failure, replica, and
cold-start rows contain a positive integer `value`.

Keep raw Azure responses under `evidence/observability/raw/`, then normalize them into the
schema-declared result paths. The normalized diagnostic-setting observation records the
exact Container App/workspace IDs, setting, category, `AzureMetrics` destination, enabled
state, and observation time. Do not point a declared `resultFile` outside the repository,
through a symlink, or at an unnormalized portal export.

## Failure-closed validation

Missing files, placeholder values, zero/empty results, boolean values in numeric fields,
non-finite JSON, changed queries, mismatched hashes, unrelated resources, incorrect
same-resource-group deployment, an incorrect workbook `sourceId`, or timestamps outside
the declared order all fail. Do not turn an empty query into a success-shaped row.

From `tests/acceptance`, run the common validator:

```bash
UV_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple \
  uv --no-config run catalog-validate-challenge-evidence observability \
  evidence/observability-report.json \
  --handoff evidence/modernization-contract.json \
  --contracts workshop/contracts \
  --repository-root ../..
```

Run the focused implementation checks:

```bash
UV_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple \
  uv --no-config run pytest -q tests/test_p6_observability_challenge.py
```
