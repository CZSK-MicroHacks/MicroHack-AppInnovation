"""Executable contracts for deterministic Challenge 2 evidence rendering."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
import pytest

from catalog_acceptance.load_evidence import build_load_evidence
from catalog_acceptance.load_evidence_cli import main as render_main


def _load(path: Path) -> dict[str, Any]:
    """Load one test JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    """Write one deterministic test JSON object."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    """Return one test file digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prepare_renderer_repository(
    tmp_path: Path,
    repo_root: Path,
    *,
    database_family: str = "azure-sql",
) -> tuple[Path, Path, Path]:
    """Create one complete digest-bound renderer input tree."""
    repository = tmp_path / "repository"
    contracts = repo_root / "workshop/contracts"
    fixtures = contracts / "fixtures/load"
    raw = repository / "evidence/load/raw"
    raw.mkdir(parents=True)
    for source, destination in (
        ("test-run.json", "test-run.json"),
        ("container-app.json", "container-app.json"),
        ("replicas.json", "replicas.json"),
        (
            "azure-sql.json"
            if database_family == "azure-sql"
            else "postgresql.json",
            "database.json",
        ),
    ):
        shutil.copyfile(fixtures / source, raw / destination)

    load_test = repository / "tests/load/load-test.yaml"
    jmeter = repository / "tests/load/catalog-load.jmx"
    load_test.parent.mkdir(parents=True)
    load_test.write_text("version: v0.1\n", encoding="utf-8")
    jmeter.write_text("<jmeterTestPlan/>\n", encoding="utf-8")

    handoff = _load(contracts / "modernization-contract.example.json")
    if database_family == "postgresql-flexible":
        handoff["sliceId"] = "manual-java"
        handoff["source"]["stack"] = "java-postgresql"
        handoff["database"]["family"] = "postgresql-flexible"
        handoff["database"]["resourceId"] = (
            "/subscriptions/00000000-0000-0000-0000-000000000000/"
            "resourceGroups/rg-mh-example/providers/"
            "Microsoft.DBforPostgreSQL/flexibleServers/psql-example"
        )
    handoff_path = repository / "evidence/modernization-contract.json"
    _write(handoff_path, handoff)

    capture = _load(contracts / "load-evidence-capture.example.json")
    capture["artifacts"]["configurationSha256"] = _sha256(load_test)
    capture["artifacts"]["jmeterSha256"] = _sha256(jmeter)
    if database_family == "postgresql-flexible":
        database_path = raw / "database.json"
        capture["databaseSignal"].update(
            {
                "sha256": _sha256(database_path),
                "resourceId": handoff["database"]["resourceId"],
                "metricName": "cpu_percent",
                "aggregation": "Maximum",
            }
        )
    capture_path = repository / "evidence/load/capture.json"
    _write(capture_path, capture)
    return repository, capture_path, handoff_path


@pytest.mark.parametrize(
    ("database_family", "metric", "aggregation"),
    [
        ("azure-sql", "app_cpu_billed", "Total"),
        ("postgresql-flexible", "cpu_percent", "Maximum"),
    ],
)
def test_renderer_builds_both_database_family_bundles(
    tmp_path: Path,
    repo_root: Path,
    database_family: str,
    metric: str,
    aggregation: str,
) -> None:
    """Raw Azure fixtures render to exact report and observation contracts."""
    repository, capture_path, handoff_path = _prepare_renderer_repository(
        tmp_path,
        repo_root,
        database_family=database_family,
    )

    report, observations = build_load_evidence(
        capture_path,
        handoff_path,
        repository,
    )
    schema = _load(repo_root / "workshop/contracts/load-test-evidence.schema.json")
    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(report)

    assert report["schemaVersion"] == "1.1.0"
    assert report["databaseSignal"] == {
        "resourceId": report["subject"]["databaseResourceId"],
        "family": database_family,
        "metric": metric,
        "aggregation": aggregation,
        "baseline": 4.0 if database_family == "azure-sql" else 5.0,
        "peak": 12.0 if database_family == "azure-sql" else 40.0,
        "unit": "count" if database_family == "azure-sql" else "percent",
        "resultFile": "evidence/load/database.json",
    }
    assert report["replicas"]["baselineObserved"] == 1
    assert report["replicas"]["peakObserved"] == 3
    assert report["recovery"]["observedReplicas"] == 1
    assert set(observations) == {
        "evidence/load/test-run.json",
        "evidence/load/scale-configuration.json",
        "evidence/load/replicas.json",
        "evidence/load/database.json",
        "evidence/load/recovery.json",
    }
    assert all(
        observation["schemaVersion"] == "1.1.0"
        for observation in observations.values()
    )


