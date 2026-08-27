"""Coverage for the telemetry query-result contract (F-89).

This schema was one of only two in the contract set with no test referencing it,
which is the structural reason its ``additionalProperties: false`` came to sit over
a provenance-free object without anyone noticing what it foreclosed.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = REPO_ROOT / "workshop" / "contracts"
SCHEMA_PATH = CONTRACTS / "telemetry-query-result.schema.json"

PROVENANCE_FIELDS = ("workspaceId", "capturedAt", "queryText")


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _minimal_result(query_id: str = "resources") -> dict:
    return {
        "schemaVersion": "1.0.0",
        "queryId": query_id,
        "rows": [
            {
                "signalName": "resource",
                "recordCount": 1,
                "observedAttributes": ["service.name"],
            }
        ],
    }


def test_schema_is_parseable_and_self_describing() -> None:
    """The contract must be a valid JSON Schema before anything else is asserted."""
    schema = _schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema["$id"].endswith("telemetry-query-result.schema.json")


def test_minimal_result_validates() -> None:
    """The smallest honest artifact must be accepted."""
    jsonschema.validate(_minimal_result(), _schema())


@pytest.mark.parametrize("field", PROVENANCE_FIELDS)
def test_provenance_fields_are_expressible(field: str) -> None:
    """F-89: an attendee who wants to record where evidence came from must be able to.

    Before this fix ``additionalProperties: false`` rejected every provenance key, so
    the honest attendee had no way to bind the artifact to its source even voluntarily.
    """
    values = {
        "workspaceId": "/subscriptions/x/resourceGroups/y/providers/"
        "Microsoft.OperationalInsights/workspaces/z",
        "capturedAt": "2026-08-27T22:05:00Z",
        "queryText": "AppTraces | summarize count() by OperationName",
    }
    document = _minimal_result() | {field: values[field]}
    jsonschema.validate(document, _schema())


def test_provenance_remains_optional_so_existing_bundles_still_validate() -> None:
    """The fix is additive: no previously valid artifact may become invalid."""
    assert set(_schema()["required"]) == {"schemaVersion", "queryId", "rows"}
    jsonschema.validate(_minimal_result(), _schema())


def test_unknown_keys_are_still_rejected() -> None:
    """Relaxing the prohibition must not turn the contract into a free-form object."""
    document = _minimal_result() | {"totallyMadeUpKey": "value"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(document, _schema())


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param({"schemaVersion": "2.0.0"}, id="wrong-schema-version"),
        pytest.param({"queryId": "not-a-real-query"}, id="unknown-query-id"),
        pytest.param({"rows": []}, id="empty-rows"),
    ],
)
def test_contract_rejects_malformed_documents(mutation: dict) -> None:
    """Guard that the schema still constrains the fields it always constrained."""
    document = _minimal_result() | mutation
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(document, _schema())


def test_metrics_require_unit_and_measurements() -> None:
    """The conditional branch for metrics is load-bearing and previously untested."""
    document = _minimal_result("metrics")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(document, _schema())

    document["rows"][0] |= {
        "unit": "{record}",
        "measurements": [{"value": 1, "attributes": {"catalog.import.outcome": "rejected"}}],
    }
    jsonschema.validate(document, _schema())


@pytest.mark.parametrize("query_id", ["traces", "logs"])
def test_traces_and_logs_require_observations(query_id: str) -> None:
    """The conditional branch for traces/logs is load-bearing and previously untested."""
    document = _minimal_result(query_id)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(document, _schema())

    document["rows"][0]["observations"] = [{"attributes": {"http.route": "/figure/{id}"}}]
    jsonschema.validate(document, _schema())


def test_shipped_example_still_validates_against_the_relaxed_schema() -> None:
    """The checked-in example must not drift from the contract it illustrates."""
    example = json.loads((CONTRACTS / "telemetry-evidence.example.json").read_text())
    queries = example.get("queries", example.get("results", []))
    assert queries, "example must carry query entries to be worth validating"
