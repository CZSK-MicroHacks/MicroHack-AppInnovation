"""Contract tests for the migration topology provisioning-state precondition.

The precondition exists to prove a migration runs on the declared source VM with the
declared network topology. It must not fail a correct migration because the platform
happens to be patching the guest at that instant, and when it does fail it must say
what it saw.
"""

from __future__ import annotations

import pytest

from catalog_migrate.azure import _require_resource_state
from catalog_migrate.errors import PreconditionError, ToolError
from catalog_migrate.process import ProcessResult

RESOURCE_ID = (
    "/subscriptions/00000000-0000-0000-0000-000000000000"
    "/resourceGroups/rg-user001"
    "/providers/Microsoft.Compute/virtualMachines/vm-java-user001"
)
SUBSCRIPTION_ID = "00000000-0000-0000-0000-000000000000"


class _ScriptedRunner:
    """Return a scripted provisioning state for each successive query."""

    def __init__(self, states: list[str]) -> None:
        self._states = list(states)
        self.calls = 0

    def run(self, argv: list[str], **_: object) -> ProcessResult:
        self.calls += 1
        if not self._states:
            raise AssertionError("provisioning state queried more times than scripted")
        return ProcessResult(f"{self._states.pop(0)}\n", "")


def _never_sleep(_: float) -> None:
    """Collapse the retry delay so the bounded window costs no test time."""
    return None


def test_succeeded_is_accepted_without_retrying() -> None:
    """The common case costs exactly one query."""
    runner = _ScriptedRunner(["Succeeded"])
    _require_resource_state(
        runner, RESOURCE_ID, SUBSCRIPTION_ID, sleep=_never_sleep
    )
    assert runner.calls == 1


def test_transient_updating_is_retried_and_then_accepted() -> None:
    """A guest patch assessment must not fail a migration that is otherwise correct.

    Azure flips a virtual machine to ``Updating`` for the duration of every platform
    patch assessment. The machine is running, its identity is unchanged and its
    network topology is unchanged, so none of what this precondition verifies is
    affected. Failing here ends a multi-minute migration at second zero for a reason
    the operator neither caused nor can influence.
    """
    runner = _ScriptedRunner(["Updating", "Updating", "Succeeded"])
    _require_resource_state(
        runner, RESOURCE_ID, SUBSCRIPTION_ID, sleep=_never_sleep
    )
    assert runner.calls == 3


def test_terminal_failure_is_not_retried() -> None:
    """A resource that will never become ready must fail immediately, not after a wait."""
    runner = _ScriptedRunner(["Failed"])
    with pytest.raises(PreconditionError):
        _require_resource_state(
            runner, RESOURCE_ID, SUBSCRIPTION_ID, sleep=_never_sleep
        )
    assert runner.calls == 1


def test_persistent_transient_state_eventually_fails() -> None:
    """The retry window is bounded, so a stuck resource still stops the command."""
    runner = _ScriptedRunner(["Updating"] * 4)
    with pytest.raises(PreconditionError):
        _require_resource_state(
            runner, RESOURCE_ID, SUBSCRIPTION_ID, attempts=4, sleep=_never_sleep
        )
    assert runner.calls == 4


def test_failure_names_the_observed_state() -> None:
    """"Is not provisioned" alone cannot distinguish "wait" from "stop".

    Regression guard: the original message described every outcome as an absent
    resource, so an operator seeing it could not tell a transient patch window from a
    genuine provisioning failure, and the two demand opposite responses.
    """
    runner = _ScriptedRunner(["Failed"])
    with pytest.raises(PreconditionError) as failure:
        _require_resource_state(
            runner, RESOURCE_ID, SUBSCRIPTION_ID, sleep=_never_sleep
        )
    assert "provisioningState=Failed" in str(failure.value)
    assert RESOURCE_ID in str(failure.value)


def test_empty_state_is_reported_as_unavailable() -> None:
    """An empty query result must not be reported as a state the operator can act on."""
    runner = _ScriptedRunner([""])
    with pytest.raises(PreconditionError) as failure:
        _require_resource_state(
            runner, RESOURCE_ID, SUBSCRIPTION_ID, sleep=_never_sleep
        )
    assert "provisioningState=unavailable" in str(failure.value)


def test_query_failure_is_not_disguised_as_a_precondition() -> None:
    """A broken query must surface as a tool failure, never as "not provisioned"."""

    class _FailingRunner:
        def run(self, argv: list[str], **_: object) -> ProcessResult:
            raise ToolError("external tool failed: az")

    with pytest.raises(ToolError):
        _require_resource_state(
            _FailingRunner(), RESOURCE_ID, SUBSCRIPTION_ID, sleep=_never_sleep
        )
