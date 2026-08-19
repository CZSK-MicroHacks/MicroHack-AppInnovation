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


def _solution_contents(repo_root: Path) -> dict[str, str]:
    """Return stack IDs mapped to their registered solution guide content."""
    registry = _load_registry(repo_root)
    return {
        str(slice_definition["id"]): _read_owned_document(
            repo_root, slice_definition["solution"]
        )
        for slice_definition in _modernization_slices(registry)
    }


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


def test_guides_recapture_the_clean_committed_modernized_source(
    repo_root: Path,
) -> None:
    """Build and evidence identity comes from the committed modernization delta."""
    for content in _solution_contents(repo_root).values():
        assert content.count("$SourceCommit = (git rev-parse HEAD).Trim()") == 1
        commit_position = content.index("git commit -m")
        stage_position = content.index("git add --", 0, commit_position)
        staged = content[stage_position:commit_position]
        clean_position = content.index(
            "if (git status --porcelain)", commit_position
        )
        source_position = content.index(
            "$SourceCommit = (git rev-parse HEAD).Trim()", clean_position
        )
        build_position = content.index("## 4. Build the immutable container")
        assert commit_position < clean_position < source_position < build_position
        assert "$SourceCommit -cnotmatch '^[0-9a-f]{40}$'" in content
        assert "Do not use `$StartingCommit`" in content
        assert "evidence\\ide-extensions.txt" in staged

    dotnet = _solution_contents(repo_root)["copilot-modernization-dotnet"]
    dotnet_commit = dotnet.index("git commit -m")
    assert '--logger "trx;LogFileName=dotnet-modernization.trx"' in dotnet
    assert "evidence\\dotnet-modernization.trx" in dotnet[:dotnet_commit]
    java = _solution_contents(repo_root)["copilot-modernization-java"]
    java_commit = java.index("git commit -m")
    assert java.index(
        "Copy-Item java\\target\\surefire-reports\\*.xml", 0, java_commit
    ) < java.index("Remove-Item -Recurse -Force java\\target", 0, java_commit)


def test_release_acceptance_binds_subject_and_keeps_key_out_of_argv(
    repo_root: Path,
) -> None:
    """Full acceptance binds release identity and reads its API key from env."""
    for content in _solution_contents(repo_root).values():
        acceptance = content.split(
            "## 7. Full acceptance, telemetry, and handoff", maxsplit=1
        )[1]
        assert "$ReleaseTarget.sourceCommit -ne $SourceCommit" in content
        assert "$ReleaseTarget.containerImage.digest -ne $ImageDigest" in content
        assert (
            "$ReleaseTarget.application.revisionName" in content
            and "$ReleaseRevision" in content
        )
        assert "--source-commit $SourceCommit" in acceptance
        assert "--image-digest $ImageDigest" in acceptance
        assert "--revision-name $ReleaseRevision" in acceptance
        assert "--performance-api-key" not in content

        set_position = acceptance.index("$env:PERFTEST_API_KEY =")
        command_position = acceptance.index(
            "uv --no-config run python -m catalog_acceptance", set_position
        )
        clear_position = acceptance.index(
            "Remove-Item Env:PERFTEST_API_KEY", command_position
        )
        assert set_position < command_position < clear_position


def test_java_scopes_migration_secrets_to_declared_commands(
    repo_root: Path,
) -> None:
    """Java password-mode secrets are absent from image copy and handoff."""
    java = _solution_contents(repo_root)["copilot-modernization-java"]
    migration = java.split(
        "## 5. Native PostgreSQL and Blob cutover", maxsplit=1
    )[1].split("## 6. Deploy baseline and release", maxsplit=1)[0]

    source_set = migration.index("$env:MIGRATION_SOURCE_DATABASE_PASSWORD =")
    export_command = migration.index(
        "catalog-migrate postgresql export", source_set
    )
    source_clear = migration.index(
        "Remove-Item Env:MIGRATION_SOURCE_DATABASE_PASSWORD", export_command
    )
    administrator_set = migration.index(
        "$env:MIGRATION_TARGET_ADMINISTRATOR_PASSWORD =", source_clear
    )
    first_set = migration.index(
        "$env:MIGRATION_TARGET_APPLICATION_PASSWORD = '<target-app-password>'",
        administrator_set,
    )
    import_command = migration.index(
        "catalog-migrate postgresql import", first_set
    )
    first_clear = migration.index(
        "Remove-Item Env:MIGRATION_TARGET_APPLICATION_PASSWORD", import_command
    )
    image_copy = migration.index("catalog-migrate images copy", first_clear)
    second_set = migration.index(
        "$env:MIGRATION_TARGET_APPLICATION_PASSWORD = '<target-app-password>'",
        image_copy,
    )
    verify_command = migration.index("catalog-migrate verify", second_set)
    second_clear = migration.index(
        "Remove-Item Env:MIGRATION_TARGET_APPLICATION_PASSWORD", verify_command
    )
    assert (
        source_set
        < export_command
        < source_clear
        < administrator_set
        < first_set
        < import_command
        < first_clear
        < image_copy
        < second_set
        < verify_command
        < second_clear
    )
    administrator_clear = migration.index(
        "Remove-Item Env:MIGRATION_TARGET_ADMINISTRATOR_PASSWORD",
        import_command,
    )
    assert import_command < administrator_clear < image_copy
    handoff = java.split("catalog-migrate render-handoff", maxsplit=1)[0]
    assert handoff.rfind(
        "Remove-Item Env:MIGRATION_TARGET_APPLICATION_PASSWORD"
    ) > handoff.rfind("catalog-migrate verify")
