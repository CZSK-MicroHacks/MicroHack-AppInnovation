"""Optional live test that runs the complete path-neutral acceptance contract."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import SecretStr

from catalog_acceptance.manifest import load_json
from catalog_acceptance.models.contracts import AcceptanceSettings
from catalog_acceptance.runner import AcceptanceRunner


@pytest.mark.live
def test_live_application_contract(repo_root: Path) -> None:
    """Run the full contract when application URL and API key are configured."""
    base_url = os.getenv("CATALOG_BASE_URL")
    api_key = os.getenv("PERFTEST_API_KEY")
    if not base_url or not api_key:
        pytest.skip("CATALOG_BASE_URL and PERFTEST_API_KEY are required")

    database_kind = os.getenv("CATALOG_DATABASE_KIND")
    database_password = os.getenv("CATALOG_DATABASE_PASSWORD")
    settings = AcceptanceSettings(
        profile=os.getenv("CATALOG_ACCEPTANCE_PROFILE", "smoke"),
        base_url=base_url,
        performance_api_key=SecretStr(api_key),
        data_directory=repo_root / "data",
        database_kind=database_kind,
        database_host=os.getenv("CATALOG_DATABASE_HOST"),
        database_port=(
            int(os.environ["CATALOG_DATABASE_PORT"])
            if os.getenv("CATALOG_DATABASE_PORT")
            else None
        ),
        database_name=os.getenv("CATALOG_DATABASE_NAME"),
        database_username=os.getenv("CATALOG_DATABASE_USERNAME"),
        database_password=SecretStr(database_password) if database_password else None,
        database_access_token=(
            SecretStr(os.environ["SQLCMDACCESS_TOKEN"])
            if os.getenv("SQLCMDACCESS_TOKEN")
            else None
        ),
        database_ssl_mode=os.getenv("CATALOG_DATABASE_SSL_MODE", "prefer"),
        database_trust_certificate=os.getenv(
            "CATALOG_DATABASE_TRUST_CERTIFICATE", ""
        ).lower()
        in ("1", "true", "yes"),
        database_target=os.getenv("CATALOG_DATABASE_TARGET", "local"),
        source_commit=os.getenv("CATALOG_SOURCE_COMMIT"),
        image_digest=os.getenv("CATALOG_IMAGE_DIGEST"),
        revision_name=os.getenv("CATALOG_REVISION_NAME"),
        expected_work_factor=int(os.getenv("PERFTEST_WORK_FACTOR", "10")),
    )
    report = AcceptanceRunner(settings).run()
    rendered = report.model_dump(by_alias=True, mode="json", exclude_none=True)
    schema = load_json(
        repo_root / "workshop" / "contracts" / "acceptance-report.schema.json"
    )
    Draft202012Validator(
        schema, format_checker=FormatChecker()
    ).validate(rendered)
    assert report.status == "passed", rendered
