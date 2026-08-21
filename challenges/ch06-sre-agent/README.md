# Challenge 6: investigate and approve an SRE Agent rollback

## Goal

Use Azure SRE Agent to investigate one harmless failure in the exact modernized catalog
selected by `evidence/modernization-contract.json`. Establish the affected revision and
time window from source evidence, challenge the proposed diagnosis, review the only
permitted rollback, and have the facilitator approve it.

The frozen contract is `workshop/contracts/sre-agent.json` version `1.2.0`. Checked-in
files under `workshop/contracts/fixtures/sre-agent/` are sanitized shape examples. Their
zero IDs, example timestamps, query rows, and outcomes are never live evidence.

## Required starting state

Start only after the facilitator confirms all of the following:

- the selected P5 handoff and its P6 CI/CD and observability reports validate;
- one dedicated `Microsoft.App/agents@2026-01-01` resource exists for your team;
- its action and knowledge identity is user-assigned and its two telemetry connectors use
  the system identity;
- the exact participant resource group has Reader, Log Analytics Reader, and Monitoring
  Reader for both identities;
- only the user-assigned identity has the Azure-documented subscription Monitoring
  Contributor exception for Azure Monitor alert ingestion and the exact-Container-App
  custom traffic role;
- you have SRE Agent Standard User only, while the facilitator has SRE Agent
  Administrator;
- the Azure Monitor response plan is in **Review** mode with Low action access;
- a rejected preflight test proved the alert reaches the plan and performs no write;
- the retained healthy revision uses the handoff image digest and remains available; and
- the drill revision was created at zero traffic before the recorded incident window; and
- `workshop/sre-agent/runbook.md` is available to the agent as the bounded runbook.

The drill revision reuses the immutable handoff image and every secret reference. Its only
intentional application changes are `CATALOG_DATABASE_HOST=<name>.sre-drill.invalid` and a
readiness probe routed to `/healthz` instead of `/readyz`. This makes the revision appear
platform-healthy while catalog requests fail against a harmless non-secret endpoint.

## Safety boundary

The only permitted in-window agent write is a traffic update on the exact handoff
Container App:

| Revision | Final weight |
| --- | ---: |
| Retained healthy revision | 100 |
| Drill revision | 0 |

Do not approve or request any image, secret, environment, scale, ingress-mode, revision
activation, role, policy, or resource deletion change. Autonomous mode, participant
approval, on-behalf-of elevation, broad Contributor/Owner roles, and subscription-wide
resource changes are prohibited. The alert-ingestion role is not permission to target
resources outside the participant scope.

Azure authorizes the rollback through exact-resource `Microsoft.App/containerApps/write`;
that ARM action is not JSON-field-scoped. Treat the reviewed command and before/after state
comparison as mandatory controls: approval is prohibited unless only ingress traffic
weights change.

## Task 1: scope the incident

Ask the agent to identify:

1. the exact handoff Container App and service;
2. the bad and retained healthy revisions;
3. the incident start and investigation end;
4. which revision has traffic; and
5. the failed-request window.

Reject an answer based only on a remembered runbook or the known rollback. Require the
live native ARM revision-list responses, nested `properties.trafficWeight`, deployment
chronology, and revision-filtered request evidence. Reject a flattened revision object or
one created at or after the incident start.

## Task 2: require the complete investigation

The agent must correlate all six signals before proposing an action:

1. complete, non-paginated Container App revision/deployment history;
2. current revision traffic;
3. request failures filtered by handoff `service.name`, 40-hex source commit, bad
   revision, and incident window;
4. exceptions under the same filters;
5. failed SqlClient dependencies with `db.system.name=microsoft.sql_server` or failed
   JDBC dependencies with `db.system.name=postgresql`; and
6. the selected database's live availability: Azure SQL database `Online` or PostgreSQL
   flexible-server parent `Ready`.

The investigation evidence must be captured strictly after the alert-bound
`IncidentActivitySnapshot` and before `AgentResponse`.

## Task 3: challenge the hypothesis

Require the agent to support the hypothesis
`bad-revision-selected-database-endpoint` from the captured invalid dependency target.
Ask it to reject both alternatives with evidence:

- `selected-database-platform-outage`; and
- `application-image-regression`.

An available selected database rejects the first. The same immutable image digest on the
healthy and bad revisions rejects the second. A narrative guess or a missing alternative
does not pass.

## Task 4: review the proposal

Before approval, inspect the exact proposal. It must state:

- affected revision and time window;
- counts and types from all diagnostic captures;
- exact bad dependency target and selected-database status;
- the supported hypothesis and both rejected alternatives;
- blast radius `exact-bad-revision-traffic`;
- retained healthy revision `100`, bad revision `0`; and
- verification steps `healthy-revision-100`, `bad-revision-0`, `health-200`,
  `readiness-200`, and `alert-resolved`.

The Review-mode tool event must prove `writeExecuted=false`.

## Task 5: facilitator approval

Show the proposal to the facilitator. Only the facilitator may select **Approve**. Record
the facilitator principal, approval timestamp, thread, trace, and correlation IDs. Do not
continue if the proposed command touches anything except traffic weights on the exact
handoff Container App.

## Task 6: verify recovery

After the agent executes the approved write, prove:

- exactly one correlation-bound user-assigned-identity Container App write follows the
  earlier facilitator seed write;
- before/after Container App documents differ only in ingress traffic;
- the retained healthy revision is active at `100` and the drill revision at `0`;
- the exact handoff `/healthz` and `/readyz` URLs return HTTP `200`;
- the Azure Monitor alert is `Resolved`;
- agent audit contains `IncidentActivitySnapshot`, `AgentResponse`,
  `AgentToolExecution`, `ApprovalDecision`, `AgentAzCliExecution`, and
  `AgentExecution` in order; and
- the execution event reports success.

## Task 7: submit the incident evidence

Write a concise assessment containing the evidence-supported root cause, both rejected
alternatives, the traffic rollback, and one prevention action: validate selected-database
endpoint configuration and `/readyz` behavior before assigning traffic.

Create `evidence/sre-agent/capture.json` with exactly the seven digest-bound artifact kinds
defined by the contract. Render and validate the report from `tests/acceptance`:

```bash
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
  --repository-root ../..
```

Do not manually create or edit the normalized report. Any altered digest, wrong scope,
missing signal, unsupported hypothesis, early evidence, autonomous write, participant
approval, extra Activity Log write, or changed protected resource fails closed.

Agent deletion is facilitator-owned and required to end its fixed four-agent-unit hourly
charge. Stopping the agent does not end that billing.

[Solution steps](../../solutions/ch06-sre-agent/README.md)
