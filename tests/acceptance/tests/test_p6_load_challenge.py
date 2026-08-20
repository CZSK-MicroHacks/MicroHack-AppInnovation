"""Executable ownership and frozen-input checks for Challenge 2."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_load_challenge_consumes_the_frozen_registry() -> None:
    """Keep the load implementation anchored to its owned files and signals."""
    registry = json.loads(
        (ROOT / "workshop/contracts/shared-challenges.json").read_text(
            encoding="utf-8"
        )
    )
    challenge = next(
        item for item in registry["challenges"] if item["id"] == "load-autoscaling"
    )

    assert challenge["artifacts"] == [
        "tests/load/catalog-load.jmx",
        "tests/load/load-test.yaml",
        "tests/acceptance/tests/test_p6_load_challenge.py",
    ]
    assert challenge["evidenceSchema"].endswith("load-test-evidence.schema.json")
    assert "catalog-validate-challenge-evidence load" in challenge[
        "evidenceValidationCommand"
    ]
    assert registry["loadSignals"]["testRun"] == {
        "resourceType": "Microsoft.LoadTestService/loadTests"
    }
    assert registry["loadSignals"]["replicas"] == {
        "resourceType": "Microsoft.App/containerApps",
        "metric": "Replicas",
        "minimum": 1,
        "scaleOutMinimum": 2,
        "maximum": 3,
        "scaleRule": {
            "name": "http",
            "type": "http",
            "concurrentRequests": 50,
        },
    }
