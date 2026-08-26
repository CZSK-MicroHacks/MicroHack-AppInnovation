"""Static acceptance tests for the SRE Agent vertical slice."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    """Load one checked-in JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _read(repo_root: Path, relative_path: str) -> str:
    """Read one repository text asset."""
    return (repo_root / relative_path).read_text(encoding="utf-8")


def test_sre_bicep_consumes_the_frozen_resource_contract(repo_root: Path) -> None:
    """The entry point and modules deploy only the frozen SRE Agent resource shape."""
    contract = _load_json(repo_root / "workshop/contracts/sre-agent.json")
    entry = _read(repo_root, "infra/sre-agent.bicep")
    foundation = _read(repo_root, "infra/modules/sre-agent-foundation.bicep")

    assert contract["schemaVersion"] == "1.2.0"
    assert contract["resources"]["applicationInsightsQueryApiVersion"] == "2018-04-20"
    assert (
        "loadJsonContent('../workshop/contracts/sre-agent.json')" in entry
    )
    assert "'Microsoft.App/agents@2026-01-01'" in foundation
    assert (
        foundation.count(
            "'Microsoft.App/agents/connectors@2026-01-01'"
        )
        == 2
    )
    assert "type: sreContract.resources.identityMode" in foundation
    assert "mode: sreContract.responsePlan.autonomyMode" in foundation
    assert "accessLevel: sreContract.responsePlan.actionAccessLevel" in foundation
    assert "upgradeChannel: sreContract.resources.upgradeChannel" in foundation
    assert "connectionName: 'azure-monitor'" in foundation
    assert "type: sreContract.resources.incidentManagementType" in foundation

    combined = entry + foundation
    for forbidden in (
        "responsePlans@",
        "agentSpaceId:",
        "defaultModel:",
        "connectionKey:",
        "connectionUrl:",
        "oboUser:",
        "Autonomous",
    ):
        assert forbidden not in combined


def test_sre_bicep_freezes_dual_identity_and_connector_ownership(
    repo_root: Path,
) -> None:
    """Actions and knowledge use UAMI while telemetry connectors use system."""
    foundation = _read(repo_root, "infra/modules/sre-agent-foundation.bicep")

    assert foundation.count("identity: actionIdentity.id") == 2
    assert "managedResources: [\n        participantResourceGroupId" in foundation
    assert "identity: applicationConnector.identity" in foundation
    assert "identity: workspaceConnector.identity" in foundation
    assert "'resource.name': applicationInsightsName" in foundation
    assert "appId: applicationConnectorAppId" in foundation
    assert "'resource.name': logAnalyticsWorkspaceName" in foundation
    assert "appId: agentApplicationInsights.properties.AppId" in foundation
    assert (
        "connectionString: "
        "agentApplicationInsights.properties.ConnectionString"
    ) in foundation
    assert "output systemAssignedPrincipalId string = agent.identity.principalId" in (
        foundation
    )


def test_sre_bicep_creates_only_the_exact_role_surface(repo_root: Path) -> None:
    """The two identities and two humans receive only frozen roles and scopes."""
    contract = _load_json(repo_root / "workshop/contracts/sre-agent.json")
    entry = _read(repo_root, "infra/sre-agent.bicep")
    foundation = _read(repo_root, "infra/modules/sre-agent-foundation.bicep")
    workload = _read(repo_root, "infra/modules/sre-agent-workload-rbac.bicep")
    combined = entry + foundation + workload

    assert [role["name"] for role in contract["rbac"]["knowledgeAndConnectorRoles"]] == [
        "Reader",
        "Log Analytics Reader",
        "Monitoring Reader",
        "Monitoring Contributor",
    ]
    assert "participantReaderRoles = [" in workload
    assert "knowledgeAndConnectorRoles[0]" in workload
    assert "knowledgeAndConnectorRoles[1]" in workload
    assert "knowledgeAndConnectorRoles[2]" in workload
    assert "scope: containerApp" in workload
    assert "roleDefinitionId: customRollbackRoleDefinitionId" in workload
    assert "knowledgeAndConnectorRoles[3].roleDefinitionId" in entry
    assert "resource monitoringContributor" in entry
    assert contract["rbac"]["knowledgeAndConnectorRoles"][3]["purpose"] == (
        "azure-monitor-alert-ingestion"
    )
    assert contract["rbac"]["customRollbackRole"]["armWriteIsFieldScoped"] is False
    assert contract["rbac"]["customRollbackRole"]["trafficOnlyEnforcement"] == [
        "review-mode-exact-command",
        "facilitator-approval",
        "before-after-state-evidence",
    ]
    assert "rbac.humanRoles[0].roleDefinitionId" in foundation
    assert "rbac.humanRoles[1].roleDefinitionId" in foundation
    assert "scope: agent" in foundation
    assert "assignableScopes: [\n      participantResourceGroup.id" in entry
    assert "actions: sreContract.rbac.customRollbackRole.actions" in entry

    for role_id in contract["rbac"]["forbiddenRoleDefinitionIds"]:
        assert role_id not in combined


