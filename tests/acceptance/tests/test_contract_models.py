"""Negative tests for evidence rules that JSON shape alone cannot express."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from catalog_acceptance import database
from catalog_acceptance.models.contracts import (
    AcceptanceReport,
    AcceptanceSettings,
    CatalogItem,
    FULL_ACCEPTANCE_CHECKS,
)
from catalog_acceptance.runner import AcceptanceRunner


def _full_report() -> dict:
    """Build the smallest valid full report for model tests."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "profile": "full",
        "status": "passed",
        "startedAt": now,
        "finishedAt": now,
        "baseUrl": "https://catalog.example.invalid",
        "databaseKind": "sqlserver",
        "databaseTarget": "managed",
        "corpus": {
            "figures": 198,
            "categories": 20,
            "images": 198,
        },
        "checks": [
            {
                "name": name,
                "status": "passed",
                "detail": "fixture",
                "required": True,
            }
            for name in FULL_ACCEPTANCE_CHECKS
        ],
    }


@pytest.mark.parametrize(
    "mutation",
    [
        lambda report: report["checks"].pop(),
        lambda report: report["checks"].append(report["checks"][-1].copy()),
        lambda report: report["checks"].reverse(),
        lambda report: report["checks"][0].update(status="skipped"),
        lambda report: report["checks"][0].update(required=False),
    ],
)
def test_full_report_rejects_incomplete_evidence(mutation) -> None:
    """Reject missing, duplicated, reordered, skipped, or optional full checks."""
    report = _full_report()
    mutation(report)
    with pytest.raises(ValidationError):
        AcceptanceReport.model_validate(report)


def test_full_settings_reject_image_sampling(tmp_path: Path) -> None:
    """Prevent a sampled image run from producing full evidence."""
    with pytest.raises(ValidationError, match="complete image"):
        AcceptanceSettings(
            profile="full",
            base_url="https://catalog.example.invalid",
            performance_api_key=SecretStr("not-a-default"),
            data_directory=tmp_path,
            database_kind="sqlserver",
            database_host="localhost",
            database_name="catalog",
            database_username="catalog",
            database_password=SecretStr("secret"),
            verify_all_images=False,
        )


def test_managed_settings_require_verified_tls(tmp_path: Path) -> None:
    """Require strict certificate validation for managed database evidence."""
    with pytest.raises(ValidationError, match="requires TLS"):
        AcceptanceSettings(
            profile="full",
            base_url="https://catalog.example.invalid",
            performance_api_key=SecretStr("not-a-default"),
            data_directory=tmp_path,
            database_kind="postgresql",
            database_host="example.postgres.database.azure.com",
            database_name="catalog",
            database_username="catalog",
            database_password=SecretStr("secret"),
            database_target="managed",
            database_ssl_mode="prefer",
        )


def test_managed_azure_sql_settings_require_only_an_access_token(
    tmp_path: Path,
) -> None:
    """Entra-only Azure SQL never accepts SQL authentication evidence."""
    settings = AcceptanceSettings(
        profile="full",
        base_url="https://catalog.example.invalid",
        performance_api_key=SecretStr("not-a-default"),
        data_directory=tmp_path,
        database_kind="sqlserver",
        database_host="example.database.windows.net",
        database_name="catalog",
        database_access_token=SecretStr("transient-token"),
        database_target="managed",
        database_ssl_mode="require",
    )
    assert settings.database_username is None
    assert settings.database_password is None
    assert AcceptanceRunner(settings)._database_credentials() == (
        None,
        None,
        "transient-token",
    )

    with pytest.raises(ValidationError, match="requires SQLCMDACCESS_TOKEN"):
        AcceptanceSettings(
            profile="full",
            base_url="https://catalog.example.invalid",
            performance_api_key=SecretStr("not-a-default"),
            data_directory=tmp_path,
            database_kind="sqlserver",
            database_host="example.database.windows.net",
            database_name="catalog",
            database_target="managed",
            database_ssl_mode="require",
        )

    with pytest.raises(ValidationError, match="forbids username and password"):
        AcceptanceSettings(
            profile="full",
            base_url="https://catalog.example.invalid",
            performance_api_key=SecretStr("not-a-default"),
            data_directory=tmp_path,
            database_kind="sqlserver",
            database_host="example.database.windows.net",
            database_name="catalog",
            database_username="catalog",
            database_password=SecretStr("password"),
            database_access_token=SecretStr("transient-token"),
            database_target="managed",
            database_ssl_mode="require",
        )


