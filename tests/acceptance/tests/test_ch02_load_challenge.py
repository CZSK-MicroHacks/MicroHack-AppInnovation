"""Executable producer checks for the refrozen load challenge."""

from copy import deepcopy
import hashlib
import json
import re
from pathlib import Path
import shutil
import xml.etree.ElementTree as ElementTree

import pytest

from catalog_acceptance import shared_challenges
from catalog_acceptance.load_evidence_cli import main as render_main
from catalog_acceptance.manifest import load_json


ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "workshop/contracts"
FIXTURES = CONTRACTS / "fixtures/load"
CONFIGURATION = ROOT / "tests/load/load-test.yaml"
JMETER = ROOT / "tests/load/catalog-load.jmx"
GUIDES = (ROOT / "challenges/ch02/README.md", ROOT / "solutions/ch02/README.md")
SLICES = (
    ("manual-dotnet", "dotnet-sqlserver", "azure-sql"),
    ("manual-java", "java-postgresql", "postgresql-flexible"),
    ("copilot-rewrite-dotnet", "dotnet-sqlserver", "azure-sql"),
    ("copilot-rewrite-java", "java-postgresql", "postgresql-flexible"),
    ("copilot-modernization-dotnet", "dotnet-sqlserver", "azure-sql"),
    ("copilot-modernization-java", "java-postgresql", "postgresql-flexible"),
)


def _write_json(path: Path, value: dict[str, object]) -> None:
    """Write one deterministic test JSON object."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    """Return one lowercase file digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_bounded_jmeter(path: Path) -> None:
    """Require the exact no-redirect bounded sampler behavior."""
    root = ElementTree.parse(path).getroot()
    thread_group = root.find(".//ThreadGroup")
    assert thread_group is not None
    thread_properties = {
        element.attrib["name"]: element.text
        for element in thread_group
        if element.tag in {"stringProp", "boolProp"}
    }
    assert thread_properties["ThreadGroup.num_threads"] == "80"
    assert thread_properties["ThreadGroup.duration"] == "300"
    assert thread_properties["ThreadGroup.scheduler"] == "true"
    assert thread_properties["ThreadGroup.on_sample_error"] == "stoptestnow"

    samplers = root.findall(".//HTTPSamplerProxy")
    assert len(samplers) == 1
    sampler_properties = {
        element.attrib["name"]: element.text
        for element in samplers[0]
        if element.tag in {"stringProp", "boolProp"}
    }
    assert sampler_properties["HTTPSampler.protocol"] == "https"
    assert sampler_properties["HTTPSampler.domain"] == "${catalog_base_host}"
    assert sampler_properties["HTTPSampler.path"] == "/perftest/catalog"
    assert sampler_properties["HTTPSampler.method"] == "GET"
    assert sampler_properties["HTTPSampler.follow_redirects"] == "false"
    assert sampler_properties["HTTPSampler.auto_redirects"] == "false"

    assertions = root.findall(".//ResponseAssertion")
    assert len(assertions) == 1
    assertion_properties = {
        element.attrib["name"]: element.text
        for element in assertions[0]
        if element.tag in {"stringProp", "intProp"}
    }
    assert assertion_properties["Assertion.test_field"] == "Assertion.response_code"
    assert assertion_properties["Assertion.test_type"] == "8"
    response_codes = assertions[0].find(
        './collectionProp[@name="Asserion.test_strings"]'
    )
    assert response_codes is not None
    assert [element.text for element in response_codes] == ["200"]


