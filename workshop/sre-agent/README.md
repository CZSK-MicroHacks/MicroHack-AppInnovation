# Azure SRE Agent facilitator foundation

This component prepares and operates the facilitator-owned foundation for Challenge 6.
It consumes the frozen SRE Agent contract and one validated modernization handoff. Commands are
examples for an authorized facilitator; repository validation does not execute them.

## Build and inspect the Bicep

From the repository root:

```bash
az bicep build --file infra/sre-agent.bicep
```

Validate the selected handoff before extracting any resource:

```bash
set -euo pipefail
umask 077

(
  cd tests/acceptance
  uv --no-config run python -m catalog_acceptance.handoff_cli \
    ../../evidence/modernization-contract.json \
    --contracts ../../workshop/contracts \
    --repository-root ../..
)

HANDOFF=evidence/modernization-contract.json
APP_RESOURCE_ID=$(jq -er '.application.resourceId' "$HANDOFF")
APP_INSIGHTS_RESOURCE_ID=$(jq -er '.observability.applicationInsightsResourceId' "$HANDOFF")
WORKSPACE_RESOURCE_ID=$(jq -er '.observability.logAnalyticsWorkspaceResourceId' "$HANDOFF")
SUBSCRIPTION_ID=$(cut -d/ -f3 <<<"$APP_RESOURCE_ID")
PARTICIPANT_RESOURCE_GROUP=$(cut -d/ -f5 <<<"$APP_RESOURCE_ID")
APPLICATION_INSIGHTS_QUERY_API_VERSION=$(jq -er \
  '.resources.applicationInsightsQueryApiVersion' workshop/contracts/sre-agent.json)
```

The deploying principal needs Owner or User Access Administrator for role assignment.
The user-assigned identity receives the single plan-approved subscription exception:
Monitoring Contributor, required by Azure SRE Agent's Azure Monitor alert scanner. It does
not authorize resource actions outside the exact participant workload roles.
The exact-app custom role necessarily includes `Microsoft.App/containerApps/write`; Azure
RBAC cannot restrict that action to one JSON field. Review-mode command inspection,
facilitator approval, and native before/after evidence enforce the traffic-only boundary.
Set explicit participant/facilitator object IDs and the facilitator sponsor-group object
ID. Run what-if before the separately authorized deployment:

```bash
: "${TEAM_NAME:?Set the lowercase participant/team name}"
: "${FACILITATOR_PRINCIPAL_OBJECT_ID:?Set the facilitator object ID}"
: "${PARTICIPANT_PRINCIPAL_OBJECT_ID:?Set the participant object ID}"
: "${INITIAL_SPONSOR_GROUP_ID:?Set the facilitator sponsor-group object ID}"

az deployment sub what-if \
  --location swedencentral \
  --template-file infra/sre-agent.bicep \
  --parameters \
    teamName="$TEAM_NAME" \
    containerAppResourceId="$APP_RESOURCE_ID" \
    applicationInsightsResourceId="$APP_INSIGHTS_RESOURCE_ID" \
    logAnalyticsWorkspaceResourceId="$WORKSPACE_RESOURCE_ID" \
    facilitatorPrincipalObjectId="$FACILITATOR_PRINCIPAL_OBJECT_ID" \
    participantPrincipalObjectId="$PARTICIPANT_PRINCIPAL_OBJECT_ID" \
    initialSponsorGroupId="$INITIAL_SPONSOR_GROUP_ID"
```

Only after reviewing the exact what-if and authorizing the four-agent-unit hourly cost:

```bash
az deployment sub create \
  --name "sre-${TEAM_NAME}" \
  --location swedencentral \
  --template-file infra/sre-agent.bicep \
  --parameters \
    teamName="$TEAM_NAME" \
    containerAppResourceId="$APP_RESOURCE_ID" \
    applicationInsightsResourceId="$APP_INSIGHTS_RESOURCE_ID" \
    logAnalyticsWorkspaceResourceId="$WORKSPACE_RESOURCE_ID" \
    facilitatorPrincipalObjectId="$FACILITATOR_PRINCIPAL_OBJECT_ID" \
    participantPrincipalObjectId="$PARTICIPANT_PRINCIPAL_OBJECT_ID" \
    initialSponsorGroupId="$INITIAL_SPONSOR_GROUP_ID" \
  --query properties.outputs.sreAgentFoundation.value \
  --output json > evidence/sre-agent/foundation-deployment-output.json
```

