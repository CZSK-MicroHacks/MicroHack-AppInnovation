"""Render a schema-valid modernization handoff from exact evidence documents."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from catalog_migrate.azure import validate_release
from catalog_migrate.contracts import (
    load_json,
    load_target_output,
    repository_path,
    repository_root,
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
    output_path: Path,
    modernization_path: Literal[
        "manual", "copilot-rewrite", "copilot-modernization"
    ],
    rollback_revision: str,
    rollback_runbook_path: Path,
    root: Path | None = None,
) -> dict[str, Any]:
    """Consume validated evidence and render the frozen modernization contract."""
    root = (root or repository_root()).resolve()
    target = load_target_output(target_path, required_stage="application")
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
    for document, schema in (
        (migration, "migration-report.schema.json"),
        (acceptance, "acceptance-report.schema.json"),
        (telemetry, "telemetry-evidence.schema.json"),
        (runtime, "runtime-test-evidence.schema.json"),
    ):
        validate_document(document, schema)
    registry = load_json(root / "workshop" / "contracts" / "challenge-paths.json")
    validate_document(registry, "challenge-paths.schema.json")
    matching_slices = [
        item
        for item in registry["slices"]
        if item["path"] == modernization_path and item["stack"] == target["stack"]
    ]
    if len(matching_slices) != 1:
        raise InvalidInputError("selected path and stack do not resolve to one slice")
    selected_slice = matching_slices[0]
    if selected_slice["databaseFamily"] != target["database"]["family"]:
        raise InvalidInputError("selected slice differs from target database family")
    if selected_slice["imageProvider"] != target["images"]["provider"]:
        raise InvalidInputError(
            f"{modernization_path} requires "
            f"{selected_slice['imageProvider']} images"
        )
    expected_paths = {
        "evidence/azure-target-output.json": target_path,
        "evidence/migration-report.json": migration_path,
        "evidence/acceptance-report.json": acceptance_path,
        "evidence/runtime-test-report.json": runtime_path,
        "evidence/telemetry-report.json": telemetry_path,
        "evidence/modernization-contract.json": output_path,
        "evidence/rollback-runbook.md": rollback_runbook_path,
    }
    required_evidence = set(selected_slice["requiredEvidence"])
    if required_evidence != set(expected_paths):
        raise InvalidInputError("selected slice required evidence is unsupported")
    for expected, supplied in expected_paths.items():
        if repository_path(supplied, root) != expected:
            raise InvalidInputError(
                f"selected slice requires exact evidence path: {expected}"
            )
    rollback_runbook = repository_path(rollback_runbook_path, root)
    try:
        rollback_runbook_contents = rollback_runbook_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise InvalidInputError("rollback runbook could not be read") from error
    if not rollback_runbook_contents.strip():
        raise InvalidInputError("rollback runbook must not be empty")
    for relative_path in selected_slice["pathEvidence"]:
        evidence_path = root / relative_path
        try:
            evidence_path.resolve().relative_to(root)
            valid_file = (
                not evidence_path.is_symlink()
                and evidence_path.is_file()
                and evidence_path.stat().st_size > 0
            )
        except OSError as error:
            raise InvalidInputError(
                f"selected path evidence could not be read: {relative_path}"
            ) from error
        except ValueError as error:
            raise InvalidInputError(
                f"selected path evidence escapes the repository: {relative_path}"
            ) from error
        if not valid_file:
            raise InvalidInputError(
                f"selected path evidence must be a nonempty regular file: {relative_path}"
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
    manifest = load_json(root / "data" / "manifest.json")
    handoff = {
        "schemaVersion": "1.4.0",
        "sliceId": selected_slice["id"],
        "source": {
            "stack": stack,
            "runtimeVersion": runtime_version,
            "frameworkVersion": framework_version,
            "commitSha": target["sourceCommit"],
        },
        "seedManifest": {
            key: manifest[key]
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
            "report": repository_path(acceptance_path, root),
            "profile": acceptance["profile"],
            "result": acceptance["status"],
        },
        "deployment": {
            "mechanism": "bicep",
            "iacPath": "infra",
            "targetOutput": repository_path(target_path, root),
        },
        "rollback": {
            "targetRevision": rollback_revision,
            "runbook": rollback_runbook,
        },
        "evidence": {
            "migrationReport": repository_path(migration_path, root),
            "telemetryReport": repository_path(telemetry_path, root),
            "runtimeTestReport": repository_path(runtime_path, root),
            "pathEvidence": selected_slice["pathEvidence"],
        },
    }
    validate_document(handoff, "modernization-contract.schema.json")
    return handoff