def _prepare_capture(
    repository: Path,
    slice_id: str,
    stack: str,
    database_family: str,
) -> tuple[Path, Path, dict[str, object]]:
    """Create one raw-capture tree that exercises the frozen renderer."""
    raw = repository / "evidence/load/raw"
    raw.mkdir(parents=True)
    database_fixture = (
        "azure-sql.json"
        if database_family == "azure-sql"
        else "postgresql.json"
    )
    for source, destination in (
        ("test-run.json", "test-run.json"),
        ("container-app.json", "container-app.json"),
        ("replicas.json", "replicas.json"),
        (database_fixture, "database.json"),
    ):
        shutil.copyfile(FIXTURES / source, raw / destination)

    test_run = load_json(raw / "test-run.json")
    test_run["testId"] = "catalog-autoscaling"
    test_run["testRunId"] = f"{slice_id}-run-000001"
    _write_json(raw / "test-run.json", test_run)

    assets = repository / "tests/load"
    assets.mkdir(parents=True)
    shutil.copyfile(CONFIGURATION, assets / "load-test.yaml")
    shutil.copyfile(JMETER, assets / "catalog-load.jmx")

    handoff = deepcopy(load_json(CONTRACTS / "modernization-contract.example.json"))
    handoff["sliceId"] = slice_id
    handoff["source"]["stack"] = stack
    if database_family == "postgresql-flexible":
        handoff["database"]["family"] = database_family
        handoff["database"]["resourceId"] = (
            "/subscriptions/00000000-0000-0000-0000-000000000000/"
            "resourceGroups/rg-mh-example/providers/"
            "Microsoft.DBforPostgreSQL/flexibleServers/psql-example/"
            "databases/catalog"
        )
    handoff_path = repository / "evidence/modernization-contract.json"
    _write_json(handoff_path, handoff)

    capture = deepcopy(
        load_json(CONTRACTS / "load-evidence-capture.example.json")
    )
    capture["testRun"]["sha256"] = _sha256(raw / "test-run.json")
    capture["scaleConfiguration"]["sha256"] = _sha256(
        raw / "container-app.json"
    )
    capture["replicas"]["sha256"] = _sha256(raw / "replicas.json")
    capture["artifacts"]["configurationSha256"] = _sha256(
        assets / "load-test.yaml"
    )
    capture["artifacts"]["jmeterSha256"] = _sha256(
        assets / "catalog-load.jmx"
    )
    if database_family == "postgresql-flexible":
        capture["databaseSignal"].update(
            {
                "resourceId": handoff["database"]["resourceId"].rsplit(
                    "/databases/", maxsplit=1
                )[0],
                "metricName": "cpu_percent",
                "aggregation": "Maximum",
            }
        )
    capture["databaseSignal"]["sha256"] = _sha256(raw / "database.json")
    capture_path = repository / "evidence/load/capture.json"
    _write_json(capture_path, capture)
    return capture_path, handoff_path, handoff


def _render(
    repository: Path,
    capture_path: Path,
    handoff_path: Path,
) -> Path:
    """Run the public frozen renderer and return its canonical report."""
    result = render_main(
        [
            "--capture",
            str(capture_path.relative_to(repository)),
            "--handoff",
            str(handoff_path.relative_to(repository)),
            "--output",
            "evidence/load-test-report.json",
            "--repository-root",
            str(repository),
        ]
    )
    assert result == 0
    return repository / "evidence/load-test-report.json"


def test_load_assets_are_bounded_executable_and_secret_free() -> None:
    """Require the Azure definition and exact JMeter runtime controls."""
    configuration = CONFIGURATION.read_text(encoding="utf-8")
    assert "version: v0.1" in configuration
    assert "testId: catalog-autoscaling" in configuration
    assert "testType: JMX" in configuration
    assert "testPlan: catalog-load.jmx" in configuration
    assert "engineInstances: 1" in configuration
    assert "percentage(error) > 0" in configuration
    assert "secrets:" not in configuration

    _assert_bounded_jmeter(JMETER)
    xml = JMETER.read_text(encoding="utf-8")
    assert 'System.getenv("CATALOG_BASE_HOST")' in xml
    assert "${__GetSecret(PERFTEST_API_KEY)}" in xml
    assert '<stringProp name="Header.name">x-api-key</stringProp>' in xml


def test_redirect_enabled_plan_is_rejected(tmp_path: Path) -> None:
    """A 3xx response cannot be hidden by either JMeter redirect mode."""
    unsafe = tmp_path / "unsafe.jmx"
    unsafe.write_text(
        JMETER.read_text(encoding="utf-8").replace(
            '<boolProp name="HTTPSampler.follow_redirects">false</boolProp>',
            '<boolProp name="HTTPSampler.follow_redirects">true</boolProp>',
        ),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError):
        _assert_bounded_jmeter(unsafe)


