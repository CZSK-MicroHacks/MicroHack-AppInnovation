"""End-to-end coverage for the telemetry evidence renderer (F-89).

The load-bearing test renders a bundle and submits it to the *real* handoff gate,
``_validate_telemetry_results``. The gate re-reads the behavior contract itself, so
acceptance is not self-consistency between the renderer and its own fixture.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from catalog_acceptance.handoff import _validate_telemetry_results
from catalog_acceptance.telemetry_evidence import (
    TelemetryCaptureError,
    render_telemetry_evidence,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = REPO_ROOT / "workshop" / "contracts"
REVISION = "ca-mh-catalog-user001--release-47acf263d332"

ROUTE_ATTRS = {
    "http.request.method": "GET",
    "http.route": "/figure/{id}",
    "http.response.status_code": 200,
    "server.address": "localhost",
}


def _behavior() -> dict[str, Any]:
    return json.loads((CONTRACTS / "behavior-contract.json").read_text())["telemetry"]


def _capture() -> dict[str, Any]:
    """Build a capture manifest describing a fully exercised application."""
    behavior = _behavior()
    resource_attributes = {
        name: "observed" for name in behavior["requiredResourceAttributes"]
    }

    def signals(spec: dict[str, list[str]], kind: str) -> dict[str, Any]:
        built: dict[str, Any] = {}
        for name, attributes in spec.items():
            entry: dict[str, Any] = {
                "recordCount": 7,
                "observedAttributes": list(attributes),
            }
            payload = {"attributes": {a: "observed" for a in attributes}}
            if kind == "metrics":
                entry["measurements"] = [{"value": 1.5, **payload}]
            else:
                entry["observations"] = [payload]
            built[name] = entry
        return built

    traces = signals(behavior["traces"], "traces")
    metrics = signals(behavior["metrics"], "metrics")
    logs = signals(behavior["logs"], "logs")

    # The route probe the gate demands, in each of its three carriers.
    traces["http.server"]["observations"].append({"attributes": dict(ROUTE_ATTRS)})
    logs["http.server.request"]["observations"].append({"attributes": dict(ROUTE_ATTRS)})
    metrics["http.server.request.duration"]["measurements"].append(
        {"value": 0.02, "attributes": dict(ROUTE_ATTRS)}
    )
    # The rejected-import aggregate, which only exists after a real rejection.
    metrics["catalog.import.records"]["measurements"].append(
        {"value": 3, "attributes": {"catalog.import.outcome": "rejected"}}
    )

    return {
        "schemaVersion": "1.0.0",
        "workspaceId": "/subscriptions/s/resourceGroups/r/providers/"
        "Microsoft.OperationalInsights/workspaces/w",
        "capturedAt": "2026-08-27T22:05:00Z",
        "service": "mh-catalog-java",
        "resourceAttributes": resource_attributes,
        "queries": {
            "resources": {
                "query": "AppDependencies | where TimeGenerated > ago(30m)",
                "revision": REVISION,
                "signals": {
                    "resource": {
                        "recordCount": 1,
                        "observedAttributes": list(
                            behavior["requiredResourceAttributes"]
                        ),
                    }
                },
            },
            "traces": {
                "query": "AppDependencies | project Name",
                "revision": REVISION,
                "signals": traces,
            },
            "metrics": {
                "query": "AppMetrics | project Name",
                "revision": REVISION,
                "signals": metrics,
            },
            "logs": {
                "query": "AppTraces | project Message",
                "revision": REVISION,
                "signals": logs,
            },
        },
    }


def _render(root: Path, capture: dict[str, Any]) -> dict[str, Any]:
    capture_path = root / "evidence" / "telemetry-capture.json"
    capture_path.parent.mkdir(parents=True, exist_ok=True)
    capture_path.write_text(json.dumps(capture))
    return render_telemetry_evidence(
        capture_path, CONTRACTS, root / "evidence" / "telemetry-report.json", root
    )


def test_rendered_bundle_is_accepted_by_the_real_handoff_gate(tmp_path: Path) -> None:
    """The deliverable, not the diff: render then submit to the gate that judges it."""
    _render(tmp_path, _capture())
    report = json.loads((tmp_path / "evidence" / "telemetry-report.json").read_text())
    _validate_telemetry_results(report, CONTRACTS, tmp_path)


def test_renderer_supplies_metric_units_so_they_are_never_hand_typed(
    tmp_path: Path,
) -> None:
    """`{record}` is contract data, not something an attendee should retype."""
    capture = _capture()
    for signal in capture["queries"]["metrics"]["signals"].values():
        assert "unit" not in signal
    _render(tmp_path, capture)
    metrics = json.loads((tmp_path / "evidence" / "telemetry" / "metrics.json").read_text())
    units = {row["signalName"]: row["unit"] for row in metrics["rows"]}
    assert units["catalog.import.records"] == "{record}"
    assert units["http.server.request.duration"] == "s"


def test_renderer_stamps_provenance_into_every_result_file(tmp_path: Path) -> None:
    """F-89's point: evidence must be able to say where it came from."""
    capture = _capture()
    _render(tmp_path, capture)
    for query_id in ("resources", "traces", "metrics", "logs"):
        document = json.loads(
            (tmp_path / "evidence" / "telemetry" / f"{query_id}.json").read_text()
        )
        assert document["workspaceId"] == capture["workspaceId"]
        assert document["capturedAt"] == capture["capturedAt"]
        assert len(document["queryText"]) >= 10


