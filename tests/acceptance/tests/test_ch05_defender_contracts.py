"""Executable contract and false-success tests for Challenge 5."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Callable

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
import pytest

from catalog_acceptance import defender_evidence
from catalog_acceptance.defender_evidence import (
    build_defender_evidence,
    validate_defender_evidence,
    write_defender_evidence,
)
from catalog_acceptance.defender_evidence_cli import render_main, validate_main
from catalog_acceptance.models.defender import DefenderDecision


ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "workshop/contracts"
FIXTURES = CONTRACTS / "fixtures/defender"
CAPTURE_EXAMPLE = CONTRACTS / "defender-evidence-capture.example.json"
REPORT_EXAMPLE = CONTRACTS / "defender-evidence.example.json"
HANDOFF_FIXTURE = FIXTURES / "handoff.json"


def _load(path: Path) -> dict[str, Any]:
    """Load one checked-in JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    """Write one deterministic JSON test document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    """Return one lowercase test-file digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate(schema_name: str, document: dict[str, Any]) -> None:
    """Validate one document against a checked-in schema."""
    schema = _load(CONTRACTS / schema_name)
    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(document)


def _copy_bundle(tmp_path: Path) -> Path:
    """Copy the representative Defender fixture bundle into a temporary root."""
    root = tmp_path / "repo"
    (root / "workshop").mkdir(parents=True)
    shutil.copytree(CONTRACTS, root / "workshop/contracts")
    (root / "workshop/defender").mkdir(parents=True)
    shutil.copy2(
        ROOT / "workshop/defender/lab-profile.json",
        root / "workshop/defender/lab-profile.json",
    )
    return root


def _update_reference_digest(value: Any, file: str, sha256: str) -> int:
    """Update every manifest reference to one mutated fixture."""
    updated = 0
    if isinstance(value, dict):
        if value.get("file") == file and "sha256" in value:
            value["sha256"] = sha256
            updated += 1
        for child in value.values():
            updated += _update_reference_digest(child, file, sha256)
    elif isinstance(value, list):
        for child in value:
            updated += _update_reference_digest(child, file, sha256)
    return updated


def _mutate_artifact(
    root: Path,
    relative: str,
    mutate: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    """Mutate one raw artifact and refresh its capture-manifest digest."""
    path = root / relative
    value = _load(path)
    mutate(value)
    _write(path, value)
    capture_path = root / "workshop/contracts/defender-evidence-capture.example.json"
    capture = _load(capture_path)
    assert _update_reference_digest(capture, relative, _sha256(path)) == 1
    _write(capture_path, capture)
    return capture


def _refresh_capture_digest(root: Path, relative: str) -> None:
    """Refresh one capture-manifest digest after a test edits an artifact."""
    artifact_path = root / relative
    capture_path = root / "workshop/contracts/defender-evidence-capture.example.json"
    capture = _load(capture_path)
    assert (
        _update_reference_digest(
            capture,
            relative,
            _sha256(artifact_path),
        )
        == 1
    )
    _write(capture_path, capture)


def _set_cleanup_inventory_queried_at(
    inventory: dict[str, Any],
    queried_at: str,
) -> None:
    """Set every independent cleanup-inventory observation time."""
    for producer_name in (
        "resourceGraph",
        "autoProvisioningSettings",
        "settings",
    ):
        inventory[producer_name]["request"]["queriedAt"] = queried_at


def _mutate_seed_artifact(
    root: Path,
    relative: str,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    """Mutate one seed input and refresh both levels of its digest chain."""
    path = root / relative
    value = _load(path)
    mutate(value)
    _write(path, value)

    snapshot_relative = (
        "workshop/contracts/fixtures/defender/seed-snapshot.json"
    )
    snapshot_path = root / snapshot_relative
    snapshot = _load(snapshot_path)
    assert _update_reference_digest(snapshot, relative, _sha256(path)) == 1
    _write(snapshot_path, snapshot)
    _refresh_capture_digest(root, snapshot_relative)


def _build(root: Path) -> dict[str, Any]:
    """Render the temporary representative bundle."""
    return build_defender_evidence(
        root / "workshop/contracts/defender-evidence-capture.example.json",
        root / "workshop/contracts/fixtures/defender/handoff.json",
        root,
    )


def test_defender_registry_and_examples_are_schema_valid() -> None:
    """Freeze every Defender registry, capture, report, profile, and cleanup schema."""
    registry = _load(CONTRACTS / "defender.json")
    _validate("defender.schema.json", registry)
    _validate(
        "defender-evidence-capture.schema.json",
        _load(CAPTURE_EXAMPLE),
    )
    _validate("defender-evidence.schema.json", _load(REPORT_EXAMPLE))
    _validate(
        "defender-lab-profile.schema.json",
        _load(ROOT / "workshop/defender/lab-profile.json"),
    )
    _validate(
        "defender-cleanup.schema.json",
        _load(FIXTURES / "cleanup-manifest.json"),
    )
    _validate(
        "defender-pricing-envelope.schema.json",
        _load(FIXTURES / "pricings-before.json"),
    )
    _validate(
        "defender-pricing-envelope.schema.json",
        _load(FIXTURES / "pricings.json"),
    )
    _validate(
        "defender-budget-envelope.schema.json",
        _load(FIXTURES / "budget.json"),
    )
    _validate(
        "defender-cleanup-inventory-envelope.schema.json",
        _load(FIXTURES / "cleanup-inventory-before.json"),
    )
    _validate(
        "defender-legacy-vm-coverage.schema.json",
        _load(FIXTURES / "legacy-vm-coverage.json"),
    )
    _validate(
        "defender-seed-snapshot.schema.json",
        _load(FIXTURES / "seed-snapshot.json"),
    )
    _validate(
        "defender-attack-path-envelope.schema.json",
        _load(FIXTURES / "attack-paths.json"),
    )
    Draft202012Validator.check_schema(
        _load(CONTRACTS / "defender-cost-query-envelope.schema.json")
    )

    plans = registry["foundation"]["requiredPricings"]
    assert [plan["name"] for plan in plans] == [
        "CloudPosture",
        "Containers",
        "SqlServers",
        "OpenSourceRelationalDatabases",
        "VirtualMachines",
    ]
    assert plans[0]["extensions"] == [
        {
            "name": "ContainerRegistriesVulnerabilityAssessments",
            "isEnabled": "True",
        }
    ]
    assert plans[1]["extensions"] == []
    assert plans[-1]["subPlan"] == "P2"
    assert plans[-1]["enforce"] == "True"
    assert registry["foundation"]["legacyVmCoverage"] == {
        "schema": (
            "workshop/contracts/defender-legacy-vm-coverage.schema.json"
        ),
        "apiVersion": "2024-11-01",
        "requiredWorkloads": ["dotnet", "java"],
        "pricingName": "VirtualMachines",
        "pricingSubPlan": "P2",
        "subscriptionPricingEnforce": "True",
    }
    assert registry["foundation"]["seedSnapshot"] == {
        "schema": "workshop/contracts/defender-seed-snapshot.schema.json",
        "requiredNonEmptySignals": [
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
        "attackPaths": "query-required-results-optional",
    }
    assert registry["foundation"]["budget"] == {
        "scope": "handoff-subscription",
        "apiVersion": "2023-11-01",
        "category": "Cost",
        "timeGrain": "Monthly",
        "maximumNotificationThreshold": 80,
        "notificationTargetRequired": True,
    }
    assert registry["evidence"]["gradedSignal"] == "query-attempt-and-provenance"
    assert registry["evidence"]["queryContracts"] == {
        "imageAssessment": {
            "scope": "handoff-container-registry",
            "method": "GET",
            "resourcePath": (
                "providers/Microsoft.Security/assessments/"
                "c0b7cfc6-3172-465a-b378-53c7ff2cc0d5/subAssessments"
            ),
            "apiVersion": "2019-01-01-preview",
        },
        "recommendations": {
            "scope": "handoff-subscription",
            "method": "GET",
            "resourcePath": "providers/Microsoft.Security/assessments",
            "apiVersion": "2020-01-01",
        },
        "secureScore": {
            "scope": "handoff-subscription",
            "method": "GET",
            "resourcePath": "providers/Microsoft.Security/secureScores",
            "apiVersion": "2020-01-01",
        },
        "mcsb": {
            "scope": "handoff-subscription",
            "method": "GET",
            "resourcePath": (
                "providers/Microsoft.Security/regulatoryComplianceStandards/"
                "Microsoft-cloud-security-benchmark/"
                "regulatoryComplianceControls"
            ),
            "apiVersion": "2019-01-01-preview",
        },
        "attackPaths": {
            "scope": "handoff-subscription",
            "method": "POST",
            "resourcePath": "providers/Microsoft.ResourceGraph/resources",
            "apiVersion": "2022-10-01",
            "queryTemplate": (
                "securityresources\n"
                '| where type == "microsoft.security/attackpaths"\n'
                '| where subscriptionId == "{subscriptionId}"'
            ),
            "envelopeSchema": (
                "workshop/contracts/defender-attack-path-envelope.schema.json"
            ),
            "completeResponseRequired": True,
            "graded": True,
        },
    }
    assert registry["cleanup"] == {
        "manifestSchemaVersion": "1.1.0",
        "requiresFacilitatorAuthorization": True,
        "priorPricingSnapshotRequired": True,
        "restorePriorPricingState": True,
        "restorePriorEnforceState": True,
        "verifyPriorPricingStateRestored": True,
        "postCleanupPricingSnapshotRequired": True,
        "priorCleanupInventoryRequired": True,
        "postCleanupInventoryRequired": True,
        "cleanupInventoryEnvelopeSchema": (
            "workshop/contracts/defender-cleanup-inventory-envelope.schema.json"
        ),
        "cleanupInventoryResourceTypes": [
            "microsoft.compute/virtualmachines/extensions",
            "microsoft.hybridcompute/machines/extensions",
            "microsoft.insights/datacollectionruleassociations",
            "microsoft.security/autoprovisioningsettings",
            "microsoft.security/settings",
            "microsoft.security/pricings",
            "microsoft.authorization/policyassignments",
        ],
        "cleanupInventoryProducers": {
            "resourceGraph": {
                "method": "POST",
                "operation": "subscription-defender-cleanup-inventory",
                "resourcePath": "providers/Microsoft.ResourceGraph/resources",
                "apiVersion": "2022-10-01",
                "tables": {
                    "Resources": [
                        "microsoft.compute/virtualmachines/extensions",
                        "microsoft.hybridcompute/machines/extensions",
                    ],
                    "InsightResources": [
                        "microsoft.insights/datacollectionruleassociations"
                    ],
                    "SecurityResources": ["microsoft.security/pricings"],
                    "PolicyResources": [
                        "microsoft.authorization/policyassignments"
                    ],
                },
            },
            "autoProvisioningSettings": {
                "method": "GET",
                "operation": (
                    "subscription-defender-auto-provisioning-settings"
                ),
                "resourcePath": (
                    "providers/Microsoft.Security/autoProvisioningSettings"
                ),
                "apiVersion": "2017-08-01-preview",
                "resourceType": (
                    "microsoft.security/autoprovisioningsettings"
                ),
            },
            "settings": {
                "method": "GET",
                "operation": "subscription-defender-settings",
                "resourcePath": "providers/Microsoft.Security/settings",
                "apiVersion": "2021-06-01",
                "resourceType": "microsoft.security/settings",
            },
        },
        "costQueryAfterRestoration": True,
        "costQueryEnvelopeSchema": (
            "workshop/contracts/defender-cost-query-envelope.schema.json"
        ),
        "costDataMayLag": True,
    }


def test_representative_capture_renders_exact_report() -> None:
    """Prove the sanitized raw bundle deterministically reproduces its report."""
    rendered = build_defender_evidence(CAPTURE_EXAMPLE, HANDOFF_FIXTURE, ROOT)
    assert rendered == _load(REPORT_EXAMPLE)
    assert rendered["result"] == "passed"
    assert rendered["securityContext"]["nonEmptyFindingsRequired"] is False
    assert (
        rendered["postureComparison"]["containerApp"]["runtimeProtectionClaim"]
        == "not-claimed-for-azure-container-apps"
    )


def test_renderer_rejects_missing_required_pricing(tmp_path: Path) -> None:
    """Reject a pricing capture that omits one plan required by the source plan."""
    root = _copy_bundle(tmp_path)

    def remove_containers(value: dict[str, Any]) -> None:
        value["response"]["value"] = [
            item
            for item in value["response"]["value"]
            if item["name"] != "Containers"
        ]

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/pricings.json",
        remove_containers,
    )
    with pytest.raises(ValueError, match="required Defender pricing is absent"):
        _build(root)


def test_virtual_machine_pricing_must_be_subscription_enforced(
    tmp_path: Path,
) -> None:
    """Reject P2 pricing that descendants can override below the subscription."""
    root = _copy_bundle(tmp_path)

    def disable_enforcement(value: dict[str, Any]) -> None:
        plan = next(
            item
            for item in value["response"]["value"]
            if item["name"] == "VirtualMachines"
        )
        plan["properties"]["enforce"] = "False"

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/pricings.json",
        disable_enforcement,
    )
    with pytest.raises(
        ValueError,
        match="VirtualMachines pricing enforce must be True",
    ):
        _build(root)


def test_legacy_vm_coverage_requires_both_workloads(tmp_path: Path) -> None:
    """Reject a coverage envelope that omits the retained Java VM."""
    root = _copy_bundle(tmp_path)

    def remove_java(value: dict[str, Any]) -> None:
        value["virtualMachines"] = [
            item
            for item in value["virtualMachines"]
            if item["workload"] != "java"
        ]

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/legacy-vm-coverage.json",
        remove_java,
    )
    with pytest.raises(JsonSchemaValidationError):
        _build(root)


