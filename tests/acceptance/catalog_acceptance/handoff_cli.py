"""Command-line entry point for modernization handoff validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from catalog_acceptance.handoff import validate_handoff


def main(argv: Sequence[str] | None = None) -> int:
    """Validate a handoff bundle and print a machine-readable result."""
    parser = argparse.ArgumentParser(
        description="Validate a modernization handoff and referenced evidence."
    )
    parser.add_argument("handoff", type=Path)
    parser.add_argument("--contracts", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    args = parser.parse_args(argv)

    validate_handoff(
        args.handoff.resolve(),
        args.contracts.resolve(),
        args.repository_root.resolve(),
    )
    print(
        json.dumps(
            {
                "status": "passed",
                "handoff": str(args.handoff),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
