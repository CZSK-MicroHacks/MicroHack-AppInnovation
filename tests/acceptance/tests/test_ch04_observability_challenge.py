"""Executable implementation checks for the bounded Challenge 4 stream."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from catalog_acceptance.shared_challenges import (
    render_observability_query_source,
)


ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "workshop/contracts"
PANEL_IDS = [
    "error-rate",
    "latency",
    "database-dependency-failures",
    "replica-count",
    "cold-starts",
]


def _load_json(path: Path) -> dict[str, Any]:
    """Load a repository JSON document."""
    return json.loads(path.read_text(encoding="utf-8"))


def _query_contract() -> dict[str, Any]:
    """Return the frozen observability query contract."""
    return _load_json(CONTRACTS / "observability-queries.json")


def test_queries_kql_is_the_exact_deterministic_contract_rendering() -> None:
    """The checked-in KQL source is the shared producer's exact rendering."""
    query_path = ROOT / "workshop/observability/queries.kql"
    actual = query_path.read_text(encoding="utf-8")
    expected = render_observability_query_source(CONTRACTS)

    assert actual == expected
    assert hashlib.sha256(actual.encode()).hexdigest() == hashlib.sha256(
        expected.encode()
    ).hexdigest()

    replica = next(
        item["template"]
        for item in _query_contract()["queries"]
        if item["id"] == "replica-count"
    )
    assert "AzureMetrics |" in replica
    assert '_ResourceId =~ "__CONTAINER_APP_RESOURCE_ID__"' in replica
    assert 'MetricName == "Replicas" and TimeGrain == "PT1M"' in replica
    assert "toint(max(Total))" in replica
    for forbidden in (
        "AzureMetricsV2",
        'Dimension["revisionName"]',
        "__REVISION_NAME__",
        "Maximum",
    ):
        assert forbidden not in replica


def test_workbook_is_exactly_the_five_workspace_logs_panels() -> None:
    """The deterministic workbook has only the five frozen Logs panels."""
    workbook_path = ROOT / "workshop/observability/workbook.json"
    workbook_text = workbook_path.read_text(encoding="utf-8")
    workbook = json.loads(workbook_text)
    declarations = _query_contract()["queries"]

    assert workbook_text == json.dumps(workbook, indent=2) + "\n"
    assert hashlib.sha256(workbook_text.encode()).hexdigest() == hashlib.sha256(
        (json.dumps(workbook, indent=2) + "\n").encode()
    ).hexdigest()
    assert workbook["version"] == "Notebook/1.0"
    assert set(workbook) == {"version", "items"}
    assert [item["name"] for item in workbook["items"]] == PANEL_IDS
    assert len(workbook["items"]) == 5

    for item, declaration in zip(workbook["items"], declarations, strict=True):
        assert set(item) == {"type", "name", "content"}
        assert item["type"] == 3
        assert item["name"] == declaration["id"]
        content = item["content"]
        assert content["version"] == "KqlItem/1.0"
        assert type(content["queryType"]) is int
        assert content["queryType"] == 0
        assert (
            content["resourceType"]
            == "microsoft.operationalinsights/workspaces"
        )
        assert content["query"] == declaration["template"]
        assert content.get("crossComponentResources") in (None, [])

    replica = workbook["items"][3]["content"]
    assert replica["title"] == "Peak one-minute total Container App replicas"
    assert "Peak Total replicas at PT1M for the whole Container App" in replica[
        "description"
    ]
    for forbidden in (
        "AzureMetricsV2",
        'Dimension["revisionName"]',
        "Maximum",
    ):
        assert forbidden not in replica["query"]


