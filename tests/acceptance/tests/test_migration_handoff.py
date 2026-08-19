"""Schema and evidence tests for migration reports and rendered handoffs."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from catalog_migrate.contracts import load_json
from catalog_migrate.handoff import render_handoff


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
    paths = {}
    for name, document in (
        ("target", target),
        ("migration", migration),
        ("acceptance", acceptance),
        ("telemetry", telemetry),
        ("runtime", runtime),
    ):
        path = repo_root / f"tests/acceptance/{name}-migration-test.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        paths[name] = path
    try:
        handoff = render_handoff(
            target_path=paths["target"],
            migration_path=paths["migration"],
            acceptance_path=paths["acceptance"],
            telemetry_path=paths["telemetry"],
            runtime_path=paths["runtime"],
        )
    finally:
        for path in paths.values():
            path.unlink(missing_ok=True)
    assert handoff["source"]["runtimeVersion"] == "21.0.12"
    assert handoff["source"]["frameworkVersion"] == "Spring Boot 4.0.7"
    assert handoff["database"]["migrationMechanism"] == "pg-dump-restore"
    assert handoff["database"]["migrationVersion"] == "18.6"
    assert handoff["rollback"]["targetRevision"] == target["application"]["revisionName"]


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
