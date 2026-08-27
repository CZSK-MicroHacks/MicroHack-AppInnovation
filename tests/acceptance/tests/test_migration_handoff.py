"""Schema and evidence tests for migration reports and rendered handoffs."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from catalog_acceptance.golden_dryrun import STEPS, Rehearsal
from catalog_acceptance.golden_dryrun import main as golden_dryrun_main
from catalog_migrate.contracts import load_json
from catalog_migrate.errors import InvalidInputError
from catalog_migrate.handoff import render_handoff
from catalog_migrate.process import ProcessResult


class ReleaseRunner:
    """Return the frozen tag digest and a healthy inactive baseline revision."""

    def __init__(self, target: dict, rollback_revision: str) -> None:
        self.target = target
        self.rollback_revision = rollback_revision

    def run(self, argv: list[str], **kwargs) -> ProcessResult:
        del kwargs
        if argv[:2] == ["az", "version"]:
            return ProcessResult('{"azure-cli":"2.80.0"}', "")
        if argv[:4] == ["az", "acr", "manifest", "show-metadata"]:
            return ProcessResult(self.target["containerImage"]["digest"], "")
        if argv[:4] == ["az", "containerapp", "revision", "show"]:
            image = self.target["containerImage"]
            return ProcessResult(
                json.dumps(
                    {
                        "active": False,
                        "health": "Healthy",
                        "error": None,
                        "images": [
                            f"{self.target['containerRegistry']['loginServer']}/"
                            f"{image['repository']}@{image['digest']}"
                        ],
                    }
                ),
                "",
            )
        raise AssertionError(f"Unexpected command: {argv}")


def test_frozen_examples_validate_against_migration_schemas(repo_root: Path) -> None:
    """Both migration reports and the operation result remain executable examples."""
    contracts = repo_root / "workshop/contracts"
    for schema_name, examples in (
        (
            "migration-report.schema.json",
            ("migration-report.sql.example.json", "migration-report.postgresql.example.json"),
        ),
        (
            "migration-operation-result.schema.json",
            ("migration-operation-result.example.json",),
        ),
    ):
        validator = Draft202012Validator(
            load_json(contracts / schema_name),
            format_checker=FormatChecker(),
        )
        for example in examples:
            validator.validate(load_json(contracts / example))


def test_render_handoff_uses_stack_specific_migration_provenance(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """Rendered Java evidence identifies Spring Boot and pg_dump/restore provenance."""
    contracts = repo_root / "workshop/contracts"
    target = load_json(contracts / "azure-target-output.application.example.json")
    rollback_revision = (
        f'{target["application"]["containerAppName"]}'
        f'--baseline-{target["sourceCommit"][:12]}'
    )
    migration = load_json(contracts / "migration-report.postgresql.example.json")
    commit = target["sourceCommit"]
    migration["sourceCommit"] = commit
    runtime = {
        "schemaVersion": "1.1.0",
        "stack": "java-postgresql",
        "sourceCommit": commit,
        "status": "passed",
        "artifactFormat": "junit",
        "artifact": "java/target/surefire-reports",
        "command": "OTEL_SDK_DISABLED=true ./mvnw -q test",
        "tests": _runtime_tests(contracts, "java-postgresql"),
    }
    acceptance = _acceptance(target)
    telemetry = _telemetry(target, "mh-catalog-java")
    (tmp_path / "workshop/contracts").mkdir(parents=True)
    for name in ("challenge-paths.json", "challenge-paths.schema.json"):
        (tmp_path / "workshop/contracts" / name).write_text(
            (contracts / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    (tmp_path / "data").mkdir()
    (tmp_path / "data/manifest.json").write_text(
        (repo_root / "data/manifest.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    paths: dict[str, Path] = {}
    for name, document in (
        ("azure-target-output", target),
        ("migration-report", migration),
        ("acceptance-report", acceptance),
        ("telemetry-report", telemetry),
        ("runtime-test-report", runtime),
    ):
        path = evidence / f"{name}.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        paths[name] = path
    for path in (
        "baseline-backup.md",
        "managed-database-separation.json",
        "container-build.json",
        "iac-review.md",
        "rollback-runbook.md",
    ):
        (evidence / path).write_text("durable evidence\n", encoding="utf-8")
    output_path = evidence / "modernization-contract.json"
    handoff = render_handoff(
        runner=ReleaseRunner(target, rollback_revision),
        target_path=paths["azure-target-output"],
        migration_path=paths["migration-report"],
        acceptance_path=paths["acceptance-report"],
        telemetry_path=paths["telemetry-report"],
        runtime_path=paths["runtime-test-report"],
        output_path=output_path,
        modernization_path="manual",
        rollback_revision=rollback_revision,
        rollback_runbook_path=evidence / "rollback-runbook.md",
        root=tmp_path,
    )
    with pytest.raises(
        InvalidInputError,
        match="copilot-modernization requires azure-blob images",
    ):
        render_handoff(
            runner=ReleaseRunner(target, rollback_revision),
            target_path=paths["azure-target-output"],
            migration_path=paths["migration-report"],
            acceptance_path=paths["acceptance-report"],
            telemetry_path=paths["telemetry-report"],
            runtime_path=paths["runtime-test-report"],
            output_path=output_path,
            modernization_path="copilot-modernization",
            rollback_revision=rollback_revision,
            rollback_runbook_path=evidence / "rollback-runbook.md",
            root=tmp_path,
        )
    assert handoff["source"]["runtimeVersion"] == "21.0.12"
    assert handoff["source"]["frameworkVersion"] == "Spring Boot 4.0.7"
    assert handoff["database"]["migrationMechanism"] == "pg-dump-restore"
    assert handoff["database"]["migrationVersion"] == "18.6"
    assert handoff["schemaVersion"] == "1.4.0"
    assert handoff["sliceId"] == "manual-java"
    assert handoff["path"] == "manual"
    assert handoff["rollback"]["targetRevision"] == rollback_revision
    assert handoff["rollback"]["runbook"] == "evidence/rollback-runbook.md"
    assert handoff["evidence"]["pathEvidence"] == [
        "evidence/baseline-backup.md",
        "evidence/managed-database-separation.json",
        "evidence/container-build.json",
        "evidence/iac-review.md",
    ]

    invalid_target = copy.deepcopy(target)
    invalid_target["database"]["resourceId"] = target["database"]["resourceId"].replace(
        "/resourceGroups/rg-mh-java-example/",
        "/resourceGroups/rg-mh-other/",
    )
    paths["azure-target-output"].write_text(
        json.dumps(invalid_target), encoding="utf-8"
    )
    with pytest.raises(InvalidInputError, match="outside the declared scope"):
        render_handoff(
            runner=ReleaseRunner(invalid_target, rollback_revision),
            target_path=paths["azure-target-output"],
            migration_path=paths["migration-report"],
            acceptance_path=paths["acceptance-report"],
            telemetry_path=paths["telemetry-report"],
            runtime_path=paths["runtime-test-report"],
            output_path=output_path,
            modernization_path="manual",
            rollback_revision=rollback_revision,
            rollback_runbook_path=evidence / "rollback-runbook.md",
            root=tmp_path,
        )
    paths["azure-target-output"].write_text(json.dumps(target), encoding="utf-8")

    (evidence / "iac-review.md").unlink()
    with pytest.raises(InvalidInputError, match="nonempty regular file"):
        render_handoff(
            runner=ReleaseRunner(target, rollback_revision),
            target_path=paths["azure-target-output"],
            migration_path=paths["migration-report"],
            acceptance_path=paths["acceptance-report"],
            telemetry_path=paths["telemetry-report"],
            runtime_path=paths["runtime-test-report"],
            output_path=output_path,
            modernization_path="manual",
            rollback_revision=rollback_revision,
            rollback_runbook_path=evidence / "rollback-runbook.md",
            root=tmp_path,
        )
    (evidence / "iac-review.md").mkdir()
    (evidence / "iac-review.md/placeholder").write_text(
        "not the required file\n", encoding="utf-8"
    )
    with pytest.raises(InvalidInputError, match="nonempty regular file"):
        render_handoff(
            runner=ReleaseRunner(target, rollback_revision),
            target_path=paths["azure-target-output"],
            migration_path=paths["migration-report"],
            acceptance_path=paths["acceptance-report"],
            telemetry_path=paths["telemetry-report"],
            runtime_path=paths["runtime-test-report"],
            output_path=output_path,
            modernization_path="manual",
            rollback_revision=rollback_revision,
            rollback_runbook_path=evidence / "rollback-runbook.md",
            root=tmp_path,
        )


def _runtime_tests(contracts: Path, stack: str) -> list[dict]:
    schema = load_json(contracts / "runtime-test-evidence.schema.json")
    names = [
        "LivenessSurvivesDatabaseOutage",
        "ReadinessFailsDuringDatabaseOutage",
        "ReadinessReportsImportFailure",
        "DatabaseFailureIsControlled",
        "TimeoutIsControlled",
        "MissingKeyReturnsUnauthorized",
        "InvalidKeyReturnsUnauthorized",
        "MissingWorkFactorUsesDefault",
        "BoundsAreAccepted",
        "InvalidWorkFactorsFailStartup",
        "NormalizationVectors",
        "TextValidationVectors",
        "FinalResponseStatus",
        "RejectedDocumentIncrementsOnce",
    ]
    ids = schema["$defs"]["test"]["properties"]["id"]["enum"]
    classes = [
        "RuntimeHealthContractTest",
        "RuntimeHealthContractTest",
        "RuntimeHealthContractTest",
        "RuntimePerformanceContractTest",
        "RuntimePerformanceContractTest",
        "RuntimePerformanceContractTest",
        "RuntimePerformanceContractTest",
        "RuntimePerformanceContractTest",
        "RuntimePerformanceContractTest",
        "RuntimePerformanceContractTest",
        "ConformanceVectorTest",
        "ConformanceVectorTest",
        "TelemetryContractTest",
        "TelemetryContractTest",
    ]
    groups = [
        "Health",
        "Health",
        "Health",
        "Performance",
        "Performance",
        "Performance",
        "Performance",
        "Performance",
        "Performance",
        "Performance",
        "Conformance",
        "Conformance",
        "Telemetry",
        "Telemetry",
    ]
    return [
        {
            "id": identifier,
            "testName": f"Contract.{group}.{name}",
            "testIdentity": (
                f"com.microsoft.microhack.catalog.{class_name}"
                f"#Contract.{group}.{name}"
            ),
        }
        for identifier, name, class_name, group in zip(ids, names, classes, groups)
    ]


def _acceptance(target: dict) -> dict:
    checks = [
        {
            "name": item,
            "status": "passed",
            "detail": "verified",
            "required": True,
        }
        for item in (
            "liveness",
            "readiness",
            "catalog-order-and-count",
            "name-search",
            "name-only-search",
            "category-filter-slug",
            "category-filter-name",
            "known-figure",
            "unknown-figure",
            "image-storage",
            "import-new-category",
            "idempotent-import",
            "invalid-import",
            "performance-authentication-missing",
            "performance-authentication-invalid",
            "performance-contract",
            "database-corpus",
            "database-schema",
            "database-constraints",
            "database-indexes",
            "database-migrations",
            "database-tls",
        )
    ]
    return {
        "schemaVersion": "1.0.0",
        "profile": "full",
        "status": "passed",
        "startedAt": "2026-08-18T00:00:00Z",
        "finishedAt": "2026-08-18T00:01:00Z",
        "baseUrl": target["application"]["url"],
        "databaseKind": "postgresql",
        "databaseTarget": "managed",
        "subject": {
            "sourceCommit": target["sourceCommit"],
            "imageDigest": target["containerImage"]["digest"],
            "revisionName": target["application"]["revisionName"],
        },
        "corpus": {"figures": 198, "categories": 20, "images": 198},
        "checks": checks,
    }


def _telemetry(target: dict, service: str) -> dict:
    revision = target["application"]["revisionName"]
    return {
        "schemaVersion": "1.0.0",
        "capturedAt": "2026-08-18T00:00:00Z",
        "service": service,
        "resourceAttributes": {
            "service.name": service,
            "service.namespace": "app-innovation",
            "service.version": target["sourceCommit"],
            "deployment.environment": "lab",
            "service.instance.id": "instance-1",
            "azure.containerapps.revision.name": revision,
        },
        "queries": {
            name: {
                "query": "query with sufficient length",
                "resultFile": f"evidence/{name}.json",
                "expectedSignalNames": ["resource"],
            }
            for name in ("resources", "traces", "metrics", "logs")
        },
    }


GOLDEN_STACK = "java-postgresql"

#: One request whose matched route template proves the instrumentation records the
#: template rather than the raw path. The validator looks for it in traces, metrics and
#: logs, so every golden bundle has to carry it in all three.
ROUTE_PROBE: dict[str, str | int] = {
    "http.request.method": "GET",
    "http.route": "/figure/{id}",
    "http.response.status_code": 200,
}


def _golden_telemetry(
    contracts: Path,
    target: dict,
    service: str,
) -> tuple[dict, dict[str, dict]]:
    """Build a telemetry report and the query results its validator will accept.

    Everything is derived from `behavior-contract.json` rather than restated, because
    the validator compares the two: signal names, per-signal attributes and metric units
    all have to agree exactly. A hand-written copy would agree only until the contract
    changed, and then this would be testing a fossil.
    """
    behavior = load_json(contracts / "behavior-contract.json")["telemetry"]
    resource_attributes = {
        "service.name": service,
        "service.namespace": behavior["serviceNamespace"],
        "service.version": target["sourceCommit"],
        "deployment.environment": behavior["deploymentEnvironment"],
        "service.instance.id": "instance-1",
        behavior["revisionResourceAttribute"]: target["application"]["revisionName"],
    }
    signals: dict[str, dict] = {
        "resources": {"resource": sorted(resource_attributes)},
        "traces": behavior["traces"],
        "metrics": behavior["metrics"],
        "logs": behavior["logs"],
    }
    route_carrier = {
        "traces": "http.server",
        "metrics": "http.server.request.duration",
        "logs": "http.server.request",
    }
    report = {
        "schemaVersion": "1.0.0",
        "capturedAt": "2026-08-18T00:00:00Z",
        "service": service,
        "resourceAttributes": resource_attributes,
        "queries": {
            query_id: {
                "query": "query with sufficient length",
                "resultFile": f"evidence/{query_id}.json",
                "expectedSignalNames": list(names),
            }
            for query_id, names in signals.items()
        },
    }
    results: dict[str, dict] = {}
    for query_id, names in signals.items():
        rows: list[dict] = []
        for signal, attributes in names.items():
            row: dict = {
                "signalName": signal,
                "recordCount": 1,
                "observedAttributes": sorted(set(attributes)),
            }
            if query_id == "resources":
                row["resourceAttributes"] = resource_attributes
            if query_id == "metrics":
                row["unit"] = behavior["metricUnits"][signal]
                row["measurements"] = [{"value": 1, "attributes": {}}]
                if signal == "catalog.import.records":
                    # The rejected aggregate has to be a positive whole number: a
                    # rejected-count of zero would mean the import never rejected
                    # anything, which is the case the chapter is teaching.
                    row["measurements"] = [
                        {
                            "value": 1,
                            "attributes": {"catalog.import.outcome": "rejected"},
                        }
                    ]
            if query_id in ("traces", "logs"):
                row["observations"] = [
                    {"attributes": {name: "observed" for name in attributes}}
                ]
            if signal == route_carrier.get(query_id):
                if query_id == "metrics":
                    row["measurements"] = [
                        {"value": 1, "attributes": dict(ROUTE_PROBE)}
                    ]
                else:
                    row["observations"] = [{"attributes": dict(ROUTE_PROBE)}]
            rows.append(row)
        results[query_id] = {
            "schemaVersion": "1.0.0",
            "queryId": query_id,
            "rows": rows,
            "workspaceId": (
                "/subscriptions/s/resourceGroups/r/providers/"
                "Microsoft.OperationalInsights/workspaces/w"
            ),
            "capturedAt": "2026-08-27T22:05:00Z",
            "queryText": "AppTraces | summarize count() by OperationName",
        }
    return report, results


def _golden_bundle(repo_root: Path, destination: Path) -> Path:
    """Build one complete, valid golden handoff bundle.

    A golden bundle is its own validation root, so everything the rehearsal reads --
    the contracts directory, the seed manifest, every declared artifact -- has to live
    inside it. The contract is produced by ``render_handoff`` rather than hand-written,
    because a hand-written one would drift away from the renderer and the rehearsal
    would then be validating a fiction.
    """
    contracts = repo_root / "workshop" / "contracts"
    bundle = destination / GOLDEN_STACK
    evidence = bundle / "evidence"
    evidence.mkdir(parents=True)
    (bundle / "data").mkdir()
    (bundle / "infra").mkdir()
    (bundle / "infra" / "main.bicep").write_text("// golden bundle\n", encoding="utf-8")
    shutil.copytree(contracts, bundle / "workshop" / "contracts")
    shutil.copy(
        repo_root / "workshop" / "toolchain.lock.json",
        bundle / "workshop" / "toolchain.lock.json",
    )
    shutil.copy(repo_root / "data" / "manifest.json", bundle / "data" / "manifest.json")

    target = load_json(contracts / "azure-target-output.application.example.json")
    commit = target["sourceCommit"]
    rollback_revision = (
        f"{target['application']['containerAppName']}--baseline-{commit[:12]}"
    )
    migration = load_json(contracts / "migration-report.postgresql.example.json")
    migration["sourceCommit"] = commit
    runtime = {
        "schemaVersion": "1.1.0",
        "stack": GOLDEN_STACK,
        "sourceCommit": commit,
        "status": "passed",
        "artifactFormat": "junit",
        "artifact": "java/target/surefire-reports",
        "command": "OTEL_SDK_DISABLED=true ./mvnw -q test",
        "tests": _runtime_tests(contracts, GOLDEN_STACK),
    }
    telemetry, telemetry_results = _golden_telemetry(
        contracts, target, "mh-catalog-java"
    )
    paths: dict[str, Path] = {}
    for name, document in (
        ("azure-target-output", target),
        ("migration-report", migration),
        ("acceptance-report", _acceptance(target)),
        ("telemetry-report", telemetry),
        ("runtime-test-report", runtime),
    ):
        path = evidence / f"{name}.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        paths[name] = path
    for name in (
        "baseline-backup.md",
        "managed-database-separation.json",
        "container-build.json",
        "iac-review.md",
        "rollback-runbook.md",
    ):
        (evidence / name).write_text("durable evidence\n", encoding="utf-8")
    # The telemetry report cites a result file per query, and the validator opens each
    # one and checks it carries the signals the report claims.
    for query_id, result in telemetry_results.items():
        (bundle / telemetry["queries"][query_id]["resultFile"]).write_text(
            json.dumps(result), encoding="utf-8"
        )
    # The runtime report points at the JUnit output rather than embedding it, and the
    # validator cross-checks every frozen test identity against a passing result there.
    # Synthesizing the artifact from the same frozen list is what makes this a real
    # bundle rather than one that only looks like one.
    surefire = bundle / "java" / "target" / "surefire-reports"
    surefire.mkdir(parents=True)
    cases = "\n".join(
        f'  <testcase classname="{test["testIdentity"].split("#", 1)[0]}"'
        f' name="{test["testName"]}"/>'
        for test in runtime["tests"]
    )
    (surefire / "TEST-catalog.xml").write_text(
        f"<testsuite>\n{cases}\n</testsuite>\n", encoding="utf-8"
    )

    contract_path = evidence / "modernization-contract.json"
    handoff = render_handoff(
        runner=ReleaseRunner(target, rollback_revision),
        target_path=paths["azure-target-output"],
        migration_path=paths["migration-report"],
        acceptance_path=paths["acceptance-report"],
        telemetry_path=paths["telemetry-report"],
        runtime_path=paths["runtime-test-report"],
        output_path=contract_path,
        modernization_path="manual",
        rollback_revision=rollback_revision,
        rollback_runbook_path=evidence / "rollback-runbook.md",
        root=bundle,
    )
    # `render_handoff` returns the contract and validates where it will live; writing it
    # is the caller's job, exactly as `catalog-migrate render-handoff` does.
    contract_path.write_text(json.dumps(handoff, indent=2), encoding="utf-8")
    return bundle


def _first_failing_step(bundle: Path) -> tuple[str, str]:
    """Return the first rehearsal step that fails, with its message."""
    state = Rehearsal(
        bundle=bundle,
        root=bundle,
        contracts=bundle / "workshop" / "contracts",
    )
    for name, step in STEPS:
        try:
            step(state)
        except (OSError, ValueError, JsonSchemaValidationError) as error:
            return name, str(error)
    return "", ""


def _contract(bundle: Path) -> Path:
    return bundle / "evidence" / "modernization-contract.json"


def _misplace_contract(bundle: Path) -> None:
    _contract(bundle).rename(bundle / "modernization-contract.json")


def _corrupt_contract_json(bundle: Path) -> None:
    _contract(bundle).write_text("{", encoding="utf-8")


def _drop_contract_section(bundle: Path) -> None:
    path = _contract(bundle)
    contract = json.loads(path.read_text(encoding="utf-8"))
    del contract["database"]
    path.write_text(json.dumps(contract), encoding="utf-8")


def _mislabel_stack(bundle: Path) -> Path:
    """Put one stack's bundle in the other stack's folder.

    Editing `/source/stack` instead would be caught a step earlier, by the schema, since
    `sliceId` would no longer agree. The defect this step actually exists for is a
    correct contract filed under the wrong directory.
    """
    renamed = bundle.parent / "dotnet-sqlserver"
    bundle.rename(renamed)
    return renamed


def _delete_declared_artifact(bundle: Path) -> None:
    (bundle / "evidence" / "telemetry-report.json").unlink()


def _empty_declared_artifact(bundle: Path) -> None:
    (bundle / "evidence" / "rollback-runbook.md").write_text("", encoding="utf-8")


def _break_cross_field_agreement(bundle: Path) -> None:
    path = bundle / "evidence" / "acceptance-report.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["sourceCommit"] = "0" * 40
    path.write_text(json.dumps(report), encoding="utf-8")


def test_golden_rehearsal_accepts_a_complete_bundle(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """A bundle built exactly as `workshop/golden/README.md` describes passes.

    The repository cannot ship a golden handoff -- every field in one is a live Azure
    identifier -- so the rejoin path is validated by the `golden-dryrun` command at T-4
    rather than by anything checked in. That makes the command itself load-bearing: if
    it were broken, a facilitator would discover the rejoin path was unusable at 15:15
    on day one, which is the single failure the whole procedure exists to prevent. This
    proves the harness works, so the only thing still deferred to T-4 is live Azure.
    """
    assert _first_failing_step(_golden_bundle(repo_root, tmp_path)) == ("", "")


@pytest.mark.parametrize(
    ("mutate", "expected_step", "expected_message"),
    (
        (_misplace_contract, "locate-contract", "challenge-paths.json"),
        (_corrupt_contract_json, "parse-contract", ""),
        (_drop_contract_section, "contract-fields", "database"),
        (_mislabel_stack, "stack-match", "wrong stack"),
        (_delete_declared_artifact, "declared-evidence", "is absent"),
        (_empty_declared_artifact, "declared-evidence", "is an empty file"),
        (_break_cross_field_agreement, "cross-field-checks", ""),
    ),
    ids=(
        "contract-in-the-wrong-place",
        "contract-is-not-json",
        "contract-is-missing-a-section",
        "bundle-holds-the-other-stack",
        "declared-artifact-was-deleted",
        "declared-artifact-is-empty",
        "evidence-disagrees-with-the-contract",
    ),
)
def test_golden_rehearsal_stops_at_the_first_defect(
    repo_root: Path,
    tmp_path: Path,
    mutate,
    expected_step: str,
    expected_message: str,
) -> None:
    """Each defect is caught by its own step, and by no earlier one.

    The command promises to stop at the *first* thing a facilitator has to fix. That
    promise is what makes it usable under time pressure: a facilitator at T-4 fixes one
    named thing and re-runs, rather than reading a wall of failures. A step that fired
    early would send them after the wrong problem, and a step that fired late would let
    a worse defect hide behind a smaller one.
    """
    bundle = _golden_bundle(repo_root, tmp_path)
    bundle = mutate(bundle) or bundle
    step, message = _first_failing_step(bundle)
    assert step == expected_step, (
        f"expected {expected_step} to fail, got {step or 'no failure'}: {message}"
    )
    assert expected_message in message


def test_golden_rehearsal_command_exits_zero_and_prints_a_machine_readable_verdict(
    repo_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The T-4 command a facilitator actually runs must exit 0 and say so in JSON.

    `docs/Facilitator.md` tells a facilitator to run this and requires exit `0`, so the
    exit status is part of the contract, not an implementation detail. The last line is
    JSON on purpose: a facilitator running thirty of these wants to pipe the results
    somewhere rather than read thirty screens.
    """
    bundle = _golden_bundle(repo_root, tmp_path)

    assert golden_dryrun_main([str(bundle)]) == 0

    output = capsys.readouterr().out
    assert output.count("  ok    ") == len(STEPS), (
        f"expected all {len(STEPS)} steps to report ok:\n{output}"
    )
    verdict = json.loads(output.strip().splitlines()[-1])
    assert verdict["status"] == "passed"
    assert verdict["stack"] == GOLDEN_STACK
    assert verdict["bundle"] == str(bundle)
    assert isinstance(verdict["elapsedMs"], float)


def test_golden_rehearsal_command_names_the_failing_step_in_its_verdict(
    repo_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A non-zero exit must name the step, so the failure is actionable unread."""
    bundle = _golden_bundle(repo_root, tmp_path)
    (bundle / "java" / "target" / "surefire-reports" / "TEST-catalog.xml").unlink()

    assert golden_dryrun_main([str(bundle)]) == 1

    verdict = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert verdict["status"] == "failed"
    assert verdict["step"] == "cross-field-checks"
    assert "surefire-reports" in verdict["error"]
