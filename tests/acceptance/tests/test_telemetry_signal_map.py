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