def test_legacy_vm_coverage_binds_the_second_vm_identity(
    tmp_path: Path,
) -> None:
    """Reject a Java coverage response for any VM but the retained sibling."""
    root = _copy_bundle(tmp_path)

    def replace_java_identity(value: dict[str, Any]) -> None:
        java = next(
            item
            for item in value["virtualMachines"]
            if item["workload"] == "java"
        )
        java["response"]["body"]["id"] += "-other"

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/legacy-vm-coverage.json",
        replace_java_identity,
    )
    with pytest.raises(
        ValueError,
        match="does not prove the retained java VM",
    ):
        _build(root)


def test_seed_recommendations_cover_every_challenge_resource(
    tmp_path: Path,
) -> None:
    """Reject a pre-warmed recommendation set without database context."""
    root = _copy_bundle(tmp_path)

    def remove_database(value: dict[str, Any]) -> None:
        value["response"]["value"] = [
            item
            for item in value["response"]["value"]
            if "/providers/Microsoft.Sql/" not in item["properties"][
                "resourceDetails"
            ]["id"]
        ]

    _mutate_seed_artifact(
        root,
        "workshop/contracts/fixtures/defender/seed-recommendations.json",
        remove_database,
    )
    with pytest.raises(
        ValueError,
        match="omit required resource context: database",
    ):
        _build(root)


def test_seed_recommendations_require_an_unhealthy_finding(
    tmp_path: Path,
) -> None:
    """Reject a pre-warmed snapshot with no deterministic unhealthy finding."""
    root = _copy_bundle(tmp_path)

    def make_all_healthy(value: dict[str, Any]) -> None:
        for item in value["response"]["value"]:
            item["properties"]["status"]["code"] = "Healthy"

    _mutate_seed_artifact(
        root,
        "workshop/contracts/fixtures/defender/seed-recommendations.json",
        make_all_healthy,
    )
    with pytest.raises(
        ValueError,
        match="lack the deterministic unhealthy finding",
    ):
        _build(root)


@pytest.mark.parametrize(
    ("fixture_name", "expected_error"),
    [
        ("seed-secure-score.json", "lacks the subscription Secure Score"),
        ("seed-mcsb.json", "lacks MCSB control context"),
        (
            "seed-image-assessment.json",
            "completed image assessment has no handoff digest result",
        ),
    ],
)
def test_seed_snapshot_requires_each_nonempty_signal(
    tmp_path: Path,
    fixture_name: str,
    expected_error: str,
) -> None:
    """Reject an empty mandatory pre-warmed signal."""
    root = _copy_bundle(tmp_path)

    _mutate_seed_artifact(
        root,
        f"workshop/contracts/fixtures/defender/{fixture_name}",
        lambda value: value["response"].update(value=[]),
    )
    with pytest.raises(ValueError, match=expected_error):
        _build(root)


def test_seed_snapshot_must_precede_current_query_evidence(
    tmp_path: Path,
) -> None:
    """Reject a purported seed snapshot captured after current live queries."""
    root = _copy_bundle(tmp_path)

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/seed-snapshot.json",
        lambda value: value.update(capturedAt="2025-01-01T09:54:00Z"),
    )
    with pytest.raises(
        ValueError,
        match="chronology does not prove pre-warmed Defender context",
    ):
        _build(root)


