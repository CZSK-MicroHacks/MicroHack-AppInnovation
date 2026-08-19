"""Focused documentation checks for the bounded standard-Copilot rewrite path."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
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


def _fenced_block(section: str, language: str) -> str:
    """Extract the first fenced command block for executable documentation tests."""
    opening = f"```{language}\n"
    start = section.index(opening) + len(opening)
    end = section.index("\n```", start)
    return section[start:end]


def _migration_execution_fragment(content: str) -> str:
    """Extract the migration command sequence without its interactive helper."""
    section = _between(
        content,
        "### Windows P3 source-VM migration",
        "### Baseline then release",
    )
    start = section.index("Push-Location tests\\acceptance")
    end = section.index("\nPop-Location", start) + len("\nPop-Location")
    return section[start:end]


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


def test_rewrite_migration_guards_identity_and_secret_transitions(
    repo_root: Path,
) -> None:
    """Migration validates identity before transfer and isolates command secrets."""
    for stack, content in _rewrite_solution_documents(repo_root).items():
        normalized = content.lower()
        migration = _between(
            normalized,
            "### windows p3 source-vm migration",
            "### baseline then release",
        )
        identity_guard = migration.index(
            "$target.sourcecommit -cne $sourcecommit"
        )
        export = migration.index("catalog-migrate", identity_guard)
        source_cleanup = migration.index(
            "remove-item env:migration_source_database_password",
            export,
        )
        database_import = migration.index("catalog-migrate", source_cleanup)
        image_copy = migration.index("catalog-migrate", database_import + 1)
        verify = migration.index("catalog-migrate verify", image_copy)

        assert identity_guard < export < source_cleanup < database_import
        assert database_import < image_copy < verify
        assert "read-host $prompt -assecurestring" in migration
        if stack == "java-postgresql":
            admin_set = migration.index(
                "$env:migration_target_administrator_password = "
                "read-protectedvalue",
                source_cleanup,
            )
            admin_cleanup = migration.index(
                "remove-item env:migration_target_administrator_password",
                database_import,
            )
            app_cleanup = migration.index(
                "remove-item env:migration_target_application_password",
                database_import,
            )
            app_verify_set = migration.index(
                "$env:migration_target_application_password = "
                "read-protectedvalue",
                app_cleanup,
            )
            assert source_cleanup < admin_set < database_import < admin_cleanup
            assert admin_cleanup < app_cleanup < image_copy < app_verify_set < verify


def test_rewrite_slice_blocks_fail_before_commit(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """Execute each documented Bash loop with failures injected before commit."""
    prelude = r"""
git() {
  if [ "${1:-}" = "commit" ]; then
    : > "$COMMIT_MARKER"
  fi
  return 0
}
dotnet() { return "${NATIVE_EXIT:-0}"; }
mvnw() { return "${NATIVE_EXIT:-0}"; }
uv() {
  case "$*" in
    *catalog_acceptance*) return "${ACCEPTANCE_EXIT:-0}" ;;
  esac
  return 0
}
rm() { return 0; }
mkdir() { return 0; }
cp() { return 0; }
"""
    for stack, content in _rewrite_solution_documents(repo_root).items():
        section = _between(content, "## 3. Slice loop", "## 4.")
        block = _fenced_block(section, "bash")
        block = block.replace("<slice-name>", "test-slice")
        block = block.replace("./java/mvnw", "mvnw")
        for case, native_exit, acceptance_exit, should_commit in (
            ("native-failure", "17", "0", False),
            ("acceptance-failure", "0", "19", False),
            ("success", "0", "0", True),
        ):
            marker = tmp_path / f"{stack}-{case}.commit"
            environment = {
                **os.environ,
                "COMMIT_MARKER": str(marker),
                "NATIVE_EXIT": native_exit,
                "ACCEPTANCE_EXIT": acceptance_exit,
                "CATALOG_BASE_URL": "http://127.0.0.1:1",
                "PERFTEST_API_KEY": "test-key",
            }
            result = subprocess.run(
                ["bash", "-c", prelude + "\n" + block],
                cwd=repo_root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

            assert (result.returncode == 0) is should_commit
            assert marker.exists() is should_commit


def test_rewrite_migration_blocks_enforce_secret_protocol(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """Execute extracted PowerShell migration flows with stubbed command boundaries."""
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        return

    known_secrets = (
        "MIGRATION_SOURCE_DATABASE_PASSWORD",
        "MIGRATION_TARGET_ADMINISTRATOR_PASSWORD",
        "MIGRATION_TARGET_APPLICATION_PASSWORD",
    )
    prelude = r"""
