"""Render deterministic Azure SRE Agent evidence from digest-bound captures."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
import math
import os
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from catalog_acceptance.artifact_io import (
    load_digest_bound_json,
    load_json_object,
    resolve_repository_file,
    sha256_file,
)
from catalog_acceptance.handoff import validate_handoff
from catalog_acceptance.shared_challenges import (
    validate_shared_challenge_evidence,
)

_REPORT_VERSION = "1.0.0"
_AGENT_API_VERSION = "2026-01-01"
_CONNECTOR_API_VERSION = "2026-01-01"
_RESOURCE_GRAPH_API_VERSION = "2022-10-01"
_ROLE_READER = "acdd72a7-3385-48ef-bd42-f606fba81ae7"
_ROLE_LOG_ANALYTICS_READER = "73c42c96-874c-492b-b04d-ab87d138a893"
_ROLE_MONITORING_READER = "43d0d8ad-25c7-4714-9337-8ba259a9fe05"
_ROLE_MONITORING_CONTRIBUTOR = "749f88d5-cbae-40b8-bcfc-e573ddc772fa"
_ROLE_SRE_ADMINISTRATOR = "e79298df-d852-4c6d-84f9-5d13249d1e55"
_ROLE_SRE_STANDARD_USER = "2d84a65a-63b2-4343-bbb6-31105d857bc1"
_ROLE_SRE_READER = "a4b156ac-253f-4a1a-9851-96d62b71b047"
_CUSTOM_ROLE_ACTIONS = {
    "Microsoft.App/containerApps/read",
    "Microsoft.App/containerApps/write",
    "Microsoft.App/containerApps/revisions/read",
}
_REQUIRED_AUDIT_EVENTS = {
    "IncidentActivitySnapshot",
    "AgentResponse",
    "AgentToolExecution",
    "ApprovalDecision",
    "AgentAzCliExecution",
    "AgentExecution",
}
_ARTIFACT_SCHEMAS = {
    "target-output": "azure-target-output.schema.json",
    "cicd-evidence": "cicd-evidence.schema.json",
    "observability-evidence": "observability-evidence.schema.json",
    "sre-agent-foundation": "sre-agent-foundation.schema.json",
    "sre-agent-response-plan": "sre-agent-response-plan.schema.json",
    "sre-agent-incident": "sre-agent-incident.schema.json",
    "sre-agent-cleanup": "sre-agent-cleanup.schema.json",
}
_GUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def _validate_schema(schema_path: Path, value: dict[str, Any]) -> None:
    """Validate one object with a checked-in Draft 2020-12 schema."""
    Draft202012Validator(
        load_json_object(schema_path),
        format_checker=FormatChecker(),
    ).validate(value)


def _require(condition: bool, message: str) -> None:
    """Raise a validation error when one evidence invariant is false."""
    if not condition:
        raise ValueError(message)


def _mapping(value: Any, name: str) -> dict[str, Any]:
    """Return one mapping or fail with its evidence field name."""
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _array(value: Any, name: str) -> list[Any]:
    """Return one array or fail with its evidence field name."""
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    return value


def _string(value: Any, name: str) -> str:
    """Return one non-empty string or fail with its evidence field name."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _integer(value: Any, name: str) -> int:
    """Return one strict JSON integer."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    return value


def _number(value: Any, name: str) -> float:
    """Return one finite strict JSON number."""
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _timestamp(value: Any, name: str) -> datetime:
    """Parse one timezone-aware ISO-8601 timestamp."""
    text = _string(value, name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be ISO-8601") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _usage_date(value: Any, name: str) -> date:
    """Parse one Cost Management UTC usage date."""
    if isinstance(value, int) and not isinstance(value, bool):
        text = str(value)
    elif isinstance(value, str):
        text = value
    else:
        raise ValueError(f"{name} must be YYYYMMDD")
    if re.fullmatch(r"\d{8}", text) is None:
        raise ValueError(f"{name} must be YYYYMMDD")
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError as error:
        raise ValueError(f"{name} must be a valid UTC usage date") from error


def _same_resource(left: Any, right: Any) -> bool:
    """Compare Azure resource IDs case-insensitively."""
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    return left.rstrip("/").casefold() == right.rstrip("/").casefold()


def _role_id(value: Any, name: str) -> str:
    """Return the GUID suffix from one role definition resource ID."""
    resource_id = _string(value, name)
    role_id = resource_id.rstrip("/").split("/")[-1].casefold()
    if not _GUID_PATTERN.fullmatch(role_id):
        raise ValueError(f"{name} must end with a role definition GUID")
    return role_id


def _resource_group_id(resource_id: Any, name: str) -> str:
    """Return the resource-group scope containing one Azure resource."""
    value = _string(resource_id, name).rstrip("/")
    marker = "/providers/"
    index = value.casefold().find(marker)
    if index < 0:
        raise ValueError(f"{name} must be a provider resource ID")
    scope = value[:index]
    if "/resourcegroups/" not in scope.casefold():
        raise ValueError(f"{name} must be in a resource group")
    return scope


def _subscription_scope(subscription_id: str) -> str:
    """Return the canonical subscription resource ID."""
    return f"/subscriptions/{subscription_id}"


def _application_insights_query_endpoint(
    resource_id: str,
    registry: dict[str, Any],
) -> str:
    """Return the frozen ARM resource-query endpoint."""
    resources = _mapping(registry["resources"], "registry.resources")
    version = _string(
        resources.get("applicationInsightsQueryApiVersion"),
        "registry.resources.applicationInsightsQueryApiVersion",
    )
    return f"{resource_id}/query?api-version={version}"


def _relative_file(root: Path, path: Path, name: str) -> str:
    """Return one repository-relative path or reject an external file."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise ValueError(f"{name} must stay inside the repository") from error


def _contracts_directory(root: Path, path: Path) -> Path:
    """Require the repository's exact checked-in contract directory."""
    expected = root / "workshop/contracts"
    if path.resolve() != expected.resolve() or not expected.is_dir():
        raise ValueError(
            "contracts directory must be the repository workshop/contracts tree"
        )
    for current in [root / "workshop", expected]:
        if current.is_symlink():
            raise ValueError("workshop contracts path cannot contain a symlink")
    return expected


def _contains_key(value: Any, forbidden: set[str]) -> bool:
    """Return whether nested evidence includes any forbidden property name."""
    if isinstance(value, dict):
        return any(
            any(token in key.casefold() for token in forbidden)
            or _contains_key(child, forbidden)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_key(child, forbidden) for child in value)
    return False