def test_guides_require_raw_capture_renderer_and_common_validator() -> None:
    """Keep both guides anchored to the complete refrozen producer protocol."""
    required = (
        "shared-challenges.json",
        "loadEvidenceProtocol",
        "load-evidence-capture.schema.json",
        "evidence/load/capture.json",
        "evidence/load/raw/test-run.json",
        "evidence/load/raw/container-app.json",
        "evidence/load/raw/replicas.json",
        "evidence/load/raw/database.json",
        "catalog-render-load-evidence",
        "catalog-validate-challenge-evidence load",
        "/perftest/catalog",
        "/healthz",
        "/readyz",
        "80",
        "300",
        "app_cpu_billed",
        "cpu_percent",
        "flexible-server parent",
        "Total",
        "Maximum",
        "Replicas",
        "revisionName",
        "PT1M",
        "etag",
        "concurrentRequests",
        "50",
        "GetSecret",
    )
    for guide in GUIDES:
        content = guide.read_text(encoding="utf-8")
        normalized = " ".join(content.lower().split())
        for value in required:
            assert value in content, f"{guide.relative_to(ROOT)} omits {value}"
        for slice_id, _, _ in SLICES:
            assert slice_id in content
        assert "create a replacement revision" in normalized
        assert "not live proof" in normalized
        assert "do not manually" in normalized
    assert "DATABASE_METRIC_RESOURCE_ID" in GUIDES[1].read_text(encoding="utf-8")


