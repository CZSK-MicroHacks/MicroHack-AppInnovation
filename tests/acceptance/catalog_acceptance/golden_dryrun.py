"""Facilitator rehearsal for the T-4 golden handoff procedure.

``golden-dryrun`` walks the procedure in ``workshop/golden/README.md`` against a
golden handoff bundle, times each step, and stops at the *first* thing a
facilitator has to fix. It exists so that an incomplete rejoin path is
discovered at T-4, when there is still room to rebuild it, instead of at 15:15
on day one, when there is not.

The command is read-only. It never renders, repairs, or writes a contract.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, NoReturn, Sequence

from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from catalog_acceptance.artifact_io import load_json_object
from catalog_acceptance.golden_contract_fields import first_contract_defect
from catalog_acceptance.handoff import validate_handoff
from catalog_acceptance.manifest import load_json, repository_root

CONTRACT_RELATIVE_PATH = "evidence/modernization-contract.json"
SEED_MANIFEST_RELATIVE_PATH = "data/manifest.json"
KNOWN_STACKS = ("dotnet-sqlserver", "java-postgresql")


class RehearsalDefect(ValueError):
    """The first missing or malformed thing in a golden handoff bundle."""


@dataclass
class Rehearsal:
    """Mutable state threaded through the ordered rehearsal steps."""

    bundle: Path
    root: Path
    contracts: Path
    contract_path: Path = field(default_factory=Path)
    contract: dict[str, Any] = field(default_factory=dict)


def _require_artifact(root: Path, value: str, label: str) -> None:
    """Require one declared artifact to exist and carry durable content."""
    path = root / value
    if not path.exists():
        raise RehearsalDefect(f"{label} is absent: {path}")
    if path.is_dir():
        if not any(
            child.is_file() and child.stat().st_size > 0 for child in path.rglob("*")
        ):
            raise RehearsalDefect(f"{label} is an empty directory: {path}")
        return
    if path.stat().st_size == 0:
        raise RehearsalDefect(f"{label} is an empty file: {path}")


def _step_locate_bundle(state: Rehearsal) -> str:
    """Require the stack bundle directory the facilitator claims to have built."""
    if not state.bundle.is_dir():
        raise RehearsalDefect(f"golden bundle directory is absent: {state.bundle}")
    return state.bundle.name


def _step_locate_contract(state: Rehearsal) -> str:
    """Require a rendered handoff at the only path the registry accepts."""
    expected = state.root / CONTRACT_RELATIVE_PATH
    if expected.is_file():
        state.contract_path = expected
        return CONTRACT_RELATIVE_PATH
    misplaced = state.bundle / "modernization-contract.json"
    if misplaced.is_file():
        raise RehearsalDefect(
            f"the rendered handoff is at {misplaced}, but every slice in "
            f"challenge-paths.json declares '{CONTRACT_RELATIVE_PATH}' as required "
            f"evidence; move it to {expected} so the bundle validates"
        )
    raise RehearsalDefect(
        f"no rendered handoff in the bundle: expected {expected}. Challenge 1 has "
        "not been completed for this stack -- run 'catalog-migrate render-handoff' "
        "against a facilitator-owned deployment (workshop/golden/README.md)"
    )


def _step_parse_contract(state: Rehearsal) -> str:
    """Require the handoff to be one strict JSON object."""
    state.contract = load_json_object(state.contract_path)
    return f"{len(state.contract)} top-level members"


def _step_contract_fields(state: Rehearsal) -> str:
    """Name the first missing or malformed field against the contract schema."""
    schema_path = state.contracts / "modernization-contract.schema.json"
    if not schema_path.is_file():
        raise RehearsalDefect(f"contract schema is absent: {schema_path}")
    defect = first_contract_defect(state.contract, load_json(schema_path))
    if defect is not None:
        raise RehearsalDefect(f"contract field {defect}")
    return "schema satisfied"


def _step_stack_match(state: Rehearsal) -> str:
    """Require the bundle directory and the contract to describe one stack."""
    stack = state.contract["source"]["stack"]
    if state.bundle.name in KNOWN_STACKS and state.bundle.name != stack:
        raise RehearsalDefect(
            f"contract field /source/stack is '{stack}' but the bundle is "
            f"'{state.bundle.name}'; this handoff would hand a participant the "
            "wrong stack"
        )
    return stack


def _step_declared_evidence(state: Rehearsal) -> str:
    """Require every artifact the contract points at to exist and be non-empty."""
    contract = state.contract
    declared: list[tuple[str, str]] = [
        (contract[section][key], f"contract field /{section}/{key}")
        for section, key in (
            ("acceptance", "report"),
            ("deployment", "targetOutput"),
            ("deployment", "iacPath"),
            ("rollback", "runbook"),
            ("evidence", "migrationReport"),
            ("evidence", "telemetryReport"),
            ("evidence", "runtimeTestReport"),
        )
    ]
    declared.extend(
        (value, f"contract field /evidence/pathEvidence/{index}")
        for index, value in enumerate(contract["evidence"]["pathEvidence"])
    )
    declared.append(
        (
            SEED_MANIFEST_RELATIVE_PATH,
            "canonical seed manifest for the validation root",
        )
    )
    for value, label in declared:
        _require_artifact(state.root, value, label)
    return f"{len(declared)} artifacts present"


def _step_cross_field_checks(state: Rehearsal) -> str:
    """Run the validation the golden procedure requires to exit zero."""
    validate_handoff(state.contract_path, state.contracts, state.root)
    return "handoff agrees with its evidence"


STEPS: tuple[tuple[str, Callable[[Rehearsal], str]], ...] = (
    ("locate-bundle", _step_locate_bundle),
    ("locate-contract", _step_locate_contract),
    ("parse-contract", _step_parse_contract),
    ("contract-fields", _step_contract_fields),
    ("stack-match", _step_stack_match),
    ("declared-evidence", _step_declared_evidence),
    ("cross-field-checks", _step_cross_field_checks),
)


class _MachineReadableArgumentParser(argparse.ArgumentParser):
    """Raise argument errors so command failures remain JSON."""

    def error(self, message: str) -> NoReturn:
        """Raise one stable validation error instead of exiting with text."""
        raise ValueError(f"invalid arguments: {message}")


def build_parser() -> argparse.ArgumentParser:
    """Build the golden handoff rehearsal argument parser."""
    parser = _MachineReadableArgumentParser(
        prog="golden-dryrun",
        description=(
            "Rehearse the T-4 golden handoff procedure against one stack bundle "
            "and name the first thing that is missing or malformed."
        ),
    )
    parser.add_argument(
        "bundle",
        type=Path,
        help="golden handoff bundle directory, e.g. workshop/golden/dotnet-sqlserver",
    )
    parser.add_argument(
        "--contracts",
        type=Path,
        default=repository_root() / "workshop" / "contracts",
        help="workshop contracts directory (default: the checked-in one)",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=None,
        help="validation root for repository-relative evidence (default: the bundle)",
    )
    return parser


def _contract_age_days(path: Path) -> int:
    """Return whole days since the rendered handoff was last written."""
    rendered = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return max((datetime.now(tz=timezone.utc) - rendered).days, 0)


def _print_success(state: Rehearsal) -> None:
    """Print the rejoin-path summary and the keep-them-alive reminder."""
    application = state.contract["application"]
    database = state.contract["database"]
    summary = (
        ("resource group", f"{application['resourceGroup']} ({application['region']})"),
        ("container app", f"{application['containerAppName']}"),
        ("revision", application["revisionName"]),
        ("database", f"{database['server']}/{database['database']}"),
        ("rendered", f"{_contract_age_days(state.contract_path)} day(s) ago"),
    )
    print(f"\nPASS  {state.bundle.name} is a usable rejoin path")
    for label, value in summary:
        print(f"      {label:<16}{value}")
    print(
        "      These resources must stay alive until the workshop ends. Re-run\n"
        "      this command before 09:00 on day one (docs/DayOfCard.md)."
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Walk the T-4 procedure, timing each step, and stop at the first defect.

    Returns:
        ``0`` when the bundle is a complete, valid rejoin path; ``1`` when it is
        not. The final line of stdout is always a machine-readable verdict.
    """
    started = time.perf_counter()
    step_name = "arguments"
    try:
        args = build_parser().parse_args(argv)
        bundle = args.bundle.resolve()
        state = Rehearsal(
            bundle=bundle,
            root=(args.repository_root.resolve() if args.repository_root else bundle),
            contracts=args.contracts.resolve(),
        )
        print(f"T-4 golden handoff rehearsal\n  bundle     {state.bundle}")
        print(f"  root       {state.root}\n  contracts  {state.contracts}\n")
        for step_name, step in STEPS:
            step_started = time.perf_counter()
            try:
                detail = step(state)
            except (OSError, ValueError, JsonSchemaValidationError):
                elapsed = (time.perf_counter() - step_started) * 1000
                print(f"  FAIL  {step_name:<20}{elapsed:>9.1f}ms")
                raise
            elapsed = (time.perf_counter() - step_started) * 1000
            print(f"  ok    {step_name:<20}{elapsed:>9.1f}ms  {detail}")
    except (OSError, ValueError, JsonSchemaValidationError) as error:
        total = (time.perf_counter() - started) * 1000
        print(f"\nFAIL  {step_name}: {error}")
        print(
            json.dumps(
                {
                    "status": "failed",
                    "step": step_name,
                    "error": str(error),
                    "elapsedMs": round(total, 1),
                },
                sort_keys=True,
            )
        )
        return 1
    _print_success(state)
    print(
        json.dumps(
            {
                "status": "passed",
                "bundle": str(state.bundle),
                "stack": state.contract["source"]["stack"],
                "sliceId": state.contract["sliceId"],
                "elapsedMs": round((time.perf_counter() - started) * 1000, 1),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