def test_missing_signal_is_reported_and_never_invented(tmp_path: Path) -> None:
    """A signal that was never observed must fail, not be defaulted into existence."""
    capture = _capture()
    del capture["queries"]["logs"]["signals"]["catalog.database.failed"]
    with pytest.raises(TelemetryCaptureError) as error:
        _render(tmp_path, capture)
    assert any("catalog.database.failed" in p for p in error.value.problems)
    assert not (tmp_path / "evidence" / "telemetry" / "logs.json").exists()


def test_every_problem_is_reported_in_one_run(tmp_path: Path) -> None:
    """The gate raises one ValueError at a time; the renderer must not."""
    capture = _capture()
    del capture["queries"]["logs"]["signals"]["exception"]
    del capture["queries"]["traces"]["signals"]["db.client"]
    capture["queries"]["metrics"]["signals"]["catalog.import.records"]["measurements"] = [
        {"value": 5, "attributes": {"catalog.import.outcome": "inserted"}}
    ]
    with pytest.raises(TelemetryCaptureError) as error:
        _render(tmp_path, capture)
    problems = "\n".join(error.value.problems)
    assert len(error.value.problems) >= 3
    assert "exception" in problems
    assert "db.client" in problems
    assert "rejected" in problems


def test_missing_route_probe_is_reported_with_actionable_guidance(
    tmp_path: Path,
) -> None:
    """The three-carrier route probe is the least discoverable gate rule."""
    capture = _capture()
    capture["queries"]["traces"]["signals"]["http.server"]["observations"] = [
        {"attributes": {a: "observed" for a in _behavior()["traces"]["http.server"]}}
    ]
    with pytest.raises(TelemetryCaptureError) as error:
        _render(tmp_path, capture)
    joined = "\n".join(error.value.problems)
    assert "route-template probe" in joined
    assert "/figure/{id}" in joined


@pytest.mark.parametrize(
    "value", [0, -3, 2.5, float("inf")], ids=["zero", "negative", "fractional", "infinite"]
)
def test_rejected_import_aggregate_must_be_positive_and_integral(
    tmp_path: Path, value: float
) -> None:
    """Mirror the gate's arithmetic so it is caught locally, not at handoff.

    ``ValueError`` rather than ``TelemetryCaptureError`` because the infinite case is
    caught even earlier: ``artifact_io`` refuses to parse the non-standard ``Infinity``
    constant, so a non-finite aggregate cannot survive being written to a capture file.
    """
    capture = _capture()
    capture["queries"]["metrics"]["signals"]["catalog.import.records"]["measurements"] = [
        {"value": value, "attributes": {"catalog.import.outcome": "rejected"}}
    ]
    with pytest.raises(ValueError):
        _render(tmp_path, capture)


def test_absent_rejection_points_at_the_fault_injection_runbook(tmp_path: Path) -> None:
    """F-74 compounds F-89, so the error must name the way out."""
    capture = _capture()
    capture["queries"]["metrics"]["signals"]["catalog.import.records"]["measurements"] = [
        {"value": 5, "attributes": {"catalog.import.outcome": "inserted"}}
    ]
    with pytest.raises(TelemetryCaptureError) as error:
        _render(tmp_path, capture)
    assert any("TelemetryFaultInjection" in p for p in error.value.problems)