@pytest.mark.parametrize(("slice_id", "stack", "database_family"), SLICES)
def test_renderer_and_validator_rejoin_every_handoff_slice(
    slice_id: str,
    stack: str,
    database_family: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Render raw captures and validate all six handoff identities."""
    repository = tmp_path / "repository"
    capture_path, handoff_path, handoff = _prepare_capture(
        repository,
        slice_id,
        stack,
        database_family,
    )
    report_path = _render(repository, capture_path, handoff_path)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    validated = shared_challenges.validate_shared_challenge_evidence(
        "load",
        report_path,
        handoff_path,
        CONTRACTS,
        repository,
    )
    assert validated["schemaVersion"] == "1.1.0"
    assert validated["subject"]["sliceId"] == slice_id
    assert validated["subject"]["stack"] == stack
    assert validated["subject"]["databaseFamily"] == database_family


def test_common_validator_rejects_manual_report_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A schema-valid manual report change cannot replace renderer output."""
    repository = tmp_path / "repository"
    capture_path, handoff_path, handoff = _prepare_capture(
        repository,
        *SLICES[0],
    )
    report_path = _render(repository, capture_path, handoff_path)
    report = load_json(report_path)
    report["capturedAt"] = "2026-08-20T12:16:00Z"
    _write_json(report_path, report)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(
        ValueError,
        match="differs from deterministic raw-capture rendering",
    ):
        shared_challenges.validate_shared_challenge_evidence(
            "load",
            report_path,
            handoff_path,
            CONTRACTS,
            repository,
        )


def test_common_validator_rejects_manual_normalized_observation_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A manual normalized JSON edit cannot replace renderer output."""
    repository = tmp_path / "repository"
    capture_path, handoff_path, handoff = _prepare_capture(
        repository,
        *SLICES[0],
    )
    report_path = _render(repository, capture_path, handoff_path)
    observation_path = repository / "evidence/load/replicas.json"
    observation = load_json(observation_path)
    observation["points"][0]["timestamp"] = "2026-08-20T11:58:30Z"
    _write_json(observation_path, observation)
    monkeypatch.setattr(shared_challenges, "validate_handoff", lambda *_: handoff)

    with pytest.raises(
        ValueError,
        match="normalized load observation differs from raw capture",
    ):
        shared_challenges.validate_shared_challenge_evidence(
            "load",
            report_path,
            handoff_path,
            CONTRACTS,
            repository,
        )


def test_renderer_rejects_delayed_post_run_scale_out(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Scale-out after the Azure run timestamps cannot satisfy the challenge."""
    repository = tmp_path / "repository"
    capture_path, handoff_path, _ = _prepare_capture(
        repository,
        *SLICES[0],
    )
    raw_path = repository / "evidence/load/raw/replicas.json"
    raw = load_json(raw_path)
    for point in raw["value"][0]["timeseries"][0]["data"]:
        if point["timeStamp"] <= "2026-08-20T12:05:00Z":
            point["maximum"] = 1
    _write_json(raw_path, raw)
    capture = load_json(capture_path)
    capture["replicas"]["sha256"] = _sha256(raw_path)
    _write_json(capture_path, capture)

    assert (
        render_main(
            [
                "--capture",
                "evidence/load/capture.json",
                "--handoff",
                "evidence/modernization-contract.json",
                "--output",
                "evidence/load-test-report.json",
                "--repository-root",
                str(repository),
            ]
        )
        == 1
    )
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "failed"
    assert "in-load scale-out" in result["error"]


SCALE_RULE = ROOT / "infra/modules/environment.bicep"


def _scale_rule_numbers() -> tuple[int, int]:
    """Return ``(concurrentRequests, maxReplicas)`` from the Container Apps scale rule."""
    source = SCALE_RULE.read_text(encoding="utf-8")
    concurrent = re.search(r"concurrentRequests:\s*'(\d+)'", source)
    maximum = re.search(r"maxReplicas:\s*(\d+)", source)
    assert concurrent is not None, f"no concurrentRequests in {SCALE_RULE}"
    assert maximum is not None, f"no maxReplicas in {SCALE_RULE}"
    return int(concurrent.group(1)), int(maximum.group(1))


def test_the_load_profile_can_actually_trigger_the_scale_rule() -> None:
    """The shipped load must be able to produce the replica evidence the challenge demands.

    Challenge 2 requires ``evidence/load/raw/replicas.json`` to show "one replica
    immediately before load, two or three" during it. Whether that evidence is
    *obtainable* is pure arithmetic: the KEDA HTTP scaler asks for
    ``ceil(concurrent / concurrentRequests)`` replicas, so a virtual-user count at or
    below the threshold pins the app at one replica no matter how long it runs.

    Both numbers were frozen independently -- the user count by this module, the
    threshold by the bicep and the shared-challenge contract -- and nothing compared
    them. Shipped, they were 40 against 50: the participant could execute the documented
    run perfectly, get a green ``DONE`` with zero errors, and still be unable to produce
    the required artifact. The challenge's own troubleshooting table named this exact
    arithmetic as a cause and offered a remedy only for the *other* cause.

    This test is the comparison that was missing. It fails if either number drifts to
    where the evidence gate stops being satisfiable.

    The user count is not arbitrary. Two warm digest-pinned runs against the deployed
    .NET app measured the window directly: 40 concurrent held one replica with zero
    errors, and 160 concurrent scaled to three but returned 2.06% HTTP 500s. Challenge 2
    requires *both* zero errors and two-or-three replicas, so neither measured point
    satisfies it. Throughput is database-bound at ~22 rps -- latency tracks Little's Law,
    ``p50 ~= concurrency / rps`` -- so driving harder deepens the queue instead of raising
    throughput, and the errors are queue depth, not app-tier capacity. 80 sits at the
    geometric midpoint of the two measured points, asks for two replicas rather than
    pinning the ceiling at three, and predicts a p50 near 3.6s against the 7.6s where
    errors appeared.
    """
    thread_group = ElementTree.parse(JMETER).getroot().iter("ThreadGroup")
    threads = [
        int(prop.text or "0")
        for group in thread_group
        for prop in group.iter("stringProp")
        if prop.get("name") == "ThreadGroup.num_threads"
    ]
    assert len(threads) == 1, f"expected exactly one thread group, found {len(threads)}"
    users = threads[0]

    concurrent_requests, max_replicas = _scale_rule_numbers()
    desired = -(-users // concurrent_requests)

    assert desired >= 2, (
        f"{users} virtual users against a concurrentRequests threshold of "
        f"{concurrent_requests} asks for {desired} replica(s), so the run can never show "
        "the two-or-three replicas Challenge 2 requires as evidence; raise the user count "
        "above the threshold or lower the threshold"
    )
    assert desired <= max_replicas, (
        f"{users} virtual users ask for {desired} replicas but maxReplicas is "
        f"{max_replicas}, so the scale-out saturates and the run cannot demonstrate the "
        "rule it is teaching"
    )
