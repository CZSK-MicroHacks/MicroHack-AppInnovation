"""Focused documentation checks for the Copilot modernization path."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
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
    """Resolve and read a nonempty document inside the owned modernization directories."""
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


def _between(content: str, start: str, end: str) -> str:
    """Return a required documentation section between two headings."""
    start_index = content.index(start)
    return content[start_index : content.index(end, start_index)]


def _migration_execution_fragment(content: str) -> str:
    """Extract one complete Copilot-modernization migration command block."""
    section = _between(content, "## 5. Native", "## 6.")
    start = section.index("Push-Location tests\\acceptance")
    marker = "\nfinally { Pop-Location }"
    end = section.index(marker, start) + len(marker)
    return section[start:end]


def _acceptance_execution_fragment(content: str) -> str:
    """Extract one complete Copilot-modernization acceptance command block."""
    section = _between(
        content,
        "## 7. Full acceptance, telemetry, and handoff",
        "Exercise normal",
    )
    opening = "```powershell\n"
    start = section.index(opening) + len(opening)
    return section[start : section.index("\n```", start)]


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
        assert "Read-Host $Prompt -AsSecureString" in content
        assert "<runtime-performance-api-key>" not in content
        assert "--output $AcceptanceReport" in acceptance

        report_position = acceptance.index("$AcceptanceReport =")
        removal_position = acceptance.index(
            "Remove-Item -LiteralPath $AcceptanceReport", report_position
        )
        credential_positions = [
            position
            for marker in ("az account get-access-token", "Read-ProtectedValue")
            if (position := acceptance.find(marker)) >= 0
        ]
        set_position = acceptance.index("$env:PERFTEST_API_KEY =")
        command_position = acceptance.index(
            "uv --no-config run python -m catalog_acceptance", set_position
        )
        clear_position = acceptance.index(
            "Remove-Item Env:PERFTEST_API_KEY", command_position
        )
        assert report_position < removal_position < min(credential_positions)
        assert set_position < command_position < clear_position


def test_modernization_acceptance_removes_stale_evidence_before_failures(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """Token, prompt, and process failures cannot preserve stale acceptance proof."""
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        return

    workspace = tmp_path / "workspace"
    (workspace / "tests/acceptance").mkdir(parents=True)
    (workspace / "evidence").mkdir()
    prelude = r"""