def test_seed_queries_must_follow_pricing_enablement(tmp_path: Path) -> None:
    """Reject inner seed evidence captured before Defender was enabled."""
    root = _copy_bundle(tmp_path)
    seed_relative = (
        "workshop/contracts/fixtures/defender/seed-recommendations.json"
    )
    _mutate_seed_artifact(
        root,
        seed_relative,
        lambda value: value["request"].update(
            queriedAt="2025-01-01T09:00:00Z"
        ),
    )
    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/seed-snapshot.json",
        lambda value: value["recommendations"].update(
            queriedAt="2025-01-01T09:00:00Z"
        ),
    )
    with pytest.raises(
        ValueError,
        match="chronology does not prove pre-warmed Defender context",
    ):
        _build(root)


def test_seed_snapshot_cannot_alias_current_query_evidence(
    tmp_path: Path,
) -> None:
    """Reject reuse of a current asynchronous query as deterministic seed data."""
    root = _copy_bundle(tmp_path)
    capture = _load(
        root / "workshop/contracts/defender-evidence-capture.example.json"
    )
    current = capture["securityContext"]["recommendations"]

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/seed-snapshot.json",
        lambda value: value.update(recommendations=current),
    )
    with pytest.raises(
        ValueError,
        match="must use distinct artifacts from current query evidence",
    ):
        _build(root)


def test_empty_query_response_cannot_be_relabelled(tmp_path: Path) -> None:
    """Reject an empty response whose bound request names another operation."""
    root = _copy_bundle(tmp_path)

    def relabel_request(value: dict[str, Any]) -> None:
        value["request"]["operation"] = "subscription-secure-score"

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/recommendations.json",
        relabel_request,
    )
    with pytest.raises(ValueError, match="raw request provenance differs"):
        _build(root)


@pytest.mark.parametrize(
    "fixture_name",
    ["image-assessment.json", "mcsb.json"],
)
def test_query_request_is_bound_to_the_exact_resource_path(
    tmp_path: Path,
    fixture_name: str,
) -> None:
    """Reject a valid operation and scope aimed at another nested resource."""
    root = _copy_bundle(tmp_path)

    _mutate_artifact(
        root,
        f"workshop/contracts/fixtures/defender/{fixture_name}",
        lambda value: value["request"].update(
            resourcePath=f"{value['request']['resourcePath']}-other"
        ),
    )
    with pytest.raises(ValueError, match="raw request provenance differs"):
        _build(root)


def test_image_response_is_bound_to_the_requested_assessment(
    tmp_path: Path,
) -> None:
    """Reject a matching digest returned beneath another assessment key."""
    root = _copy_bundle(tmp_path)

    def change_assessment(value: dict[str, Any]) -> None:
        value["response"]["value"][0]["id"] = value["response"]["value"][0][
            "id"
        ].replace(
            "c0b7cfc6-3172-465a-b378-53c7ff2cc0d5",
            "11111111-1111-1111-1111-111111111111",
        )

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/image-assessment.json",
        change_assessment,
    )
    with pytest.raises(ValueError, match="no handoff digest result"):
        _build(root)


def test_mcsb_response_is_bound_to_the_requested_standard(
    tmp_path: Path,
) -> None:
    """Reject controls returned beneath a different compliance standard."""
    root = _copy_bundle(tmp_path)
    seed = _load(
        root / "workshop/contracts/fixtures/defender/seed-mcsb.json"
    )

    def inject_other_standard(value: dict[str, Any]) -> None:
        value["response"] = seed["response"]
        value["response"]["value"][0]["id"] = value["response"]["value"][0][
            "id"
        ].replace(
            "Microsoft-cloud-security-benchmark",
            "PCI-DSS-3.2",
        )

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/mcsb.json",
        inject_other_standard,
    )
    with pytest.raises(
        ValueError,
        match="outside the requested MCSB standard",
    ):
        _build(root)


def test_renderer_rejects_duplicate_registry_assessment_extension(
    tmp_path: Path,
) -> None:
    """Reject duplicate enabled copies of the registry assessment extension."""
    root = _copy_bundle(tmp_path)

    def duplicate_extension(value: dict[str, Any]) -> None:
        cloud_posture = next(
            item
            for item in value["response"]["value"]
            if item["name"] == "CloudPosture"
        )
        cloud_posture["properties"]["extensions"].append(
            {
                "name": "ContainerRegistriesVulnerabilityAssessments",
                "isEnabled": "True",
            }
        )

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/pricings.json",
        duplicate_extension,
    )
    with pytest.raises(ValueError, match="exactly once"):
        _build(root)


def test_registry_assessment_extension_is_owned_only_by_cloud_posture(
    tmp_path: Path,
) -> None:
    """Reject duplicate registry-assessment ownership under another plan."""
    root = _copy_bundle(tmp_path)

    def add_extension_to_containers(value: dict[str, Any]) -> None:
        containers = next(
            item
            for item in value["response"]["value"]
            if item["name"] == "Containers"
        )
        containers["properties"]["extensions"].append(
            {
                "name": "ContainerRegistriesVulnerabilityAssessments",
                "isEnabled": "True",
            }
        )

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/pricings.json",
        add_extension_to_containers,
    )
    with pytest.raises(ValueError, match="only under CloudPosture"):
        _build(root)


def test_renderer_rejects_mismatched_effective_nsg_association(
    tmp_path: Path,
) -> None:
    """Reject effective rules associated with a NIC other than the VM NIC."""
    root = _copy_bundle(tmp_path)

    def swap_association(value: dict[str, Any]) -> None:
        association = value["networkInterfaces"][0][
            "effectiveNetworkSecurityGroups"
        ]["value"][0]["association"]["networkInterface"]
        association["id"] += "-other"

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/vm-after.json",
        swap_association,
    )
    with pytest.raises(ValueError, match="association is not attached"):
        _build(root)


def test_renderer_rejects_acr_admin_authentication(tmp_path: Path) -> None:
    """Reject an after-state that leaves the ACR administrator enabled."""
    root = _copy_bundle(tmp_path)
    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/acr-after.json",
        lambda value: value["properties"].update(adminUserEnabled=True),
    )
    with pytest.raises(ValueError, match="ACR admin authentication must be disabled"):
        _build(root)


def test_renderer_requires_acr_scoped_pull_role(tmp_path: Path) -> None:
    """Reject identity-based registry configuration without AcrPull evidence."""
    root = _copy_bundle(tmp_path)
    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/acr-role-assignments.json",
        lambda value: value.update(value=[]),
    )
    with pytest.raises(ValueError, match="exactly one captured ACR role"):
        _build(root)


def test_renderer_rejects_paginated_acr_role_assignments(tmp_path: Path) -> None:
    """Reject an incomplete first page of registry role assignments."""
    root = _copy_bundle(tmp_path)
    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/acr-role-assignments.json",
        lambda value: value.update(
            nextLink=(
                "https://management.azure.com/providers/"
                "Microsoft.Authorization/roleAssignments?$skipToken=next"
            )
        ),
    )
    with pytest.raises(ValueError, match="must not be paginated"):
        _build(root)


def test_renderer_rejects_mutable_or_password_registry_pull(tmp_path: Path) -> None:
    """Reject a mutable image reference and any non-identity pull configuration."""
    root = _copy_bundle(tmp_path)

    def weaken_container_app(value: dict[str, Any]) -> None:
        value["properties"]["template"]["containers"][0][
            "image"
        ] = "acrexample.azurecr.io/catalog-dotnet:latest"
        value["properties"]["configuration"]["registries"][0].update(
            username="catalog",
            passwordSecretRef="acr-password",
        )

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/container-app-after.json",
        weaken_container_app,
    )
    with pytest.raises(ValueError, match="registry pull must use only"):
        _build(root)


def test_renderer_rejects_an_extra_handoff_registry_credential(
    tmp_path: Path,
) -> None:
    """Reject a second entry that bypasses the approved identity for the ACR."""
    root = _copy_bundle(tmp_path)

    def add_password_entry(value: dict[str, Any]) -> None:
        value["properties"]["configuration"]["registries"].append(
            {
                "server": "ACREXAMPLE.AZURECR.IO",
                "username": "catalog",
                "passwordSecretRef": "acr-password",
            }
        )

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/container-app-after.json",
        add_password_entry,
    )
    with pytest.raises(ValueError, match="exactly one entry"):
        _build(root)


