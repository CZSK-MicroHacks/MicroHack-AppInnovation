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

    for required in (
        "dotnet-sqlserver",
        "java-postgresql",
        "dotnet-smoke.json",
        "java-smoke.json",
        "198",
        "20",
        "evidence/ch00-selection.json",
        "az vm deallocate",
        "facilitator authorizes",
    ):
        assert required in challenge

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


def test_reconciled_navigation_has_no_broken_local_links() -> None:
    """Ensure every local link introduced by final navigation resolves in the repository."""
    broken: list[str] = []

    for source in _active_guide_paths():
        relative_path = source.relative_to(ROOT).as_posix()
        assert source.is_file(), relative_path
        for target in _local_link_targets(source):
            if not target.is_relative_to(ROOT) or not target.exists():
                broken.append(f"{relative_path}: {target}")

    assert not broken, "\n".join(broken)
