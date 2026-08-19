"""Executable tests for the frozen catalog-migrate command surface."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from catalog_migrate import cli
from catalog_migrate.contracts import guard_target, load_json, require_secrets
from catalog_migrate.errors import InvalidInputError, PreconditionError

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
    """Return a valid application-stage target output."""
    return load_json(
        repo_root / "workshop/contracts/azure-target-output.application.example.json"
    )


def _target_arguments(target: dict, target_path: Path, section: str) -> list[str]:
    resource_id = target[section]["resourceId"]
    return [
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
    with pytest.raises(SystemExit) as error:
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
            "--artifact", "catalog.bacpac",
        ],
        [
            "sql", "import",
            "--artifact", "catalog.bacpac",
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
            "--artifact", "catalog.dump",
        ],
        [
            "postgresql", "import",
            "--artifact", "catalog.dump",
            "--target-output", "target.json",
            "--target-resource-id", "resource",
            "--confirm-target-resource-id", "resource",
            "--execute",
        ],
        [
            "images", "copy",
            "--source-directory", "images",
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
            "--output", "handoff.json",
        ],
    ],
)
def test_each_command_rejects_undeclared_arguments(arguments: list[str]) -> None:
    """Every frozen command path rejects arguments outside its exact declaration."""
    parser = cli._parser()
    parser.parse_args(arguments)
    with pytest.raises(SystemExit) as error:
        parser.parse_args([*arguments, "--undeclared"])
    assert error.value.code == 2


def test_sql_export_emits_schema_valid_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """SQL export uses its one declared secret and emits the frozen result."""
    monkeypatch.setenv("MIGRATION_SOURCE_DATABASE_PASSWORD", "source-secret")
    monkeypatch.setattr(cli, "export_sql", lambda *args, **kwargs: ARTIFACT)
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
        ]
    )
    assert result == 0
    assert json.loads(capsys.readouterr().out)["command"] == "sql export"


def test_postgresql_export_emits_schema_valid_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
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
            "--artifact",
            str(tmp_path / "catalog.dump"),
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
    target["database"] = {
        "resourceId": (
            "/subscriptions/00000000-0000-0000-0000-000000000000/"
            "resourceGroups/rg-mh-example/providers/Microsoft.Sql/servers/"
            "sql-example/databases/catalog"
        ),
        "family": "azure-sql",
        "server": "sql-example.database.windows.net",
        "database": "catalog",
        "authentication": "managed-identity",
        "localAdministratorPrincipal": None,
        "entraAdministratorPrincipal": None,
        "applicationPrincipal": {
            "name": "id-mh-example",
            "kind": "managed-identity",
            "principalId": "00000000-0000-0000-0000-000000000002",
        },
    }
    target_path = tmp_path / "target.json"
    target_path.write_text(json.dumps(target), encoding="utf-8")
    monkeypatch.setattr(cli, "import_sql", lambda *args, **kwargs: ARTIFACT)
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
    monkeypatch.setattr(cli, "render_handoff", lambda **kwargs: handoff)
    output = tmp_path / "handoff.json"

    result = cli.main(
        [
            "render-handoff",
            "--target-output",
            "target.json",
            "--migration-report",
            "migration.json",
            "--acceptance-report",
            "acceptance.json",
            "--telemetry-report",
            "telemetry.json",
            "--runtime-test-report",
            "runtime.json",
            "--output",
            str(output),
        ]
    )

    assert result == 0
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


def test_undeclared_secret_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A command rejects known migration secrets outside its frozen declaration."""
    monkeypatch.setenv("MIGRATION_TARGET_ADMINISTRATOR_PASSWORD", "undeclared")
    with pytest.raises(InvalidInputError):
        require_secrets(set(), set())