def _load_artifacts(
    capture: dict[str, Any],
    capture_path: Path,
    root: Path,
    contracts: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    """Load the exact six unique digest-bound artifacts in one manifest."""
    required = set(_ARTIFACT_SCHEMAS)
    documents: dict[str, dict[str, Any]] = {}
    references: dict[str, dict[str, str]] = {}
    paths: set[str] = set()
    capture_relative = _relative_file(root, capture_path, "capture manifest")
    for index, raw_reference in enumerate(_array(capture["artifacts"], "artifacts")):
        reference = _mapping(raw_reference, f"artifacts[{index}]")
        kind = _string(reference.get("kind"), f"artifacts[{index}].kind")
        path = _string(reference.get("path"), f"artifacts[{index}].path")
        digest = _string(reference.get("sha256"), f"artifacts[{index}].sha256")
        _require(kind not in documents, f"duplicate artifact kind: {kind}")
        _require(path not in paths, f"duplicate artifact path: {path}")
        _require(path != capture_relative, "capture manifest cannot reference itself")
        document = load_digest_bound_json(root, path, digest)
        _validate_schema(contracts / _ARTIFACT_SCHEMAS[kind], document)
        documents[kind] = document
        references[kind] = {"path": path, "sha256": digest}
        paths.add(path)
    _require(set(documents) == required, "capture artifact kinds are incomplete")
    return documents, references


def _validate_upstream(
    handoff: dict[str, Any],
    handoff_sha256: str,
    target: dict[str, Any],
    cicd: dict[str, Any],
    observability: dict[str, Any],
) -> None:
    """Bind SRE Agent evidence to the exact accepted modernization and shared-challenge workload identity."""
    application = _mapping(handoff["application"], "handoff.application")
    source = _mapping(handoff["source"], "handoff.source")
    handoff_observability = _mapping(
        handoff["observability"],
        "handoff.observability",
    )
    target_application = _mapping(target["application"], "target.application")
    target_observability = _mapping(
        target["observability"],
        "target.observability",
    )
    cicd_subject = _mapping(cicd["subject"], "cicd.subject")
    cicd_image = _mapping(cicd["image"], "cicd.image")
    cicd_revisions = _mapping(cicd["revisions"], "cicd.revisions")
    cicd_traffic = _mapping(cicd["traffic"], "cicd.traffic")
    cicd_rollback = _mapping(cicd_traffic["rollback"], "cicd.traffic.rollback")
    obs_subject = _mapping(observability["subject"], "observability.subject")
    obs_source = _mapping(observability["source"], "observability.source")

    _require(
        cicd["workflow"]["handoffSha256"] == handoff_sha256,
        "CI/CD evidence does not bind the supplied modernization handoff digest",
    )
    _require(
        handoff["sliceId"] == cicd_subject["sliceId"] == obs_subject["sliceId"],
        "modernization and CI/CD slice identities differ",
    )
    _require(
        source["stack"] == target["stack"],
        "handoff and target stack differ",
    )
    _require(
        source["commitSha"]
        == target["sourceCommit"]
        == cicd_subject["sourceCommit"]
        == obs_subject["sourceCommit"],
        "modernization and CI/CD source commits differ",
    )
    app_id = application["resourceId"]
    _require(
        all(
            _same_resource(app_id, candidate)
            for candidate in [
                target_application["resourceId"],
                cicd_subject["containerAppResourceId"],
                obs_subject["containerAppResourceId"],
            ]
        ),
        "modernization and CI/CD Container App identities differ",
    )
    revision = application["revisionName"]
    _require(
        revision
        == target_application["revisionName"]
        == cicd_subject["revisionName"]
        == obs_subject["revisionName"]
        == cicd_revisions["previous"],
        "CI/CD evidence does not prove the handoff revision remained healthy",
    )
    _require(
        cicd_rollback["previous"] == 100
        and cicd_rollback["candidate"] == 0,
        "CI/CD rollback did not restore all traffic to the healthy revision",
    )
    _require(
        handoff["containerImage"]["digest"]
        == target["containerImage"]["digest"]
        == cicd_subject["imageDigest"]
        == cicd_image["digest"],
        "modernization and CI/CD image digests differ",
    )
    _require(
        cicd["assertions"]["rollbackVerified"]
        and cicd["assertions"]["previousRevisionRetained"],
        "CI/CD evidence did not retain and verify the healthy revision",
    )
    _require(
        _same_resource(
            handoff_observability["applicationInsightsResourceId"],
            target_observability["applicationInsightsResourceId"],
        )
        and _same_resource(
            handoff_observability["applicationInsightsResourceId"],
            obs_source["applicationInsightsResourceId"],
        ),
        "modernization and observability Application Insights identities differ",
    )
    _require(
        _same_resource(
            handoff_observability["logAnalyticsWorkspaceResourceId"],
            target_observability["logAnalyticsWorkspaceResourceId"],
        )
        and _same_resource(
            handoff_observability["logAnalyticsWorkspaceResourceId"],
            obs_source["logAnalyticsWorkspaceResourceId"],
        ),
        "modernization and observability Log Analytics identities differ",
    )
    _require(
        observability["assertions"]["telemetryIdentityBound"]
        and observability["assertions"][
            "applicationTelemetryRevisionFilterApplied"
        ],
        "observability evidence is not workload and revision bound",
    )


def _rbac_query(principal_id: str, *, human_roles_only: bool = False) -> str:
    """Render one frozen complete-subscription RBAC inventory query."""
    prefix = (
        "authorizationresources "
        "| where type =~ 'microsoft.authorization/roleassignments' "
        "| extend principalId = tostring(properties.principalId)"
    )
    if human_roles_only:
        return (
            f"{prefix}, roleDefinitionId = "
            "tolower(tostring(properties.roleDefinitionId)) "
            f"| where principalId == '{principal_id}' "
            f"| where roleDefinitionId endswith '/{_ROLE_SRE_ADMINISTRATOR}' "
            f"or roleDefinitionId endswith '/{_ROLE_SRE_STANDARD_USER}' "
            f"or roleDefinitionId endswith '/{_ROLE_SRE_READER}' "
            "| project id, properties | order by id asc"
        )
    return (
        f"{prefix} | where principalId == '{principal_id}' "
        "| project id, properties | order by id asc"
    )


def _role_record_list(
    values: list[Any],
    name: str,
    principal_id: str,
) -> list[tuple[str, str, str]]:
    """Normalize role assignments from ARM-shaped or flattened records."""
    records: list[tuple[str, str, str]] = []
    assignment_ids: set[str] = set()
    for index, raw_item in enumerate(values):
        item = _mapping(raw_item, f"{name}[{index}]")
        properties = item.get("properties", item)
        role = _mapping(properties, f"{name}[{index}] role properties")
        _require(
            role.get("principalId") == principal_id,
            f"{name} contains another principal",
        )
        assignment_id = item.get("id")
        if assignment_id is not None:
            normalized_id = _string(
                assignment_id,
                f"{name}[{index}].id",
            ).casefold()
            _require(
                normalized_id not in assignment_ids,
                f"{name} contains duplicate role assignments",
            )
            assignment_ids.add(normalized_id)
        records.append(
            (
                principal_id,
                _role_id(
                    role.get("roleDefinitionId"),
                    f"{name}[{index}].roleDefinitionId",
                ),
                _string(
                    role.get("scope"),
                    f"{name}[{index}].scope",
                ).rstrip("/").casefold(),
            )
        )
    return records


def _role_records(
    capture: Any,
    name: str,
    principal_id: str,
    subscription_id: str,
    *,
    human_roles_only: bool = False,
    require_effective_access: bool = False,
) -> list[tuple[str, str, str]]:
    """Validate and normalize one complete Resource Graph RBAC inventory."""
    document = _mapping(capture, name)
    request = _mapping(document.get("request"), f"{name}.request")
    response = _mapping(document.get("response"), f"{name}.response")
    _require(request.get("method") == "POST", f"{name} must use POST")
    _require(
        request.get("url")
        == (
            "/providers/Microsoft.ResourceGraph/resources"
            f"?api-version={_RESOURCE_GRAPH_API_VERSION}"
        ),
        f"{name} must use the frozen Resource Graph API",
    )
    body = _mapping(request.get("body"), f"{name}.request.body")
    _require(
        body.get("subscriptions") == [subscription_id]
        and body.get("query")
        == _rbac_query(
            principal_id,
            human_roles_only=human_roles_only,
        )
        and body.get("options") == {"resultFormat": "objectArray"},
        f"{name} must use the complete frozen RBAC query",
    )
    _require(
        response.get("resultTruncated") == "false"
        and response.get("facets") == []
        and "$skipToken" not in response,
        f"{name} is truncated or paginated",
    )
    data = _array(response.get("data"), f"{name}.response.data")
    count = _integer(response.get("count"), f"{name}.response.count")
    total = _integer(
        response.get("totalRecords"),
        f"{name}.response.totalRecords",
    )
    _require(count == total == len(data), f"{name} result counts differ")
    records = _role_record_list(
        data,
        f"{name}.response.data",
        principal_id,
    )
    if require_effective_access:
        effective = _mapping(
            document.get("effectiveAccess"),
            f"{name}.effectiveAccess",
        )
        effective_request = _mapping(
            effective.get("request"),
            f"{name}.effectiveAccess.request",
        )
        expected_command = (
            "az role assignment list --all --include-inherited "
            f"--assignee-object-id {principal_id} "
            f"--subscription {subscription_id} "
            "--fill-principal-name false "
            "--fill-role-definition-name false --output json"
        )
        _require(
            effective_request
            == {
                "command": expected_command,
                "assigneeObjectId": principal_id,
                "subscriptionId": subscription_id,
                "all": True,
                "includeInherited": True,
                "fillPrincipalName": False,
                "fillRoleDefinitionName": False,
            },
            f"{name} effective-access command differs",
        )
        effective_records = _role_record_list(
            _array(
                effective.get("response"),
                f"{name}.effectiveAccess.response",
            ),
            f"{name}.effectiveAccess.response",
            principal_id,
        )
        _require(
            set(effective_records) == set(records),
            f"{name} Resource Graph and inherited effective access differ",
        )
    return records


def _validate_foundation(
    foundation: dict[str, Any],
    handoff: dict[str, Any],
    target: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Validate the agent, connector, RBAC, and portal preflight boundary."""
    subscription_id = _string(
        foundation["subscriptionId"],
        "foundation.subscriptionId",
    )
    participant_rg = _string(
        target["resourceGroup"]["resourceId"],
        "target.resourceGroup.resourceId",
    )
    container_app_id = _string(
        handoff["application"]["resourceId"],
        "handoff.application.resourceId",
    )
    _require(
        _same_resource(foundation["participantResourceGroupId"], participant_rg),
        "foundation participant resource group differs from target output",
    )
    _require(
        _same_resource(foundation["containerAppResourceId"], container_app_id),
        "foundation Container App differs from the handoff",
    )
    _require(
        participant_rg.casefold().startswith(
            f"/subscriptions/{subscription_id}/".casefold()
        ),
        "foundation subscription differs from the workload",
    )
    agent_rg = _string(
        foundation["agentResourceGroupId"],
        "foundation.agentResourceGroupId",
    )
    _require(
        not _same_resource(agent_rg, participant_rg),
        "SRE Agent resources require a dedicated resource group",
    )
    agent_observability = _mapping(
        foundation["agentObservability"],
        "foundation.agentObservability",
    )
    agent_app_insights_id = _string(
        agent_observability["applicationInsightsResourceId"],
        "foundation.agentObservability.applicationInsightsResourceId",
    )
    agent_workspace_id = _string(
        agent_observability["logAnalyticsWorkspaceResourceId"],
        "foundation.agentObservability.logAnalyticsWorkspaceResourceId",
    )
    _require(
        _resource_group_id(
            agent_app_insights_id,
            "foundation agent Application Insights resource",
        ).casefold()
        == agent_rg.casefold()
        and _resource_group_id(
            agent_workspace_id,
            "foundation agent Log Analytics workspace",
        ).casefold()
        == agent_rg.casefold(),
        "agent observability resources must stay in the dedicated agent group",
    )

    agent_capture = _mapping(foundation["agent"], "foundation.agent")
    agent_request = _mapping(agent_capture["request"], "foundation.agent.request")
    agent = _mapping(agent_capture["response"], "foundation.agent.response")
    agent_id = _string(agent.get("id"), "foundation.agent.response.id")
    expected_agent_url = f"{agent_id}?api-version={_AGENT_API_VERSION}"
    _require(
        agent_request == {"method": "GET", "url": expected_agent_url},
        "agent evidence must be the exact 2026 ARM GET",
    )
    _require(
        _resource_group_id(agent_id, "foundation.agent.response.id")
        .casefold()
        == agent_rg.casefold(),
        "agent is not in the dedicated resource group",
    )
    _require(agent.get("type") == "Microsoft.App/agents", "agent type differs")
    tags = _mapping(agent.get("tags"), "foundation.agent.response.tags")
    hidden_link = f"hidden-link:{agent_app_insights_id}".casefold()
    _require(
        len(tags) == 1
        and {
            key.casefold(): value
            for key, value in tags.items()
        }.get(hidden_link)
        == "Resource",
        "agent is not source-bound to its Application Insights resource",
    )
    identity = _mapping(agent.get("identity"), "foundation.agent.response.identity")
    _require(
        identity.get("type") == "SystemAssigned,UserAssigned",
        "agent must use both system- and user-assigned identities",
    )
    system_principal = _string(
        identity.get("principalId"),
        "foundation.agent.response.identity.principalId",
    )
    user_identities = _mapping(
        identity.get("userAssignedIdentities"),
        "foundation.agent.response.identity.userAssignedIdentities",
    )
    _require(
        len(user_identities) == 1,
        "agent must bind exactly one user-assigned identity",
    )
    user_identity_id, raw_user_identity = next(iter(user_identities.items()))
    user_identity = _mapping(
        raw_user_identity,
        "foundation.agent.response.identity.userAssignedIdentities value",
    )
    user_principal = _string(
        user_identity.get("principalId"),
        "foundation user-assigned principalId",
    )
    _string(user_identity.get("clientId"), "foundation user-assigned clientId")
    _require(
        user_principal != system_principal,
        "system and user-assigned principal IDs must differ",
    )
    _require(
        _GUID_PATTERN.fullmatch(user_principal) is not None
        and _GUID_PATTERN.fullmatch(system_principal) is not None,
        "agent principal IDs must be GUIDs",
    )

    properties = _mapping(agent.get("properties"), "foundation.agent.properties")
    _require(
        properties.get("provisioningState") == "Succeeded",
        "agent provisioning did not succeed",
    )
    _require(
        properties.get("upgradeChannel") == "Stable",
        "agent must use the Stable upgrade channel",
    )
    _require(
        _mapping(
            properties.get("agentLoggingConfiguration"),
            "foundation.agent.properties.agentLoggingConfiguration",
        ).get("appInsightsConnectionString")
        == "<redacted>",
        "agent logging connection string must be configured and redacted",
    )
    action = _mapping(
        properties.get("actionConfiguration"),
        "foundation.agent.properties.actionConfiguration",
    )
    action_identity = _mapping(
        action.get("identity"),
        "foundation.agent.properties.actionConfiguration.identity",
    )
    _require(
        action.get("actionMode") == "Review"
        and action.get("accessLevel") == "Low",
        "agent action configuration must be Review/Low",
    )
    _require(
        action_identity.get("type") == "UserAssigned"
        and _same_resource(
            action_identity.get("identityResourceId"),
            user_identity_id,
        ),
        "agent actions must use the exact user-assigned identity",
    )
    knowledge = _mapping(
        properties.get("knowledgeGraphConfiguration"),
        "foundation.agent.properties.knowledgeGraphConfiguration",
    )
    managed_resources = _array(
        knowledge.get("managedResources"),
        "foundation.agent.properties.knowledgeGraphConfiguration.managedResources",
    )
    knowledge_identity = _mapping(
        knowledge.get("identity"),
        "foundation.agent.properties.knowledgeGraphConfiguration.identity",
    )
    _require(
        len(managed_resources) == 1
        and _same_resource(managed_resources[0], participant_rg),
        "knowledge graph scope must be the exact participant resource group",
    )
    _require(
        knowledge_identity.get("type") == "UserAssigned"
        and _same_resource(
            knowledge_identity.get("identityResourceId"),
            user_identity_id,
        ),
        "knowledge graph must use the exact user-assigned identity",
    )
    incident_management = _mapping(
        properties.get("incidentManagementConfiguration"),
        "foundation.agent.properties.incidentManagementConfiguration",
    )
    _require(
        incident_management.get("type") == "AzMonitor",
        "agent incident integration must be Azure Monitor",
    )
    _require(
        not _contains_key(
            agent,
            {
                "onbehalfof",
                "onbehalfofelevation",
                "oboelevation",
                "incidentfilters",
            },
        ),
        "agent capture contains forbidden OBO or opaque response-plan settings",
    )

    connector_summaries: list[dict[str, str]] = []
    connectors = _array(foundation["connectors"], "foundation.connectors")
    by_name: dict[str, dict[str, Any]] = {}
    for index, raw_connector in enumerate(connectors):
        connector_capture = _mapping(
            raw_connector,
            f"foundation.connectors[{index}]",
        )
        request = _mapping(
            connector_capture["request"],
            f"foundation.connectors[{index}].request",
        )
        connector = _mapping(
            connector_capture["response"],
            f"foundation.connectors[{index}].response",
        )
        name = _string(
            connector.get("name"),
            f"foundation.connectors[{index}].response.name",
        )
        _require(name not in by_name, f"duplicate connector: {name}")
        connector_id = _string(
            connector.get("id"),
            f"foundation.connectors[{index}].response.id",
        )
        _require(
            _same_resource(
                connector_id,
                f"{agent_id}/connectors/{name}",
            ),
            f"{name} connector is not a child of the validated agent",
        )
        _require(
            request
            == {
                "method": "GET",
                "url": (
                    f"{connector_id}?api-version={_CONNECTOR_API_VERSION}"
                ),
            },
            f"{name} connector evidence must be the exact 2026 ARM GET",
        )
        _require(
            connector.get("type") == "Microsoft.App/agents/connectors",
            f"{name} connector type differs",
        )
        by_name[name] = connector
    expected_connectors = {
        "application-insights": (
            "AppInsights",
            handoff["observability"]["applicationInsightsResourceId"],
            {"armResourceId", "resource.name", "appId"},
        ),
        "log-analytics": (
            "LogAnalytics",
            handoff["observability"]["logAnalyticsWorkspaceResourceId"],
            {"armResourceId", "resource.name"},
        ),
    }
    _require(
        set(by_name) == set(expected_connectors),
        "connector set differs from the frozen contract",
    )
    for name, (connector_type, source_id, required_properties) in (
        expected_connectors.items()
    ):
        connector_properties = _mapping(
            by_name[name].get("properties"),
            f"foundation connector {name}.properties",
        )
        extended = _mapping(
            connector_properties.get("extendedProperties"),
            f"foundation connector {name}.extendedProperties",
        )
        _require(
            connector_properties.get("dataConnectorType") == connector_type,
            f"{name} connector type differs",
        )
        _require(
            _same_resource(connector_properties.get("dataSource"), source_id)
            and _same_resource(extended.get("armResourceId"), source_id),
            f"{name} connector data source differs from the handoff",
        )
        _require(
            connector_properties.get("identity") == "system",
            f"{name} connector must use the system identity",
        )
        _require(
            connector_properties.get("provisioningState") == "Succeeded",
            f"{name} connector provisioning did not succeed",
        )
        _require(
            required_properties.issubset(extended),
            f"{name} connector metadata is incomplete",
        )
        connector_summaries.append(
            {
                "name": name,
                "type": connector_type,
                "dataSource": source_id,
                "identity": "system",
            }
        )

    custom_capture = _mapping(
        foundation["customRollbackRole"],
        "foundation.customRollbackRole",
    )
    custom_role = _mapping(
        custom_capture["response"],
        "foundation.customRollbackRole.response",
    )
    custom_properties = _mapping(
        custom_role.get("properties"),
        "foundation.customRollbackRole.response.properties",
    )
    permissions = _array(
        custom_properties.get("permissions"),
        "foundation.customRollbackRole.response.properties.permissions",
    )
    _require(len(permissions) == 1, "custom rollback role needs one permission set")
    permission = _mapping(permissions[0], "custom rollback role permission")
    _require(
        set(_array(permission.get("actions"), "custom role actions"))
        == _CUSTOM_ROLE_ACTIONS,
        "custom rollback role actions differ",
    )
    for field in ("notActions", "dataActions", "notDataActions"):
        _require(
            _array(permission.get(field), f"custom role {field}") == [],
            f"custom rollback role {field} must be empty",
        )
    _require(
        custom_properties.get("roleName")
        == "MicroHack Container App Traffic Rollback",
        "custom rollback role name differs",
    )
    _require(
        custom_properties.get("assignableScopes") == [participant_rg],
        "custom rollback role assignable scope differs",
    )
    custom_role_id = _role_id(
        custom_role.get("id"),
        "foundation.customRollbackRole.response.id",
    )

    assignments = _mapping(
        foundation["roleAssignments"],
        "foundation.roleAssignments",
    )
    user_records = _role_records(
        assignments["userAssigned"],
        "foundation.roleAssignments.userAssigned",
        user_principal,
        subscription_id,
        require_effective_access=True,
    )
    system_records = _role_records(
        assignments["systemAssigned"],
        "foundation.roleAssignments.systemAssigned",
        system_principal,
        subscription_id,
        require_effective_access=True,
    )
    facilitator_records = _role_records(
        assignments["facilitator"],
        "foundation.roleAssignments.facilitator",
        _principal_from_inventory(assignments["facilitator"], "facilitator"),
        subscription_id,
        human_roles_only=True,
    )
    participant_records = _role_records(
        assignments["participant"],
        "foundation.roleAssignments.participant",
        _principal_from_inventory(assignments["participant"], "participant"),
        subscription_id,
        human_roles_only=True,
    )
    facilitator_principal = facilitator_records[0][0]
    participant_principal = participant_records[0][0]
    subscription_scope = _subscription_scope(subscription_id).casefold()
    participant_scope = participant_rg.casefold()
    container_scope = container_app_id.casefold()
    agent_scope = agent_id.casefold()
    expected_user = {
        (user_principal, _ROLE_READER, participant_scope),
        (user_principal, _ROLE_LOG_ANALYTICS_READER, participant_scope),
        (user_principal, _ROLE_MONITORING_READER, participant_scope),
        (user_principal, _ROLE_MONITORING_CONTRIBUTOR, subscription_scope),
        (user_principal, custom_role_id, container_scope),
    }
    expected_system = {
        (system_principal, _ROLE_READER, participant_scope),
        (system_principal, _ROLE_LOG_ANALYTICS_READER, participant_scope),
        (system_principal, _ROLE_MONITORING_READER, participant_scope),
    }
    _require(set(user_records) == expected_user, "user-assigned RBAC differs")
    _require(set(system_records) == expected_system, "system-assigned RBAC differs")
    _require(
        set(facilitator_records)
        == {(facilitator_principal, _ROLE_SRE_ADMINISTRATOR, agent_scope)},
        "facilitator must have only SRE Agent Administrator at the agent",
    )
    _require(
        set(participant_records)
        == {(participant_principal, _ROLE_SRE_STANDARD_USER, agent_scope)},
        "participant must have only SRE Agent Standard User at the agent",
    )

    availability = _mapping(
        foundation["availabilityPreflight"],
        "foundation.availabilityPreflight",
    )
    _require(
        availability["goNoGo"] == "go"
        and all(
            availability[field] is True
            for field in (
                "providerRegistered",
                "locationAvailable",
                "networkReachable",
                "agentReady",
                "connectorsReady",
            )
        ),
        "SRE Agent availability preflight is not go",
    )

    summary = {
        "agentApiVersion": _AGENT_API_VERSION,
        "connectorApiVersion": _CONNECTOR_API_VERSION,
        "provisioningState": "Succeeded",
        "location": agent["location"],
        "identities": {
            "userAssignedResourceId": user_identity_id,
            "userAssignedPrincipalId": user_principal,
            "systemAssignedPrincipalId": system_principal,
        },
        "actionConfiguration": {
            "mode": "Review",
            "accessLevel": "Low",
            "identity": "UserAssigned",
        },
        "connectors": sorted(
            connector_summaries,
            key=lambda item: item["name"],
        ),
        "roleAssignments": {
            "userAssignedCount": len(user_records),
            "systemAssignedCount": len(system_records),
            "facilitatorRoleDefinitionId": _ROLE_SRE_ADMINISTRATOR,
            "participantRoleDefinitionId": _ROLE_SRE_STANDARD_USER,
            "customRollbackRoleDefinitionId": custom_role_id,
            "subscriptionMonitoringContributorException": True,
        },
        "availability": "go",
    }
    context = {
        "subscriptionId": subscription_id,
        "participantResourceGroupId": participant_rg,
        "agentResourceGroupId": agent_rg,
        "agentResourceId": agent_id,
        "agentName": _string(agent["name"], "foundation.agent.response.name"),
        "agentApplicationInsightsResourceId": agent_app_insights_id,
        "agentLogAnalyticsWorkspaceResourceId": agent_workspace_id,
        "userPrincipalId": user_principal,
        "systemPrincipalId": system_principal,
        "facilitatorPrincipalId": facilitator_principal,
        "participantPrincipalId": participant_principal,
    }
    return summary, context


def _principal_from_inventory(capture: Any, name: str) -> str:
    """Read the single principal represented by a human-role inventory."""
    document = _mapping(capture, f"foundation.roleAssignments.{name}")
    response = _mapping(
        document.get("response"),
        f"foundation.roleAssignments.{name}.response",
    )
    data = _array(
        response.get("data"),
        f"foundation.roleAssignments.{name}.response.data",
    )
    _require(len(data) == 1, f"{name} RBAC inventory must contain one role")
    properties = _mapping(
        _mapping(data[0], f"{name} role assignment").get("properties"),
        f"{name} role assignment properties",
    )
    return _string(properties.get("principalId"), f"{name} principalId")


def _query_row(
    query_capture: dict[str, Any],
    name: str,
) -> dict[str, Any]:
    """Return the only row from one Azure Monitor query response."""
    response = _mapping(query_capture["response"], f"{name}.response")
    tables = _array(response.get("tables"), f"{name}.response.tables")
    _require(len(tables) == 1, f"{name} must contain one result table")
    table = _mapping(tables[0], f"{name}.response.tables[0]")
    columns = [
        _string(_mapping(column, f"{name} column").get("name"), f"{name} column")
        for column in _array(table.get("columns"), f"{name}.columns")
    ]
    rows = _array(table.get("rows"), f"{name}.rows")
    _require(len(rows) == 1, f"{name} must contain one result row")
    row = _array(rows[0], f"{name}.rows[0]")
    _require(len(row) == len(columns), f"{name} row width differs")
    return dict(zip(columns, row, strict=True))


def _audit_rows(
    query_capture: dict[str, Any],
) -> list[dict[str, Any]]:
    """Parse the exact bounded SRE Agent audit query response."""
    response = _mapping(query_capture["response"], "incident.agentAudit.response")
    tables = _array(response.get("tables"), "incident.agentAudit.response.tables")
    _require(len(tables) == 1, "agent audit must contain one result table")
    table = _mapping(tables[0], "incident.agentAudit.response.tables[0]")
    columns = [
        _string(
            _mapping(column, "incident.agentAudit column").get("name"),
            "incident.agentAudit column name",
        )
        for column in _array(table.get("columns"), "incident.agentAudit.columns")
    ]
    expected_columns = [
        "timestamp",
        "name",
        "AgentId",
        "AgentName",
        "TraceId",
        "SpanId",
        "ParentSpanId",
        "ThreadId",
        "CorrelationId",
        "LogTimestamp",
        "Properties",
    ]
    _require(columns == expected_columns, "agent audit columns differ")
    rows: list[dict[str, Any]] = []
    for index, raw_row in enumerate(
        _array(table.get("rows"), "incident.agentAudit.rows")
    ):
        row = _array(raw_row, f"incident.agentAudit.rows[{index}]")
        _require(
            len(row) == len(columns),
            f"incident.agentAudit.rows[{index}] width differs",
        )
        rows.append(dict(zip(columns, row, strict=True)))
    return rows


def _validate_response_plan(
    response_plan: dict[str, Any],
    registry: dict[str, Any],
    context: dict[str, str],
    foundation_observed_at: datetime,
) -> dict[str, Any]:
    """Validate the source-bound portal Review-plan preflight."""
    _require(
        response_plan["producer"] == "azure-portal-facilitator-export"
        and response_plan["capturedByPrincipalId"]
        == context["facilitatorPrincipalId"],
        "response-plan capture is not facilitator source evidence",
    )
    _require(
        _same_resource(
            response_plan["agentResourceId"],
            context["agentResourceId"],
        )
        and _same_resource(
            response_plan["agentApplicationInsightsResourceId"],
            context["agentApplicationInsightsResourceId"],
        ),
        "response-plan capture targets another agent or audit source",
    )
    plan = _mapping(response_plan["plan"], "responsePlan.plan")
    _require(
        plan
        == {
            "platform": "AzureMonitor",
            "name": plan["name"],
            "autonomyMode": "Review",
            "quickstartPlanEnabled": False,
            "participantApprovalAllowed": False,
            "reviewProposalObserved": True,
        },
        "portal response plan differs from the frozen Review protocol",
    )
    incident = _mapping(
        response_plan["testIncident"],
        "responsePlan.testIncident",
    )
    test_start = _timestamp(incident["testStart"], "responsePlan testStart")
    delivered_at = _timestamp(
        incident["deliveredAt"],
        "responsePlan deliveredAt",
    )
    reviewed_at = _timestamp(
        incident["reviewedAt"],
        "responsePlan reviewedAt",
    )
    test_end = _timestamp(incident["testEnd"], "responsePlan testEnd")
    captured_at = _timestamp(
        response_plan["capturedAt"],
        "responsePlan capturedAt",
    )
    _require(
        test_start <= delivered_at < reviewed_at <= test_end <= captured_at
        <= foundation_observed_at,
        "response-plan preflight chronology is invalid",
    )
    _require(
        incident["decision"] == "Rejected"
        and incident["reviewedByPrincipalId"]
        == context["facilitatorPrincipalId"]
        and incident["writeExecuted"] is False,
        "response-plan preflight did not stop at facilitator Review",
    )

    audit = _mapping(response_plan["audit"], "responsePlan.audit")
    audit_request = _mapping(audit["request"], "responsePlan.audit.request")
    expected_query = _render_query(
        registry["queries"]["responsePlanPreflightAudit"],
        testStart=incident["testStart"],
        testEnd=incident["testEnd"],
        agentId=context["agentResourceId"],
        threadId=incident["threadId"],
    )
    expected_endpoint = _application_insights_query_endpoint(
        context["agentApplicationInsightsResourceId"],
        registry,
    )
    _require(
        audit_request
        == {
            "method": "POST",
            "url": expected_endpoint,
            "query": expected_query,
        },
        "response-plan audit query or source differs",
    )
    rows = _audit_rows(audit)
    _require(
        [row["name"] for row in rows]
        == ["IncidentActivitySnapshot", "AgentResponse", "ApprovalDecision"],
        "response-plan preflight audit sequence differs",
    )
    for row in rows:
        _require(
            _same_resource(row["AgentId"], context["agentResourceId"])
            and row["AgentName"] == context["agentName"]
            and row["TraceId"] == incident["traceId"]
            and row["ThreadId"] == incident["threadId"]
            and row["CorrelationId"] == incident["correlationId"]
            and row["SpanId"]
            and row["LogTimestamp"] == row["timestamp"],
            f"response-plan audit correlation differs for {row['name']}",
        )
    snapshot = _mapping(rows[0]["Properties"], "preflight snapshot Properties")
    proposal = _mapping(rows[1]["Properties"], "preflight response Properties")
    decision = _mapping(rows[2]["Properties"], "preflight decision Properties")
    _require(
        snapshot.get("alertId") == incident["alertId"]
        and snapshot.get("testIncidentId") == incident["id"],
        "response-plan test alert is not bound to the agent audit",
    )
    _require(
        proposal
        == {
            "reviewRequired": True,
            "writeRequested": False,
        },
        "response-plan test did not produce a non-writing review proposal",
    )
    _require(
        decision
        == {
            "decision": "Rejected",
            "reviewedByPrincipalId": context["facilitatorPrincipalId"],
            "writeExecuted": False,
        },
        "response-plan test decision differs from portal evidence",
    )
    _require(
        _timestamp(rows[0]["timestamp"], "preflight snapshot timestamp")
        == delivered_at
        and _timestamp(rows[2]["timestamp"], "preflight decision timestamp")
        == reviewed_at,
        "response-plan portal and audit timestamps differ",
    )
    return {
        "producer": "azure-portal-facilitator-export",
        "platform": "AzureMonitor",
        "name": plan["name"],
        "autonomyMode": "Review",
        "quickstartPlanEnabled": False,
        "testIncidentId": incident["id"],
        "participantApprovalAllowed": False,
    }


def _traffic_weights(
    snapshot: Any,
    name: str,
    application_id: str,
) -> tuple[dict[str, int], datetime]:
    """Validate one native ARM revision-list traffic capture."""
    capture = _mapping(snapshot, name)
    expected_url = f"{application_id}/revisions?api-version=2025-01-01"
    _require(
        _mapping(capture.get("request"), f"{name}.request")
        == {"method": "GET", "url": expected_url},
        f"{name} does not use the exact Container App ARM revisions list",
    )
    response = _mapping(capture.get("response"), f"{name}.response")
    _require(
        "nextLink" in response and response.get("nextLink") is None,
        f"{name} is paginated",
    )
    weights: dict[str, int] = {}
    for index, raw_revision in enumerate(
        _array(response.get("value"), f"{name}.response.value")
    ):
        revision = _mapping(raw_revision, f"{name}.response.value[{index}]")
        revision_name = _string(
            revision.get("name"),
            f"{name}.response.value[{index}].name",
        )
        _require(revision_name not in weights, f"{name} repeats a revision")
        _require(
            _same_resource(
                revision.get("id"),
                f"{application_id}/revisions/{revision_name}",
            )
            and revision.get("type") == "Microsoft.App/containerApps/revisions",
            f"{name} contains another resource",
        )
        properties = _mapping(
            revision.get("properties"),
            f"{name}.response.value[{index}].properties",
        )
        _require(
            isinstance(properties.get("active"), bool),
            f"{name} revision active state is not native",
        )
        weight = _integer(
            properties.get("trafficWeight"),
            f"{name}.response.value[{index}].properties.trafficWeight",
        )
        _require(0 <= weight <= 100, f"{name} has an invalid traffic weight")
        weights[revision_name] = weight
    _require(sum(weights.values()) == 100, f"{name} traffic does not total 100")
    return weights, _timestamp(capture.get("observedAt"), f"{name}.observedAt")


def _container_from_revision(revision: dict[str, Any], name: str) -> dict[str, Any]:
    """Return the sole catalog container from one revision snapshot."""
    properties = _mapping(revision.get("properties"), f"{name}.properties")
    template = _mapping(properties.get("template"), f"{name}.properties.template")
    containers = _array(
        template.get("containers"),
        f"{name}.properties.template.containers",
    )
    catalog = [
        _mapping(item, f"{name} catalog container")
        for item in containers
        if isinstance(item, dict) and item.get("name") == "catalog"
    ]
    _require(len(catalog) == 1, f"{name} must contain one catalog container")
    return catalog[0]


def _environment_maps(
    container: dict[str, Any],
    name: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Split one container environment into values and secret references."""
    values: dict[str, str] = {}
    secrets: dict[str, str] = {}
    for index, raw_entry in enumerate(_array(container.get("env"), f"{name}.env")):
        entry = _mapping(raw_entry, f"{name}.env[{index}]")
        variable = _string(entry.get("name"), f"{name}.env[{index}].name")
        _require(
            variable not in values and variable not in secrets,
            f"{name} repeats environment variable {variable}",
        )
        if "secretRef" in entry:
            secrets[variable] = _string(
                entry.get("secretRef"),
                f"{name}.env[{index}].secretRef",
            )
        else:
            values[variable] = _string(
                entry.get("value"),
                f"{name}.env[{index}].value",
            )
    return values, secrets


def _probe_paths(container: dict[str, Any], name: str) -> dict[str, str]:
    """Return exact HTTP probe paths by probe type."""
    paths: dict[str, str] = {}
    for index, raw_probe in enumerate(
        _array(container.get("probes"), f"{name}.probes")
    ):
        probe = _mapping(raw_probe, f"{name}.probes[{index}]")
        probe_type = _string(probe.get("type"), f"{name}.probes[{index}].type")
        http_get = _mapping(
            probe.get("httpGet"),
            f"{name}.probes[{index}].httpGet",
        )
        _require(
            probe_type not in paths,
            f"{name} repeats the {probe_type} probe",
        )
        paths[probe_type] = _string(
            http_get.get("path"),
            f"{name}.probes[{index}].httpGet.path",
        )
    return paths


def _container_app_state(
    capture: Any,
    name: str,
    container_app_id: str,
) -> tuple[dict[str, int], datetime, dict[str, Any]]:
    """Normalize one raw Container App GET for a traffic-only comparison."""
    document = _mapping(capture, name)
    observed_at = _timestamp(document.get("observedAt"), f"{name}.observedAt")
    request = _mapping(document.get("request"), f"{name}.request")
    expected_url = f"{container_app_id}?api-version=2025-01-01"
    _require(
        request == {"method": "GET", "url": expected_url},
        f"{name} must use the exact Container App ARM GET",
    )
    response = _mapping(document.get("response"), f"{name}.response")
    _require(
        _same_resource(response.get("id"), container_app_id)
        and response.get("type") == "Microsoft.App/containerApps",
        f"{name} targets another Container App",
    )
    normalized = json.loads(json.dumps(response))
    normalized.pop("etag", None)
    normalized.pop("systemData", None)
    properties = _mapping(normalized.get("properties"), f"{name}.properties")
    for field in (
        "provisioningState",
        "runningStatus",
        "latestRevisionName",
        "latestReadyRevisionName",
        "eventStreamEndpoint",
    ):
        properties.pop(field, None)
    configuration = _mapping(
        properties.get("configuration"),
        f"{name}.properties.configuration",
    )
    ingress = _mapping(
        configuration.get("ingress"),
        f"{name}.properties.configuration.ingress",
    )
    traffic = _array(
        ingress.get("traffic"),
        f"{name}.properties.configuration.ingress.traffic",
    )
    weights: dict[str, int] = {}
    for index, raw_target in enumerate(traffic):
        target = _mapping(raw_target, f"{name}.traffic[{index}]")
        revision = _string(
            target.get("revisionName"),
            f"{name}.traffic[{index}].revisionName",
        )
        weight = _integer(
            target.get("weight"),
            f"{name}.traffic[{index}].weight",
        )
        _require(revision not in weights, f"{name} repeats a traffic target")
        _require(0 <= weight <= 100, f"{name} has an invalid traffic weight")
        weights[revision] = weight
    _require(sum(weights.values()) == 100, f"{name} traffic does not total 100")
    ingress["traffic"] = "<traffic-only-diff>"
    return weights, observed_at, normalized


def _render_query(template: str, **values: str) -> str:
    """Render one frozen KQL template with literal contract values."""
    return template.format(**values)


def _validate_investigation(
    investigation: dict[str, Any],
    registry: dict[str, Any],
    handoff: dict[str, Any],
    incident_start: str,
    healthy_revision: str,
    bad_revision: str,
    bad_host: str,
    expected_digest: str,
    seed_time: datetime,
    bad_time: datetime,
    fired_at: datetime,
) -> dict[str, Any]:
    """Validate the source-bound diagnosis that supports the rollback."""
    incident_start_time = _timestamp(
        incident_start,
        "incident.investigation incidentStart",
    )
    investigation_end = _timestamp(
        investigation["investigationEnd"],
        "incident.investigation.investigationEnd",
    )
    _require(
        bad_time < fired_at <= investigation_end,
        "investigation window does not follow failure and alert evidence",
    )
    application_id = handoff["application"]["resourceId"]
    application_insights_id = handoff["observability"][
        "applicationInsightsResourceId"
    ]
    query_endpoint = _application_insights_query_endpoint(
        application_insights_id,
        registry,
    )

    deployment = _mapping(
        investigation["deploymentHistory"],
        "incident.investigation.deploymentHistory",
    )
    deployment_observed = _timestamp(
        deployment["observedAt"],
        "incident.investigation.deploymentHistory.observedAt",
    )
    _require(
        _mapping(
            deployment["request"],
            "incident.investigation.deploymentHistory.request",
        )
        == {
            "method": "GET",
            "url": f"{application_id}/revisions?api-version=2025-01-01",
        },
        "deployment history does not use the exact Container App ARM list",
    )
    deployment_response = _mapping(
        deployment["response"],
        "incident.investigation.deploymentHistory.response",
    )
    _require(
        deployment_response.get("nextLink") is None,
        "deployment history is paginated",
    )
    revisions: dict[str, dict[str, Any]] = {}
    for index, raw_revision in enumerate(
        _array(
            deployment_response.get("value"),
            "incident.investigation.deploymentHistory.response.value",
        )
    ):
        revision = _mapping(
            raw_revision,
            f"deployment history revision[{index}]",
        )
        name = _string(revision.get("name"), "deployment history revision name")
        _require(name not in revisions, "deployment history repeats a revision")
        _require(
            _same_resource(
                revision.get("id"),
                f"{application_id}/revisions/{name}",
            )
            and revision.get("type") == "Microsoft.App/containerApps/revisions",
            "deployment history contains another resource",
        )
        revisions[name] = revision
    _require(
        healthy_revision in revisions and bad_revision in revisions,
        "deployment history omits an incident revision",
    )
    deployment_times: dict[str, datetime] = {}
    for name in (healthy_revision, bad_revision):
        properties = _mapping(
            revisions[name].get("properties"),
            f"deployment history {name} properties",
        )
        deployment_times[name] = _timestamp(
            properties.get("createdTime"),
            f"deployment history {name} createdTime",
        )
        _require(
            properties.get("active") is True,
            f"deployment history {name} is not active",
        )
        container = _container_from_revision(
            revisions[name],
            f"deployment history {name}",
        )
        _require(
            _string(
                container.get("image"),
                f"deployment history {name} image",
            ).endswith(f"@{expected_digest}"),
            "deployment history image differs from the handoff digest",
        )
    healthy_properties = _mapping(
        revisions[healthy_revision]["properties"],
        "deployment history healthy properties",
    )
    bad_properties = _mapping(
        revisions[bad_revision]["properties"],
        "deployment history bad properties",
    )
    _require(
        deployment_times[healthy_revision] < deployment_times[bad_revision]
        == seed_time
        and deployment_times[bad_revision] < incident_start_time
        and deployment_times[bad_revision] < bad_time
        and healthy_properties.get("trafficWeight") == 0
        and bad_properties.get("trafficWeight") == 100,
        "deployment history does not identify the seeded affected revision",
    )

    def observed_query(
        key: str,
        query_name: str,
        query_values: dict[str, str],
    ) -> tuple[dict[str, Any], datetime]:
        capture = _mapping(
            investigation[key],
            f"incident.investigation.{key}",
        )
        observed_at = _timestamp(
            capture["observedAt"],
            f"incident.investigation.{key}.observedAt",
        )
        request = _mapping(
            capture["request"],
            f"incident.investigation.{key}.request",
        )
        _require(
            request
            == {
                "method": "POST",
                "url": query_endpoint,
                "query": _render_query(
                    registry["queries"][query_name],
                    **query_values,
                ),
            },
            f"investigation {key} query or source differs",
        )
        return _query_row(capture, f"incident.investigation.{key}"), observed_at

    request_values = {
        "incidentStart": incident_start,
        "investigationEnd": investigation["investigationEnd"],
        "serviceName": handoff["observability"]["serviceName"],
        "sourceCommit": handoff["source"]["commitSha"],
        "badRevision": bad_revision,
    }
    request_row, request_observed = observed_query(
        "requestFailures",
        "investigationRequestFailures",
        request_values,
    )
    exception_row, exception_observed = observed_query(
        "exceptions",
        "investigationExceptions",
        request_values,
    )

    database_family = handoff["database"]["family"]
    database_contract = _mapping(
        registry["investigation"]["databaseFamilies"].get(database_family),
        f"investigation database family {database_family}",
    )
    dependency_values = dict(request_values)
    dependency_values["databaseSystem"] = database_contract["telemetrySystem"]
    dependency_row, dependency_observed = observed_query(
        "databaseDependencies",
        "investigationDatabaseDependencies",
        dependency_values,
    )

    request_count = _integer(
        request_row.get("RequestCount"),
        "investigation RequestCount",
    )
    failed_requests = _integer(
        request_row.get("FailedRequests"),
        "investigation FailedRequests",
    )
    request_first = _timestamp(
        request_row.get("FirstFailure"),
        "investigation request FirstFailure",
    )
    request_last = _timestamp(
        request_row.get("LastFailure"),
        "investigation request LastFailure",
    )
    _require(
        request_count >= failed_requests > 0
        and bad_time <= request_first <= request_last <= investigation_end,
        "investigation request failures do not identify the bad revision window",
    )

    exception_count = _integer(
        exception_row.get("ExceptionCount"),
        "investigation ExceptionCount",
    )
    exception_first = _timestamp(
        exception_row.get("FirstException"),
        "investigation FirstException",
    )
    exception_last = _timestamp(
        exception_row.get("LastException"),
        "investigation LastException",
    )
    exception_types = sorted(
        {
            _string(value, "investigation exception type")
            for value in _array(
                exception_row.get("ExceptionTypes"),
                "investigation ExceptionTypes",
            )
        }
    )
    _require(
        exception_count > 0
        and exception_types
        and bad_time <= exception_first <= exception_last <= investigation_end,
        "investigation exceptions do not identify the bad revision window",
    )

    dependency_count = _integer(
        dependency_row.get("DependencyCount"),
        "investigation DependencyCount",
    )
    failed_dependencies = _integer(
        dependency_row.get("FailedDependencies"),
        "investigation FailedDependencies",
    )
    dependency_first = _timestamp(
        dependency_row.get("FirstFailure"),
        "investigation dependency FirstFailure",
    )
    dependency_last = _timestamp(
        dependency_row.get("LastFailure"),
        "investigation dependency LastFailure",
    )
    dependency_targets = sorted(
        {
            _string(value, "investigation dependency target")
            for value in _array(
                dependency_row.get("Targets"),
                "investigation dependency Targets",
            )
        }
    )
    _require(
        dependency_count >= failed_dependencies > 0
        and bad_host in dependency_targets
        and bad_time <= dependency_first <= dependency_last <= investigation_end,
        "investigation dependencies do not identify the invalid endpoint",
    )

    database_resource_id = handoff["database"]["resourceId"]
    if database_family == "azure-sql":
        availability_resource_id = database_resource_id
        availability_type = "Microsoft.Sql/servers/databases"
        status_field = "status"
        database_label = "Azure SQL database"
    elif database_family == "postgresql-flexible":
        availability_resource_id = database_resource_id.rsplit("/databases/", 1)[0]
        availability_type = "Microsoft.DBforPostgreSQL/flexibleServers"
        status_field = "state"
        database_label = "PostgreSQL Flexible Server"
    else:
        raise ValueError(f"unsupported investigation database family: {database_family}")
    availability = _mapping(
        investigation["databaseAvailability"],
        "incident.investigation.databaseAvailability",
    )
    availability_observed = _timestamp(
        availability["observedAt"],
        "incident.investigation.databaseAvailability.observedAt",
    )
    _require(
        _mapping(
            availability["request"],
            "incident.investigation.databaseAvailability.request",
        )
        == {
            "method": "GET",
            "url": (
                f"{availability_resource_id}?api-version="
                f"{database_contract['availabilityApiVersion']}"
            ),
        },
        "selected-database availability does not use the exact ARM GET",
    )
    availability_response = _mapping(
        availability["response"],
        "incident.investigation.databaseAvailability.response",
    )
    availability_status = _mapping(
        availability_response.get("properties"),
        "selected-database availability properties",
    ).get(status_field)
    _require(
        _same_resource(
            availability_response.get("id"),
            availability_resource_id,
        )
        and availability_response.get("type") == availability_type
        and availability_status == database_contract["availabilityStatus"],
        "selected database is not proven available",
    )

    observed_times = [
        deployment_observed,
        request_observed,
        exception_observed,
        dependency_observed,
        availability_observed,
    ]
    _require(
        observed_times == sorted(observed_times)
        and investigation_end < observed_times[0],
        "investigation evidence chronology differs",
    )
    evidence_references = [
        "investigation.deploymentHistory",
        "investigation.requestFailures",
        "investigation.exceptions",
        "investigation.databaseDependencies",
        "investigation.databaseAvailability",
    ]
    supporting_evidence = {
        "requestFailures": failed_requests,
        "exceptions": exception_count,
        "exceptionTypes": exception_types,
        "failedDatabaseDependencies": failed_dependencies,
        "databaseSystem": database_contract["telemetrySystem"],
        "dependencyTargets": dependency_targets,
        "selectedDatabaseResourceId": availability_resource_id,
        "selectedDatabaseStatus": availability_status,
    }
    alternatives = [
        {"code": code, "disposition": "rejected"}
        for code in registry["investigation"]["alternativeCodes"]
    ]
    response = {
        "affectedRevision": bad_revision,
        "incidentStart": incident_start,
        "investigationEnd": investigation["investigationEnd"],
        "evidenceReferences": evidence_references,
        "supportingEvidence": supporting_evidence,
        "hypothesisCode": registry["investigation"]["hypothesisCode"],
        "alternatives": alternatives,
        "proposedOperation": "container-app-traffic-weight-update",
        "healthyRevision": healthy_revision,
        "healthyRevisionWeight": 100,
        "badRevision": bad_revision,
        "badRevisionWeight": 0,
        "blastRadius": registry["investigation"]["blastRadius"],
        "verificationPlan": registry["investigation"]["verificationPlan"],
    }
    assessment_evidence = {
        "requestFailures": failed_requests,
        "exceptions": exception_count,
        "failedDatabaseDependencies": failed_dependencies,
        "selectedDatabaseStatus": availability_status,
    }
    root_cause = (
        f"Revision {bad_revision} used invalid selected-database host {bad_host} "
        f"while the selected {database_label} remained {availability_status}; "
        "the retained image digest matched the healthy revision."
    )
    return {
        "agentResponse": response,
        "assessment": {
            "affectedRevision": bad_revision,
            "rootCauseCode": registry["investigation"]["hypothesisCode"],
            "rootCause": root_cause,
            "supportingEvidence": assessment_evidence,
            "evidenceReferences": evidence_references,
            "alternativesConsidered": registry["investigation"]["alternativeCodes"],
            "recommendedAction": (
                "Restore 100 percent traffic to the retained CI/CD-proven "
                "healthy handoff revision."
            ),
            "preventionAction": (
                "Validate the selected-database endpoint and readiness path "
                "before assigning production traffic."
            ),
        },
        "summary": {
            "windowEnd": investigation["investigationEnd"],
            "evidenceObservedAt": investigation["databaseAvailability"]["observedAt"],
            "affectedRevision": bad_revision,
            "deploymentCount": len(revisions),
            "evidenceReferences": evidence_references,
            "supportingEvidence": supporting_evidence,
            "hypothesisCode": registry["investigation"]["hypothesisCode"],
            "alternativesRejected": registry["investigation"]["alternativeCodes"],
            "blastRadius": registry["investigation"]["blastRadius"],
            "verificationPlan": registry["investigation"]["verificationPlan"],
        },
        "firstObservedAt": observed_times[0],
        "lastObservedAt": observed_times[-1],
    }


def _validate_incident(
    incident: dict[str, Any],
    registry: dict[str, Any],
    handoff: dict[str, Any],
    foundation_observed_at: datetime,
    context: dict[str, str],
) -> dict[str, Any]:
    """Validate the reviewed rollback state machine and recovery evidence."""
    start = _timestamp(incident["incidentStart"], "incident.incidentStart")
    end = _timestamp(incident["incidentEnd"], "incident.incidentEnd")
    _require(foundation_observed_at < start < end, "incident window chronology differs")
    subject = _mapping(incident["subject"], "incident.subject")
    healthy_revision = _string(
        subject["healthyRevision"],
        "incident.subject.healthyRevision",
    )
    bad_revision = _string(subject["badRevision"], "incident.subject.badRevision")
    _require(
        subject["sliceId"] == handoff["sliceId"],
        "incident slice differs from the handoff",
    )
    _require(
        _same_resource(subject["agentResourceId"], context["agentResourceId"])
        and subject["agentName"] == context["agentName"],
        "incident agent identity differs from the foundation",
    )
    _require(
        _same_resource(
            subject["containerAppResourceId"],
            handoff["application"]["resourceId"],
        ),
        "incident Container App differs from the handoff",
    )
    _require(
        _same_resource(
            subject["applicationInsightsResourceId"],
            handoff["observability"]["applicationInsightsResourceId"],
        ),
        "incident Application Insights resource differs from the handoff",
    )
    _require(
        healthy_revision == handoff["application"]["revisionName"],
        "incident healthy revision is not the CI/CD-proven handoff revision",
    )
    _require(
        bad_revision != healthy_revision,
        "incident bad and healthy revisions must differ",
    )

    seed = _mapping(incident["seed"], "incident.seed")
    seed_time = _timestamp(seed["createdAt"], "incident.seed.createdAt")
    _require(
        foundation_observed_at < seed_time < start,
        "drill revision must be created before the incident window",
    )
    expected_digest = handoff["containerImage"]["digest"]
    _require(seed["imageDigest"] == expected_digest, "seed image digest differs")
    _require(
        seed["databaseHostEnvironmentVariable"] == "CATALOG_DATABASE_HOST",
        "seed changed another environment variable",
    )
    bad_host = _string(seed["badDatabaseHost"], "incident.seed.badDatabaseHost")
    _require(
        bad_host.endswith(".sre-drill.invalid")
        and bad_host != handoff["database"]["server"],
        "seed database host is not the bounded invalid drill endpoint",
    )
    _require(
        seed["secretReferencesPreserved"] is True
        and seed["imageChanged"] is False,
        "seed changed image or secret references",
    )
    _require(
        seed["healthyReadinessPath"] == "/readyz"
        and seed["drillReadinessPath"] == "/healthz"
        and seed["livenessPath"] == "/healthz",
        "seed probe paths differ from the frozen drill",
    )

    healthy_capture = _mapping(
        seed["healthyRevision"],
        "incident.seed.healthyRevision",
    )
    bad_capture = _mapping(seed["revision"], "incident.seed.revision")
    expected_revision_base = f"{subject['containerAppResourceId']}/revisions"
    _require(
        _mapping(
            healthy_capture.get("request"),
            "incident.seed.healthyRevision.request",
        )
        == {
            "method": "GET",
            "url": (
                f"{expected_revision_base}/{healthy_revision}"
                "?api-version=2025-01-01"
            ),
        }
        and _mapping(
            bad_capture.get("request"),
            "incident.seed.revision.request",
        )
        == {
            "method": "GET",
            "url": (
                f"{expected_revision_base}/{bad_revision}"
                "?api-version=2025-01-01"
            ),
        },
        "seed revision evidence does not use the exact ARM GETs",
    )
    healthy_snapshot = _mapping(
        healthy_capture["response"],
        "incident.seed.healthyRevision.response",
    )
    bad_snapshot = _mapping(
        bad_capture["response"],
        "incident.seed.revision.response",
    )
    _require(
        healthy_snapshot.get("name") == healthy_revision
        and bad_snapshot.get("name") == bad_revision,
        "seed revision snapshots differ from the incident subject",
    )
    bad_revision_properties = _mapping(
        bad_snapshot.get("properties"),
        "incident.seed.revision.response.properties",
    )
    _require(
        _integer(
            bad_revision_properties.get("trafficWeight"),
            "incident.seed.revision.response.properties.trafficWeight",
        )
        == 0,
        "drill revision was not created at zero traffic",
    )
    healthy_container = _container_from_revision(
        healthy_snapshot,
        "incident.seed.healthyRevision.response",
    )
    bad_container = _container_from_revision(
        bad_snapshot,
        "incident.seed.revision.response",
    )
    expected_image_suffix = f"@{expected_digest}"
    _require(
        _string(healthy_container.get("image"), "healthy container image").endswith(
            expected_image_suffix
        )
        and _string(bad_container.get("image"), "bad container image").endswith(
            expected_image_suffix
        ),
        "seed revisions do not reuse the exact handoff image digest",
    )
    healthy_values, healthy_secrets = _environment_maps(
        healthy_container,
        "healthy container",
    )
    bad_values, bad_secrets = _environment_maps(bad_container, "bad container")
    expected_healthy_host = _string(
        _mapping(handoff["database"], "handoff.database").get("server"),
        "handoff.database.server",
    )
    healthy_host = _string(
        healthy_values.get("CATALOG_DATABASE_HOST"),
        "healthy container CATALOG_DATABASE_HOST",
    )
    _require(
        healthy_host.casefold() == expected_healthy_host.casefold(),
        "healthy revision database host differs from the handoff",
    )
    _require(
        healthy_secrets == bad_secrets and bool(healthy_secrets),
        "seed did not preserve every secret reference",
    )
    healthy_non_database = {
        key: value
        for key, value in healthy_values.items()
        if key != "CATALOG_DATABASE_HOST"
    }
    bad_non_database = {
        key: value
        for key, value in bad_values.items()
        if key != "CATALOG_DATABASE_HOST"
    }
    _require(
        healthy_non_database == bad_non_database
        and bad_values.get("CATALOG_DATABASE_HOST") == bad_host,
        "seed changed configuration beyond the database host",
    )
    _require(
        _probe_paths(healthy_container, "healthy container")
        == {"Liveness": "/healthz", "Readiness": "/readyz"}
        and _probe_paths(bad_container, "bad container")
        == {"Liveness": "/healthz", "Readiness": "/healthz"},
        "seed probe mutation differs from the frozen drill",
    )

    before_weights, before_time = _traffic_weights(
        seed["trafficBefore"],
        "incident.seed.trafficBefore",
        subject["containerAppResourceId"],
    )
    bad_weights, bad_time = _traffic_weights(
        seed["trafficBad"],
        "incident.seed.trafficBad",
        subject["containerAppResourceId"],
    )
    _require(
        start <= before_time < bad_time < end,
        "seed traffic chronology differs",
    )
    _require(
        before_weights.get(healthy_revision) == 100
        and before_weights.get(bad_revision) == 0,
        "seed did not begin with healthy traffic",
    )
    _require(
        bad_weights.get(healthy_revision) == 0
        and bad_weights.get(bad_revision) == 100,
        "seed did not route traffic to the drill revision",
    )
    _require(
        all(
            weight == 0
            for revision, weight in bad_weights.items()
            if revision != bad_revision
        ),
        "an unrelated revision retained traffic during the drill",
    )

    alert_fired = _mapping(
        incident["alertFired"]["response"],
        "incident.alertFired.response",
    )
    alert_id = _string(alert_fired.get("id"), "incident.alertFired.response.id")
    _require(
        _mapping(
            incident["alertFired"].get("request"),
            "incident.alertFired.request",
        )
        == {
            "method": "GET",
            "url": f"{alert_id}?api-version=2019-05-05",
        },
        "fired alert evidence does not use the exact ARM GET",
    )
    fired_essentials = _mapping(
        _mapping(
            alert_fired.get("properties"),
            "incident.alertFired.response.properties",
        ).get("essentials"),
        "incident.alertFired.response.properties.essentials",
    )
    fired_at = _timestamp(
        fired_essentials.get("firedDateTime"),
        "incident.alertFired firedDateTime",
    )
    _require(
        bad_time < fired_at < end,
        "alert did not fire after bad-revision traffic",
    )
    _require(
        fired_essentials.get("severity") == registry["responsePlan"]["severity"]
        and fired_essentials.get("monitorCondition") == "Fired"
        and _string(
            fired_essentials.get("alertRule"),
            "incident.alertFired alertRule",
        ).startswith(registry["responsePlan"]["alertTitlePrefix"]),
        "fired alert differs from the response-plan contract",
    )
    target_ids = _array(
        fired_essentials.get("targetResourceIds"),
        "incident.alertFired targetResourceIds",
    )
    _require(
        len(target_ids) == 1
        and _same_resource(target_ids[0], subject["containerAppResourceId"]),
        "fired alert targets another resource",
    )

    failure_query = _mapping(
        incident["badRevisionFailures"],
        "incident.badRevisionFailures",
    )
    failure_request = _mapping(
        failure_query["request"],
        "incident.badRevisionFailures.request",
    )
    expected_failure_query = _render_query(
        registry["queries"]["badRevisionFailures"],
        incidentStart=incident["incidentStart"],
        incidentEnd=incident["incidentEnd"],
        badRevision=bad_revision,
    )
    _require(
        failure_request.get("method") == "POST"
        and failure_request.get("query") == expected_failure_query
        and failure_request.get("url")
        == _application_insights_query_endpoint(
            subject["applicationInsightsResourceId"],
            registry,
        ),
        "bad-revision failure query differs from the frozen query",
    )
    failure_row = _query_row(failure_query, "incident.badRevisionFailures")
    request_count = _integer(
        failure_row.get("RequestCount"),
        "bad-revision RequestCount",
    )
    failed_requests = _integer(
        failure_row.get("FailedRequests"),
        "bad-revision FailedRequests",
    )
    _require(
        request_count >= failed_requests > 0,
        "bad revision has no failed request evidence",
    )
    first_failure = _timestamp(
        failure_row.get("FirstFailure"),
        "bad-revision FirstFailure",
    )
    last_failure = _timestamp(
        failure_row.get("LastFailure"),
        "bad-revision LastFailure",
    )
    _require(
        bad_time <= first_failure <= last_failure <= end,
        "bad-revision failures are outside the drill window",
    )
    _require(
        first_failure <= fired_at,
        "alert fired before the observed bad-revision failure",
    )
    investigation_result = _validate_investigation(
        _mapping(
            incident["investigation"],
            "incident.investigation",
        ),
        registry,
        handoff,
        incident["incidentStart"],
        healthy_revision,
        bad_revision,
        bad_host,
        expected_digest,
        seed_time,
        bad_time,
        fired_at,
    )

    audit = _mapping(incident["agentAudit"], "incident.agentAudit")
    audit_request = _mapping(
        audit["request"],
        "incident.agentAudit.request",
    )
    expected_audit_query = _render_query(
        registry["queries"]["agentAudit"],
        incidentStart=incident["incidentStart"],
        incidentEnd=incident["incidentEnd"],
        agentId=context["agentResourceId"],
        threadId=subject["threadId"],
    )
    _require(
        audit_request.get("method") == "POST"
        and audit_request.get("query") == expected_audit_query
        and audit_request.get("url")
        == _application_insights_query_endpoint(
            context["agentApplicationInsightsResourceId"],
            registry,
        ),
        "agent audit query or source differs from the frozen contract",
    )
    audit_rows = _audit_rows(audit)
    expected_event_sequence = [
        "IncidentActivitySnapshot",
        "AgentResponse",
        "AgentToolExecution",
        "ApprovalDecision",
        "AgentAzCliExecution",
        "AgentExecution",
    ]
    _require(
        len(audit_rows) == len(_REQUIRED_AUDIT_EVENTS)
        and [row["name"] for row in audit_rows] == expected_event_sequence,
        "agent audit event sequence differs",
    )
    audit_times = [
        _timestamp(row["timestamp"], f"agent audit {row['name']} timestamp")
        for row in audit_rows
    ]
    _require(audit_times == sorted(audit_times), "agent audit is not ordered")
    _require(
        all(start <= value <= end for value in audit_times),
        "agent audit contains an event outside the incident window",
    )
    for row in audit_rows:
        _require(
            _same_resource(row["AgentId"], context["agentResourceId"])
            and row["AgentName"] == context["agentName"]
            and row["TraceId"] == subject["traceId"]
            and row["ThreadId"] == subject["threadId"]
            and row["CorrelationId"] == subject["correlationId"]
            and row["SpanId"]
            and row["LogTimestamp"] == row["timestamp"],
            f"agent audit correlation differs for {row['name']}",
        )
        _mapping(row["Properties"], f"agent audit {row['name']} Properties")
    by_event = {row["name"]: row for row in audit_rows}
    snapshot = _mapping(
        by_event["IncidentActivitySnapshot"]["Properties"],
        "IncidentActivitySnapshot Properties",
    )
    _require(
        snapshot
        == {
            "alertId": alert_id,
            "alertRule": fired_essentials["alertRule"],
            "targetResourceId": subject["containerAppResourceId"],
            "monitorCondition": "Fired",
        },
        "agent incident snapshot is not bound to the fired alert",
    )
    proposal = _mapping(
        by_event["AgentResponse"]["Properties"],
        "AgentResponse Properties",
    )
    _require(
        proposal == investigation_result["agentResponse"],
        "agent response does not accurately summarize the investigation",
    )
    tool = _mapping(
        by_event["AgentToolExecution"]["Properties"],
        "AgentToolExecution Properties",
    )
    _require(
        tool.get("phase") == "review" and tool.get("writeExecuted") is False,
        "agent tool executed a write before approval",
    )
    approval = _mapping(
        by_event["ApprovalDecision"]["Properties"],
        "ApprovalDecision Properties",
    )
    approval_time = _timestamp(
        by_event["ApprovalDecision"]["timestamp"],
        "ApprovalDecision timestamp",
    )
    _require(
        approval.get("decision") == "Approved"
        and approval.get("approvedByPrincipalId")
        == context["facilitatorPrincipalId"],
        "rollback was not approved by the facilitator",
    )
    snapshot_time = _timestamp(
        by_event["IncidentActivitySnapshot"]["timestamp"],
        "IncidentActivitySnapshot timestamp",
    )
    proposal_time = _timestamp(
        by_event["AgentResponse"]["timestamp"],
        "AgentResponse timestamp",
    )
    tool_time = _timestamp(
        by_event["AgentToolExecution"]["timestamp"],
        "AgentToolExecution timestamp",
    )
    command = _mapping(
        by_event["AgentAzCliExecution"]["Properties"],
        "AgentAzCliExecution Properties",
    )
    execution = _mapping(
        by_event["AgentExecution"]["Properties"],
        "AgentExecution Properties",
    )
    _require(
        command.get("operation") == "container-app-traffic-weight-update"
        and _same_resource(
            command.get("resourceId"),
            subject["containerAppResourceId"],
        ),
        "agent command differs from the frozen traffic rollback",
    )
    _require(
        execution.get("status") == "Succeeded"
        and execution.get("writeExecuted") is True,
        "agent execution did not record one successful write",
    )
    write_times = [
        _timestamp(
            by_event[name]["timestamp"],
            f"{name} timestamp",
        )
        for name in ("AgentAzCliExecution", "AgentExecution")
    ]
    _require(
        fired_at <= snapshot_time
        < investigation_result["firstObservedAt"]
        <= investigation_result["lastObservedAt"]
        < proposal_time
        <= tool_time
        < approval_time
        < write_times[0]
        <= write_times[1],
        "alert, review, approval, and execution chronology differs",
    )

    activity = _mapping(incident["activityLog"], "incident.activityLog")
    activity_request = _mapping(
        activity.get("request"),
        "incident.activityLog.request",
    )
    expected_activity_url = (
        f"{_subscription_scope(context['subscriptionId'])}"
        "/providers/Microsoft.Insights/eventtypes/management/values"
        "?api-version=2015-04-01&$filter="
        f"eventTimestamp%20ge%20'{incident['incidentStart']}'"
        "%20and%20"
        f"eventTimestamp%20le%20'{incident['incidentEnd']}'"
        "%20and%20"
        f"resourceUri%20eq%20'{subject['containerAppResourceId']}'"
    )
    _require(
        activity_request == {"method": "GET", "url": expected_activity_url},
        "activity-log evidence does not use the exact incident ARM query",
    )
    activity_response = _mapping(
        activity["response"],
        "incident.activityLog.response",
    )
    _require(
        activity_response.get("nextLink") is None,
        "activity-log evidence is paginated",
    )
    activity_values = _array(
        activity_response.get("value"),
        "incident.activityLog.response.value",
    )
    _require(
        len(activity_values) == 2,
        "activity log must contain the seed and approved rollback writes",
    )
    seed_activity: dict[str, Any] | None = None
    activity_entry: dict[str, Any] | None = None
    for index, raw_activity in enumerate(activity_values):
        entry = _mapping(
            raw_activity,
            f"incident.activityLog.response.value[{index}]",
        )
        authorization = _mapping(
            entry.get("authorization"),
            f"incident activity[{index}] authorization",
        )
        _require(
            _same_resource(
                entry.get("resourceId"),
                subject["containerAppResourceId"],
            )
            and _same_resource(
                authorization.get("scope"),
                subject["containerAppResourceId"],
            )
            and authorization.get("action")
            == "Microsoft.App/containerApps/write"
            and _mapping(
                entry.get("operationName"),
                f"incident activity[{index}] operationName",
            ).get("value")
            == "Microsoft.App/containerApps/write"
            and _mapping(
                entry.get("status"),
                f"incident activity[{index}] status",
            ).get("value")
            == "Succeeded",
            "activity log contains a write outside the exact Container App scope",
        )
        if entry.get("correlationId") == subject["correlationId"]:
            _require(
                activity_entry is None,
                "activity log repeats the approved rollback correlation",
            )
            activity_entry = entry
        else:
            _require(seed_activity is None, "activity log contains an extra write")
            seed_activity = entry
    _require(
        activity_entry is not None and seed_activity is not None,
        "activity log does not distinguish seed and rollback writes",
    )
    activity_time = _timestamp(
        activity_entry.get("eventTimestamp"),
        "approved rollback activity timestamp",
    )
    seed_activity_time = _timestamp(
        seed_activity.get("eventTimestamp"),
        "seed activity timestamp",
    )
    _require(
        seed_activity.get("caller") == context["facilitatorPrincipalId"]
        and start <= seed_activity_time <= bad_time < fired_at
        and activity_entry.get("caller") == context["userPrincipalId"]
        and activity_time > approval_time,
        "activity log seed or approved rollback identity differs",
    )

    before_app_weights, before_app_time, before_app_state = _container_app_state(
        incident["containerAppBeforeRollback"],
        "incident.containerAppBeforeRollback",
        subject["containerAppResourceId"],
    )
    after_app_weights, after_app_time, after_app_state = _container_app_state(
        incident["containerAppAfterRollback"],
        "incident.containerAppAfterRollback",
        subject["containerAppResourceId"],
    )
    _require(
        before_app_weights.get(healthy_revision) == 0
        and before_app_weights.get(bad_revision) == 100
        and after_app_weights.get(healthy_revision) == 100
        and after_app_weights.get(bad_revision) == 0,
        "Container App before/after traffic differs from the approved rollback",
    )
    _require(
        before_app_state == after_app_state,
        "approved Container App write changed state beyond traffic",
    )
    _require(
        tool_time <= before_app_time < approval_time < activity_time
        <= after_app_time,
        "Container App before/after snapshots do not bracket the approved write",
    )

    recovered_weights, recovered_time = _traffic_weights(
        incident["recoveredTraffic"],
        "incident.recoveredTraffic",
        subject["containerAppResourceId"],
    )
    _require(
        recovered_time >= after_app_time
        and recovered_weights.get(healthy_revision) == 100
        and recovered_weights.get(bad_revision) == 0
        and all(
            weight == 0
            for revision, weight in recovered_weights.items()
            if revision != healthy_revision
        ),
        "traffic did not recover to the exact healthy revision",
    )
    health_results = _array(incident["recoveryHealth"], "incident.recoveryHealth")
    health_by_url: dict[str, dict[str, Any]] = {}
    for index, raw_capture in enumerate(health_results):
        capture = _mapping(raw_capture, f"incident.recoveryHealth[{index}]")
        request = _mapping(
            capture.get("request"),
            f"incident.recoveryHealth[{index}].request",
        )
        url = _string(
            request.get("url"),
            f"incident.recoveryHealth[{index}].request.url",
        )
        _require(url not in health_by_url, "recovery health repeats a URL")
        _require(
            request
            == {
                "method": "GET",
                "url": url,
                "redirectsAllowed": False,
            },
            "recovery health request permits redirects or differs",
        )
        response = _mapping(
            capture.get("response"),
            f"incident.recoveryHealth[{index}].response",
        )
        status = _integer(
            response.get("http_code"),
            f"incident.recoveryHealth[{index}].response.http_code",
        )
        _require(
            status == 200
            and _integer(
                response.get("exitcode"),
                f"incident.recoveryHealth[{index}].response.exitcode",
            )
            == 0
            and _integer(
                response.get("num_redirects"),
                f"incident.recoveryHealth[{index}].response.num_redirects",
            )
            == 0
            and response.get("url_effective") == url,
            "recovery health curl evidence is not an exact non-redirected HTTP 200",
        )
        observed_at = _timestamp(
            capture.get("observedAt"),
            f"incident.recoveryHealth[{index}].observedAt",
        )
        _require(
            observed_at >= recovered_time,
            "recovery health request preceded traffic restoration",
        )
        health_by_url[url] = {
            "status": status,
            "observedAt": capture["observedAt"],
        }
    _require(
        set(health_by_url)
        == {
            handoff["application"]["healthUrl"],
            handoff["application"]["readinessUrl"],
        },
        "recovery did not test exact handoff health and readiness URLs",
    )
    latest_health = max(
        _timestamp(result["observedAt"], "recovery health observedAt")
        for result in health_by_url.values()
    )

    resolved = _mapping(
        incident["alertResolved"]["response"],
        "incident.alertResolved.response",
    )
    _require(
        _same_resource(resolved.get("id"), alert_id),
        "resolved alert differs from the fired alert",
    )
    _require(
        _mapping(
            incident["alertResolved"].get("request"),
            "incident.alertResolved.request",
        )
        == {
            "method": "GET",
            "url": f"{alert_id}?api-version=2019-05-05",
        },
        "resolved alert evidence does not use the exact ARM GET",
    )
    resolved_essentials = _mapping(
        _mapping(
            resolved.get("properties"),
            "incident.alertResolved.response.properties",
        ).get("essentials"),
        "incident.alertResolved.response.properties.essentials",
    )
    resolved_at = _timestamp(
        resolved_essentials.get("resolvedDateTime"),
        "incident.alertResolved resolvedDateTime",
    )
    _require(
        resolved_essentials.get("monitorCondition") == "Resolved"
        and resolved_at >= latest_health,
        "alert did not resolve after recovery",
    )
    resolved_targets = _array(
        resolved_essentials.get("targetResourceIds"),
        "incident.alertResolved targetResourceIds",
    )
    _require(
        len(resolved_targets) == 1
        and _same_resource(
            resolved_targets[0],
            subject["containerAppResourceId"],
        ),
        "resolved alert targets another resource",
    )

    assessment = _mapping(incident["assessment"], "incident.assessment")
    _require(
        assessment["performedByPrincipalId"] == context["participantPrincipalId"]
        and assessment["approvedByPrincipalId"]
        == context["facilitatorPrincipalId"]
        and assessment["participantApproved"] is False
        and assessment["autonomousExecution"] is False
        and assessment["secretChanged"] is False
        and assessment["imageChanged"] is False
        and assessment["resourceDeleted"] is False,
        "incident assessment violates participant or mutation boundaries",
    )
    _require(
        all(
            assessment.get(field) == value
            for field, value in investigation_result["assessment"].items()
        ),
        "incident assessment is not supported by the investigation evidence",
    )
    _require(
        resolved_at
        <= _timestamp(assessment["recordedAt"], "incident.assessment.recordedAt")
        <= end,
        "incident assessment chronology differs",
    )

    return {
        "start": incident["incidentStart"],
        "end": incident["incidentEnd"],
        "healthyRevision": healthy_revision,
        "badRevision": bad_revision,
        "imageDigest": expected_digest,
        "badDatabaseHost": bad_host,
        "alertId": alert_id,
        "alertFiredAt": fired_essentials["firedDateTime"],
        "alertResolvedAt": resolved_essentials["resolvedDateTime"],
        "failedRequests": failed_requests,
        "investigation": investigation_result["summary"],
        "audit": {
            "threadId": subject["threadId"],
            "traceId": subject["traceId"],
            "correlationId": subject["correlationId"],
            "eventNames": [row["name"] for row in audit_rows],
            "approvedAt": by_event["ApprovalDecision"]["timestamp"],
            "executedAt": by_event["AgentExecution"]["timestamp"],
        },
        "activity": {
            "operation": "Microsoft.App/containerApps/write",
            "scope": subject["containerAppResourceId"],
            "callerPrincipalId": context["userPrincipalId"],
            "observedAt": activity_entry["eventTimestamp"],
        },
        "traffic": {
            "badRevisionAt100At": seed["trafficBad"]["observedAt"],
            "healthyRevisionAt100At": incident["recoveredTraffic"]["observedAt"],
        },
        "health": [
            {
                "url": url,
                "status": health_by_url[url]["status"],
                "observedAt": health_by_url[url]["observedAt"],
            }
            for url in sorted(health_by_url)
        ],
        "assessment": {
            "performedByPrincipalId": assessment["performedByPrincipalId"],
            "affectedRevision": assessment["affectedRevision"],
            "rootCauseCode": assessment["rootCauseCode"],
            "rootCause": assessment["rootCause"],
            "supportingEvidence": assessment["supportingEvidence"],
            "evidenceReferences": assessment["evidenceReferences"],
            "alternativesConsidered": assessment["alternativesConsidered"],
            "recommendedAction": assessment["recommendedAction"],
            "preventionAction": assessment["preventionAction"],
            "participantApproved": False,
            "autonomousExecution": False,
        },
    }


def _protected_resources(target: dict[str, Any]) -> set[str]:
    """Return every upstream resource that SRE Agent cleanup must preserve."""
    network = _mapping(target["network"], "target.network")
    protected = {
        target["resourceGroup"]["resourceId"],
        network["virtualNetworkResourceId"],
        network["migrationSourceVirtualNetworkResourceId"],
        network["migrationSourceVmResourceId"],
        network["migrationSourceToTargetPeeringResourceId"],
        network["migrationTargetToSourcePeeringResourceId"],
        target["containerRegistry"]["resourceId"],
        target["workloadIdentity"]["resourceId"],
        target["containerAppsEnvironmentResourceId"],
        target["database"]["resourceId"],
        target["images"]["resourceId"],
        target["observability"]["applicationInsightsResourceId"],
        target["observability"]["logAnalyticsWorkspaceResourceId"],
        target["application"]["resourceId"],
    }
    protected.update(network["migrationPrivateDnsZoneLinkResourceIds"])
    return {value.rstrip("/").casefold() for value in protected}


def _validate_empty_rbac_inventory(
    capture: Any,
    name: str,
    principal_id: str,
    subscription_id: str,
    after: datetime,
) -> None:
    """Require an unpaginated empty post-cleanup RBAC inventory."""
    document = _mapping(capture, name)
    _require(
        _timestamp(document.get("observedAt"), f"{name}.observedAt") >= after,
        f"{name} was captured before role removal",
    )
    request = _mapping(document.get("request"), f"{name}.request")
    response = _mapping(document.get("response"), f"{name}.response")
    body = _mapping(request.get("body"), f"{name}.request.body")
    _require(
        request.get("method") == "POST"
        and request.get("url")
        == (
            "/providers/Microsoft.ResourceGraph/resources"
            f"?api-version={_RESOURCE_GRAPH_API_VERSION}"
        )
        and body
        == {
            "subscriptions": [subscription_id],
            "query": _rbac_query(principal_id),
            "options": {"resultFormat": "objectArray"},
        },
        f"{name} does not use the frozen RBAC inventory query",
    )
    _require(
        response.get("data") == []
        and response.get("count") == 0
        and response.get("totalRecords") == 0
        and response.get("resultTruncated") == "false"
        and response.get("facets") == []
        and "$skipToken" not in response,
        f"{name} still contains or truncates role assignments",
    )
    effective = _mapping(
        document.get("effectiveAccess"),
        f"{name}.effectiveAccess",
    )
    effective_request = _mapping(
        effective.get("request"),
        f"{name}.effectiveAccess.request",
    )
    _require(
        effective_request
        == {
            "command": (
                "az role assignment list --all --include-inherited "
                f"--assignee-object-id {principal_id} "
                f"--subscription {subscription_id} "
                "--fill-principal-name false "
                "--fill-role-definition-name false --output json"
            ),
            "assigneeObjectId": principal_id,
            "subscriptionId": subscription_id,
            "all": True,
            "includeInherited": True,
            "fillPrincipalName": False,
            "fillRoleDefinitionName": False,
        }
        and effective.get("response") == [],
        f"{name} still has inherited effective access",
    )


def _validate_not_found(
    capture: Any,
    name: str,
    deleted_at: datetime,
    resource_id: str,
    api_version: str,
) -> datetime:
    """Validate one exact post-delete ARM GET returning HTTP 404."""
    document = _mapping(capture, name)
    request = _mapping(document["request"], f"{name}.request")
    observed_at = _timestamp(document["observedAt"], f"{name}.observedAt")
    _require(
        request
        == {
            "method": "GET",
            "url": f"{resource_id}?api-version={api_version}",
        }
        and document["statusCode"] == 404,
        f"{name} is not the exact post-delete ARM 404",
    )
    _require(observed_at > deleted_at, f"{name} preceded deletion")
    return observed_at


def _validate_cleanup(
    cleanup: dict[str, Any],
    target: dict[str, Any],
    incident_end: datetime,
    context: dict[str, str],
) -> dict[str, Any]:
    """Validate authorized deletion, role cleanup, and cost verification."""
    authorization = _mapping(cleanup["authorization"], "cleanup.authorization")
    authorized_at = _timestamp(
        authorization["authorizedAt"],
        "cleanup.authorization.authorizedAt",
    )
    _require(
        authorization["authorized"] is True
        and authorization["scope"] == "sre-agent-only"
        and authorization["authorizedByPrincipalId"]
        == context["facilitatorPrincipalId"],
        "cleanup lacks exact facilitator authorization",
    )
    evidence_exported_at = _timestamp(
        cleanup["evidenceExportedAt"],
        "cleanup.evidenceExportedAt",
    )
    agent_deleted_at = _timestamp(
        cleanup["agentDeletedAt"],
        "cleanup.agentDeletedAt",
    )
    _require(
        incident_end < authorized_at <= evidence_exported_at < agent_deleted_at,
        "cleanup authorization/export/deletion chronology differs",
    )
    agent_verified_at = _validate_not_found(
        cleanup["agentVerification"],
        "cleanup.agentVerification",
        agent_deleted_at,
        context["agentResourceId"],
        _AGENT_API_VERSION,
    )
    roles_removed_at = _timestamp(
        cleanup["roleAssignmentsRemovedAt"],
        "cleanup.roleAssignmentsRemovedAt",
    )
    _require(
        roles_removed_at >= agent_verified_at,
        "cross-scope roles were removed before agent deletion was verified",
    )
    role_verification = _mapping(
        cleanup["roleAssignmentVerification"],
        "cleanup.roleAssignmentVerification",
    )
    _validate_empty_rbac_inventory(
        role_verification.get("userAssigned"),
        "cleanup.roleAssignmentVerification.userAssigned",
        context["userPrincipalId"],
        context["subscriptionId"],
        roles_removed_at,
    )
    _validate_empty_rbac_inventory(
        role_verification.get("systemAssigned"),
        "cleanup.roleAssignmentVerification.systemAssigned",
        context["systemPrincipalId"],
        context["subscriptionId"],
        roles_removed_at,
    )

    resource_group_deleted_at = _timestamp(
        cleanup["resourceGroupDeletedAt"],
        "cleanup.resourceGroupDeletedAt",
    )
    _require(
        resource_group_deleted_at > roles_removed_at,
        "agent resource group was deleted before cross-scope role cleanup",
    )
    resource_group_verified_at = _validate_not_found(
        cleanup["resourceGroupVerification"],
        "cleanup.resourceGroupVerification",
        resource_group_deleted_at,
        context["agentResourceGroupId"],
        "2024-11-01",
    )

    expected_protected = _protected_resources(target)
    actual_protected = {
        _string(value, "cleanup.protectedResources item").rstrip("/").casefold()
        for value in _array(
            cleanup["protectedResources"],
            "cleanup.protectedResources",
        )
    }
    _require(
        actual_protected == expected_protected,
        "cleanup protected-resource inventory differs from the target output",
    )
    _require(
        context["agentResourceGroupId"].casefold() not in actual_protected
        and context["agentResourceId"].casefold() not in actual_protected,
        "cleanup mixed SRE Agent resources into the protected workload set",
    )
    protected_verification = _array(
        cleanup["protectedResourceVerification"],
        "cleanup.protectedResourceVerification",
    )
    verified_resources: set[str] = set()
    latest_protected_verification = resource_group_verified_at
    for index, raw_verification in enumerate(protected_verification):
        verification = _mapping(
            raw_verification,
            f"cleanup.protectedResourceVerification[{index}]",
        )
        request = _mapping(
            verification.get("request"),
            f"cleanup.protectedResourceVerification[{index}].request",
        )
        url = _string(
            request.get("url"),
            f"cleanup.protectedResourceVerification[{index}].request.url",
        )
        resource_id, separator, api_version = url.partition("?api-version=")
        _require(
            request.get("method") == "GET"
            and separator
            and api_version
            and verification.get("statusCode") == 200,
            "protected-resource verification must be one exact ARM GET",
        )
        normalized_id = resource_id.rstrip("/").casefold()
        _require(
            normalized_id in expected_protected
            and normalized_id not in verified_resources,
            "protected-resource verification targets an unexpected resource",
        )
        observed_at = _timestamp(
            verification.get("observedAt"),
            f"cleanup.protectedResourceVerification[{index}].observedAt",
        )
        _require(
            observed_at > resource_group_verified_at,
            "protected resource was checked before agent-group deletion",
        )
        verified_resources.add(normalized_id)
        latest_protected_verification = max(
            latest_protected_verification,
            observed_at,
        )
    _require(
        verified_resources == expected_protected,
        "post-cleanup protected-resource verification is incomplete",
    )

    cost = _mapping(cleanup["costVerification"], "cleanup.costVerification")
    cost_request = _mapping(cost["request"], "cleanup.costVerification.request")
    queried_at = _timestamp(cost["queriedAt"], "cleanup.costVerification.queriedAt")
    data_through = _timestamp(
        cost["dataThrough"],
        "cleanup.costVerification.dataThrough",
    )
    subscription_scope = _subscription_scope(context["subscriptionId"])
    expected_query_url = (
        f"{subscription_scope}/providers/Microsoft.CostManagement/query"
        "?api-version=2023-03-01"
    )
    _require(
        cost_request.get("method") == "POST"
        and cost_request.get("url") == expected_query_url,
        "cost verification does not query the exact subscription",
    )
    cost_body = _mapping(
        cost_request.get("body"),
        "cleanup.costVerification.request.body",
    )
    _require(
        set(cost_body) == {"type", "timeframe", "timePeriod", "dataset"}
        and cost_body.get("type") == "Usage"
        and cost_body.get("timeframe") == "Custom",
        "Cost Management query definition differs",
    )
    time_period = _mapping(
        cost_body.get("timePeriod"),
        "cleanup.costVerification.request.body.timePeriod",
    )
    _require(
        set(time_period) == {"from", "to"},
        "Cost Management query time period differs",
    )
    timeframe_start = _timestamp(
        time_period.get("from"),
        "cleanup Cost Management timePeriod.from",
    )
    timeframe_end = _timestamp(
        time_period.get("to"),
        "cleanup Cost Management timePeriod.to",
    )
    expected_dataset = {
        "granularity": "Daily",
        "aggregation": {
            "agentUnits": {
                "name": "UsageQuantity",
                "function": "Sum",
            }
        },
        "grouping": [{"type": "Dimension", "name": "Meter"}],
        "filter": {
            "dimensions": {
                "name": "Meter",
                "operator": "In",
                "values": ["Azure SRE Agent"],
            }
        },
    }
    _require(
        cost_body.get("dataset") == expected_dataset,
        "Cost Management query dataset differs",
    )
    _require(
        timeframe_start < agent_deleted_at < timeframe_end <= queried_at,
        "cost query does not span the agent deletion",
    )
    _require(
        queried_at > latest_protected_verification
        and data_through >= timeframe_end
        and data_through <= queried_at
        and cost["costDataLagAcknowledged"] is True,
        "post-deletion cost verification is incomplete",
    )
    cost_response = _mapping(cost["response"], "cleanup.costVerification.response")
    response_id = _string(
        cost_response.get("id"),
        "cleanup.costVerification.response.id",
    ).strip("/").casefold()
    response_name = _string(
        cost_response.get("name"),
        "cleanup.costVerification.response.name",
    )
    expected_response_prefix = (
        f"{subscription_scope}/providers/Microsoft.CostManagement/query/"
    ).strip("/").casefold()
    _require(
        response_id.startswith(expected_response_prefix)
        and response_id.endswith(f"/{response_name.casefold()}")
        and str(cost_response.get("type", "")).casefold()
        == "microsoft.costmanagement/query",
        "Cost Management response identity differs",
    )
    cost_properties = _mapping(
        cost_response.get("properties"),
        "cleanup.costVerification.response.properties",
    )
    _require(
        "nextLink" in cost_properties
        and cost_properties.get("nextLink") is None,
        "Cost Management response is paginated",
    )
    raw_columns = _array(
        cost_properties.get("columns"),
        "cleanup.costVerification.response.properties.columns",
    )
    expected_column_types = {
        "UsageQuantity": "Number",
        "UsageDate": "Number",
        "Meter": "String",
    }
    column_indexes: dict[str, int] = {}
    for index, raw_column in enumerate(raw_columns):
        column = _mapping(raw_column, f"cost columns[{index}]")
        column_name = _string(
            column.get("name"),
            f"cost columns[{index}].name",
        )
        _require(
            column_name not in column_indexes,
            "Cost Management response repeats a column",
        )
        column_indexes[column_name] = index
        if column_name in expected_column_types:
            _require(
                column.get("type") == expected_column_types[column_name],
                f"Cost Management {column_name} column type differs",
            )
    _require(
        set(expected_column_types).issubset(column_indexes),
        "Cost Management response omits required columns",
    )
    rows = _array(cost_properties.get("rows"), "cost rows")
    _require(rows, "cost verification did not observe SRE Agent usage")
    usage_rows: list[tuple[date, float]] = []
    for index, raw_row in enumerate(rows):
        row = _array(raw_row, f"cost rows[{index}]")
        _require(
            len(row) == len(raw_columns),
            f"cost rows[{index}] shape differs",
        )
        usage_day = _usage_date(
            row[column_indexes["UsageDate"]],
            f"cost rows[{index}] UsageDate",
        )
        _require(
            timeframe_start.date() <= usage_day <= timeframe_end.date(),
            f"cost rows[{index}] falls outside the requested timeframe",
        )
        _require(
            row[column_indexes["Meter"]] == "Azure SRE Agent",
            f"cost rows[{index}] meter differs",
        )
        units = _number(
            row[column_indexes["UsageQuantity"]],
            f"cost rows[{index}] UsageQuantity",
        )
        _require(units >= 0, f"cost rows[{index}] UsageQuantity is negative")
        usage_rows.append((usage_day, units))
    _require(
        any(units >= 4 for _, units in usage_rows),
        "cost verification did not observe the four-AAU agent meter",
    )
    billing_after_deletion = any(
        usage_day > agent_deleted_at.date() and units > 0
        for usage_day, units in usage_rows
    )
    _require(
        cost["billingAfterDeletionObserved"] is billing_after_deletion,
        "billing-after-deletion flag differs from Cost Management rows",
    )
    _require(
        not billing_after_deletion,
        "cost verification observed billing after agent deletion",
    )
    completed_at = _timestamp(cleanup["completedAt"], "cleanup.completedAt")
    _require(completed_at >= queried_at, "cleanup completed before cost verification")

    return {
        "authorizedBy": authorization["authorizedBy"],
        "evidenceExportedAt": cleanup["evidenceExportedAt"],
        "agentDeletedAt": cleanup["agentDeletedAt"],
        "roleAssignmentsRemovedAt": cleanup["roleAssignmentsRemovedAt"],
        "resourceGroupDeletedAt": cleanup["resourceGroupDeletedAt"],
        "costQueriedAt": cost["queriedAt"],
        "costDataThrough": cost["dataThrough"],
        "protectedResourceCount": len(actual_protected),
        "completedAt": cleanup["completedAt"],
    }


def build_sre_agent_evidence(
    capture_path: Path,
    handoff_path: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Build the canonical SRE Agent report from immutable checked captures."""
    root = repository_root.resolve()
    contracts = _contracts_directory(root, root / "workshop/contracts")
    capture_resolved = resolve_repository_file(
        root,
        _relative_file(root, capture_path, "capture manifest"),
    )
    handoff_resolved = resolve_repository_file(
        root,
        _relative_file(root, handoff_path, "handoff"),
    )
    capture = load_json_object(capture_resolved)
    handoff = load_json_object(handoff_resolved)
    registry = load_json_object(contracts / "sre-agent.json")
    _validate_schema(contracts / "sre-agent.schema.json", registry)
    _validate_schema(
        contracts / "sre-agent-evidence-capture.schema.json",
        capture,
    )
    _validate_schema(
        contracts / "modernization-contract.schema.json",
        handoff,
    )
    documents, references = _load_artifacts(
        capture,
        capture_resolved,
        root,
        contracts,
    )
    target = documents["target-output"]
    cicd = documents["cicd-evidence"]
    observability = documents["observability-evidence"]
    foundation = documents["sre-agent-foundation"]
    response_plan = documents["sre-agent-response-plan"]
    incident = documents["sre-agent-incident"]
    cleanup = documents["sre-agent-cleanup"]
    handoff_sha256 = sha256_file(handoff_resolved)
    _validate_upstream(
        handoff,
        handoff_sha256,
        target,
        cicd,
        observability,
    )
    foundation_summary, context = _validate_foundation(
        foundation,
        handoff,
        target,
    )
    foundation_summary["responsePlan"] = _validate_response_plan(
        response_plan,
        registry,
        context,
        _timestamp(foundation["observedAt"], "foundation.observedAt"),
    )
    incident_summary = _validate_incident(
        incident,
        registry,
        handoff,
        _timestamp(foundation["observedAt"], "foundation.observedAt"),
        context,
    )
    cleanup_summary = _validate_cleanup(
        cleanup,
        target,
        _timestamp(incident["incidentEnd"], "incident.incidentEnd"),
        context,
    )
    report = {
        "schemaVersion": _REPORT_VERSION,
        "capturedAt": capture["capturedAt"],
        "subject": {
            "sliceId": handoff["sliceId"],
            "stack": handoff["source"]["stack"],
            "sourceCommit": handoff["source"]["commitSha"],
            "subscriptionId": context["subscriptionId"],
            "participantResourceGroupId": context["participantResourceGroupId"],
            "containerAppResourceId": handoff["application"]["resourceId"],
            "applicationInsightsResourceId": handoff["observability"][
                "applicationInsightsResourceId"
            ],
            "logAnalyticsWorkspaceResourceId": handoff["observability"][
                "logAnalyticsWorkspaceResourceId"
            ],
            "agentResourceGroupId": context["agentResourceGroupId"],
            "agentResourceId": context["agentResourceId"],
        },
        "provenance": {
            "captureManifest": {
                "kind": "sre-agent-capture-manifest",
                "path": _relative_file(
                    root,
                    capture_resolved,
                    "capture manifest",
                ),
                "sha256": sha256_file(capture_resolved),
            },
            "artifacts": [
                {
                    "kind": kind,
                    "path": references[kind]["path"],
                    "sha256": references[kind]["sha256"],
                }
                for kind in sorted(references)
            ],
        },
        "dependencies": {
            "handoff": {
                "schemaVersion": handoff["schemaVersion"],
                "sha256": handoff_sha256,
            },
            "targetOutput": {
                "schemaVersion": target["schemaVersion"],
                "sha256": references["target-output"]["sha256"],
            },
            "cicdEvidence": {
                "schemaVersion": cicd["schemaVersion"],
                "sha256": references["cicd-evidence"]["sha256"],
            },
            "observabilityEvidence": {
                "schemaVersion": observability["schemaVersion"],
                "sha256": references["observability-evidence"]["sha256"],
            },
        },
        "foundation": foundation_summary,
        "incident": incident_summary,
        "cleanup": cleanup_summary,
        "assertions": {
            "upstreamEvidenceBound": True,
            "agentAndConnectorsReady": True,
            "dualIdentityBound": True,
            "leastPrivilegeRolesExact": True,
            "monitoringContributorExceptionExact": True,
            "reviewModeEnforced": True,
            "quickstartPlanDisabled": True,
            "portalPreflightPassed": True,
            "handoffImageReused": True,
            "secretReferencesPreserved": True,
            "badRevisionFailureObserved": True,
            "investigationComplete": True,
            "facilitatorApprovedBeforeWrite": True,
            "participantDidNotApprove": True,
            "noAutonomousExecution": True,
            "onlyTrafficRollbackExecuted": True,
            "healthyRevisionRestored": True,
            "healthAndReadinessRecovered": True,
            "alertResolved": True,
            "auditCorrelationComplete": True,
            "agentDeleted": True,
            "crossScopeRolesRemoved": True,
            "agentResourceGroupDeleted": True,
            "handoffResourcesProtected": True,
            "postDeletionCostQueried": True,
        },
    }
    _validate_schema(contracts / "sre-agent-evidence.schema.json", report)
    return report


def render_sre_agent_evidence(
    capture_path: Path,
    handoff_path: Path,
    output_path: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Atomically write the canonical SRE Agent evidence report."""
    root = repository_root.resolve()
    report = build_sre_agent_evidence(capture_path, handoff_path, root)
    output_relative = _relative_file(root, output_path, "report output")
    destination = root / output_relative
    for parent in [destination.parent, *destination.parents]:
        if parent == root.parent:
            break
        if parent.is_symlink():
            raise ValueError("SRE Agent report output path contains a symlink")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "schemaVersion": _REPORT_VERSION,
        "report": output_relative,
        "sha256": sha256_file(destination),
    }


def validate_sre_agent_evidence(
    capture_path: Path,
    handoff_path: Path,
    report_path: Path,
    contracts_directory: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Validate upstream handoff evidence and independently reproduce the SRE Agent evidence."""
    root = repository_root.resolve()
    contracts = _contracts_directory(root, contracts_directory)
    capture_resolved = resolve_repository_file(
        root,
        _relative_file(root, capture_path, "capture manifest"),
    )
    handoff_resolved = resolve_repository_file(
        root,
        _relative_file(root, handoff_path, "handoff"),
    )
    report_resolved = resolve_repository_file(
        root,
        _relative_file(root, report_path, "SRE Agent report"),
    )
    validate_handoff(handoff_resolved, contracts, root)
    capture = load_json_object(capture_resolved)
    references = {
        reference["kind"]: reference
        for reference in _array(capture.get("artifacts"), "artifacts")
        if isinstance(reference, dict) and "kind" in reference
    }
    for kind, artifact_kind in (
        ("cicd", "cicd-evidence"),
        ("observability", "observability-evidence"),
    ):
        reference = _mapping(
            references.get(artifact_kind),
            f"capture {artifact_kind} reference",
        )
        evidence_path = resolve_repository_file(
            root,
            _string(reference.get("path"), f"{artifact_kind} path"),
        )
        validate_shared_challenge_evidence(
            kind,
            evidence_path,
            handoff_resolved,
            contracts,
            root,
        )
    expected = build_sre_agent_evidence(capture_resolved, handoff_resolved, root)
    actual = load_json_object(report_resolved)
    _validate_schema(contracts / "sre-agent-evidence.schema.json", actual)
    _require(actual == expected, "SRE Agent report differs from raw captures")
    return {
        "kind": "sre-agent",
        "schemaVersion": actual["schemaVersion"],
        "report": _relative_file(root, report_resolved, "SRE Agent report"),
        "sha256": sha256_file(report_resolved),
        "assertions": actual["assertions"],
    }