def test_renderer_requires_exception_for_residual_database_access(
    tmp_path: Path,
) -> None:
    """Reject an observed public database after-state labeled as remediated."""
    root = _copy_bundle(tmp_path)
    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/database-after.json",
        lambda value: value["properties"].update(publicNetworkAccess="Enabled"),
    )
    with pytest.raises(ValueError, match="must be documented-exception"):
        _build(root)


def test_renderer_requires_exception_for_residual_vm_exposure(
    tmp_path: Path,
) -> None:
    """Reject broad management ingress labeled as remediated."""
    root = _copy_bundle(tmp_path)

    def expose_vm(value: dict[str, Any]) -> None:
        rule = value["networkInterfaces"][0]["effectiveNetworkSecurityGroups"][
            "value"
        ][0]["securityRules"][0]
        rule["sourceAddressPrefix"] = "*"

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/vm-after.json",
        expose_vm,
    )
    with pytest.raises(ValueError, match="must be documented-exception"):
        _build(root)


def test_renderer_rejects_unbound_or_empty_vm_network_capture(
    tmp_path: Path,
) -> None:
    """Reject VM exposure evidence that omits attached effective NSG state."""
    root = _copy_bundle(tmp_path)
    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/vm-after.json",
        lambda value: value.update(networkInterfaces=[]),
    )
    with pytest.raises(ValueError, match="do not match the VM-attached NICs"):
        _build(root)


def test_jit_policy_must_cover_the_public_management_port(
    tmp_path: Path,
) -> None:
    """Reject public SSH when the bound JIT policy covers only RDP."""
    root = _copy_bundle(tmp_path)

    def expose_ssh_with_rdp_jit(value: dict[str, Any]) -> None:
        rule = value["networkInterfaces"][0]["effectiveNetworkSecurityGroups"][
            "value"
        ][0]["securityRules"][0]
        rule["sourceAddressPrefix"] = "*"
        rule["destinationPortRange"] = "22"
        vm_id = value["vm"]["id"]
        value["jitPolicy"] = {
            "id": (
                "/subscriptions/00000000-0000-0000-0000-000000000000/"
                "resourceGroups/rg-mh-source-example/providers/"
                "Microsoft.Security/locations/swedencentral/"
                "jitNetworkAccessPolicies/default"
            ),
            "type": "Microsoft.Security/locations/jitNetworkAccessPolicies",
            "properties": {
                "virtualMachines": [
                    {
                        "id": vm_id,
                        "ports": [{"number": 3389}],
                    }
                ]
            },
        }

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/vm-after.json",
        expose_ssh_with_rdp_jit,
    )
    with pytest.raises(ValueError, match="must be documented-exception"):
        _build(root)


def test_bound_jit_policy_can_cover_the_public_management_port(
    tmp_path: Path,
) -> None:
    """Accept public RDP only when the bound JIT policy covers RDP."""
    root = _copy_bundle(tmp_path)

    def expose_rdp_with_rdp_jit(value: dict[str, Any]) -> None:
        rule = value["networkInterfaces"][0]["effectiveNetworkSecurityGroups"][
            "value"
        ][0]["securityRules"][0]
        rule["sourceAddressPrefix"] = "*"
        value["jitPolicy"] = {
            "id": (
                "/subscriptions/00000000-0000-0000-0000-000000000000/"
                "resourceGroups/rg-mh-source-example/providers/"
                "Microsoft.Security/locations/swedencentral/"
                "jitNetworkAccessPolicies/default"
            ),
            "type": "Microsoft.Security/locations/jitNetworkAccessPolicies",
            "properties": {
                "virtualMachines": [
                    {
                        "id": value["vm"]["id"],
                        "ports": [{"number": 3389}],
                    }
                ]
            },
        }

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/vm-after.json",
        expose_rdp_with_rdp_jit,
    )
    report = _build(root)
    assert report["controls"]["legacyVm"]["afterState"] == "segmented-or-jit"


def test_jit_evidence_must_be_a_bound_defender_policy(tmp_path: Path) -> None:
    """Reject a lookalike object that is not a Defender JIT policy resource."""
    root = _copy_bundle(tmp_path)

    def add_fake_jit(value: dict[str, Any]) -> None:
        value["jitPolicy"] = {
            "id": (
                "/subscriptions/00000000-0000-0000-0000-000000000000/"
                "resourceGroups/rg-mh-source-example/providers/"
                "Microsoft.Security/locations/swedencentral/"
                "jitNetworkAccessPolicies/default"
            ),
            "type": "Microsoft.Security/assessments",
            "properties": {
                "virtualMachines": [
                    {
                        "id": value["vm"]["id"],
                        "ports": [{"number": 3389}],
                    }
                ]
            },
        }

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/vm-after.json",
        add_fake_jit,
    )
    with pytest.raises(ValueError, match="not a bound Defender JIT policy"):
        _build(root)


def test_jit_policy_id_must_use_the_exact_arm_shape(tmp_path: Path) -> None:
    """Reject a typed JIT object with extra ARM path segments."""
    root = _copy_bundle(tmp_path)

    def add_malformed_jit(value: dict[str, Any]) -> None:
        value["jitPolicy"] = {
            "id": (
                "/subscriptions/00000000-0000-0000-0000-000000000000/"
                "resourceGroups/rg-mh-source-example/providers/"
                "Microsoft.Security/locations/swedencentral/extra/"
                "jitNetworkAccessPolicies/default"
            ),
            "type": "Microsoft.Security/locations/jitNetworkAccessPolicies",
            "properties": {
                "virtualMachines": [
                    {
                        "id": value["vm"]["id"],
                        "ports": [{"number": 3389}],
                    }
                ]
            },
        }

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/vm-after.json",
        add_malformed_jit,
    )
    with pytest.raises(ValueError, match="not a bound Defender JIT policy"):
        _build(root)


def test_budget_requires_an_early_notification_target(tmp_path: Path) -> None:
    """Reject a real budget whose only notification cannot alert anyone."""
    root = _copy_bundle(tmp_path)

    def remove_notification_targets(value: dict[str, Any]) -> None:
        notification = next(
            iter(value["response"]["properties"]["notifications"].values())
        )
        notification["contactEmails"] = []
        notification["contactGroups"] = []
        notification["contactRoles"] = []

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/budget.json",
        remove_notification_targets,
    )
    with pytest.raises(ValueError, match="notification at or below 80 percent"):
        _build(root)


def test_budget_is_bound_to_the_workshop_subscription(tmp_path: Path) -> None:
    """Reject a budget query captured from another subscription."""
    root = _copy_bundle(tmp_path)

    def change_budget_scope(value: dict[str, Any]) -> None:
        value["request"]["scopeResourceId"] = (
            "/subscriptions/11111111-1111-1111-1111-111111111111"
        )

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/budget.json",
        change_budget_scope,
    )
    with pytest.raises(ValueError, match="frozen subscription contract"):
        _build(root)


def test_all_protected_resources_share_the_defender_subscription(
    tmp_path: Path,
) -> None:
    """Reject a source VM that is outside the proven pricing subscription."""
    root = _copy_bundle(tmp_path)

    def move_vm_to_another_subscription(value: dict[str, Any]) -> None:
        value["network"]["migrationSourceVmResourceId"] = value["network"][
            "migrationSourceVmResourceId"
        ].replace(
            "00000000-0000-0000-0000-000000000000",
            "11111111-1111-1111-1111-111111111111",
        )

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/target-output.json",
        move_vm_to_another_subscription,
    )
    with pytest.raises(ValueError, match="protected resources: legacy VM"):
        _build(root)


def test_pending_image_assessment_does_not_false_fail(tmp_path: Path) -> None:
    """Allow an empty asynchronous image query only when status is pending."""
    root = _copy_bundle(tmp_path)
    capture = _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/image-assessment.json",
        lambda value: value["response"].update(value=[]),
    )
    capture["imageAssessment"]["status"] = "pending"
    capture_path = root / "workshop/contracts/defender-evidence-capture.example.json"
    _write(capture_path, capture)
    report = _build(root)
    assert report["imageAssessment"]["status"] == "pending"
    assert report["imageAssessment"]["findingCount"] is None

    capture["imageAssessment"]["status"] = "completed"
    _write(capture_path, capture)
    with pytest.raises(ValueError, match="no handoff digest result"):
        _build(root)


