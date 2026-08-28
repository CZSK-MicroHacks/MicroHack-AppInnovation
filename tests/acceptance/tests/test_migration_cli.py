"""Executable tests for the frozen catalog-migrate command surface."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from catalog_migrate import cli
from catalog_migrate.contracts import (
    guard_target,
    load_json,
    require_secrets,
    require_source_commit,
)
from catalog_migrate.errors import (
    InvalidInputError,
    PreconditionError,
    ToolError,
    error_document,
)

ARTIFACT = {
    "format": "bacpac",
    "exportTool": {"name": "SqlPackage", "version": "170.4.83"},
    "importTool": {"name": "SqlPackage", "version": "170.4.83"},
    "sha256": "0" * 64,
    "bytes": 1,
}
IMAGE_VERIFICATION = {
    "imageCount": 198,
    "imageBytes": 323011386,
    "imageSetSha256": "c706eda9b7d74a2b578b02487e6527e707819bc3cdd09adc59e3cb62ffcba7be",
    "seedManifestVersion": "1.0.0",
}


@pytest.fixture
def target(repo_root: Path) -> dict:
    """Return a valid bootstrap-stage target output."""
    target = load_json(
        repo_root / "workshop/contracts/azure-target-output.application.example.json"
    )
    target["deploymentStage"] = "bootstrap"
    target["applicationRevisionRole"] = None
    target["containerImage"] = None
    target["application"] = None
    return target


def _dotnet_bootstrap(repo_root: Path) -> dict:
    """Load the checked-in .NET bootstrap target fixture."""
    return load_json(
        repo_root / "workshop/contracts/azure-target-output.bootstrap.example.json"
    )


def _target_arguments(target: dict, target_path: Path, section: str) -> list[str]:
    resource_id = target[section]["resourceId"]
    return [
        "--source-commit",
        target["sourceCommit"],
        "--target-output",
        str(target_path),
        "--target-resource-id",
        resource_id,
        "--confirm-target-resource-id",
        resource_id,
        "--execute",
    ]


def test_exact_seven_commands_are_registered() -> None:
    """The parser exposes only the seven frozen command paths."""
    parser = cli._parser()
    help_text = parser.format_help()
    assert "{sql,postgresql,images,verify,render-handoff}" in help_text
    with pytest.raises(InvalidInputError) as error:
        parser.parse_args(["delete"])
    assert error.value.code == 2


@pytest.mark.parametrize(
    "arguments",
    [
        [
            "sql", "export",
            "--source-server", "source",
            "--source-database", "catalog",
            "--source-username", "catalog",
            "--source-commit", "0" * 40,
            "--artifact", "catalog.bacpac",
            "--target-output", "target.json",
        ],
        [
            "sql", "import",
            "--artifact", "catalog.bacpac",
            "--source-commit", "0" * 40,
            "--target-output", "target.json",
            "--target-resource-id", "resource",
            "--confirm-target-resource-id", "resource",
            "--execute",
        ],
        [
            "postgresql", "export",
            "--source-host", "source",
            "--source-port", "5432",
            "--source-database", "catalog",
            "--source-username", "catalog",
            "--source-commit", "0" * 40,
            "--artifact", "catalog.dump",
            "--target-output", "target.json",
        ],
        [
            "postgresql", "import",
            "--artifact", "catalog.dump",
            "--source-commit", "0" * 40,
            "--target-output", "target.json",
            "--target-resource-id", "resource",
            "--confirm-target-resource-id", "resource",
            "--execute",
        ],
        [
            "images", "copy",
            "--source-directory", "images",
            "--source-commit", "0" * 40,
            "--target-output", "target.json",
            "--target-resource-id", "resource",
            "--confirm-target-resource-id", "resource",
            "--execute",
        ],
        [
            "verify",
            "--stack", "java-postgresql",
            "--source-commit", "0" * 40,
            "--database-artifact", "catalog.dump",
            "--target-output", "target.json",
            "--output", "report.json",
        ],
        [
            "render-handoff",
            "--target-output", "target.json",
            "--migration-report", "migration.json",
            "--acceptance-report", "acceptance.json",
            "--telemetry-report", "telemetry.json",
            "--runtime-test-report", "runtime.json",
            "--path", "manual",
            "--rollback-revision", "catalog--baseline-000000000000",
            "--rollback-runbook", "rollback.md",
            "--output", "handoff.json",
        ],
    ],
)
def test_each_command_rejects_undeclared_arguments(arguments: list[str]) -> None:
    """Every frozen command path rejects arguments outside its exact declaration."""
    parser = cli._parser()
    parser.parse_args(arguments)
    with pytest.raises(InvalidInputError) as error:
        parser.parse_args([*arguments, "--undeclared"])
    assert error.value.code == 2


def test_sql_export_emits_schema_valid_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """SQL export uses its one declared secret and emits the frozen result."""
    monkeypatch.setenv("MIGRATION_SOURCE_DATABASE_PASSWORD", "source-secret")
    monkeypatch.setattr(cli, "export_sql", lambda *args, **kwargs: ARTIFACT)
    monkeypatch.setattr(
        cli,
        "validate_migration_topology",
        lambda *args, **kwargs: {"topologyValidated": True},
        raising=False,
    )
    target = _dotnet_bootstrap(repo_root)
    target_path = tmp_path / "target.json"
    target_path.write_text(json.dumps(target), encoding="utf-8")
    result = cli.main(
        [
            "sql",
            "export",
            "--source-server",
            "localhost",
            "--source-database",
            "catalog",
            "--source-username",
            "catalog",
            "--source-commit",
            target["sourceCommit"],
            "--artifact",
            str(tmp_path / "catalog.bacpac"),
            "--target-output",
            str(target_path),
        ]
    )
    assert result == 0
    assert json.loads(capsys.readouterr().out)["command"] == "sql export"


def test_postgresql_export_emits_schema_valid_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    target: dict,
) -> None:
    """PostgreSQL export emits the exact custom-archive identity."""
    postgresql_artifact = copy.deepcopy(ARTIFACT)
    postgresql_artifact.update(
        {
            "format": "postgresql-custom",
            "exportTool": {"name": "pg_dump", "version": "18.6"},
            "importTool": {"name": "pg_restore", "version": "18.6"},
        }
    )
    monkeypatch.setenv("MIGRATION_SOURCE_DATABASE_PASSWORD", "source-secret")
    monkeypatch.setattr(
        cli, "export_postgresql", lambda *args, **kwargs: postgresql_artifact
    )
    monkeypatch.setattr(
        cli,
        "validate_migration_topology",
        lambda *args, **kwargs: {"topologyValidated": True},
        raising=False,
    )
    target_path = tmp_path / "target.json"
    target_path.write_text(json.dumps(target), encoding="utf-8")
    result = cli.main(
        [
            "postgresql",
            "export",
            "--source-host",
            "localhost",
            "--source-port",
            "5432",
            "--source-database",
            "catalog",
            "--source-username",
            "catalog",
            "--source-commit",
            target["sourceCommit"],
            "--artifact",
            str(tmp_path / "catalog.dump"),
            "--target-output",
            str(target_path),
        ]
    )
    assert result == 0
    assert json.loads(capsys.readouterr().out)["command"] == "postgresql export"


def test_sql_import_requires_exact_target_and_execute(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    target: dict,
) -> None:
    """SQL import consumes the target output and never accepts an inferred target."""
    target["stack"] = "dotnet-sqlserver"
    target["network"]["migrationSourceVmResourceId"] = (
        "/subscriptions/00000000-0000-0000-0000-000000000000/"
        "resourceGroups/rg-mh-source-example/providers/Microsoft.Compute/"
        "virtualMachines/vm-dotnet-user001"
    )
    target["network"]["migrationPrivateDnsZoneLinkResourceIds"][0] = target[
        "network"
    ]["migrationPrivateDnsZoneLinkResourceIds"][0].replace(
        "private.postgres.database.azure.com",
        "privatelink.database.windows.net",
    )
    target["database"] = {
        "resourceId": (
            "/subscriptions/00000000-0000-0000-0000-000000000000/"
            f"resourceGroups/{target['resourceGroup']['name']}/"
            "providers/Microsoft.Sql/servers/"
            "sql-example/databases/catalog"
        ),
        "family": "azure-sql",
        "server": "sql-example.database.windows.net",
        "database": "catalog",
        "authentication": "managed-identity",
        "localAdministratorPrincipal": None,
        "entraAdministratorPrincipal": None,
        "applicationPrincipal": {
            "name": target["workloadIdentity"]["resourceId"].rsplit("/", 1)[-1],
            "kind": "managed-identity",
            "principalId": target["workloadIdentity"]["principalId"],
        },
    }
    target_path = tmp_path / "target.json"
    target_path.write_text(json.dumps(target), encoding="utf-8")
    monkeypatch.setattr(cli, "import_sql", lambda *args, **kwargs: ARTIFACT)
    monkeypatch.setattr(
        cli,
        "validate_migration_topology",
        lambda *args, **kwargs: {"topologyValidated": True},
        raising=False,
    )
    result = cli.main(
        [
            "sql",
            "import",
            "--artifact",
            str(tmp_path / "catalog.bacpac"),
            *_target_arguments(target, target_path, "database"),
        ]
    )
    assert result == 0
    assert json.loads(capsys.readouterr().out)["target"]["family"] == "azure-sql"


def test_postgresql_import_enforces_mode_specific_secrets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    target: dict,
) -> None:
    """Password mode requires separate administrator and application secrets."""
    target_path = tmp_path / "target.json"
    target_path.write_text(json.dumps(target), encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "validate_migration_topology",
        lambda *args, **kwargs: {"topologyValidated": True},
        raising=False,
    )
    monkeypatch.setenv("MIGRATION_TARGET_ADMINISTRATOR_PASSWORD", "admin-secret")
    monkeypatch.delenv("MIGRATION_TARGET_APPLICATION_PASSWORD", raising=False)
    result = cli.main(
        [
            "postgresql",
            "import",
            "--artifact",
            str(tmp_path / "catalog.dump"),
            *_target_arguments(target, target_path, "database"),
        ]
    )
    assert result == 2


def test_managed_postgresql_forbids_application_password(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    target: dict,
) -> None:
    """Managed identity mode rejects the compatibility application password."""
    target["database"]["authentication"] = "managed-identity"
    target["database"]["applicationPrincipal"] = {
        "name": "id-mh-java-example",
        "kind": "managed-identity",
        "principalId": target["workloadIdentity"]["principalId"],
    }
    target_path = tmp_path / "target.json"
    target_path.write_text(json.dumps(target), encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "validate_migration_topology",
        lambda *args, **kwargs: {"topologyValidated": True},
        raising=False,
    )
    monkeypatch.setenv("MIGRATION_TARGET_ADMINISTRATOR_PASSWORD", "admin-secret")
    monkeypatch.setenv("MIGRATION_TARGET_APPLICATION_PASSWORD", "forbidden")
    result = cli.main(
        [
            "postgresql",
            "import",
            "--artifact",
            str(tmp_path / "catalog.dump"),
            *_target_arguments(target, target_path, "database"),
        ]
    )
    assert result == 2


def test_images_copy_emits_schema_valid_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    target: dict,
) -> None:
    """Image copy reports the exact target and canonical verification."""
    target_path = tmp_path / "target.json"
    target_path.write_text(json.dumps(target), encoding="utf-8")
    monkeypatch.setattr(cli, "copy_images", lambda *args, **kwargs: IMAGE_VERIFICATION)
    monkeypatch.setattr(
        cli,
        "validate_migration_topology",
        lambda *args, **kwargs: {"topologyValidated": True},
        raising=False,
    )
    result = cli.main(
        [
            "images",
            "copy",
            "--source-directory",
            str(tmp_path / "images"),
            *_target_arguments(target, target_path, "images"),
        ]
    )
    assert result == 0
    document = json.loads(capsys.readouterr().out)
    assert document["command"] == "images copy"
    assert document["artifact"] is None


def test_verify_writes_the_exact_migration_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    repo_root: Path,
    tmp_path: Path,
    target: dict,
) -> None:
    """Verify writes and emits the schema-valid report returned by bounded checks."""
    target_path = tmp_path / "target.json"
    target_path.write_text(json.dumps(target), encoding="utf-8")
    report = load_json(
        repo_root / "workshop/contracts/migration-report.postgresql.example.json"
    )
    report["sourceCommit"] = target["sourceCommit"]
    monkeypatch.setenv("MIGRATION_TARGET_APPLICATION_PASSWORD", "application-secret")
    monkeypatch.setattr(
        cli,
        "verify_target_images",
        lambda *args, **kwargs: IMAGE_VERIFICATION,
    )
    monkeypatch.setattr(
        cli,
        "build_migration_report",
        lambda *args, **kwargs: report,
    )
    monkeypatch.setattr(
        cli,
        "validate_migration_topology",
        lambda *args, **kwargs: report["migrationExecution"],
        raising=False,
    )
    output = tmp_path / "migration.json"

    result = cli.main(
        [
            "verify",
            "--stack",
            "java-postgresql",
            "--source-commit",
            target["sourceCommit"],
            "--database-artifact",
            str(tmp_path / "catalog.dump"),
            "--target-output",
            str(target_path),
            "--output",
            str(output),
        ]
    )

    assert result == 0
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert json.loads(capsys.readouterr().out) == report


def test_render_handoff_writes_the_schema_valid_document(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """The seventh command persists exactly one validated modernization handoff."""
    handoff = load_json(
        repo_root / "workshop/contracts/modernization-contract.example.json"
    )
    target = load_json(
        repo_root / "workshop/contracts/azure-target-output.application.example.json"
    )
    target_path = tmp_path / "target.json"
    target_path.write_text(json.dumps(target), encoding="utf-8")
    rendered: dict[str, object] = {}

    def render(**kwargs: object) -> dict:
        rendered.update(kwargs)
        return handoff

    monkeypatch.setattr(cli, "render_handoff", render)
    monkeypatch.setattr(
        cli,
        "validate_migration_topology",
        lambda *args, **kwargs: {"topologyValidated": True},
    )
    output = tmp_path / "handoff.json"

    result = cli.main(
        [
            "render-handoff",
            "--target-output",
            str(target_path),
            "--migration-report",
            "migration.json",
            "--acceptance-report",
            "acceptance.json",
            "--telemetry-report",
            "telemetry.json",
            "--runtime-test-report",
            "runtime.json",
            "--path",
            "manual",
            "--rollback-revision",
            "catalog--baseline-000000000000",
            "--rollback-runbook",
            str(repo_root / "infra/README.md"),
            "--output",
            str(output),
        ]
    )

    assert result == 0
    assert rendered["modernization_path"] == "manual"
    assert rendered["output_path"] == output
    assert rendered["rollback_runbook_path"] == repo_root / "infra/README.md"
    assert json.loads(output.read_text(encoding="utf-8")) == handoff
    assert json.loads(capsys.readouterr().out) == handoff


def test_target_guard_rejects_wrong_confirmation_and_execute(target: dict) -> None:
    """Mutations cannot proceed with a mismatched confirmation or false execute flag."""
    resource_id = target["database"]["resourceId"]
    with pytest.raises(InvalidInputError):
        guard_target(target, "wrong", resource_id, True, "database")
    with pytest.raises(PreconditionError):
        guard_target(target, resource_id, "wrong", True, "database")
    with pytest.raises(PreconditionError):
        guard_target(target, resource_id, resource_id, False, "database")


def test_source_commit_guard_rejects_invalid_or_stale_identity(target: dict) -> None:
    """Every transfer command binds the bootstrap target to one source commit."""
    require_source_commit(target, target["sourceCommit"])
    with pytest.raises(InvalidInputError, match="lowercase 40-hex"):
        require_source_commit(target, "invalid")
    with pytest.raises(InvalidInputError, match="differs from target output"):
        require_source_commit(target, "1" * 40)


def test_verify_rejects_stale_source_before_topology_or_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    target: dict,
) -> None:
    """Verification cannot relabel a protected target for another source commit."""
    target_path = tmp_path / "target.json"
    target_path.write_text(json.dumps(target), encoding="utf-8")
    output = tmp_path / "migration.json"

    def unexpected_topology(*args: object, **kwargs: object) -> dict:
        raise AssertionError("topology must not run for stale source identity")

    monkeypatch.setattr(
        cli,
        "validate_migration_topology",
        unexpected_topology,
        raising=False,
    )
    result = cli.main(
        [
            "verify",
            "--stack",
            "java-postgresql",
            "--source-commit",
            "1" * 40,
            "--database-artifact",
            str(tmp_path / "catalog.dump"),
            "--target-output",
            str(target_path),
            "--output",
            str(output),
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert captured.out == ""
    assert "source commit differs from target output" in json.loads(captured.err)[
        "error"
    ]["message"]
    assert not output.exists()


def test_undeclared_secret_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A command rejects known migration secrets outside its frozen declaration."""
    monkeypatch.setenv("MIGRATION_TARGET_ADMINISTRATOR_PASSWORD", "undeclared")
    with pytest.raises(InvalidInputError):
        require_secrets(set(), set())


