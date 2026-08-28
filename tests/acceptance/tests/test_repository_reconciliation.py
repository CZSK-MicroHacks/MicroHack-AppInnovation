"""Acceptance checks for the final workshop navigation and repository boundary."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[3]

REQUIRED_CHAPTERS = {
    0: ("challenges/ch00/README.md", "solutions/ch00/README.md"),
    1: ("challenges/ch01/README.md", "solutions/ch01/README.md"),
    2: ("challenges/ch02/README.md", "solutions/ch02/README.md"),
    3: ("challenges/ch03/README.md", "solutions/ch03/README.md"),
    4: ("challenges/ch04/README.md", "solutions/ch04/README.md"),
    5: (
        "challenges/ch05-defender/README.md",
        "solutions/ch05-defender/README.md",
    ),
    6: (
        "challenges/ch06-sre-agent/README.md",
        "solutions/ch06-sre-agent/README.md",
    ),
}

NAVIGATION_DOCUMENTS = [
    "README.md",
    "baseInfra/README.md",
    "baseInfra/terraform/README.md",
    "dotnet/README.md",
    "infra/README.md",
    "java/README.md",
    "tests/acceptance/README.md",
    "docs/Design.md",
    "docs/Troubleshooting.md",
]

STALE_ASSETS = [
    "config.tfvars.example",
    "baseInfra/scripts/delete_all_rg.sh",
    "challenges/ch05-enterprise/README.md",
    "challenges/ch05-innovation/README.md",
    "solutions/ch03/bicep/main.bicep",
    "solutions/ch03/bicep/main.bicepparam",
    "solutions/ch03/bicep/.github/workflows/deploy.yaml",
    "solutions/ch03/bicep/README.md",
    "solutions/ch04/bicep/main.bicep",
    "solutions/ch04/bicep/main.bicepparam",
    "solutions/ch04/bicep/.github/workflows/deploy.yaml",
    "solutions/ch04/bicep/README.md",
]

MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
POWERSHELL_FENCE = re.compile(
    r"```(?:powershell|pwsh)\r?\n(?P<body>.*?)```",
    flags=re.DOTALL,
)


def _read(relative_path: str) -> str:
    """Read one UTF-8 repository document."""
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _local_link_targets(source: Path) -> list[Path]:
    """Resolve local Markdown links from one document."""
    targets: list[Path] = []
    for raw_target in MARKDOWN_LINK.findall(source.read_text(encoding="utf-8")):
        target = raw_target.strip().strip("<>")
        parsed = urlsplit(target)
        if parsed.scheme or target.startswith(("#", "mailto:")):
            continue
        path = unquote(parsed.path)
        if not path:
            continue
        targets.append((source.parent / path).resolve())
    return targets


def _powershell_block_containing(document: str, marker: str) -> str:
    """Return the unique PowerShell fence containing the requested marker."""
    matches = [
        match.group("body")
        for match in POWERSHELL_FENCE.finditer(document)
        if marker in match.group("body")
    ]
    assert len(matches) == 1, marker
    return matches[0]


def _active_guide_paths() -> list[Path]:
    """Return every participant, solution, and reconciled navigation document."""
    chapter_documents = [
        path
        for parent in ("challenges", "solutions")
        for path in (ROOT / parent).rglob("README.md")
    ]
    navigation_documents = [ROOT / relative for relative in NAVIGATION_DOCUMENTS]
    return sorted(set(navigation_documents + chapter_documents))


def test_required_chapters_have_participant_and_solution_guides() -> None:
    """Require a complete zero-through-six sequence plus the two optional tracks."""
    for challenge, solution in REQUIRED_CHAPTERS.values():
        assert (ROOT / challenge).is_file(), challenge
        assert (ROOT / solution).is_file(), solution

    assert (ROOT / "challenges/ch07-enterprise/README.md").is_file()
    assert (ROOT / "challenges/ch07-innovation/README.md").is_file()


def test_root_readme_freezes_matrix_sequence_and_facilitator_gates() -> None:
    """Keep the workshop entry point aligned with stacks, paths, and live gates."""
    readme = _read("README.md")

    for required in (
        "dotnet-sqlserver",
        "java-postgresql",
        "Manual rebuild",
        "GitHub Copilot-assisted rewrite",
        "GitHub Copilot modernization",
        "Challenges 0 through 6 are required",
        "Facilitator go/no-go matrix",
        "Subscription isolation",
        "Providers and regions",
        "Quotas and budget",
        "Challenge 5 paid services",
        "Challenge 6 paid services",
        "Golden rejoin",
        "Cleanup",
    ):
        assert required in readme

    assert "Azure12345678" not in readme
    assert "ch05-enterprise" not in readme
    assert "ch05-innovation" not in readme

    for number, (challenge, solution) in REQUIRED_CHAPTERS.items():
        assert re.search(rf"\|\s*\*\*{number}\.", readme)
        assert f"]({challenge})" in readme
        assert f"]({solution})" in readme

    for optional in (
        "challenges/ch07-enterprise/README.md",
        "challenges/ch07-innovation/README.md",
    ):
        assert f"]({optional})" in readme


def test_challenge_zero_proves_both_baselines_and_one_selection() -> None:
    """Require executable comparison, selection evidence, and bounded deallocation."""
    challenge = _read("challenges/ch00/README.md")
    solution = _read("solutions/ch00/README.md")
    behavior_version = json.loads(
        _read("workshop/contracts/behavior-contract.json")
    )["schemaVersion"]
    behavior_reference = (
        f"workshop/contracts/behavior-contract.json@{behavior_version}"
    )

    # A prose phrase must survive the paragraph being re-wrapped: a line break inside
    # "facilitator authorizes" is a formatting change, not a missing warning, and failing
    # a correct document is how a team learns to delete the check. Commands stay exact --
    # "az vm deallocate" split across a newline is broken code, not re-wrapped prose.
    flowed = " ".join(challenge.split())

    for required in (
        "dotnet-sqlserver",
        "java-postgresql",
        "dotnet-smoke.json",
        "java-smoke.json",
        "198",
        "20",
        "evidence/ch00-selection.json",
        "az vm deallocate",
    ):
        assert required in challenge

    for required in ("facilitator authorizes",):
        assert required in flowed

    selection_record = _powershell_block_containing(
        challenge, "$selection = [ordered]@{"
    )
    assert f"baselineContract = '{behavior_reference}'" in selection_record
    assert "sourceCommit = $expectedSourceCommit" in selection_record

    baseline_validation = _powershell_block_containing(
        challenge, "$marker.sourceCommit"
    )
    assert (
        "$expectedSourceCommit -cnotmatch '^[0-9a-f]{40}$'"
        in baseline_validation
    )
    assert "$marker.sourceCommit -cne $expectedSourceCommit" in baseline_validation
    assert (
        "Use the same facilitator-provided\n`$expectedSourceCommit`"
        in challenge
    )

    selection_validation = _powershell_block_containing(
        challenge, "$expectedSelectedVm"
    )
    for required in (
        "'^rg-(user[0-9]{3})$'",
        '"vm-dotnet-$participant"',
        '"vm-java-$participant"',
        "$selection.selectedVm -ne $expectedSelectedVm",
        "$selection.unselectedVm -ne $expectedUnselectedVm",
        "$expectedSourceCommit -cnotmatch '^[0-9a-f]{40}$'",
        "$selection.sourceCommit -cne $expectedSourceCommit",
        f"'{behavior_reference}'",
    ):
        assert required in selection_validation

    active_guides = {
        path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in _active_guide_paths()
    }
    assert sum(
        document.count("az vm deallocate")
        for document in active_guides.values()
    ) == 1
    assert all("az vm stop" not in document for document in active_guides.values())
    assert all("Stop-AzVM" not in document for document in active_guides.values())

    deallocation = _powershell_block_containing(
        active_guides["challenges/ch00/README.md"], "az vm deallocate"
    )
    assert deallocation.strip() == (
        "az vm deallocate `\n"
        "  --resource-group $selection.resourceGroup `\n"
        "  --name $selection.unselectedVm"
    )

    facilitator_validation = _powershell_block_containing(
        solution, "az vm get-instance-view"
    )
    for required in (
        "$selection.selectedVm -ne $expectedSelectedVm",
        "$selection.unselectedVm -ne $expectedUnselectedVm",
        "$selection.sourceCommit -cne $expectedSourceCommit",
        "--name $selection.selectedVm",
        "--name $selection.unselectedVm",
    ):
        assert required in facilitator_validation

    assert "PowerState/deallocated" in solution
    assert "golden handoff" in solution
    assert "az vm delete" not in challenge
    assert "az group delete" not in challenge


def test_design_describes_current_cross_stack_architecture() -> None:
    """Reject the retired single-stack design and preserve current ownership."""
    design = _read("docs/Design.md")

    for required in (
        "dotnet-sqlserver",
        "java-postgresql",
        "Azure SQL Database",
        "PostgreSQL Flexible Server",
        "infra/main.bicep",
        "modernization-contract.json",
        "native producer response",
        "Protected resources and cleanup",
    ):
        assert required in design

    assert "LF-" not in design
    assert ".NET-only" not in design
    assert "Azure SQL and Blob access use the workload managed identity." in design
    assert "supports the frozen `managed-identity` mode or the bounded" in design
    assert "`password-secret`" in design
    assert "Azure Files uses the Container Apps" in design
    assert "`aca-volume-secret` boundary" in design
    assert not re.search(
        r"(?i)\b(?:all|every)\b.{0,80}\b(?:database|storage|image store)s?\b"
        r".{0,80}\bmanaged identity\b",
        design,
    )


def test_optional_tracks_are_chapter_seven_and_do_not_overlap() -> None:
    """Keep enterprise controls and AI innovation cross-stack and independently scoped."""
    enterprise = _read("challenges/ch07-enterprise/README.md")
    innovation = _read("challenges/ch07-innovation/README.md")

    for required in (
        "Private networking",
        "Microsoft Entra",
        "Key Vault",
        "Web Application Firewall",
        "customer-managed key",
        "Azure Policy",
        "Azure SQL Database",
        "PostgreSQL Flexible Server",
    ):
        assert required in enterprise

    assert "Defender" not in enterprise

    for required in (
        ".NET/SQL Server",
        "Java/PostgreSQL",
        "Azure AI Search",
        "managed identity",
        "assistant-ui",
        "citation",
        "evaluation",
    ):
        assert required in innovation


def test_stale_duplicates_and_broad_cleanup_are_absent() -> None:
    """Remove repository assets that conflict with the authoritative deployment path."""
    for relative_path in STALE_ASSETS:
        assert not (ROOT / relative_path).exists(), relative_path

    base_infrastructure = _read("baseInfra/README.md")
    assert "az vm deallocate" not in base_infrastructure
    assert "evidence/ch00-selection.json" in base_infrastructure
    assert "../challenges/ch00/README.md" in base_infrastructure


LOCAL_LINK_FLOOR = 25


def test_reconciled_navigation_has_no_broken_local_links() -> None:
    """Ensure every local link introduced by final navigation resolves in the repository."""
    broken: list[str] = []
    checked = 0

    for source in _active_guide_paths():
        relative_path = source.relative_to(ROOT).as_posix()
        assert source.is_file(), relative_path
        for target in _local_link_targets(source):
            checked += 1
            if not target.is_relative_to(ROOT) or not target.exists():
                broken.append(f"{relative_path}: {target}")

    # An empty link set passes this guard as happily as a correct one, so the walk
    # has to prove it happened before its silence means anything.
    assert checked >= LOCAL_LINK_FLOOR, (
        f"only {checked} local links were resolved; the link extractor has stopped "
        "finding navigation that this guard is supposed to be protecting"
    )
    assert not broken, "\n".join(broken)


def test_run_command_conflict_documents_both_orphan_classes() -> None:
    """Keep the cheap, recoverable orphan check ahead of the unrecoverable one.

    Two different failures produce the same `Conflict` message. A *named* run-command
    stuck in `Pending` is listable and deletable and clears instantly; an orphaned
    `invoke` is neither and must be waited out. Documenting only the second -- which is
    what the page did before the pilot found the first -- sends a reader who could have
    been unblocked in one command into an hour of waiting instead.
    """
    troubleshooting = (ROOT / "docs" / "Troubleshooting.md").read_text(encoding="utf-8")

    named_check = troubleshooting.find("az vm run-command list")
    invoke_probe = troubleshooting.find("az monitor activity-log list")
    assert named_check != -1, (
        "Troubleshooting.md no longer tells a blocked reader to list named run-commands; "
        "the recoverable orphan class has become invisible"
    )
    assert invoke_probe != -1, "the activity-log probe for the invoke orphan is missing"
    assert named_check < invoke_probe, (
        "the listable, instantly-fixable orphan check must come before the probe for the "
        "one that can only be waited out -- a reader stops at the first thing that applies"
    )

    for required in (
        "az vm run-command delete",
        "executionState",
        "does not self-clear",
    ):
        assert required in troubleshooting, (
            f"Troubleshooting.md no longer contains {required!r}, which the named-orphan "
            "remedy depends on"
        )

    facilitator = (ROOT / "docs" / "Facilitator.md").read_text(encoding="utf-8")
    assert "az vm run-command delete" in facilitator, (
        "Facilitator.md no longer tells facilitators to delete named run-commands they "
        "leave on participant VMs, which is how the pilot's blockage was caused"
    )


def test_run_command_docs_never_project_instance_view_from_a_list() -> None:
    """Keep the documented orphan check executable against the real Azure CLI.

    `az vm run-command list` has no `--show-details` flag, and its response carries
    `instanceView: null` even when asked with `--expand instanceView`. A documented
    command that projects `instanceView.executionState` out of a *list* therefore either
    errors with `unrecognized arguments` or silently renders an empty column -- and the
    execution state is the only field that distinguishes the recoverable orphan from the
    unrecoverable one. `show --instance-view` is the call that carries it.
    """
    offenders: list[str] = []
    for name in ("Troubleshooting.md", "DayOfCard.md", "Facilitator.md"):
        text = (ROOT / "docs" / name).read_text(encoding="utf-8")
        for block in text.split("```")[1::2]:
            if "run-command list" not in block:
                continue
            if "--show-details" in block:
                offenders.append(f"{name}: `run-command list --show-details` is not a flag")
            if "instanceView" in block and "run-command show" not in block:
                offenders.append(f"{name}: `run-command list` cannot project instanceView")
    assert not offenders, (
        "documented run-command orphan checks cannot run as written: "
        + "; ".join(sorted(set(offenders)))
    )


def test_run_command_conflict_tells_you_to_retry_before_escalating() -> None:
    """Keep the cheapest cause of `Conflict` ahead of the expensive ones.

    Measured on an idle VM with no named run-commands and no other caller: five
    invocations ~33s apart all succeeded, and three fired 1-2s apart immediately
    after all returned `Conflict`. The message usually means the caller's own
    previous command is still tearing down, which clears in seconds. Routing that
    person to an orphan hunt or an hour-long wait costs them the difference.

    Asserting on the measured claim rather than on the word "retry", which already
    appeared in the table above this section and made an earlier version of this
    guard pass without the fix it was written for.
    """
    text = (ROOT / "docs" / "Troubleshooting.md").read_text(encoding="utf-8")
    marker = "az vm run-command` returns `Conflict"
    start = text.find(marker)
    assert start != -1, "the run-command Conflict section is gone"
    section = text[start : start + 8000]
    disclaimer = section.find("not evidence of an orphan")
    named = section.find("named* run-command")
    assert disclaimer != -1, (
        "Troubleshooting.md no longer states that a single Conflict is not evidence of "
        "an orphan, which is the measured, cheapest-first advice"
    )
    assert named != -1, "the named-orphan check is gone"
    assert disclaimer < named, (
        "the retry-first advice must precede the named-orphan hunt: a single Conflict is "
        "not evidence of an orphan, and the orphan hunt is the more expensive path"
    )


def test_ch00_baseline_filename_is_derived_from_the_stack_variable():
    """Challenge 0 tells participants to change two values when switching stacks.

    The evidence filename must therefore come from ``$stack`` rather than being
    hardcoded, or following the instruction literally files a Java measurement under
    the .NET name (F-102).
    """
    text = (ROOT / "challenges" / "ch00" / "README.md").read_text(encoding="utf-8")

    assert 'Set-Content "evidence/ch00-$stack-baseline.json"' in text, (
        "challenges/ch00 must derive the baseline evidence filename from $stack"
    )
    assert "Set-Content evidence/ch00-dotnet-baseline.json" not in text, (
        "challenges/ch00 still hardcodes the .NET baseline filename"
    )
    for hardcoded in (
        "throw 'The .NET baseline HTTP checks failed.'",
        "throw 'The .NET provisioning marker does not match the frozen baseline.'",
    ):
        assert hardcoded not in text, (
            f"challenges/ch00 still hardcodes a .NET-specific failure message: {hardcoded}"
        )


def test_ch01_warns_that_modernizing_ends_the_legacy_application():
    """Challenge 1 edits configuration in the tree the legacy app boots from.

    That destroys the workshop's "before" system silently and permanently, and the
    wrap-up later asks for a comparison against it (F-103).
    """
    text = (ROOT / "challenges" / "ch01" / "README.md").read_text(encoding="utf-8")
    lowered = text.lower()

    assert "ends the legacy application" in lowered, (
        "challenges/ch01 must warn that the legacy application stops running"
    )
    assert "legacy-source" in text, (
        "challenges/ch01 must offer the copy that preserves the legacy tree"
    )

    warning = lowered.index("ends the legacy application")
    body = lowered[warning : warning + 1600]
    assert "challenge 0" in body, (
        "the warning must point back to Challenge 0 evidence as the surviving record"
    )
