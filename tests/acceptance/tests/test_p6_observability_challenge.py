"""Executable ownership and frozen-input checks for Challenge 4."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_observability_challenge_consumes_the_frozen_registry() -> None:
    """Keep workbook implementation anchored to exact files and panel identities."""
    registry = json.loads(
        (ROOT / "workshop/contracts/shared-challenges.json").read_text(
            encoding="utf-8"
        )
    )
    challenge = next(
        item for item in registry["challenges"] if item["id"] == "observability"
    )

    assert challenge["artifacts"] == [
        "workshop/observability/queries.kql",
        "workshop/observability/workbook.json",
        "infra/observability-workbook.bicep",
        "tests/acceptance/tests/test_p6_observability_challenge.py",
    ]
    assert "catalog-validate-challenge-evidence observability" in challenge[
        "evidenceValidationCommand"
    ]
    assert registry["observabilityPanels"] == [
        "error-rate",
        "latency",
        "database-dependency-failures",
        "replica-count",
        "cold-starts",
    ]
    assert registry["observabilityMetrics"] == {
        "source": "container-app-diagnostic-setting",
        "category": "AllMetrics",
        "destination": "handoff-log-analytics-workspace",
        "destinationTable": "AzureMetricsV2",
        "requiredMetric": "Replicas",
    }