def test_sre_bicep_uses_a_dedicated_observable_agent_scope(
    repo_root: Path,
) -> None:
    """Agent infrastructure is isolated and emits no connection string."""
    entry = _read(repo_root, "infra/sre-agent.bicep")
    foundation = _read(repo_root, "infra/modules/sre-agent-foundation.bicep")

    assert "resource agentResourceGroup" in entry
    assert "dedicatedAgentResourceGroupIsSeparate" in entry
    assert "'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30'" in (
        foundation
    )
    assert "'Microsoft.OperationalInsights/workspaces@2023-09-01'" in foundation
    assert "'Microsoft.Insights/components@2020-02-02'" in foundation
    assert "WorkspaceResourceId: agentWorkspace.id" in foundation
    assert "retentionInDays: 30" in foundation
    assert "responsePlanConfiguredInIaC: false" in entry
    agent_tags = foundation.split(
        "resource agent 'Microsoft.App/agents@2026-01-01'",
        1,
    )[1].split("  identity:", 1)[0]
    assert "tags: {" in agent_tags
    assert "hidden-link:" in agent_tags
    assert "union(tags" not in agent_tags

    output_section = entry.split("output sreAgentFoundation object =", 1)[1]
    assert "contractVersion: sreContract.schemaVersion" in output_section
    assert "connectionString" not in output_section
    assert "instrumentationKey" not in output_section


def test_challenge_requires_investigation_before_review(repo_root: Path) -> None:
    """The participant guide covers all plan-required evidence and causality."""
    challenge = _read(repo_root, "challenges/ch06-sre-agent/README.md")
    compact_challenge = " ".join(challenge.split())

    for required in (
        "complete, non-paginated Container App revision/deployment history",
        "request failures",
        "exceptions",
        "SqlClient dependencies",
        "JDBC dependencies",
        "microsoft.sql_server",
        "db.system.name=postgresql",
        "Azure SQL database `Online`",
        "flexible-server parent `Ready`",
        "bad-revision-selected-database-endpoint",
        "selected-database-platform-outage",
        "application-image-regression",
        "exact-bad-revision-traffic",
        "strictly after",
    ):
        assert required in compact_challenge

    assert challenge.index("## Task 2: require the complete investigation") < (
        challenge.index("## Task 4: review the proposal")
    )
    assert challenge.index("## Task 4: review the proposal") < challenge.index(
        "## Task 5: facilitator approval"
    )


def test_challenge_and_runbook_preserve_the_safety_boundary(
    repo_root: Path,
) -> None:
    """No participant path permits autonomous or destructive remediation."""
    challenge = _read(repo_root, "challenges/ch06-sre-agent/README.md")
    runbook = _read(repo_root, "workshop/sre-agent/runbook.md")
    combined = challenge + runbook

    for required in (
        "Retained healthy revision | 100",
        "Drill revision | 0",
        "Never use Autonomous mode",
        "Never delete a resource",
        "change a secret or image",
        "facilitator",
        "Stopping the agent does not end",
    ):
        assert required in combined

    assert "az group delete" not in challenge
    assert "az role assignment create" not in challenge
    assert "Contributor" not in runbook
    assert "Owner" not in runbook


