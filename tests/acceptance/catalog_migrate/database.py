"""Database export, import, principal bootstrap, and verification operations."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from catalog_acceptance.database import verify_database_connection
from catalog_acceptance.manifest import load_catalog
from catalog_migrate.contracts import (
    artifact_metadata_path,
    load_json,
    repository_root,
    validate_document,
)
from catalog_migrate.errors import (
    InvalidInputError,
    PreconditionError,
    ToolError,
    VerificationError,
)
from catalog_migrate.models import Artifact, DatabaseTool
from catalog_migrate.process import CommandRunner

SQLPACKAGE_VERSION = "170.4.83"
POSTGRESQL_VERSION = "18.6"
AZURE_CLI_VERSION = "2.80.0"
SQLCMD_VERSION = "1.7.0"
AZURE_CONFIG = str(Path.home() / ".azure-365")
IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,62}$")
LEGACY_SQL_PRINCIPAL = "catalog"
_PROTECT_SECRET_DIRECTORY_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$Directory = [IO.Path]::GetFullPath($env:MIGRATION_SECRET_DIRECTORY)
$Acl = New-Object Security.AccessControl.DirectorySecurity
$Acl.SetAccessRuleProtection($true, $false)
$Inheritance = [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
$Propagation = [Security.AccessControl.PropagationFlags]::None
$Allow = [Security.AccessControl.AccessControlType]::Allow
$Identities = @(
    [Security.Principal.WindowsIdentity]::GetCurrent().User,
    (New-Object Security.Principal.SecurityIdentifier('S-1-5-18')),
    (New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544'))
)
foreach ($Identity in $Identities) {
    $Rule = New-Object Security.AccessControl.FileSystemAccessRule(
        $Identity,
        [Security.AccessControl.FileSystemRights]::FullControl,
        $Inheritance,
        $Propagation,
        $Allow
    )
    $Acl.AddAccessRule($Rule)
}
[IO.Directory]::SetAccessControl($Directory, $Acl)
"""


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


def _protect_secret_directory(
    runner: CommandRunner,
    directory: Path,
    *,
    platform_name: str = os.name,
) -> None:
    """Restrict a temporary secret directory before writing secret material."""
    if platform_name != "nt":
        directory.chmod(0o700)
        return
    runner.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "-",
        ],
        environment={"MIGRATION_SECRET_DIRECTORY": str(directory)},
        input_text=_PROTECT_SECRET_DIRECTORY_SCRIPT,
    )


def _remove_secret_response_file(path: Path, directory: Path) -> None:
    """Zero and remove one bounded response file and its private directory."""
    try:
        if path.exists():
            length = path.stat().st_size
            with path.open("r+b", buffering=0) as stream:
                stream.write(b"\0" * length)
                os.fsync(stream.fileno())
            path.unlink()
        directory.rmdir()
    except OSError as error:
        raise ToolError("SqlPackage secret response file could not be removed") from error


@contextmanager
def _sqlpackage_password_response(
    runner: CommandRunner,
    password: str,
) -> Iterator[Path]:
    """Create and reliably remove a protected SqlPackage password response file."""
    if "\r" in password or "\n" in password:
        raise InvalidInputError("SQL Server source password must be one line")
    directory = Path(tempfile.mkdtemp(prefix="catalog-sqlpackage-"))
    path = directory / "source-password.rsp"
    try:
        _protect_secret_directory(runner, directory)
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(f"/SourcePassword:{password}\n")
        yield path
    finally:
        _remove_secret_response_file(path, directory)


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


def _database_executor(runner: CommandRunner):
    """Adapt the migration runner to the shared full database verifier."""

    def execute(
        command: list[str],
        environment: dict[str, str],
        client_name: str,
    ) -> str:
        del client_name
        return runner.run(command, environment=environment, timeout=60).stdout

    return execute


def _canonical_corpus() -> tuple[list[Any], list[str]]:
    """Load the exact figure and category corpus expected in both databases."""
    items = load_catalog(repository_root() / "data")
    return items, sorted({item.category for item in items})


def _verification_document(kind: str, verification: Any) -> dict[str, Any]:
    """Convert a successful complete verification to migration-report shape."""
    contract = load_json(
        repository_root() / "workshop" / "contracts" / "database-contract.json"
    )[kind]
    return {
        "migrationHistory": contract["migration"]["orderedHistory"],
        "schemaVerified": True,
        "constraintsVerified": True,
        "indexesVerified": True,
        "seedManifestVersion": "1.0.0",
        "verifiedRowCounts": {
            "figures": verification.figure_count,
            "categories": verification.category_count,
        },
    }


