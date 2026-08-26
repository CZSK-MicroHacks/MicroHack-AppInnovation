"""Safety and tool-boundary tests for database migration operations."""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace
from pathlib import Path

import pytest

from catalog_migrate import database
from catalog_migrate.errors import (
    InvalidInputError,
    PreconditionError,
    ToolError,
    VerificationError,
)
from catalog_migrate.process import CommandRunner, ProcessResult


class RecordingRunner:
    """Record subprocess boundaries and provide deterministic command output."""

    def __init__(self, expected_user: dict | None = None) -> None:
        self.calls: list[tuple[list[str], dict[str, str], str | None]] = []
        self.redactions: list[list[str]] = []
        self.expected_user = expected_user

    def run(
        self,
        argv: list[str],
        *,
        environment: dict[str, str] | None = None,
        input_text: str | None = None,
        redactions: list[str] | tuple[str, ...] = (),
        timeout: int = 300,
    ) -> ProcessResult:
        """Capture one simulated command."""
        del timeout
        self.calls.append((list(argv), dict(environment or {}), input_text))
        self.redactions.append(list(redactions))
        if argv[:5] == ["az", "ad", "signed-in-user", "show", "--output"]:
            return ProcessResult(json.dumps(self.expected_user), "")
        if argv[:3] == ["az", "account", "get-access-token"]:
            return ProcessResult("transient-token\n", "")
        if argv[:2] == ["az", "version"]:
            return ProcessResult('{"azure-cli":"2.80.0"}', "")
        if argv[:2] == ["sqlcmd", "--version"]:
            return ProcessResult("sqlcmd 1.7.0", "")
        if argv[0] == "sqlcmd" and any(
            "STRING_AGG(r.name" in argument for argument in argv
        ):
            return ProcessResult("db_datareader,db_datawriter\n", "")
        if argv[0] == "sqlcmd" and any(
            "FROM sys.database_principals WHERE name = N'catalog'" in argument
            for argument in argv
        ):
            return ProcessResult("0\n", "")
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
    """SqlPackage reads a protected transient response file without secret argv."""
    runner = RecordingRunner()
    artifact = tmp_path / "catalog.bacpac"
    response: dict[str, object] = {}

    def create_artifact(*args, **kwargs) -> ProcessResult:
        result = RecordingRunner.run(runner, *args, **kwargs)
        if args[0][0] == "SqlPackage" and "/Action:Export" in args[0]:
            response_path = Path(
                next(argument[1:] for argument in args[0] if argument.startswith("@"))
            )
            response["path"] = response_path
            response["content"] = response_path.read_text(encoding="utf-8")
            artifact.write_bytes(b"x")
        return result

    monkeypatch.setattr(runner, "run", create_artifact)
    monkeypatch.setattr(
        database,
        "verify_source_database",
        lambda *args, **kwargs: {"schemaVerified": True},
    )
    database.export_sql(
        runner,
        server="localhost",
        database="catalog",
        username="catalog",
        artifact_path=artifact,
        password="source-secret",
    )
    export_index = next(
        index
        for index, call in enumerate(runner.calls)
        if "/Action:Export" in call[0]
    )
    export_call = runner.calls[export_index]
    assert all("source-secret" not in argument for argument in export_call[0])
    assert "/SourceTrustServerCertificate:True" in export_call[0]
    assert export_call[1] == {}
    assert runner.redactions[export_index] == ["source-secret"]
    assert response["content"] == "/SourcePassword:source-secret\n"
    assert not Path(response["path"]).exists()


def test_windows_sqlpackage_response_directory_gets_a_protected_acl(
    tmp_path: Path,
) -> None:
    """Windows protection removes inheritance before a response file is written."""
    runner = RecordingRunner()
    database._protect_secret_directory(
        runner,
        tmp_path,
        platform_name="nt",
    )

    argv, environment, input_text = runner.calls[0]
    assert argv == [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "-",
    ]
    assert environment == {"MIGRATION_SECRET_DIRECTORY": str(tmp_path)}
    assert "SetAccessRuleProtection($true, $false)" in str(input_text)
    assert "source-secret" not in str(input_text)


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
    assert "ALTER ROLE [db_owner] DROP MEMBER [catalog]" in principal_call[0][-1]
    assert principal_call[0][-1].index("DROP USER [catalog]") < principal_call[0][
        -1
    ].index("CREATE USER [id-mh-team-dotnet]")
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


def test_postgresql_verification_requires_each_table_privilege() -> None:
    """A comma-list must not let one privilege stand in for all required grants."""
    predicates = database._postgresql_table_privilege_predicates("catalog_app")

    assert "SELECT,INSERT,UPDATE,DELETE" not in predicates
    assert predicates.count("has_table_privilege(") == 8
    for table in ("figures", "categories"):
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            assert f"'public.{table}', '{privilege}'" in predicates


