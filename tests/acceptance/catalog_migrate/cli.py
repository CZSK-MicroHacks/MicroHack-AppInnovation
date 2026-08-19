"""Exact seven-command command-line surface for bounded target migration."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from catalog_migrate.contracts import (
    COMMIT_PATTERN,
    KNOWN_SECRETS,
    guard_target,
    load_target_output,
    require_secrets,
    validate_document,
)
from catalog_migrate.azure import validate_migration_topology
from catalog_migrate.database import (
    build_migration_report,
    export_postgresql,
    export_sql,
    import_postgresql,
    import_sql,
    target_fragment,
    timestamp,
)
from catalog_migrate.errors import (
    InvalidInputError,
    MigrationError,
    ToolError,
    error_document,
)
from catalog_migrate.handoff import render_handoff
from catalog_migrate.images import copy_images, verify_target_images
from catalog_migrate.process import CommandRunner


class MigrationArgumentParser(argparse.ArgumentParser):
    """Raise typed failures instead of writing argparse usage text."""

    def error(self, message: str) -> None:
        raise InvalidInputError(f"argument error: {message}")


def _parser() -> argparse.ArgumentParser:
    parser = MigrationArgumentParser(prog="catalog-migrate")
    families = parser.add_subparsers(dest="family", required=True)

    sql = families.add_parser("sql")
    sql_commands = sql.add_subparsers(dest="operation", required=True)
    sql_export = sql_commands.add_parser("export")
    sql_export.add_argument("--source-server", required=True)
    sql_export.add_argument("--source-database", required=True)
    sql_export.add_argument("--source-username", required=True)
    sql_export.add_argument("--artifact", required=True, type=Path)
    sql_export.add_argument("--target-output", required=True, type=Path)
    _add_import(sql_commands.add_parser("import"))

    postgresql = families.add_parser("postgresql")
    postgresql_commands = postgresql.add_subparsers(dest="operation", required=True)
    postgresql_export = postgresql_commands.add_parser("export")
    postgresql_export.add_argument("--source-host", required=True)
    postgresql_export.add_argument("--source-port", required=True, type=int)
    postgresql_export.add_argument("--source-database", required=True)
    postgresql_export.add_argument("--source-username", required=True)
    postgresql_export.add_argument("--artifact", required=True, type=Path)
    postgresql_export.add_argument("--target-output", required=True, type=Path)
    _add_import(postgresql_commands.add_parser("import"))

    images = families.add_parser("images")
    image_commands = images.add_subparsers(dest="operation", required=True)
    image_copy = image_commands.add_parser("copy")
    image_copy.add_argument("--source-directory", required=True, type=Path)
    _add_target_guard(image_copy)

    verify = families.add_parser("verify")
    verify.add_argument(
        "--stack", required=True, choices=("dotnet-sqlserver", "java-postgresql")
    )
    verify.add_argument("--source-commit", required=True)
    verify.add_argument("--database-artifact", required=True, type=Path)
    verify.add_argument("--target-output", required=True, type=Path)
    verify.add_argument("--output", required=True, type=Path)

    handoff = families.add_parser("render-handoff")
    handoff.add_argument("--target-output", required=True, type=Path)
    handoff.add_argument("--migration-report", required=True, type=Path)
    handoff.add_argument("--acceptance-report", required=True, type=Path)
    handoff.add_argument("--telemetry-report", required=True, type=Path)
    handoff.add_argument("--runtime-test-report", required=True, type=Path)
    handoff.add_argument(
        "--path",
        required=True,
        choices=("manual", "copilot-rewrite", "copilot-modernization"),
    )
    handoff.add_argument("--rollback-revision", required=True)
    handoff.add_argument("--rollback-runbook", required=True, type=Path)
    handoff.add_argument("--output", required=True, type=Path)
    return parser


def _add_target_guard(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--target-output", required=True, type=Path)
    parser.add_argument("--target-resource-id", required=True)
    parser.add_argument("--confirm-target-resource-id", required=True)
    parser.add_argument("--execute", required=True, action="store_true")


def _add_import(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--artifact", required=True, type=Path)
    _add_target_guard(parser)


def _operation_result(
    command: str,
    started: str,
    *,
    target: dict[str, Any] | None = None,
    artifact: dict[str, Any] | None = None,
    image_verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    document = {
        "schemaVersion": "1.0.0",
        "command": command,
        "status": "succeeded",
        "startedAt": started,
        "completedAt": timestamp(),
        "target": target,
        "artifact": artifact,
        "imageVerification": image_verification,
    }
    validate_document(document, "migration-operation-result.schema.json")
    return document


def _write_json(path: Path, document: dict[str, Any]) -> None:
    if path.exists():
        raise InvalidInputError(f"output already exists: {path}")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        raise ToolError(f"output document could not be written: {path}") from error


def _execute(args: argparse.Namespace, runner: CommandRunner) -> dict[str, Any]:
    started = timestamp()
    command = f"{args.family} {args.operation}" if hasattr(args, "operation") else args.family
    if command == "sql export":
        target = load_target_output(args.target_output, required_stage="bootstrap")
        if target["stack"] != "dotnet-sqlserver":
            raise InvalidInputError("SQL export requires a dotnet-sqlserver target")
        validate_migration_topology(runner, target)
        secrets = require_secrets(
            {"MIGRATION_SOURCE_DATABASE_PASSWORD"},
            {"MIGRATION_SOURCE_DATABASE_PASSWORD"},
        )
        artifact = export_sql(
            runner,
            server=args.source_server,
            database=args.source_database,
            username=args.source_username,
            artifact_path=args.artifact,
            password=secrets["MIGRATION_SOURCE_DATABASE_PASSWORD"],
        )
        return _operation_result(command, started, artifact=artifact)
    if command == "postgresql export":
        target = load_target_output(args.target_output, required_stage="bootstrap")
        if target["stack"] != "java-postgresql":
            raise InvalidInputError("PostgreSQL export requires a java-postgresql target")
        validate_migration_topology(runner, target)
        secrets = require_secrets(
            {"MIGRATION_SOURCE_DATABASE_PASSWORD"},
            {"MIGRATION_SOURCE_DATABASE_PASSWORD"},
        )
        artifact = export_postgresql(
            runner,
            host=args.source_host,
            port=args.source_port,
            database=args.source_database,
            username=args.source_username,
            artifact_path=args.artifact,
            password=secrets["MIGRATION_SOURCE_DATABASE_PASSWORD"],
        )
        return _operation_result(command, started, artifact=artifact)
    if command in {"sql import", "postgresql import", "images copy"}:
        target = load_target_output(args.target_output, required_stage="bootstrap")
        section = "images" if command == "images copy" else "database"
        guard_target(
            target,
            args.target_resource_id,
            args.confirm_target_resource_id,
            args.execute,
            section,
        )
        validate_migration_topology(runner, target)
        if command == "sql import":
            require_secrets(set(), set())
            artifact = import_sql(runner, artifact_path=args.artifact, target=target)
            return _operation_result(
                command,
                started,
                target=target_fragment(target),
                artifact=artifact,
            )
        if command == "postgresql import":
            authentication = target["database"]["authentication"]
            allowed = {"MIGRATION_TARGET_ADMINISTRATOR_PASSWORD"}
            required = set(allowed)
            if authentication == "password-secret":
                allowed.add("MIGRATION_TARGET_APPLICATION_PASSWORD")
                required.add("MIGRATION_TARGET_APPLICATION_PASSWORD")
            secrets = require_secrets(allowed, required)
            artifact = import_postgresql(
                runner,
                artifact_path=args.artifact,
                target=target,
                administrator_password=secrets[
                    "MIGRATION_TARGET_ADMINISTRATOR_PASSWORD"
                ],
                application_password=secrets.get(
                    "MIGRATION_TARGET_APPLICATION_PASSWORD"
                ),
            )
            return _operation_result(
                command,
                started,
                target=target_fragment(target),
                artifact=artifact,
            )
        require_secrets(set(), set())
        verification = copy_images(
            runner,
            source_directory=args.source_directory,
            target=target,
        )
        return _operation_result(
            command,
            started,
            target={
                "kind": "images",
                "resourceId": target["images"]["resourceId"],
                "provider": target["images"]["provider"],
            },
            image_verification=verification,
        )
    if args.family == "verify":
        if not COMMIT_PATTERN.fullmatch(args.source_commit):
            raise InvalidInputError("source commit must be lowercase 40-hex")
        target = load_target_output(args.target_output, required_stage="bootstrap")
        migration_execution = validate_migration_topology(runner, target)
        authentication = target["database"]["authentication"]
        allowed = (
            {"MIGRATION_TARGET_APPLICATION_PASSWORD"}
            if authentication == "password-secret"
            else set()
        )
        secrets = require_secrets(allowed, allowed)
        image_verification = verify_target_images(runner, target["images"])
        report = build_migration_report(
            runner,
            stack=args.stack,
            source_commit=args.source_commit,
            artifact_path=args.database_artifact,
            target=target,
            image_verification=image_verification,
            application_password=secrets.get("MIGRATION_TARGET_APPLICATION_PASSWORD"),
            migration_execution=migration_execution,
        )
        _write_json(args.output, report)
        return report
    if args.family == "render-handoff":
        require_secrets(set(), set())
        target = load_target_output(args.target_output, required_stage="application")
        validate_migration_topology(runner, target)
        handoff = render_handoff(
            runner=runner,
            target_path=args.target_output,
            migration_path=args.migration_report,
            acceptance_path=args.acceptance_report,
            telemetry_path=args.telemetry_report,
            runtime_path=args.runtime_test_report,
            modernization_path=args.path,
            rollback_revision=args.rollback_revision,
            rollback_runbook_path=args.rollback_runbook,
        )
        _write_json(args.output, handoff)
        return handoff
    raise InvalidInputError(f"unsupported command: {args.family}")


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: CommandRunner | None = None,
) -> int:
    """Run catalog-migrate and emit exactly one JSON result or error."""
    command: str | None = None
    try:
        args = _parser().parse_args(argv)
        command = (
            f"{args.family} {args.operation}"
            if hasattr(args, "operation")
            else args.family
        )
        document = _execute(args, runner or CommandRunner())
        print(json.dumps(document, sort_keys=True))
        return 0
    except MigrationError as error:
        redactions = [
            os.environ.get(name, "")
            for name in KNOWN_SECRETS
        ]
        print(
            json.dumps(
                error_document(error, command, redactions=redactions),
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return error.exit_code
    except (OSError, UnicodeError) as error:
        failure = ToolError("migration filesystem operation failed")
        print(
            json.dumps(error_document(failure, command), sort_keys=True),
            file=sys.stderr,
        )
        return failure.exit_code
    except Exception:
        failure = ToolError("unexpected internal migration failure")
        print(
            json.dumps(error_document(failure, command), sort_keys=True),
            file=sys.stderr,
        )
        return failure.exit_code
