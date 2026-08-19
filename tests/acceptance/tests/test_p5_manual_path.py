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


def _solution_texts(repo_root: Path) -> dict[str, str]:
    """Load each manual solution independently for stack-specific assertions."""
    return {
        slice_id: (repo_root / path).read_text(encoding="utf-8")
        for slice_id, path in OWNED_SOLUTIONS.items()
    }


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

    texts = _solution_texts(repo_root)
    assert "vscjava.migrate-java-to-azure" not in "\n".join(texts.values())
    assert "github.copilot" not in "\n".join(texts.values()).lower()
    assert ":latest" not in "\n".join(texts.values()).lower()


def test_each_manual_stack_orders_all_fail_closed_stages(repo_root: Path) -> None:
    """Each stack orders migration, separation, image, baseline, release, and handoff."""
    commands = {
        "manual-dotnet": (
            "catalog-migrate sql export",
            "catalog-migrate sql import",
        ),
        "manual-java": (
            "catalog-migrate postgresql export",
            "catalog-migrate postgresql import",
        ),
    }

    for slice_id, text in _solution_texts(repo_root).items():
        export, database_import = commands[slice_id]
        ordered_markers = (
            "bootstrap deployment failed",
            export,
            database_import,
            "catalog-migrate images copy",
            "catalog-migrate verify",
            "evidence/managed-database-separation.json",
            "az acr build",
            "$BaselineTargetJson = az deployment sub create",
            "$ReleaseTargetJson = az deployment sub create",
            "evidence\\acceptance-report.json",
            "catalog-migrate render-handoff",
            "python -m catalog_acceptance.handoff_cli",
        )
        positions = [text.index(marker) for marker in ordered_markers]
        assert positions == sorted(positions)


def test_each_manual_stack_guards_and_captures_both_application_stages(
    repo_root: Path,
) -> None:
    """Baseline is verified before a guarded release whose exact output is persisted."""
    for text in _solution_texts(repo_root).values():
        baseline = text.index("$BaselineTargetJson = az deployment sub create")
        baseline_guard = text.index(
            "if ($LASTEXITCODE -ne 0) { throw 'baseline deployment failed' }",
            baseline,
        )
        baseline_verify = text.index(
            "baseline revision is not the healthy active immutable target",
            baseline_guard,
        )
        baseline_readiness = text.index(
            "baseline health or readiness failed",
            baseline_verify,
        )
        release = text.index("$ReleaseTargetJson = az deployment sub create")
        release_guard = text.index(
            "if ($LASTEXITCODE -ne 0) { throw 'release deployment failed' }",
            release,
        )
        release_write = text.index(
            '($ReleaseTargetJson -join "`n") + "`n"',
            release_guard,
        )

        assert baseline < baseline_guard < baseline_verify < baseline_readiness < release
        assert release < release_guard < release_write
        assert "| Out-Null" not in text[baseline:release]


def test_each_manual_stack_rehydrates_source_commit_in_second_terminal(
    repo_root: Path,
) -> None:
    """The separation acceptance terminal initializes and validates its own commit."""
    for text in _solution_texts(repo_root).values():
        second_terminal = text.index("In a second source-VM terminal")
        acceptance = text.index(
            "evidence\\transient\\vm-managed-acceptance.json",
            second_terminal,
        )
        snippet = text[second_terminal:acceptance]

        assert "$SourceCommit = (git rev-parse HEAD).Trim()" in snippet
        assert "$SourceCommit -notmatch '^[0-9a-f]{40}$'" in snippet
        assert "--source-commit $SourceCommit" in snippet


def test_each_manual_stack_reinjects_second_terminal_secrets(
    repo_root: Path,
) -> None:
    """Each acceptance terminal acquires and clears its own protected inputs."""
    for slice_id, text in _solution_texts(repo_root).items():
        second_terminal = text.index("In a second source-VM terminal")
        acceptance = text.index(
            "evidence\\transient\\vm-managed-acceptance.json",
            second_terminal,
        )
        cleanup_end = text.index(
            "VM/managed-database acceptance failed",
            acceptance,
        )
        snippet = text[second_terminal:cleanup_end]

        assert "Read-Host $Prompt -AsSecureString" in snippet
        assert "$env:PERFTEST_API_KEY = Read-ProtectedValue" in snippet
        assert "Remove-Item Env:PERFTEST_API_KEY" in snippet
        if slice_id == "manual-java":
            assert "$env:CATALOG_DATABASE_PASSWORD = Read-ProtectedValue" in snippet
            assert "Remove-Item Env:CATALOG_DATABASE_PASSWORD" in snippet
            assert "MIGRATION_TARGET_APPLICATION_PASSWORD" not in snippet
        else:
            assert "az account get-access-token" in snippet
            assert "Remove-Item Env:SQLCMDACCESS_TOKEN" in snippet


def test_each_manual_stack_uses_single_revision_rollback(repo_root: Path) -> None:
    """Rollback activates and verifies the retained revision without traffic weights."""
    for text in _solution_texts(repo_root).values():
        rollback_section = text.index("Write `evidence/rollback-runbook.md`")
        rollback_precheck = text.index(
            "$RollbackStateJson = az containerapp revision show",
            rollback_section,
        )
        rollback = text.index("az containerapp revision activate", rollback_precheck)
        activated_lookup = text.index("$ActivatedStateJson = az containerapp revision show")
        activation_guard = text.index(
            "if ($LASTEXITCODE -ne 0) { throw 'rollback revision activation failed' }",
            rollback,
        )
        active_verify = text.index(
            "rollback revision did not become the healthy active immutable revision",
            activated_lookup,
        )
        release_deactivation = text.index(
            "single revision mode did not deactivate the superseded release",
            active_verify,
        )
        readiness = text.index(
            "activated rollback revision failed health or readiness",
            release_deactivation,
        )

        precheck = text[rollback_precheck:rollback]
        assert "$RollbackState.active -or" in precheck
        assert "$RollbackState.health -ne 'Healthy'" in precheck
        assert rollback_precheck < rollback < activation_guard < activated_lookup
        assert activated_lookup < active_verify < release_deactivation < readiness
        assert "execute it only after rollback approval" in text[rollback_section:rollback]
        assert "az containerapp ingress traffic set" not in text
        assert "--revision-weight" not in text
