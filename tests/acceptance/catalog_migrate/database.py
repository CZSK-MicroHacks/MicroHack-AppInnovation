"""Database export, import, principal bootstrap, and verification operations."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from catalog_migrate.contracts import (
    artifact_metadata_path,
    load_json,
    repository_root,
    validate_document,
)
from catalog_migrate.errors import InvalidInputError, PreconditionError, VerificationError
from catalog_migrate.models import Artifact, DatabaseTool
from catalog_migrate.process import CommandRunner

SQLPACKAGE_VERSION = "170.4.83"
POSTGRESQL_VERSION = "18.6"
AZURE_CLI_VERSION = "2.80.0"
SQLCMD_VERSION = "1.7.0"
AZURE_CONFIG = str(Path.home() / ".azure-365")
IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,62}$")


def timestamp() -> str:
    """Return an RFC 3339 UTC timestamp."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    """Hash one migration artifact.

    Raises:
        InvalidInputError: If the artifact is absent or empty.
    """
    if not path.is_file() or path.stat().st_size <= 0:
        raise InvalidInputError(f"migration artifact is absent or empty: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_document(path: Path, family: str) -> dict[str, Any]:
    """Build the frozen artifact identity for SQL Server or PostgreSQL."""
    if family == "sqlserver":
        format_name = "bacpac"
        export_tool = import_tool = DatabaseTool(
            name="SqlPackage", version=SQLPACKAGE_VERSION
        )
    elif family == "postgresql":
        format_name = "postgresql-custom"
        export_tool = DatabaseTool(name="pg_dump", version=POSTGRESQL_VERSION)
        import_tool = DatabaseTool(name="pg_restore", version=POSTGRESQL_VERSION)
    else:
        raise InvalidInputError(f"unsupported artifact family: {family}")
    return Artifact(
        format=format_name,
        exportTool=export_tool,
        importTool=import_tool,
        sha256=file_sha256(path),
        bytes=path.stat().st_size,
    ).model_dump()


def require_artifact(path: Path, family: str) -> dict[str, Any]:
    """Validate artifact suffix, sidecar family, size, and digest.

    Raises:
        InvalidInputError: If the artifact belongs to the wrong engine or was altered.
    """
    expected_suffix = ".bacpac" if family == "sqlserver" else ".dump"
    if path.suffix.casefold() != expected_suffix:
        raise InvalidInputError(
            f"{family} artifacts must use the {expected_suffix} suffix"
        )
    sidecar = load_json(artifact_metadata_path(path))
    if sidecar.get("family") != family:
        raise InvalidInputError("artifact metadata belongs to a different engine")
    artifact = artifact_document(path, family)
    if sidecar.get("artifact") != artifact:
        raise InvalidInputError("artifact digest or tool identity differs from metadata")
    return artifact


def write_metadata(
    path: Path,
    *,
    family: str,
    server: str,
    database: str,
    artifact: dict[str, Any],
) -> None:
    """Write a non-secret immutable artifact sidecar."""
    document = {
        "schemaVersion": "1.0.0",
        "family": family,
        "server": server,
        "database": database,
        "artifact": artifact,
    }
    metadata = artifact_metadata_path(path)
    metadata.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def azure_environment() -> dict[str, str]:
    """Return the mandatory isolated Azure CLI environment."""
    return {"AZURE_CONFIG_DIR": AZURE_CONFIG}


def check_tool_versions(
    runner: CommandRunner,
    *,
    sqlpackage: bool = False,
    sqlcmd: bool = False,
    postgresql: bool = False,
    azure: bool = False,
) -> None:
    """Require exact frozen external tool versions before an operation."""
    if sqlpackage:
        result = runner.run(["SqlPackage", "/Version"])
        if SQLPACKAGE_VERSION not in result.stdout:
            raise PreconditionError(f"SqlPackage {SQLPACKAGE_VERSION} is required")
    if sqlcmd:
        result = runner.run(["sqlcmd", "--version"])
        if SQLCMD_VERSION not in result.stdout:
            raise PreconditionError(f"sqlcmd {SQLCMD_VERSION} is required")
    if postgresql:
        for tool in ("pg_dump", "pg_restore", "psql"):
            result = runner.run([tool, "--version"])
            if POSTGRESQL_VERSION not in result.stdout:
                raise PreconditionError(f"{tool} {POSTGRESQL_VERSION} is required")
    if azure:
        result = runner.run(
            ["az", "version", "--output", "json"],
            environment=azure_environment(),
        )
        try:
            version = json.loads(result.stdout)["azure-cli"]
        except (KeyError, json.JSONDecodeError) as error:
            raise PreconditionError("Azure CLI version output is invalid") from error
        if version != AZURE_CLI_VERSION:
            raise PreconditionError(f"Azure CLI {AZURE_CLI_VERSION} is required")


def export_sql(
    runner: CommandRunner,
    *,
    server: str,
    database: str,
    username: str,
    artifact_path: Path,
    password: str,
) -> dict[str, Any]:
    """Export a SQL Server source into a pinned BACPAC."""
    if artifact_path.suffix.casefold() != ".bacpac":
        raise InvalidInputError("SQL Server export artifact must end in .bacpac")
    if artifact_path.exists() or artifact_metadata_path(artifact_path).exists():
        raise PreconditionError("export artifact or metadata already exists")
    check_tool_versions(runner, sqlpackage=True)
    runner.run(
        [
            "SqlPackage",
            "/Action:Export",
            f"/SourceServerName:{server}",
            f"/SourceDatabaseName:{database}",
            f"/SourceUser:{username}",
            f"/TargetFile:{artifact_path}",
        ],
        environment={"SQLPACKAGE_SOURCEPASSWORD": password},
        timeout=1800,
    )
    artifact = artifact_document(artifact_path, "sqlserver")
    write_metadata(
        artifact_path,
        family="sqlserver",
        server=server,
        database=database,
        artifact=artifact,
    )
    return artifact


def export_postgresql(
    runner: CommandRunner,
    *,
    host: str,
    port: int,
    database: str,
    username: str,
    artifact_path: Path,
    password: str,
) -> dict[str, Any]:
    """Export a PostgreSQL source into a pinned custom-format archive."""
    if artifact_path.suffix.casefold() != ".dump":
        raise InvalidInputError("PostgreSQL export artifact must end in .dump")
    if artifact_path.exists() or artifact_metadata_path(artifact_path).exists():
        raise PreconditionError("export artifact or metadata already exists")
    check_tool_versions(runner, postgresql=True)
    runner.run(
        [
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--host",
            host,
            "--port",
            str(port),
            "--username",
            username,
            "--file",
            str(artifact_path),
            database,
        ],
        environment={"PGPASSWORD": password},
        timeout=1800,
    )
    artifact = artifact_document(artifact_path, "postgresql")
    write_metadata(
        artifact_path,
        family="postgresql",
        server=host,
        database=database,
        artifact=artifact,
    )
    return artifact


def target_fragment(target: dict[str, Any]) -> dict[str, Any]:
    """Build the database target fragment used by operation results."""
    database = target["database"]
    return {
        "kind": "database",
        "resourceId": database["resourceId"],
        "family": database["family"],
        "authentication": database["authentication"],
        "localAdministratorPrincipal": database["localAdministratorPrincipal"],
        "entraAdministratorPrincipal": database["entraAdministratorPrincipal"],
        "applicationPrincipal": database["applicationPrincipal"],
    }


def _azure_token(
    runner: CommandRunner, resource_arguments: list[str]
) -> str:
    result = runner.run(
        [
            "az",
            "account",
            "get-access-token",
            *resource_arguments,
            "--query",
            "accessToken",
            "--output",
            "tsv",
        ],
        environment=azure_environment(),
    )
    token = result.stdout.strip()
    if not token:
        raise PreconditionError("Azure CLI returned an empty access token")
    return token


def import_sql(
    runner: CommandRunner,
    *,
    artifact_path: Path,
    target: dict[str, Any],
) -> dict[str, Any]:
    """Import an immutable BACPAC into an empty Azure SQL database."""
    if target["stack"] != "dotnet-sqlserver":
        raise InvalidInputError("SQL import requires a dotnet-sqlserver target")
    artifact = require_artifact(artifact_path, "sqlserver")
    check_tool_versions(runner, sqlpackage=True, sqlcmd=True, azure=True)
    database = target["database"]
    token = _azure_token(runner, ["--resource", "https://database.windows.net/"])
    empty = runner.run(
        [
            "sqlcmd",
            "-S",
            database["server"],
            "-d",
            database["database"],
            "-G",
            "-h",
            "-1",
            "-W",
            "-Q",
            "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.tables;",
        ],
        environment={**azure_environment(), "SQLCMDACCESS_TOKEN": token},
    ).stdout.strip()
    if empty != "0":
        raise PreconditionError("Azure SQL target database is not empty")
    runner.run(
        [
            "SqlPackage",
            "/Action:Import",
            f"/SourceFile:{artifact_path}",
            (
                "/TargetConnectionString:Server="
                f"{database['server']};Database={database['database']};"
                "Authentication=Active Directory Default;Encrypt=True"
            ),
        ],
        environment=azure_environment(),
        timeout=1800,
    )
    principal = database["applicationPrincipal"]
    if not IDENTIFIER.fullmatch(principal["name"]):
        raise InvalidInputError("managed identity name is not a safe SQL identifier")
    principal_sql = (
        f"CREATE USER [{principal['name']}] FROM EXTERNAL PROVIDER "
        f"WITH OBJECT_ID='{principal['principalId']}'; "
        f"ALTER ROLE db_datareader ADD MEMBER [{principal['name']}]; "
        f"ALTER ROLE db_datawriter ADD MEMBER [{principal['name']}];"
    )
    runner.run(
        [
            "sqlcmd",
            "-S",
            database["server"],
            "-d",
            database["database"],
            "-G",
            "-b",
            "-Q",
            principal_sql,
        ],
        environment={**azure_environment(), "SQLCMDACCESS_TOKEN": token},
    )
    return artifact


def _postgres_base(database: dict[str, Any], database_name: str) -> list[str]:
    return [
        "--host",
        database["server"],
        "--port",
        "5432",
        "--username",
        database["localAdministratorPrincipal"]["name"],
        "--dbname",
        database_name,
    ]


def _validate_postgresql_principals(database: dict[str, Any]) -> None:
    for principal in (
        database["localAdministratorPrincipal"]["name"],
        database["applicationPrincipal"]["name"],
    ):
        if not IDENTIFIER.fullmatch(principal):
            raise InvalidInputError("PostgreSQL principal name is invalid")


def _bootstrap_password_principal(
    runner: CommandRunner,
    database: dict[str, Any],
    administrator_password: str,
    application_password: str,
) -> None:
    principal_name = database["applicationPrincipal"]["name"]
    quoted_principal = f'"{principal_name}"'
    script = (
        "\\getenv app_password MIGRATION_TARGET_APPLICATION_PASSWORD\n"
        "SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', "
        f"'{principal_name}', :'app_password') "
        "WHERE NOT EXISTS (SELECT 1 FROM pg_roles "
        f"WHERE rolname = '{principal_name}') \\gexec\n"
        f"GRANT CONNECT ON DATABASE {database['database']} "
        f"TO {quoted_principal};\n"
        f"GRANT USAGE ON SCHEMA public TO {quoted_principal};\n"
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
        f"TO {quoted_principal};\n"
        f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public "
        f"TO {quoted_principal};\n"
    )
    runner.run(
        ["psql", *_postgres_base(database, database["database"]), "-v", "ON_ERROR_STOP=1"],
        environment={
            "PGPASSWORD": administrator_password,
            "MIGRATION_TARGET_APPLICATION_PASSWORD": application_password,
        },
        input_text=script,
    )


def _bootstrap_managed_principal(
    runner: CommandRunner,
    target: dict[str, Any],
) -> None:
    database = target["database"]
    signed_in = runner.run(
        ["az", "ad", "signed-in-user", "show", "--output", "json"],
        environment=azure_environment(),
    )
    try:
        user = json.loads(signed_in.stdout)
    except json.JSONDecodeError as error:
        raise PreconditionError("signed-in Azure CLI principal output is invalid") from error
    expected = database["entraAdministratorPrincipal"]
    actual_name = user.get("userPrincipalName") or user.get("mail")
    if user.get("id") != expected["objectId"] or actual_name != expected["name"]:
        raise PreconditionError(
            "signed-in Azure CLI user differs from the PostgreSQL Entra administrator"
        )
    token = _azure_token(runner, ["--resource-type", "oss-rdbms"])
    principal = database["applicationPrincipal"]
    if principal["principalId"] != target["workloadIdentity"]["principalId"]:
        raise InvalidInputError(
            "PostgreSQL application principal differs from the workload identity"
        )
    create_script = (
        "SELECT pg_catalog.pgaadauth_create_principal_with_oid("
        ":'principal_name', :'principal_id', 'service', false, false);\n"
    )
    entra_arguments = [
        "--host",
        database["server"],
        "--port",
        "5432",
        "--username",
        expected["name"],
    ]
    runner.run(
        [
            "psql",
            *entra_arguments,
            "--dbname",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            "-v",
            f"principal_name={principal['name']}",
            "-v",
            f"principal_id={principal['principalId']}",
        ],
        environment={"PGPASSWORD": token},
        input_text=create_script,
    )
    quoted_principal = f'"{principal["name"]}"'
    grant_script = (
        f"GRANT CONNECT ON DATABASE {database['database']} TO "
        f"{quoted_principal};\n"
        f"GRANT USAGE ON SCHEMA public TO {quoted_principal};\n"
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "
        f"{quoted_principal};\n"
        f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO "
        f"{quoted_principal};\n"
    )
    runner.run(
        [
            "psql",
            *entra_arguments,
            "--dbname",
            database["database"],
            "-v",
            "ON_ERROR_STOP=1",
        ],
        environment={"PGPASSWORD": token},
        input_text=grant_script,
    )


def import_postgresql(
    runner: CommandRunner,
    *,
    artifact_path: Path,
    target: dict[str, Any],
    administrator_password: str,
    application_password: str | None,
) -> dict[str, Any]:
    """Restore PostgreSQL and create the mode-specific least-privilege principal."""
    if target["stack"] != "java-postgresql":
        raise InvalidInputError("PostgreSQL import requires a java-postgresql target")
    artifact = require_artifact(artifact_path, "postgresql")
    check_tool_versions(runner, postgresql=True, azure=True)
    database = target["database"]
    _validate_postgresql_principals(database)
    count = runner.run(
        [
            "psql",
            *_postgres_base(database, database["database"]),
            "-At",
            "-c",
            "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='public';",
        ],
        environment={"PGPASSWORD": administrator_password},
    ).stdout.strip()
    if count != "0":
        raise PreconditionError("PostgreSQL target database is not empty")
    runner.run(
        [
            "pg_restore",
            "--no-owner",
            "--no-privileges",
            *_postgres_base(database, database["database"]),
            str(artifact_path),
        ],
        environment={"PGPASSWORD": administrator_password},
        timeout=1800,
    )
    if database["authentication"] == "password-secret":
        if application_password is None:
            raise InvalidInputError("application password is required")
        _bootstrap_password_principal(
            runner,
            database,
            administrator_password,
            application_password,
        )
    else:
        if application_password is not None:
            raise InvalidInputError(
                "application password is forbidden for managed identity"
            )
        _bootstrap_managed_principal(runner, target)
    return artifact


def _verification_result(
    runner: CommandRunner,
    target: dict[str, Any],
    application_password: str | None,
) -> dict[str, Any]:
    database = target["database"]
    if target["stack"] == "dotnet-sqlserver":
        check_tool_versions(runner, sqlcmd=True, azure=True)
        token = _azure_token(runner, ["--resource", "https://database.windows.net/"])
        query = (
            "SET NOCOUNT ON; "
            "SELECT (SELECT COUNT(*) FROM dbo.Figures),"
            "(SELECT COUNT(*) FROM dbo.Categories),"
            "(SELECT STRING_AGG(MigrationId + '|' + ProductVersion, ',') "
            "FROM dbo.__EFMigrationsHistory),"
            "CASE WHEN OBJECT_ID('dbo.Figures') IS NOT NULL AND "
            "OBJECT_ID('dbo.Categories') IS NOT NULL THEN 1 ELSE 0 END,"
            "CASE WHEN EXISTS(SELECT 1 FROM sys.foreign_keys) THEN 1 ELSE 0 END,"
            "CASE WHEN EXISTS(SELECT 1 FROM sys.indexes WHERE is_primary_key=0 "
            "AND name IS NOT NULL) THEN 1 ELSE 0 END;"
        )
        output = runner.run(
            [
                "sqlcmd",
                "-S",
                database["server"],
                "-d",
                database["database"],
                "-G",
                "-h",
                "-1",
                "-W",
                "-s",
                "\t",
                "-Q",
                query,
            ],
            environment={**azure_environment(), "SQLCMDACCESS_TOKEN": token},
        ).stdout.strip()
    else:
        check_tool_versions(runner, postgresql=True, azure=True)
        query = (
            "SELECT (SELECT count(*) FROM figures),"
            "(SELECT count(*) FROM categories),"
            "(SELECT string_agg(installed_rank || '|' || version || '|' || "
            "description || '|' || type || '|' || script || '|' || success, ',' "
            "ORDER BY installed_rank) FROM flyway_schema_history),"
            "(to_regclass('public.figures') IS NOT NULL AND "
            "to_regclass('public.categories') IS NOT NULL)::int,"
            "EXISTS(SELECT 1 FROM pg_constraint WHERE contype IN ('p','f','u'))::int,"
            "EXISTS(SELECT 1 FROM pg_indexes WHERE schemaname='public')::int;"
        )
        if database["authentication"] == "password-secret":
            if application_password is None:
                raise InvalidInputError("application password is required for verification")
            environment = {"PGPASSWORD": application_password}
            username = database["applicationPrincipal"]["name"]
        else:
            if application_password is not None:
                raise InvalidInputError(
                    "application password is forbidden for managed identity verification"
                )
            username = database["entraAdministratorPrincipal"]["name"]
            environment = {
                "PGPASSWORD": _azure_token(runner, ["--resource-type", "oss-rdbms"])
            }
        output = runner.run(
            [
                "psql",
                "--host",
                database["server"],
                "--port",
                "5432",
                "--username",
                username,
                "--dbname",
                database["database"],
                "-At",
                "-F",
                "\t",
                "-c",
                query,
            ],
            environment=environment,
        ).stdout.strip()
    fields = output.split("\t")
    if len(fields) != 6:
        raise VerificationError("database verification output is malformed")
    figures, categories, history, schema, constraints, indexes = fields
    expected_history = (
        ["202608180001_ContractBaseline|8.0.22"]
        if target["stack"] == "dotnet-sqlserver"
        else ["1|1|contract baseline|SQL|V1__contract_baseline.sql|true"]
    )
    actual_history = [item for item in history.split(",") if item]
    if target["stack"] == "java-postgresql":
        actual_history = [
            item.removeprefix("1|") for item in actual_history
        ]
        expected_history = ["1|contract baseline|SQL|V1__contract_baseline.sql|true"]
    if (
        int(figures) != 198
        or int(categories) != 20
        or actual_history != expected_history
        or (schema, constraints, indexes) != ("1", "1", "1")
    ):
        raise VerificationError("database differs from the frozen migration contract")
    return {
        "migrationHistory": expected_history,
        "schemaVerified": True,
        "constraintsVerified": True,
        "indexesVerified": True,
        "seedManifestVersion": "1.0.0",
        "verifiedRowCounts": {"figures": 198, "categories": 20},
    }


def build_migration_report(
    runner: CommandRunner,
    *,
    stack: str,
    source_commit: str,
    artifact_path: Path,
    target: dict[str, Any],
    image_verification: dict[str, Any],
    application_password: str | None,
) -> dict[str, Any]:
    """Verify a migrated target and build the exact migration report."""
    family = "sqlserver" if stack == "dotnet-sqlserver" else "postgresql"
    if target["stack"] != stack:
        raise InvalidInputError("stack differs from target output")
    artifact = require_artifact(artifact_path, family)
    sidecar = load_json(artifact_metadata_path(artifact_path))
    started = timestamp()
    database_verification = _verification_result(
        runner, target, application_password
    )
    database = target["database"]
    report = {
        "schemaVersion": "1.0.0",
        "runId": __import__("uuid").uuid4().hex,
        "status": "passed",
        "startedAt": started,
        "completedAt": timestamp(),
        "sourceCommit": source_commit,
        "stack": stack,
        "sourceDatabase": {
            "family": family,
            "server": sidecar["server"],
            "database": sidecar["database"],
            "engineVersion": "2022" if family == "sqlserver" else POSTGRESQL_VERSION,
        },
        "targetDatabase": database,
        "databaseArtifact": artifact,
        "databaseVerification": database_verification,
        "images": {
            **target["images"],
            "verification": image_verification,
        },
    }
    # UUID hex is accepted by Python but the schema requires the conventional form.
    from uuid import UUID

    report["runId"] = str(UUID(report["runId"]))
    validate_document(report, "migration-report.schema.json")
    return report
