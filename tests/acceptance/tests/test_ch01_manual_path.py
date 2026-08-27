"""Focused registry and workshop-document checks for the manual modernization path."""

from __future__ import annotations

import os
import shutil
import subprocess
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


def _between(content: str, start: str, end: str) -> str:
    """Return a required documentation section between two headings."""
    start_index = content.index(start)
    return content[start_index : content.index(end, start_index)]


def _migration_execution_fragment(content: str) -> str:
    """Extract one complete manual migration command block."""
    section = _between(content, "## 3. Export", "## 4.")
    start = section.index("Push-Location tests\\acceptance")
    marker = "\nfinally { Pop-Location }"
    end = section.index(marker, start) + len(marker)
    return section[start:end]


def _fenced_block(section: str, language: str) -> str:
    """Extract the first fenced command block from a documentation section."""
    opening = f"```{language}\n"
    start = section.index(opening) + len(opening)
    return section[start : section.index("\n```", start)]


def _release_execution_fragment(content: str) -> str:
    """Extract the manual release acceptance block."""
    return _fenced_block(_between(content, "## 7. Release", "Exercise successful"), "powershell")


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
            "$BaselineTargetJson = az deployment group create",
            "$ReleaseTargetJson = az deployment group create",
            "evidence\\acceptance-report.json",
            "catalog-migrate render-handoff",
            "python -m catalog_acceptance.handoff_cli",
        )
        positions = [text.index(marker) for marker in ordered_markers]
        assert positions == sorted(positions)


def test_manual_transfer_commands_bind_target_source_identity(repo_root: Path) -> None:
    """Every transfer command binds the current commit to protected target output."""
    commands = {
        "manual-dotnet": (
            "catalog-migrate sql export",
            "catalog-migrate sql import",
            "catalog-migrate images copy",
        ),
        "manual-java": (
            "catalog-migrate postgresql export",
            "catalog-migrate postgresql import",
            "catalog-migrate images copy",
        ),
    }
    for slice_id, content in _solution_texts(repo_root).items():
        migration = _between(content, "## 3. Export", "## 4.")
        identity_guard = migration.index("$Target.sourceCommit -cne $SourceCommit")
        first_transfer = migration.index(commands[slice_id][0])
        assert identity_guard < first_transfer
        for command in commands[slice_id]:
            command_start = migration.index(command)
            command_end = migration.index("\n\n", command_start)
            assert "--source-commit $SourceCommit" in migration[
                command_start:command_end
            ]


def test_manual_handoff_stops_at_each_native_failure(repo_root: Path) -> None:
    """Rendering and validation have immediate guards in all manual guides."""
    for content in _solution_texts(repo_root).values():
        handoff = content.index("catalog-migrate render-handoff")
        render_guard = content.index("handoff rendering failed", handoff)
        validation = content.index(
            "python -m catalog_acceptance.handoff_cli", render_guard
        )
        validation_guard = content.index("handoff validation failed", validation)
        assert handoff < render_guard < validation < validation_guard


