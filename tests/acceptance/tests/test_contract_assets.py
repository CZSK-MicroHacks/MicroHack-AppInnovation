"""Executable tests that freeze schemas, corpus identity, and normalization."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError

from catalog_acceptance.handoff import _runtime_test_outcomes, validate_handoff
from catalog_acceptance.handoff_cli import main as handoff_cli_main
from catalog_acceptance.manifest import (
    category_slug,
    identity_is_valid,
    load_json,
    validate_seed,
)
from catalog_acceptance.models.contracts import CatalogItem, FULL_ACCEPTANCE_CHECKS


def _validate(schema: dict, instance: object) -> None:
    """Validate one instance with strict format checking."""
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(instance)


def test_contract_schemas_are_valid(repo_root: Path) -> None:
    """Require every checked-in JSON Schema to be a valid Draft 2020-12 schema."""
    contracts = repo_root / "workshop" / "contracts"
    for path in contracts.glob("*.schema.json"):
        Draft202012Validator.check_schema(load_json(path))


def test_catalog_and_manifest_match_schemas(repo_root: Path) -> None:
    """Require the canonical corpus and manifest to match their public schemas."""
    contracts = repo_root / "workshop" / "contracts"
    data = repo_root / "data"
    _validate(load_json(contracts / "catalog.schema.json"), load_json(data / "catalog.json"))
    _validate(
        load_json(contracts / "seed-manifest.schema.json"),
        load_json(data / "manifest.json"),
    )
    _validate(
        load_json(contracts / "database-contract.schema.json"),
        load_json(contracts / "database-contract.json"),
    )


def test_handoff_example_matches_schema(repo_root: Path) -> None:
    """Require the participant handoff example to remain schema-valid."""
    contracts = repo_root / "workshop" / "contracts"
    _validate(
        load_json(contracts / "modernization-contract.schema.json"),
        load_json(contracts / "modernization-contract.example.json"),
    )
    _validate(
        load_json(contracts / "telemetry-evidence.schema.json"),
        load_json(contracts / "telemetry-evidence.example.json"),
    )


def test_sanitized_fixtures_cover_atomic_rejection_inputs(repo_root: Path) -> None:
    """Require valid prefixes followed by either frozen invalid record to fail."""
    contracts = repo_root / "workshop" / "contracts"
    fixtures = repo_root / "tests" / "acceptance" / "fixtures"
    _validate(
        load_json(contracts / "catalog.schema.json"),
        load_json(fixtures / "catalog.valid.json"),
    )
    mixed_items = load_json(fixtures / "catalog.invalid.json")
    CatalogItem.model_validate(mixed_items[0])
    with pytest.raises(ValidationError):
        CatalogItem.model_validate(mixed_items[1])
    empty_slug_items = load_json(fixtures / "catalog.invalid-empty-slug.json")
    CatalogItem.model_validate(empty_slug_items[0])
    with pytest.raises(ValidationError):
        CatalogItem.model_validate(empty_slug_items[1])


def test_normalization_vectors(repo_root: Path) -> None:
    """Require Python normalization to match every cross-runtime vector."""
    vectors = load_json(
        repo_root / "workshop" / "contracts" / "normalization-vectors.json"
    )
    for vector in vectors["vectors"]:
        assert category_slug(vector["input"]) == vector["expected"]
    for vector in vectors["invalidVectors"]:
        assert category_slug(vector["input"]) == ""


def test_text_validation_vectors(repo_root: Path) -> None:
    """Require storage-safe text vectors to pass or fail exactly."""
    vectors = load_json(
        repo_root / "workshop" / "contracts" / "text-validation-vectors.json"
    )
    base = {
        "productId": "10000000-0000-4000-8000-000000000099",
        "name": "Contract Figure",
        "description": "A representative figure used for text validation.",
        "category": "Contract Figures",
        "filename": "10000000-0000-4000-8000-000000000099.png",
        "imagePrompt": "Photorealistic construction-toy figure on a clean background.",
    }
    for vector in vectors["vectors"]:
        candidate = dict(base)
        candidate[vector["field"]] = vector["fragment"] * vector["repeat"]
        if vector["valid"]:
            CatalogItem.model_validate(candidate)
        else:
            with pytest.raises(ValidationError):
                CatalogItem.model_validate(candidate)


def test_runtime_evidence_schema_freezes_requirement_names(repo_root: Path) -> None:
    """Reject a passing but unrelated native test name."""
    contracts = repo_root / "workshop" / "contracts"
    evidence = load_json(contracts / "runtime-test-evidence.example.json")
    evidence["tests"][0]["testName"] = "Contract.Unrelated.Passes"
    with pytest.raises(JsonSchemaValidationError):
        _validate(
            load_json(contracts / "runtime-test-evidence.schema.json"),
            evidence,
        )
    duplicate = load_json(contracts / "runtime-test-evidence.example.json")
    duplicate["tests"] = [duplicate["tests"][0]] * 14
    with pytest.raises(JsonSchemaValidationError):
        _validate(
            load_json(contracts / "runtime-test-evidence.schema.json"),
            duplicate,
        )
    unqualified = load_json(contracts / "runtime-test-evidence.example.json")
    unqualified["tests"][0]["testIdentity"] = "UnqualifiedTest"
    with pytest.raises(JsonSchemaValidationError):
        _validate(
            load_json(contracts / "runtime-test-evidence.schema.json"),
            unqualified,
        )


def test_junit_runtime_evidence_uses_class_and_display_name(tmp_path: Path) -> None:
    """Bind JUnit evidence to its package-qualified class and display name."""
    reports = tmp_path / "surefire-reports"
    reports.mkdir()
    name = "Contract.Telemetry.FinalResponseStatus"
    class_name = "com.microsoft.microhack.catalog.TelemetryContractTest"
    (reports / "TEST-telemetry.xml").write_text(
        (
            "<testsuite>"
            f'<testcase name="{name}" classname="{class_name}" />'
            "</testsuite>"
        ),
        encoding="utf-8",
    )

    assert _runtime_test_outcomes(reports, "junit") == {
        (name, f"{class_name}#{name}"): ["passed"]
    }


def test_identity_vectors(repo_root: Path) -> None:
    """Require identity validation to match every cross-runtime vector."""
    vectors = load_json(
        repo_root / "workshop" / "contracts" / "identity-vectors.json"
    )
    for vector in vectors["vectors"]:
        assert (
            identity_is_valid(vector["productId"], vector["filename"])
            is vector["valid"]
        )


def test_canonical_seed_manifest(repo_root: Path) -> None:
    """Require all 198 records, 20 categories, and 198 images to match the manifest."""
    manifest = validate_seed(repo_root / "data")
    assert manifest.counts.figures == 198
    assert manifest.counts.categories == 20
    assert manifest.counts.images == 198


def test_behavior_contract_has_unique_routes(repo_root: Path) -> None:
    """Require the frozen route table to avoid ambiguous method/path pairs."""
    behavior = load_json(
        repo_root / "workshop" / "contracts" / "behavior-contract.json"
    )
    routes = [(route["method"], route["path"]) for route in behavior["routes"]]
    assert len(routes) == len(set(routes))
    assert behavior["performance"]["apiKeyEnvironmentVariable"] == "PERFTEST_API_KEY"


def test_toolchain_matrix_is_exact(repo_root: Path) -> None:
    """Require source/target runtimes and modernization extension versions to be pinned."""
    toolchain = load_json(repo_root / "workshop" / "toolchain.lock.json")
    _validate(
        load_json(repo_root / "workshop" / "contracts" / "toolchain-lock.schema.json"),
        toolchain,
    )
    assert toolchain["runtimes"]["dotnet"]["sourceSdk"] == "8.0.424"
    assert toolchain["runtimes"]["dotnet"]["targetSdk"] == "10.0.400"
    assert toolchain["runtimes"]["java"]["sourceSpringBoot"] == "3.5.16"
    assert toolchain["runtimes"]["java"]["targetSpringBoot"] == "4.0.7"
    assert toolchain["hosts"]["workshopVm"]["azureImage"]["version"] != "latest"
    assert toolchain["databases"]["sqlserver"]["client"]["installer"]["version"] == "1.7.0"
    assert toolchain["provisioning"]["mutableRefsForbidden"] is True
    assert "{commitSha}" in toolchain["provisioning"]["sourceArchiveTemplate"]
    assert toolchain["databases"]["sqlserver"]["localContainer"][
        "indexDigest"
    ].startswith("sha256:")
    assert toolchain["databases"]["postgresql"]["localContainer"][
        "indexDigest"
    ].startswith("sha256:")
    assert toolchain["extensions"]["vscjava.migrate-java-to-azure"]
    assert toolchain["extensions"]["vscjava.vscode-java-upgrade"]
    assert toolchain["extensions"]["ms-dotnettools.vscode-dotnet-modernize"]
    assert toolchain["extensions"]["ms-dotnettools.upgrade-agent"]


def test_handoff_bundle_cross_file_consistency(
    repo_root: Path, tmp_path: Path
) -> None:
    """Require handoff, acceptance, and telemetry evidence to agree."""
    contracts = repo_root / "workshop" / "contracts"
    handoff = load_json(contracts / "modernization-contract.example.json")
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    iac_directory = tmp_path / "solutions" / "ch01-manual" / "dotnet" / "bicep"
    iac_directory.mkdir(parents=True)
    (iac_directory / "main.bicep").write_text(
        "metadata contractFixture = true\n",
        encoding="utf-8",
    )
    data_directory = tmp_path / "data"
    data_directory.mkdir()
    (data_directory / "manifest.json").write_text(
        (repo_root / "data" / "manifest.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (evidence / "rollback.md").write_text("rollback fixture\n", encoding="utf-8")
    runtime_example = load_json(contracts / "runtime-test-evidence.example.json")
    runtime_results = "\n".join(
        f'<UnitTestResult testId="runtime-{index}" '
        f'testName="{test["testName"]}" outcome="Passed" />'
        for index, test in enumerate(runtime_example["tests"])
    )
    runtime_definitions = "\n".join(
        (
            f'<UnitTest id="runtime-{index}" name="{test["testName"]}">'
            f'<TestMethod className="{test["testIdentity"].rsplit(".", 1)[0]}" '
            f'name="{test["testIdentity"].rsplit(".", 1)[1]}" />'
            "</UnitTest>"
        )
        for index, test in enumerate(runtime_example["tests"])
    )
    (evidence / "runtime-tests.trx").write_text(
        (
            f"<TestRun><Results>{runtime_results}</Results>"
            f"<TestDefinitions>{runtime_definitions}</TestDefinitions></TestRun>\n"
        ),
        encoding="utf-8",
    )
    handoff_path = evidence / "modernization-contract.json"
    handoff_path.write_text(
        json.dumps(handoff),
        encoding="utf-8",
    )
    report = {
        "schemaVersion": "1.0.0",
        "profile": "full",
        "status": "passed",
        "startedAt": "2026-08-18T00:00:00Z",
        "finishedAt": "2026-08-18T00:01:00Z",
        "baseUrl": handoff["application"]["url"],
        "databaseKind": "sqlserver",
        "corpus": {
            "figures": 198,
            "categories": 20,
            "images": 198,
        },
        "databaseTarget": "managed",
        "subject": {
            "sourceCommit": handoff["source"]["commitSha"],
            "imageDigest": handoff["containerImage"]["digest"],
            "revisionName": handoff["application"]["revisionName"],
        },
        "checks": [
            {
                "name": name,
                "status": "passed",
                "detail": "fixture",
                "required": True,
            }
            for name in FULL_ACCEPTANCE_CHECKS
        ],
    }
    (evidence / "acceptance-report.json").write_text(
        json.dumps(report),
        encoding="utf-8",
    )
    (evidence / "telemetry-report.json").write_text(
        (contracts / "telemetry-evidence.example.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    telemetry = load_json(contracts / "telemetry-evidence.example.json")
    signal_contract = load_json(contracts / "behavior-contract.json")["telemetry"]
    telemetry_directory = evidence / "telemetry"
    telemetry_directory.mkdir()
    for query_id, query in telemetry["queries"].items():
        rows = []
        for signal_name in query["expectedSignalNames"]:
            observed_attributes = (
                list(telemetry["resourceAttributes"])
                if query_id == "resources"
                else signal_contract[query_id][signal_name]
            )
            row = {
                "signalName": signal_name,
                "recordCount": 1,
                "observedAttributes": observed_attributes,
            }
            if query_id == "resources":
                row["resourceAttributes"] = telemetry["resourceAttributes"]
            if query_id == "metrics":
                row["unit"] = signal_contract["metricUnits"][signal_name]
                row["measurements"] = [
                    {
                        "value": (
                            3
                            if signal_name == "catalog.import.records"
                            else 1
                        ),
                        "attributes": (
                            {
                                "http.request.method": "GET",
                                "http.route": "/figure/{id}",
                                "http.response.status_code": 200,
                            }
                            if signal_name == "http.server.request.duration"
                            else (
                                {"catalog.import.outcome": "rejected"}
                                if signal_name == "catalog.import.records"
                                else {}
                            )
                        ),
                    }
                ]
            if query_id in ("traces", "logs"):
                is_http = signal_name in ("http.server", "http.server.request")
                row["observations"] = [
                    {
                        "attributes": (
                            {
                                "http.request.method": "GET",
                                "http.route": "/figure/{id}",
                                "http.response.status_code": 200,
                            }
                            if is_http
                            else {}
                        )
                    }
                ]
            rows.append(row)
        result_path = tmp_path / query["resultFile"]
        result_path.write_text(
            json.dumps(
                {
                    "schemaVersion": "1.0.0",
                    "queryId": query_id,
                    "rows": rows,
                }
            ),
            encoding="utf-8",
        )
    (evidence / "runtime-test-report.json").write_text(
        (contracts / "runtime-test-evidence.example.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    assert validate_handoff(handoff_path, contracts, tmp_path) == handoff
    assert (
        handoff_cli_main(
            [
                str(handoff_path),
                "--contracts",
                str(contracts),
                "--repository-root",
                str(tmp_path),
            ]
        )
        == 0
    )

    metrics_path = tmp_path / telemetry["queries"]["metrics"]["resultFile"]
    passing_metrics = load_json(metrics_path)
    invalid_metrics = json.loads(json.dumps(passing_metrics))
    invalid_metrics["rows"][0]["unit"] = "ms"
    metrics_path.write_text(json.dumps(invalid_metrics), encoding="utf-8")
    with pytest.raises(ValueError, match="unit differs"):
        validate_handoff(handoff_path, contracts, tmp_path)
    invalid_metrics = json.loads(json.dumps(passing_metrics))
    import_row = next(
        row
        for row in invalid_metrics["rows"]
        if row["signalName"] == "catalog.import.records"
    )
    import_row["measurements"][0]["value"] = 1.5
    metrics_path.write_text(json.dumps(invalid_metrics), encoding="utf-8")
    with pytest.raises(ValueError, match="positive integral aggregate"):
        validate_handoff(handoff_path, contracts, tmp_path)
    metrics_path.write_text(json.dumps(passing_metrics), encoding="utf-8")

    runtime_artifact = evidence / "runtime-tests.trx"
    passing_runtime_results = runtime_artifact.read_text(encoding="utf-8")
    runtime_artifact.write_text(
        passing_runtime_results.replace('outcome="Passed"', 'outcome="Failed"', 1),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="lacks passing"):
        validate_handoff(handoff_path, contracts, tmp_path)
    runtime_artifact.write_text(passing_runtime_results, encoding="utf-8")
    runtime_artifact.write_text(
        passing_runtime_results.replace(
            'className="LegoCatalog.App.Tests.HealthContractTests"',
            'className="LegoCatalog.App.Tests.UnrelatedTests"',
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="lacks passing"):
        validate_handoff(handoff_path, contracts, tmp_path)
    runtime_artifact.write_text(passing_runtime_results, encoding="utf-8")

    invalid_handoff = json.loads(json.dumps(handoff))
    invalid_handoff["seedManifest"]["hashes"]["imageSetSha256"] = "0" * 64
    handoff_path.write_text(json.dumps(invalid_handoff), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical manifest"):
        validate_handoff(handoff_path, contracts, tmp_path)
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

    rollback = evidence / "rollback.md"
    rollback.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="artifact is empty"):
        validate_handoff(handoff_path, contracts, tmp_path)
    rollback.write_text("rollback fixture\n", encoding="utf-8")

    iac_file = iac_directory / "main.bicep"
    iac_file.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="artifact is empty"):
        validate_handoff(handoff_path, contracts, tmp_path)
    iac_file.write_text("metadata contractFixture = true\n", encoding="utf-8")
    wrong_extension = iac_file.with_suffix(".tf")
    iac_file.rename(wrong_extension)
    with pytest.raises(ValueError, match=r"no non-empty .*\.bicep"):
        validate_handoff(handoff_path, contracts, tmp_path)
    wrong_extension.rename(iac_file)

    report["profile"] = "smoke"
    (evidence / "acceptance-report.json").write_text(
        json.dumps(report),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="full passing"):
        validate_handoff(handoff_path, contracts, tmp_path)
