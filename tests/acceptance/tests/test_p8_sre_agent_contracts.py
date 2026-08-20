"""Executable contracts and false-success tests for Challenge 6."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
import shutil
from typing import Any, Callable

from jsonschema import Draft202012Validator, FormatChecker
import pytest

from catalog_acceptance import sre_evidence
from catalog_acceptance.sre_evidence import (
    build_sre_agent_evidence,
    render_sre_agent_evidence,
    validate_sre_agent_evidence,
)
from catalog_acceptance.sre_evidence_cli import render_main, validate_main


ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "workshop/contracts"
FIXTURES = CONTRACTS / "fixtures/sre-agent"
CAPTURE_EXAMPLE = CONTRACTS / "sre-agent-evidence-capture.example.json"
REPORT_EXAMPLE = CONTRACTS / "sre-agent-evidence.example.json"
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
    """Return one lowercase SHA-256 digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate(schema_name: str, document: dict[str, Any]) -> None:
    """Validate one document against a checked-in schema."""
    Draft202012Validator(
        _load(CONTRACTS / schema_name),
        format_checker=FormatChecker(),
    ).validate(document)


def _copy_bundle(tmp_path: Path) -> Path:
    """Copy the representative P8 contract bundle to one temporary root."""
    root = tmp_path / "repo"
    (root / "workshop").mkdir(parents=True)
    shutil.copytree(CONTRACTS, root / "workshop/contracts")
    return root


def _capture_reference(capture: dict[str, Any], kind: str) -> dict[str, str]:
    """Return one unique artifact reference from a capture manifest."""
    references = [
        reference
        for reference in capture["artifacts"]
        if reference["kind"] == kind
    ]
    assert len(references) == 1
    return references[0]