def test_manual_migration_blocks_enforce_secret_and_failure_protocol(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """Execute manual migration blocks with per-command failures and secret inspection."""
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        return

    secret_names = (
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
function Get-Content {
  return ('{"sourceCommit":"' + $env:SOURCE_COMMIT +
    '","database":{"resourceId":"database-resource-id"},' +
    '"images":{"resourceId":"image-resource-id"}}')
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
  $FailureProbe = @(
    $args | ForEach-Object { "$_" } | Where-Object { $_ -notmatch '[\\/]' }
  ) -join ' '
  $global:LASTEXITCODE = if (
    $env:FAIL_COMMAND -and $FailureProbe.Contains($env:FAIL_COMMAND)
  ) { 23 } else { 0 }
}
$SourceCommit = $env:SOURCE_COMMIT
$DatabaseArtifact = 'database-artifact'
$env:CATALOG_DATABASE_HOST = 'source-host'
$env:CATALOG_DATABASE_PORT = '5432'
$env:CATALOG_DATABASE_NAME = 'catalog'
$env:CATALOG_DATABASE_USERNAME = 'catalog'
"""
    epilogue = r"""
$Residual = @(
  'MIGRATION_SOURCE_DATABASE_PASSWORD',
  'MIGRATION_TARGET_ADMINISTRATOR_PASSWORD',
  'MIGRATION_TARGET_APPLICATION_PASSWORD'
) | Where-Object { Test-Path "Env:$_" }
[IO.File]::WriteAllText($env:RESIDUAL_LOG, ($Residual -join ','))
[IO.File]::WriteAllText($env:LOCATION_LOG, (Get-Location).Path)
"""
    scenarios = {
        "manual-dotnet": [
            "sql export|MIGRATION_SOURCE_DATABASE_PASSWORD",
            "sql import|",
            "images copy|",
            "verify|",
        ],
        "manual-java": [
            "postgresql export|MIGRATION_SOURCE_DATABASE_PASSWORD",
            (
                "postgresql import|MIGRATION_TARGET_ADMINISTRATOR_PASSWORD,"
                "MIGRATION_TARGET_APPLICATION_PASSWORD"
            ),
            "images copy|",
            "verify|MIGRATION_TARGET_APPLICATION_PASSWORD",
        ],
    }

    for slice_id, expected_invocations in scenarios.items():
        fragment = _migration_execution_fragment(
            _solution_texts(repo_root)[slice_id]
        )
        failure_commands = [
            expected.split("|", maxsplit=1)[0] for expected in expected_invocations
        ]
        cases = [("success", "", "")]
        cases.extend(
            (f"fail-{command}", command, "") for command in failure_commands
        )
        cases.append(
            ("fail-source-prompt", "", "Source SQL Server database password")
            if slice_id == "manual-dotnet"
            else (
                "fail-source-prompt",
                "",
                "Source PostgreSQL database password",
            )
        )
        if slice_id == "manual-java":
            cases.append(
                (
                    "fail-application-prompt",
                    "",
                    "Target PostgreSQL application password",
                )
            )

        for case, fail_command, fail_prompt in cases:
            invocation_log = tmp_path / f"{slice_id}-{case}.invocations"
            residual_log = tmp_path / f"{slice_id}-{case}.residual"
            location_log = tmp_path / f"{slice_id}-{case}.location"
            environment = {
                key: value
                for key, value in os.environ.items()
                if key not in secret_names
            }
            environment.update(
                {
                    "FAIL_COMMAND": fail_command,
                    "FAIL_PROMPT": fail_prompt,
                    "SOURCE_COMMIT": "0123456789abcdef0123456789abcdef01234567",
                    "UV_INVOCATION_LOG": str(invocation_log),
                    "RESIDUAL_LOG": str(residual_log),
                    "LOCATION_LOG": str(location_log),
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
            script_path = tmp_path / f"{slice_id}-{case}.ps1"
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
            assert residual_log.read_text(encoding="utf-8") == ""
            assert Path(location_log.read_text(encoding="utf-8")).resolve() == repo_root
            invocations = (
                invocation_log.read_text(encoding="utf-8").splitlines()
                if invocation_log.exists()
                else []
            )
            for index, invocation in enumerate(invocations):
                command, secrets = invocation.split("|", maxsplit=1)
                expected_command, expected_secrets = expected_invocations[index].split(
                    "|", maxsplit=1
                )
                assert expected_command in command
                assert "--source-commit" in command
                assert secrets == expected_secrets
            if case == "success":
                assert len(invocations) == len(expected_invocations)
            elif fail_command:
                assert len(invocations) == failure_commands.index(fail_command) + 1


def test_manual_release_acceptance_replaces_stale_evidence_or_stops(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """A failed release check removes stale evidence, secrets, and location state."""
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        return

    workspace = tmp_path / "workspace"
    (workspace / "tests/acceptance").mkdir(parents=True)
    (workspace / "evidence").mkdir()
    (workspace / "java").mkdir()
    prelude = r"""
$ErrorActionPreference = 'Stop'
function Read-ProtectedValue {
  param([string]$Prompt)
  if ($env:FAIL_PROMPT -and $Prompt -eq $env:FAIL_PROMPT) {
    throw 'injected prompt failure'
  }
  return 'test-secret'
}
function dotnet { $global:LASTEXITCODE = [int]$env:NATIVE_EXIT }
function Invoke-NativeTests { $global:LASTEXITCODE = [int]$env:NATIVE_EXIT }
function az {
  $global:LASTEXITCODE = [int]$env:TOKEN_EXIT
  return 'test-access-token'
}
function uv {
  $Names = @(
    'SQLCMDACCESS_TOKEN',
    'CATALOG_DATABASE_PASSWORD',
    'PERFTEST_API_KEY',
    'MIGRATION_TARGET_APPLICATION_PASSWORD'
  )
  $Present = @($Names | Where-Object { Test-Path "Env:$_" })
  [IO.File]::WriteAllText($env:UV_SECRET_LOG, ($Present -join ','))
  $global:LASTEXITCODE = [int]$env:ACCEPTANCE_EXIT
  if ($global:LASTEXITCODE -eq 0) {
    [IO.File]::WriteAllText($env:REPORT_PATH, 'fresh')
  }
}
$SourceCommit = '0123456789abcdef0123456789abcdef01234567'
$ImageDigest = 'sha256:' + ('0' * 64)
$Target = [pscustomobject]@{
  application = [pscustomobject]@{
    url = 'https://catalog.example'
    revisionName = 'catalog--release-0123456789ab'
  }
  database = [pscustomobject]@{
    server = 'database.example'
    database = 'catalog'
    applicationPrincipal = [pscustomobject]@{ name = 'catalog_app' }
  }
}
"""
    epilogue = r"""
$Residual = @(
  'SQLCMDACCESS_TOKEN',
  'CATALOG_DATABASE_PASSWORD',
  'PERFTEST_API_KEY',
  'MIGRATION_TARGET_APPLICATION_PASSWORD'
) | Where-Object { Test-Path "Env:$_" }
[IO.File]::WriteAllText($env:RESIDUAL_LOG, ($Residual -join ','))
[IO.File]::WriteAllText($env:LOCATION_LOG, (Get-Location).Path)
"""
    contents = _solution_texts(repo_root)
    for slice_id, content in contents.items():
        fragment = _release_execution_fragment(content)
        if slice_id == "manual-java":
            fragment = fragment.replace(".\\mvnw.cmd test", "Invoke-NativeTests")
            expected_secrets = "CATALOG_DATABASE_PASSWORD,PERFTEST_API_KEY"
        else:
            expected_secrets = "SQLCMDACCESS_TOKEN,PERFTEST_API_KEY"

        cases = [
            ("success", "0", "0", "", "0", True),
            ("acceptance-failure", "0", "19", "", "0", True),
            ("native-failure", "17", "0", "", "0", False),
            (
                "performance-prompt-failure",
                "0",
                "0",
                "Runtime performance API key",
                "0",
                False,
            ),
        ]
        if slice_id == "manual-java":
            cases.append(
                (
                    "database-prompt-failure",
                    "0",
                    "0",
                    "Acceptance verifier database password",
                    "0",
                    False,
                )
            )
        else:
            cases.append(("token-failure", "0", "0", "", "19", False))

        for (
            case,
            native_exit,
            acceptance_exit,
            fail_prompt,
            token_exit,
            acceptance_invoked,
        ) in cases:
            report = workspace / "evidence/acceptance-report.json"
            report.write_text("stale", encoding="utf-8")
            secret_log = tmp_path / f"{slice_id}-{case}.release-secrets"
            residual_log = tmp_path / f"{slice_id}-{case}.release-residual"
            location_log = tmp_path / f"{slice_id}-{case}.release-location"
            environment = {
                key: value
                for key, value in os.environ.items()
                if key
                not in {
                    "SQLCMDACCESS_TOKEN",
                    "CATALOG_DATABASE_PASSWORD",
                    "PERFTEST_API_KEY",
                    "MIGRATION_TARGET_APPLICATION_PASSWORD",
                }
            }
            environment.update(
                {
                    "NATIVE_EXIT": native_exit,
                    "ACCEPTANCE_EXIT": acceptance_exit,
                    "FAIL_PROMPT": fail_prompt,
                    "TOKEN_EXIT": token_exit,
                    "REPORT_PATH": str(report),
                    "UV_SECRET_LOG": str(secret_log),
                    "RESIDUAL_LOG": str(residual_log),
                    "LOCATION_LOG": str(location_log),
                }
            )
            script = (
                prelude
                + "\n$Failed = $false\ntry {\n"
                + fragment
                + "\n}\ncatch { $Failed = $true }\n"
                + epilogue
                + "\nif ($Failed) { exit 23 }\n"
            )
            script_path = tmp_path / f"{slice_id}-{case}-release.ps1"
            script_path.write_text(script, encoding="utf-8")
            result = subprocess.run(
                [pwsh, "-NoProfile", "-NonInteractive", "-File", str(script_path)],
                cwd=workspace,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

            assert (result.returncode == 0) is (case == "success")
            if acceptance_invoked:
                assert secret_log.read_text(encoding="utf-8") == expected_secrets
            else:
                assert not secret_log.exists()
            assert residual_log.read_text(encoding="utf-8") == ""
            assert Path(location_log.read_text(encoding="utf-8")).resolve() == workspace
            if case == "success":
                assert report.read_text(encoding="utf-8") == "fresh"
            else:
                assert not report.exists()


def test_each_manual_stack_guards_and_captures_both_application_stages(
    repo_root: Path,
) -> None:
    """Baseline is verified before a guarded release whose exact output is persisted."""
    for text in _solution_texts(repo_root).values():
        baseline = text.index("$BaselineTargetJson = az deployment group create")
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
        release = text.index("$ReleaseTargetJson = az deployment group create")
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

        # Every path authors a Dockerfile, commits it, and pushes it to the
        # participant's own repository, because Challenge 3 checks the application
        # source out of GitHub at this exact SHA and builds that Dockerfile. The
        # archive marker records which upstream zip was provisioned and is therefore
        # a commit GitHub has never seen; using it here would make Challenge 3
        # unbuildable.
        assert "$SourceCommit = (git rev-parse HEAD).Trim()" in snippet
        assert (
            "$SourceCommit = (Get-Content "
            "'C:\\MicroHack\\source\\.source-commit' -Raw).Trim()"
        ) not in snippet
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