$ErrorActionPreference = 'Stop'
function Read-ProtectedValue {
  param([string]$Prompt)
  if ($env:FAIL_PROMPT -and $Prompt -eq $env:FAIL_PROMPT) {
    throw 'injected prompt failure'
  }
  return 'test-secret'
}
function uv {
  $Command = ($args | ForEach-Object { "$_" }) -join ' '
  $Names = @(
    'MIGRATION_SOURCE_DATABASE_PASSWORD',
    'MIGRATION_TARGET_ADMINISTRATOR_PASSWORD',
    'MIGRATION_TARGET_APPLICATION_PASSWORD'
  )
  $Present = @($Names | Where-Object { Test-Path "Env:$_" })
  Add-Content -LiteralPath $env:UV_INVOCATION_LOG `
    -Value ("{0}|{1}" -f $Command, ($Present -join ','))
  if ($env:FAIL_COMMAND -and $Command.Contains($env:FAIL_COMMAND)) {
    throw 'injected command failure'
  }
  $global:LASTEXITCODE = 0
}
$Target = [pscustomobject]@{
  database = [pscustomobject]@{ authentication = $env:TARGET_AUTH }
}
$TargetOutput = 'target.json'
$MigrationReport = 'migration.json'
$ImageDirectory = 'images'
$DatabaseArtifact = 'database-artifact'
$TargetDatabaseResourceId = 'database-resource-id'
$TargetImageResourceId = 'image-resource-id'
$SourceCommit = '0123456789abcdef0123456789abcdef01234567'
"""
    epilogue = r"""
$Residual = @(
  'MIGRATION_SOURCE_DATABASE_PASSWORD',
  'MIGRATION_TARGET_ADMINISTRATOR_PASSWORD',
  'MIGRATION_TARGET_APPLICATION_PASSWORD'
) | Where-Object { Test-Path "Env:$_" }
[IO.File]::WriteAllText($env:RESIDUAL_LOG, ($Residual -join ','))
"""
    scenarios = {
        "dotnet-sqlserver": {
            "authentication": "managed-identity",
            "expected": [
                "sql export|MIGRATION_SOURCE_DATABASE_PASSWORD",
                "sql import|",
                "images copy|",
                "verify|",
            ],
            "failures": ("sql export",),
        },
        "java-postgresql-password": {
            "authentication": "password-secret",
            "expected": [
                "postgresql export|MIGRATION_SOURCE_DATABASE_PASSWORD",
                (
                    "postgresql import|MIGRATION_TARGET_ADMINISTRATOR_PASSWORD,"
                    "MIGRATION_TARGET_APPLICATION_PASSWORD"
                ),
                "images copy|",
                "verify|MIGRATION_TARGET_APPLICATION_PASSWORD",
            ],
            "failures": ("postgresql export", "postgresql import", "verify"),
        },
        "java-postgresql-managed": {
            "authentication": "managed-identity",
            "expected": [
                "postgresql export|MIGRATION_SOURCE_DATABASE_PASSWORD",
                "postgresql import|MIGRATION_TARGET_ADMINISTRATOR_PASSWORD",
                "images copy|",
                "verify|",
            ],
            "failures": ("postgresql import",),
        },
    }

    documents = _rewrite_solution_documents(repo_root)
    for scenario, configuration in scenarios.items():
        stack = (
            "dotnet-sqlserver"
            if scenario == "dotnet-sqlserver"
            else "java-postgresql"
        )
        fragment = _migration_execution_fragment(documents[stack])
        cases = [("success", "", "")]
        cases.extend((f"fail-{command}", command, "") for command in configuration["failures"])
        if configuration["authentication"] == "password-secret":
            cases.append(
                (
                    "fail-application-prompt",
                    "",
                    "Target PostgreSQL application password",
                )
            )

        for case, fail_command, fail_prompt in cases:
            invocation_log = tmp_path / f"{scenario}-{case}.invocations"
            residual_log = tmp_path / f"{scenario}-{case}.residual"
            environment = {
                key: value
                for key, value in os.environ.items()
                if key not in known_secrets
            }
            environment.update(
                {
                    "FAIL_COMMAND": fail_command,
                    "FAIL_PROMPT": fail_prompt,
                    "TARGET_AUTH": configuration["authentication"],
                    "UV_INVOCATION_LOG": str(invocation_log),
                    "RESIDUAL_LOG": str(residual_log),
                }
            )
            script = (
                prelude
                + "\ntry {\n"
                + fragment
                + "\n}\ncatch {\n"
                + epilogue
                + "\nexit 23\n}\n"
                + epilogue
            )
            script_path = tmp_path / f"{scenario}-{case}.ps1"
            script_path.write_text(script, encoding="utf-8")
            result = subprocess.run(
                [pwsh, "-NoProfile", "-NonInteractive", "-File", str(script_path)],
                cwd=repo_root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

            assert (result.returncode == 0) is (case == "success")
            assert residual_log.exists(), (result.returncode, result.stdout, result.stderr)
            assert residual_log.read_text(encoding="utf-8") == ""
            invocations = invocation_log.read_text(encoding="utf-8").splitlines()
            for index, expected in enumerate(configuration["expected"]):
                if index >= len(invocations):
                    break
                command, secrets = invocations[index].split("|", maxsplit=1)
                expected_command, expected_secrets = expected.split("|", maxsplit=1)
                assert expected_command in command
                assert secrets == expected_secrets
            if case == "success":
                assert len(invocations) == len(configuration["expected"])


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
        assert "$resourcegroup = $release.resourcegroup.name" in normalized
        assert "$release.application.resourcegroup" not in normalized
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
        fail_fast = slice_loop.index("set -euo pipefail")
        native_test = min(
            index
            for command in ("dotnet test", "./java/mvnw")
            if (index := slice_loop.find(command)) >= 0
        )
        acceptance = slice_loop.index("-m catalog_acceptance")
        commit = slice_loop.index("git commit -m")
        assert fail_fast < native_test < acceptance < commit
        assert "-m catalog_acceptance" in slice_loop
        assert "--profile smoke" in slice_loop
        assert "application must be running" in slice_loop
        assert "static contract tests" in slice_loop
        assert "## architecture delta" in evidence