def test_facilitator_guide_uses_exact_foundation_producers(
    repo_root: Path,
) -> None:
    """Foundation capture retains native APIs, RBAC, and portal preflight."""
    guide = _read(repo_root, "workshop/sre-agent/README.md")
    compact_guide = " ".join(guide.split())

    for required in (
        "az bicep build --file infra/sre-agent.bicep",
        "az deployment sub what-if",
        "Microsoft.ResourceGraph/resources?api-version=2022-10-01",
        "authorizationresources",
        "resultFormat: \"objectArray\"",
        "--include-inherited",
        "--fill-principal-name false",
        "--fill-role-definition-name false",
        "api-version=2026-01-01",
        "api-version=2022-04-01",
        "azure-portal-facilitator-export",
        "Review mode and Low action access",
        "select **Reject**",
        "PREFLIGHT_QUERY=$(jq -r",
        "queries.responsePlanPreflightAudit",
        "applicationInsightsQueryApiVersion",
        "api-version=${APPLICATION_INSIGHTS_QUERY_API_VERSION}",
        "gsub(\"\\\\{agentId\\\\}\"; $agent)",
        "no write",
        "dedicated agent Application Insights",
        "BAD_REVISION_CREATED_AT",
        "before** recording `INCIDENT_START`",
        "capture_revision_list",
        ".properties.trafficWeight",
    ):
        assert required in compact_guide

    assert "jq '{value: .}'" not in guide
    assert "az role assignment list" in guide
    assert "responsePlans@" not in guide


def test_solution_uses_exact_cross_stack_investigation_producers(
    repo_root: Path,
) -> None:
    """The solution captures both database families and exact KQL templates."""
    solution = _read(repo_root, "solutions/ch06-sre-agent/README.md")

    for required in (
        "revisions?api-version=2025-01-01",
        "investigationRequestFailures",
        "investigationExceptions",
        "investigationDatabaseDependencies",
        "microsoft.sql_server",
        "postgresql",
        "2023-08-01",
        "2024-08-01",
        "applicationInsightsQueryApiVersion",
        "api-version=${APPLICATION_INSIGHTS_QUERY_API_VERSION}",
        "AGENT_APPLICATION_INSIGHTS_RESOURCE_ID",
        ".agentObservability.applicationInsightsResourceId",
        "AGENT_AUDIT_QUERY=$(jq -r",
        ".queries.agentAudit",
        "gsub(\"\\\\{threadId\\\\}\"; $thread)",
        "eventtypes/management/values?api-version=2015-04-01",
        "exactly two successful",
        "response.properties.configuration.ingress.traffic",
        "capture_container_app",
        "$RAW/${name}-response.json",
        "ACTIVITY_URL=",
        "&\\$filter=${ENCODED_FILTER}",
        "activity-log-response.json",
        "BAD_REVISION_CREATED_AT",
        "fromdateiso8601",
        "recovered-traffic-response.json",
        ".response.value[] | .properties.trafficWeight",
        "--write-out '%{json}\\n'",
        "redirectsAllowed: false",
        "num_redirects",
        "catalog-render-sre-agent-evidence",
        "catalog-validate-sre-agent-evidence",
    ):
        assert required in solution

    assert "requests\n| where" not in solution
    assert "exceptions\n| where" not in solution
    assert "dependencies\n| where" not in solution
    assert "az containerapp revision list" not in solution
    assert "--ids \"$APP_RESOURCE_ID\"" not in solution
    assert "%24filter" not in solution
    assert "$value|@uri" not in solution
    assert "manually create" not in solution.lower()


def test_facilitator_cleanup_is_authorized_and_protects_the_handoff(
    repo_root: Path,
) -> None:
    """Cleanup deletes only agent resources and verifies workload survival first."""
    guide = _read(repo_root, "workshop/sre-agent/README.md")

    assert "separate authorization gate" in " ".join(guide.split())
    assert "sre-agent-only" in guide
    assert "delete the agent and prove its ARM GET returns `404`" in guide
    assert "delete only the dedicated agent resource group" in " ".join(guide.split())
    assert "ARM GET every protected modernization and shared-challenge handoff resource" in guide
    assert "require HTTP `200`" in guide
    assert "query Cost Management last" in guide
    assert '"UsageQuantity"' in guide
    assert '"Azure SRE Agent"' in guide
    assert "cost-query-body.json" in guide
    assert "--body @\"$RAW/cost-query-body.json\"" in guide
    assert ".properties.nextLink == null" in guide
    assert "response: $response[0]" in guide
    assert "do not flatten" in " ".join(guide.split())
    assert "timeframeStart" not in guide
    assert "timeframeEnd" not in guide
    assert "Never run `az group delete` against the participant resource group" in guide
    assert "Stopping an agent does not end" in guide