def test_cli_parser_failure_is_one_typed_json_document(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Parser failures use the frozen JSON error protocol without usage text."""
    result = cli.main(["delete"])

    captured = capsys.readouterr()
    error = json.loads(captured.err)
    assert captured.out == ""
    assert error == {
        "schemaVersion": "1.0.0",
        "status": "failed",
        "command": None,
        "exitCode": 2,
        "error": {
            "code": "invalid-input",
            "message": error["error"]["message"],
        },
    }
    assert "\n" not in error["error"]["message"]


def test_error_redaction_precedes_message_truncation() -> None:
    """A long echoed secret cannot leak a truncated prefix."""
    secret = "secret-" + ("x" * 1100)
    document = error_document(
        ToolError(f"external tool failed: {secret}"),
        "sql export",
        redactions=[secret],
    )

    assert "secret-" not in document["error"]["message"]
    assert "[REDACTED]" in document["error"]["message"]


def test_bootstrap_commands_reject_application_output(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """Migration operations cannot consume an application-stage output."""
    application = load_json(
        repo_root / "workshop/contracts/azure-target-output.application.example.json"
    )
    target_path = tmp_path / "application.json"
    target_path.write_text(json.dumps(application), encoding="utf-8")
    monkeypatch.setenv("MIGRATION_SOURCE_DATABASE_PASSWORD", "source-secret")

    result = cli.main(
        [
            "sql",
            "export",
            "--source-server",
            "localhost",
            "--source-database",
            "catalog",
            "--source-username",
            "catalog",
            "--artifact",
            str(tmp_path / "catalog.bacpac"),
            "--target-output",
            str(target_path),
        ]
    )

    assert result == 2


def test_both_database_clients_decode_as_utf8_like_the_catalog_they_compare() -> None:
    """The decode must match the data, and the fixture proves why it must.

    This pins a *relation*: the seed catalog is UTF-8 and contains characters
    that no single-byte console code page can decode, so any client output
    decoded through the host locale either mojibakes the row or raises far from
    the call site. Pinning one client and leaving the other on the interpreter
    default is the failure this guard exists to prevent, so it fails if the
    decoding becomes conditional on which client is running again.
    """
    root = Path(__file__).resolve().parents[3]
    source = (
        root / "tests/acceptance/catalog_acceptance/database.py"
    ).read_text(encoding="utf-8")

    assert 'if client_name == "psql" else {}' not in source, (
        "database client decoding must not be conditional on the client; the "
        "sqlcmd path was left on the interpreter default and failed on cp1252"
    )
    assert '{"encoding": "utf-8", "errors": "strict"}' in source
    assert "UnicodeDecodeError" in source, (
        "a decode failure must be named, not surface as AttributeError on None"
    )

    fixture = (root / "tests/acceptance/fixtures/catalog.valid.json").read_bytes()
    try:
        fixture.decode("cp1252")
    except UnicodeDecodeError:
        return
    raise AssertionError(
        "the fixture no longer proves the hazard; if it became cp1252-clean the "
        "UTF-8 pin above must be re-justified rather than assumed"
    )


def test_a_crashing_acceptance_run_cannot_leave_a_stale_report_on_disk() -> None:
    """The report is written after the run, so a crash must not preserve the old one.

    Without this the sequence green run, fault injection, crashing re-run leaves
    a pre-injection green report in place, and the handoff certifies an
    acceptance result that predates the changes it is attesting to.
    """
    root = Path(__file__).resolve().parents[3]
    source = (
        root / "tests/acceptance/catalog_acceptance/cli.py"
    ).read_text(encoding="utf-8")

    unlink = source.find("unlink(missing_ok=True)")
    run = source.find("AcceptanceRunner(settings).run()")
    assert unlink != -1, "the previous report must be removed before the run"
    assert unlink < run, (
        "the stale report must be removed *before* the run, otherwise a crash "
        "inside run() preserves it"
    )
