# Challenge 6 solution: source-bound reviewed rollback

**What this is for.** Every command, prompt, and capture behind
[Challenge 6](../../challenges/ch06-sre-agent/README.md) — the exact investigation
producers the agent's answers must be checkable against, the assembly of the incident
evidence, the recovery-clock calculation, and the facilitator-owned teardown.

**When to open it.** Open it if the agent keeps answering from the runbook and you cannot
tell what to demand instead, if a capture fails the validator, or if you are facilitating
and need the approval and cleanup sequence in one place. If you have not yet tried to
make the agent reject a hypothesis on your own, close this and go back — that argument is
the chapter.

Run commands from the repository root in Bash unless a section says otherwise. Use the
exact participant scope selected by the handoff. Participants investigate and review;
only the facilitator approves the write and performs cleanup.

## 1. Validate and bind every upstream input

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
TARGET_OUTPUT=$(jq -er '.deployment.targetOutput' "$HANDOFF")
APP_RESOURCE_ID=$(jq -er '.application.resourceId' "$HANDOFF")
APP_NAME=$(jq -er '.application.containerAppName' "$HANDOFF")
APP_INSIGHTS_RESOURCE_ID=$(jq -er '.observability.applicationInsightsResourceId' "$HANDOFF")
WORKSPACE_RESOURCE_ID=$(jq -er '.observability.logAnalyticsWorkspaceResourceId' "$HANDOFF")
HEALTHY_REVISION=$(jq -er '.application.revisionName' "$HANDOFF")
SOURCE_COMMIT=$(jq -er '.source.commitSha' "$HANDOFF")
SERVICE_NAME=$(jq -er '.observability.serviceName' "$HANDOFF")
IMAGE_DIGEST=$(jq -er '.containerImage.digest' "$HANDOFF")
DATABASE_RESOURCE_ID=$(jq -er '.database.resourceId' "$HANDOFF")
DATABASE_FAMILY=$(jq -er '.database.family' "$HANDOFF")
HEALTH_URL=$(jq -er '.application.healthUrl' "$HANDOFF")
READINESS_URL=$(jq -er '.application.readinessUrl' "$HANDOFF")
SUBSCRIPTION_ID=$(cut -d/ -f3 <<<"$APP_RESOURCE_ID")
RESOURCE_GROUP=$(cut -d/ -f5 <<<"$APP_RESOURCE_ID")
FOUNDATION=evidence/sre-agent/foundation.json
AGENT_ID=$(jq -er '.agent.response.id' "$FOUNDATION")
AGENT_APPLICATION_INSIGHTS_RESOURCE_ID=$(jq -er \
  '.agentObservability.applicationInsightsResourceId' "$FOUNDATION")
APPLICATION_INSIGHTS_QUERY_API_VERSION=$(jq -er \
  '.resources.applicationInsightsQueryApiVersion' workshop/contracts/sre-agent.json)