def test_renderer_cli_writes_a_deterministic_complete_bundle(
    tmp_path: Path,
    repo_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The public CLI writes every declared output and returns JSON status."""
    repository, capture_path, handoff_path = _prepare_renderer_repository(
        tmp_path,
        repo_root,
    )
    arguments = [
        "--capture",
        str(capture_path.relative_to(repository)),
        "--handoff",
        str(handoff_path.relative_to(repository)),
        "--output",
        "evidence/load-test-report.json",
        "--repository-root",
        str(repository),
    ]

    assert render_main(arguments) == 0
    first = {
        path: (repository / path).read_bytes()
        for path in (
            "evidence/load-test-report.json",
            "evidence/load/test-run.json",
            "evidence/load/scale-configuration.json",
            "evidence/load/replicas.json",
            "evidence/load/database.json",
            "evidence/load/recovery.json",
        )
    }
    assert render_main(arguments) == 0
    assert first == {
        path: (repository / path).read_bytes() for path in first
    }
    statuses = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line
    ]
    assert statuses == [
        {
            "status": "passed",
            "schemaVersion": "1.1.0",
            "report": "evidence/load-test-report.json",
            "observations": [
                "evidence/load/database.json",
                "evidence/load/recovery.json",
                "evidence/load/replicas.json",
                "evidence/load/scale-configuration.json",
                "evidence/load/test-run.json",
            ],
        },
        {
            "status": "passed",
            "schemaVersion": "1.1.0",
            "report": "evidence/load-test-report.json",
            "observations": [
                "evidence/load/database.json",
                "evidence/load/recovery.json",
                "evidence/load/replicas.json",
                "evidence/load/scale-configuration.json",
                "evidence/load/test-run.json",
            ],
        },
    ]


def test_renderer_rejects_delayed_scale_out_as_recovery(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """A post-load scale-out cannot satisfy the in-load scaling assertion."""
    repository, capture_path, handoff_path = _prepare_renderer_repository(
        tmp_path,
        repo_root,
    )
    raw_path = repository / "evidence/load/raw/replicas.json"
    raw = _load(raw_path)
    data = raw["value"][0]["timeseries"][0]["data"]
    for point in data:
        if any(
            timestamp in point["timeStamp"]
            for timestamp in ("12:02:00Z", "12:04:00Z", "12:05:00Z")
        ):
            point["maximum"] = 1
    _write(raw_path, raw)
    capture = _load(capture_path)
    capture["replicas"]["sha256"] = _sha256(raw_path)
    _write(capture_path, capture)

    with pytest.raises(ValueError, match="in-load scale-out"):
        build_load_evidence(capture_path, handoff_path, repository)


def test_renderer_rejects_missing_metric_values(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """Missing Azure Monitor values are never normalized as zero."""
    repository, capture_path, handoff_path = _prepare_renderer_repository(
        tmp_path,
        repo_root,
    )
    raw_path = repository / "evidence/load/raw/replicas.json"
    raw = _load(raw_path)
    del raw["value"][0]["timeseries"][0]["data"][0]["maximum"]
    _write(raw_path, raw)
    capture = _load(capture_path)
    capture["replicas"]["sha256"] = _sha256(raw_path)
    _write(capture_path, capture)

    with pytest.raises(ValueError, match="maximum must be a number"):
        build_load_evidence(capture_path, handoff_path, repository)


def test_renderer_rejects_raw_capture_digest_drift(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """A raw response cannot change after the capture manifest is signed."""
    repository, capture_path, handoff_path = _prepare_renderer_repository(
        tmp_path,
        repo_root,
    )
    raw_path = repository / "evidence/load/raw/test-run.json"
    raw = deepcopy(_load(raw_path))
    raw["testRunStatistics"]["Total"]["sampleCount"] += 1
    _write(raw_path, raw)

    with pytest.raises(ValueError, match="raw capture digest mismatch"):
        build_load_evidence(capture_path, handoff_path, repository)


def test_renderer_cli_rejects_output_collision(
    tmp_path: Path,
    repo_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CLI cannot replace a normalized observation with the report."""
    repository, capture_path, handoff_path = _prepare_renderer_repository(
        tmp_path,
        repo_root,
    )

    assert (
        render_main(
            [
                "--capture",
                str(capture_path.relative_to(repository)),
                "--handoff",
                str(handoff_path.relative_to(repository)),
                "--output",
                "evidence/load/test-run.json",
                "--repository-root",
                str(repository),
            ]
        )
        == 1
    )
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "failed"
    assert "must be evidence/load-test-report.json" in result["error"]
    assert not (repository / "evidence/load/test-run.json").exists()
    assert not (repository / "evidence/load-test-report.json").exists()


def test_renderer_enforces_raw_capture_schema_paths(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """Pydantic-valid paths outside the frozen raw directory are rejected."""
    repository, capture_path, handoff_path = _prepare_renderer_repository(
        tmp_path,
        repo_root,
    )
    capture = _load(capture_path)
    capture["testRun"]["file"] = "evidence/load/not-raw.json"
    _write(capture_path, capture)

    with pytest.raises(
        ValueError,
        match="load capture manifest violates its frozen schema",
    ):
        build_load_evidence(capture_path, handoff_path, repository)


def test_renderer_rejects_capture_output_self_overwrite(
    tmp_path: Path,
    repo_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The canonical report cannot be supplied as its own capture input."""
    repository, capture_path, handoff_path = _prepare_renderer_repository(
        tmp_path,
        repo_root,
    )
    collision_path = repository / "evidence/load-test-report.json"
    shutil.copyfile(capture_path, collision_path)
    original = collision_path.read_bytes()

    assert (
        render_main(
            [
                "--capture",
                str(collision_path.relative_to(repository)),
                "--handoff",
                str(handoff_path.relative_to(repository)),
                "--output",
                str(collision_path.relative_to(repository)),
                "--repository-root",
                str(repository),
            ]
        )
        == 1
    )
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "failed"
    assert "must be evidence/load/capture.json" in result["error"]
    assert collision_path.read_bytes() == original


def test_renderer_rejects_duplicate_raw_json_members(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """Duplicate source members cannot change meaning across JSON decoders."""
    repository, capture_path, handoff_path = _prepare_renderer_repository(
        tmp_path,
        repo_root,
    )
    raw_path = repository / "evidence/load/raw/test-run.json"
    raw_path.write_text(
        '{"testRunId":"one","testRunId":"two"}\n',
        encoding="utf-8",
    )
    capture = _load(capture_path)
    capture["testRun"]["sha256"] = _sha256(raw_path)
    _write(capture_path, capture)

    with pytest.raises(ValueError, match="duplicate JSON member"):
        build_load_evidence(capture_path, handoff_path, repository)
