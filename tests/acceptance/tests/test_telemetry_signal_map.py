"""The signal map is only useful if it stays in step with the frozen contract.

Two of the four trace signals do not exist as literal strings anywhere in
Application Insights, and every wrong query returns zero rows rather than an
error. That makes the map load-bearing: an attendee who follows it finds the
signal, and an attendee who does not concludes the application is not emitting
it and goes off to instrument code that is already correct. A map that silently
drifts from the contract is worse than no map, because it is trusted.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = REPO_ROOT / "workshop" / "contracts"


def _load(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def test_the_signal_map_covers_every_contract_signal_and_invents_none() -> None:
    behavior = _load("behavior-contract.json")["telemetry"]
    mapping = _load("telemetry-signal-map.json")

    # The contract names the four that are required; the map may name more,
    # because the map records what the store actually carries.
    assert set(behavior["requiredResourceAttributes"]) <= set(
        mapping["resourceAttributes"]["attributes"]
    )
    assert set(mapping["metrics"]["signals"]) == set(behavior["metrics"])
    for group in ("traces", "logs"):
        mapped = {k for k in mapping[group] if not k.startswith("$")}
        assert mapped == set(behavior[group]), f"{group} drifted from the contract"


def test_every_mapped_signal_names_a_table_and_a_selector() -> None:
    """A map entry that omits the discriminator recreates the trap it removes."""
    mapping = _load("telemetry-signal-map.json")
    for group, required in (("traces", "selector"), ("logs", "form")):
        for name, entry in mapping[group].items():
            if name.startswith("$"):
                continue
            assert entry.get("table"), f"{group}/{name} names no table"
            assert entry.get(required), f"{group}/{name} names no {required}"


def test_the_map_is_reachable_from_the_material() -> None:
    doc = (REPO_ROOT / "docs" / "TelemetryFaultInjection.md").read_text(encoding="utf-8")
    assert "telemetry-signal-map.json" in doc


def test_each_fault_is_verified_restored_by_the_probe_that_showed_it_failing() -> None:
    """A restore is verified with the request that failed, never a weaker one.

    The page documents that ``/readyz`` returns 200 throughout the step 2 fault
    because it never reads application data. A probe that cannot observe a fault
    while it is present cannot observe its removal, so prescribing it as the
    restore check is a guaranteed false negative. A bare ``/`` is weaker than the
    ``/?search=`` request the fault section drives, and fails the same way.
    """
    root = Path(__file__).resolve().parents[3]
    page = (root / "docs/TelemetryFaultInjection.md").read_text(encoding="utf-8")

    # Markdown prose wraps, so a restore instruction is a paragraph and not a
    # line. Scoping this check to single lines is how an earlier draft of this
    # guard passed against the very document it was written to reject.
    paragraphs = [p for p in page.split("\n\n") if "**Restore" in p]
    assert paragraphs, "the restore instructions moved; this guard has gone blind"

    for paragraph in paragraphs:
        prescription = paragraph.split("Do not verify")[0]
        assert "/readyz" not in prescription, (
            "restore verified with /readyz, which the same page says cannot see "
            f"the fault: {prescription}"
        )
        assert "/?search=" in prescription, (
            f"restore must be verified with the request that failed: {prescription}"
        )

    # The page must still contain the observation that makes the rule necessary,
    # otherwise the rule reads as arbitrary and the next editor will undo it.
    assert "it never reads application data" in page

    order = page.split("## 6. Order of operations", 1)[1]
    for step in ("3. Step 2. Restore", "4. Step 3. Restore"):
        line = next((n for n in order.splitlines() if n.startswith(step)), None)
        assert line is not None, f"{step!r} moved; guard is blind"
        assert "/?search=" in line, (
            f"the summarised order must name the same probe as the section: {line}"
        )


def test_the_acceptance_re_run_is_ordered_after_every_fault_is_restored() -> None:
    """The handoff pins acceptance to ``passed``, so ordering is not optional.

    Without a stated position in the sequence, an attendee can re-run acceptance
    while a fault is active, get a failing report, and have no instruction saying
    the order was wrong rather than the application.
    """
    root = Path(__file__).resolve().parents[3]
    page = (root / "docs/TelemetryFaultInjection.md").read_text(encoding="utf-8")
    order = page.split("## 6. Order of operations", 1)[1]

    assert "acceptance" in order.lower(), (
        "the order of operations must say where the acceptance re-run belongs"
    )
    assert "passed" in order, (
        "the ordering must state why it matters: the contract pins result=passed"
    )
