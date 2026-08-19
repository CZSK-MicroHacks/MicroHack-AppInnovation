"""Render a schema-valid modernization handoff from exact evidence documents."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from catalog_migrate.azure import validate_release
from catalog_migrate.contracts import (
    load_json,
    repository_path,
    validate_document,
)
from catalog_migrate.errors import InvalidInputError
from catalog_migrate.process import CommandRunner


def render_handoff(
    *,
    runner: CommandRunner,
    target_path: Path,
    migration_path: Path,
    acceptance_path: Path,
    telemetry_path: Path,
    runtime_path: Path,
    modernization_path: Literal[
        "manual", "copilot-rewrite", "copilot-modernization"
    ],
    rollback_revision: str,
    rollback_runbook_path: Path,
) -> dict[str, Any]:
    """Consume validated evidence and render the frozen modernization contract."""
    target = load_json(target_path)
    migration = load_json(migration_path)
    acceptance = load_json(acceptance_path)
    telemetry = load_json(telemetry_path)
    runtime = load_json(runtime_path)
    if modernization_path not in {
        "manual",
        "copilot-rewrite",
        "copilot-modernization",
    }:
        raise InvalidInputError("unsupported modernization path")
    if rollback_runbook_path.suffix.lower() != ".md":
        raise InvalidInputError("rollback runbook must be a Markdown document")
    rollback_runbook = repository_path(rollback_runbook_path)
    try:
        rollback_runbook_contents = rollback_runbook_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise InvalidInputError("rollback runbook could not be read") from error
    if not rollback_runbook_contents.strip():
        raise InvalidInputError("rollback runbook must not be empty")
    for document, schema in (
        (target, "azure-target-output.schema.json"),
        (migration, "migration-report.schema.json"),
        (acceptance, "acceptance-report.schema.json"),
        (telemetry, "telemetry-evidence.schema.json"),
        (runtime, "runtime-test-evidence.schema.json"),
    ):
        validate_document(document, schema)
    expected_image_provider = (
        "azure-files" if modernization_path == "manual" else "azure-blob"
    )
    if target["images"]["provider"] != expected_image_provider:
        raise InvalidInputError(
            f"{modernization_path} requires {expected_image_provider} images"
        )
    if target["deploymentStage"] != "application" or target["application"] is None:
        raise InvalidInputError("handoff requires application-stage target output")
    validate_release(runner, target, rollback_revision)
    stack = target["stack"]
    if (
        migration["stack"] != stack
        or runtime["stack"] != stack
        or migration["sourceCommit"] != target["sourceCommit"]
        or runtime["sourceCommit"] != target["sourceCommit"]
    ):
        raise InvalidInputError("evidence stack or source commit is inconsistent")
    app = target["application"]
    image = target["containerImage"]
    database = target["database"]
    if (
        migration["targetDatabase"] != database
        or {
            key: migration["images"][key]
            for key in ("resourceId", "provider", "location", "authentication")
        }
        != target["images"]
    ):
        raise InvalidInputError("migration target differs from target output")
    acceptance_subject = acceptance.get("subject")
    if acceptance_subject is None:
        raise InvalidInputError("handoff requires release-bound acceptance evidence")
    if (
        acceptance_subject["sourceCommit"] != target["sourceCommit"]
        or acceptance_subject["imageDigest"] != image["digest"]
        or acceptance_subject["revisionName"] != app["revisionName"]
        or acceptance["baseUrl"] != app["url"]
    ):
        raise InvalidInputError("acceptance subject differs from target output")
    image_verification = migration["images"]["verification"]
    runtime_version, framework_version, service_name = (
        ("10.0.11", "ASP.NET Core 10.0.11", "mh-catalog-dotnet")
        if stack == "dotnet-sqlserver"
        else ("21.0.12", "Spring Boot 4.0.7", "mh-catalog-java")
    )
    if telemetry["service"] != service_name:
        raise InvalidInputError("telemetry service differs from target stack")
    resource_attributes = telemetry["resourceAttributes"]
    if (
        resource_attributes["service.version"] != target["sourceCommit"]
        or resource_attributes["azure.containerapps.revision.name"]
        != app["revisionName"]
    ):
        raise InvalidInputError("telemetry identity differs from target output")
    handoff = {
        "schemaVersion": "1.3.0",
        "source": {
            "stack": stack,
            "runtimeVersion": runtime_version,
            "frameworkVersion": framework_version,
            "commitSha": target["sourceCommit"],
        },
        "seedManifest": {
            key: load_json(Path(__file__).resolve().parents[3] / "data" / "manifest.json")[key]
            for key in ("schemaVersion", "counts", "hashes")
        },
        "path": modernization_path,
        "application": {
            **app,
            "region": target["location"],
            "resourceGroup": target["resourceGroup"]["name"],
        },
        "containerImage": {
            "registryResourceId": target["containerRegistry"]["resourceId"],
            "registry": target["containerRegistry"]["loginServer"],
            **image,
        },
        "database": {
            "resourceId": database["resourceId"],
            "family": database["family"],
            "server": database["server"],
            "database": database["database"],
            "migrationMechanism": (
                "sqlpackage-bacpac"
                if stack == "dotnet-sqlserver"
                else "pg-dump-restore"
            ),
            "migrationVersion": migration["databaseArtifact"]["importTool"]["version"],
            "seedManifestVersion": migration["databaseVerification"][
                "seedManifestVersion"
            ],
            "applicationPrincipal": database["applicationPrincipal"],
            "verifiedRowCounts": migration["databaseVerification"][
                "verifiedRowCounts"
            ],
        },
        "images": {
            "resourceId": target["images"]["resourceId"],
            "provider": target["images"]["provider"],
            "location": target["images"]["location"],
            "verification": {"verified": True, **image_verification},
        },
        "authentication": {
            "containerRegistry": "managed-identity",
            "database": database["authentication"],
            "imageStore": target["images"]["authentication"],
            "telemetry": "connection-string-secret",
        },
        "observability": {
            "serviceName": service_name,
            "serviceNamespace": "app-innovation",
            "environment": resource_attributes["deployment.environment"],
            "serviceVersion": resource_attributes["service.version"],
            "serviceInstanceId": resource_attributes["service.instance.id"],
            "revision": resource_attributes["azure.containerapps.revision.name"],
            **target["observability"],
        },
        "acceptance": {
            "report": repository_path(acceptance_path),
            "profile": acceptance["profile"],
            "result": acceptance["status"],
        },
        "deployment": {
            "mechanism": "bicep",
            "iacPath": "infra",
            "targetOutput": repository_path(target_path),
        },
        "rollback": {
            "targetRevision": rollback_revision,
            "runbook": rollback_runbook,
        },
        "evidence": {
            "migrationReport": repository_path(migration_path),
            "telemetryReport": repository_path(telemetry_path),
            "runtimeTestReport": repository_path(runtime_path),
        },
    }
    validate_document(handoff, "modernization-contract.schema.json")
    return handoff