def test_completed_image_assessment_requires_a_structured_acr_record(
    tmp_path: Path,
) -> None:
    """Reject a free-text digest that impersonates an image subassessment."""
    root = _copy_bundle(tmp_path)
    digest = (
        "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    )

    def replace_with_free_text(value: dict[str, Any]) -> None:
        value["response"]["value"] = [{"note": f"scanned {digest}"}]

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/image-assessment.json",
        replace_with_free_text,
    )
    with pytest.raises(ValueError, match="no handoff digest result"):
        _build(root)


def test_attack_path_query_is_required_but_empty_results_are_accepted(
    tmp_path: Path,
) -> None:
    """Require provenance for attack-path inspection without requiring a finding."""
    root = _copy_bundle(tmp_path)
    report = _build(root)
    assert report["securityContext"]["attackPathsQueried"] is True
    assert report["securityContext"]["attackPathCount"] == 0

    capture_path = root / "workshop/contracts/defender-evidence-capture.example.json"
    capture = _load(capture_path)
    del capture["securityContext"]["attackPaths"]
    _write(capture_path, capture)
    with pytest.raises(
        JsonSchemaValidationError,
        match="'attackPaths' is a required property",
    ):
        _build(root)


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ("query", "request differs from the contract"),
        ("subscription", "request differs from the contract"),
        ("count", "response is incomplete"),
        ("resource", "resource outside the subscription"),
    ],
)
def test_attack_path_arg_query_rejects_false_success(
    tmp_path: Path,
    mutation: str,
    expected_error: str,
) -> None:
    """Reject malformed, incomplete, or out-of-scope attack-path ARG evidence."""
    root = _copy_bundle(tmp_path)

    def mutate_attack_paths(value: dict[str, Any]) -> None:
        if mutation == "query":
            value["request"]["body"]["query"] += " "
        elif mutation == "subscription":
            value["request"]["body"]["subscriptions"] = [
                "11111111-1111-1111-1111-111111111111"
            ]
        elif mutation == "count":
            value["response"]["totalRecords"] = 1
        else:
            value["response"].update(
                totalRecords=1,
                count=1,
                data=[
                    {
                        "id": (
                            "/subscriptions/"
                            "11111111-1111-1111-1111-111111111111/"
                            "providers/Microsoft.Security/attackPaths/example"
                        ),
                        "name": "example",
                        "type": "microsoft.security/attackpaths",
                        "subscriptionId": (
                            "11111111-1111-1111-1111-111111111111"
                        ),
                        "properties": {},
                    }
                ],
            )

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/attack-paths.json",
        mutate_attack_paths,
    )
    with pytest.raises(ValueError, match=expected_error):
        _build(root)


def test_attack_path_arg_uses_complete_resource_graph_shape() -> None:
    """Freeze Resource Graph truncation and pagination failure semantics."""
    fixture = _load(FIXTURES / "attack-paths.json")
    assert fixture["response"]["resultTruncated"] == "false"
    for field, value in (
        ("resultTruncated", False),
        ("$skipToken", "next-page"),
    ):
        invalid = json.loads(json.dumps(fixture))
        invalid["response"][field] = value
        with pytest.raises(JsonSchemaValidationError):
            _validate("defender-attack-path-envelope.schema.json", invalid)


def test_seed_snapshot_must_precede_current_attack_path_query(
    tmp_path: Path,
) -> None:
    """Reject current attack-path evidence that is not later than the seed."""
    root = _copy_bundle(tmp_path)
    capture = _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/attack-paths.json",
        lambda value: value["request"].update(
            queriedAt="2025-01-01T09:34:00Z"
        ),
    )
    capture["securityContext"]["attackPaths"]["queriedAt"] = (
        "2025-01-01T09:34:00Z"
    )
    _write(
        root / "workshop/contracts/defender-evidence-capture.example.json",
        capture,
    )
    with pytest.raises(
        ValueError,
        match="chronology does not prove pre-warmed Defender context",
    ):
        _build(root)


def test_context_queries_are_bound_to_frozen_scope(tmp_path: Path) -> None:
    """Reject an empty context response declared against another scope."""
    root = _copy_bundle(tmp_path)
    capture_path = root / "workshop/contracts/defender-evidence-capture.example.json"
    capture = _load(capture_path)
    capture["securityContext"]["secureScore"]["scopeResourceId"] += (
        "/resourceGroups/rg-mh-example"
    )
    _write(capture_path, capture)
    with pytest.raises(ValueError, match="secureScore query scope differs"):
        _build(root)


def test_raw_capture_digest_tampering_is_rejected(tmp_path: Path) -> None:
    """Reject edited ARM state when its capture-manifest digest is unchanged."""
    root = _copy_bundle(tmp_path)
    path = root / "workshop/contracts/fixtures/defender/acr-after.json"
    value = _load(path)
    value["properties"]["provisioningState"] = "Updating"
    _write(path, value)
    with pytest.raises(ValueError, match="artifact digest mismatch"):
        _build(root)


def test_capture_rejects_noncanonical_artifact_alias(tmp_path: Path) -> None:
    """Prevent one artifact from satisfying distinct roles through a path alias."""
    root = _copy_bundle(tmp_path)
    capture_path = (
        root / "workshop/contracts/defender-evidence-capture.example.json"
    )
    capture = _load(capture_path)
    capture["resources"]["containerRegistry"]["after"] = {
        **capture["resources"]["containerRegistry"]["before"],
        "file": "workshop/contracts/fixtures/defender/./acr-before.json",
    }
    _write(capture_path, capture)

    with pytest.raises(JsonSchemaValidationError):
        _build(root)


def test_postgresql_database_parent_uses_family_specific_resource() -> None:
    """Apply the database control to a PostgreSQL server, not its database child."""
    handoff = {
        "database": {
            "family": "postgresql-flexible",
            "resourceId": (
                "/subscriptions/00000000-0000-0000-0000-000000000000/"
                "resourceGroups/rg-mh-java-example/providers/"
                "Microsoft.DBforPostgreSQL/flexibleServers/"
                "psql-mh-java-example/databases/catalog"
            ),
        }
    }
    decision = DefenderDecision.model_validate(
        {
            "disposition": "remediated",
            "justification": None,
            "compensatingControls": [],
        }
    )
    result = defender_evidence._parse_database_control(
        _load(FIXTURES / "database-postgresql-before.json"),
        _load(FIXTURES / "database-postgresql-after.json"),
        handoff,
        decision,
    )
    assert result["resourceId"].endswith(
        "/Microsoft.DBforPostgreSQL/flexibleServers/psql-mh-java-example"
    )
    assert result["afterState"] == "public-network-disabled"


def test_writer_and_renderer_cli_use_only_canonical_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Write the canonical report and reject a second arbitrary destination."""
    root = _copy_bundle(tmp_path)
    capture = root / "workshop/contracts/defender-evidence-capture.example.json"
    handoff = root / "workshop/contracts/fixtures/defender/handoff.json"
    report = root / "evidence/defender-report.json"
    result = write_defender_evidence(capture, handoff, report, root)
    assert result["report"] == "evidence/defender-report.json"
    assert _load(report)["result"] == "passed"
    assert (
        render_main(
            [
                "--capture",
                "workshop/contracts/defender-evidence-capture.example.json",
                "--handoff",
                "workshop/contracts/fixtures/defender/handoff.json",
                "--output",
                "evidence/defender-report.json",
                "--repository-root",
                str(root),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "passed"
    with pytest.raises(ValueError, match="must be evidence/defender-report.json"):
        write_defender_evidence(
            capture,
            handoff,
            root / "evidence/alternate.json",
            root,
        )


@pytest.mark.parametrize(
    "entrypoint",
    [render_main, validate_main],
    ids=["render", "validate"],
)
def test_cli_argument_failures_are_machine_readable(
    entrypoint: Callable[[list[str]], int],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Return stable JSON rather than argparse text for invalid invocations."""
    assert entrypoint([]) == 1
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["status"] == "failed"
    assert result["error"].startswith("invalid arguments:")
    assert captured.err == ""


