"""Command-line entry points for Challenge 6 evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import NoReturn, Sequence

from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from catalog_acceptance.manifest import repository_root
from catalog_acceptance.sre_evidence import (
    validate_recovery_time,
    render_sre_agent_evidence,
    validate_sre_agent_evidence,
)


class _MachineReadableArgumentParser(argparse.ArgumentParser):
    """Raise argument errors so command failures remain JSON."""

    def error(self, message: str) -> NoReturn:
        """Raise one stable validation error instead of exiting with text."""
        raise ValueError(f"invalid arguments: {message}")


def _base_parser(program: str, description: str) -> argparse.ArgumentParser:
    """Build the shared SRE Agent evidence argument parser."""
    parser = _MachineReadableArgumentParser(prog=program, description=description)
    parser.add_argument(
        "--capture",
        type=Path,
        required=True,
        help="repository-relative SRE Agent capture manifest",
    )
    parser.add_argument(
        "--handoff",
        type=Path,
        required=True,
        help="repository-relative modernization handoff",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=repository_root(),
        help=argparse.SUPPRESS,
    )
    return parser


def build_render_parser() -> argparse.ArgumentParser:
    """Build the deterministic SRE Agent renderer parser."""
    parser = _base_parser(
        "catalog-render-sre-agent-evidence",
        "Render Challenge 6 evidence from digest-bound Azure captures.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evidence/sre-agent-report.json"),
        help="repository-relative rendered report path",
    )
    return parser


def build_validate_parser() -> argparse.ArgumentParser:
    """Build the independent SRE Agent validator parser."""
    parser = _base_parser(
        "catalog-validate-sre-agent-evidence",
        "Validate the handoff and replay Challenge 6 evidence.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        required=True,
        help="repository-relative rendered SRE Agent report",
    )
    parser.add_argument(
        "--contracts",
        type=Path,
        required=True,
        help="repository-relative workshop contracts directory",
    )
    parser.add_argument(
        "--recovery-time",
        type=Path,
        default=None,
        help=(
            "repository-relative evidence/ch06-mttr.json; when given, its "
            "arithmetic is recomputed and its recovery instant is compared "
            "against the resolved alert the report seals"
        ),
    )
    return parser


def _print_failure(error: Exception) -> int:
    """Print one stable machine-readable CLI failure."""
    print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
    return 1


def render_main(argv: Sequence[str] | None = None) -> int:
    """Render one SRE Agent bundle and print its artifact inventory."""
    try:
        args = build_render_parser().parse_args(argv)
        root = args.repository_root.resolve()
        result = render_sre_agent_evidence(
            root / args.capture,
            root / args.handoff,
            root / args.output,
            root,
        )
    except (OSError, ValueError, JsonSchemaValidationError) as error:
        return _print_failure(error)
    print(json.dumps({"status": "passed", **result}, sort_keys=True))
    return 0


def validate_main(argv: Sequence[str] | None = None) -> int:
    """Validate one rendered report by replaying every immutable input."""
    try:
        args = build_validate_parser().parse_args(argv)
        root = args.repository_root.resolve()
        result = validate_sre_agent_evidence(
            root / args.capture,
            root / args.handoff,
            root / args.report,
            root / args.contracts,
            root,
        )
        if args.recovery_time is not None:
            result["recoveryTime"] = validate_recovery_time(
                root / args.recovery_time,
                root / args.report,
                root,
            )
    except (OSError, ValueError, JsonSchemaValidationError) as error:
        return _print_failure(error)
    print(json.dumps({"status": "passed", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(render_main())
