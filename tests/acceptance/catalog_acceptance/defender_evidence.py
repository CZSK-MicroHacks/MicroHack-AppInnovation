"""Render deterministic Defender evidence from digest-bound Azure captures."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError

from catalog_acceptance.artifact_io import (
    load_digest_bound_json,
    load_json_object,
    resolve_repository_file,
    sha256_file,
)
from catalog_acceptance.handoff import validate_handoff
from catalog_acceptance.models.defender import (
    ArtifactReference,
    DefenderDecision,
    DefenderEvidenceCapture,
    DefenderImageAssessmentCapture,
    QueryArtifact,
)

_REPORT_VERSION = "1.1.0"
_LAB_PROFILE_PATH = "workshop/defender/lab-profile.json"
_REPORT_OUTPUT = "evidence/defender-report.json"
_REQUIRED_PLAN_NAMES = {
    "CloudPosture",
    "Containers",
    "SqlServers",
    "OpenSourceRelationalDatabases",
    "VirtualMachines",
}
_PUBLIC_SOURCES = {"*", "Internet", "0.0.0.0/0", "::/0", "Any"}
_MANAGEMENT_PORTS = {22, 3389}
_ACR_PULL_ROLE_ID = "7f951dda-4ed3-4680-a7ca-43fe172d538d"
_REGISTRY_VULNERABILITY_EXTENSION = (
    "ContainerRegistriesVulnerabilityAssessments"
)


def _validate_schema(schema_path: Path, value: dict[str, Any]) -> None:
    """Validate one document with a checked-in Draft 2020-12 schema."""
    schema = load_json_object(schema_path)
    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(value)


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    """Return one mapping or fail with its source field name."""
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _require_list(value: Any, name: str) -> list[Any]:
    """Return one list or fail with its source field name."""
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    return value


def _require_string(value: Any, name: str) -> str:
    """Return one non-empty string or fail with its source field name."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_bool(value: Any, name: str) -> bool:
    """Return one strict JSON boolean."""
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _format_datetime(value: datetime) -> str:
    """Render one timestamp canonically in UTC."""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_aware_datetime(value: Any, name: str) -> datetime:
    """Parse one offset-aware ISO-8601 timestamp."""
    text = _require_string(value, name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be ISO-8601") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed


def _same_resource_id(left: str, right: str) -> bool:
    """Compare Azure resource IDs case-insensitively without trailing slashes."""
    return left.rstrip("/").casefold() == right.rstrip("/").casefold()


def _resource_subscription_id(value: Any, name: str) -> str:
    """Return the subscription segment from one Azure resource ID."""
    resource_id = _require_string(value, name)
    parts = resource_id.strip("/").split("/")
    if (
        len(parts) < 2
        or parts[0].casefold() != "subscriptions"
        or not parts[1]
    ):
        raise ValueError(f"{name} must be a subscription-scoped resource ID")
    return parts[1]


def _normalized_pricing_extensions(
    value: Any,
    name: str,
) -> list[dict[str, Any]]:
    """Normalize the mutable extension settings used for exact restoration."""
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(_require_list(value, name)):
        extension = _require_mapping(item, f"{name}[{index}]")
        additional_properties = extension.get(
            "additionalExtensionProperties",
            {},
        )
        if not isinstance(additional_properties, dict):
            raise ValueError(
                f"{name}[{index}].additionalExtensionProperties "
                "must be an object"
            )
        normalized.append(
            {
                "name": _require_string(
                    extension.get("name"),
                    f"{name}[{index}].name",
                ),
                "isEnabled": _require_string(
                    extension.get("isEnabled"),
                    f"{name}[{index}].isEnabled",
                ),
                "additionalExtensionProperties": additional_properties,
            }
        )
    return sorted(
        normalized,
        key=lambda extension: json.dumps(
            extension,
            sort_keys=True,
            separators=(",", ":"),
        ),
    )


def _relative_file(root: Path, path: Path, name: str) -> str:
    """Return one repository-relative path or reject an external file."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise ValueError(f"{name} must stay inside the repository") from error


def _validate_contracts_directory(root: Path, path: Path) -> Path:
    """Require the repository's exact checked-in workshop contract directory."""
    expected = root / "workshop/contracts"
    declared = root
    for part in Path("workshop/contracts").parts:
        declared /= part
        if declared.is_symlink():
            raise ValueError("workshop contracts directory cannot contain a symlink")
    if (
        path.absolute() != expected.absolute()
        or path.resolve() != expected.resolve()
        or not expected.is_dir()
    ):
        raise ValueError(
            "contracts directory must be the repository workshop/contracts tree"
        )
    return expected


def _contract_file(root: Path, contracts: Path, name: str) -> Path:
    """Resolve one non-symlinked contract file from the active repository."""
    relative = (contracts.relative_to(root) / name).as_posix()
    return resolve_repository_file(root, relative)


def _load_reference(
    root: Path,
    reference: ArtifactReference | QueryArtifact,
) -> dict[str, Any]:
    """Load one digest-bound capture reference."""
    return load_digest_bound_json(root, reference.file, reference.sha256)


def _validate_identity(
    root: Path,
    contracts: Path,
    capture: DefenderEvidenceCapture,
    capture_path: Path,
    handoff_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Validate the handoff, target output, lab profile, and cleanup identity."""
    handoff_relative = _relative_file(root, handoff_path, "handoff")
    capture_relative = _relative_file(root, capture_path, "capture")
    if handoff_relative != capture.identity.handoff.file:
        raise ValueError("capture handoff file differs from the supplied handoff")
    if capture_relative in {
        capture.identity.handoff.file,
        capture.identity.target_output.file,
        capture.identity.lab_profile.file,
        capture.identity.cleanup_manifest.file,
    }:
        raise ValueError("capture manifest cannot also serve as an evidence input")
    handoff = _load_reference(root, capture.identity.handoff)
    supplied_handoff = load_json_object(handoff_path)
    if handoff != supplied_handoff:
        raise ValueError("digest-bound handoff differs from the supplied handoff")
    _validate_schema(
        _contract_file(root, contracts, "modernization-contract.schema.json"),
        handoff,
    )

    target_output = _load_reference(root, capture.identity.target_output)
    if handoff["deployment"]["targetOutput"] != capture.identity.target_output.file:
        raise ValueError("target output path differs from the handoff declaration")
    _validate_schema(
        _contract_file(root, contracts, "azure-target-output.schema.json"),
        target_output,
    )
    checks = (
        (
            target_output.get("deploymentStage") == "application",
            "target output must be the application stage",
        ),
        (
            target_output.get("sourceCommit") == handoff["source"]["commitSha"],
            "target output source commit differs from the handoff",
        ),
        (
            target_output.get("stack") == handoff["source"]["stack"],
            "target output stack differs from the handoff",
        ),
        (
            _same_resource_id(
                target_output["application"]["resourceId"],
                handoff["application"]["resourceId"],
            ),
            "target output Container App differs from the handoff",
        ),
        (
            _same_resource_id(
                target_output["containerRegistry"]["resourceId"],
                handoff["containerImage"]["registryResourceId"],
            ),
            "target output registry differs from the handoff",
        ),
        (
            _same_resource_id(
                target_output["database"]["resourceId"],
                handoff["database"]["resourceId"],
            ),
            "target output database differs from the handoff",
        ),
        (
            target_output["containerImage"]["digest"]
            == handoff["containerImage"]["digest"],
            "target output image digest differs from the handoff",
        ),
    )
    failures = [message for passed, message in checks if not passed]
    if failures:
        raise ValueError("; ".join(failures))

    if capture.identity.lab_profile.file != _LAB_PROFILE_PATH:
        raise ValueError(f"lab profile must be {_LAB_PROFILE_PATH}")
    profile = _load_reference(root, capture.identity.lab_profile)
    _validate_schema(
        _contract_file(root, contracts, "defender-lab-profile.schema.json"),
        profile,
    )
    expected_profile = load_json_object(root / _LAB_PROFILE_PATH)
    if profile != expected_profile:
        raise ValueError("captured lab profile differs from the frozen profile")
    if (
        profile.get("schemaVersion") != "1.0.0"
        or profile.get("activationPolicy") != "do-not-weaken-secure-baseline"
        or set(
            profile.get("asynchronousFindings", {}).get(
                "requiredToQuery",
                [],
            )
        )
        != {
            "image-vulnerability-assessment",
            "recommendations",
            "secure-score",
            "mcsb-controls",
            "attack-paths",
        }
        or profile.get("asynchronousFindings", {}).get("requiredToBeNonEmpty")
        != []
        or profile.get("asynchronousFindings", {}).get("attackPaths")
        != "query-required-results-optional"
        or profile.get("prewarmedSnapshot")
        != {
            "requiredSignals": [
                "image-vulnerability-assessment",
                "recommendations",
                "secure-score",
                "mcsb-controls",
            ],
            "recommendationResourceCoverage": [
                "dotnet-vm",
                "java-vm",
                "container-app",
                "container-registry",
                "database",
            ],
            "minimumUnhealthyRecommendations": 1,
        }
    ):
        raise ValueError("lab profile does not implement the frozen safety boundary")

    cleanup = _load_reference(root, capture.identity.cleanup_manifest)
    _validate_schema(
        _contract_file(root, contracts, "defender-cleanup.schema.json"),
        cleanup,
    )
    return handoff, target_output, profile, cleanup


def _parse_pricing_envelope(
    raw: dict[str, Any],
    subscription_id: str,
    root: Path,
    contracts: Path,
) -> tuple[dict[str, Any], datetime]:
    """Validate one subscription-bound Defender pricing query envelope."""
    _validate_schema(
        _contract_file(root, contracts, "defender-pricing-envelope.schema.json"),
        raw,
    )
    request = _require_mapping(raw.get("request"), "pricings.request")
    expected_scope = f"/subscriptions/{subscription_id}"
    if (
        not _same_resource_id(
            _require_string(
                request.get("scopeResourceId"),
                "pricings.request.scopeResourceId",
            ),
            expected_scope,
        )
        or request.get("apiVersion") != "2024-01-01"
        or request.get("operation") != "subscription-defender-pricings"
        or request.get("method") != "GET"
    ):
        raise ValueError("Defender pricing query targets another subscription")
    queried_at = _parse_aware_datetime(
        request.get("queriedAt"),
        "pricings.request.queriedAt",
    )
    return _require_mapping(raw.get("response"), "pricings.response"), queried_at


def _index_pricings(
    response: dict[str, Any],
    subscription_id: str,
    name: str,
) -> dict[str, dict[str, Any]]:
    """Index required pricing records after binding every ARM resource ID."""
    values = _require_list(response.get("value"), f"{name}.value")
    by_name: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(values):
        item = _require_mapping(value, f"{name}.value[{index}]")
        pricing_name = _require_string(
            item.get("name"),
            f"{name}.value[{index}].name",
        )
        if pricing_name in by_name:
            raise ValueError(f"duplicate pricing response for {pricing_name}")
        if pricing_name in _REQUIRED_PLAN_NAMES:
            expected_id = (
                f"/subscriptions/{subscription_id}/providers/"
                f"Microsoft.Security/pricings/{pricing_name}"
            )
            if not _same_resource_id(
                _require_string(item.get("id"), f"{pricing_name}.id"),
                expected_id,
            ):
                raise ValueError(
                    f"{pricing_name} pricing resource targets another subscription"
                )
        by_name[pricing_name] = item
    missing = _REQUIRED_PLAN_NAMES - set(by_name)
    if missing:
        raise ValueError(
            f"required Defender pricing is absent: {sorted(missing)[0]}"
        )
    return by_name


def _parse_pricings(
    raw: dict[str, Any],
    registry: dict[str, Any],
    subscription_id: str,
    root: Path,
    contracts: Path,
) -> tuple[list[dict[str, Any]], datetime]:
    """Validate enabled pricing plans and normalize their frozen contract."""
    response, queried_at = _parse_pricing_envelope(
        raw,
        subscription_id,
        root,
        contracts,
    )
    by_name = _index_pricings(response, subscription_id, "pricings.response")

    expected_plans = registry["foundation"]["requiredPricings"]
    expected_names = {plan["name"] for plan in expected_plans}
    if expected_names != _REQUIRED_PLAN_NAMES:
        raise ValueError("Defender registry required pricing names changed")
    normalized: list[dict[str, Any]] = []
    for expected in expected_plans:
        name = expected["name"]
        if name not in by_name:
            raise ValueError(f"required Defender pricing is absent: {name}")
        item = by_name[name]
        properties = _require_mapping(item.get("properties"), f"{name}.properties")
        if properties.get("pricingTier") != expected["pricingTier"]:
            raise ValueError(f"{name} pricing tier must be Standard")
        if expected.get("subPlan") is not None and (
            properties.get("subPlan") != expected["subPlan"]
        ):
            raise ValueError(f"{name} pricing subPlan must be {expected['subPlan']}")
        if expected.get("enforce") is not None and (
            properties.get("enforce") != expected["enforce"]
        ):
            raise ValueError(f"{name} pricing enforce must be {expected['enforce']}")
        extensions = _require_list(properties.get("extensions", []), f"{name}.extensions")
        for required_extension in expected["extensions"]:
            matches = [
                extension
                for extension in extensions
                if isinstance(extension, dict)
                and extension.get("name") == required_extension["name"]
                and extension.get("isEnabled") == required_extension["isEnabled"]
            ]
            if len(matches) != 1:
                raise ValueError(
                    f"{name} must enable {required_extension['name']} exactly once"
                )
        registry_vulnerability_extensions = [
            extension
            for extension in extensions
            if isinstance(extension, dict)
            and extension.get("name") == _REGISTRY_VULNERABILITY_EXTENSION
        ]
        if name == "CloudPosture":
            if (
                len(registry_vulnerability_extensions) != 1
                or registry_vulnerability_extensions[0].get("isEnabled") != "True"
            ):
                raise ValueError(
                    "CloudPosture must exclusively configure registry "
                    "vulnerability assessment"
                )
        elif registry_vulnerability_extensions:
            raise ValueError(
                "registry vulnerability assessment must be configured only "
                "under CloudPosture"
            )
        normalized.append(expected)
    return normalized, queried_at


def _parse_manual_preflight(
    raw: dict[str, Any],
    subscription_id: str,
) -> dict[str, Any]:
    """Validate the facilitator-owned Serverless Containers preflight."""
    if (
        raw.get("subscriptionId") != subscription_id
        or raw.get("controlId") != "serverless-containers"
        or raw.get("enabled") is not True
        or raw.get("operatorRole") != "Owner"
        or raw.get("source") != "azure-portal-owner-preflight"
    ):
        raise ValueError("Serverless Containers Owner preflight is not satisfied")
    parsed = _parse_aware_datetime(
        raw.get("observedAt"),
        "manualPreflight.observedAt",
    )
    return {
        "enabled": True,
        "observedAt": _format_datetime(parsed),
        "operatorRole": "Owner",
        "source": "azure-portal-owner-preflight",
    }


def _parse_budget(
    raw: dict[str, Any],
    reference: QueryArtifact,
    registry: dict[str, Any],
    subscription_id: str,
    root: Path,
    contracts: Path,
) -> dict[str, Any]:
    """Validate an active subscription budget with an early alert target."""
    _validate_schema(
        _contract_file(root, contracts, "defender-budget-envelope.schema.json"),
        raw,
    )
    budget_contract = registry["foundation"]["budget"]
    request = _require_mapping(raw.get("request"), "budget.request")
    expected_scope = f"/subscriptions/{subscription_id}"
    request_queried_at = _parse_aware_datetime(
        request.get("queriedAt"),
        "budget.request.queriedAt",
    )
    if (
        request.get("method") != "GET"
        or request.get("operation") != "subscription-cost-budget"
        or not _same_resource_id(
            _require_string(
                request.get("scopeResourceId"),
                "budget.request.scopeResourceId",
            ),
            expected_scope,
        )
        or request.get("apiVersion") != budget_contract["apiVersion"]
        or request.get("apiVersion") != reference.api_version
        or not _same_resource_id(
            reference.scope_resource_id,
            expected_scope,
        )
        or request_queried_at != reference.queried_at
    ):
        raise ValueError("budget query differs from the frozen subscription contract")

    response = _require_mapping(raw.get("response"), "budget.response")
    budget_id = _require_string(response.get("id"), "budget.response.id")
    expected_prefix = (
        f"{expected_scope}/providers/Microsoft.Consumption/budgets/"
    )
    if not budget_id.casefold().startswith(expected_prefix.casefold()):
        raise ValueError("budget resource differs from the workshop subscription")
    properties = _require_mapping(
        response.get("properties"),
        "budget.response.properties",
    )
    if (
        properties.get("category") != budget_contract["category"]
        or properties.get("timeGrain") != budget_contract["timeGrain"]
    ):
        raise ValueError("budget category or time grain differs from the contract")
    period = _require_mapping(
        properties.get("timePeriod"),
        "budget.response.properties.timePeriod",
    )
    starts_at = _parse_aware_datetime(
        period.get("startDate"),
        "budget.response.properties.timePeriod.startDate",
    )
    ends_at = _parse_aware_datetime(
        period.get("endDate"),
        "budget.response.properties.timePeriod.endDate",
    )
    if not starts_at <= request_queried_at <= ends_at:
        raise ValueError("budget is not active when its evidence is captured")

    notifications = _require_mapping(
        properties.get("notifications"),
        "budget.response.properties.notifications",
    )
    qualifying_thresholds: list[float] = []
    for notification_name, notification_value in notifications.items():
        notification = _require_mapping(
            notification_value,
            f"budget notification {notification_name}",
        )
        threshold = notification.get("threshold")
        contacts = [
            *_require_list(
                notification.get("contactEmails"),
                f"budget notification {notification_name}.contactEmails",
            ),
            *_require_list(
                notification.get("contactGroups"),
                f"budget notification {notification_name}.contactGroups",
            ),
            *_require_list(
                notification.get("contactRoles"),
                f"budget notification {notification_name}.contactRoles",
            ),
        ]
        if (
            notification.get("enabled") is True
            and isinstance(threshold, (int, float))
            and not isinstance(threshold, bool)
            and threshold
            <= budget_contract["maximumNotificationThreshold"]
            and contacts
        ):
            qualifying_thresholds.append(float(threshold))
    if not qualifying_thresholds:
        raise ValueError(
            "budget requires an enabled notification at or below 80 percent "
            "with a notification target"
        )
    return {
        "resourceId": budget_id,
        "name": _require_string(response.get("name"), "budget.response.name"),
        "amount": properties["amount"],
        "category": budget_contract["category"],
        "timeGrain": budget_contract["timeGrain"],
        "queriedAt": _format_datetime(request_queried_at),
        "notificationThresholds": sorted(qualifying_thresholds),
    }


def _resource_properties(
    raw: dict[str, Any],
    expected_id: str,
    expected_type: str,
    name: str,
) -> dict[str, Any]:
    """Validate one raw ARM resource identity and return its properties."""
    resource_id = _require_string(raw.get("id"), f"{name}.id")
    resource_type = _require_string(raw.get("type"), f"{name}.type")
    if not _same_resource_id(resource_id, expected_id):
        raise ValueError(f"{name} targets a resource other than the handoff")
    if resource_type.casefold() != expected_type.casefold():
        raise ValueError(f"{name} resource type must be {expected_type}")
    return _require_mapping(raw.get("properties"), f"{name}.properties")


def _parse_registry_control(
    before: dict[str, Any],
    after: dict[str, Any],
    role_assignments: dict[str, Any],
    handoff: dict[str, Any],
    target_output: dict[str, Any],
    container_app_after: dict[str, Any],
) -> dict[str, Any]:
    """Validate ACR admin disablement and managed-identity image pulls."""
    resource_id = handoff["containerImage"]["registryResourceId"]
    before_properties = _resource_properties(
        before,
        resource_id,
        "Microsoft.ContainerRegistry/registries",
        "containerRegistry.before",
    )
    after_properties = _resource_properties(
        after,
        resource_id,
        "Microsoft.ContainerRegistry/registries",
        "containerRegistry.after",
    )
    before_admin = _require_bool(
        before_properties.get("adminUserEnabled"),
        "containerRegistry.before.adminUserEnabled",
    )
    after_admin = _require_bool(
        after_properties.get("adminUserEnabled"),
        "containerRegistry.after.adminUserEnabled",
    )
    if after_admin:
        raise ValueError("ACR admin authentication must be disabled")
    if (
        after_properties.get("loginServer") != handoff["containerImage"]["registry"]
        or after_properties.get("provisioningState") != "Succeeded"
    ):
        raise ValueError("ACR after-state is not the healthy handoff registry")

    app_properties = _resource_properties(
        container_app_after,
        handoff["application"]["resourceId"],
        "Microsoft.App/containerApps",
        "containerApp.after",
    )
    identity_id = target_output["workloadIdentity"]["resourceId"]
    identities = _require_mapping(
        container_app_after.get("identity"),
        "containerApp.after.identity",
    )
    assigned = _require_mapping(
        identities.get("userAssignedIdentities"),
        "containerApp.after.identity.userAssignedIdentities",
    )
    if not any(_same_resource_id(value, identity_id) for value in assigned):
        raise ValueError("Container App does not include the handoff workload identity")
    configuration = _require_mapping(
        app_properties.get("configuration"),
        "containerApp.after.configuration",
    )
    registries = _require_list(
        configuration.get("registries"),
        "containerApp.after.configuration.registries",
    )
    registry_matches = [
        item
        for item in registries
        if isinstance(item, dict)
        and isinstance(item.get("server"), str)
        and item["server"].casefold()
        == handoff["containerImage"]["registry"].casefold()
    ]
    if len(registry_matches) != 1:
        raise ValueError(
            "Container App must have exactly one entry for the handoff registry"
        )
    registry_entry = registry_matches[0]
    if (
        not isinstance(registry_entry.get("identity"), str)
        or not _same_resource_id(registry_entry["identity"], identity_id)
        or "passwordSecretRef" in registry_entry
        or "username" in registry_entry
    ):
        raise ValueError("Container App registry pull must use only the handoff identity")

    template = _require_mapping(
        app_properties.get("template"),
        "containerApp.after.template",
    )
    containers = _require_list(
        template.get("containers"),
        "containerApp.after.template.containers",
    )
    expected_image = (
        f"{handoff['containerImage']['registry']}/"
        f"{handoff['containerImage']['repository']}@"
        f"{handoff['containerImage']['digest']}"
    )
    matching_images = [
        item
        for item in containers
        if isinstance(item, dict) and item.get("image") == expected_image
    ]
    if len(matching_images) != 1:
        raise ValueError("Container App image must use the exact handoff digest")
    assignments = _require_list(
        role_assignments.get("value"),
        "containerRegistryRoleAssignments.value",
    )
    principal_id = target_output["workloadIdentity"]["principalId"]
    expected_role_definition_id = (
        f"/subscriptions/{resource_id.split('/')[2]}/providers/"
        f"Microsoft.Authorization/roleDefinitions/{_ACR_PULL_ROLE_ID}"
    )
    if len(assignments) != 1:
        raise ValueError(
            "registry identity must have exactly one captured ACR role assignment"
        )
    assignment = _require_mapping(
        assignments[0],
        "containerRegistryRoleAssignments.value[0]",
    )
    assignment_id = _require_string(
        assignment.get("id"),
        "containerRegistryRoleAssignments.value[0].id",
    )
    assignment_properties = _require_mapping(
        assignment.get("properties"),
        "containerRegistryRoleAssignments.value[0].properties",
    )
    expected_assignment_prefix = (
        f"{resource_id}/providers/Microsoft.Authorization/roleAssignments/"
    )
    if not assignment_id.casefold().startswith(expected_assignment_prefix.casefold()):
        raise ValueError("AcrPull role assignment is not scoped to the handoff registry")
    if (
        assignment.get("type") != "Microsoft.Authorization/roleAssignments"
        or assignment_properties.get("principalId", "").casefold()
        != principal_id.casefold()
        or not _same_resource_id(
            _require_string(
                assignment_properties.get("roleDefinitionId"),
                "containerRegistryRoleAssignments.roleDefinitionId",
            ),
            expected_role_definition_id,
        )
    ):
        raise ValueError(
            "registry identity must have only AcrPull at the handoff registry"
        )
    return {
        "resourceId": resource_id,
        "disposition": "remediated" if before_admin else "already-compliant",
        "beforeAdminUserEnabled": before_admin,
        "afterAdminUserEnabled": False,
        "managedIdentityResourceId": identity_id,
        "principalId": principal_id,
        "roleAssignmentId": assignment_id,
        "roleDefinitionId": expected_role_definition_id,
        "imageReference": expected_image,
    }


def _validate_decision(
    decision: DefenderDecision,
    expected_disposition: str,
    control_name: str,
) -> None:
    """Require the capture decision to match the observed resource transition."""
    if decision.disposition != expected_disposition:
        raise ValueError(
            f"{control_name} disposition must be {expected_disposition}, "
            f"not {decision.disposition}"
        )


def _decision_result(
    resource_id: str,
    decision: DefenderDecision,
    before_state: str,
    after_state: str,
) -> dict[str, Any]:
    """Render one validated control decision."""
    return {
        "resourceId": resource_id,
        "disposition": decision.disposition,
        "beforeState": before_state,
        "afterState": after_state,
        "justification": decision.justification,
        "compensatingControls": decision.compensating_controls,
    }


def _parse_container_app_control(
    before: dict[str, Any],
    after: dict[str, Any],
    handoff: dict[str, Any],
    decision: DefenderDecision,
) -> dict[str, Any]:
    """Validate Container App ingress posture and the chosen disposition."""
    resource_id = handoff["application"]["resourceId"]
    before_properties = _resource_properties(
        before,
        resource_id,
        "Microsoft.App/containerApps",
        "containerApp.before",
    )
    after_properties = _resource_properties(
        after,
        resource_id,
        "Microsoft.App/containerApps",
        "containerApp.after",
    )
    if (
        after_properties.get("provisioningState") != "Succeeded"
        or after_properties.get("latestReadyRevisionName")
        != handoff["application"]["revisionName"]
    ):
        raise ValueError("Container App after-state is not the handoff revision")
    before_ingress = _require_mapping(
        _require_mapping(
            before_properties.get("configuration"),
            "containerApp.before.configuration",
        ).get("ingress"),
        "containerApp.before.configuration.ingress",
    )
    after_ingress = _require_mapping(
        _require_mapping(
            after_properties.get("configuration"),
            "containerApp.after.configuration",
        ).get("ingress"),
        "containerApp.after.configuration.ingress",
    )
    before_external = _require_bool(
        before_ingress.get("external"),
        "containerApp.before.ingress.external",
    )
    after_external = _require_bool(
        after_ingress.get("external"),
        "containerApp.after.ingress.external",
    )
    before_insecure = _require_bool(
        before_ingress.get("allowInsecure"),
        "containerApp.before.ingress.allowInsecure",
    )
    after_insecure = _require_bool(
        after_ingress.get("allowInsecure"),
        "containerApp.after.ingress.allowInsecure",
    )
    if after_insecure:
        raise ValueError("Container App after-state must reject insecure HTTP")
    if after_external:
        expected = "justified"
    elif before_external:
        expected = "remediated"
    else:
        expected = "already-compliant"
    _validate_decision(decision, expected, "containerAppIngress")

    def state(external: bool, insecure: bool) -> str:
        if not external:
            return "internal-only"
        return "external-insecure-http" if insecure else "external-https"

    return _decision_result(
        resource_id,
        decision,
        state(before_external, before_insecure),
        state(after_external, after_insecure),
    )


def _database_server_id(handoff: dict[str, Any]) -> str:
    """Return the server-level database resource ID for either frozen family."""
    resource_id = handoff["database"]["resourceId"].rstrip("/")
    family = handoff["database"]["family"]
    marker = "/databases/"
    if marker.casefold() not in resource_id.casefold():
        raise ValueError("handoff database resource ID is not a database child")
    server_id = resource_id[: resource_id.casefold().rfind(marker.casefold())]
    expected_provider = (
        "/providers/Microsoft.Sql/servers/"
        if family == "azure-sql"
        else "/providers/Microsoft.DBforPostgreSQL/flexibleServers/"
    )
    if expected_provider.casefold() not in server_id.casefold():
        raise ValueError("handoff database family and resource ID disagree")
    return server_id


def _parse_database_control(
    before: dict[str, Any],
    after: dict[str, Any],
    handoff: dict[str, Any],
    decision: DefenderDecision,
) -> dict[str, Any]:
    """Validate database server public-network posture."""
    resource_id = _database_server_id(handoff)
    resource_type = (
        "Microsoft.Sql/servers"
        if handoff["database"]["family"] == "azure-sql"
        else "Microsoft.DBforPostgreSQL/flexibleServers"
    )
    before_properties = _resource_properties(
        before,
        resource_id,
        resource_type,
        "database.before",
    )
    after_properties = _resource_properties(
        after,
        resource_id,
        resource_type,
        "database.after",
    )
    before_public = before_properties.get("publicNetworkAccess")
    after_public = after_properties.get("publicNetworkAccess")
    if before_public not in {"Enabled", "Disabled"}:
        raise ValueError("database.before.publicNetworkAccess is invalid")
    if after_public not in {"Enabled", "Disabled"}:
        raise ValueError("database.after.publicNetworkAccess is invalid")
    if after_public == "Disabled":
        expected = "remediated" if before_public == "Enabled" else "already-compliant"
    else:
        expected = "documented-exception"
    _validate_decision(decision, expected, "databaseNetwork")
    return _decision_result(
        resource_id,
        decision,
        f"public-network-{before_public.casefold()}",
        f"public-network-{after_public.casefold()}",
    )


def _management_ports_in_expression(value: Any) -> set[int]:
    """Return management ports contained in one NSG port expression."""
    if not isinstance(value, str):
        return set()
    if value == "*":
        return set(_MANAGEMENT_PORTS)
    if value.isdigit():
        port = int(value)
        return {port} if port in _MANAGEMENT_PORTS else set()
    if "-" in value:
        start_text, end_text = value.split("-", 1)
        if start_text.isdigit() and end_text.isdigit():
            start = int(start_text)
            end = int(end_text)
            return {
                port for port in _MANAGEMENT_PORTS if start <= port <= end
            }
    return set()


def _validate_vm_network_binding(
    raw: dict[str, Any],
    vm_properties: dict[str, Any],
    name: str,
) -> None:
    """Bind every effective-NSG response to a NIC attached to the selected VM."""
    network_profile = _require_mapping(
        vm_properties.get("networkProfile"),
        f"{name}.vm.properties.networkProfile",
    )
    declared_interfaces = _require_list(
        network_profile.get("networkInterfaces"),
        f"{name}.vm.properties.networkProfile.networkInterfaces",
    )
    declared_ids = {
        _require_string(
            _require_mapping(item, f"{name}.vm.networkInterface").get("id"),
            f"{name}.vm.networkInterface.id",
        ).casefold()
        for item in declared_interfaces
    }
    if not declared_ids:
        raise ValueError(f"{name} must declare at least one attached network interface")
    captures = _require_list(raw.get("networkInterfaces"), f"{name}.networkInterfaces")
    captured_ids: set[str] = set()
    for index, capture_value in enumerate(captures):
        capture_item = _require_mapping(
            capture_value,
            f"{name}.networkInterfaces[{index}]",
        )
        nic = _require_mapping(
            capture_item.get("resource"),
            f"{name}.networkInterfaces[{index}].resource",
        )
        nic_id = _require_string(
            nic.get("id"),
            f"{name}.networkInterfaces[{index}].resource.id",
        )
        if nic.get("type") != "Microsoft.Network/networkInterfaces":
            raise ValueError(f"{name} contains a non-NIC network resource")
        captured_ids.add(nic_id.casefold())
        nic_properties = _require_mapping(
            nic.get("properties"),
            f"{name}.networkInterfaces[{index}].resource.properties",
        )
        subnet_ids: set[str] = set()
        ip_configurations = _require_list(
            nic_properties.get("ipConfigurations"),
            f"{name}.networkInterfaces[{index}].resource.ipConfigurations",
        )
        for ip_configuration in ip_configurations:
            ip_properties = _require_mapping(
                _require_mapping(
                    ip_configuration,
                    f"{name}.networkInterfaces[{index}].ipConfiguration",
                ).get("properties"),
                f"{name}.networkInterfaces[{index}].ipConfiguration.properties",
            )
            subnet = _require_mapping(
                ip_properties.get("subnet"),
                f"{name}.networkInterfaces[{index}].ipConfiguration.subnet",
            )
            subnet_ids.add(
                _require_string(
                    subnet.get("id"),
                    f"{name}.networkInterfaces[{index}].subnet.id",
                ).casefold()
            )
        allowed_associations = {nic_id.casefold(), *subnet_ids}
        effective = _require_mapping(
            capture_item.get("effectiveNetworkSecurityGroups"),
            f"{name}.networkInterfaces[{index}].effectiveNetworkSecurityGroups",
        )
        groups = _require_list(
            effective.get("value"),
            f"{name}.networkInterfaces[{index}].effectiveNetworkSecurityGroups.value",
        )
        if not groups:
            raise ValueError(f"{name} effective NSG response cannot be empty")
        for group in groups:
            group_mapping = _require_mapping(group, f"{name}.effectiveNsg")
            association = _require_mapping(
                group_mapping.get("association"),
                f"{name}.effectiveNsg.association",
            )
            association_ids = {
                child["id"].casefold()
                for key in ("networkInterface", "subnet")
                if isinstance((child := association.get(key)), dict)
                and isinstance(child.get("id"), str)
            }
            if len(association_ids) != 1 or not (
                association_ids <= allowed_associations
            ):
                raise ValueError(
                    f"{name} effective NSG association is not attached to its NIC"
                )
            rules = _require_list(
                group_mapping.get("securityRules"),
                f"{name}.effectiveNsg.securityRules",
            )
            if not rules:
                raise ValueError(f"{name} effective NSG rules cannot be empty")
    if captured_ids != declared_ids:
        raise ValueError(
            f"{name} effective NSG captures do not match the VM-attached NICs"
        )


def _vm_public_management_ports(raw: dict[str, Any]) -> set[int]:
    """Return publicly exposed SSH and RDP ports from effective NSG output."""
    exposed_ports: set[int] = set()
    interfaces = _require_list(
        raw.get("networkInterfaces"),
        "legacyVm.networkInterfaces",
    )
    for interface_value in interfaces:
        interface = _require_mapping(interface_value, "legacyVm.networkInterface")
        effective = _require_mapping(
            interface.get("effectiveNetworkSecurityGroups"),
            "legacyVm.effectiveNetworkSecurityGroups",
        )
        groups = _require_list(
            effective.get("value"),
            "legacyVm.effectiveNetworkSecurityGroups.value",
        )
        for group_value in groups:
            group = _require_mapping(group_value, "legacyVm.effectiveNsg")
            rules = _require_list(
                group.get("securityRules"),
                "legacyVm.effectiveNsg.securityRules",
            )
            for rule_value in rules:
                rule = _require_mapping(rule_value, "legacyVm.securityRule")
                rule_properties = (
                    _require_mapping(
                        rule.get("properties"),
                        "legacyVm.securityRule.properties",
                    )
                    if "properties" in rule
                    else rule
                )
                if (
                    str(rule_properties.get("access", "")).casefold() != "allow"
                    or str(rule_properties.get("direction", "")).casefold() != "inbound"
                ):
                    continue
                sources = [
                    rule_properties.get("sourceAddressPrefix"),
                    *_require_list(
                        rule_properties.get("sourceAddressPrefixes", []),
                        "legacyVm.securityRule.sourceAddressPrefixes",
                    ),
                ]
                ports = [
                    rule_properties.get("destinationPortRange"),
                    *_require_list(
                        rule_properties.get("destinationPortRanges", []),
                        "legacyVm.securityRule.destinationPortRanges",
                    ),
                ]
                if any(source in _PUBLIC_SOURCES for source in sources):
                    for port in ports:
                        exposed_ports.update(
                            _management_ports_in_expression(port)
                        )
    return exposed_ports


def _vm_jit_management_ports(
    raw: dict[str, Any],
    expected_vm_id: str,
) -> set[int]:
    """Return management ports covered by a bound Defender JIT policy."""
    policy = raw.get("jitPolicy")
    if policy is None:
        return set()
    policy_mapping = _require_mapping(policy, "legacyVm.jitPolicy")
    policy_id = _require_string(
        policy_mapping.get("id"),
        "legacyVm.jitPolicy.id",
    )
    policy_type = _require_string(
        policy_mapping.get("type"),
        "legacyVm.jitPolicy.type",
    )
    vm_parts = expected_vm_id.strip("/").split("/")
    policy_parts = policy_id.strip("/").split("/")
    if (
        policy_type.casefold()
        != "Microsoft.Security/locations/jitNetworkAccessPolicies".casefold()
        or len(policy_parts) != 10
        or policy_parts[0].casefold() != "subscriptions"
        or policy_parts[1].casefold() != vm_parts[1].casefold()
        or policy_parts[2].casefold() != "resourcegroups"
        or policy_parts[3].casefold() != vm_parts[3].casefold()
        or policy_parts[4].casefold() != "providers"
        or policy_parts[5].casefold() != "microsoft.security"
        or policy_parts[6].casefold() != "locations"
        or not policy_parts[7]
        or policy_parts[8].casefold() != "jitnetworkaccesspolicies"
        or not policy_parts[9]
    ):
        raise ValueError(
            "legacy VM JIT evidence is not a bound Defender JIT policy"
        )
    properties = _require_mapping(
        policy_mapping.get("properties"),
        "legacyVm.jitPolicy.properties",
    )
    virtual_machines = _require_list(
        properties.get("virtualMachines", []),
        "legacyVm.jitPolicy.virtualMachines",
    )
    matches = [
        _require_mapping(item, "legacyVm.jitPolicy.virtualMachine")
        for item in virtual_machines
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and _same_resource_id(item["id"], expected_vm_id)
    ]
    if len(matches) != 1:
        raise ValueError(
            "legacy VM JIT policy must include the exact source VM once"
        )
    covered_ports: set[int] = set()
    for index, port_value in enumerate(
        _require_list(
            matches[0].get("ports"),
            "legacyVm.jitPolicy.virtualMachine.ports",
        )
    ):
        port = _require_mapping(
            port_value,
            f"legacyVm.jitPolicy.virtualMachine.ports[{index}]",
        ).get("number")
        if not isinstance(port, int) or isinstance(port, bool):
            raise ValueError(
                "legacyVm.jitPolicy port number must be an integer"
            )
        if port in _MANAGEMENT_PORTS:
            covered_ports.add(port)
    return covered_ports


def _parse_vm_control(
    before: dict[str, Any],
    after: dict[str, Any],
    target_output: dict[str, Any],
    decision: DefenderDecision,
) -> dict[str, Any]:
    """Validate source-VM management exposure or its documented exception."""
    resource_id = target_output["network"]["migrationSourceVmResourceId"]
    for name, raw in (("legacyVm.before", before), ("legacyVm.after", after)):
        vm = _require_mapping(raw.get("vm"), f"{name}.vm")
        vm_properties = _resource_properties(
            vm,
            resource_id,
            "Microsoft.Compute/virtualMachines",
            f"{name}.vm",
        )
        _validate_vm_network_binding(raw, vm_properties, name)
    before_exposed = bool(
        _vm_public_management_ports(before)
        - _vm_jit_management_ports(before, resource_id)
    )
    after_exposed = bool(
        _vm_public_management_ports(after)
        - _vm_jit_management_ports(after, resource_id)
    )
    if after_exposed:
        expected = "documented-exception"
    elif before_exposed:
        expected = "remediated"
    else:
        expected = "already-compliant"
    _validate_decision(decision, expected, "legacyVmExposure")
    return _decision_result(
        resource_id,
        decision,
        "public-management-ingress" if before_exposed else "segmented-or-jit",
        "public-management-ingress" if after_exposed else "segmented-or-jit",
    )


def _is_matching_image_subassessment(
    value: Any,
    registry_resource_id: str,
    resource_path: str,
    repository: str,
    digest: str,
) -> bool:
    """Match one structured image subassessment beneath the handoff ACR."""
    if not isinstance(value, dict):
        return False
    record_type = value.get("type")
    record_id = value.get("id")
    if (
        not isinstance(record_type, str)
        or record_type.casefold()
        != "Microsoft.Security/assessments/subAssessments".casefold()
        or not isinstance(record_id, str)
    ):
        return False
    prefix = f"{registry_resource_id.rstrip('/')}/{resource_path}/"
    if not record_id.casefold().startswith(prefix.casefold()):
        return False
    subassessment_name = record_id[len(prefix) :]
    if not subassessment_name or "/" in subassessment_name:
        return False
    properties = value.get("properties")
    if not isinstance(properties, dict):
        return False
    artifact = properties.get("artifactDetails")
    return (
        isinstance(artifact, dict)
        and artifact.get("repositoryName") == repository
        and artifact.get("digest") == digest
    )


def _parse_image_assessment(
    raw: dict[str, Any],
    reference: DefenderImageAssessmentCapture,
    handoff: dict[str, Any],
    resource_path: str,
) -> dict[str, Any]:
    """Validate a digest-bound image assessment query without timing assumptions."""
    digest = reference.digest
    if digest != handoff["containerImage"]["digest"]:
        raise ValueError("image assessment digest differs from the handoff")
    values = _require_list(raw.get("value"), "imageAssessment.value")
    matching = [
        item
        for item in values
        if _is_matching_image_subassessment(
            item,
            handoff["containerImage"]["registryResourceId"],
            resource_path,
            handoff["containerImage"]["repository"],
            digest,
        )
    ]
    if reference.status == "completed" and not matching:
        raise ValueError("completed image assessment has no handoff digest result")
    finding_count: int | None = (
        len(matching) if reference.status == "completed" else None
    )
    return {
        "digest": digest,
        "status": reference.status,
        "queriedAt": _format_datetime(reference.queried_at),
        "findingCount": finding_count,
        "asynchronous": True,
    }


def _query_count(raw: dict[str, Any], name: str) -> int:
    """Return the record count from one Defender list response."""
    return len(_require_list(raw.get("value"), f"{name}.value"))


def _validate_query_envelope(
    raw: dict[str, Any],
    reference: QueryArtifact | DefenderImageAssessmentCapture,
    operation: str,
    resource_path: str,
    root: Path,
    contracts: Path,
) -> dict[str, Any]:
    """Validate request provenance inside one digest-bound query artifact."""
    _validate_schema(
        _contract_file(root, contracts, "defender-query-envelope.schema.json"),
        raw,
    )
    request = _require_mapping(raw.get("request"), f"{operation}.request")
    expected_scope = getattr(
        reference,
        "scope_resource_id",
        getattr(reference, "registry_resource_id", None),
    )
    if (
        request.get("method") != "GET"
        or request.get("operation") != operation
        or not isinstance(expected_scope, str)
        or not _same_resource_id(
            _require_string(
                request.get("scopeResourceId"),
                f"{operation}.request.scopeResourceId",
            ),
            expected_scope,
        )
        or request.get("resourcePath") != resource_path
        or request.get("apiVersion") != reference.api_version
        or _parse_aware_datetime(
            request.get("queriedAt"),
            f"{operation}.request.queriedAt",
        )
        != reference.queried_at
    ):
        raise ValueError(f"{operation} raw request provenance differs from capture")
    return _require_mapping(raw.get("response"), f"{operation}.response")


def _validate_attack_path_envelope(
    raw: dict[str, Any],
    reference: QueryArtifact,
    subscription_id: str,
    contract: dict[str, Any],
    root: Path,
    contracts: Path,
) -> list[dict[str, Any]]:
    """Validate one complete subscription-bound attack-path ARG response."""
    _validate_schema(
        _contract_file(
            root,
            contracts,
            "defender-attack-path-envelope.schema.json",
        ),
        raw,
    )
    request = _require_mapping(raw.get("request"), "attackPaths.request")
    body = _require_mapping(request.get("body"), "attackPaths.request.body")
    expected_scope = f"/subscriptions/{subscription_id}"
    expected_query = contract["queryTemplate"].replace(
        "{subscriptionId}",
        subscription_id,
    )
    if (
        request.get("method") != contract["method"]
        or request.get("operation") != "subscription-attack-paths"
        or not _same_resource_id(
            _require_string(
                request.get("scopeResourceId"),
                "attackPaths.request.scopeResourceId",
            ),
            expected_scope,
        )
        or request.get("resourcePath") != contract["resourcePath"]
        or request.get("apiVersion") != reference.api_version
        or _parse_aware_datetime(
            request.get("queriedAt"),
            "attackPaths.request.queriedAt",
        )
        != reference.queried_at
        or body.get("subscriptions") != [subscription_id]
        or body.get("query") != expected_query
        or body.get("options") != {"resultFormat": "objectArray"}
    ):
        raise ValueError(
            "attackPaths Azure Resource Graph request differs from the contract"
        )

    response = _require_mapping(raw.get("response"), "attackPaths.response")
    data = _require_list(response.get("data"), "attackPaths.response.data")
    if (
        response.get("count") != len(data)
        or response.get("totalRecords") != len(data)
        or response.get("resultTruncated") != "false"
    ):
        raise ValueError("attackPaths Azure Resource Graph response is incomplete")

    prefix = (
        f"/subscriptions/{subscription_id}/providers/"
        "Microsoft.Security/attackPaths/"
    )
    records: list[dict[str, Any]] = []
    for index, value in enumerate(data):
        item = _require_mapping(value, f"attackPaths.response.data[{index}]")
        resource_id = _require_string(
            item.get("id"),
            f"attackPaths.response.data[{index}].id",
        )
        _require_mapping(
            item.get("properties"),
            f"attackPaths.response.data[{index}].properties",
        )
        name = resource_id[len(prefix) :] if resource_id.casefold().startswith(
            prefix.casefold()
        ) else ""
        if (
            not name
            or "/" in name
            or item.get("name") != name
            or not isinstance(item.get("type"), str)
            or item["type"].casefold() != "microsoft.security/attackpaths"
            or item.get("subscriptionId", "").casefold() != subscription_id.casefold()
        ):
            raise ValueError(
                "attackPaths response contains a resource outside the subscription"
            )
        records.append(item)
    return records


def _validate_query_contracts(
    capture: DefenderEvidenceCapture,
    handoff: dict[str, Any],
    registry: dict[str, Any],
    subscription_id: str,
) -> None:
    """Bind each asynchronous query attempt to its frozen Azure scope."""
    subscription_scope = f"/subscriptions/{subscription_id}"
    contracts = registry["evidence"]["queryContracts"]
    checks = (
        (
            "imageAssessment",
            capture.image_assessment.registry_resource_id,
            handoff["containerImage"]["registryResourceId"],
            capture.image_assessment.api_version,
        ),
        (
            "recommendations",
            capture.security_context.recommendations.scope_resource_id,
            subscription_scope,
            capture.security_context.recommendations.api_version,
        ),
        (
            "secureScore",
            capture.security_context.secure_score.scope_resource_id,
            subscription_scope,
            capture.security_context.secure_score.api_version,
        ),
        (
            "mcsb",
            capture.security_context.mcsb.scope_resource_id,
            subscription_scope,
            capture.security_context.mcsb.api_version,
        ),
    )
    for name, actual_scope, expected_scope, api_version in checks:
        if not _same_resource_id(actual_scope, expected_scope):
            raise ValueError(f"{name} query scope differs from the frozen handoff scope")
        if api_version != contracts[name]["apiVersion"]:
            raise ValueError(f"{name} query API version differs from the registry")
    attack_paths = capture.security_context.attack_paths
    if (
        not _same_resource_id(attack_paths.scope_resource_id, subscription_scope)
        or attack_paths.api_version != contracts["attackPaths"]["apiVersion"]
    ):
        raise ValueError("attackPaths query differs from the frozen subscription query")


def _parse_legacy_vm_coverage(
    raw: dict[str, Any],
    source_vm_resource_id: str,
    registry: dict[str, Any],
    repository_root: Path,
    contracts: Path,
) -> tuple[dict[str, Any], datetime]:
    """Validate that subscription-enforced P2 covers both retained legacy VMs."""
    _validate_schema(
        _contract_file(
            repository_root,
            contracts,
            "defender-legacy-vm-coverage.schema.json",
        ),
        raw,
    )
    coverage_contract = registry["foundation"]["legacyVmCoverage"]
    if raw.get("apiVersion") != coverage_contract["apiVersion"]:
        raise ValueError("legacy VM coverage API version differs from the contract")
    observed_at = _parse_aware_datetime(
        raw.get("observedAt"),
        "legacyVmCoverage.observedAt",
    )

    parts = source_vm_resource_id.strip("/").split("/")
    if (
        len(parts) != 8
        or parts[0].casefold() != "subscriptions"
        or parts[2].casefold() != "resourcegroups"
        or parts[4].casefold() != "providers"
        or parts[5].casefold() != "microsoft.compute"
        or parts[6].casefold() != "virtualmachines"
    ):
        raise ValueError("migration source VM does not use the frozen ARM shape")
    source_name = parts[7]
    prefixes = ("vm-dotnet-", "vm-java-")
    matching_prefix = next(
        (prefix for prefix in prefixes if source_name.casefold().startswith(prefix)),
        None,
    )
    if matching_prefix is None:
        raise ValueError("migration source VM does not use the frozen stack name")
    participant_suffix = source_name[len(matching_prefix) :]
    if not participant_suffix:
        raise ValueError("migration source VM has no participant suffix")
    parent_id = "/" + "/".join(parts[:7])
    expected_ids = {
        workload: f"{parent_id}/vm-{workload}-{participant_suffix}"
        for workload in coverage_contract["requiredWorkloads"]
    }

    entries = _require_list(
        raw.get("virtualMachines"),
        "legacyVmCoverage.virtualMachines",
    )
    by_workload: dict[str, dict[str, Any]] = {}
    for index, entry_value in enumerate(entries):
        entry = _require_mapping(
            entry_value,
            f"legacyVmCoverage.virtualMachines[{index}]",
        )
        workload = _require_string(
            entry.get("workload"),
            f"legacyVmCoverage.virtualMachines[{index}].workload",
        )
        if workload in by_workload:
            raise ValueError("legacy VM coverage repeats a workload")
        request = _require_mapping(
            entry.get("request"),
            f"legacyVmCoverage.{workload}.request",
        )
        response = _require_mapping(
            entry.get("response"),
            f"legacyVmCoverage.{workload}.response",
        )
        body = _require_mapping(
            response.get("body"),
            f"legacyVmCoverage.{workload}.response.body",
        )
        expected_id = expected_ids.get(workload)
        if (
            expected_id is None
            or request.get("method") != "GET"
            or not _same_resource_id(
                _require_string(
                    request.get("resourceId"),
                    f"legacyVmCoverage.{workload}.request.resourceId",
                ),
                expected_id,
            )
            or response.get("statusCode") != 200
            or not _same_resource_id(
                _require_string(
                    body.get("id"),
                    f"legacyVmCoverage.{workload}.response.body.id",
                ),
                expected_id,
            )
            or body.get("name") != expected_id.rsplit("/", 1)[-1]
            or not isinstance(body.get("type"), str)
            or body["type"].casefold()
            != "Microsoft.Compute/virtualMachines".casefold()
            or _require_mapping(
                body.get("properties"),
                f"legacyVmCoverage.{workload}.response.body.properties",
            ).get("provisioningState")
            != "Succeeded"
        ):
            raise ValueError(
                f"legacy VM coverage does not prove the retained {workload} VM"
            )
        by_workload[workload] = {
            "workload": workload,
            "resourceId": expected_id,
            "location": _require_string(
                body.get("location"),
                f"legacyVmCoverage.{workload}.response.body.location",
            ),
            "provisioningState": "Succeeded",
        }
    if set(by_workload) != set(coverage_contract["requiredWorkloads"]):
        raise ValueError("legacy VM coverage must contain dotnet and java exactly once")
    if not any(
        _same_resource_id(source_vm_resource_id, item["resourceId"])
        for item in by_workload.values()
    ):
        raise ValueError("legacy VM coverage omits the selected migration source VM")
    return (
        {
            "subscriptionPricingEnforced": True,
            "pricingName": coverage_contract["pricingName"],
            "pricingSubPlan": coverage_contract["pricingSubPlan"],
            "observedAt": _format_datetime(observed_at),
            "virtualMachines": [
                by_workload[workload]
                for workload in coverage_contract["requiredWorkloads"]
            ],
        },
        observed_at,
    )


def _parse_seed_recommendations(
    response: dict[str, Any],
    expected_resources: dict[str, str],
    minimum_unhealthy: int,
) -> dict[str, Any]:
    """Require pre-warmed assessment context for every challenge resource."""
    values = _require_list(response.get("value"), "seed recommendations.value")
    covered: set[str] = set()
    unhealthy = 0
    for index, item_value in enumerate(values):
        item = _require_mapping(
            item_value,
            f"seed recommendations.value[{index}]",
        )
        if (
            not isinstance(item.get("type"), str)
            or item["type"].casefold()
            != "Microsoft.Security/assessments".casefold()
        ):
            raise ValueError("seed recommendation has an invalid resource type")
        properties = _require_mapping(
            item.get("properties"),
            f"seed recommendations.value[{index}].properties",
        )
        resource_details = _require_mapping(
            properties.get("resourceDetails"),
            f"seed recommendations.value[{index}].resourceDetails",
        )
        resource_id = _require_string(
            resource_details.get("id"),
            f"seed recommendations.value[{index}].resourceDetails.id",
        )
        assessment_id = _require_string(
            item.get("id"),
            f"seed recommendations.value[{index}].id",
        )
        if (
            resource_details.get("source") != "Azure"
            or not assessment_id.casefold().startswith(
                (
                    resource_id.rstrip("/")
                    + "/providers/Microsoft.Security/assessments/"
                ).casefold()
            )
            or not _require_string(
                properties.get("displayName"),
                f"seed recommendations.value[{index}].displayName",
            )
        ):
            raise ValueError("seed recommendation is not bound to an Azure resource")
        status = _require_mapping(
            properties.get("status"),
            f"seed recommendations.value[{index}].status",
        ).get("code")
        if status not in {"Healthy", "Unhealthy", "NotApplicable"}:
            raise ValueError("seed recommendation has an invalid assessment status")
        if status == "Unhealthy":
            unhealthy += 1
        for label, expected_id in expected_resources.items():
            if _same_resource_id(resource_id, expected_id):
                covered.add(label)
                break
    missing = set(expected_resources) - covered
    if missing:
        raise ValueError(
            "pre-warmed recommendations omit required resource context: "
            + sorted(missing)[0]
        )
    if unhealthy < minimum_unhealthy:
        raise ValueError(
            "pre-warmed recommendations lack the deterministic unhealthy finding"
        )
    return {
        "recordCount": len(values),
        "unhealthyCount": unhealthy,
        "coveredResources": list(expected_resources),
    }


def _parse_seed_secure_score(
    response: dict[str, Any],
    subscription_id: str,
) -> int:
    """Require one structurally valid subscription Secure Score record."""
    values = _require_list(response.get("value"), "seed secureScore.value")
    expected_id = (
        f"/subscriptions/{subscription_id}/providers/"
        "Microsoft.Security/secureScores/ascScore"
    )
    matches = [
        item
        for item in values
        if isinstance(item, dict)
        and item.get("name") == "ascScore"
        and isinstance(item.get("type"), str)
        and item["type"].casefold()
        == "Microsoft.Security/secureScores".casefold()
        and isinstance(item.get("id"), str)
        and _same_resource_id(item["id"], expected_id)
    ]
    if len(matches) != 1:
        raise ValueError("pre-warmed snapshot lacks the subscription Secure Score")
    properties = _require_mapping(
        matches[0].get("properties"),
        "seed secureScore.properties",
    )
    score = _require_mapping(
        properties.get("score"),
        "seed secureScore.properties.score",
    )
    current = score.get("current")
    maximum = score.get("max")
    percentage = score.get("percentage")
    numeric = lambda value: isinstance(value, (int, float)) and not isinstance(
        value,
        bool,
    )
    if (
        not numeric(current)
        or not numeric(maximum)
        or not numeric(percentage)
        or maximum <= 0
        or current < 0
        or current > maximum
        or percentage < 0
        or percentage > 1
    ):
        raise ValueError("pre-warmed Secure Score values are invalid")
    return len(values)


def _validate_mcsb_response(
    response: dict[str, Any],
    subscription_id: str,
    resource_path: str,
    source: str,
) -> list[dict[str, Any]]:
    """Bind every MCSB response record to the requested standard path."""
    values = _require_list(response.get("value"), f"{source}.value")
    prefix = f"/subscriptions/{subscription_id}/{resource_path}/"
    validated: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        item = _require_mapping(value, f"{source}.value[{index}]")
        resource_id = _require_string(
            item.get("id"),
            f"{source}.value[{index}].id",
        )
        control_name = resource_id[len(prefix) :] if resource_id.casefold().startswith(
            prefix.casefold()
        ) else ""
        if (
            not control_name
            or "/" in control_name
            or not isinstance(item.get("type"), str)
            or item["type"].casefold()
            != "Microsoft.Security/regulatoryComplianceControl".casefold()
        ):
            raise ValueError(f"{source} response is outside the requested MCSB standard")
        validated.append(item)
    return validated


def _parse_seed_mcsb(
    response: dict[str, Any],
    subscription_id: str,
    resource_path: str,
) -> int:
    """Require one structurally valid MCSB regulatory compliance control."""
    values = _validate_mcsb_response(
        response,
        subscription_id,
        resource_path,
        "seed mcsb",
    )
    if not values:
        raise ValueError("pre-warmed snapshot lacks MCSB control context")
    for index, item in enumerate(values):
        properties = _require_mapping(
            item.get("properties"),
            f"seed mcsb.value[{index}].properties",
        )
        if (
            properties.get("state")
            not in {"Passed", "Failed", "Skipped", "Unsupported"}
            or not _require_string(
                properties.get("description"),
                f"seed mcsb.value[{index}].description",
            )
        ):
            raise ValueError("pre-warmed MCSB control state is invalid")
        for field in (
            "passedAssessments",
            "failedAssessments",
            "skippedAssessments",
        ):
            value = properties.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError("pre-warmed MCSB assessment counts are invalid")
    return len(values)


def _parse_seed_snapshot(
    raw: dict[str, Any],
    capture: DefenderEvidenceCapture,
    handoff: dict[str, Any],
    coverage: dict[str, Any],
    registry: dict[str, Any],
    enabled_pricings_queried_at: datetime,
    repository_root: Path,
    contracts: Path,
) -> dict[str, Any]:
    """Validate a pre-warmed, digest-bound deterministic Defender snapshot."""
    _validate_schema(
        _contract_file(
            repository_root,
            contracts,
            "defender-seed-snapshot.schema.json",
        ),
        raw,
    )
    subscription_id = capture.foundation.subscription_id
    if raw.get("subscriptionId") != subscription_id:
        raise ValueError("seed snapshot targets another subscription")
    try:
        recommendations = QueryArtifact.model_validate(raw["recommendations"])
        secure_score = QueryArtifact.model_validate(raw["secureScore"])
        mcsb = QueryArtifact.model_validate(raw["mcsb"])
        image = DefenderImageAssessmentCapture.model_validate(
            raw["imageAssessment"]
        )
    except ValidationError as error:
        raise ValueError(f"seed snapshot references are invalid: {error}") from error
    references = [recommendations, secure_score, mcsb, image]
    files = [reference.file for reference in references]
    current_files = {
        capture.security_context.recommendations.file,
        capture.security_context.secure_score.file,
        capture.security_context.mcsb.file,
        capture.image_assessment.file,
    }
    if len(files) != len(set(files)) or set(files) & current_files:
        raise ValueError(
            "seed snapshot must use distinct artifacts from current query evidence"
        )

    snapshot_at = _parse_aware_datetime(
        raw.get("capturedAt"),
        "seedSnapshot.capturedAt",
    )
    current_query_times = (
        capture.security_context.recommendations.queried_at,
        capture.security_context.secure_score.queried_at,
        capture.security_context.mcsb.queried_at,
        capture.image_assessment.queried_at,
        capture.security_context.attack_paths.queried_at,
    )
    if (
        snapshot_at <= enabled_pricings_queried_at
        or any(
            reference.queried_at <= enabled_pricings_queried_at
            for reference in references
        )
        or any(snapshot_at <= reference.queried_at for reference in references)
        or snapshot_at >= min(current_query_times)
        or snapshot_at > capture.captured_at
    ):
        raise ValueError(
            "seed snapshot chronology does not prove pre-warmed Defender context"
        )

    subscription_scope = f"/subscriptions/{subscription_id}"
    query_contracts = registry["evidence"]["queryContracts"]
    checks = (
        (
            recommendations,
            subscription_scope,
            query_contracts["recommendations"]["apiVersion"],
            "recommendations",
        ),
        (
            secure_score,
            subscription_scope,
            query_contracts["secureScore"]["apiVersion"],
            "secureScore",
        ),
        (
            mcsb,
            subscription_scope,
            query_contracts["mcsb"]["apiVersion"],
            "mcsb",
        ),
        (
            image,
            handoff["containerImage"]["registryResourceId"],
            query_contracts["imageAssessment"]["apiVersion"],
            "imageAssessment",
        ),
    )
    for reference, expected_scope, expected_api_version, name in checks:
        actual_scope = getattr(
            reference,
            "scope_resource_id",
            getattr(reference, "registry_resource_id", None),
        )
        if (
            not isinstance(actual_scope, str)
            or not _same_resource_id(actual_scope, expected_scope)
            or reference.api_version != expected_api_version
        ):
            raise ValueError(f"seed {name} query differs from the frozen contract")

    recommendations_response = _validate_query_envelope(
        _load_reference(repository_root, recommendations),
        recommendations,
        "subscription-recommendations",
        query_contracts["recommendations"]["resourcePath"],
        repository_root,
        contracts,
    )
    secure_score_response = _validate_query_envelope(
        _load_reference(repository_root, secure_score),
        secure_score,
        "subscription-secure-score",
        query_contracts["secureScore"]["resourcePath"],
        repository_root,
        contracts,
    )
    mcsb_response = _validate_query_envelope(
        _load_reference(repository_root, mcsb),
        mcsb,
        "subscription-mcsb-controls",
        query_contracts["mcsb"]["resourcePath"],
        repository_root,
        contracts,
    )
    image_response = _validate_query_envelope(
        _load_reference(repository_root, image),
        image,
        "registry-image-subassessments",
        query_contracts["imageAssessment"]["resourcePath"],
        repository_root,
        contracts,
    )
    coverage_ids = {
        item["workload"]: item["resourceId"]
        for item in coverage["virtualMachines"]
    }
    expected_resources = {
        "dotnet-vm": coverage_ids["dotnet"],
        "java-vm": coverage_ids["java"],
        "container-app": handoff["application"]["resourceId"],
        "container-registry": handoff["containerImage"]["registryResourceId"],
        "database": _database_server_id(handoff),
    }
    snapshot_contract = registry["foundation"]["seedSnapshot"]
    recommendation_summary = _parse_seed_recommendations(
        recommendations_response,
        expected_resources,
        snapshot_contract["minimumUnhealthyRecommendations"],
    )
    secure_score_count = _parse_seed_secure_score(
        secure_score_response,
        subscription_id,
    )
    mcsb_count = _parse_seed_mcsb(
        mcsb_response,
        subscription_id,
        query_contracts["mcsb"]["resourcePath"],
    )
    image_summary = _parse_image_assessment(
        image_response,
        image,
        handoff,
        query_contracts["imageAssessment"]["resourcePath"],
    )
    if image_summary["findingCount"] is None or image_summary["findingCount"] < 1:
        raise ValueError("pre-warmed snapshot lacks image assessment context")
    return {
        "capturedAt": _format_datetime(snapshot_at),
        "requiredSignals": snapshot_contract["requiredNonEmptySignals"],
        "recommendationRecordCount": recommendation_summary["recordCount"],
        "unhealthyRecommendationCount": recommendation_summary[
            "unhealthyCount"
        ],
        "recommendationResourceCoverage": recommendation_summary[
            "coveredResources"
        ],
        "secureScoreRecordCount": secure_score_count,
        "mcsbRecordCount": mcsb_count,
        "imageAssessmentRecordCount": image_summary["findingCount"],
    }


def _normalize_cleanup_resource(
    item_value: Any,
    item_name: str,
    subscription_id: str,
    allowed_types: set[str],
    seen_ids: set[str],
    state_fields: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Normalize one cleanup resource after enforcing its subscription boundary."""
    item = _require_mapping(item_value, item_name)
    resource_id = _require_string(item.get("id"), f"{item_name}.id")
    normalized_id = resource_id.rstrip("/").casefold()
    if normalized_id in seen_ids:
        raise ValueError("cleanup inventory contains a duplicate resource ID")
    seen_ids.add(normalized_id)
    resource_type = _require_string(item.get("type"), f"{item_name}.type").casefold()
    if (
        _resource_subscription_id(resource_id, item_name).casefold()
        != subscription_id.casefold()
        or resource_type not in allowed_types
    ):
        raise ValueError(
            "cleanup inventory contains a resource outside its "
            "subscription or type boundary"
        )
    normalized = {
        "id": normalized_id,
        "name": _require_string(item.get("name"), f"{item_name}.name").casefold(),
        "type": resource_type,
        "kind": item.get("kind"),
        "properties": _require_mapping(
            item.get("properties"),
            f"{item_name}.properties",
        ),
    }
    normalized.update({field: item.get(field) for field in state_fields})
    return normalized


def _validate_cleanup_arm_properties(
    producer_name: str,
    item: dict[str, Any],
    item_name: str,
) -> None:
    """Validate the exact state fields returned by a Defender settings list."""
    properties = _require_mapping(item.get("properties"), f"{item_name}.properties")
    if producer_name == "autoProvisioningSettings":
        if (
            set(properties) != {"autoProvision"}
            or properties.get("autoProvision") not in {"On", "Off"}
            or item.get("kind") is not None
        ):
            raise ValueError(
                "cleanup auto-provisioning response has an invalid state shape"
            )
        return
    if (
        set(properties) != {"enabled"}
        or type(properties.get("enabled")) is not bool
        or item.get("kind") not in {"AlertSyncSettings", "DataExportSettings"}
    ):
        raise ValueError("cleanup settings response has an invalid state shape")


def _parse_cleanup_inventory(
    raw: dict[str, Any],
    subscription_id: str,
    registry: dict[str, Any],
    repository_root: Path,
    contracts: Path,
    name: str,
) -> tuple[list[dict[str, Any]], datetime, datetime]:
    """Validate and normalize one bounded Defender cleanup inventory."""
    _validate_schema(
        _contract_file(
            repository_root,
            contracts,
            "defender-cleanup-inventory-envelope.schema.json",
        ),
        raw,
    )
    cleanup_contract = registry["cleanup"]
    resource_types = set(cleanup_contract["cleanupInventoryResourceTypes"])
    producers = _require_mapping(
        cleanup_contract.get("cleanupInventoryProducers"),
        "cleanup.cleanupInventoryProducers",
    )
    resource_graph_contract = _require_mapping(
        producers.get("resourceGraph"),
        "cleanup.cleanupInventoryProducers.resourceGraph",
    )
    tables = _require_mapping(
        resource_graph_contract.get("tables"),
        "cleanup.cleanupInventoryProducers.resourceGraph.tables",
    )
    graph_resource_types = [
        _require_string(resource_type, f"cleanup table {table_name} resource type")
        for table_name, table_types in tables.items()
        for resource_type in _require_list(
            table_types,
            f"cleanup cleanupInventoryProducers.resourceGraph.tables.{table_name}",
        )
    ]
    arm_contracts = {
        producer_name: _require_mapping(
            producers.get(producer_name),
            f"cleanup.cleanupInventoryProducers.{producer_name}",
        )
        for producer_name in ("autoProvisioningSettings", "settings")
    }
    producer_resource_types = set(graph_resource_types) | {
        _require_string(
            producer.get("resourceType"),
            f"cleanup cleanupInventoryProducers.{producer_name}.resourceType",
        )
        for producer_name, producer in arm_contracts.items()
    }
    if (
        len(graph_resource_types) != len(set(graph_resource_types))
        or producer_resource_types != resource_types
    ):
        raise ValueError(
            "cleanup inventory producers do not cover the frozen resource types"
        )
    expected_query = (
        "union "
        + ", ".join(tables)
        + " | where type in~ ("
        + ", ".join(f"'{resource_type}'" for resource_type in graph_resource_types)
        + (
            ") | project id, name, type, properties, identity, location "
            "| order by id asc"
        )
    )
    resource_graph = _require_mapping(
        raw.get("resourceGraph"),
        f"{name}.resourceGraph",
    )
    request = _require_mapping(
        resource_graph.get("request"),
        f"{name}.resourceGraph.request",
    )
    body = _require_mapping(
        request.get("body"),
        f"{name}.resourceGraph.request.body",
    )
    expected_scope = f"/subscriptions/{subscription_id}"
    if (
        request.get("method") != resource_graph_contract["method"]
        or request.get("operation")
        != resource_graph_contract["operation"]
        or request.get("resourcePath")
        != resource_graph_contract["resourcePath"]
        or request.get("apiVersion")
        != resource_graph_contract["apiVersion"]
        or not _same_resource_id(
            _require_string(
                request.get("scopeResourceId"),
                f"{name}.resourceGraph.request.scopeResourceId",
            ),
            expected_scope,
        )
        or body.get("subscriptions") != [subscription_id]
        or body.get("query") != expected_query
    ):
        raise ValueError(
            f"{name} Resource Graph query differs from the cleanup inventory contract"
        )
    query_times = [
        _parse_aware_datetime(
            request.get("queriedAt"),
            f"{name}.resourceGraph.request.queriedAt",
        )
    ]
    response = _require_mapping(
        resource_graph.get("response"),
        f"{name}.resourceGraph.response",
    )
    data = _require_list(
        response.get("data"),
        f"{name}.resourceGraph.response.data",
    )
    if (
        response.get("count") != len(data)
        or response.get("totalRecords") != len(data)
        or response.get("resultTruncated") != "false"
        or "$skipToken" in response
    ):
        raise ValueError(f"{name} Resource Graph response is incomplete")

    graph_allowed_types = set(graph_resource_types)
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item_value in enumerate(data):
        normalized.append(
            _normalize_cleanup_resource(
                item_value,
                f"{name}.resourceGraph.response.data[{index}]",
                subscription_id,
                graph_allowed_types,
                seen_ids,
                ("identity", "location"),
            )
        )

    for producer_name, producer_contract in arm_contracts.items():
        envelope = _require_mapping(raw.get(producer_name), f"{name}.{producer_name}")
        arm_request = _require_mapping(
            envelope.get("request"),
            f"{name}.{producer_name}.request",
        )
        if (
            arm_request.get("method") != producer_contract["method"]
            or arm_request.get("operation") != producer_contract["operation"]
            or arm_request.get("resourcePath") != producer_contract["resourcePath"]
            or arm_request.get("apiVersion") != producer_contract["apiVersion"]
            or not _same_resource_id(
                _require_string(
                    arm_request.get("scopeResourceId"),
                    f"{name}.{producer_name}.request.scopeResourceId",
                ),
                expected_scope,
            )
        ):
            raise ValueError(
                f"{name} {producer_name} query differs from the cleanup "
                "inventory contract"
            )
        query_times.append(
            _parse_aware_datetime(
                arm_request.get("queriedAt"),
                f"{name}.{producer_name}.request.queriedAt",
            )
        )
        arm_response = _require_mapping(
            envelope.get("response"),
            f"{name}.{producer_name}.response",
        )
        if arm_response.get("nextLink") is not None:
            raise ValueError(f"{name} {producer_name} response is incomplete")
        values = _require_list(
            arm_response.get("value"),
            f"{name}.{producer_name}.response.value",
        )
        expected_type = {
            _require_string(
                producer_contract.get("resourceType"),
                f"cleanup {producer_name}.resourceType",
            )
        }
        for index, item_value in enumerate(values):
            item_name = f"{name}.{producer_name}.response.value[{index}]"
            item = _require_mapping(item_value, item_name)
            _validate_cleanup_arm_properties(producer_name, item, item_name)
            normalized_item = _normalize_cleanup_resource(
                item,
                item_name,
                subscription_id,
                expected_type,
                seen_ids,
            )
            item_resource_name = _require_string(
                item.get("name"),
                f"{item_name}.name",
            )
            expected_resource_id = (
                f"{expected_scope}/{producer_contract['resourcePath']}/"
                f"{item_resource_name}"
            )
            if not _same_resource_id(
                _require_string(item.get("id"), f"{item_name}.id"),
                expected_resource_id,
            ):
                raise ValueError(
                    f"{name} {producer_name} response ID differs from "
                    "the requested collection"
                )
            normalized.append(normalized_item)
    return (
        sorted(normalized, key=lambda item: item["id"]),
        min(query_times),
        max(query_times),
    )


def _validate_cleanup(
    cleanup: dict[str, Any],
    subscription_id: str,
    repository_root: Path,
    contracts: Path,
    registry: dict[str, Any],
    enabled_pricings_queried_at: datetime,
) -> dict[str, Any]:
    """Validate post-workshop restoration and cost-verification intent."""
    if cleanup["subscriptionId"] != subscription_id:
        raise ValueError("cleanup manifest targets another subscription")
    plans = cleanup["plans"]
    names = [plan["name"] for plan in plans]
    if len(names) != len(set(names)) or set(names) != _REQUIRED_PLAN_NAMES:
        raise ValueError("cleanup manifest must cover each managed pricing once")
    prior_reference = _require_mapping(
        cleanup.get("priorPricings"),
        "cleanup.priorPricings",
    )
    prior_raw = load_digest_bound_json(
        repository_root,
        _require_string(
            prior_reference.get("file"),
            "cleanup.priorPricings.file",
        ),
        _require_string(
            prior_reference.get("sha256"),
            "cleanup.priorPricings.sha256",
        ),
    )
    prior_response, prior_queried_at = _parse_pricing_envelope(
        prior_raw,
        subscription_id,
        repository_root,
        contracts,
    )
    if prior_queried_at >= enabled_pricings_queried_at:
        raise ValueError("prior pricing snapshot must precede paid-plan enablement")
    prior_inventory_reference = _require_mapping(
        cleanup.get("priorCleanupInventory"),
        "cleanup.priorCleanupInventory",
    )
    (
        prior_inventory,
        _prior_inventory_first_queried_at,
        prior_inventory_last_queried_at,
    ) = _parse_cleanup_inventory(
        load_digest_bound_json(
            repository_root,
            _require_string(
                prior_inventory_reference.get("file"),
                "cleanup.priorCleanupInventory.file",
            ),
            _require_string(
                prior_inventory_reference.get("sha256"),
                "cleanup.priorCleanupInventory.sha256",
            ),
        ),
        subscription_id,
        registry,
        repository_root,
        contracts,
        "cleanup.priorCleanupInventory",
    )
    if prior_inventory_last_queried_at >= enabled_pricings_queried_at:
        raise ValueError(
            "prior cleanup inventory must precede paid-plan enablement"
        )
    prior_by_name = _index_pricings(
        prior_response,
        subscription_id,
        "cleanup.priorPricings.response",
    )
    for plan in plans:
        properties = _require_mapping(
            prior_by_name[plan["name"]].get("properties"),
            f"prior {plan['name']}.properties",
        )
        if (
            properties.get("pricingTier") != plan["priorPricingTier"]
            or properties.get("subPlan") != plan.get("priorSubPlan")
            or properties.get("enforce") != plan.get("priorEnforce")
            or _normalized_pricing_extensions(
                properties.get("extensions", []),
                f"prior {plan['name']}.extensions",
            )
            != _normalized_pricing_extensions(
                plan.get("priorExtensions", []),
                f"cleanup {plan['name']}.priorExtensions",
            )
        ):
            raise ValueError(
                f"cleanup {plan['name']} prior state differs from its snapshot"
            )
    cost_status = cleanup["costVerification"]["status"]
    if cleanup["status"] == "scheduled" and cost_status != "scheduled":
        raise ValueError(
            "scheduled cleanup requires scheduled cost verification"
        )
    if cleanup["status"] == "completed" and cost_status != "queried":
        raise ValueError("completed cleanup requires a cost query")
    if cleanup["status"] == "completed":
        completed_at = _parse_aware_datetime(
            cleanup.get("completedAt"),
            "cleanup.completedAt",
        )
        if completed_at <= enabled_pricings_queried_at:
            raise ValueError(
                "cleanup must complete after paid-plan enablement"
            )
        post_inventory_reference = _require_mapping(
            cleanup.get("postCleanupInventory"),
            "cleanup.postCleanupInventory",
        )
        (
            post_inventory,
            post_inventory_first_queried_at,
            post_inventory_last_queried_at,
        ) = _parse_cleanup_inventory(
            load_digest_bound_json(
                repository_root,
                _require_string(
                    post_inventory_reference.get("file"),
                    "cleanup.postCleanupInventory.file",
                ),
                _require_string(
                    post_inventory_reference.get("sha256"),
                    "cleanup.postCleanupInventory.sha256",
                ),
            ),
            subscription_id,
            registry,
            repository_root,
            contracts,
            "cleanup.postCleanupInventory",
        )
        if post_inventory_first_queried_at <= completed_at:
            raise ValueError(
                "post-cleanup inventory query must follow cleanup"
            )
        if post_inventory != prior_inventory:
            raise ValueError(
                "post-cleanup Defender agent/resource inventory differs "
                "from prior state"
            )
        pricing_reference = _require_mapping(
            cleanup.get("postCleanupPricings"),
            "cleanup.postCleanupPricings",
        )
        pricing_raw = load_digest_bound_json(
            repository_root,
            _require_string(
                pricing_reference.get("file"),
                "cleanup.postCleanupPricings.file",
            ),
            _require_string(
                pricing_reference.get("sha256"),
                "cleanup.postCleanupPricings.sha256",
            ),
        )
        pricing_response, post_pricings_queried_at = _parse_pricing_envelope(
            pricing_raw,
            subscription_id,
            repository_root,
            contracts,
        )
        if post_pricings_queried_at <= completed_at:
            raise ValueError("post-cleanup pricing query must follow cleanup")
        pricing_by_name = _index_pricings(
            pricing_response,
            subscription_id,
            "cleanup.postCleanupPricings.response",
        )
        for plan in plans:
            properties = _require_mapping(
                pricing_by_name[plan["name"]].get("properties"),
                f"post-cleanup {plan['name']}.properties",
            )
            if properties.get("pricingTier") != plan["priorPricingTier"]:
                raise ValueError(
                    f"post-cleanup {plan['name']} tier differs from prior state"
                )
            if properties.get("subPlan") != plan.get("priorSubPlan"):
                raise ValueError(
                    f"post-cleanup {plan['name']} subPlan differs from prior state"
                )
            if properties.get("enforce") != plan.get("priorEnforce"):
                raise ValueError(
                    f"post-cleanup {plan['name']} enforce differs from prior state"
                )
            if _normalized_pricing_extensions(
                properties.get("extensions", []),
                f"post-cleanup {plan['name']}.extensions",
            ) != _normalized_pricing_extensions(
                plan.get("priorExtensions", []),
                f"cleanup {plan['name']}.priorExtensions",
            ):
                raise ValueError(
                    f"post-cleanup {plan['name']} extensions differ from prior state"
                )
        cost = cleanup["costVerification"]
        declared_queried_at = _parse_aware_datetime(
            cost.get("queriedAt"),
            "cleanup.costVerification.queriedAt",
        )
        cost_evidence = load_digest_bound_json(
            repository_root,
            _require_string(
                cost.get("evidenceFile"),
                "cleanup.costVerification.evidenceFile",
            ),
            _require_string(
                cost.get("evidenceSha256"),
                "cleanup.costVerification.evidenceSha256",
            ),
        )
        _validate_schema(
            _contract_file(
                repository_root,
                contracts,
                "defender-cost-query-envelope.schema.json",
            ),
            cost_evidence,
        )
        cost_request = _require_mapping(
            cost_evidence.get("request"),
            "cleanup.costVerification.request",
        )
        cost_queried_at = _parse_aware_datetime(
            cost_request.get("queriedAt"),
            "cleanup.costVerification.request.queriedAt",
        )
        if (
            not _same_resource_id(
                _require_string(
                    cost_request.get("scopeResourceId"),
                    "cleanup.costVerification.request.scopeResourceId",
                ),
                f"/subscriptions/{subscription_id}",
            )
            or cost_queried_at != declared_queried_at
            or cost_queried_at
            <= max(post_pricings_queried_at, post_inventory_last_queried_at)
        ):
            raise ValueError(
                "cleanup cost query must target the subscription after restoration"
            )
        query_period = _require_mapping(
            _require_mapping(
                cost_request.get("body"),
                "cleanup.costVerification.request.body",
            ).get("timePeriod"),
            "cleanup.costVerification.request.body.timePeriod",
        )
        query_from = _parse_aware_datetime(
            query_period.get("from"),
            "cleanup.costVerification.request.body.timePeriod.from",
        )
        query_to = _parse_aware_datetime(
            query_period.get("to"),
            "cleanup.costVerification.request.body.timePeriod.to",
        )
        if query_from > enabled_pricings_queried_at:
            raise ValueError(
                "cleanup cost query period does not cover paid-plan enablement"
            )
        if query_to < max(
            post_pricings_queried_at,
            post_inventory_last_queried_at,
        ):
            raise ValueError(
                "cleanup cost query period does not cover pricing restoration"
            )
        if query_to > cost_queried_at:
            raise ValueError(
                "cleanup cost query period ends after the query was captured"
            )

        cost_response = _require_mapping(
            cost_evidence.get("response"),
            "cleanup.costVerification.response",
        )
        response_id = _require_string(
            cost_response.get("id"),
            "cleanup.costVerification.response.id",
        )
        expected_response_prefix = (
            f"/subscriptions/{subscription_id}/providers/"
            "Microsoft.CostManagement/Query/"
        )
        if not response_id.casefold().startswith(
            expected_response_prefix.casefold()
        ):
            raise ValueError(
                "cleanup cost response ID differs from the cleanup subscription"
            )
        cost_properties = _require_mapping(
            cost_response.get("properties"),
            "cleanup.costVerification.response.properties",
        )
        if cost_properties.get("nextLink") is not None:
            raise ValueError("cleanup cost response must contain every result page")
        columns = _require_list(
            cost_properties.get("columns"),
            "cleanup.costVerification.response.properties.columns",
        )
        column_names = [
            _require_string(
                _require_mapping(
                    column,
                    (
                        "cleanup.costVerification.response.properties."
                        f"columns[{index}]"
                    ),
                ).get("name"),
                (
                    "cleanup.costVerification.response.properties."
                    f"columns[{index}].name"
                ),
            )
            for index, column in enumerate(columns)
        ]
        if not {
            "PreTaxCost",
            "ServiceName",
            "ResourceId",
            "Currency",
        }.issubset(set(column_names)):
            raise ValueError(
                "cleanup cost response is missing required Defender cost columns"
            )
        if len(column_names) != len(set(column_names)):
            raise ValueError(
                "cleanup cost response contains duplicate column names"
            )
        rows = _require_list(
            cost_properties.get("rows"),
            "cleanup.costVerification.response.properties.rows",
        )
        for index, row in enumerate(rows):
            if len(_require_list(row, f"cleanup cost row {index}")) != len(columns):
                raise ValueError(
                    "cleanup cost response row "
                    f"{index} does not match the column count"
                )
    return {
        "status": cleanup["status"],
        "facilitatorApprovalRequired": True,
        "costVerificationStatus": cost_status,
        "agentCleanupStatus": (
            "restored" if cleanup["status"] == "completed" else "scheduled"
        ),
        "priorCleanupInventoryCount": len(prior_inventory),
        "postCleanupInventoryCount": (
            len(post_inventory) if cleanup["status"] == "completed" else None
        ),
    }


def build_defender_evidence(
    capture_path: Path,
    handoff_path: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Build a deterministic Defender report without writing files.

    Args:
        capture_path: Digest-bound Challenge 5 capture manifest.
        handoff_path: Modernization handoff selected for the challenge.
        repository_root: Trusted repository boundary for all artifacts.

    Returns:
        A schema-valid normalized Defender evidence report.

    Raises:
        OSError: If an input cannot be read.
        ValueError: If provenance or security assertions fail.
        jsonschema.ValidationError: If an input or output violates its schema.
    """
    root = repository_root.resolve()
    contracts = _validate_contracts_directory(
        root,
        root / "workshop/contracts",
    )
    capture_resolved = resolve_repository_file(
        root,
        _relative_file(root, capture_path, "capture"),
    )
    handoff_resolved = resolve_repository_file(
        root,
        _relative_file(root, handoff_path, "handoff"),
    )
    capture_document = load_json_object(capture_resolved)
    _validate_schema(
        _contract_file(
            root,
            contracts,
            "defender-evidence-capture.schema.json",
        ),
        capture_document,
    )
    try:
        capture = DefenderEvidenceCapture.model_validate(capture_document)
    except ValidationError as error:
        raise ValueError(f"Defender capture manifest is invalid: {error}") from error

    registry = load_json_object(_contract_file(root, contracts, "defender.json"))
    _validate_schema(
        _contract_file(root, contracts, "defender.schema.json"),
        registry,
    )
    handoff, target_output, _, cleanup = _validate_identity(
        root,
        contracts,
        capture,
        capture_resolved,
        handoff_resolved,
    )
    subscription_id = capture.foundation.subscription_id
    protected_resource_ids = {
        "Container App": handoff["application"]["resourceId"],
        "container registry": handoff["containerImage"]["registryResourceId"],
        "database": handoff["database"]["resourceId"],
        "legacy VM": target_output["network"]["migrationSourceVmResourceId"],
    }
    mismatched_resources = [
        name
        for name, resource_id in protected_resource_ids.items()
        if _resource_subscription_id(resource_id, name).casefold()
        != subscription_id.casefold()
    ]
    if mismatched_resources:
        raise ValueError(
            "Defender subscription differs from protected resources: "
            + ", ".join(mismatched_resources)
        )

    pricings, enabled_pricings_queried_at = _parse_pricings(
        _load_reference(root, capture.foundation.pricings),
        registry,
        subscription_id,
        root,
        contracts,
    )
    if enabled_pricings_queried_at > capture.captured_at:
        raise ValueError(
            "Defender pricing state was queried after the capture completed"
        )
    manual_preflight = _parse_manual_preflight(
        _load_reference(root, capture.foundation.manual_preflight),
        subscription_id,
    )
    budget = _parse_budget(
        _load_reference(root, capture.foundation.budget),
        capture.foundation.budget,
        registry,
        subscription_id,
        root,
        contracts,
    )
    if (
        _parse_aware_datetime(
            manual_preflight["observedAt"],
            "manualPreflight.observedAt",
        )
        > enabled_pricings_queried_at
    ):
        raise ValueError(
            "manual preflight must precede the enabled pricing observation"
        )
    _validate_query_contracts(capture, handoff, registry, subscription_id)
    legacy_vm_coverage, legacy_vm_coverage_observed_at = (
        _parse_legacy_vm_coverage(
            _load_reference(root, capture.foundation.legacy_vm_coverage),
            target_output["network"]["migrationSourceVmResourceId"],
            registry,
            root,
            contracts,
        )
    )
    if (
        legacy_vm_coverage_observed_at < enabled_pricings_queried_at
        or legacy_vm_coverage_observed_at > capture.captured_at
    ):
        raise ValueError(
            "legacy VM coverage must be observed after P2 enablement"
        )
    seed_snapshot = _parse_seed_snapshot(
        _load_reference(root, capture.foundation.seed_snapshot),
        capture,
        handoff,
        legacy_vm_coverage,
        registry,
        enabled_pricings_queried_at,
        root,
        contracts,
    )
    acr_before = _load_reference(root, capture.resources.container_registry.before)
    acr_after = _load_reference(root, capture.resources.container_registry.after)
    acr_role_assignments = _load_reference(
        root,
        capture.resources.container_registry_role_assignments,
    )
    app_before = _load_reference(root, capture.resources.container_app.before)
    app_after = _load_reference(root, capture.resources.container_app.after)
    database_before = _load_reference(root, capture.resources.database.before)
    database_after = _load_reference(root, capture.resources.database.after)
    vm_before = _load_reference(root, capture.resources.legacy_vm.before)
    vm_after = _load_reference(root, capture.resources.legacy_vm.after)
    image_raw = _load_reference(root, capture.image_assessment)
    recommendations_raw = _load_reference(
        root,
        capture.security_context.recommendations,
    )
    secure_score_raw = _load_reference(root, capture.security_context.secure_score)
    mcsb_raw = _load_reference(root, capture.security_context.mcsb)
    attack_paths_raw = _load_reference(
        root,
        capture.security_context.attack_paths,
    )
    query_contracts = registry["evidence"]["queryContracts"]
    image_response = _validate_query_envelope(
        image_raw,
        capture.image_assessment,
        "registry-image-subassessments",
        query_contracts["imageAssessment"]["resourcePath"],
        root,
        contracts,
    )
    recommendations_response = _validate_query_envelope(
        recommendations_raw,
        capture.security_context.recommendations,
        "subscription-recommendations",
        query_contracts["recommendations"]["resourcePath"],
        root,
        contracts,
    )
    secure_score_response = _validate_query_envelope(
        secure_score_raw,
        capture.security_context.secure_score,
        "subscription-secure-score",
        query_contracts["secureScore"]["resourcePath"],
        root,
        contracts,
    )
    mcsb_response = _validate_query_envelope(
        mcsb_raw,
        capture.security_context.mcsb,
        "subscription-mcsb-controls",
        query_contracts["mcsb"]["resourcePath"],
        root,
        contracts,
    )
    attack_path_records = _validate_attack_path_envelope(
        attack_paths_raw,
        capture.security_context.attack_paths,
        subscription_id,
        query_contracts["attackPaths"],
        root,
        contracts,
    )

    controls = {
        "containerRegistry": _parse_registry_control(
            acr_before,
            acr_after,
            acr_role_assignments,
            handoff,
            target_output,
            app_after,
        ),
        "containerApp": _parse_container_app_control(
            app_before,
            app_after,
            handoff,
            capture.decisions.container_app_ingress,
        ),
        "database": _parse_database_control(
            database_before,
            database_after,
            handoff,
            capture.decisions.database_network,
        ),
        "legacyVm": _parse_vm_control(
            vm_before,
            vm_after,
            target_output,
            capture.decisions.legacy_vm_exposure,
        ),
    }
    image_assessment = _parse_image_assessment(
        image_response,
        capture.image_assessment,
        handoff,
        query_contracts["imageAssessment"]["resourcePath"],
    )
    mcsb_record_count = len(
        _validate_mcsb_response(
            mcsb_response,
            subscription_id,
            query_contracts["mcsb"]["resourcePath"],
            "mcsb",
        )
    )
    cleanup_result = _validate_cleanup(
        cleanup,
        subscription_id,
        root,
        contracts,
        registry,
        enabled_pricings_queried_at,
    )
    cleanup_result.update(
        {
            "manifestFile": capture.identity.cleanup_manifest.file,
            "manifestSha256": capture.identity.cleanup_manifest.sha256,
        }
    )

    if (
        str(capture.health.health_url).rstrip("/")
        != handoff["application"]["healthUrl"].rstrip("/")
        or str(capture.health.readiness_url).rstrip("/")
        != handoff["application"]["readinessUrl"].rstrip("/")
        or capture.health.revision_name != handoff["application"]["revisionName"]
    ):
        raise ValueError("post-change health does not target the handoff revision")

    report = {
        "schemaVersion": _REPORT_VERSION,
        "capturedAt": _format_datetime(capture.captured_at),
        "subject": {
            "sliceId": handoff["sliceId"],
            "sourceCommit": handoff["source"]["commitSha"],
            "containerAppResourceId": handoff["application"]["resourceId"],
            "revisionName": handoff["application"]["revisionName"],
            "containerRegistryResourceId": handoff["containerImage"][
                "registryResourceId"
            ],
            "databaseResourceId": handoff["database"]["resourceId"],
            "legacyVmResourceId": target_output["network"][
                "migrationSourceVmResourceId"
            ],
            "imageDigest": handoff["containerImage"]["digest"],
        },
        "capture": {
            "manifestFile": _relative_file(root, capture_resolved, "capture"),
            "manifestSha256": sha256_file(capture_resolved),
        },
        "foundation": {
            "subscriptionId": subscription_id,
            "dedicatedWorkshopSubscription": True,
            "facilitatorChangeApproval": capture.foundation.facilitator_change_approval,
            "requiredPricings": pricings,
            "budget": budget,
            "legacyVmCoverage": legacy_vm_coverage,
            "seedSnapshot": seed_snapshot,
            "serverlessContainers": manual_preflight,
        },
        "controls": controls,
        "imageAssessment": image_assessment,
        "securityContext": {
            "recommendationsQueried": True,
            "recommendationCount": _query_count(
                recommendations_response,
                "recommendations",
            ),
            "secureScoreQueried": True,
            "secureScoreRecordCount": _query_count(
                secure_score_response,
                "secureScore",
            ),
            "mcsbQueried": True,
            "mcsbRecordCount": mcsb_record_count,
            "attackPathsQueried": True,
            "attackPathCount": len(attack_path_records),
            "nonEmptyFindingsRequired": False,
        },
        "postureComparison": {
            "legacyVm": {
                "resourceId": target_output["network"]["migrationSourceVmResourceId"],
                "operatingSystemPatching": "customer-managed",
                "hostManagementSurface": "present",
            },
            "containerApp": {
                "resourceId": handoff["application"]["resourceId"],
                "operatingSystemPatching": "platform-managed",
                "hostManagementSurface": "absent",
                "runtimeProtectionClaim": "not-claimed-for-azure-container-apps",
            },
        },
        "health": {
            "observedAt": _format_datetime(capture.health.observed_at),
            "revisionName": capture.health.revision_name,
            "healthUrl": str(capture.health.health_url),
            "healthStatus": capture.health.health_status,
            "readinessUrl": str(capture.health.readiness_url),
            "readinessStatus": capture.health.readiness_status,
        },
        "cleanup": cleanup_result,
        "assertions": [
            "required-pricings-enabled",
            "both-retained-vms-covered-by-enforced-p2",
            "prewarmed-deterministic-snapshot-validated",
            "subscription-budget-active",
            "serverless-containers-owner-preflight",
            "acr-admin-authentication-disabled",
            "managed-identity-image-pull",
            "immutable-image-digest",
            "container-app-ingress-reviewed",
            "database-network-reviewed",
            "legacy-vm-exposure-reviewed",
            "image-assessment-queried",
            "secure-score-and-mcsb-context-queried",
            "post-change-health-passed",
            "cleanup-and-cost-verification-prepared",
            "asynchronous-findings-not-required",
        ],
        "result": "passed",
    }
    _validate_schema(
        _contract_file(root, contracts, "defender-evidence.schema.json"),
        report,
    )
    return report


def write_defender_evidence(
    capture_path: Path,
    handoff_path: Path,
    report_path: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Render and atomically write the canonical Challenge 5 report.

    Args:
        capture_path: Digest-bound Defender capture manifest.
        handoff_path: Modernization handoff selected for the challenge.
        report_path: Canonical Defender report destination.
        repository_root: Trusted repository boundary.

    Returns:
        A machine-readable inventory of the written report.

    Raises:
        OSError: If an input or output cannot be accessed.
        ValueError: If validation or output safety checks fail.
    """
    root = repository_root.resolve()
    report_relative = _relative_file(root, report_path, "Defender report output")
    if report_relative != _REPORT_OUTPUT:
        raise ValueError(f"Defender report output must be {_REPORT_OUTPUT}")
    report = build_defender_evidence(capture_path, handoff_path, root)
    destination = root / report_relative
    for part_index in range(1, len(destination.relative_to(root).parts)):
        ancestor = root.joinpath(*destination.relative_to(root).parts[:part_index])
        if ancestor.is_symlink():
            raise ValueError("Defender report output path contains a symlink")
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
        "report": report_relative,
        "sha256": sha256_file(destination),
    }


def validate_defender_evidence(
    capture_path: Path,
    handoff_path: Path,
    report_path: Path,
    contracts_directory: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Validate the upstream handoff and independently reproduce the report.

    Args:
        capture_path: Digest-bound Defender capture manifest.
        handoff_path: Modernization handoff selected for the challenge.
        report_path: Previously rendered Defender report.
        contracts_directory: Checked-in workshop contract directory.
        repository_root: Trusted repository boundary.

    Returns:
        A machine-readable validation result.

    Raises:
        OSError: If required evidence cannot be read.
        ValueError: If provenance or report comparison fails.
        jsonschema.ValidationError: If a document violates its schema.
    """
    root = repository_root.resolve()
    contracts = _validate_contracts_directory(root, contracts_directory)
    report_resolved = resolve_repository_file(
        root,
        _relative_file(root, report_path, "Defender report"),
    )
    validate_handoff(handoff_path, contracts, root)
    expected = build_defender_evidence(capture_path, handoff_path, root)
    actual = load_json_object(report_resolved)
    _validate_schema(
        _contract_file(root, contracts, "defender-evidence.schema.json"),
        actual,
    )
    if actual != expected:
        raise ValueError("Defender report differs from deterministic raw replay")
    return {
        "schemaVersion": _REPORT_VERSION,
        "report": _relative_file(root, report_resolved, "Defender report"),
        "sha256": sha256_file(report_resolved),
        "result": "passed",
    }


__all__ = [
    "build_defender_evidence",
    "validate_defender_evidence",
    "write_defender_evidence",
]
