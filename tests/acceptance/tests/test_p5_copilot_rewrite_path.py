"""Focused documentation checks for the bounded standard-Copilot rewrite path."""

from __future__ import annotations

import json
from pathlib import Path


STANDARD_COPILOT_TOOLS = ["github.copilot", "github.copilot-chat"]
REWRITE_SLICE_IDS = {"copilot-rewrite-dotnet", "copilot-rewrite-java"}
OWNED_DOCUMENT_ROOTS = (
    "challenges/ch01-copilot-rewrite/",
    "solutions/ch01-copilot-rewrite/",
)


def _load_registry(repo_root: Path) -> dict[str, object]:
    """Load the frozen path registry without restating its JSON Schema."""
    path = repo_root / "workshop/contracts/challenge-paths.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _read_owned_document(repo_root: Path, relative_path: str) -> str:
    """Read a nonempty rewrite document that stays within the owned path roots."""
    assert relative_path.startswith(OWNED_DOCUMENT_ROOTS)
    document = repo_root / relative_path
    assert document.is_file()
    content = document.read_text(encoding="utf-8")
    assert content.strip()
    return content


def _rewrite_solution_documents(repo_root: Path) -> dict[str, str]:
    """Return stack-keyed solution text resolved from the frozen registry."""
    registry = _load_registry(repo_root)
    return {
        item["stack"]: _read_owned_document(repo_root, item["solution"])
        for item in registry["slices"]
        if item["id"] in REWRITE_SLICE_IDS
    }


def _between(content: str, start: str, end: str) -> str:
    """Return a required documentation section bounded by two headings."""
    start_index = content.index(start)
    end_index = content.index(end, start_index)
    return content[start_index:end_index]


def test_rewrite_registry_resolves_to_owned_nonempty_documents(repo_root: Path) -> None:
    """Both frozen rewrite slices resolve to the owned challenge and stack guides."""
    registry = _load_registry(repo_root)
    slices = {
        item["id"]: item
        for item in registry["slices"]
        if item["id"] in REWRITE_SLICE_IDS
    }

    assert set(slices) == REWRITE_SLICE_IDS
    for item in slices.values():
        _read_owned_document(repo_root, item["challenge"])
        _read_owned_document(repo_root, item["solution"])


def test_rewrite_registry_uses_only_standard_copilot_and_blob(repo_root: Path) -> None:
    """Rewrite slices keep exact standard Copilot tooling and the Blob provider."""
    registry = _load_registry(repo_root)
    rewrite_slices = [
        item for item in registry["slices"] if item["id"] in REWRITE_SLICE_IDS
    ]

    assert len(rewrite_slices) == 2
    for item in rewrite_slices:
        assert item["path"] == "copilot-rewrite"
        assert item["tooling"] == STANDARD_COPILOT_TOOLS
        assert item["imageProvider"] == "azure-blob"


def test_rewrite_guides_define_evidence_checkpoints_and_handoff(repo_root: Path) -> None:
    """Each guide names objective evidence, review checkpoints, and final handoff."""
    registry = _load_registry(repo_root)
    required_vocabulary = {
        "characterization",
        "bounded-plan",
        "review-checklist",
        "decision-log",
        "checkpoint",
        "acceptance",
        "telemetry",
        "rollback-runbook",
        "stop and replan",
        "cleanup",
        "rejoin",
    }
    handoff_protocol = (
        "catalog-migrate render-handoff --path copilot-rewrite "
        "--rollback-runbook"
    )

    document_paths = {
        item[key]
        for item in registry["slices"]
        if item["id"] in REWRITE_SLICE_IDS
        for key in ("challenge", "solution")
    }
    for path in document_paths:
        normalized = " ".join(_read_owned_document(repo_root, path).lower().split())
        missing = required_vocabulary - {
            term for term in required_vocabulary if term in normalized
        }
        assert not missing, f"{path} is missing required vocabulary: {sorted(missing)}"
        assert handoff_protocol in normalized


def test_rewrite_guides_reject_other_tooling_and_provider_leakage(
    repo_root: Path,
) -> None:
    """Rewrite documentation does not leak extension-assisted or manual providers."""
    registry = _load_registry(repo_root)
    document_paths = {
        item[key]
        for item in registry["slices"]
        if item["id"] in REWRITE_SLICE_IDS
        for key in ("challenge", "solution")
    }
    combined = "\n".join(
        _read_owned_document(repo_root, path).lower() for path in document_paths
    )

    assert "vscjava.migrate-java-to-azure" not in combined
    assert "azure-files" not in combined