def test_migration_report_rejects_a_commit_different_from_target() -> None:
    """Migration evidence cannot be relabeled with an unrelated release commit."""
    with pytest.raises(InvalidInputError, match="source commit differs"):
        database.build_migration_report(
            RecordingRunner(),
            stack="dotnet-sqlserver",
            source_commit="b" * 40,
            artifact_path=Path("unused.bacpac"),
            target={
                "stack": "dotnet-sqlserver",
                "sourceCommit": "a" * 40,
            },
            image_verification={},
            application_password=None,
            migration_execution={},
        )


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


def test_command_runner_redacts_without_forwarding_a_response_file_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SqlPackage response-file secrets redact failures without entering its environment."""
    captured_environment: dict[str, str] = {}

    def failed(*args, **kwargs):
        captured_environment.update(kwargs["env"])
        return subprocess.CompletedProcess(
            args[0],
            1,
            stdout="",
            stderr="authentication failed for response-secret",
        )

    monkeypatch.setattr(subprocess, "run", failed)

    with pytest.raises(ToolError) as error:
        CommandRunner().run(["tool"], redactions=["response-secret"])

    assert "response-secret" not in captured_environment.values()
    assert "response-secret" not in str(error.value)
    assert "[REDACTED]" in str(error.value)


def test_command_runner_uses_a_minimal_child_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inherited credentials and undeclared migration values never reach tools."""
    captured: dict[str, str] = {}
    monkeypatch.setenv("GITHUB_TOKEN", "host-token")
    monkeypatch.setenv("MIGRATION_UNDECLARED_SECRET", "migration-secret")

    def completed(*args, **kwargs):
        captured.update(kwargs["env"])
        return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", completed)
    CommandRunner().run(
        ["tool"],
        environment={"PGPASSWORD": "declared-secret"},
    )

    assert captured["PGPASSWORD"] == "declared-secret"
    assert "GITHUB_TOKEN" not in captured
    assert "MIGRATION_UNDECLARED_SECRET" not in captured


def test_target_database_verification_reuses_the_full_acceptance_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Migration verification delegates to complete schema and corpus checks."""
    observed: dict = {}

    def verify_connection(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(figure_count=198, category_count=20)

    monkeypatch.setattr(
        database,
        "verify_database_connection",
        verify_connection,
        raising=False,
    )
    target = {
        "stack": "dotnet-sqlserver",
        "database": {
            "family": "azure-sql",
            "server": "catalog.database.windows.net",
            "database": "catalog",
            "authentication": "managed-identity",
            "applicationPrincipal": {"name": "id-catalog"},
        },
    }

    verification = database.verify_target_database(RecordingRunner(), target)

    assert observed["kind"] == "sqlserver"
    assert observed["target"] == "managed"
    assert verification["verifiedRowCounts"] == {"figures": 198, "categories": 20}


def test_target_database_verification_rejects_the_legacy_sql_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verification fails if the imported db_owner-era user still exists."""

    class LegacyPrincipalRunner(RecordingRunner):
        def run(self, argv, **kwargs) -> ProcessResult:
            result = super().run(argv, **kwargs)
            if argv[0] == "sqlcmd" and any(
                "FROM sys.database_principals WHERE name = N'catalog'" in argument
                for argument in argv
            ):
                return ProcessResult("1\n", "")
            return result

    monkeypatch.setattr(
        database,
        "verify_database_connection",
        lambda **kwargs: SimpleNamespace(figure_count=198, category_count=20),
        raising=False,
    )
    target = {
        "stack": "dotnet-sqlserver",
        "database": {
            "family": "azure-sql",
            "server": "catalog.database.windows.net",
            "database": "catalog",
            "authentication": "managed-identity",
            "applicationPrincipal": {"name": "id-catalog"},
        },
    }

    with pytest.raises(VerificationError, match="privileged legacy"):
        database.verify_target_database(LegacyPrincipalRunner(), target)


def test_source_contains_no_delete_or_resource_mutation_commands(repo_root: Path) -> None:
    """Migration implementation has no delete or Azure resource-management command.

    The module count is asserted because the check is a substring search over a joined
    string: if the walk returns nothing, the join produces ``""`` and every forbidden
    token is trivially absent. A destructive command could then be added to the
    migration code with this guard still reporting green.
    """
    modules = sorted((repo_root / "tests/acceptance/catalog_migrate").rglob("*.py"))
    assert len(modules) >= 10, (
        f"only {len(modules)} migration modules found; this guard is not reading the "
        "implementation it claims to protect"
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in modules)
    offending = [token for token in (
        '"delete"',
        "'delete'",
        '"group", "create"',
        '"resource", "create"',
        '"deployment", "create"',
    ) if token in source]
    assert not offending, (
        "the migration implementation may only read and copy; these commands mutate or "
        "destroy Azure resources: " + ", ".join(offending)
    )