def test_validator_replays_raw_state_instead_of_trusting_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject a schema-valid report edit after deterministic rendering."""
    root = _copy_bundle(tmp_path)
    capture = root / "workshop/contracts/defender-evidence-capture.example.json"
    handoff = root / "workshop/contracts/fixtures/defender/handoff.json"
    report_path = root / "evidence/defender-report.json"
    _write(report_path, _build(root))
    monkeypatch.setattr(defender_evidence, "validate_handoff", lambda *args: {})
    result = validate_defender_evidence(
        capture,
        handoff,
        report_path,
        root / "workshop/contracts",
        root,
    )
    assert result["result"] == "passed"

    report = _load(report_path)
    report["foundation"]["facilitatorChangeApproval"] = "edited-approval"
    _write(report_path, report)
    with pytest.raises(ValueError, match="differs from deterministic raw replay"):
        validate_defender_evidence(
            capture,
            handoff,
            report_path,
            root / "workshop/contracts",
            root,
        )


def test_cleanup_prior_state_must_match_immutable_snapshot(
    tmp_path: Path,
) -> None:
    """Reject cleanup declarations forged independently of the prior snapshot."""
    root = _copy_bundle(tmp_path)

    def forge_prior_tier(value: dict[str, Any]) -> None:
        value["plans"][0]["priorPricingTier"] = "Standard"

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/cleanup-manifest.json",
        forge_prior_tier,
    )
    with pytest.raises(ValueError, match="prior state differs from its snapshot"):
        _build(root)


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ("query", "query differs from the cleanup inventory contract"),
        ("scope", "query differs from the cleanup inventory contract"),
        ("count", "Resource Graph response is incomplete"),
        ("pagination", "Resource Graph response is incomplete"),
        ("chronology", "must precede paid-plan enablement"),
        ("resource-subscription", "outside its subscription or type boundary"),
        ("arm-path", "query differs from the cleanup inventory contract"),
        ("arm-pagination", "response is incomplete"),
        ("arm-resource-subscription", "outside its subscription or type boundary"),
        ("arm-response-path", "response ID differs from the requested collection"),
        ("arm-state", "invalid state shape"),
    ],
)
def test_cleanup_inventory_rejects_false_success(
    tmp_path: Path,
    mutation: str,
    expected_error: str,
) -> None:
    """Reject malformed, incomplete, late, or out-of-scope cleanup inventories."""
    root = _copy_bundle(tmp_path)
    fixture_root = root / "workshop/contracts/fixtures/defender"
    inventory_path = fixture_root / "cleanup-inventory-before.json"
    inventory = _load(inventory_path)
    if mutation == "query":
        inventory["resourceGraph"]["request"]["body"]["query"] += " "
    elif mutation == "scope":
        inventory["resourceGraph"]["request"]["body"]["subscriptions"] = [
            "11111111-1111-1111-1111-111111111111"
        ]
    elif mutation == "count":
        inventory["resourceGraph"]["response"]["count"] -= 1
    elif mutation == "pagination":
        inventory["resourceGraph"]["response"]["$skipToken"] = "next-page"
    elif mutation == "chronology":
        inventory["settings"]["request"]["queriedAt"] = "2025-01-01T10:01:00Z"
    elif mutation == "resource-subscription":
        inventory["resourceGraph"]["response"]["data"][0]["id"] = inventory[
            "resourceGraph"
        ]["response"]["data"][0]["id"].replace(
            "00000000-0000-0000-0000-000000000000",
            "11111111-1111-1111-1111-111111111111",
        )
    elif mutation == "arm-path":
        inventory["autoProvisioningSettings"]["request"]["resourcePath"] += "/default"
    elif mutation == "arm-pagination":
        inventory["autoProvisioningSettings"]["response"]["nextLink"] = (
            "https://management.azure.com/next-page"
        )
    elif mutation == "arm-resource-subscription":
        inventory["settings"]["response"]["value"][0]["id"] = inventory[
            "settings"
        ]["response"]["value"][0]["id"].replace(
            "00000000-0000-0000-0000-000000000000",
            "11111111-1111-1111-1111-111111111111",
        )
    elif mutation == "arm-response-path":
        inventory["autoProvisioningSettings"]["response"]["value"][0][
            "id"
        ] = inventory["autoProvisioningSettings"]["response"]["value"][0][
            "id"
        ].replace(
            "Microsoft.Security/autoProvisioningSettings",
            "Microsoft.Security/settings",
        )
    else:
        inventory["autoProvisioningSettings"]["response"]["value"][0][
            "properties"
        ]["autoProvision"] = "Invalid"
    _write(inventory_path, inventory)

    cleanup_path = fixture_root / "cleanup-manifest.json"
    cleanup = _load(cleanup_path)
    cleanup["priorCleanupInventory"]["sha256"] = _sha256(inventory_path)
    _write(cleanup_path, cleanup)
    _refresh_capture_digest(
        root,
        "workshop/contracts/fixtures/defender/cleanup-manifest.json",
    )

    with pytest.raises(ValueError, match=expected_error):
        _build(root)


def test_cleanup_inventory_rejects_unbounded_resource_type(
    tmp_path: Path,
) -> None:
    """Reject cleanup inventory entries outside the frozen resource-type set."""
    root = _copy_bundle(tmp_path)
    fixture_root = root / "workshop/contracts/fixtures/defender"
    inventory_path = fixture_root / "cleanup-inventory-before.json"
    inventory = _load(inventory_path)
    inventory["resourceGraph"]["response"]["data"][0]["type"] = (
        "microsoft.resources/deployments"
    )
    _write(inventory_path, inventory)

    cleanup_path = fixture_root / "cleanup-manifest.json"
    cleanup = _load(cleanup_path)
    cleanup["priorCleanupInventory"]["sha256"] = _sha256(inventory_path)
    _write(cleanup_path, cleanup)
    _refresh_capture_digest(
        root,
        "workshop/contracts/fixtures/defender/cleanup-manifest.json",
    )

    with pytest.raises(
        ValueError,
        match="outside its subscription or type boundary",
    ):
        _build(root)


def test_cleanup_inventory_uses_resource_graph_enum_shape() -> None:
    """Freeze the 2022-10-01 REST API string enum for truncation state."""
    inventory = _load(FIXTURES / "cleanup-inventory-before.json")
    assert inventory["resourceGraph"]["response"]["resultTruncated"] == "false"
    invalid = json.loads(json.dumps(inventory))
    invalid["resourceGraph"]["response"]["resultTruncated"] = False
    with pytest.raises(JsonSchemaValidationError):
        _validate("defender-cleanup-inventory-envelope.schema.json", invalid)


def test_cleanup_inventory_requires_the_resource_graph_endpoint() -> None:
    """Reject an ARG-shaped response not bound to the Resource Graph endpoint."""
    inventory = _load(FIXTURES / "cleanup-inventory-before.json")
    inventory["resourceGraph"]["request"]["resourcePath"] += "/wrong"
    with pytest.raises(JsonSchemaValidationError):
        _validate("defender-cleanup-inventory-envelope.schema.json", inventory)


def test_cleanup_inventory_maps_each_type_to_a_truthful_producer() -> None:
    """Freeze the authoritative ARG tables and bounded ARM list producers."""
    registry = _load(CONTRACTS / "defender.json")
    inventory = _load(FIXTURES / "cleanup-inventory-before.json")
    producers = registry["cleanup"]["cleanupInventoryProducers"]
    tables = producers["resourceGraph"]["tables"]
    assert tables == {
        "Resources": [
            "microsoft.compute/virtualmachines/extensions",
            "microsoft.hybridcompute/machines/extensions",
        ],
        "InsightResources": [
            "microsoft.insights/datacollectionruleassociations"
        ],
        "SecurityResources": ["microsoft.security/pricings"],
        "PolicyResources": ["microsoft.authorization/policyassignments"],
    }
    query = inventory["resourceGraph"]["request"]["body"]["query"]
    assert query.startswith(
        "union Resources, InsightResources, SecurityResources, PolicyResources "
    )
    assert (
        "| project id, name, type, properties, identity, location "
        "| order by id asc"
    ) in query
    assert "microsoft.security/autoprovisioningsettings" not in query
    assert "microsoft.security/settings" not in query
    assert (
        inventory["autoProvisioningSettings"]["request"]["resourcePath"]
        == producers["autoProvisioningSettings"]["resourcePath"]
    )
    assert (
        inventory["settings"]["request"]["resourcePath"]
        == producers["settings"]["resourcePath"]
    )
    produced_types = {
        resource_type
        for resource_types in tables.values()
        for resource_type in resource_types
    } | {
        producers["autoProvisioningSettings"]["resourceType"],
        producers["settings"]["resourceType"],
    }
    assert produced_types == set(
        registry["cleanup"]["cleanupInventoryResourceTypes"]
    )
    assert {
        item["type"]
        for item in inventory["resourceGraph"]["response"]["data"]
    } == {
        resource_type
        for resource_types in tables.values()
        for resource_type in resource_types
    }
    assert {
        item["type"].casefold()
        for item in inventory["autoProvisioningSettings"]["response"]["value"]
    } == {producers["autoProvisioningSettings"]["resourceType"]}
    assert {
        item["type"].casefold()
        for item in inventory["settings"]["response"]["value"]
    } == {producers["settings"]["resourceType"]}


def test_scheduled_cleanup_cannot_claim_queried_cost_evidence(
    tmp_path: Path,
) -> None:
    """Reject a queried cost status before cleanup and restoration complete."""
    root = _copy_bundle(tmp_path)

    def forge_cost_status(value: dict[str, Any]) -> None:
        evidence_path = (
            root
            / "workshop/contracts/fixtures/defender/recommendations.json"
        )
        value["costVerification"] = {
            "status": "queried",
            "billingDataMayLag": True,
            "queriedAt": "2025-01-01T10:00:00Z",
            "evidenceFile": (
                "workshop/contracts/fixtures/defender/recommendations.json"
            ),
            "evidenceSha256": _sha256(evidence_path),
        }

    _mutate_artifact(
        root,
        "workshop/contracts/fixtures/defender/cleanup-manifest.json",
        forge_cost_status,
    )
    with pytest.raises(
        JsonSchemaValidationError,
        match="should not be valid",
    ):
        _build(root)


def test_completed_cleanup_requires_restoration_and_cost_evidence(
    tmp_path: Path,
) -> None:
    """Require completed cleanup to prove prior pricing and a later cost query."""
    root = _copy_bundle(tmp_path)
    fixture_root = root / "workshop/contracts/fixtures/defender"
    post_pricings = {
        "schemaVersion": "1.0.0",
        "request": {
            "method": "GET",
            "operation": "subscription-defender-pricings",
            "scopeResourceId": (
                "/subscriptions/00000000-0000-0000-0000-000000000000"
            ),
            "apiVersion": "2024-01-01",
            "queriedAt": "2025-01-01T11:02:00Z",
        },
        "response": {
            "value": [
                {
                    "id": (
                        "/subscriptions/00000000-0000-0000-0000-000000000000/"
                        f"providers/Microsoft.Security/pricings/{name}"
                    ),
                    "name": name,
                    "type": "Microsoft.Security/pricings",
                    "properties": {
                        "pricingTier": "Free",
                        "enforce": "False",
                        "extensions": [],
                    },
                }
                for name in [
                    "CloudPosture",
                    "Containers",
                    "SqlServers",
                    "OpenSourceRelationalDatabases",
                    "VirtualMachines",
                ]
            ]
        },
    }
    post_path = fixture_root / "post-cleanup-pricings.json"
    post_inventory_path = fixture_root / "post-cleanup-inventory.json"
    cost_path = fixture_root / "cost-query.json"
    _write(post_path, post_pricings)
    post_inventory = _load(fixture_root / "cleanup-inventory-before.json")
    _set_cleanup_inventory_queried_at(
        post_inventory,
        "2025-01-01T11:03:00Z",
    )
    _write(post_inventory_path, post_inventory)
    cost_evidence = {
        "schemaVersion": "1.0.0",
        "request": {
                "method": "POST",
                "operation": "subscription-defender-cost-query",
                "scopeResourceId": (
                    "/subscriptions/00000000-0000-0000-0000-000000000000"
                ),
                "apiVersion": "2023-11-01",
                "queriedAt": "2025-01-01T11:05:00Z",
                "body": {
                    "type": "Usage",
                    "timeframe": "Custom",
                    "timePeriod": {
                        "from": "2025-01-01T09:05:00Z",
                        "to": "2025-01-01T11:05:00Z",
                    },
                    "dataset": {
                        "granularity": "Daily",
                        "aggregation": {
                            "totalCost": {
                                "name": "PreTaxCost",
                                "function": "Sum",
                            }
                        },
                        "grouping": [
                            {
                                "type": "Dimension",
                                "name": "ServiceName",
                            },
                            {
                                "type": "Dimension",
                                "name": "ResourceId",
                            },
                        ],
                        "filter": {
                            "dimensions": {
                                "name": "ServiceName",
                                "operator": "In",
                                "values": ["Microsoft Defender for Cloud"],
                            }
                        },
                    },
                },
        },
        "response": {
            "id": (
                "/subscriptions/00000000-0000-0000-0000-000000000000/"
                "providers/Microsoft.CostManagement/Query/"
                "11111111-1111-1111-1111-111111111111"
            ),
            "name": "11111111-1111-1111-1111-111111111111",
            "type": "microsoft.costmanagement/Query",
            "properties": {
                "columns": [
                    {"name": "PreTaxCost", "type": "Number"},
                    {"name": "ServiceName", "type": "String"},
                    {"name": "ResourceId", "type": "String"},
                    {"name": "Currency", "type": "String"},
                ],
                "rows": [],
            },
        },
    }
    _write(cost_path, cost_evidence)

    cleanup_path = fixture_root / "cleanup-manifest.json"
    cleanup = _load(cleanup_path)
    cleanup.update(
        {
            "status": "completed",
            "completedAt": "2025-01-01T11:00:00Z",
            "postCleanupPricings": {
                "file": "workshop/contracts/fixtures/defender/post-cleanup-pricings.json",
                "sha256": _sha256(post_path),
            },
            "postCleanupInventory": {
                "file": "workshop/contracts/fixtures/defender/post-cleanup-inventory.json",
                "sha256": _sha256(post_inventory_path),
            },
        }
    )
    cleanup["costVerification"] = {
        "status": "queried",
        "billingDataMayLag": True,
        "queriedAt": "2025-01-01T11:05:00Z",
        "evidenceFile": "workshop/contracts/fixtures/defender/cost-query.json",
        "evidenceSha256": _sha256(cost_path),
    }
    _write(cleanup_path, cleanup)
    cleanup_relative = (
        "workshop/contracts/fixtures/defender/cleanup-manifest.json"
    )
    _refresh_capture_digest(root, cleanup_relative)
    assert _build(root)["cleanup"]["status"] == "completed"

    post_pricings["response"]["value"][0]["properties"]["enforce"] = "True"
    _write(post_path, post_pricings)
    cleanup["postCleanupPricings"]["sha256"] = _sha256(post_path)
    _write(cleanup_path, cleanup)
    _refresh_capture_digest(root, cleanup_relative)
    with pytest.raises(ValueError, match="enforce differs from prior state"):
        _build(root)

    post_pricings["response"]["value"][0]["properties"]["enforce"] = "False"
    _write(post_path, post_pricings)
    cleanup["postCleanupPricings"]["sha256"] = _sha256(post_path)

    cleanup["completedAt"] = "2025-01-01T09:05:00Z"
    _write(cleanup_path, cleanup)
    _refresh_capture_digest(root, cleanup_relative)
    with pytest.raises(ValueError, match="must complete after paid-plan enablement"):
        _build(root)
    cleanup["completedAt"] = "2025-01-01T11:00:00Z"

    post_pricings["request"]["queriedAt"] = "2025-01-01T11:00:00Z"
    _write(post_path, post_pricings)
    cleanup["postCleanupPricings"]["sha256"] = _sha256(post_path)
    _write(cleanup_path, cleanup)
    _refresh_capture_digest(root, cleanup_relative)
    with pytest.raises(ValueError, match="pricing query must follow cleanup"):
        _build(root)
    post_pricings["request"]["queriedAt"] = "2025-01-01T11:02:00Z"
    _write(post_path, post_pricings)
    cleanup["postCleanupPricings"]["sha256"] = _sha256(post_path)

    _set_cleanup_inventory_queried_at(
        post_inventory,
        "2025-01-01T11:00:00Z",
    )
    _write(post_inventory_path, post_inventory)
    cleanup["postCleanupInventory"]["sha256"] = _sha256(post_inventory_path)
    _write(cleanup_path, cleanup)
    _refresh_capture_digest(root, cleanup_relative)
    with pytest.raises(ValueError, match="inventory query must follow cleanup"):
        _build(root)
    _set_cleanup_inventory_queried_at(
        post_inventory,
        "2025-01-01T11:03:00Z",
    )
    _write(post_inventory_path, post_inventory)
    cleanup["postCleanupInventory"]["sha256"] = _sha256(post_inventory_path)

    cost_evidence["request"]["queriedAt"] = "2025-01-01T11:03:00Z"
    cost_evidence["request"]["body"]["timePeriod"]["to"] = (
        "2025-01-01T11:03:00Z"
    )
    _write(cost_path, cost_evidence)
    cleanup["costVerification"]["queriedAt"] = "2025-01-01T11:03:00Z"
    cleanup["costVerification"]["evidenceSha256"] = _sha256(cost_path)
    _write(cleanup_path, cleanup)
    _refresh_capture_digest(root, cleanup_relative)
    with pytest.raises(ValueError, match="after restoration"):
        _build(root)
    cost_evidence["request"]["queriedAt"] = "2025-01-01T11:05:00Z"
    cost_evidence["request"]["body"]["timePeriod"]["to"] = (
        "2025-01-01T11:05:00Z"
    )
    _write(cost_path, cost_evidence)
    cleanup["costVerification"]["queriedAt"] = "2025-01-01T11:05:00Z"
    cleanup["costVerification"]["evidenceSha256"] = _sha256(cost_path)

    cost_evidence["response"]["properties"]["nextLink"] = (
        "https://management.azure.com/next-page"
    )
    _write(cost_path, cost_evidence)
    cleanup["costVerification"]["evidenceSha256"] = _sha256(cost_path)
    _write(cleanup_path, cleanup)
    _refresh_capture_digest(root, cleanup_relative)
    with pytest.raises(ValueError, match="must contain every result page"):
        _build(root)

    del cost_evidence["response"]["properties"]["nextLink"]
    _write(cost_path, cost_evidence)
    cleanup["costVerification"]["evidenceSha256"] = _sha256(cost_path)
    post_inventory["resourceGraph"]["response"]["data"].append(
        {
            "id": (
                "/subscriptions/00000000-0000-0000-0000-000000000000/"
                "resourceGroups/rg-mh-source-example/providers/"
                "Microsoft.Compute/virtualMachines/vm-dotnet-user001/"
                "extensions/MDE.Windows"
            ),
            "name": "MDE.Windows",
            "type": "microsoft.compute/virtualmachines/extensions",
            "properties": {
                "publisher": "Microsoft.Azure.AzureDefenderForServers"
            },
            "identity": None,
            "location": "westeurope",
        }
    )
    post_inventory["resourceGraph"]["response"]["count"] = 10
    post_inventory["resourceGraph"]["response"]["totalRecords"] = 10
    _write(post_inventory_path, post_inventory)
    cleanup["postCleanupInventory"]["sha256"] = _sha256(
        post_inventory_path
    )
    _write(cleanup_path, cleanup)
    _refresh_capture_digest(root, cleanup_relative)
    with pytest.raises(ValueError, match="inventory differs from prior state"):
        _build(root)

    post_inventory["resourceGraph"]["response"]["data"].pop()
    post_inventory["resourceGraph"]["response"]["count"] = 9
    post_inventory["resourceGraph"]["response"]["totalRecords"] = 9
    policy_assignment = next(
        item
        for item in post_inventory["resourceGraph"]["response"]["data"]
        if item["type"] == "microsoft.authorization/policyassignments"
    )
    policy_assignment["identity"]["principalId"] = (
        "00000000-0000-0000-0000-000000000099"
    )
    _write(post_inventory_path, post_inventory)
    cleanup["postCleanupInventory"]["sha256"] = _sha256(
        post_inventory_path
    )
    _write(cleanup_path, cleanup)
    _refresh_capture_digest(root, cleanup_relative)
    with pytest.raises(ValueError, match="inventory differs from prior state"):
        _build(root)

    policy_assignment["identity"]["principalId"] = (
        "00000000-0000-0000-0000-000000000021"
    )
    _write(post_inventory_path, post_inventory)
    cleanup["postCleanupInventory"]["sha256"] = _sha256(
        post_inventory_path
    )
    cleanup["completedAt"] = "2025-01-01T09:00:00Z"
    post_pricings["request"]["queriedAt"] = "2025-01-01T09:01:00Z"
    _write(post_path, post_pricings)
    cleanup["postCleanupPricings"]["sha256"] = _sha256(post_path)
    _write(cleanup_path, cleanup)
    _refresh_capture_digest(root, cleanup_relative)
    with pytest.raises(ValueError, match="must complete after paid-plan enablement"):
        _build(root)

    cleanup["completedAt"] = "2025-01-01T11:00:00Z"
    post_pricings["request"]["queriedAt"] = "2025-01-01T11:02:00Z"
    _write(post_path, post_pricings)
    cleanup["postCleanupPricings"]["sha256"] = _sha256(post_path)
    valid_cost_response = cost_evidence["response"]
    cost_evidence["response"] = {"properties": {"note": "not a query result"}}
    _write(cost_path, cost_evidence)
    cleanup["costVerification"]["evidenceSha256"] = _sha256(cost_path)
    _write(cleanup_path, cleanup)
    _refresh_capture_digest(root, cleanup_relative)
    with pytest.raises(
        JsonSchemaValidationError,
        match="'id' is a required property",
    ):
        _build(root)

    cost_evidence["response"] = valid_cost_response
    cost_evidence["request"]["scopeResourceId"] = (
        "/subscriptions/11111111-1111-1111-1111-111111111111"
    )
    _write(cost_path, cost_evidence)
    cleanup["costVerification"]["evidenceSha256"] = _sha256(cost_path)
    _write(cleanup_path, cleanup)
    _refresh_capture_digest(root, cleanup_relative)
    with pytest.raises(ValueError, match="must target the subscription"):
        _build(root)

    cost_evidence["request"]["scopeResourceId"] = (
        "/subscriptions/00000000-0000-0000-0000-000000000000"
    )
    cost_evidence["request"]["queriedAt"] = "2025-01-01T11:01:00Z"
    cost_evidence["request"]["body"]["timePeriod"]["to"] = (
        "2025-01-01T11:01:00Z"
    )
    _write(cost_path, cost_evidence)
    cleanup["costVerification"]["queriedAt"] = "2025-01-01T11:01:00Z"
    cleanup["costVerification"]["evidenceSha256"] = _sha256(cost_path)
    _write(cleanup_path, cleanup)
    _refresh_capture_digest(root, cleanup_relative)
    with pytest.raises(ValueError, match="after restoration"):
        _build(root)

    cost_evidence["request"]["queriedAt"] = "2025-01-01T11:05:00Z"
    cost_evidence["request"]["body"]["timePeriod"]["to"] = (
        "2025-01-01T11:05:00Z"
    )
    cleanup["costVerification"]["queriedAt"] = "2025-01-01T11:05:00Z"
    _write(cost_path, cost_evidence)
    cleanup["costVerification"]["evidenceSha256"] = _sha256(cost_path)
    post_pricings["response"]["value"][0]["properties"][
        "pricingTier"
    ] = "Standard"
    _write(post_path, post_pricings)
    cleanup["postCleanupPricings"]["sha256"] = _sha256(post_path)
    _write(cleanup_path, cleanup)
    _refresh_capture_digest(root, cleanup_relative)
    with pytest.raises(ValueError, match="tier differs from prior state"):
        _build(root)


def test_renderer_consumes_registry_from_the_active_repository(
    tmp_path: Path,
) -> None:
    """Prove rendering cannot borrow the installed package's Defender registry."""
    root = _copy_bundle(tmp_path)
    registry_path = root / "workshop/contracts/defender.json"
    registry = _load(registry_path)
    registry["evidence"]["queryContracts"]["recommendations"][
        "apiVersion"
    ] = "2020-01-02"
    _write(registry_path, registry)
    with pytest.raises(ValueError, match="API version differs from the registry"):
        _build(root)


def test_renderer_consumes_schemas_from_the_active_repository(
    tmp_path: Path,
) -> None:
    """Prove rendering cannot borrow the installed package's Defender schemas."""
    root = _copy_bundle(tmp_path)
    schema_path = (
        root / "workshop/contracts/defender-evidence-capture.schema.json"
    )
    schema = _load(schema_path)
    schema["required"].append("repositorySentinel")
    _write(schema_path, schema)
    with pytest.raises(
        JsonSchemaValidationError,
        match="'repositorySentinel' is a required property",
    ):
        _build(root)


def test_validator_rejects_substitute_contract_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject an alternate contract tree before upstream handoff validation."""
    root = _copy_bundle(tmp_path)
    capture = root / "workshop/contracts/defender-evidence-capture.example.json"
    handoff = root / "workshop/contracts/fixtures/defender/handoff.json"
    report_path = root / "evidence/defender-report.json"
    _write(report_path, _build(root))
    alternate = root / "alternate-contracts"
    alternate.mkdir()
    monkeypatch.setattr(defender_evidence, "validate_handoff", lambda *args: {})
    with pytest.raises(ValueError, match="repository workshop/contracts"):
        validate_defender_evidence(
            capture,
            handoff,
            report_path,
            alternate,
            root,
        )
