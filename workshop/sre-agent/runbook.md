# Catalog SRE Agent runbook

## Topology

The selected modernization handoff is authoritative. Investigate only its Azure Container
App, retained healthy revision, Application Insights component, Log Analytics workspace,
and selected Azure SQL or PostgreSQL database. The agent uses its user-assigned identity
for knowledge and approved actions and its system identity for the two telemetry
connectors.

## Safe rollback

The only approved write is an ingress traffic-weight update on the exact handoff Container
App: retained healthy revision `100`, drill revision `0`. Preserve the image digest,
secrets, environment variables, revision activation state, scale settings, ingress mode,
and every unrelated resource property.

The exact-resource `Microsoft.App/containerApps/write` authorization is not field-scoped.
Review the proposed command before approval, and reject recovery unless native before/after
state proves that only `properties.configuration.ingress.traffic` changed.

## Forbidden actions

Never use Autonomous mode. Never delete a resource, change a secret or image, activate or
deactivate a revision, assign a role, approve as the participant, or modify another
resource group. A facilitator must inspect and approve the exact Review-mode proposal.

## Verification

After approval, prove the retained revision has all traffic and the drill revision has
none. Require HTTP `200` from `/healthz` and `/readyz`, a resolved alert, exactly one
correlation-bound user-assigned-identity rollback write after the facilitator seed write,
and the complete SRE Agent audit trail in its dedicated Application Insights component.
