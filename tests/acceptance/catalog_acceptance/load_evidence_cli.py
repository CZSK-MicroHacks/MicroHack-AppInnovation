"""Command-line entry point for deterministic load evidence rendering."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from catalog_acceptance.load_evidence import write_load_evidence
from catalog_acceptance.manifest import repository_root


def build_parser() -> argparse.ArgumentParser:
    """Build the load evidence renderer argument parser."""
    parser = argparse.ArgumentParser(
        prog="catalog-render-load-evidence",
        description=(
            "Render normalized Challenge 2 evidence from a digest-bound "
            "Azure capture manifest."
        ),
    )
    parser.add_argument(
        "--capture",
        type=Path,
        required=True,
        help="repository-relative load capture manifest",
    )
    parser.add_argument(
        "--handoff",
        type=Path,
        required=True,
        help="repository-relative modernization handoff",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evidence/load-test-report.json"),
        help="repository-relative rendered report path",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=repository_root(),
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Render one evidence bundle and print its machine-readable inventory."""
    args = build_parser().parse_args(argv)
    root = args.repository_root.resolve()
    try:
        result = write_load_evidence(
            root / args.capture,
            root / args.handoff,
            root / args.output,
            root,
        )
    except (OSError, ValueError) as error:
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
    print(json.dumps({"status": "passed", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
