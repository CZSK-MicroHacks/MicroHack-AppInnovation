"""Verify catalog persistence through database-native command-line clients."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Literal

from catalog_acceptance.manifest import load_json, repository_root
from catalog_acceptance.models.contracts import CatalogItem
from catalog_acceptance.normalization import category_slug

DatabaseKind = Literal["sqlserver", "postgresql"]
DatabaseTarget = Literal["local", "managed"]


@dataclass(frozen=True)
class DatabaseState:
    """Represent complete persisted catalog state relevant to the contract."""

    figures: tuple[tuple[str, ...], ...]
    categories: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class DatabaseVerification:
    """Summarize a successful full database verification."""

    figure_count: int
    category_count: int
    tls_detail: str


def _expected_rows(items: list[CatalogItem]) -> tuple[tuple[str, ...], ...]:
    """Return every canonical field persisted for each figure."""
    return tuple(
        sorted(
            (
                str(item.product_id),
                item.name,
                item.description,
                item.category,
                category_slug(item.category),
                item.filename,
                "valid",
            )
            for item in items
        )
    )


def _expected_categories(categories: list[str]) -> tuple[tuple[str, str], ...]:
    """Return canonical category display-name and slug pairs."""
    return tuple(sorted((name, category_slug(name)) for name in categories))


def _run_client(
    command: list[str],
    environment: dict[str, str],
    client_name: str,
) -> str:
    """Run a database client and return stdout without exposing credentials.

    Raises:
        RuntimeError: If the client is missing, fails, or times out.
    """
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
            env=environment,
        )
    except FileNotFoundError as error:
        raise RuntimeError(f"{client_name} is required for database verification") from error
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"{client_name} database query failed") from error
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"{client_name} database query timed out") from error
    return result.stdout


def _parse_rows(output: str, width: int) -> tuple[tuple[str, ...], ...]:
    """Parse sorted tab-separated database rows with an exact width."""
    rows: list[tuple[str, ...]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        columns = tuple(column.strip() for column in line.split("\t"))
        if len(columns) != width:
            raise ValueError("database client returned an unexpected row shape")
        rows.append(columns)
    return tuple(rows)


def _sqlserver_connection(
    host: str,
    port: int,
    database: str,
    username: str,
    require_encryption: bool,
    trust_certificate: bool,
) -> list[str]:
    """Build common sqlcmd connection arguments."""
    endpoint = host if "\\" in host else f"tcp:{host},{port}"
    connection = [
        "sqlcmd",
        "-S",
        endpoint,
        "-d",
        database,
        "-U",
        username,
        "-h",
        "-1",
        "-W",
    ]
    if require_encryption:
        connection.append("-N")
    if trust_certificate:
        connection.append("-C")
    return connection


def _postgresql_connection(
    host: str,
    port: int,
    database: str,
    username: str,
) -> list[str]:
    """Build common psql connection arguments."""
    return [
        "psql",
        "--host",
        host,
        "--port",
        str(port),
        "--dbname",
        database,
        "--username",
        username,
        "--no-align",
        "--tuples-only",
        "--field-separator",
        "\t",
    ]


def _database_command(
    kind: DatabaseKind,
    connection: list[str],
    query: str,
    environment: dict[str, str],
) -> str:
    """Execute one query with the selected native client."""
    if kind == "sqlserver":
        return _run_client(
            [*connection, "-s", "\t", "-Q", f"SET NOCOUNT ON; {query}"],
            environment,
            "sqlcmd",
        )
    return _run_client(
        [*connection, "--command", query],
        environment,
        "psql",
    )


def _connection(
    kind: DatabaseKind,
    host: str,
    port: int | None,
    database: str,
    username: str,
    password: str,
    ssl_mode: str,
    trust_certificate: bool,
    target: DatabaseTarget,
) -> tuple[list[str], dict[str, str]]:
    """Build client arguments and its secret-only environment."""
    environment = os.environ.copy()
    if kind == "sqlserver":
        environment["SQLCMDPASSWORD"] = password
        return (
            _sqlserver_connection(
                host,
                port or 1433,
                database,
                username,
                target == "managed" or ssl_mode == "require",
                trust_certificate,
            ),
            environment,
        )
    environment["PGPASSWORD"] = password
    environment["PGSSLMODE"] = "require" if target == "managed" else ssl_mode
    return (
        _postgresql_connection(
            host,
            port or 5432,
            database,
            username,
        ),
        environment,
    )


def fetch_database_state(
    kind: DatabaseKind,
    host: str,
    port: int | None,
    database: str,
    username: str,
    password: str,
    ssl_mode: str,
    trust_certificate: bool,
    target: DatabaseTarget,
) -> DatabaseState:
    """Read complete figure and category state for comparison and reset checks."""
    connection, environment = _connection(
        kind,
        host,
        port,
        database,
        username,
        password,
        ssl_mode,
        trust_certificate,
        target,
    )
    if kind == "sqlserver":
        figures_query = (
            "SELECT LOWER(CONVERT(varchar(36), f.Id)), f.Name, f.Description, "
            "c.Name, c.Slug, f.ImageFile, "
            "CASE WHEN f.CreatedUtc IS NOT NULL AND f.LastUpdatedUtc IS NOT NULL "
            "AND f.CreatedUtc <= f.LastUpdatedUtc THEN 'valid' ELSE 'invalid' END "
            "FROM dbo.Figures AS f "
            "INNER JOIN dbo.Categories AS c ON c.Id = f.CategoryId "
            "ORDER BY f.Id;"
        )
        categories_query = (
            "SELECT Name, Slug FROM dbo.Categories ORDER BY Name, Slug;"
        )
    else:
        figures_query = (
            "SELECT f.id::text, f.name, f.description, c.name, c.slug, f.image_file, "
            "CASE WHEN f.created_at IS NOT NULL AND f.updated_at IS NOT NULL "
            "AND f.created_at <= f.updated_at THEN 'valid' ELSE 'invalid' END "
            "FROM public.figures AS f "
            "INNER JOIN public.categories AS c ON c.id = f.category_id "
            "ORDER BY f.id;"
        )
        categories_query = (
            "SELECT name, slug FROM public.categories ORDER BY name, slug;"
        )
    figures = tuple(
        sorted(
            _parse_rows(
                _database_command(kind, connection, figures_query, environment),
                7,
            )
        )
    )
    categories = tuple(
        sorted(
            _parse_rows(
                _database_command(kind, connection, categories_query, environment),
                2,
            )
        )
    )
    return DatabaseState(figures=figures, categories=categories)


def _schema_rows(
    kind: DatabaseKind,
    connection: list[str],
    environment: dict[str, str],
) -> tuple[tuple[str, ...], ...]:
    """Read normalized application-table column metadata."""
    if kind == "sqlserver":
        query = (
            "SELECT TABLE_NAME, COLUMN_NAME, LOWER(DATA_TYPE), "
            "COALESCE(CONVERT(varchar(12), CHARACTER_MAXIMUM_LENGTH), ''), "
            "CASE IS_NULLABLE WHEN 'YES' THEN 'true' ELSE 'false' END "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME IN ('Categories', 'Figures') "
            "ORDER BY TABLE_NAME, ORDINAL_POSITION;"
        )
    else:
        query = (
            "SELECT table_name, column_name, lower(data_type), "
            "COALESCE(character_maximum_length::text, ''), "
            "CASE is_nullable WHEN 'YES' THEN 'true' ELSE 'false' END "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name IN ('categories', 'figures') "
            "ORDER BY table_name, ordinal_position;"
        )
    return _parse_rows(_database_command(kind, connection, query, environment), 5)


def _constraint_rows(
    kind: DatabaseKind,
    connection: list[str],
    environment: dict[str, str],
) -> tuple[str, ...]:
    """Read constraint names, columns, references, actions, and expressions."""
    if kind == "sqlserver":
        query = (
            "SELECT t.name, k.name, "
            "CASE k.type WHEN 'PK' THEN 'PRIMARY KEY' ELSE 'UNIQUE' END, "
            "STRING_AGG(c.name, ',') WITHIN GROUP (ORDER BY ic.key_ordinal), "
            "'-', '-', '-', '-' "
            "FROM sys.key_constraints AS k "
            "INNER JOIN sys.tables AS t ON t.object_id = k.parent_object_id "
            "INNER JOIN sys.index_columns AS ic ON ic.object_id = t.object_id "
            "AND ic.index_id = k.unique_index_id AND ic.key_ordinal > 0 "
            "INNER JOIN sys.columns AS c ON c.object_id = t.object_id "
            "AND c.column_id = ic.column_id "
            "WHERE SCHEMA_NAME(t.schema_id) = 'dbo' "
            "AND t.name IN ('Categories', 'Figures') "
            "GROUP BY t.name, k.name, k.type "
            "UNION ALL "
            "SELECT pt.name, fk.name, 'FOREIGN KEY', "
            "STRING_AGG(pc.name, ',') "
            "WITHIN GROUP (ORDER BY fkc.constraint_column_id), "
            "SCHEMA_NAME(rt.schema_id) + '.' + rt.name + '(' + "
            "STRING_AGG(rc.name, ',') "
            "WITHIN GROUP (ORDER BY fkc.constraint_column_id) + ')', "
            "fk.update_referential_action_desc, fk.delete_referential_action_desc, '-' "
            "FROM sys.foreign_keys AS fk "
            "INNER JOIN sys.tables AS pt ON pt.object_id = fk.parent_object_id "
            "INNER JOIN sys.tables AS rt ON rt.object_id = fk.referenced_object_id "
            "INNER JOIN sys.foreign_key_columns AS fkc "
            "ON fkc.constraint_object_id = fk.object_id "
            "INNER JOIN sys.columns AS pc ON pc.object_id = pt.object_id "
            "AND pc.column_id = fkc.parent_column_id "
            "INNER JOIN sys.columns AS rc ON rc.object_id = rt.object_id "
            "AND rc.column_id = fkc.referenced_column_id "
            "WHERE SCHEMA_NAME(pt.schema_id) = 'dbo' "
            "AND pt.name IN ('Categories', 'Figures') "
            "GROUP BY pt.name, fk.name, rt.schema_id, rt.name, "
            "fk.update_referential_action_desc, fk.delete_referential_action_desc "
            "UNION ALL "
            "SELECT t.name, cc.name, 'CHECK', '-', '-', '-', '-', "
            "REPLACE(REPLACE(REPLACE(cc.definition, ' ', ''), CHAR(13), ''), CHAR(10), '') "
            "FROM sys.check_constraints AS cc "
            "INNER JOIN sys.tables AS t ON t.object_id = cc.parent_object_id "
            "WHERE SCHEMA_NAME(t.schema_id) = 'dbo' "
            "AND t.name IN ('Categories', 'Figures') "
            "UNION ALL "
            "SELECT 'Categories', 'IDENTITY:Categories.Id', 'IDENTITY', "
            "'Id', '-', '-', '-', '-' "
            "WHERE COLUMNPROPERTY(OBJECT_ID('dbo.Categories'), 'Id', 'IsIdentity') = 1 "
            "ORDER BY 1, 2;"
        )
    else:
        query = (
            "SELECT tc.table_name, tc.constraint_name, tc.constraint_type, "
            "COALESCE((SELECT string_agg(kcu.column_name, ',' "
            "ORDER BY kcu.ordinal_position) "
            "FROM information_schema.key_column_usage AS kcu "
            "WHERE kcu.constraint_schema = tc.constraint_schema "
            "AND kcu.constraint_name = tc.constraint_name), '-'), "
            "CASE WHEN tc.constraint_type = 'FOREIGN KEY' "
            "THEN ccu.table_schema || '.' || ccu.table_name || '(' || ccu.column_name || ')' "
            "ELSE '-' END, "
            "COALESCE(rc.update_rule, '-'), COALESCE(rc.delete_rule, '-'), "
            "CASE WHEN tc.constraint_type = 'CHECK' "
            "THEN regexp_replace(cc.check_clause, '\\s+', '', 'g') ELSE '-' END "
            "FROM information_schema.table_constraints AS tc "
            "LEFT JOIN information_schema.referential_constraints AS rc "
            "ON rc.constraint_schema = tc.constraint_schema "
            "AND rc.constraint_name = tc.constraint_name "
            "LEFT JOIN information_schema.constraint_column_usage AS ccu "
            "ON ccu.constraint_schema = tc.constraint_schema "
            "AND ccu.constraint_name = tc.constraint_name "
            "AND tc.constraint_type = 'FOREIGN KEY' "
            "LEFT JOIN information_schema.check_constraints AS cc "
            "ON cc.constraint_schema = tc.constraint_schema "
            "AND cc.constraint_name = tc.constraint_name "
            "WHERE tc.table_schema = 'public' "
            "AND tc.table_name IN ('categories', 'figures') "
            "AND (tc.constraint_type <> 'CHECK' OR EXISTS ("
            "SELECT 1 FROM pg_catalog.pg_constraint AS pgc "
            "INNER JOIN pg_catalog.pg_class AS pgcl "
            "ON pgcl.oid = pgc.conrelid "
            "INNER JOIN pg_catalog.pg_namespace AS pgn "
            "ON pgn.oid = pgc.connamespace "
            "WHERE pgn.nspname = tc.constraint_schema "
            "AND pgcl.relname = tc.table_name "
            "AND pgc.conname = tc.constraint_name "
            "AND pgc.contype = 'c')) "
            "UNION ALL "
            "SELECT 'categories', 'IDENTITY:categories.id', 'IDENTITY', "
            "'id', '-', '-', '-', '-' "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'categories' "
            "AND column_name = 'id' AND is_identity = 'YES' "
            "ORDER BY 1, 2;"
        )
    return tuple(
        "|".join(row)
        for row in _parse_rows(
            _database_command(kind, connection, query, environment),
            8,
        )
    )


def _index_rows(
    kind: DatabaseKind,
    connection: list[str],
    environment: dict[str, str],
) -> tuple[str, ...]:
    """Read index uniqueness, ordered keys, direction, and filtering."""
    if kind == "sqlserver":
        query = (
            "SELECT OBJECT_NAME(i.object_id), i.name, "
            "CASE i.is_unique WHEN 1 THEN 'true' ELSE 'false' END, "
            "STRING_AGG(c.name + ':' + "
            "CASE ic.is_descending_key WHEN 1 THEN 'desc' ELSE 'asc' END, ',') "
            "WITHIN GROUP (ORDER BY ic.key_ordinal), "
            "COALESCE(REPLACE(i.filter_definition, ' ', ''), '-') "
            "FROM sys.indexes AS i "
            "INNER JOIN sys.index_columns AS ic ON ic.object_id = i.object_id "
            "AND ic.index_id = i.index_id AND ic.key_ordinal > 0 "
            "INNER JOIN sys.columns AS c ON c.object_id = i.object_id "
            "AND c.column_id = ic.column_id "
            "WHERE OBJECT_SCHEMA_NAME(i.object_id) = 'dbo' "
            "AND OBJECT_NAME(i.object_id) IN ('Categories', 'Figures') "
            "AND i.name IS NOT NULL AND i.is_hypothetical = 0 "
            "GROUP BY i.object_id, i.name, i.is_unique, i.filter_definition "
            "ORDER BY 1, 2;"
        )
    else:
        query = (
            "SELECT t.relname, i.relname, "
            "CASE ix.indisunique WHEN true THEN 'true' ELSE 'false' END, "
            "string_agg(pg_get_indexdef(ix.indexrelid, key_position, true) || ':' || "
            "CASE WHEN (ix.indoption[key_position - 1] & 1) = 1 "
            "THEN 'desc' ELSE 'asc' END, ',' ORDER BY key_position), "
            "COALESCE(regexp_replace(pg_get_expr(ix.indpred, ix.indrelid), "
            "'\\s+', '', 'g'), '-') "
            "FROM pg_index AS ix "
            "INNER JOIN pg_class AS t ON t.oid = ix.indrelid "
            "INNER JOIN pg_namespace AS n ON n.oid = t.relnamespace "
            "INNER JOIN pg_class AS i ON i.oid = ix.indexrelid "
            "CROSS JOIN LATERAL generate_series(1, ix.indnkeyatts) AS key_position "
            "WHERE n.nspname = 'public' "
            "AND t.relname IN ('categories', 'figures') "
            "GROUP BY t.relname, i.relname, ix.indisunique, "
            "ix.indpred, ix.indrelid "
            "ORDER BY 1, 2;"
        )
    return tuple(
        "|".join(row)
        for row in _parse_rows(
            _database_command(kind, connection, query, environment),
            5,
        )
    )


def _migration_rows(
    kind: DatabaseKind,
    connection: list[str],
    environment: dict[str, str],
) -> tuple[str, ...]:
    """Read the complete ordered migration history."""
    query = (
        "SELECT MigrationId, ProductVersion FROM dbo.__EFMigrationsHistory "
        "ORDER BY MigrationId;"
        if kind == "sqlserver"
        else "SELECT version, description, type, script, "
        "CASE success WHEN true THEN 'true' ELSE 'false' END "
        "FROM public.flyway_schema_history ORDER BY installed_rank;"
    )
    width = 2 if kind == "sqlserver" else 5
    return tuple(
        "|".join(row)
        for row in _parse_rows(
            _database_command(kind, connection, query, environment),
            width,
        )
    )


def _tls_detail(
    kind: DatabaseKind,
    connection: list[str],
    environment: dict[str, str],
    target: DatabaseTarget,
) -> str:
    """Read server-reported TLS state and enforce it for managed targets."""
    query = (
        "SELECT encrypt_option, protocol_type FROM sys.dm_exec_connections "
        "WHERE session_id = @@SPID;"
        if kind == "sqlserver"
        else "SELECT ssl::text, COALESCE(version, '') FROM pg_stat_ssl "
        "WHERE pid = pg_backend_pid();"
    )
    rows = _parse_rows(_database_command(kind, connection, query, environment), 2)
    if len(rows) != 1:
        raise ValueError("database did not report one TLS connection state")
    enabled, protocol = rows[0]
    if target == "managed" and enabled.casefold() not in ("true", "t"):
        raise ValueError("managed database connection is not encrypted")
    if target == "managed" and not protocol:
        raise ValueError("managed database did not report a TLS protocol")
    if (
        kind == "postgresql"
        and target == "managed"
        and protocol not in ("TLSv1.2", "TLSv1.3")
    ):
        raise ValueError("managed PostgreSQL negotiated an unsupported TLS protocol")
    return f"encrypted={enabled}, protocol={protocol or 'not-reported'}"


def _expected_schema(contract: dict) -> tuple[tuple[str, ...], ...]:
    """Flatten contract column metadata into database query rows."""
    rows: list[tuple[str, ...]] = []
    for table_name, columns in contract["tables"].items():
        for column in columns:
            rows.append(
                (
                    table_name,
                    column["name"],
                    column["type"],
                    column["maximumLength"],
                    str(column["nullable"]).lower(),
                )
            )
    return tuple(sorted(rows))


def verify_database(
    kind: DatabaseKind,
    host: str,
    port: int | None,
    database: str,
    username: str,
    password: str,
    ssl_mode: str,
    trust_certificate: bool,
    target: DatabaseTarget,
    items: list[CatalogItem],
    expected_categories: list[str],
) -> DatabaseVerification:
    """Verify complete data, schema, constraints, indexes, migrations, and TLS."""
    state = fetch_database_state(
        kind,
        host,
        port,
        database,
        username,
        password,
        ssl_mode,
        trust_certificate,
        target,
    )
    if state.figures != _expected_rows(items):
        raise ValueError("database figure rows differ from the canonical corpus")
    if state.categories != _expected_categories(expected_categories):
        raise ValueError("database categories differ from the canonical corpus")

    connection, environment = _connection(
        kind,
        host,
        port,
        database,
        username,
        password,
        ssl_mode,
        trust_certificate,
        target,
    )
    contract = load_json(
        repository_root() / "workshop" / "contracts" / "database-contract.json"
    )[kind]
    if tuple(sorted(_schema_rows(kind, connection, environment))) != _expected_schema(
        contract
    ):
        raise ValueError("database application-table schema differs from contract")
    if tuple(sorted(_constraint_rows(kind, connection, environment))) != tuple(
        sorted(contract["constraints"])
    ):
        raise ValueError("database constraints differ from contract")
    if tuple(sorted(_index_rows(kind, connection, environment))) != tuple(
        sorted(contract["indexes"])
    ):
        raise ValueError("database indexes differ from contract")
    if _migration_rows(kind, connection, environment) != tuple(
        contract["migration"]["orderedHistory"]
    ):
        raise ValueError("database migration history differs from contract")
    tls_detail = _tls_detail(kind, connection, environment, target)
    return DatabaseVerification(
        figure_count=len(state.figures),
        category_count=len(state.categories),
        tls_detail=tls_detail,
    )


def delete_acceptance_fixture(
    kind: DatabaseKind,
    host: str,
    port: int | None,
    database: str,
    username: str,
    password: str,
    ssl_mode: str,
    trust_certificate: bool,
    target: DatabaseTarget,
    product_id: str,
    category_name: str,
) -> None:
    """Delete only the reserved acceptance fixture and its now-empty category."""
    if not product_id.startswith("10000000-0000-4000-8000-"):
        raise ValueError("refusing to delete a product outside the acceptance fixture range")
    escaped_category = category_name.replace("'", "''")
    connection, environment = _connection(
        kind,
        host,
        port,
        database,
        username,
        password,
        ssl_mode,
        trust_certificate,
        target,
    )
    if kind == "sqlserver":
        query = (
            "BEGIN TRANSACTION; "
            f"DELETE FROM dbo.Figures WHERE Id = '{product_id}'; "
            "DELETE FROM dbo.Categories "
            f"WHERE Name = N'{escaped_category}' "
            "AND NOT EXISTS (SELECT 1 FROM dbo.Figures WHERE CategoryId = Categories.Id); "
            "COMMIT TRANSACTION;"
        )
    else:
        query = (
            "BEGIN; "
            f"DELETE FROM public.figures WHERE id = '{product_id}'::uuid; "
            "DELETE FROM public.categories "
            f"WHERE name = '{escaped_category}' "
            "AND NOT EXISTS (SELECT 1 FROM public.figures "
            "WHERE category_id = categories.id); "
            "COMMIT;"
        )
    _database_command(kind, connection, query, environment)