The output is a deployment handoff, not graded live evidence. The foundation artifact
must preserve native ARM GETs and complete role inventories.

## Capture the native foundation

Read IDs from the deployment output and preserve exact API requests:

```bash
FOUNDATION_OUTPUT=evidence/sre-agent/foundation-deployment-output.json
AGENT_ID=$(jq -er '.agentResourceId' "$FOUNDATION_OUTPUT")
AGENT_RG_ID=$(jq -er '.agentResourceGroupId' "$FOUNDATION_OUTPUT")
AGENT_APPI_ID=$(jq -er '.agentApplicationInsightsResourceId' "$FOUNDATION_OUTPUT")
UAMI_PRINCIPAL_ID=$(jq -er '.userAssignedPrincipalId' "$FOUNDATION_OUTPUT")
SYSTEM_PRINCIPAL_ID=$(jq -er '.systemAssignedPrincipalId' "$FOUNDATION_OUTPUT")
ROLLBACK_ROLE_ID=$(jq -er '.customRollbackRoleDefinitionId' "$FOUNDATION_OUTPUT")
RAW=evidence/sre-agent/raw
mkdir -p "$RAW"

az rest --method get \
  --url "https://management.azure.com${AGENT_ID}?api-version=2026-01-01" \
  > "$RAW/agent.json"
az rest --method get \
  --url "https://management.azure.com${AGENT_ID}/connectors/application-insights?api-version=2026-01-01" \
  > "$RAW/application-insights-connector.json"
az rest --method get \
  --url "https://management.azure.com${AGENT_ID}/connectors/log-analytics?api-version=2026-01-01" \
  > "$RAW/log-analytics-connector.json"
az rest --method get \
  --url "https://management.azure.com${ROLLBACK_ROLE_ID}?api-version=2022-04-01" \
  > "$RAW/rollback-role.json"
```

For each identity, POST the exact subscription-bound Resource Graph body. Do not replace
this with `az role assignment list` or permit a truncated response:

```bash
for principal_id in "$UAMI_PRINCIPAL_ID" "$SYSTEM_PRINCIPAL_ID"; do
  safe_name=$([ "$principal_id" = "$UAMI_PRINCIPAL_ID" ] && printf user || printf system)
  jq -n \
    --arg subscription "$SUBSCRIPTION_ID" \
    --arg principal "$principal_id" '
    {
      subscriptions: [$subscription],
      query: (
        "authorizationresources "
        + "| where type =~ '\''microsoft.authorization/roleassignments'\'' "
        + "| extend principalId = tostring(properties.principalId) "
        + "| where principalId == '\''" + $principal + "'\'' "
        + "| project id, properties | order by id asc"
      ),
      options: {resultFormat: "objectArray"}
    }' > "$RAW/${safe_name}-role-query.json"

  az rest --method post \
    --url "https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01" \
    --body @"$RAW/${safe_name}-role-query.json" \
    > "$RAW/${safe_name}-roles.json"

  az role assignment list \
    --all \
    --include-inherited \
    --assignee-object-id "$principal_id" \
    --subscription "$SUBSCRIPTION_ID" \
    --fill-principal-name false \
    --fill-role-definition-name false \
    --output json > "$RAW/${safe_name}-effective-access.json"
done
```

Assemble `evidence/sre-agent/foundation.json` as the request/response envelopes required by
`workshop/contracts/sre-agent-foundation.schema.json`. Preserve the exact native
`.data[].properties`, `count`, `totalRecords`, `resultTruncated`, and effective-access
arrays. The common validator requires exactly five user-assigned roles and three
system-assigned roles at the frozen scopes.

## Configure and preflight the response plan

The response-plan payload is intentionally not in Bicep. In the Azure SRE Agent portal,
configure one Azure Monitor plan named `catalog-reviewed-rollback` with:

- Review mode and Low action access;
- quickstart plan disabled;
- alert titles beginning `MH-SRE-`;
- participant approval disabled; and
- facilitator approval required.

Create or bind one Sev2 log alert for failed requests on the exact handoff revision. Send
a harmless test incident, inspect the proposal, and select **Reject**. Verify no write
occurred. Export the portal state and test metadata to
`evidence/sre-agent/response-plan-preflight.json` with producer
`azure-portal-facilitator-export`.

Render `queries.responsePlanPreflightAudit` from `workshop/contracts/sre-agent.json` with
the exact test window, agent ID, and thread ID, then query the dedicated agent Application
Insights component:

