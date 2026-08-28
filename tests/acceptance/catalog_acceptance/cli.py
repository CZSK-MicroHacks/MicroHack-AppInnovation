"""Command-line entry point for live catalog acceptance verification."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from pydantic import SecretStr

from catalog_acceptance.manifest import repository_root
from catalog_acceptance.models.contracts import AcceptanceSettings
from catalog_acceptance.runner import AcceptanceRunner


def build_parser() -> argparse.ArgumentParser:
    """Build the stable command-line interface for acceptance runs."""
    parser = argparse.ArgumentParser(
        description="Verify a MicroHack catalog application against contract 1.1.0"
    )
    parser.add_argument(
        "--profile",
        choices=("full", "smoke"),
        default=os.getenv("CATALOG_ACCEPTANCE_PROFILE", "full"),
        help="full evidence or non-handoff smoke verification",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("CATALOG_BASE_URL"),
        help="Application base URL (or CATALOG_BASE_URL)",
    )
    parser.add_argument(
        "--performance-api-key",
        default=os.getenv("PERFTEST_API_KEY"),
        help="Performance endpoint key (or PERFTEST_API_KEY)",
    )
    parser.add_argument(
        "--data-directory",
        type=Path,
        default=repository_root() / "data",
        help="Canonical data directory",
    )
    parser.add_argument(
        "--database-kind",
        choices=("sqlserver", "postgresql"),
        default=os.getenv("CATALOG_DATABASE_KIND"),
        help="Optional database family (or CATALOG_DATABASE_KIND)",
    )
    parser.add_argument(
        "--database-host",
        default=os.getenv("CATALOG_DATABASE_HOST"),
        help="Optional database host (or CATALOG_DATABASE_HOST)",
    )
    parser.add_argument(
        "--database-port",
        type=int,
        default=(
            int(os.environ["CATALOG_DATABASE_PORT"])
            if os.getenv("CATALOG_DATABASE_PORT")
            else None
        ),
        help="Optional database port (or CATALOG_DATABASE_PORT)",
    )
    parser.add_argument(
        "--database-name",
        default=os.getenv("CATALOG_DATABASE_NAME"),
        help="Optional database name (or CATALOG_DATABASE_NAME)",
    )
    parser.add_argument(
        "--database-username",
        default=os.getenv("CATALOG_DATABASE_USERNAME"),
        help="Optional database username (or CATALOG_DATABASE_USERNAME)",
    )
    parser.add_argument(
        "--database-password",
        default=os.getenv("CATALOG_DATABASE_PASSWORD"),
        help="Optional database password (or CATALOG_DATABASE_PASSWORD)",
    )
    parser.add_argument(
        "--database-ssl-mode",
        choices=("disable", "allow", "prefer", "require"),
        default=os.getenv("CATALOG_DATABASE_SSL_MODE", "prefer"),
        help="PostgreSQL SSL mode (or CATALOG_DATABASE_SSL_MODE)",
    )
    parser.add_argument(
        "--database-trust-certificate",
        action="store_true",
        default=os.getenv("CATALOG_DATABASE_TRUST_CERTIFICATE", "").lower()
        in ("1", "true", "yes"),
        help="Trust a SQL Server certificate for local development",
    )
    parser.add_argument(
        "--database-target",
        choices=("local", "managed"),
        default=os.getenv("CATALOG_DATABASE_TARGET", "local"),
        help="Database deployment target (or CATALOG_DATABASE_TARGET)",
    )
    parser.add_argument(
        "--expected-work-factor",
        type=int,
        default=int(os.getenv("PERFTEST_WORK_FACTOR", "10")),
        help="Expected bounded performance work factor",
    )
    parser.add_argument(
        "--skip-import",
        action="store_true",
        help="Skip duplicate and invalid upload checks in smoke profile",
    )
    parser.add_argument(
        "--sample-images",
        action="store_true",
        help="Check one representative image instead of the complete corpus",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the JSON report to this path instead of stdout",
    )
    parser.add_argument(
        "--source-commit",
        default=os.getenv("CATALOG_SOURCE_COMMIT"),
        help="Release source commit for handoff binding",
    )
    parser.add_argument(
        "--image-digest",
        default=os.getenv("CATALOG_IMAGE_DIGEST"),
        help="Release image digest for handoff binding",
    )
    parser.add_argument(
        "--revision-name",
        default=os.getenv("CATALOG_REVISION_NAME"),
        help="Deployed revision for handoff binding",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run acceptance checks and return zero only when all required checks pass."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if not arguments.base_url:
        parser.error("--base-url or CATALOG_BASE_URL is required")
    if not arguments.performance_api_key:
        parser.error("--performance-api-key or PERFTEST_API_KEY is required")

    settings = AcceptanceSettings(
        profile=arguments.profile,
        base_url=arguments.base_url,
        performance_api_key=SecretStr(arguments.performance_api_key),
        data_directory=arguments.data_directory.resolve(),
        database_kind=arguments.database_kind,
        database_host=arguments.database_host,
        database_port=arguments.database_port,
        database_name=arguments.database_name,
        database_username=arguments.database_username,
        database_password=(
            SecretStr(arguments.database_password)
            if arguments.database_password
            else None
        ),
        database_access_token=(
            SecretStr(os.environ["SQLCMDACCESS_TOKEN"])
            if os.getenv("SQLCMDACCESS_TOKEN")
            else None
        ),
        database_ssl_mode=arguments.database_ssl_mode,
        database_trust_certificate=arguments.database_trust_certificate,
        database_target=arguments.database_target,
        source_commit=arguments.source_commit,
        image_digest=arguments.image_digest,
        revision_name=arguments.revision_name,
        expected_work_factor=arguments.expected_work_factor,
        verify_import=not arguments.skip_import,
        verify_all_images=not arguments.sample_images,
    )
    if arguments.output:
        # A crashing run must not leave the previous report on disk looking
        # current: the report is written after the run, so any failure inside
        # run() would otherwise preserve a stale -- possibly green, possibly
        # pre-fault-injection -- result that the handoff would then certify.
        arguments.output.unlink(missing_ok=True)
    report = AcceptanceRunner(settings).run()
    rendered = json.dumps(
        report.model_dump(
            by_alias=True,
            mode="json",
            exclude_none=True,
        ),
        indent=2,
    )
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(f"{rendered}\n", encoding="utf-8")
    else:
        print(rendered)
    return 0 if report.status == "passed" else 1
