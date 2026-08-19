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
