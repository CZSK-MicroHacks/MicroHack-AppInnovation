"""Schema and evidence tests for migration reports and rendered handoffs."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

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
