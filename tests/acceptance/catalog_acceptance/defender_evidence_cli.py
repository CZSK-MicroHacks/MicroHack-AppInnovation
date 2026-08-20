"""Command-line entry points for Challenge 5 evidence rendering and validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import NoReturn, Sequence

from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from catalog_acceptance.defender_evidence import (
    validate_defender_evidence,
    write_defender_evidence,
)
from catalog_acceptance.manifest import repository_root


class _MachineReadableArgumentParser(argparse.ArgumentParser):
    """Raise argument errors so command failures remain JSON."""

    def error(self, message: str) -> NoReturn:
        """Raise one stable validation error instead of exiting with text."""
        raise ValueError(f"invalid arguments: {message}")


def _base_parser(program: str, description: str) -> argparse.ArgumentParser:
    """Build the shared Defender evidence argument parser."""
    parser = _MachineReadableArgumentParser(prog=program, description=description)
    parser.add_argument(
        "--capture",
        type=Path,
        required=True,
        help="repository-relative Defender capture manifest",
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
    """Build the deterministic Defender renderer argument parser."""
    parser = _base_parser(
        "catalog-render-defender-evidence",
        "Render Challenge 5 evidence from digest-bound Azure captures.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evidence/defender-report.json"),
        help="repository-relative rendered report path",
    )
    return parser


def build_validate_parser() -> argparse.ArgumentParser:
    """Build the independent Defender validation argument parser."""
    parser = _base_parser(
        "catalog-validate-defender-evidence",
        "Validate the modernization handoff and replay Challenge 5 evidence.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        required=True,
        help="repository-relative rendered Defender report",
    )
    parser.add_argument(
        "--contracts",
        type=Path,
        required=True,
        help="repository-relative workshop contracts directory",
    )
    return parser


def _print_failure(error: Exception) -> int:
    """Print one stable machine-readable CLI failure."""
    print(
        json.dumps(
            {
                "status": "failed",
                "error": str(error),
            },
            sort_keys=True,
        )
    )
    return 1


def render_main(argv: Sequence[str] | None = None) -> int:
    """Render one evidence bundle and print its machine-readable inventory."""
    try:
        args = build_render_parser().parse_args(argv)
        root = args.repository_root.resolve()
        result = write_defender_evidence(
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
    """Validate one rendered report by replaying every digest-bound input."""
    try:
        args = build_validate_parser().parse_args(argv)
        root = args.repository_root.resolve()
        result = validate_defender_evidence(
            root / args.capture,
            root / args.handoff,
            root / args.report,
            root / args.contracts,
            root,
        )
    except (OSError, ValueError, JsonSchemaValidationError) as error:
        return _print_failure(error)
    print(json.dumps({"status": "passed", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(render_main())