test "$(jq -er '.application.resourceId' "$TARGET_OUTPUT")" = "$APP_RESOURCE_ID"
test "$(jq -er '.sourceCommit' "$TARGET_OUTPUT")" = "$SOURCE_COMMIT"
test "$(jq -er '.containerImage.digest' "$TARGET_OUTPUT")" = "$IMAGE_DIGEST"
[[ "$SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]]
[[ "$IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]]
```

Require the exact Challenge 3 CI/CD and Challenge 4 observability reports referenced by
this chapter's capture. The independent Challenge 6 validator replays both shared
validators; a copied summary is insufficient.

Read the facilitator-provided `foundation.json` and `response-plan-preflight.json`. Confirm
that the agent is Review/Low, the two managed identities have only the frozen roles, the
test incident was rejected by the facilitator, and no preflight write executed.

## 2. Establish the incident window and complete revision history

Record UTC `INCIDENT_START`, `INVESTIGATION_END`, `INCIDENT_END`, the facilitator-provided
`BAD_REVISION`, `BAD_REVISION_CREATED_AT`, and the agent/thread identifiers. The drill
revision creation must precede `INCIDENT_START`; the investigation must begin strictly
after the alert-bound `IncidentActivitySnapshot`.

```bash
RAW=evidence/sre-agent/raw
mkdir -p "$RAW"
: "${BAD_REVISION_CREATED_AT:?Set the facilitator-captured drill creation time}"
: "${INCIDENT_START:?Set the incident-window start after drill creation}"
: "${BAD_REVISION:?Set the facilitator-captured drill revision name}"

jq -en \
  --arg created "$BAD_REVISION_CREATED_AT" \
  --arg start "$INCIDENT_START" \
  '($created | fromdateiso8601) < ($start | fromdateiso8601)' >/dev/null

az rest --method get \
  --url "https://management.azure.com${APP_RESOURCE_ID}/revisions?api-version=2025-01-01" \
  > "$RAW/deployment-history.json"

jq -e --arg healthy "$HEALTHY_REVISION" --arg bad "$BAD_REVISION" '
  (.nextLink == null)
  and ([.value[].name] | index($healthy) != null)
  and ([.value[].name] | index($bad) != null)
' "$RAW/deployment-history.json" >/dev/null
```

Do not use only `az containerapp revision show` for one revision. The producer is the
complete list, with no `nextLink`. Both revisions must use the same handoff image digest;
the drill revision must be newer and currently carry traffic. Preserve each native ARM
revision object, including nested `properties.trafficWeight`; never flatten or synthesize
the list response.

## 3. Capture request, exception, and dependency evidence

Render the three exact query templates from `workshop/contracts/sre-agent.json`. For
Azure SQL use `microsoft.sql_server`; for PostgreSQL use `postgresql`.

```bash
: "${INVESTIGATION_END:?Set the investigation-window end, strictly after the incident start}"

case "$DATABASE_FAMILY" in
  azure-sql)
    DATABASE_SYSTEM=microsoft.sql_server
    DATABASE_AVAILABILITY_ID=$DATABASE_RESOURCE_ID
    DATABASE_API_VERSION=2023-08-01
    ;;
  postgresql-flexible)
    DATABASE_SYSTEM=postgresql
    DATABASE_AVAILABILITY_ID=${DATABASE_RESOURCE_ID%/databases/*}
    DATABASE_API_VERSION=2024-08-01
    ;;
  *)
    printf 'Unsupported database family: %s\n' "$DATABASE_FAMILY" >&2
    exit 1
    ;;
esac

render_query() {
  local key=$1
  jq -r \
    --arg key "$key" \
    --arg start "$INCIDENT_START" \
    --arg end "$INVESTIGATION_END" \
    --arg service "$SERVICE_NAME" \
    --arg commit "$SOURCE_COMMIT" \
    --arg revision "$BAD_REVISION" \
    --arg system "$DATABASE_SYSTEM" '
      .queries[$key]
      | gsub("\\{incidentStart\\}"; $start)
      | gsub("\\{investigationEnd\\}"; $end)
      | gsub("\\{serviceName\\}"; $service)
      | gsub("\\{sourceCommit\\}"; $commit)
      | gsub("\\{badRevision\\}"; $revision)
      | gsub("\\{databaseSystem\\}"; $system)
    ' workshop/contracts/sre-agent.json
}

REQUEST_QUERY=$(render_query investigationRequestFailures)
EXCEPTION_QUERY=$(render_query investigationExceptions)
DEPENDENCY_QUERY=$(render_query investigationDatabaseDependencies)

for query_name in request exception dependency; do
  case "$query_name" in
    request) query=$REQUEST_QUERY ;;
    exception) query=$EXCEPTION_QUERY ;;
    dependency) query=$DEPENDENCY_QUERY ;;
  esac
  printf '%s\n' "$query" > "$RAW/${query_name}.kql"
  az rest --method post \
    --url "https://management.azure.com${APP_INSIGHTS_RESOURCE_ID}/query?api-version=${APPLICATION_INSIGHTS_QUERY_API_VERSION}" \
    --body "$(jq -n --arg query "$query" '{query: $query}')" \
    > "$RAW/${query_name}.json"
done

az rest --method get \
  --url "https://management.azure.com${DATABASE_AVAILABILITY_ID}?api-version=${DATABASE_API_VERSION}" \
  > "$RAW/database-availability.json"
```

Require nonzero failed requests, exceptions, and failed dependencies. The dependency
targets must include the `.sre-drill.invalid` host. Azure SQL must report database status
`Online`; PostgreSQL must report flexible-server state `Ready`. That live availability
rejects a platform outage.

## 4. Ask the agent, then challenge its hypothesis

Use this sequence in the exact incident thread:

1. “Scope this incident to the affected revision and time window. Cite current traffic and
   complete deployment history.”
2. “Correlate request failures, exceptions, database dependencies, and selected-database
   availability for the exact handoff service, source commit, and bad revision.”
3. “State one supported hypothesis and challenge it. Explain why a database platform
   outage and an image regression are weaker alternatives.”
4. “Propose only the runbook traffic rollback. State blast radius and the exact
   verification plan. Do not execute.”

The accepted hypothesis is `bad-revision-selected-database-endpoint`. The same image
digest on both revisions rejects `application-image-regression`. The available selected
database rejects `selected-database-platform-outage`.

Before approval, the `AgentResponse` must accurately reproduce all evidence references,
counts, exception types, dependency targets, database status, affected revision/window,
both alternatives, blast radius, and five verification steps. The following
`AgentToolExecution` must be Review phase with `writeExecuted=false`.

## 5. Obtain facilitator approval

Show the exact proposal and command to the facilitator. Reject it if the target is not
`APP_RESOURCE_ID` or if it changes anything except traffic:

```text
retained healthy revision = 100
drill revision = 0
```

Only the facilitator selects **Approve**. Preserve the `ApprovalDecision` principal,
timestamp, thread, trace, and correlation ID. The participant must never approve.

## 6. Capture rollback, recovery, and audit evidence

Capture the complete Container App immediately before and after the approved operation:

```bash
CONTAINER_APP_URL="${APP_RESOURCE_ID}?api-version=2025-01-01"
capture_container_app() {
  local name=$1
  local response="$RAW/${name}-response.json"
  local observed_at

  az rest --method get \
    --url "https://management.azure.com${CONTAINER_APP_URL}" \
    > "$response"
  observed_at=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
  jq -n \
    --arg observedAt "$observed_at" \
    --arg url "$CONTAINER_APP_URL" \
    --slurpfile response "$response" '{
      observedAt: $observedAt,
      request: {method: "GET", url: $url},
      response: $response[0]
    }' > "$RAW/${name}.json"
}

capture_container_app container-app-before-rollback

# The agent executes only after facilitator approval.

capture_container_app container-app-after-rollback

REVISION_LIST_URL="${APP_RESOURCE_ID}/revisions?api-version=2025-01-01"
az rest --method get \
  --url "https://management.azure.com${REVISION_LIST_URL}" \
  > "$RAW/recovered-traffic-response.json"
RECOVERED_TRAFFIC_OBSERVED_AT=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
jq -n \
  --arg observedAt "$RECOVERED_TRAFFIC_OBSERVED_AT" \
  --arg url "$REVISION_LIST_URL" \
  --slurpfile response "$RAW/recovered-traffic-response.json" '{
    observedAt: $observedAt,
    request: {method: "GET", url: $url},
    response: $response[0]
  }' > "$RAW/recovered-traffic.json"
jq -e '
  .response.nextLink == null
  and ([.response.value[] | .properties.trafficWeight] | add == 100)
' "$RAW/recovered-traffic.json" >/dev/null

capture_recovery() {
  local name=$1
  local url=$2
  local observed_at

  curl --fail-with-body --silent --show-error \
    --proto '=https' \
    --max-redirs 0 \
    --connect-timeout 10 \
    --max-time 30 \
    --output "$RAW/${name}.body" \
    --write-out '%{json}\n' \
    "$url" > "$RAW/${name}-transfer.json"
  observed_at=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
  jq -e \
    --arg observedAt "$observed_at" \
    --arg url "$url" \
    '{
      observedAt: $observedAt,
      request: {
        method: "GET",
        url: $url,
        redirectsAllowed: false
      },
      response: .
    }' "$RAW/${name}-transfer.json" > "$RAW/${name}-http.json"
  jq -e '
    .response.exitcode == 0
    and .response.http_code == 200
    and .response.num_redirects == 0
    and .response.url_effective == .request.url
  ' "$RAW/${name}-http.json" >/dev/null
}

capture_recovery health "$HEALTH_URL"
capture_recovery readiness "$READINESS_URL"
```

The two Container App envelope responses must be identical after removing only
`response.properties.configuration.ingress.traffic`. Preserve both generated observation
times and exact requests.

Use the generated `health-http.json` and `readiness-http.json` objects as
`recoveryHealth`; do not type status or timestamps by hand. The validator requires native
curl exit code `0`, HTTP `200`, no redirects, and the exact effective handoff URL.

Render `queries.agentAudit` from the registry with the exact incident window, agent ID,
and thread ID. Query the dedicated agent Application Insights component, not the
application component:

```bash
: "${THREAD_ID:?Set the exact incident thread ID}"
: "${INCIDENT_END:?Set the incident-window end, at or after the investigation end}"

AGENT_AUDIT_QUERY=$(jq -r \
  --arg start "$INCIDENT_START" \
  --arg end "$INCIDENT_END" \
  --arg agent "$AGENT_ID" \
  --arg thread "$THREAD_ID" '
    .queries.agentAudit
    | gsub("\\{incidentStart\\}"; $start)
    | gsub("\\{incidentEnd\\}"; $end)
    | gsub("\\{agentId\\}"; $agent)
    | gsub("\\{threadId\\}"; $thread)
  ' workshop/contracts/sre-agent.json)

az rest --method post \
  --url "https://management.azure.com${AGENT_APPLICATION_INSIGHTS_RESOURCE_ID}/query?api-version=${APPLICATION_INSIGHTS_QUERY_API_VERSION}" \
  --body "$(jq -n --arg query "$AGENT_AUDIT_QUERY" '{query: $query}')" \
  > "$RAW/agent-audit.json"
```

Capture the exact Container App Activity Log producer:

```bash
FILTER="eventTimestamp ge '${INCIDENT_START}' and eventTimestamp le '${INCIDENT_END}' and resourceUri eq '${APP_RESOURCE_ID}'"
ENCODED_FILTER=${FILTER// /%20}
ACTIVITY_URL="/subscriptions/${SUBSCRIPTION_ID}/providers/Microsoft.Insights/eventtypes/management/values?api-version=2015-04-01&\$filter=${ENCODED_FILTER}"
az rest --method get \
  --url "https://management.azure.com${ACTIVITY_URL}" \
  > "$RAW/activity-log-response.json"
jq -n \
  --arg url "$ACTIVITY_URL" \
  --slurpfile response "$RAW/activity-log-response.json" '{
    request: {method: "GET", url: $url},
    response: $response[0]
  }' > "$RAW/activity-log.json"
```

Require exactly two successful `Microsoft.App/containerApps/write` events at the exact
app: the earlier facilitator seed and the later correlation-bound user-assigned-identity
rollback. Extra writes fail.

Finally capture the alert itself, by the exact alert ID the agent thread was opened with,
at `2019-05-05`. The `IncidentActivitySnapshot` row carries that ID in its
`Properties.alertId`, so nothing here is typed by hand. Read the audit rows as named
columns rather than by position — the KQL result is a table, and column order is a
property of the query, not of the contract:

```bash
ALERT_API_VERSION=2019-05-05

audit_snapshot() {
  jq -er '
    [ .tables[]
      | [.columns[].name] as $names
      | .rows[]
      | [$names, .] | transpose | map({key: .[0], value: .[1]}) | from_entries
    ]
    | map(select(.name == "IncidentActivitySnapshot"))
    | first
  ' "$RAW/agent-audit.json"
}

ALERT_ID=$(audit_snapshot | jq -er '.Properties.alertId')

capture_alert() {
  local name=$1

  az rest --method get \
    --url "https://management.azure.com${ALERT_ID}?api-version=${ALERT_API_VERSION}" \
    > "$RAW/${name}-response.json"
  jq -n \
    --arg url "${ALERT_ID}?api-version=${ALERT_API_VERSION}" \
    --slurpfile response "$RAW/${name}-response.json" '{
      request: {method: "GET", url: $url},
      response: $response[0]
    }' > "$RAW/${name}.json"
}

capture_alert alert-resolved
jq -e '
  .response.properties.essentials.monitorCondition == "Resolved"
  and (.response.properties.essentials.resolvedDateTime | type) == "string"
' "$RAW/alert-resolved.json" >/dev/null
```

Azure Monitor can take several minutes to re-evaluate after the rollback. If the assertion
fails because the condition still reads `Fired`, wait and re-run `capture_alert
alert-resolved`; never edit the captured response. The matching `alertFired` envelope is
the same `capture_alert` call made earlier in the window, before the rollback.

## 7. Read the recovery clock

The chapter's headline number comes out of evidence you already have — no extra query.
Detection is the timestamp of the alert-bound `IncidentActivitySnapshot` in
`$RAW/agent-audit.json`; recovery is `resolvedDateTime` on the resolved alert envelope you
just captured. Both are derived, not typed:

```bash
DETECTED_AT=$(audit_snapshot | jq -er '.timestamp | sub("\\.[0-9]+Z$"; "Z")')
RECOVERED_AT=$(jq -er '
  .response.properties.essentials.resolvedDateTime | sub("\\.[0-9]+Z$"; "Z")
' "$RAW/alert-resolved.json")

jq -en \
  --arg detected "$DETECTED_AT" \
  --arg recovered "$RECOVERED_AT" \
  '($recovered | fromdateiso8601) >= ($detected | fromdateiso8601)' >/dev/null

mkdir -p evidence
jq -n \
  --arg detected "$DETECTED_AT" \
  --arg recovered "$RECOVERED_AT" \
  '{
    detectedAt: $detected,
    recoveredAt: $recovered,
    minutesToRecovery: ((($recovered | fromdateiso8601)
      - ($detected | fromdateiso8601)) / 60 | floor)
  }' > evidence/ch06-mttr.json

cat evidence/ch06-mttr.json
```

`fromdateiso8601` parses whole seconds only, which is why both values pass through
`sub("\\.[0-9]+Z$"; "Z")` — Application Insights and Azure Monitor both return
sub-second precision, and without that the block would abort on a timestamp that is
otherwise perfectly good.

Against the sanitized shape example in `workshop/contracts/fixtures/sre-agent/incident.json`
the block prints:

```json
{
  "detectedAt": "2026-08-20T15:06:05Z",
  "recoveredAt": "2026-08-20T15:09:00Z",
  "minutesToRecovery": 2
}
```

`evidence/ch06-mttr.json` is the chapter's headline number, and it is the only place it
persists: the frozen `1.2.0` evidence contract has no field for it, so do not invent one
in `capture.json`. Repeat the figure in the written assessment and carry it to the
[wrap-up scorecard](../../challenges/wrapup/README.md) as mean time to recovery.

Facilitators: collect `minutesToRecovery` from every team and read out the room's median
in the debrief. One team's figure is an anecdote; the room's median is the number people
take back to their own on-call rotation.

If a participant asks what a fair comparison looks like, the honest legacy answer is that
there is no equivalent measurement — on the VM the incident lasts until a human notices,
so detection time is unbounded rather than long.

## 8. Assemble, render, and validate

Create `evidence/sre-agent/incident.json` against the `1.2.0`
`workshop/contracts/sre-agent-incident.schema.json`. Preserve every raw request URL/body,
response, observation time, and correlation field, including the generated curl recovery
objects and native revision-list envelopes. The assessment must repeat the evidence-derived
diagnosis, both alternatives, traffic action, and prevention:
validate selected-database endpoint configuration and `/readyz` behavior before traffic.

The facilitator supplies the separately authorized cleanup artifact only after exporting
the incident. Create the seven-entry capture manifest with repository-root-relative paths
and lowercase SHA-256 digests:

```bash
sha256sum \
  "$TARGET_OUTPUT" \
  evidence/cicd-report.json \
  evidence/observability-report.json \
  evidence/sre-agent/foundation.json \
  evidence/sre-agent/response-plan-preflight.json \
  evidence/sre-agent/incident.json \
  evidence/sre-agent/cleanup.json
```

From `tests/acceptance`, run the frozen renderer and independent validator:

```bash
cd tests/acceptance
uv --no-config run catalog-render-sre-agent-evidence \
  --capture evidence/sre-agent/capture.json \
  --handoff evidence/modernization-contract.json \
  --output evidence/sre-agent-report.json \
  --repository-root ../..

uv --no-config run catalog-validate-sre-agent-evidence \
  --capture evidence/sre-agent/capture.json \
  --handoff evidence/modernization-contract.json \
  --report evidence/sre-agent-report.json \
  --contracts workshop/contracts \
  --recovery-time evidence/ch06-mttr.json \
  --repository-root ../..
```

`--recovery-time` recomputes `minutesToRecovery` from the two timestamps in
`evidence/ch06-mttr.json` and checks its `recoveredAt` against
`incident.alertResolvedAt` in the sealed report. Editing the minutes by hand, or
inventing a pair of timestamps that agree with each other, both fail here.

Do not edit `evidence/sre-agent-report.json`.

## 9. Facilitator-owned teardown and billing

Participants stop after validation. Everything below is the facilitator's, and it is the
part most easily forgotten because nothing fails when you skip it — the meter simply keeps
running.

- The agent bills a **fixed four-agent-unit hourly charge for as long as the resource
  exists**, independent of how much it was used during the drill. Stopping the agent does
  not end its fixed four-agent-unit charge; only facilitator-authorized deletion does.
- Delete the agent and prove its ARM `GET` returns `404`, delete only the dedicated agent
  resource group, then re-check every protected handoff resource still answers. The exact
  ordered sequence, the protected-resource checks, and the Cost Management query live in
  [the SRE Agent facilitator guide](../../workshop/sre-agent/README.md).
- Cleanup is a separate authorization gate, not a continuation of the drill. Never run a
  broad resource-group deletion against a participant resource group.
- Cost data lags. Query Cost Management last, and expect the final figure hours after the
  workshop ends.

Do this at the end of the day, not at the end of the chapter — and keep it out of the
participant narrative. The last thing a participant should take from Challenge 6 is their
recovery time, not a billing caveat.

---

**Back to** [Challenge 6](../../challenges/ch06-sre-agent/README.md) ·
[Solution 5](../ch05-defender/README.md) ·
[workshop overview](../../README.md)
