"""Render normalized Challenge 1 telemetry evidence from an Azure capture manifest.

F-89. Challenges 5 and 6 ship dedicated evidence renderers; Challenge 1's telemetry
evidence shipped validation only, which left the honest path hand-authored while the
fabricated path stayed cheap. This module supplies the missing producer.

Two properties matter more than convenience:

* **It cannot invent telemetry.** Every signal, attribute and measurement is copied from
  the capture manifest. A capture that never observed a signal fails; it is not defaulted.
* **It reports every problem at once.** The handoff gate raises one ``ValueError`` at the
  end of the chapter. Iterating against that is what pushes people toward editing evidence
  instead of re-measuring, so this renderer accumulates and reports the full list.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from catalog_acceptance.artifact_io import load_json_object

QUERY_IDS = ("resources", "traces", "metrics", "logs")

ROUTE_PROBE: dict[str, Any] = {
    "http.request.method": "GET",
    "http.route": "/figure/{id}",
    "http.response.status_code": 200,
}

ROUTE_PROBE_CARRIER = {
    "traces": ("http.server", "observations"),
    "metrics": ("http.server.request.duration", "measurements"),
    "logs": ("http.server.request", "observations"),
}


class TelemetryCaptureError(ValueError):
    """Raised when a capture manifest cannot produce valid evidence.

    Carries every problem found rather than the first, so one render call tells the
    attendee everything they still have to measure.
    """

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        joined = "\n".join(f"  - {problem}" for problem in problems)
        super().__init__(f"telemetry capture cannot produce valid evidence:\n{joined}")


def _signal_expectations(behavior: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    """Map each query ID to its frozen signal names and required attributes."""
    return {
        "resources": {"resource": list(behavior["requiredResourceAttributes"])},
        "traces": dict(behavior["traces"]),
        "metrics": dict(behavior["metrics"]),
        "logs": dict(behavior["logs"]),
    }


def _check_rejected_measurements(row: dict[str, Any], problems: list[str]) -> None:
    """Require a positive, finite, integral rejected-import aggregate."""
    rejected = [
        measurement
        for measurement in row.get("measurements", [])
        if measurement.get("attributes", {}).get("catalog.import.outcome") == "rejected"
    ]
    if not rejected:
        problems.append(
            "metrics/catalog.import.records has no measurement with "
            "catalog.import.outcome='rejected'. This signal only appears when an import "
            "actually rejects records -- see TelemetryFaultInjection.md (F-74)."
        )
        return
    for measurement in rejected:
        value = measurement.get("value")
        if type(value) not in (int, float):
            problems.append(f"rejected import measurement value is not numeric: {value!r}")
        elif not math.isfinite(float(value)) or value <= 0 or not float(value).is_integer():
            problems.append(
                f"rejected import measurement must be a positive whole number, got {value!r}"
            )


def _check_route_probe(query_id: str, rows: dict[str, Any], problems: list[str]) -> None:
    """Require the matched-route-template probe in the carrier the gate inspects."""
    signal_name, key = ROUTE_PROBE_CARRIER[query_id]
    observations = rows.get(signal_name, {}).get(key, [])
    if not any(
        all(item.get("attributes", {}).get(k) == v for k, v in ROUTE_PROBE.items())
        for item in observations
    ):
        problems.append(
            f"{query_id}/{signal_name}.{key} lacks the matched route-template probe "
            f"{ROUTE_PROBE}. Exercise GET /figure/{{id}} against a real figure and "
            f"re-capture."
        )


def _normalize_query(
    query_id: str,
    captured: dict[str, Any],
    expectations: dict[str, list[str]],
    behavior: dict[str, Any],
    resource_attributes: dict[str, str],
    problems: list[str],
) -> dict[str, Any]:
    """Turn one captured query into a normalized result document."""
    signals = captured.get("signals", {})
    missing = sorted(set(expectations) - set(signals))
    extra = sorted(set(signals) - set(expectations))
    if missing:
        problems.append(f"{query_id} capture is missing signals: {', '.join(missing)}")
    if extra:
        problems.append(
            f"{query_id} capture has signals outside the frozen contract: {', '.join(extra)}"
        )

    rows: list[dict[str, Any]] = []
    for signal_name in expectations:
        signal = signals.get(signal_name)
        if signal is None:
            continue
        observed = list(signal.get("observedAttributes", []))
        required = set(expectations[signal_name])
        if not required.issubset(observed):
            absent = ", ".join(sorted(required - set(observed)))
            problems.append(f"{query_id}/{signal_name} never observed attributes: {absent}")

        row: dict[str, Any] = {
            "signalName": signal_name,
            "recordCount": signal.get("recordCount", 0),
            "observedAttributes": observed,
        }
        if row["recordCount"] < 1:
            problems.append(
                f"{query_id}/{signal_name} has recordCount {row['recordCount']}; the signal "
                f"was never emitted, so there is nothing to report"
            )
        if query_id == "resources":
            row["resourceAttributes"] = dict(resource_attributes)
        if query_id == "metrics":
            # Supplied from the contract so the attendee never hand-types "{record}".
            row["unit"] = behavior["metricUnits"][signal_name]
            row["measurements"] = list(signal.get("measurements", []))
        if query_id in ("traces", "logs"):
            row["observations"] = list(signal.get("observations", []))
        rows.append(row)

    document = {
        "schemaVersion": "1.0.0",
        "queryId": query_id,
        "rows": rows,
    }
    return document


def render_telemetry_evidence(
    capture_path: Path,
    contracts_directory: Path,
    output_path: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Render the telemetry report and its four result files from a capture manifest.

    Returns a machine-readable inventory of what was written.
    """
    capture = load_json_object(capture_path)
    behavior = json.loads((contracts_directory / "behavior-contract.json").read_text())[
        "telemetry"
    ]
    expectations = _signal_expectations(behavior)
    problems: list[str] = []

    for field in ("workspaceId", "capturedAt", "service", "resourceAttributes", "queries"):
        if not capture.get(field):
            problems.append(f"capture manifest is missing required field '{field}'")
    if problems:
        raise TelemetryCaptureError(problems)

    resource_attributes = dict(capture["resourceAttributes"])
    missing_resource = set(behavior["requiredResourceAttributes"]) - set(resource_attributes)
    if missing_resource:
        problems.append(
            f"resourceAttributes is missing: {', '.join(sorted(missing_resource))}"
        )

    result_dir = output_path.parent / "telemetry"
    queries: dict[str, Any] = {}
    documents: dict[str, dict[str, Any]] = {}

    for query_id in QUERY_IDS:
        captured = capture["queries"].get(query_id)
        if captured is None:
            problems.append(f"capture manifest has no '{query_id}' query")
            continue
        query_text = captured.get("query", "")
        if len(query_text) < 10:
            problems.append(
                f"{query_id} query text is missing or too short to be a real query"
            )
        document = _normalize_query(
            query_id,
            captured,
            expectations[query_id],
            behavior,
            resource_attributes,
            problems,
        )
        # Provenance: possible since 9c17c6d, and always populated by this renderer.
        document["workspaceId"] = capture["workspaceId"]
        document["capturedAt"] = capture["capturedAt"]
        document["queryText"] = query_text
        documents[query_id] = document

        rows = {row["signalName"]: row for row in document["rows"]}
        if query_id == "metrics" and "catalog.import.records" in rows:
            _check_rejected_measurements(rows["catalog.import.records"], problems)
        if query_id in ROUTE_PROBE_CARRIER:
            _check_route_probe(query_id, rows, problems)

        relative = (result_dir / f"{query_id}.json").relative_to(repository_root)
        queries[query_id] = {
            "query": query_text,
            "resultFile": relative.as_posix(),
            "expectedSignalNames": list(expectations[query_id]),
        }

    if problems:
        raise TelemetryCaptureError(problems)

    result_dir.mkdir(parents=True, exist_ok=True)
    for query_id, document in documents.items():
        (result_dir / f"{query_id}.json").write_text(
            json.dumps(document, indent=2) + "\n"
        )

    report = {
        "schemaVersion": "1.0.0",
        "capturedAt": capture["capturedAt"],
        "service": capture["service"],
        "resourceAttributes": resource_attributes,
        "queries": queries,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n")

    return {
        "report": output_path.relative_to(repository_root).as_posix(),
        "resultFiles": [queries[q]["resultFile"] for q in QUERY_IDS],
        "signalCounts": {q: len(documents[q]["rows"]) for q in QUERY_IDS},
        "workspaceId": capture["workspaceId"],
        "capturedAt": capture["capturedAt"],
    }
