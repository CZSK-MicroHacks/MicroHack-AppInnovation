"""Safety and tool-boundary tests for database migration operations."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from catalog_migrate import database
from catalog_migrate.errors import InvalidInputError, PreconditionError, ToolError
from catalog_migrate.process import CommandRunner, ProcessResult


class RecordingRunner:
    """Record subprocess boundaries and provide deterministic command output."""

    def __init__(self, expected_user: dict | None = None) -> None:
        self.calls: list[tuple[list[str], dict[str, str], str | None]] = []
        self.expected_user = expected_user

    def run(
        self,
        argv: list[str],
        *,
        environment: dict[str, str] | None = None,
        input_text: str | None = None,
        timeout: int = 300,
    ) -> ProcessResult:
        """Capture one simulated command."""
        del timeout
        self.calls.append((list(argv), dict(environment or {}), input_text))
        if argv[:5] == ["az", "ad", "signed-in-user", "show", "--output"]:
            return ProcessResult(json.dumps(self.expected_user), "")
        if argv[:3] == ["az", "account", "get-access-token"]:
            return ProcessResult("transient-token\n", "")
        if argv[:2] == ["az", "version"]:
            return ProcessResult('{"azure-cli":"2.80.0"}', "")
        if argv[:2] == ["sqlcmd", "--version"]:
            return ProcessResult("sqlcmd 1.7.0", "")
        if "--version" in argv:
            return ProcessResult(f"{argv[0]} (PostgreSQL) 18.6", "")
        if argv[:2] == ["SqlPackage", "/Version"]:
            return ProcessResult("170.4.83", "")
        return ProcessResult("", "")


class NonemptyRunner(RecordingRunner):
    """Return a positive table count for target-empty preflight queries."""

    def run(self, argv, **kwargs) -> ProcessResult:
        result = super().run(argv, **kwargs)
        if argv[0] == "sqlcmd" and "-Q" in argv:
            return ProcessResult("1\n", "")
        if argv[0] == "psql" and "-c" in argv:
            return ProcessResult("1\n", "")
        return result


class EmptySqlRunner(RecordingRunner):
    """Return an empty Azure SQL target while recording every import boundary."""

    def run(self, argv, **kwargs) -> ProcessResult:
        result = super().run(argv, **kwargs)
        if argv[0] == "sqlcmd" and any(
            "SELECT COUNT(*) FROM sys.tables;" in argument for argument in argv
        ):
            return ProcessResult("0\n", "")
        return result


def test_sql_export_keeps_password_out_of_subprocess_argv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """SqlPackage receives the source password only through child environment."""
    runner = RecordingRunner()
    artifact = tmp_path / "catalog.bacpac"

    def create_artifact(*args, **kwargs) -> ProcessResult:
        result = RecordingRunner.run(runner, *args, **kwargs)
        if args[0][0] == "SqlPackage" and "/Action:Export" in args[0]:
            artifact.write_bytes(b"x")
        return result

    monkeypatch.setattr(runner, "run", create_artifact)
    database.export_sql(
        runner,
        server="localhost",
        database="catalog",
        username="catalog",
        artifact_path=artifact,
        password="source-secret",
    )
    export_call = next(call for call in runner.calls if "/Action:Export" in call[0])
    assert all("source-secret" not in argument for argument in export_call[0])
    assert export_call[1]["SQLPACKAGE_SOURCEPASSWORD"] == "source-secret"


def test_wrong_engine_and_changed_artifacts_are_rejected(tmp_path: Path) -> None:
    """Import refuses wrong suffixes, engine metadata, and altered bytes."""
    artifact = tmp_path / "catalog.bacpac"
    artifact.write_bytes(b"database")
    document = database.artifact_document(artifact, "sqlserver")
    database.write_metadata(
        artifact,
        family="postgresql",
        server="localhost",
        database="catalog",
        artifact=document,
    )
    with pytest.raises(InvalidInputError):
        database.require_artifact(artifact, "sqlserver")
    with pytest.raises(InvalidInputError):
        database.require_artifact(tmp_path / "catalog.dump", "sqlserver")


def test_sql_import_refuses_a_nonempty_target(tmp_path: Path) -> None:
    """SQL import stops before SqlPackage mutation when user tables already exist."""
    artifact = tmp_path / "catalog.bacpac"
    artifact.write_bytes(b"database")
    document = database.artifact_document(artifact, "sqlserver")
    database.write_metadata(
        artifact,
        family="sqlserver",
        server="source",
        database="catalog",
        artifact=document,
    )
    target = {
        "stack": "dotnet-sqlserver",
        "database": {
            "server": "catalog.database.windows.net",
            "database": "catalog",
        },
    }
    runner = NonemptyRunner()

    with pytest.raises(PreconditionError, match="not empty"):
        database.import_sql(runner, artifact_path=artifact, target=target)

    assert not any("/Action:Import" in call[0] for call in runner.calls)


def test_sql_import_supports_hyphenated_workload_identity_without_secret_argv(
    tmp_path: Path,
) -> None:
    """SQL import uses the facilitator context for the exact workload identity."""
    artifact = tmp_path / "catalog.bacpac"
    artifact.write_bytes(b"database")
    document = database.artifact_document(artifact, "sqlserver")
    database.write_metadata(
        artifact,
        family="sqlserver",
        server="source",
        database="catalog",
        artifact=document,
    )
    target = {
        "stack": "dotnet-sqlserver",
        "database": {
            "server": "catalog.database.windows.net",
            "database": "catalog",
            "applicationPrincipal": {
                "name": "id-mh-team-dotnet",
                "principalId": "00000000-0000-0000-0000-000000000002",
            },
        },
    }
    runner = EmptySqlRunner()

    database.import_sql(runner, artifact_path=artifact, target=target)

    import_call = next(call for call in runner.calls if "/Action:Import" in call[0])
    assert import_call[1]["AZURE_CONFIG_DIR"] == str(Path.home() / ".azure-365")
    assert "transient-token" not in import_call[0]
    principal_call = next(
        call
        for call in runner.calls
        if call[0][0] == "sqlcmd" and "CREATE USER" in call[0][-1]
    )
    assert "[id-mh-team-dotnet]" in principal_call[0][-1]
    assert principal_call[1]["SQLCMDACCESS_TOKEN"] == "transient-token"
    assert "transient-token" not in principal_call[0]


def test_postgresql_import_refuses_a_nonempty_target(tmp_path: Path) -> None:
    """PostgreSQL import stops before restore when public tables already exist."""
    artifact = tmp_path / "catalog.dump"
    artifact.write_bytes(b"database")
    document = database.artifact_document(artifact, "postgresql")
    database.write_metadata(
        artifact,
        family="postgresql",
        server="source",
        database="catalog",
        artifact=document,
    )
    target = {
        "stack": "java-postgresql",
        "database": {
            "server": "catalog.postgres.database.azure.com",
            "database": "catalog",
            "authentication": "password-secret",
            "localAdministratorPrincipal": {"name": "catalogadmin"},
            "applicationPrincipal": {"name": "catalog_app"},
        },
    }
    runner = NonemptyRunner()

    with pytest.raises(PreconditionError, match="not empty"):
        database.import_postgresql(
            runner,
            artifact_path=artifact,
            target=target,
            administrator_password="admin-secret",
            application_password="application-secret",
        )

    assert not any(
        call[0][0] == "pg_restore" and "--version" not in call[0]
        for call in runner.calls
    )


def test_postgresql_principals_accept_hyphenated_workload_identity() -> None:
    """Managed PostgreSQL accepts the Bicep workload identity display name."""
    database._validate_postgresql_principals(
        {
            "localAdministratorPrincipal": {"name": "catalogadmin"},
            "applicationPrincipal": {"name": "id-mh-team-java"},
        }
    )


def test_managed_bootstrap_checks_exact_entra_administrator_and_false_flags() -> None:
    """Managed bootstrap uses the isolated CLI user, postgres database, and false flags."""
    target = {
        "workloadIdentity": {
            "principalId": "00000000-0000-0000-0000-000000000002",
        },
        "database": {
            "server": "pg.example.postgres.database.azure.com",
            "database": "catalog",
            "entraAdministratorPrincipal": {
                "name": "facilitator@example.com",
                "objectId": "00000000-0000-0000-0000-000000000003",
                "principalType": "user",
            },
            "applicationPrincipal": {
                "name": "id-example",
                "principalId": "00000000-0000-0000-0000-000000000002",
            },
        }
    }
    runner = RecordingRunner(
        {
            "id": "00000000-0000-0000-0000-000000000003",
            "userPrincipalName": "facilitator@example.com",
        }
    )
    database._bootstrap_managed_principal(runner, target)
    az_calls = [call for call in runner.calls if call[0][0] == "az"]
    assert all(
        call[1]["AZURE_CONFIG_DIR"] == str(Path.home() / ".azure-365")
        for call in az_calls
    )
    create_call = next(
        call for call in runner.calls if call[2] and "pgaadauth_create_principal" in call[2]
    )
    assert "false, false" in create_call[2]
    assert create_call[0][create_call[0].index("--dbname") + 1] == "postgres"
    assert create_call[1] == {"PGPASSWORD": "transient-token"}
    assert "transient-token" not in create_call[0]


def test_managed_bootstrap_rejects_entra_administrator_mismatch() -> None:
    """A different signed-in user cannot bootstrap the workload identity."""
    target = {
        "workloadIdentity": {
            "principalId": "00000000-0000-0000-0000-000000000002",
        },
        "database": {
            "server": "pg.example.postgres.database.azure.com",
            "database": "catalog",
            "entraAdministratorPrincipal": {
                "name": "facilitator@example.com",
                "objectId": "00000000-0000-0000-0000-000000000003",
            },
            "applicationPrincipal": {
                "name": "id-example",
                "principalId": "00000000-0000-0000-0000-000000000002",
            },
        }
    }
    runner = RecordingRunner(
        {
            "id": "00000000-0000-0000-0000-000000000099",
            "userPrincipalName": "other@example.com",
        }
    )
    with pytest.raises(PreconditionError):
        database._bootstrap_managed_principal(runner, target)
    assert not any(
        call[2] and "pgaadauth_create_principal" in call[2] for call in runner.calls
    )


def test_password_role_reads_application_secret_from_environment() -> None:
    """The compatibility role password never appears in argv or static SQL text."""
    runner = RecordingRunner()
    database._bootstrap_password_principal(
        runner,
        {
            "server": "pg.example.postgres.database.azure.com",
            "database": "catalog",
            "localAdministratorPrincipal": {"name": "catalogadmin"},
            "applicationPrincipal": {"name": "catalog_app"},
        },
        "admin-secret",
        "application-secret",
    )
    argv, environment, script = runner.calls[-1]
    assert all("application-secret" not in argument for argument in argv)
    assert "application-secret" not in script
    assert "\\getenv app_password MIGRATION_TARGET_APPLICATION_PASSWORD" in script
    assert "\\gexec" in script
    assert environment["MIGRATION_TARGET_APPLICATION_PASSWORD"] == "application-secret"


def test_command_runner_maps_timeout_and_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timeouts and nonzero exits map to the frozen tool-failed condition."""
    runner = CommandRunner()

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(ToolError) as timeout_error:
        runner.run(["tool"])
    assert timeout_error.value.exit_code == 4

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 1, stdout="", stderr="failed"
        ),
    )
    with pytest.raises(ToolError) as failure_error:
        runner.run(["tool"])
    assert failure_error.value.exit_code == 4


def test_command_runner_redacts_child_secrets_from_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool output cannot copy a child-only password or token into the error JSON."""
    runner = CommandRunner()
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            1,
            stdout="",
            stderr="authentication failed for transient-secret",
        ),
    )

    with pytest.raises(ToolError) as error:
        runner.run(
            ["tool"],
            environment={"PGPASSWORD": "transient-secret"},
        )

    assert "transient-secret" not in str(error.value)
    assert "[REDACTED]" in str(error.value)


def test_source_contains_no_delete_or_resource_mutation_commands(repo_root: Path) -> None:
    """Migration implementation has no delete or Azure resource-management command."""
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (repo_root / "tests/acceptance/catalog_migrate").rglob("*.py")
    )
    forbidden = (
        '"delete"',
        "'delete'",
        '"group", "create"',
        '"resource", "create"',
        '"deployment", "create"',
    )
    assert all(token not in source for token in forbidden)