def test_signal_outside_the_frozen_contract_is_rejected(tmp_path: Path) -> None:
    """Set equality, not superset: an extra signal is a capture error."""
    capture = _capture()
    capture["queries"]["traces"]["signals"]["made.up.signal"] = {
        "recordCount": 1,
        "observedAttributes": ["x"],
        "observations": [{"attributes": {"x": "y"}}],
    }
    with pytest.raises(TelemetryCaptureError) as error:
        _render(tmp_path, capture)
    assert any("made.up.signal" in p for p in error.value.problems)


def test_unobserved_signal_with_zero_records_is_rejected(tmp_path: Path) -> None:
    """recordCount 0 means the signal never fired; that is not evidence."""
    capture = _capture()
    capture["queries"]["traces"]["signals"]["db.client"]["recordCount"] = 0
    with pytest.raises(TelemetryCaptureError) as error:
        _render(tmp_path, capture)
    assert any("never emitted" in p for p in error.value.problems)


def test_missing_manifest_field_fails_before_any_file_is_written(
    tmp_path: Path,
) -> None:
    """A capture without provenance cannot produce evidence at all."""
    capture = _capture()
    del capture["workspaceId"]
    with pytest.raises(TelemetryCaptureError) as error:
        _render(tmp_path, capture)
    assert any("workspaceId" in p for p in error.value.problems)
    assert not (tmp_path / "evidence" / "telemetry").exists()