```bash
: "${PREFLIGHT_TEST_START:?Set the captured test-window start}"
: "${PREFLIGHT_TEST_END:?Set the captured test-window end}"
: "${PREFLIGHT_THREAD_ID:?Set the captured preflight thread ID}"

PREFLIGHT_QUERY=$(jq -r \
  --arg start "$PREFLIGHT_TEST_START" \
  --arg end "$PREFLIGHT_TEST_END" \
  --arg agent "$AGENT_ID" \
  --arg thread "$PREFLIGHT_THREAD_ID" '
    .queries.responsePlanPreflightAudit
    | gsub("\\{testStart\\}"; $start)
    | gsub("\\{testEnd\\}"; $end)
    | gsub("\\{agentId\\}"; $agent)
    | gsub("\\{threadId\\}"; $thread)
  ' workshop/contracts/sre-agent.json)

az rest --method post \
  --url "https://management.azure.com${AGENT_APPI_ID}/query?api-version=${APPLICATION_INSIGHTS_QUERY_API_VERSION}" \
  --body "$(jq -n --arg query "$PREFLIGHT_QUERY" '{query: $query}')" \
  > "$RAW/response-plan-preflight-audit.json"
```

The response must contain the ordered `IncidentActivitySnapshot`, `AgentResponse`, and
rejected `ApprovalDecision`, all with shared agent/thread/trace/correlation fields.

## Seed the bounded drill

Keep the retained healthy revision active. Create exactly one `sre-bad-<commit-prefix>`
revision from the same digest-qualified image, preserving every secret reference. Change
only `CATALOG_DATABASE_HOST` to `<catalog-name>.sre-drill.invalid` and the readiness probe
from `/readyz` to `/healthz`; liveness remains `/healthz`. Create this revision with zero
traffic **before** recording `INCIDENT_START`. Its creation write is therefore outside the
incident Activity Log window.

Capture the exact healthy and drill revisions with:

```bash
az rest --method get \
  --url "https://management.azure.com${APP_RESOURCE_ID}/revisions/${HEALTHY_REVISION}?api-version=2025-01-01" \
  > "$RAW/healthy-revision.json"
az rest --method get \
  --url "https://management.azure.com${APP_RESOURCE_ID}/revisions/${BAD_REVISION}?api-version=2025-01-01" \
  > "$RAW/drill-revision.json"

BAD_REVISION_CREATED_AT=$(jq -er '.properties.createdTime' "$RAW/drill-revision.json")
test "$(jq -er '.properties.trafficWeight' "$RAW/drill-revision.json")" -eq 0
INCIDENT_START=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
jq -en \
  --arg created "$BAD_REVISION_CREATED_AT" \
  --arg start "$INCIDENT_START" \
  '($created | fromdateiso8601) < ($start | fromdateiso8601)' >/dev/null

REVISION_LIST_URL="${APP_RESOURCE_ID}/revisions?api-version=2025-01-01"
capture_revision_list() {
  local name=$1
  local response="$RAW/${name}-response.json"
  local observed_at

  az rest --method get \
    --url "https://management.azure.com${REVISION_LIST_URL}" \
    > "$response"
  observed_at=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
  jq -n \
    --arg observedAt "$observed_at" \
    --arg url "$REVISION_LIST_URL" \
    --slurpfile response "$response" '{
      observedAt: $observedAt,
      request: {method: "GET", url: $url},
      response: $response[0]
    }' > "$RAW/${name}.json"
  jq -e '
    .response.nextLink == null
    and ([.response.value[] | .properties.trafficWeight] | add == 100)
  ' "$RAW/${name}.json" >/dev/null
}

capture_revision_list traffic-before
```

Shift traffic to healthy `0`, drill `100` as the facilitator seed write. This is the first
of exactly two successful Container App writes in the incident Activity Log. Immediately
run `capture_revision_list traffic-bad`. Generate requests until the alert fires, then stop
changing resources and hand the incident to the participant. Preserve the native response
objects; do not flatten `value[].properties.trafficWeight`.

## Cleanup is a separate authorization gate

Stopping an agent does not end its fixed four-agent-unit charge. Deletion does. Do not
clean up until the incident, audit, and report artifacts are exported and the facilitator
has issued a timestamped authorization for scope `sre-agent-only`.

The authorized sequence is fixed:

1. delete the agent and prove its ARM GET returns `404`;
2. remove the UAMI's subscription Monitoring Contributor assignment and all participant
   resource-group/exact-app assignments for both managed identities;
