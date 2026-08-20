"""Command-line entry point for shared challenge evidence validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from catalog_acceptance.shared_challenges import validate_shared_challenge_evidence


def main(argv: Sequence[str] | None = None) -> int:
    """Validate one P6 evidence bundle and print a machine-readable result."""
    parser = argparse.ArgumentParser(
        description="Validate shared challenge evidence against a modernization handoff."
    )
    parser.add_argument("kind", choices=("load", "cicd", "observability"))
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--handoff", required=True, type=Path)
    parser.add_argument("--contracts", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    args = parser.parse_args(argv)

    validate_shared_challenge_evidence(
        args.kind,
        args.evidence,
        args.handoff,
        args.contracts,
        args.repository_root,
    )
    print(
        json.dumps(
            {
                "status": "passed",
                "kind": args.kind,
                "evidence": str(args.evidence),
                "handoff": str(args.handoff),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