def test_cli_reports_problems_as_json_and_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Failures stay machine-readable, matching the sibling evidence CLIs."""
    from catalog_acceptance.telemetry_evidence_cli import render_main

    capture = _capture()
    del capture["queries"]["metrics"]["signals"]["catalog.query.duration"]
    path = tmp_path / "evidence" / "telemetry-capture.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(capture))

    code = render_main(
        [
            "--capture",
            "evidence/telemetry-capture.json",
            "--repository-root",
            str(tmp_path),
            "--contracts",
            str(CONTRACTS),
        ]
    )
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert any("catalog.query.duration" in p for p in payload["problems"])


def test_cli_renders_and_reports_inventory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The success path prints what it wrote, including provenance."""
    from catalog_acceptance.telemetry_evidence_cli import render_main

    path = tmp_path / "evidence" / "telemetry-capture.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_capture()))

    code = render_main(
        [
            "--capture",
            "evidence/telemetry-capture.json",
            "--repository-root",
            str(tmp_path),
            "--contracts",
            str(CONTRACTS),
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "rendered"
    assert payload["signalCounts"] == {
        "resources": 1,
        "traces": 6,
        "metrics": 5,
        "logs": 8,
    }
    assert payload["workspaceId"].endswith("/workspaces/w")


RENDERER_DOCUMENTS = (
    "challenges/ch01-copilot-modernization/README.md",
    "challenges/ch01-copilot-rewrite/README.md",
    "challenges/ch01-manual/README.md",
    "solutions/ch01-copilot-modernization/dotnet/README.md",
    "solutions/ch01-copilot-modernization/java/README.md",
    "solutions/ch01-copilot-rewrite/dotnet/README.md",
    "solutions/ch01-copilot-rewrite/java/README.md",
    "solutions/ch01-manual/dotnet/README.md",
    "solutions/ch01-manual/java/README.md",
)


@pytest.mark.parametrize("relative", RENDERER_DOCUMENTS)
def test_every_document_that_directs_telemetry_work_names_the_renderer(
    relative: str,
) -> None:
    """F-86's lesson, applied before shipping rather than after.

    A producer that no runbook mentions is a half-landed fix: participants execute
    runbooks, not briefs, and a tool nobody is told about leaves the hand-authoring
    path in place.
    """
    text = (REPO_ROOT / relative).read_text()
    assert "telemetry_evidence_cli" in text, f"{relative} never names the renderer"


def test_renderer_document_list_cannot_silently_shrink() -> None:
    """Vacuity floor: the guard above is worthless if the list is trimmed."""
    assert len(RENDERER_DOCUMENTS) >= 9
    for relative in RENDERER_DOCUMENTS:
        assert (REPO_ROOT / relative).is_file(), relative


def test_every_rendered_document_satisfies_the_result_schema(tmp_path: Path) -> None:
    """The gap that let F-91 ship: nothing validated output against the contract.

    The three sibling renderers all import ``jsonschema`` and validate against
    checked-in schemas. This one did not, and fifteen tests never noticed.
    """
    from jsonschema import Draft202012Validator, FormatChecker

    _render(tmp_path, _capture())
    schema = json.loads((CONTRACTS / "telemetry-query-result.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    directory = tmp_path / "evidence" / "telemetry"
    rendered = sorted(path.name for path in directory.glob("*.json"))
    assert rendered == ["logs.json", "metrics.json", "resources.json", "traces.json"]
    for path in directory.glob("*.json"):
        errors = list(validator.iter_errors(json.loads(path.read_text())))
        assert not errors, f"{path.name}: {[error.message for error in errors]}"


def test_empty_observations_are_refused_at_render_time_not_at_the_handoff_gate(
    tmp_path: Path,
) -> None:
    """F-91, reported by the .NET modernization arm and reproduced here.

    A non-carrier signal with no observations passed every renderer check and
    produced a document violating ``minItems: 1``. The attendee would have met
    it as one ``ValidationError`` at the end of the chapter.
    """
    capture = _capture()
    victim = next(
        name
        for name in capture["queries"]["traces"]["signals"]
        if name != "http.server"
    )
    capture["queries"]["traces"]["signals"][victim]["observations"] = []

    with pytest.raises(TelemetryCaptureError) as caught:
        _render(tmp_path, capture)

    message = str(caught.value)
    assert "traces" in message
    assert "observations" in message
    assert "non-empty" in message or "minItems" in message


def test_an_output_outside_the_repository_is_a_handled_error(tmp_path: Path) -> None:
    """Was a raw ``relative_to`` traceback; symlinked scratch dirs hit it routinely."""
    root = tmp_path / "repo"
    (root / "evidence").mkdir(parents=True)
    capture_path = root / "evidence" / "telemetry-capture.json"
    capture_path.write_text(json.dumps(_capture()))

    with pytest.raises(TelemetryCaptureError) as caught:
        render_telemetry_evidence(
            capture_path, CONTRACTS, tmp_path / "outside" / "report.json", root
        )
    assert "--output must be inside the repository" in str(caught.value)


def test_renderer_validates_against_the_same_schema_the_gate_uses(tmp_path: Path) -> None:
    """Guard the guard: the module must carry real schema machinery, not literals.

    ``telemetry_evidence.py`` previously contained the string ``schema`` only in
    the ``schemaVersion`` values it wrote out.
    """
    source = (
        Path(__file__).resolve().parents[1]
        / "catalog_acceptance"
        / "telemetry_evidence.py"
    ).read_text()
    assert "Draft202012Validator" in source
    assert "telemetry-query-result.schema.json" in source


def test_capture_example_validates_against_the_capture_schema() -> None:
    """Telemetry shipped neither a capture schema nor an example; the other three did.

    Reported by the .NET modernization arm as part of F-91: the manifest shape
    had to be reverse-engineered from renderer source, which is the same burden
    F-89 was about, moved from the output format to the input format.
    """
    from jsonschema import Draft202012Validator, FormatChecker

    schema = json.loads(
        (CONTRACTS / "telemetry-evidence-capture.schema.json").read_text()
    )
    example = json.loads(
        (CONTRACTS / "telemetry-evidence-capture.example.json").read_text()
    )
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(example)
    )
    assert not errors, [error.message for error in errors]


def test_capture_example_renders_a_bundle_the_handoff_gate_accepts(
    tmp_path: Path,
) -> None:
    """The example is only worth shipping if it actually works end to end."""
    example = json.loads(
        (CONTRACTS / "telemetry-evidence-capture.example.json").read_text()
    )
    _render(tmp_path, example)
    report = json.loads((tmp_path / "evidence" / "telemetry-report.json").read_text())
    _validate_telemetry_results(report, CONTRACTS, tmp_path)


def test_capture_manifest_is_validated_against_its_schema(tmp_path: Path) -> None:
    """An unknown key must be refused here, not silently ignored into the bundle."""
    capture = _capture()
    capture["queries"]["traces"]["signals"]["http.server"]["typo"] = True
    with pytest.raises(TelemetryCaptureError) as caught:
        _render(tmp_path, capture)
    assert "telemetry-evidence-capture.schema.json" in str(caught.value)


def test_workspace_provenance_is_cross_checked_against_the_deployed_target(
    tmp_path: Path,
) -> None:
    """Provenance nothing reads is decoration; give it a failure mode.

    Proposed by the .NET modernization arm alongside F-91. Entirely offline,
    between two artifacts the attendee already holds.
    """
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence" / "azure-target-output.json").write_text(
        json.dumps(
            {
                "observability": {
                    "logAnalyticsWorkspaceResourceId": (
                        "/subscriptions/s/resourceGroups/g/providers/"
                        "Microsoft.OperationalInsights/workspaces/log-real-workspace"
                    )
                }
            }
        )
    )
    capture = _capture()
    capture["workspaceId"] = "log-some-other-workspace"

    with pytest.raises(TelemetryCaptureError) as caught:
        _render(tmp_path, capture)
    message = str(caught.value)
    assert "log-real-workspace" in message
    assert "Two workspaces exist" in message


def test_matching_workspace_provenance_renders_cleanly(tmp_path: Path) -> None:
    """The cross-check must not obstruct an attendee who measured correctly."""
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    capture = _capture()
    (tmp_path / "evidence" / "azure-target-output.json").write_text(
        json.dumps(
            {
                "observability": {
                    "logAnalyticsWorkspaceResourceId": (
                        "/subscriptions/s/resourceGroups/g/providers/"
                        f"Microsoft.OperationalInsights/workspaces/{capture['workspaceId']}"
                    )
                }
            }
        )
    )
    _render(tmp_path, capture)
    report = json.loads((tmp_path / "evidence" / "telemetry-report.json").read_text())
    _validate_telemetry_results(report, CONTRACTS, tmp_path)


def test_every_renderer_document_points_at_the_capture_schema_and_example() -> None:
    """Half of F-91 was discoverability: the manifest shape existed only in source.

    A schema and an example the attendee cannot find are the same as no schema and
    no example, which is the condition F-89 was about.
    """
    repo_root = Path(__file__).resolve().parents[3]
    missing = [
        document
        for document in RENDERER_DOCUMENTS
        if "telemetry-evidence-capture.schema.json"
        not in (repo_root / document).read_text(encoding="utf-8")
        or "telemetry-evidence-capture.example.json"
        not in (repo_root / document).read_text(encoding="utf-8")
    ]
    assert not missing, f"documents omit the capture schema or example: {missing}"
    assert len(RENDERER_DOCUMENTS) >= 9


def test_a_skipped_provenance_check_says_so_rather_than_passing_silently(
    tmp_path: Path,
) -> None:
    """A check that can decline to run without saying so is decoration again.

    ``azure-target-output.json`` is resolved beside ``--output``, so rendering to
    a scratch path to inspect the bundle -- the natural iteration loop -- turned
    the cross-check off. A skipped check and a passing check were byte-identical.
    """
    capture_path = tmp_path / "evidence" / "telemetry-capture.json"
    capture_path.parent.mkdir(parents=True, exist_ok=True)
    capture_path.write_text(json.dumps(_capture()))
    inventory = render_telemetry_evidence(
        capture_path, CONTRACTS, tmp_path / "scratch" / "telemetry-report.json", tmp_path
    )
    assert inventory["provenanceCheck"].startswith("skipped:")
    assert "azure-target-output.json" in inventory["provenanceCheck"]


def test_a_performed_provenance_check_is_reported_as_verified(tmp_path: Path) -> None:
    capture = _capture()
    evidence = tmp_path / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "azure-target-output.json").write_text(
        json.dumps(
            {
                "observability": {
                    "logAnalyticsWorkspaceResourceId": (
                        "/subscriptions/x/resourceGroups/y/providers/"
                        "Microsoft.OperationalInsights/workspaces/"
                        + capture["workspaceId"].rsplit("/", 1)[-1]
                    )
                }
            }
        ),
        encoding="utf-8",
    )
    inventory = _render(tmp_path, capture)
    assert inventory["provenanceCheck"] == "verified"


def test_a_capture_mixing_revisions_is_refused(tmp_path: Path) -> None:
    """The failure signals came from one revision and the happy path from another.

    Fault injection and traffic generation are separate steps; a release between
    them repoints traffic silently. Nothing downstream compares revisions, so the
    mixed capture passes the handoff gate while asserting behaviour the release
    revision never emitted.
    """
    capture = _capture()
    capture["queries"]["logs"]["revision"] = "ca-mh-catalog-user001--0000001"
    with pytest.raises(TelemetryCaptureError) as excinfo:
        _render(tmp_path, capture)
    message = str(excinfo.value)
    assert "2 different revisions" in message
    assert "ca-mh-catalog-user001--0000001" in message
    assert "AppRoleInstance" in message
