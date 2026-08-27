"""Keep the runtime-evidence template, the validator constant, and the schema aligned.

The runtime test report is required by every challenge path, but nothing in the
workshop produces it: fourteen entries totalling twenty-eight fully qualified strings
must be reproduced exactly, and every one of them is a constant the repository already
holds twice. Transcribing them by hand is pure copying with no attendee-supplied
information, and a single character of drift fails the handoff with a message that does
not say which entry is wrong. The template removes the transcription; these tests keep
the template honest, because a stale template is worse than none.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from catalog_acceptance.handoff import REQUIRED_RUNTIME_TESTS

CONTRACTS = Path(__file__).resolve().parents[3] / "workshop" / "contracts"
TEMPLATE_PATH = CONTRACTS / "runtime-test-evidence.template.json"
SCHEMA_PATH = CONTRACTS / "runtime-test-evidence.schema.json"


@pytest.fixture(scope="module")
def template() -> dict:
    return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_template_covers_every_supported_stack(template: dict) -> None:
    """An attendee on either stack must find a template to start from."""
    assert set(template) == set(REQUIRED_RUNTIME_TESTS)


@pytest.mark.parametrize("stack", sorted(REQUIRED_RUNTIME_TESTS))
def test_template_matches_the_validator_mapping(template: dict, stack: str) -> None:
    """The template must satisfy the handoff validator's exact-equality check.

    ``_validate_runtime_results`` compares the submitted mapping against
    ``REQUIRED_RUNTIME_TESTS`` for equality, so a template that drifts by one entry
    sends the attendee to a failure they did not cause and cannot diagnose.
    """
    supplied = {
        test["id"]: (test["testName"], test["testIdentity"])
        for test in template[stack]["tests"]
    }
    assert supplied == REQUIRED_RUNTIME_TESTS[stack]


@pytest.mark.parametrize("stack", sorted(REQUIRED_RUNTIME_TESTS))
def test_template_validates_against_the_published_schema(
    template: dict, schema: dict, stack: str
) -> None:
    """The template must be schema-valid before the attendee edits anything.

    The schema pins every ``testName`` as a const and constrains ``testIdentity`` by
    stack, so this also proves the schema and the validator constant agree. They are
    two independent copies of one truth, and nothing else in the tree compares them.
    """
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(
        template[stack]
    )


@pytest.mark.parametrize("stack", sorted(REQUIRED_RUNTIME_TESTS))
def test_template_placeholders_are_obviously_unfilled(
    template: dict, stack: str
) -> None:
    """A placeholder commit must be impossible to mistake for a real one.

    The template ships schema-valid so it can be checked before use, which means the
    commit field must satisfy the forty-hex pattern. An all-zero commit satisfies the
    shape while being unmistakably unset, so a template submitted unedited fails the
    handoff's provenance check rather than passing as evidence of nothing.
    """
    assert template[stack]["sourceCommit"] == "0" * 40
