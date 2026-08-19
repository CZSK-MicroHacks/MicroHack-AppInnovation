"""Focused documentation checks for the P5 Copilot modernization path."""

from __future__ import annotations

import json
import re
from pathlib import Path


MODERNIZATION_IDS = {
    "copilot-modernization-dotnet",
    "copilot-modernization-java",
}
EXPECTED_TOOLING = [
    "github.copilot",
    "github.copilot-chat",
    "vscjava.migrate-java-to-azure",
]
EXPECTED_EXTENSIONS = {
    "github.copilot": "1.388.0",
    "github.copilot-chat": "0.48.1",
    "vscjava.migrate-java-to-azure": "1.23.26081703",
}
EXPECTED_PATH_EVIDENCE = [
    "evidence/assessment.md",
    "evidence/modernization-plan.md",
    "evidence/task-results.json",
    "evidence/build-test-cve-summary.md",
]
OWNED_DOCUMENT_PREFIXES = (
    "challenges/ch01-copilot-modernization/",
    "solutions/ch01-copilot-modernization/",
)


def _load_registry(repo_root: Path) -> dict[str, object]:
    """Load the frozen challenge registry without reproducing its schema."""
    registry_path = repo_root / "workshop/contracts/challenge-paths.json"
    return json.loads(registry_path.read_text(encoding="utf-8"))


def _modernization_slices(registry: dict[str, object]) -> list[dict[str, object]]:
    """Return the two registered Copilot modernization slices."""
    slices = registry["slices"]
    assert isinstance(slices, list)
    selected = [
        item
        for item in slices
        if isinstance(item, dict) and item.get("id") in MODERNIZATION_IDS
    ]
    assert {item["id"] for item in selected} == MODERNIZATION_IDS
    return selected


def _read_owned_document(repo_root: Path, relative_path: object) -> str:
    """Resolve and read a nonempty document inside the owned P5 directories."""
    assert isinstance(relative_path, str)
    assert relative_path.startswith(OWNED_DOCUMENT_PREFIXES)
    document_path = repo_root / relative_path
    content = document_path.read_text(encoding="utf-8")
    assert content.strip()
    return content


def test_modernization_registry_resolves_exact_owned_documents(
    repo_root: Path,
) -> None:
    """Both frozen slices resolve to nonempty owned challenge and solution docs."""
    registry = _load_registry(repo_root)
    slices = _modernization_slices(registry)

    for slice_definition in slices:
        _read_owned_document(repo_root, slice_definition["challenge"])
        _read_owned_document(repo_root, slice_definition["solution"])
        assert slice_definition["tooling"] == EXPECTED_TOOLING
        assert slice_definition["imageProvider"] == "azure-blob"
        assert slice_definition["pathEvidence"] == EXPECTED_PATH_EVIDENCE


def test_guides_pin_unified_tooling_and_exact_path_evidence(
    repo_root: Path,
) -> None:
    """Every stack guide names exact tooling, Blob, and registered evidence."""
    registry = _load_registry(repo_root)

    for slice_definition in _modernization_slices(registry):
        content = _read_owned_document(repo_root, slice_definition["solution"])
        for extension_id, version in EXPECTED_EXTENSIONS.items():
            assert f"{extension_id}@{version}" in content
        for evidence_path in EXPECTED_PATH_EVIDENCE:
            assert evidence_path in content
        assert "azure-blob" in content
        assert "az acr manifest show-metadata" in content
        assert "evidence\\container-registry.json" in content
        assert "catalog-migrate render-handoff" in content
        assert "--path copilot-modernization" in content
        assert "--rollback-runbook" in content


def test_guides_keep_database_cutover_native_and_preview_optional(
    repo_root: Path,
) -> None:
    """Docs require native cutover and never require the preview Modernize CLI."""
    registry = _load_registry(repo_root)
    challenge_paths = {
        slice_definition["challenge"]
        for slice_definition in _modernization_slices(registry)
    }
    solution_paths = {
        slice_definition["solution"]
        for slice_definition in _modernization_slices(registry)
    }
    contents = [
        _read_owned_document(repo_root, path)
        for path in challenge_paths | solution_paths
    ]

    for content in contents:
        lowered = content.lower()
        semantic_text = lowered.replace("**", "")
        assert "catalog-migrate" in semantic_text
        assert re.search(
            r"(does not|never).{0,80}(perform|attribute).{0,80}"
            r"(database|schema/data|cutover)",
            semantic_text,
            re.DOTALL,
        )
        assert "modernize cli" in semantic_text
        assert "optional" in semantic_text
        assert not re.search(
            r"(require|required|must|prerequisite).{0,60}modernize cli",
            semantic_text,
        )

        prohibited_claims = (
            "the extension performs database cutover",
            "the extension performs schema/data migration",
            "the extension completes database migration",
            "database cutover is performed by the extension",
            "database migration is handled by the extension",
        )
        assert not any(claim in semantic_text for claim in prohibited_claims)