def _mutate_artifact(
    root: Path,
    kind: str,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    """Mutate one artifact and refresh its capture-manifest digest."""
    capture_path = root / "workshop/contracts/sre-agent-evidence-capture.example.json"
    capture = _load(capture_path)
    reference = _capture_reference(capture, kind)
    artifact_path = root / reference["path"]
    artifact = _load(artifact_path)
    mutate(artifact)
    _write(artifact_path, artifact)
    reference["sha256"] = _sha256(artifact_path)
    _write(capture_path, capture)


def _build(root: Path) -> dict[str, Any]:
    """Build the representative P8 report from one temporary root."""
    return build_sre_agent_evidence(
        root / "workshop/contracts/sre-agent-evidence-capture.example.json",
        root / "workshop/contracts/fixtures/sre-agent/handoff.json",
        root,
    )


def _foundation_role_inventory(
    foundation: dict[str, Any],
    principal: str,
) -> dict[str, Any]:
    """Return one named foundation RBAC inventory."""
    return foundation["roleAssignments"][principal]


def _remove_seed_activity(incident: dict[str, Any]) -> None:
    """Remove the facilitator seed write from the activity capture."""
    incident["activityLog"]["response"]["value"].pop(0)


def _move_cost_before_protected_verification(cleanup: dict[str, Any]) -> None:
    """Move cost capture after deletion but before workload verification."""
    cost = cleanup["costVerification"]
    cost["request"]["timeframeEnd"] = "2026-08-20T16:12:09Z"
    cost["queriedAt"] = "2026-08-20T16:12:10Z"


def _move_snapshot_to_first_investigation(incident: dict[str, Any]) -> None:
    """Move the audit snapshot to the first investigation capture."""
    snapshot = incident["agentAudit"]["response"]["tables"][0]["rows"][0]
    snapshot[0] = "2026-08-20T15:06:06Z"
    snapshot[9] = snapshot[0]


def test_sre_agent_registry_and_examples_are_schema_valid() -> None:
    """Freeze every registry, capture, input, and output schema."""
    _validate("sre-agent.schema.json", _load(CONTRACTS / "sre-agent.json"))
    _validate(
        "sre-agent-evidence-capture.schema.json",
        _load(CAPTURE_EXAMPLE),
    )
    _validate("sre-agent-evidence.schema.json", _load(REPORT_EXAMPLE))
    _validate(
        "sre-agent-foundation.schema.json",
        _load(FIXTURES / "foundation.json"),
    )
    _validate(
        "sre-agent-response-plan.schema.json",
        _load(FIXTURES / "response-plan-preflight.json"),
    )
    _validate(
        "sre-agent-incident.schema.json",
        _load(FIXTURES / "incident.json"),
    )
    _validate(
        "sre-agent-cleanup.schema.json",
        _load(FIXTURES / "cleanup.json"),
    )
    _validate(
        "modernization-contract.schema.json",
        _load(HANDOFF_FIXTURE),
    )
    _validate(
        "azure-target-output.schema.json",
        _load(CONTRACTS / "fixtures/defender/target-output.json"),
    )
    _validate(
        "cicd-evidence.schema.json",
        _load(FIXTURES / "cicd-evidence.json"),
    )
    _validate(
        "observability-evidence.schema.json",
        _load(FIXTURES / "observability-evidence.json"),
    )


def test_sre_agent_registry_freezes_the_bounded_architecture() -> None:
    """Freeze API versions, identities, RBAC, review mode, and deletion."""
    registry = _load(CONTRACTS / "sre-agent.json")
    report_schema = _load(CONTRACTS / "sre-agent-evidence.schema.json")
    assert report_schema["properties"]["subject"]["properties"]["stack"]["enum"] == [
        "dotnet-sqlserver",
        "java-postgresql",
    ]
    assert registry["resources"]["agentApiVersion"] == "2026-01-01"
    assert registry["resources"]["connectorApiVersion"] == "2026-01-01"
    assert registry["identity"] == {
        "knowledgeIdentity": "UserAssigned",
        "actionIdentity": "UserAssigned",
        "appInsightsConnectorIdentity": "SystemAssigned",
        "logAnalyticsConnectorIdentity": "SystemAssigned",
        "onBehalfOfElevationAllowed": False,
    }
    roles = registry["rbac"]["knowledgeAndConnectorRoles"]
    assert {
        (role["roleDefinitionId"], role["scope"], tuple(role["principals"]))
        for role in roles
    } == {
        (
            "acdd72a7-3385-48ef-bd42-f606fba81ae7",
            "participant-resource-group",
            ("user-assigned", "system-assigned"),
        ),
        (
            "73c42c96-874c-492b-b04d-ab87d138a893",
            "participant-resource-group",
            ("user-assigned", "system-assigned"),
        ),
        (
            "43d0d8ad-25c7-4714-9337-8ba259a9fe05",
            "participant-resource-group",
            ("user-assigned", "system-assigned"),
        ),
        (
            "749f88d5-cbae-40b8-bcfc-e573ddc772fa",
            "subscription-exception",
            ("user-assigned",),
        ),
    }
    assert set(registry["rbac"]["customRollbackRole"]["actions"]) == {
        "Microsoft.App/containerApps/read",
        "Microsoft.App/containerApps/write",
        "Microsoft.App/containerApps/revisions/read",
    }
    assert registry["responsePlan"]["autonomyMode"] == "Review"
    assert (
        registry["responsePlan"]["producer"]
        == "azure-portal-facilitator-export"
    )
    assert registry["responsePlan"]["quickstartPlanEnabled"] is False
    assert registry["responsePlan"]["participantMayApprove"] is False
    assert registry["responsePlan"]["opaqueIncidentFiltersInIaCAllowed"] is False
    assert registry["billing"] == {
        "fixedAgentUnitsPerHour": 4,
        "stopEndsAlwaysOnBilling": False,
        "deleteEndsAlwaysOnBilling": True,
        "postDeletionCostQueryRequired": True,
    }
    assert registry["cleanup"]["sequence"][-3:] == [
        "verify-resource-group-not-found",
        "verify-protected-handoff-resources",
        "query-cost-management",
    ]


def test_sre_agent_renderer_matches_the_canonical_example(tmp_path: Path) -> None:
    """Prove representative P5/P6 inputs render one stable report."""
    root = _copy_bundle(tmp_path)
    assert _build(root) == _load(root / REPORT_EXAMPLE.relative_to(ROOT))


def test_sre_agent_investigation_supports_postgresql() -> None:
    """Derive JDBC and flexible-server evidence for the Java stack."""
    registry = _load(CONTRACTS / "sre-agent.json")
    handoff = _load(HANDOFF_FIXTURE)
    incident = _load(FIXTURES / "incident.json")
    investigation = incident["investigation"]
    handoff["source"]["stack"] = "java-postgresql"
    handoff["database"]["family"] = "postgresql-flexible"
    handoff["database"]["resourceId"] = (
        "/subscriptions/00000000-0000-0000-0000-000000000000/"
        "resourceGroups/rg-mh-example/providers/Microsoft.DBforPostgreSQL/"
        "flexibleServers/psql-example/databases/catalog"
    )
    handoff["observability"]["serviceName"] = "mh-catalog-java"
    values = {
        "incidentStart": incident["incidentStart"],
        "investigationEnd": investigation["investigationEnd"],
        "serviceName": "mh-catalog-java",
        "sourceCommit": handoff["source"]["commitSha"],
        "badRevision": incident["subject"]["badRevision"],
    }
    investigation["requestFailures"]["request"]["query"] = registry["queries"][
        "investigationRequestFailures"
    ].format(**values)
    investigation["exceptions"]["request"]["query"] = registry["queries"][
        "investigationExceptions"
    ].format(**values)
    investigation["exceptions"]["response"]["tables"][0]["rows"][0][3] = [
        "org.springframework.dao.DataAccessResourceFailureException"
    ]
    investigation["databaseDependencies"]["request"]["query"] = registry[
        "queries"
    ]["investigationDatabaseDependencies"].format(
        **values,
        databaseSystem="postgresql",
    )
    availability = investigation["databaseAvailability"]
    server_id = handoff["database"]["resourceId"].rsplit("/databases/", 1)[0]
    availability["request"]["url"] = f"{server_id}?api-version=2024-08-01"
    availability["response"] = {
        "id": server_id,
        "name": "psql-example",
        "type": "Microsoft.DBforPostgreSQL/flexibleServers",
        "properties": {"state": "Ready"},
    }

    result = sre_evidence._validate_investigation(
        investigation,
        registry,
        handoff,
        incident["incidentStart"],
        incident["subject"]["healthyRevision"],
        incident["subject"]["badRevision"],
        incident["seed"]["badDatabaseHost"],
        incident["seed"]["imageDigest"],
        datetime.fromisoformat(incident["seed"]["createdAt"]),
        datetime.fromisoformat(incident["seed"]["trafficBad"]["observedAt"]),
        datetime.fromisoformat(
            incident["alertFired"]["response"]["properties"]["essentials"][
                "firedDateTime"
            ]
        ),
    )

    evidence = result["summary"]["supportingEvidence"]
    assert evidence["databaseSystem"] == "postgresql"
    assert evidence["selectedDatabaseResourceId"] == server_id
    assert evidence["selectedDatabaseStatus"] == "Ready"
    assert "PostgreSQL Flexible Server remained Ready" in result["assessment"][
        "rootCause"
    ]


def test_sre_agent_report_provenance_binds_every_artifact() -> None:
    """Prove the canonical report exposes its full immutable input chain."""
    capture = _load(CAPTURE_EXAMPLE)
    report = _load(REPORT_EXAMPLE)
    assert report["provenance"]["captureManifest"]["sha256"] == _sha256(
        CAPTURE_EXAMPLE
    )
    assert {
        (item["kind"], item["path"], item["sha256"])
        for item in report["provenance"]["artifacts"]
    } == {
        (item["kind"], item["path"], item["sha256"])
        for item in capture["artifacts"]
    }


def test_sre_agent_cli_is_machine_readable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Freeze successful renderer and validator CLI output."""
    root = _copy_bundle(tmp_path)
    common = [
        "--capture",
        "workshop/contracts/sre-agent-evidence-capture.example.json",
        "--handoff",
        "workshop/contracts/fixtures/sre-agent/handoff.json",
        "--repository-root",
        str(root),
    ]
    assert (
        render_main(
            [
                *common,
                "--output",
                "evidence/sre-agent-report.json",
            ]
        )
        == 0
    )
    render_output = json.loads(capsys.readouterr().out)
    assert render_output["status"] == "passed"
    assert render_output["report"] == "evidence/sre-agent-report.json"

    calls: list[Path] = []
    shared_calls: list[str] = []

    def _record_handoff(
        handoff_path: Path,
        contracts_directory: Path,
        repository_root: Path,
    ) -> dict[str, Any]:
        calls.append(handoff_path)
        assert contracts_directory == root / "workshop/contracts"
        assert repository_root == root
        return {}

    monkeypatch.setattr(sre_evidence, "validate_handoff", _record_handoff)
    monkeypatch.setattr(
        sre_evidence,
        "validate_shared_challenge_evidence",
        lambda kind, *_: shared_calls.append(kind) or {},
    )
    assert (
        validate_main(
            [
                *common,
                "--report",
                "evidence/sre-agent-report.json",
                "--contracts",
                "workshop/contracts",
            ]
        )
        == 0
    )
    validate_output = json.loads(capsys.readouterr().out)
    assert validate_output["status"] == "passed"
    assert validate_output["kind"] == "sre-agent"
    assert calls == [
        root / "workshop/contracts/fixtures/sre-agent/handoff.json"
    ]
    assert shared_calls == ["cicd", "observability"]


def test_sre_agent_report_edits_fail_independent_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject a schema-valid report altered after deterministic rendering."""
    root = _copy_bundle(tmp_path)
    report_path = root / "evidence/sre-agent-report.json"
    render_sre_agent_evidence(
        root / "workshop/contracts/sre-agent-evidence-capture.example.json",
        root / "workshop/contracts/fixtures/sre-agent/handoff.json",
        report_path,
        root,
    )
    report = _load(report_path)
    report["incident"]["failedRequests"] += 1
    _write(report_path, report)
    monkeypatch.setattr(sre_evidence, "validate_handoff", lambda *_: {})
    monkeypatch.setattr(
        sre_evidence,
        "validate_shared_challenge_evidence",
        lambda *_: {},
    )
    with pytest.raises(ValueError, match="differs from raw captures"):
        validate_sre_agent_evidence(
            root / "workshop/contracts/sre-agent-evidence-capture.example.json",
            root / "workshop/contracts/fixtures/sre-agent/handoff.json",
            report_path,
            root / "workshop/contracts",
            root,
        )


def test_sre_agent_rejects_digest_drift(tmp_path: Path) -> None:
    """Reject a changed raw capture when its manifest digest is stale."""
    root = _copy_bundle(tmp_path)
    incident_path = root / "workshop/contracts/fixtures/sre-agent/incident.json"
    incident = _load(incident_path)
    incident["assessment"]["rootCause"] += " changed"
    _write(incident_path, incident)
    with pytest.raises(ValueError, match="artifact digest mismatch"):
        _build(root)


def test_sre_agent_rejects_path_traversal(tmp_path: Path) -> None:
    """Reject artifact paths that escape the trusted repository root."""
    root = _copy_bundle(tmp_path)
    capture_path = root / "workshop/contracts/sre-agent-evidence-capture.example.json"
    capture = _load(capture_path)
    capture["artifacts"][0]["path"] = "../target-output.json"
    _write(capture_path, capture)
    with pytest.raises(ValueError, match="stay within the repository"):
        _build(root)


@pytest.mark.parametrize(
    ("kind", "mutate", "message"),
    [
        (
            "sre-agent-response-plan",
            lambda value: value["audit"]["request"].update(
                {
                    "url": (
                        "/subscriptions/00000000-0000-0000-0000-000000000000/"
                        "resourceGroups/rg-mh-example/providers/Microsoft.Insights/"
                        "components/appi-mh-example/query?api-version=2021-10-01"
                    )
                }
            ),
            "response-plan audit query or source differs",
        ),
        (
            "sre-agent-response-plan",
            lambda value: value["audit"]["response"]["tables"][0]["rows"][0][
                10
            ].update(
                {
                    "alertId": (
                        "/subscriptions/00000000-0000-0000-0000-000000000000/"
                        "providers/Microsoft.AlertsManagement/alerts/"
                        "00000000-0000-0000-0000-000000000299"
                    )
                }
            ),
            "test alert is not bound",
        ),
        (
            "sre-agent-foundation",
            lambda value: _foundation_role_inventory(value, "userAssigned")[
                "request"
            ]["body"].update(
                {"subscriptions": ["11111111-1111-1111-1111-111111111111"]}
            ),
            "complete frozen RBAC query",
        ),
        (
            "sre-agent-foundation",
            lambda value: _foundation_role_inventory(value, "systemAssigned")[
                "response"
            ].update({"resultTruncated": "true"}),
            "false",
        ),
        (
            "sre-agent-foundation",
            lambda value: _foundation_role_inventory(value, "userAssigned")[
                "effectiveAccess"
            ]["response"].pop(),
            "Resource Graph and inherited effective access differ",
        ),
        (
            "sre-agent-incident",
            _remove_seed_activity,
            "seed and approved rollback writes",
        ),
        (
            "sre-agent-incident",
            lambda value: value["seed"]["healthyRevision"]["request"].update(
                {
                    "url": value["seed"]["healthyRevision"]["request"][
                        "url"
                    ].replace("2025-01-01", "2024-03-01")
                }
            ),
            "exact ARM GETs",
        ),
        (
            "sre-agent-incident",
            lambda value: value["alertFired"]["request"].update({"method": "POST"}),
            "fired alert evidence does not use the exact ARM GET",
        ),
        (
            "sre-agent-incident",
            lambda value: value["activityLog"]["request"].update(
                {
                    "url": value["activityLog"]["request"]["url"].replace(
                        "14:59:00Z",
                        "15:00:00Z",
                    )
                }
            ),
            "exact incident ARM query",
        ),
        (
            "sre-agent-incident",
            lambda value: value["containerAppAfterRollback"]["response"][
                "identity"
            ].update({"type": "SystemAssigned"}),
            "changed state beyond traffic",
        ),
        (
            "sre-agent-incident",
            lambda value: value["agentAudit"]["response"]["tables"][0]["rows"][0][
                10
            ].update(
                {
                    "alertId": (
                        "/subscriptions/00000000-0000-0000-0000-000000000000/"
                        "providers/Microsoft.AlertsManagement/alerts/"
                        "00000000-0000-0000-0000-000000000299"
                    )
                }
            ),
            "incident snapshot is not bound to the fired alert",
        ),
        (
            "sre-agent-incident",
            lambda value: value["agentAudit"]["response"]["tables"][0]["rows"][3]
            .__setitem__(0, "2026-08-20T15:06:25Z"),
            "agent audit is not ordered",
        ),
        (
            "sre-agent-cleanup",
            lambda value: value["authorization"].update(
                {
                    "authorizedByPrincipalId": (
                        "00000000-0000-0000-0000-000000000014"
                    )
                }
            ),
            "exact facilitator authorization",
        ),
        (
            "sre-agent-cleanup",
            lambda value: value["protectedResourceVerification"][0].update(
                {"statusCode": 404}
            ),
            "200 was expected",
        ),
        (
            "sre-agent-cleanup",
            _move_cost_before_protected_verification,
            "post-deletion cost verification is incomplete",
        ),
    ],
)
def test_review_corrections_reject_false_success(
    tmp_path: Path,
    kind: str,
    mutate: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    """Reject each false-success mode found by the P8 contract review."""
    root = _copy_bundle(tmp_path)
    _mutate_artifact(root, kind, mutate)

    with pytest.raises(Exception, match=message):
        _build(root)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: value["investigation"]["deploymentHistory"][
                "response"
            ].update({"nextLink": "https://management.azure.com/next"}),
            "deployment history is paginated",
        ),
        (
            lambda value: value["investigation"]["requestFailures"]["request"].update(
                {
                    "query": value["investigation"]["requestFailures"]["request"][
                        "query"
                    ].replace("mh-catalog-dotnet", "unrelated-service")
                }
            ),
            "investigation requestFailures query or source differs",
        ),
        (
            lambda value: value["investigation"]["exceptions"]["response"][
                "tables"
            ][0]["rows"][0].__setitem__(0, 0),
            "investigation exceptions do not identify",
        ),
        (
            lambda value: value["investigation"]["databaseDependencies"]["response"][
                "tables"
            ][0]["rows"][0].__setitem__(4, ["sql-example.database.windows.net"]),
            "investigation dependencies do not identify",
        ),
        (
            lambda value: value["investigation"]["databaseAvailability"]["response"][
                "properties"
            ].update({"status": "Offline"}),
            "selected database is not proven available",
        ),
        (
            lambda value: value["agentAudit"]["response"]["tables"][0]["rows"][1][
                10
            ]["supportingEvidence"].update({"requestFailures": 7}),
            "agent response does not accurately summarize",
        ),
        (
            lambda value: value["agentAudit"]["response"]["tables"][0]["rows"][1][
                10
            ]["alternatives"].pop(),
            "agent response does not accurately summarize",
        ),
        (
            lambda value: value["assessment"].update(
                {"rootCause": "Unsupported guess."}
            ),
            "assessment is not supported by the investigation",
        ),
        (
            lambda value: value["investigation"]["databaseAvailability"].update(
                {"observedAt": "2026-08-20T15:06:21Z"}
            ),
            "alert, review, approval, and execution chronology differs",
        ),
        (
            _move_snapshot_to_first_investigation,
            "alert, review, approval, and execution chronology differs",
        ),
    ],
)
def test_investigation_rejects_false_success(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    """Reject an unsupported diagnosis, hypothesis, or rollback proposal."""
    root = _copy_bundle(tmp_path)
    _mutate_artifact(root, "sre-agent-incident", mutate)

    with pytest.raises(Exception, match=message):
        _build(root)


@pytest.mark.parametrize(
    ("kind", "mutate", "message"),
    [
        (
            "cicd-evidence",
            lambda value: value["subject"].update({"sliceId": "manual-dotnet"}),
            "P5/P6 slice identities differ",
        ),
        (
            "observability-evidence",
            lambda value: value["source"].update(
                {
                    "applicationInsightsResourceId": (
                        "/subscriptions/00000000-0000-0000-0000-000000000000/"
                        "resourceGroups/rg-other/providers/Microsoft.Insights/"
                        "components/appi-other"
                    )
                }
            ),
            "Application Insights identities differ",
        ),
        (
            "sre-agent-foundation",
            lambda value: value["agent"]["request"].update(
                {
                    "url": value["agent"]["request"]["url"].replace(
                        "2026-01-01",
                        "2025-05-01-preview",
                    )
                }
            ),
            "exact 2026 ARM GET",
        ),
        (
            "sre-agent-foundation",
            lambda value: value["agent"]["response"]["properties"][
                "actionConfiguration"
            ].update({"actionMode": "Autonomous"}),
            "Review/Low",
        ),
        (
            "sre-agent-foundation",
            lambda value: value["agent"]["response"]["properties"].update(
                {"onBehalfOfElevation": {"enabled": True}}
            ),
            "forbidden OBO",
        ),
        (
            "sre-agent-foundation",
            lambda value: value["connectors"][0]["response"]["properties"].update(
                {"identity": "user"}
            ),
            "system identity",
        ),
        (
            "sre-agent-foundation",
            lambda value: value["customRollbackRole"]["response"]["properties"][
                "permissions"
            ][0]["actions"].append("Microsoft.App/containerApps/delete"),
            "custom rollback role actions differ",
        ),
        (
            "sre-agent-foundation",
            lambda value: _foundation_role_inventory(value, "participant")[
                "response"
            ]["data"][0]["properties"].update(
                {
                    "roleDefinitionId": (
                        "/subscriptions/00000000-0000-0000-0000-000000000000/"
                        "providers/Microsoft.Authorization/roleDefinitions/"
                        "e79298df-d852-4c6d-84f9-5d13249d1e55"
                    )
                }
            ),
            "participant must have only",
        ),
        (
            "sre-agent-foundation",
            lambda value: _foundation_role_inventory(value, "userAssigned")[
                "request"
            ]["body"].update(
                {
                    "query": (
                        "authorizationresources "
                        "| where type =~ 'microsoft.authorization/roleassignments'"
                    )
                }
            ),
            "complete frozen RBAC query",
        ),
        (
            "sre-agent-incident",
            lambda value: value["seed"].update(
                {
                    "imageDigest": (
                        "sha256:111111111111111111111111111111111111111111111111"
                        "1111111111111111"
                    )
                }
            ),
            "seed image digest differs",
        ),
        (
            "sre-agent-incident",
            lambda value: value["seed"]["revision"]["response"]["properties"][
                "template"
            ]["containers"][0]["env"][1].update({"secretRef": "changed-secret"}),
            "preserve every secret reference",
        ),
        (
            "sre-agent-incident",
            lambda value: value["seed"]["revision"]["response"]["properties"][
                "template"
            ]["containers"][0]["probes"][1]["httpGet"].update(
                {"path": "/readyz"}
            ),
            "probe mutation differs",
        ),
        (
            "sre-agent-incident",
            lambda value: value["badRevisionFailures"]["response"]["tables"][0][
                "rows"
            ][0].__setitem__(1, 0),
            "no failed request evidence",
        ),
        (
            "sre-agent-incident",
            lambda value: value["agentAudit"]["response"]["tables"][0]["rows"][
                3
            ][10].update(
                {
                    "approvedByPrincipalId": (
                        "00000000-0000-0000-0000-000000000014"
                    )
                }
            ),
            "not approved by the facilitator",
        ),
        (
            "sre-agent-incident",
            lambda value: value["agentAudit"]["response"]["tables"][0]["rows"][
                4
            ].__setitem__(0, "2026-08-20T15:06:59Z"),
            "agent audit is not ordered",
        ),
        (
            "sre-agent-incident",
            lambda value: value["activityLog"]["response"]["value"].append(
                value["activityLog"]["response"]["value"][0].copy()
            ),
            "seed and approved rollback writes",
        ),
        (
            "sre-agent-incident",
            lambda value: value["recoveredTraffic"]["value"][0].update(
                {"trafficWeight": 0}
            ),
            "traffic does not total 100",
        ),
        (
            "sre-agent-incident",
            lambda value: value["recoveryHealth"][1].update({"status": 503}),
            "did not return HTTP 200",
        ),
        (
            "sre-agent-incident",
            lambda value: value["assessment"].update(
                {"autonomousExecution": True}
            ),
            "mutation boundaries",
        ),
        (
            "sre-agent-cleanup",
            lambda value: value["agentVerification"].update({"statusCode": 200}),
            "404 was expected",
        ),
        (
            "sre-agent-cleanup",
            lambda value: value["roleAssignmentVerification"]["userAssigned"][
                "response"
            ].update(
                {
                    "data": [{"id": "lingering"}],
                    "count": 1,
                    "totalRecords": 1,
                }
            ),
            "still contains",
        ),
        (
            "sre-agent-cleanup",
            lambda value: value["protectedResources"].pop(),
            "protected-resource inventory differs",
        ),
        (
            "sre-agent-cleanup",
            lambda value: value["costVerification"].update(
                {"queriedAt": "2026-08-20T15:59:00Z"}
            ),
            "cost query does not span",
        ),
    ],
)
def test_sre_agent_rejects_false_successes(
    tmp_path: Path,
    kind: str,
    mutate: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    """Reject representative upstream, RBAC, incident, and cleanup drift."""
    root = _copy_bundle(tmp_path)
    _mutate_artifact(root, kind, mutate)
    with pytest.raises(Exception, match=message):
        _build(root)


def test_sre_agent_rejects_extra_broad_user_role(tmp_path: Path) -> None:
    """Reject broad or extra roles even when Resource Graph counts are coherent."""
    root = _copy_bundle(tmp_path)

    def _add_contributor(foundation: dict[str, Any]) -> None:
        inventory = _foundation_role_inventory(foundation, "userAssigned")
        extra = json.loads(json.dumps(inventory["response"]["data"][0]))
        extra["id"] = extra["id"].replace("000000000101", "000000000199")
        extra["properties"]["roleDefinitionId"] = (
            "/subscriptions/00000000-0000-0000-0000-000000000000/providers/"
            "Microsoft.Authorization/roleDefinitions/"
            "b24988ac-6180-42a0-ab88-20f7382dd24c"
        )
        inventory["response"]["data"].append(extra)
        inventory["response"]["count"] = 6
        inventory["response"]["totalRecords"] = 6
        inventory["effectiveAccess"]["response"].append(
            {
                "principalId": extra["properties"]["principalId"],
                "roleDefinitionId": extra["properties"]["roleDefinitionId"],
                "scope": extra["properties"]["scope"],
            }
        )

    _mutate_artifact(root, "sre-agent-foundation", _add_contributor)
    with pytest.raises(ValueError, match="user-assigned RBAC differs"):
        _build(root)


def test_sre_agent_cli_commands_are_registered() -> None:
    """Freeze the exact public renderer and validator command names."""
    pyproject = (ROOT / "tests/acceptance/pyproject.toml").read_text(
        encoding="utf-8"
    )
    registry = _load(CONTRACTS / "sre-agent.json")
    assert "catalog-render-sre-agent-evidence" in pyproject
    assert "catalog-validate-sre-agent-evidence" in pyproject
    assert (
        registry["evidence"]["rendererCommand"].split()[3]
        == "catalog-render-sre-agent-evidence"
    )
    assert (
        registry["evidence"]["validatorCommand"].split()[3]
        == "catalog-validate-sre-agent-evidence"
    )