def test_rewrite_source_identity_requires_committed_clean_bytes(
    repo_root: Path,
) -> None:
    """Source identity is derived only after accepted slices are committed and clean."""
    challenge = _read_owned_document(
        repo_root, "challenges/ch01-copilot-rewrite/README.md"
    ).lower()
    assert "commit every accepted slice" in challenge
    assert "dirty implementation tree" in challenge

    for stack, content in _rewrite_solution_documents(repo_root).items():
        normalized = content.lower()
        slice_loop = _between(normalized, "## 3. slice loop", "## 4.")
        identity = _between(normalized, "## 4.", "## 5.")
        source_path = "dotnet" if stack == "dotnet-sqlserver" else "java"
        assert "git commit -m" in slice_loop
        clean_command = f"git status --porcelain -- {source_path} data"
        assert clean_command in identity
        assert identity.index(clean_command) < identity.index(
            "git rev-parse head"
        )
        assert "-cnotmatch '^[0-9a-f]{40}$'" in identity
        assert "commit every accepted slice" in identity


def test_rewrite_migration_is_powershell_native_on_windows_source_vm(
    repo_root: Path,
) -> None:
    """Both native migration guides execute from the exact Windows P3 source VM."""
    for content in _rewrite_solution_documents(repo_root).values():
        normalized = content.lower()
        migration = _between(
            normalized,
            "### windows p3 source-vm migration",
            "### baseline then release",
        )
        assert "```powershell" in migration
        assert "target-output.network.migrationsourcevmresourceid" in migration
        assert "push-location tests\\acceptance" in migration
        assert "catalog-migrate" in migration
        assert "c:\\protected\\" in migration
        assert migration.index("git rev-parse head") < migration.index(
            "copy-item 'c:\\protected\\azure-target-output.json'"
        )
        assert "if ($lastexitcode -ne 0)" in migration
        assert "../../" not in migration
        assert "/protected/" not in migration


def test_rewrite_cutover_publishes_digest_and_captures_ordered_release(
    repo_root: Path,
) -> None:
    """Cutover publishes to ACR, deploys baseline then release, and verifies rollback."""
    for stack, content in _rewrite_solution_documents(repo_root).items():
        normalized = content.lower()
        repository = "catalog-dotnet" if stack == "dotnet-sqlserver" else "catalog-java"
        bootstrap = normalized.index("deploymentstage=bootstrap")
        baseline = normalized.index("applicationrevisionrole=baseline")
        release = normalized.index("applicationrevisionrole=release")
        release_capture = normalized.index(
            "$releaseoutput = $releaselines -join", release
        )

        assert bootstrap < baseline < release < release_capture
        assert normalized.index(
            "evidence\\azure-target-output.json'),", release_capture
        ) > release_capture
        assert "docker push $publishedtag" in normalized
        assert "az acr manifest show-metadata" in normalized
        assert f'$imagereference = "$loginserver/{repository}@$imagedigest"' in normalized
        assert "imagedigest=$imagedigest" in normalized
        assert "az containerapp revision show" in normalized
        assert "$baseline.active -ne $false" in normalized
        assert normalized.count("az deployment sub create") == 3
        assert normalized.count("if ($lastexitcode -ne 0)") >= 12


def test_rewrite_slices_require_live_acceptance_and_architecture_delta(
    repo_root: Path,
) -> None:
    """Every accepted slice proves live behavior and records architecture changes."""
    challenge = " ".join(
        _read_owned_document(
            repo_root, "challenges/ch01-copilot-rewrite/README.md"
        )
        .lower()
        .split()
    )
    assert "shared live acceptance profile" in challenge
    assert "static vocabulary" in challenge
    assert "architecture delta" in challenge

    for content in _rewrite_solution_documents(repo_root).values():
        normalized = content.lower()
        slice_loop = _between(normalized, "## 3. slice loop", "## 4.")
        evidence = _between(normalized, "## 6.", "## cleanup and rejoin")
        assert "-m catalog_acceptance" in slice_loop
        assert "--profile smoke" in slice_loop
        assert "application must be running" in slice_loop
        assert "static contract tests" in slice_loop
        assert "## architecture delta" in evidence