$ErrorActionPreference = 'Stop'
function Read-ProtectedValue {
  param([string]$Prompt)
  if ($env:FAIL_PROMPT -and $Prompt -eq $env:FAIL_PROMPT) {
    throw 'injected prompt failure'
  }
  return 'test-secret'
}
function az {
  $global:LASTEXITCODE = [int]$env:TOKEN_EXIT
  return 'test-access-token'
}
function uv {
  $Names = @(
    'SQLCMDACCESS_TOKEN',
    'CATALOG_DATABASE_PASSWORD',
    'PERFTEST_API_KEY'
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
$ReleaseRevision = 'catalog--release-0123456789ab'
$ReleaseTarget = [pscustomobject]@{
  application = [pscustomobject]@{ url = 'https://catalog.example' }
  database = [pscustomobject]@{
    server = 'database.example'
    database = 'catalog'
  }
}
"""
    epilogue = r"""
$Residual = @(
  'SQLCMDACCESS_TOKEN',
  'CATALOG_DATABASE_PASSWORD',
  'PERFTEST_API_KEY'
) | Where-Object { Test-Path "Env:$_" }
[IO.File]::WriteAllText($env:RESIDUAL_LOG, ($Residual -join ','))
[IO.File]::WriteAllText($env:LOCATION_LOG, (Get-Location).Path)
"""

    for slice_id, content in _solution_contents(repo_root).items():
        fragment = _acceptance_execution_fragment(content)
        if slice_id == "copilot-modernization-dotnet":
            expected_secrets = "SQLCMDACCESS_TOKEN,PERFTEST_API_KEY"
            stack_cases = [
                ("token-failure", "0", "", "19", False),
            ]
        else:
            expected_secrets = "CATALOG_DATABASE_PASSWORD,PERFTEST_API_KEY"
            stack_cases = [
                (
                    "database-prompt-failure",
                    "0",
                    "Acceptance verifier database password",
                    "0",
                    False,
                ),
            ]
        cases = [
            ("success", "0", "", "0", True),
            ("acceptance-failure", "19", "", "0", True),
            (
                "performance-prompt-failure",
                "0",
                "Runtime performance API key",
                "0",
                False,
            ),
            *stack_cases,
        ]

        for case, acceptance_exit, fail_prompt, token_exit, acceptance_invoked in cases:
            report = workspace / "evidence/acceptance-report.json"
            report.write_text("stale", encoding="utf-8")
            secret_log = tmp_path / f"{slice_id}-{case}.acceptance-secrets"
            residual_log = tmp_path / f"{slice_id}-{case}.acceptance-residual"
            location_log = tmp_path / f"{slice_id}-{case}.acceptance-location"
            environment = {
                key: value
                for key, value in os.environ.items()
                if key
                not in {
                    "SQLCMDACCESS_TOKEN",
                    "CATALOG_DATABASE_PASSWORD",
                    "PERFTEST_API_KEY",
                }
            }
            environment.update(
                {
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
                + "\ntry {\n"
                + fragment
                + "\n}\ncatch {\n"
                + epilogue
                + "\nexit 23\n}\n"
                + epilogue
            )
            script_path = tmp_path / f"{slice_id}-{case}-acceptance.ps1"
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
        "$env:MIGRATION_TARGET_APPLICATION_PASSWORD = Read-ProtectedValue",
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
        "$env:MIGRATION_TARGET_APPLICATION_PASSWORD = Read-ProtectedValue",
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


def test_modernization_transfer_and_handoff_guards_are_source_bound(
    repo_root: Path,
) -> None:
    """Transfer rejects stale targets and handoff failures cannot be masked."""
    commands = {
        "copilot-modernization-dotnet": (
            "catalog-migrate sql export",
            "catalog-migrate sql import",
            "catalog-migrate images copy",
        ),
        "copilot-modernization-java": (
            "catalog-migrate postgresql export",
            "catalog-migrate postgresql import",
            "catalog-migrate images copy",
        ),
    }
    for slice_id, content in _solution_contents(repo_root).items():
        migration = _between(content, "## 5. Native", "## 6.")
        identity_guard = migration.index("$Target.sourceCommit -cne $SourceCommit")
        assert identity_guard < migration.index(commands[slice_id][0])
        for command in commands[slice_id]:
            command_start = migration.index(command)
            command_end = migration.index("\n\n", command_start)
            assert "--source-commit $SourceCommit" in migration[
                command_start:command_end
            ]

        handoff = content.index("catalog-migrate render-handoff")
        render_guard = content.index("handoff rendering failed", handoff)
        validation = content.index(
            "python -m catalog_acceptance.handoff_cli", render_guard
        )
        validation_guard = content.index("handoff validation failed", validation)
        assert handoff < render_guard < validation < validation_guard


def test_modernization_guides_do_not_embed_secret_placeholders(
    repo_root: Path,
) -> None:
    """Protected prompts replace secret-bearing substitution examples."""
    secret_placeholder = re.compile(
        r"<[^>\n]*(?:password|api-key)[^>\n]*>", re.IGNORECASE
    )
    for content in _solution_contents(repo_root).values():
        assert not secret_placeholder.search(content)
        assert "Read-Host $Prompt -AsSecureString" in content
        assert "finally {" in content


def test_modernization_migration_blocks_enforce_command_boundaries(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """Execute migration blocks with injected failures and inspect secret state."""
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
  $global:LASTEXITCODE = if (
    $env:FAIL_COMMAND -and $Command.Contains($env:FAIL_COMMAND)
  ) { 23 } else { 0 }
}
$Target = [pscustomobject]@{
  database = [pscustomobject]@{ authentication = $env:TARGET_AUTH }
}
$TargetOutput = 'target.json'
$Artifact = 'database-artifact'
$DatabaseResourceId = 'database-resource-id'
$ImageResourceId = 'image-resource-id'
$SourceCommit = '0123456789abcdef0123456789abcdef01234567'
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
        "copilot-modernization-dotnet": {
            "authentication": "managed-identity",
            "expected": [
                "sql export|MIGRATION_SOURCE_DATABASE_PASSWORD",
                "sql import|",
                "images copy|",
                "verify|",
            ],
        },
        "copilot-modernization-java-password": {
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
        },
        "copilot-modernization-java-managed": {
            "authentication": "managed-identity",
            "expected": [
                "postgresql export|MIGRATION_SOURCE_DATABASE_PASSWORD",
                "postgresql import|MIGRATION_TARGET_ADMINISTRATOR_PASSWORD",
                "images copy|",
                "verify|",
            ],
        },
    }
    contents = _solution_contents(repo_root)

    for scenario, configuration in scenarios.items():
        slice_id = (
            "copilot-modernization-dotnet"
            if scenario == "copilot-modernization-dotnet"
            else "copilot-modernization-java"
        )
        fragment = _migration_execution_fragment(contents[slice_id])
        expected_invocations = configuration["expected"]
        failure_commands = [
            expected.split("|", maxsplit=1)[0] for expected in expected_invocations
        ]
        cases = [("success", "", "")]
        cases.extend(
            (f"fail-{command}", command, "") for command in failure_commands
        )
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
            location_log = tmp_path / f"{scenario}-{case}.location"
            environment = {
                key: value
                for key, value in os.environ.items()
                if key not in secret_names
            }
            environment.update(
                {
                    "FAIL_COMMAND": fail_command,
                    "FAIL_PROMPT": fail_prompt,
                    "TARGET_AUTH": configuration["authentication"],
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