def test_managed_azure_sql_connection_uses_token_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """sqlcmd receives Entra mode and its token only through the child environment."""
    monkeypatch.setenv("GITHUB_TOKEN", "unrelated-host-secret")
    monkeypatch.setenv("SQLCMDPASSWORD", "unrelated-sql-secret")
    connection, environment = database._connection(
        "sqlserver",
        "example.database.windows.net",
        1433,
        "catalog",
        None,
        None,
        "require",
        False,
        "managed",
        "transient-token",
    )

    assert "-G" in connection
    assert "-U" not in connection
    assert "-N" in connection
    assert "-C" not in connection
    assert environment["SQLCMDACCESS_TOKEN"] == "transient-token"
    assert "SQLCMDPASSWORD" not in environment
    assert "GITHUB_TOKEN" not in environment


def test_catalog_item_rejects_empty_normalized_category() -> None:
    """Reject categories that cannot produce a stable storage/query slug."""
    with pytest.raises(ValidationError, match="non-empty slug"):
        CatalogItem.model_validate(
            {
                "productId": "10000000-0000-4000-8000-000000000099",
                "name": "Invalid Category Figure",
                "description": "A representative figure whose punctuation-only category cannot be queried safely.",
                "category": "--",
                "filename": "10000000-0000-4000-8000-000000000099.png",
                "imagePrompt": "Photorealistic construction-toy figure for category validation on a clean background.",
            }
        )


def test_database_state_uses_canonical_text_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normalize engine-specific row ordering before contract comparison."""
    outputs = iter(
        (
            "ffffffff-ffff-4fff-8fff-ffffffffffff\tZed\tDescription text long enough\tZed\tzed\tffffffff-ffff-4fff-8fff-ffffffffffff.png\tvalid\n"
            "10000000-0000-4000-8000-000000000001\tAlpha\tDescription text long enough\tAlpha\talpha\t10000000-0000-4000-8000-000000000001.png\tvalid\n",
            "Zed\tzed\nAlpha\talpha\n",
        )
    )
    monkeypatch.setattr(database, "_connection", lambda *args: ([], {}))
    monkeypatch.setattr(
        database,
        "_database_command",
        lambda *args: next(outputs),
    )

    state = database.fetch_database_state(
        "sqlserver",
        "localhost",
        1433,
        "catalog",
        "user",
        "password",
        "prefer",
        True,
        "local",
    )

    assert state.figures[0][0] == "10000000-0000-4000-8000-000000000001"
    assert state.categories == (("Alpha", "alpha"), ("Zed", "zed"))


def test_postgresql_constraint_query_excludes_not_null_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compare explicit checks without duplicating verified column nullability."""

    def capture_query(
        kind: str,
        connection: list[str],
        query: str,
        environment: dict[str, str],
    ) -> str:
        assert kind == "postgresql"
        assert "pgc.contype = 'c'" in query
        assert "pgc.conenforced AND pgc.convalidated" in query
        return (
            "figures\tck_figures_image_file\tCHECK\t-\t-\t-\t-\t"
            "((image_file)::text=((id)::text||'.png'::text))\n"
        )

    monkeypatch.setattr(database, "_database_command", capture_query)

    rows = database._constraint_rows("postgresql", [], {})

    assert rows == (
        "figures|ck_figures_image_file|CHECK|-|-|-|-|"
        "((image_file)::text=((id)::text||'.png'::text))",
    )


def test_sqlserver_constraint_query_requires_trusted_enforcement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exclude disabled or untrusted SQL Server constraints and indexes."""

    def capture_query(
        kind: str,
        connection: list[str],
        query: str,
        environment: dict[str, str],
    ) -> str:
        assert kind == "sqlserver"
        assert "ki.is_disabled = 0" in query
        assert "fk.is_disabled = 0 AND fk.is_not_trusted = 0" in query
        assert "cc.is_disabled = 0 AND cc.is_not_trusted = 0" in query
        return "Figures\tPK_Figures\tPRIMARY KEY\tId\t-\t-\t-\t-\n"

    monkeypatch.setattr(database, "_database_command", capture_query)

    assert database._constraint_rows("sqlserver", [], {}) == (
        "Figures|PK_Figures|PRIMARY KEY|Id|-|-|-|-",
    )


def test_complete_database_verification_rejects_unexpected_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A legacy table cannot pass by hiding outside the two column queries."""
    monkeypatch.setattr(
        database,
        "fetch_database_state_with_connection",
        lambda *args, **kwargs: database.DatabaseState((), ()),
    )
    monkeypatch.setattr(
        database,
        "_table_names",
        lambda *args, **kwargs: (
            "Categories",
            "Figures",
            "__EFMigrationsHistory",
            "LegacyData",
        ),
    )

    with pytest.raises(ValueError, match="table inventory"):
        database.verify_database_connection(
            kind="sqlserver",
            connection=[],
            environment={},
            target="local",
            items=[],
            expected_categories=[],
        )
