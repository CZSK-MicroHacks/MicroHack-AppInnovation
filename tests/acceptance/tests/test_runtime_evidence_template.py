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

from catalog_acceptance.handoff import (
    REQUIRED_RUNTIME_TESTS,
    _validate_runtime_results,
)

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


@pytest.mark.parametrize("stack", sorted(REQUIRED_RUNTIME_TESTS))
def test_template_command_references_paths_that_exist(
    template: dict, stack: str
) -> None:
    """Every source path named by the template command must exist in the repository.

    Regression guard: the first version of this template told .NET attendees to run
    ``dotnet test dotnet/LegoCatalog.App.Tests``, but the project lives at
    ``dotnet/tests/LegoCatalog.App.Tests``, so the command failed with MSB1009. The
    validator never executes ``command``, so nothing caught it -- yet the template's
    whole purpose is to be copied verbatim, which means a wrong command sends the
    attendee into a failure and invites the conclusion that the evidence step is broken.
    A template that cannot be run is worse than no template, because it is trusted.
    """
    repository_root = CONTRACTS.parents[1]
    referenced = [
        token.strip('"')
        for token in template[stack]["command"].split()
        if token.strip('"').startswith(("dotnet/", "java/"))
    ]
    assert referenced, "command names no source path, so nothing is being verified"
    missing = [
        token for token in referenced if not (repository_root / token).exists()
    ]
    assert not missing, f"template command references missing paths: {missing}"


@pytest.mark.parametrize("stack", sorted(REQUIRED_RUNTIME_TESTS))
def test_template_command_writes_where_the_artifact_points(
    template: dict, stack: str
) -> None:
    """The command must produce results at the location ``artifact`` declares.

    The .NET command originally omitted ``--results-directory``, so the TRX landed in
    the default ``TestResults/`` while ``artifact`` pointed at ``evidence/``. The
    handoff then failed to find results that had genuinely been produced -- a silent
    mismatch between two fields of the same document.
    """
    command = template[stack]["command"]
    artifact = template[stack]["artifact"]
    if template[stack]["artifactFormat"] == "trx":
        directory, _, file_name = artifact.rpartition("/")
        assert f"--results-directory {directory}" in command
        assert f"LogFileName={file_name}" in command
    else:
        # Maven writes Surefire reports under the module's target directory.
        assert artifact.endswith("target/surefire-reports")


def test_every_document_that_demands_the_report_names_the_template() -> None:
    """Any document asking for the runtime report must point at the template.

    The template was added to remove hand transcription of twenty-eight constants, but
    it was first referenced only from the challenge briefs while all six solution
    runbooks still said to build the file "against
    ``runtime-test-evidence.schema.json``". A schema constrains values; it does not
    supply them. Participants execute the runbooks, so the fix reached the documents
    that describe the work and missed the documents that direct it, and an arm
    following its runbook verbatim still hand-typed forty-two values.

    This binds the two together: naming the artifact obliges you to name its source.
    """
    repository_root = CONTRACTS.parents[1]
    offenders = []
    examined = []
    for directory in ("challenges", "solutions"):
        for document in sorted((repository_root / directory).rglob("*.md")):
            text = document.read_text(encoding="utf-8")
            if "runtime-test-report" not in text:
                continue
            examined.append(document)
            if "runtime-test-evidence.template.json" not in text:
                offenders.append(str(document.relative_to(repository_root)))
    assert len(examined) >= 9, (
        f"only {len(examined)} documents demand the runtime report; the three challenge "
        "briefs and six solution runbooks all do, so this guard is not finding them"
    )
    assert not offenders, (
        "documents demand evidence/runtime-test-report.json without naming "
        f"the template that supplies its fixed entries: {offenders}"
    )


@pytest.mark.parametrize("stack", sorted(REQUIRED_RUNTIME_TESTS))
def test_documented_three_field_edit_is_accepted_by_the_real_validator(
    template: dict, stack: str, tmp_path
) -> None:
    """Perform the edit the runbooks document, then run the gate that judges it.

    Every other guard here compares the template to a constant, which verifies the
    diff rather than the deliverable. The rewrite arm that exercised this template for
    real made the point sharply: the half-landed reference was found by *attempting the
    artifact*, not by reading the change. So this test does what a participant does --
    copy the stack's object, replace only ``sourceCommit``, ``artifact`` and
    ``command`` -- and then submits the result to ``_validate_runtime_results``, the
    function that actually accepts or rejects it at handoff.

    The native artifact is synthesized to report exactly the frozen identities as
    passing, so a failure here means the documented procedure cannot produce an
    accepted artifact, which is the only claim the runbooks make.
    """
    report = json.loads(json.dumps(template[stack]))
    identities = [
        (test["testName"], test["testIdentity"]) for test in report["tests"]
    ]

    if report["artifactFormat"] == "trx":
        definitions = "".join(
            f'<UnitTest id="t{index}" name="{name}">'
            f'<TestMethod className="{identity.rsplit(".", 1)[0]}" '
            f'name="{identity.rsplit(".", 1)[1]}" /></UnitTest>'
            for index, (name, identity) in enumerate(identities)
        )
        results = "".join(
            f'<UnitTestResult testId="t{index}" testName="{name}" outcome="Passed" />'
            for index, (name, _) in enumerate(identities)
        )
        artifact = tmp_path / "runtime-tests.trx"
        artifact.write_text(
            f"<TestRun><TestDefinitions>{definitions}</TestDefinitions>"
            f"<Results>{results}</Results></TestRun>",
            encoding="utf-8",
        )
    else:
        cases = "".join(
            f'<testcase name="{name}" classname="{identity.split("#", 1)[0]}" />'
            for name, identity in identities
        )
        artifact = tmp_path / "surefire-reports"
        artifact.mkdir()
        (artifact / "TEST-contract.xml").write_text(
            f"<testsuite>{cases}</testsuite>", encoding="utf-8"
        )

    report["sourceCommit"] = "a" * 40
    report["artifact"] = str(artifact)
    report["command"] = "recorded by the participant"

    _validate_runtime_results(report, artifact)