def _run_full_verification(
    runner: CommandRunner,
    *,
    kind: str,
    connection: list[str],
    environment: dict[str, str],
    target: str,
) -> dict[str, Any]:
    """Run the shared complete database contract and map failures consistently."""
    items, categories = _canonical_corpus()
    try:
        verification = verify_database_connection(
            kind=kind,
            connection=connection,
            environment=environment,
            target=target,
            items=items,
            expected_categories=categories,
            executor=_database_executor(runner),
        )
    except ValueError as error:
        raise VerificationError(str(error)) from error
    return _verification_document(kind, verification)


def verify_source_database(
    runner: CommandRunner,
    *,
    kind: str,
    server: str,
    port: int | None,
    database: str,
    username: str,
    password: str,
) -> dict[str, Any]:
    """Prove the source schema and every canonical row before export."""
    if kind == "sqlserver":
        connection = [
            "sqlcmd",
            "-S",
            server,
            "-d",
            database,
            "-U",
            username,
            "-h",
            "-1",
            "-W",
            "-C",
        ]
        environment = {"SQLCMDPASSWORD": password}
    else:
        connection = [
            "psql",
            "--host",
            server,
            "--port",
            str(port or 5432),
            "--dbname",
            database,
            "--username",
            username,
            "--no-align",
            "--tuples-only",
            "--field-separator",
            "\t",
        ]
        environment = {"PGPASSWORD": password, "PGSSLMODE": "prefer"}
    return _run_full_verification(
        runner,
        kind=kind,
        connection=connection,
        environment=environment,
        target="local",
    )


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
    check_tool_versions(runner, sqlpackage=True, sqlcmd=True)
    verify_source_database(
        runner,
        kind="sqlserver",
        server=server,
        port=None,
        database=database,
        username=username,
        password=password,
    )
    with _sqlpackage_password_response(runner, password) as response_file:
        runner.run(
            [
                "SqlPackage",
                "/Action:Export",
                f"/SourceServerName:{server}",
                f"/SourceDatabaseName:{database}",
                f"/SourceUser:{username}",
                "/SourceTrustServerCertificate:True",
                f"/TargetFile:{artifact_path}",
                f"@{response_file}",
            ],
            redactions=[password],
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
    verify_source_database(
        runner,
        kind="postgresql",
        server=host,
        port=port,
        database=database,
        username=username,
        password=password,
    )
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
        "SET XACT_ABORT ON; BEGIN TRANSACTION; "
        f"IF EXISTS (SELECT 1 FROM sys.database_principals "
        f"WHERE name = N'{LEGACY_SQL_PRINCIPAL}') BEGIN "
        f"IF IS_ROLEMEMBER(N'db_owner', N'{LEGACY_SQL_PRINCIPAL}') = 1 "
        f"ALTER ROLE [db_owner] DROP MEMBER [{LEGACY_SQL_PRINCIPAL}]; "
        f"DROP USER [{LEGACY_SQL_PRINCIPAL}]; END; "
        f"CREATE USER [{principal['name']}] FROM EXTERNAL PROVIDER "
        f"WITH OBJECT_ID='{principal['principalId']}'; "
        f"ALTER ROLE db_datareader ADD MEMBER [{principal['name']}]; "
        f"ALTER ROLE db_datawriter ADD MEMBER [{principal['name']}]; "
        "COMMIT TRANSACTION;"
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


def _postgresql_table_privilege_predicates(principal: str) -> str:
    """Require every table privilege independently for both application tables."""
    return " AND ".join(
        f"has_table_privilege('{principal}', 'public.{table}', '{privilege}')"
        for table in ("figures", "categories")
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE")
    )


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


def verify_target_database(
    runner: CommandRunner,
    target: dict[str, Any],
    application_password: str | None = None,
) -> dict[str, Any]:
    """Verify the target's exact schema, corpus, TLS, history, and app principal."""
    database = target["database"]
    if target["stack"] == "dotnet-sqlserver":
        check_tool_versions(runner, sqlcmd=True, azure=True)
        token = _azure_token(runner, ["--resource", "https://database.windows.net/"])
        connection = [
            "sqlcmd",
            "-S",
            database["server"],
            "-d",
            database["database"],
            "-G",
            "-h",
            "-1",
            "-W",
            "-N",
        ]
        environment = {**azure_environment(), "SQLCMDACCESS_TOKEN": token}
        verification = _run_full_verification(
            runner,
            kind="sqlserver",
            connection=connection,
            environment=environment,
            target="managed",
        )
        principal = database["applicationPrincipal"]["name"]
        if not IDENTIFIER.fullmatch(principal):
            raise InvalidInputError("managed identity name is not a safe SQL identifier")
        roles = runner.run(
            [
                *connection,
                "-s",
                "\t",
                "-Q",
                (
                    "SET NOCOUNT ON; "
                    "SELECT STRING_AGG(r.name, ',') WITHIN GROUP (ORDER BY r.name) "
                    "FROM sys.database_role_members AS rm "
                    "INNER JOIN sys.database_principals AS r "
                    "ON r.principal_id = rm.role_principal_id "
                    "INNER JOIN sys.database_principals AS m "
                    "ON m.principal_id = rm.member_principal_id "
                    f"WHERE m.name = N'{principal}';"
                ),
            ],
            environment=environment,
        ).stdout.strip()
        if roles != "db_datareader,db_datawriter":
            raise VerificationError(
                "Azure SQL application principal roles differ from the contract"
            )
        legacy_principals = runner.run(
            [
                *connection,
                "-Q",
                (
                    "SET NOCOUNT ON; SELECT COUNT(*) "
                    "FROM sys.database_principals "
                    f"WHERE name = N'{LEGACY_SQL_PRINCIPAL}';"
                ),
            ],
            environment=environment,
        ).stdout.strip()
        if legacy_principals != "0":
            raise VerificationError(
                "Azure SQL retains the privileged legacy catalog principal"
            )
        return verification

    check_tool_versions(runner, postgresql=True, azure=True)
    if database["authentication"] == "password-secret":
        if application_password is None:
            raise InvalidInputError("application password is required for verification")
        environment = {
            "PGPASSWORD": application_password,
            "PGSSLMODE": "require",
        }
        username = database["applicationPrincipal"]["name"]
    else:
        if application_password is not None:
            raise InvalidInputError(
                "application password is forbidden for managed identity verification"
            )
        username = database["entraAdministratorPrincipal"]["name"]
        environment = {
            "PGPASSWORD": _azure_token(runner, ["--resource-type", "oss-rdbms"]),
            "PGSSLMODE": "require",
        }
    connection = [
        "psql",
        "--host",
        database["server"],
        "--port",
        "5432",
        "--username",
        username,
        "--dbname",
        database["database"],
        "--no-align",
        "--tuples-only",
        "--field-separator",
        "\t",
    ]
    verification = _run_full_verification(
        runner,
        kind="postgresql",
        connection=connection,
        environment=environment,
        target="managed",
    )
    principal = database["applicationPrincipal"]["name"]
    if not IDENTIFIER.fullmatch(principal):
        raise InvalidInputError("PostgreSQL principal name is invalid")
    escaped_principal = principal.replace("'", "''")
    table_privileges = _postgresql_table_privilege_predicates(escaped_principal)
    grants = runner.run(
        [
            *connection,
            "--command",
            (
                "SELECT (EXISTS(SELECT 1 FROM pg_roles WHERE rolname = "
                f"'{escaped_principal}' AND rolcanlogin AND NOT rolsuper "
                "AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication "
                "AND NOT rolbypassrls) "
                f"AND has_database_privilege('{escaped_principal}', current_database(), 'CONNECT') "
                f"AND has_schema_privilege('{escaped_principal}', 'public', 'USAGE') "
                f"AND {table_privileges})::int;"
            ),
        ],
        environment=environment,
    ).stdout.strip()
    if grants != "1":
        raise VerificationError(
            "PostgreSQL application principal grants differ from the contract"
        )
    return verification


def build_migration_report(
    runner: CommandRunner,
    *,
    stack: str,
    source_commit: str,
    artifact_path: Path,
    target: dict[str, Any],
    image_verification: dict[str, Any],
    application_password: str | None,
    migration_execution: dict[str, Any],
) -> dict[str, Any]:
    """Verify a migrated target and build the exact migration report."""
    family = "sqlserver" if stack == "dotnet-sqlserver" else "postgresql"
    if target["stack"] != stack:
        raise InvalidInputError("stack differs from target output")
    if target["sourceCommit"] != source_commit:
        raise InvalidInputError("source commit differs from target output")
    artifact = require_artifact(artifact_path, family)
    sidecar = load_json(artifact_metadata_path(artifact_path))
    started = timestamp()
    database_verification = verify_target_database(
        runner, target, application_password
    )
    database = target["database"]
    report = {
        "schemaVersion": "1.1.0",
        "runId": __import__("uuid").uuid4().hex,
        "status": "passed",
        "startedAt": started,
        "completedAt": timestamp(),
        "sourceCommit": target["sourceCommit"],
        "stack": stack,
        "migrationExecution": migration_execution,
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
