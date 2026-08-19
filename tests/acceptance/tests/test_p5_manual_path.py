"""Focused registry and workshop-document checks for the P5 manual path."""

from __future__ import annotations

from pathlib import Path

from catalog_migrate.contracts import load_json


MANUAL_IDS = {"manual-dotnet", "manual-java"}
OWNED_CHALLENGE = Path("challenges/ch01-manual/README.md")
OWNED_SOLUTIONS = {
    "manual-dotnet": Path("solutions/ch01-manual/dotnet/README.md"),
    "manual-java": Path("solutions/ch01-manual/java/README.md"),
}


def _manual_slices(repo_root: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Load the frozen path registry and return its two manual slices."""
    registry = load_json(repo_root / "workshop/contracts/challenge-paths.json")
    slices = [item for item in registry["slices"] if item["path"] == "manual"]
    return registry, slices


def test_manual_registry_resolves_to_nonempty_owned_documents(repo_root: Path) -> None:
    """Both manual slices resolve only to the owned challenge and solution guides."""
    _, slices = _manual_slices(repo_root)

    assert {item["id"] for item in slices} == MANUAL_IDS
    for item in slices:
        challenge = Path(item["challenge"])
        solution = Path(item["solution"])
        assert challenge == OWNED_CHALLENGE
        assert solution == OWNED_SOLUTIONS[item["id"]]
        for document in (challenge, solution):
            resolved = repo_root / document
            assert resolved.is_file()
            assert resolved.read_text(encoding="utf-8").strip()


def test_manual_guides_represent_registry_evidence_and_commands(repo_root: Path) -> None:
    """Guides include every frozen evidence path and shared command used by the slice."""
    registry, slices = _manual_slices(repo_root)
    challenge_text = (repo_root / OWNED_CHALLENGE).read_text(encoding="utf-8")
    solution_text = "\n".join(
        (repo_root / path).read_text(encoding="utf-8")
        for path in OWNED_SOLUTIONS.values()
    )
    combined = f"{challenge_text}\n{solution_text}"

    evidence = {
        path
        for item in slices
        for field in ("requiredEvidence", "pathEvidence")
        for path in item[field]
    }
    assert evidence
    assert all(path in combined for path in evidence)

    shared = registry["sharedTarget"]
    assert shared["infrastructure"] in combined
    assert shared["migrationCommand"] in combined
    assert "python -m catalog_acceptance --profile full" in combined
    assert "python -m catalog_acceptance.handoff_cli" in combined
    assert "catalog-migrate render-handoff" in combined
    assert "--path manual" in combined
    assert "--rollback-runbook" in combined
    for command in (
        "catalog-migrate sql export",
        "catalog-migrate sql import",
        "catalog-migrate postgresql export",
        "catalog-migrate postgresql import",
        "catalog-migrate images copy",
        "catalog-migrate verify",
    ):
        assert command in combined


def test_manual_slice_rejects_path_tool_and_provider_drift(repo_root: Path) -> None:
    """Manual slices stay on the frozen owned paths, providers, stacks, and native tools."""
    registry, slices = _manual_slices(repo_root)

    assert registry["sharedChallenge"] == "challenges/ch01/README.md"
    assert registry["sharedTarget"]["infrastructure"] == "infra/main.bicep"
    assert registry["sharedTarget"]["migrationCommand"] == "catalog-migrate"
    assert all(item["challenge"] == OWNED_CHALLENGE.as_posix() for item in slices)
    assert all(item["solution"] == OWNED_SOLUTIONS[item["id"]].as_posix() for item in slices)
    assert all(item["imageProvider"] == "azure-files" for item in slices)
    assert all(item["tooling"] == [] for item in slices)

    by_id = {item["id"]: item for item in slices}
    assert (
        by_id["manual-dotnet"]["stack"],
        by_id["manual-dotnet"]["databaseFamily"],
        by_id["manual-dotnet"]["dockerfile"],
    ) == ("dotnet-sqlserver", "azure-sql", "dotnet/Dockerfile")
    assert (
        by_id["manual-java"]["stack"],
        by_id["manual-java"]["databaseFamily"],
        by_id["manual-java"]["dockerfile"],
    ) == ("java-postgresql", "postgresql-flexible", "java/Dockerfile")

    texts = {
        item["id"]: (repo_root / item["solution"]).read_text(encoding="utf-8")
        for item in slices
    }
    assert "vscjava.migrate-java-to-azure" not in "\n".join(texts.values())
    assert "github.copilot" not in "\n".join(texts.values()).lower()
    assert ":latest" not in "\n".join(texts.values()).lower()