def test_bicep_uses_same_scope_existing_resources_and_two_deployments() -> None:
    """IaC deploys the workbook and metric export in the handoff resource group."""
    bicep = (ROOT / "infra/observability-workbook.bicep").read_text(
        encoding="utf-8"
    )

    for resource_id in (
        "applicationInsightsResourceId",
        "logAnalyticsWorkspaceResourceId",
        "containerAppResourceId",
    ):
        assert f"param {resource_id} string" in bicep
    assert bicep.count(" existing = {") == 3
    assert bicep.count("IsSameScope =") == 3
    assert "scope: resourceGroup(" not in bicep
    assert "applicationInsightsSegments[4]" not in bicep
    assert "workspaceSegments[4]" not in bicep
    assert "containerAppSegments[4]" not in bicep

    resource_lines = [
        line for line in bicep.splitlines() if line.startswith("resource ")
    ]
    assert len(resource_lines) == 5
    assert (
        "resource metricsExport "
        "'Microsoft.Insights/diagnosticSettings@2021-05-01-preview'" in bicep
    )
    assert "scope: containerApp" in bicep
    assert (
        "resource workbook 'Microsoft.Insights/workbooks@2023-06-01'" in bicep
    )
    assert "category: 'AllMetrics'" in bicep
    assert "workspaceId: logAnalyticsWorkspaceResourceId" in bicep
    assert "sourceId: logAnalyticsWorkspaceResourceId" in bicep
    assert "logAnalyticsDestinationType" not in bicep
    assert "dataCollection" not in bicep
    assert "Microsoft.Insights/dataCollectionRules" not in bicep

    assert "loadTextContent('../workshop/observability/workbook.json')" in bicep
    assert "serializedData: serializedData" in bicep
    assert (
        "'__APPLICATION_INSIGHTS_RESOURCE_ID__', applicationInsightsResourceId"
        in bicep
    )
    assert "'__CONTAINER_APP_RESOURCE_ID__', containerAppResourceId" in bicep
    assert "version: 'Notebook/1.0'" in bicep
    assert "output metricsDestinationTable string = 'AzureMetrics'" in bicep
    assert "output metricsScope string = 'container-app-total'" in bicep
    assert "output metricsDimensionHandling string = 'flattened'" in bicep
    assert "AzureMetricsV2" not in bicep


def test_guides_bind_frozen_live_evidence_and_common_validator() -> None:
    """Guidance covers the 1.1.0 evidence shape without false revision claims."""
    challenge = (ROOT / "challenges/ch04/README.md").read_text(encoding="utf-8")
    solution = (ROOT / "solutions/ch04/README.md").read_text(encoding="utf-8")
    combined = f"{challenge}\n{solution}"

    required_terms = (
        "evidence/modernization-contract.json",
        "evidence/telemetry-report.json",
        "application.resourceGroup",
        "applicationInsightsResourceId",
        "logAnalyticsWorkspaceResourceId",
        "containerAppResourceId",
        "serviceName",
        "serviceNamespace",
        "environment",
        "sourceCommit",
        "revisionName",
        "serializedData",
        "serializedDataSha256",
        "templateSha256",
        "queriesSha256",
        "querySha256",
        'destinationTable: "AzureMetrics"',
        'scope: "container-app-total"',
        'dimensionHandling: "flattened"',
        "applicationTelemetryRevisionFilterApplied",
        "PT1M",
        "Total",
        "raw",
        "normalized",
        "1.1.0",
    )
    for term in required_terms:
        assert term in combined

    validator = (
        "catalog-validate-challenge-evidence observability "
        "\\\n  evidence/observability-report.json "
        "\\\n  --handoff evidence/modernization-contract.json "
        "\\\n  --contracts workshop/contracts "
        "\\\n  --repository-root ../.."
    )
    assert validator in challenge
    assert validator in solution
    assert "Challenge 2 remains authoritative" in challenge
    assert "four Application Insights panels" in challenge
    assert "no revision filter" in " ".join(solution.split())
    assert "synthetic" in challenge
    assert "never live" in challenge
    assert "synthetic structure, not evidence" in solution
    assert "failure-closed" in combined
    assert "never fabricate" in solution
    assert "AzureMetricsV2" not in combined


def test_registry_identity_remains_the_refrozen_producer_contract() -> None:
    """Consume registry 1.2.0 with observability contracts still frozen at 1.1.0."""
    registry = _load_json(CONTRACTS / "shared-challenges.json")
    query_contract = _query_contract()
    evidence_schema = _load_json(
        CONTRACTS / "observability-evidence.schema.json"
    )
    challenge = next(
        item for item in registry["challenges"] if item["id"] == "observability"
    )

    assert registry["schemaVersion"] == "1.2.0"
    assert query_contract["schemaVersion"] == "1.1.0"
    assert evidence_schema["properties"]["schemaVersion"]["const"] == "1.1.0"
    assert challenge["artifacts"] == [
        "workshop/observability/queries.kql",
        "workshop/observability/workbook.json",
        "infra/observability-workbook.bicep",
        "tests/acceptance/tests/test_ch04_observability_challenge.py",
    ]
    assert registry["observabilityPanels"] == PANEL_IDS
    assert registry["observabilityMetrics"] == {
        "source": "container-app-diagnostic-setting",
        "category": "AllMetrics",
        "destination": "handoff-log-analytics-workspace",
        "destinationTable": "AzureMetrics",
        "deploymentScope": "handoff-container-app-resource-group",
        "scope": "container-app-total",
        "dimensionHandling": "flattened",
        "aggregation": "Total",
        "timeGrain": "PT1M",
        "windowReduction": "peak",
        "requiredMetric": "Replicas",
    }