3. prove Resource Graph and inherited effective-access outputs are both empty;
4. delete only the dedicated agent resource group and prove its ARM GET returns `404`;
5. ARM GET every protected modernization and shared-challenge handoff resource and require HTTP `200`; and
6. query Cost Management last, acknowledging ingestion lag, and derive
   `billingAfterDeletionObserved` from returned `UsageDate` rows rather than typing it
   independently. Any positive Azure SRE Agent usage on a later UTC date fails cleanup.

Never run `az group delete` against the participant resource group. Build
`evidence/sre-agent/cleanup.json` against
`workshop/contracts/sre-agent-cleanup.schema.json`; its protected resources come from the
validated target output, not name discovery.

After Cost Management data is available through a UTC window that includes
`AGENT_DELETED_AT`, capture the exact `2023-03-01` request body and native response. This
protocol intentionally rejects pagination rather than merging pages:

```bash
: "${AGENT_DELETED_AT:?Set the captured agent deletion time}"
: "${COST_TIMEFRAME_FROM:?Set an RFC3339 UTC start before deletion}"
: "${COST_TIMEFRAME_TO:?Set an RFC3339 UTC end after deletion with complete cost data}"
: "${COST_QUERIED_AT:?Set the actual Cost Management query time}"

COST_QUERY_URL="/subscriptions/${SUBSCRIPTION_ID}/providers/Microsoft.CostManagement/query?api-version=2023-03-01"
jq -n \
  --arg from "$COST_TIMEFRAME_FROM" \
  --arg to "$COST_TIMEFRAME_TO" '{
    type: "Usage",
    timeframe: "Custom",
    timePeriod: {from: $from, to: $to},
    dataset: {
      granularity: "Daily",
      aggregation: {
        agentUnits: {name: "UsageQuantity", function: "Sum"}
      },
      grouping: [{type: "Dimension", name: "Meter"}],
      filter: {
        dimensions: {
          name: "Meter",
          operator: "In",
          values: ["Azure SRE Agent"]
        }
      }
    }
  }' > "$RAW/cost-query-body.json"

az rest --method post \
  --url "https://management.azure.com${COST_QUERY_URL}" \
  --body @"$RAW/cost-query-body.json" \
  > "$RAW/cost-query-response.json"

jq -e '
  .properties.nextLink == null
  and (.properties.columns | map(.name) | index("UsageQuantity") != null)
  and (.properties.columns | map(.name) | index("UsageDate") != null)
  and (.properties.columns | map(.name) | index("Meter") != null)
  and (.properties.rows | length > 0)
' "$RAW/cost-query-response.json" >/dev/null

BILLING_AFTER_DELETION_OBSERVED=$(jq -r \
  --arg deleted "$AGENT_DELETED_AT" '
    .properties as $properties
    | ($properties.columns | map(.name) | index("UsageQuantity")) as $units
    | ($properties.columns | map(.name) | index("UsageDate")) as $date
    | ($properties.columns | map(.name) | index("Meter")) as $meter
    | ($deleted[0:10] | gsub("-"; "") | tonumber) as $deletedDay
    | [
        $properties.rows[]
        | select(
            .[$meter] == "Azure SRE Agent"
            and (.[$date] | tonumber) > $deletedDay
            and (.[$units] | tonumber) > 0
          )
      ]
    | length > 0
  ' "$RAW/cost-query-response.json")
[[ "$BILLING_AFTER_DELETION_OBSERVED" =~ ^(true|false)$ ]]

jq -n \
  --arg url "$COST_QUERY_URL" \
  --arg queriedAt "$COST_QUERIED_AT" \
  --arg dataThrough "$COST_TIMEFRAME_TO" \
  --argjson billingAfterDeletionObserved "$BILLING_AFTER_DELETION_OBSERVED" \
  --slurpfile body "$RAW/cost-query-body.json" \
  --slurpfile response "$RAW/cost-query-response.json" '{
    request: {method: "POST", url: $url, body: $body[0]},
    queriedAt: $queriedAt,
    dataThrough: $dataThrough,
    response: $response[0],
    billingAfterDeletionObserved: $billingAfterDeletionObserved,
    costDataLagAcknowledged: true
  }' > "$RAW/cost-verification.json"
```

Use that object unchanged as `cleanup.costVerification`. A missing request body, top-level
synthetic `columns`/`rows`, non-null `properties.nextLink`, altered filter/grouping, or a
hand-authored billing flag fails validation.
