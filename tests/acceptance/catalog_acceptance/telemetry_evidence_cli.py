"""Command-line entry points for Challenge 1 telemetry evidence (F-89)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from catalog_acceptance.manifest import repository_root
from catalog_acceptance.telemetry_evidence import (
    TelemetryCaptureError,
    render_telemetry_evidence,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the telemetry evidence renderer argument parser."""
    parser = argparse.ArgumentParser(
        prog="catalog-render-telemetry-evidence",
        description=(
            "Render normalized Challenge 1 telemetry evidence from an Azure capture "
            "manifest. Reports every unmet requirement at once instead of one per run."
        ),
    )
    parser.add_argument(
        "--capture",
        type=Path,
        required=True,
        help="repository-relative telemetry capture manifest",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evidence/telemetry-report.json"),
        help="repository-relative rendered report path",
    )
    parser.add_argument(
        "--contracts",
        type=Path,
        default=Path("workshop/contracts"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=repository_root(),
        help=argparse.SUPPRESS,
    )
    return parser


def render_main(argv: Sequence[str] | None = None) -> int:
    """Render one telemetry evidence bundle and print its inventory."""
    args = build_parser().parse_args(argv)
    root = args.repository_root.resolve()
    try:
        inventory = render_telemetry_evidence(
            root / args.capture,
            root / args.contracts,
            root / args.output,
            root,
        )
    except TelemetryCaptureError as error:
        print(
            json.dumps({"status": "failed", "problems": error.problems}, indent=2),
            flush=True,
        )
        return 1
    print(json.dumps({"status": "rendered", **inventory}, indent=2), flush=True)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Alias so the renderer matches the sibling evidence CLIs."""
    return render_main(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(render_main())
