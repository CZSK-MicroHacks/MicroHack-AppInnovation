"""Acceptance checks for the Challenge 5 Defender participant and solution guides."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "workshop/contracts/defender.json"
CHALLENGE = ROOT / "challenges/ch05-defender/README.md"
SOLUTION = ROOT / "solutions/ch05-defender/README.md"


def _read(path: Path) -> str:
    """Return UTF-8 guide text."""
    return path.read_text(encoding="utf-8")


def _contract() -> dict[str, Any]:
    """Return the frozen Defender registry."""
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def _normalized(value: str) -> str:
    """Collapse whitespace for exact multiline command assertions."""
    return " ".join(value.split())


def test_guides_use_the_frozen_handoff_and_evidence_paths() -> None:
    """Require exact repository-relative handoff, capture, and report paths."""
    combined = _read(CHALLENGE) + _read(SOLUTION)
    for value in (
        "evidence/modernization-contract.json",
        "deployment.targetOutput",
        "network.migrationSourceVmResourceId",
        "evidence/defender/capture.json",
        "evidence/defender-report.json",
        "workshop/defender/lab-profile.json",
        "workshop/contracts/defender-evidence-capture.schema.json",
    ):
        assert value in combined
    assert "repository-root-relative" in combined
    assert "SOURCE_VM_ID=$(jq -er '.network.migrationSourceVmResourceId'" in combined


def test_guides_freeze_the_registry_render_and_validate_commands() -> None:
    """Require both guides to reproduce the exact registry commands."""
    registry = _contract()["evidence"]
    challenge = _normalized(_read(CHALLENGE))
    solution = _normalized(_read(SOLUTION))
    for command_key in ("renderCommand", "validateCommand"):
        command = registry[command_key]
        assert command in challenge
        assert command in solution
    assert "From `tests/acceptance`" in _read(CHALLENGE)
    assert "From `tests/acceptance`" in _read(SOLUTION)


def test_guides_cover_the_required_posture_learning_path() -> None:
    """Require both VM identities and every Defender posture subject."""
    combined = (_read(CHALLENGE) + _read(SOLUTION)).casefold()
    for value in (
        "selected retained vm",
        "sibling retained vm",
        "defender for servers p2",
        "azure container apps",
        "azure container registry",
        "image assessment",
        "azure sql",
        "postgresql",
        "recommendations",
        "secure score",
        "mcsb",
        "attack paths",
    ):
        assert value in combined
    assert '["dotnet", "java"]' in _read(SOLUTION)


def test_guides_state_aca_posture_only_and_async_empty_results() -> None:
    """Forbid a host sensor claim and permit empty asynchronous live results."""
    combined = _normalized(_read(CHALLENGE) + _read(SOLUTION)).casefold()
    assert "posture only" in combined
    assert "no host/runtime defender sensor" in combined
    assert "platform-managed host" in combined
    assert "current live query can legitimately return zero records" in combined
    assert "complete empty response is successful query evidence" in combined
    assert "never wait for or manufacture a new recommendation or alert" in combined
    assert "aca has a host/runtime defender sensor" not in combined


def test_guides_preserve_distinct_seed_and_live_evidence() -> None:
    """Require pre-warmed deterministic evidence without example/live aliasing."""
    combined = (_read(CHALLENGE) + _read(SOLUTION)).casefold()
    for value in (
        "distinct pre-warmed",
        "seed snapshot",
        "sanitized examples",
        "never live participant evidence",
        "not current participant evidence",
        "aliasing seed and current files",
    ):
        assert value in combined
    assert "never copy fixture ids, hashes, timestamps, findings" in combined


def test_guides_limit_remediation_to_the_four_frozen_controls() -> None:
    """Require all and only the registry control identifiers."""
    challenge = _read(CHALLENGE)
    registry_controls = [item["id"] for item in _contract()["controls"]]
    assert len(registry_controls) == 4
    for control in registry_controls:
        assert control in challenge
    combined = _read(CHALLENGE) + _read(SOLUTION)
    for value in (
        "admin-enabled false",
        "--allow-insecure false",
        '"publicNetworkAccess":"Disabled"',
        "VM_MANAGEMENT_RULE_ID",
        "documented-exception",
        "already-compliant",
        "7f951dda-4ed3-4680-a7ca-43fe172d538d",
        "@<handoff sha256 digest>",
    ):
        assert value in combined


def test_database_commands_are_family_bound() -> None:
    """Require Azure SQL and PostgreSQL parent-resource handling."""
    solution = _read(SOLUTION)
    for value in (
        "azure-sql)",
        "Microsoft.Sql/servers",
        "DATABASE_API_VERSION=2023-08-01",
        "postgresql-flexible)",
        "Microsoft.DBforPostgreSQL/flexibleServers",
        "DATABASE_API_VERSION=2024-08-01",
        "DATABASE_SERVER_ID=${DATABASE_RESOURCE_ID%/databases/*}",
    ):
        assert value in solution


def test_current_queries_match_frozen_paths_methods_and_versions() -> None:
    """Require every current query producer declared by the registry."""
    challenge = _read(CHALLENGE)
    solution = _read(SOLUTION)
    queries = _contract()["evidence"]["queryContracts"]
    for name, query in queries.items():
        assert query["resourcePath"] in challenge, name
        assert query["resourcePath"] in solution, name
        assert query["apiVersion"] in challenge, name
        assert query["apiVersion"] in solution, name
        assert (
            f'method: "{query["method"]}"' in solution
            or f'method:"{query["method"]}"' in solution
        ), name
    attack = queries["attackPaths"]
    expected_query = (
        attack["queryTemplate"]
        .replace("{subscriptionId}", "%s")
        .replace("\n", "\\n")
    )
    assert expected_query in solution
    assert 'options:{resultFormat:"objectArray"}' in solution
    assert 'resultTruncated == "false"' in solution


def test_cleanup_provenance_matches_the_refrozen_composite() -> None:
    """Require truthful table and ARM-list cleanup producers."""
    combined = _read(CHALLENGE) + _read(SOLUTION)
    cleanup = _contract()["cleanup"]["cleanupInventoryProducers"]
    for table, resource_types in cleanup["resourceGraph"]["tables"].items():
        assert table in combined
        for resource_type in resource_types:
            assert resource_type in combined
    for producer_name in ("autoProvisioningSettings", "settings"):
        producer = cleanup[producer_name]
        assert producer["resourcePath"] in combined
        assert producer["apiVersion"] in combined
        assert producer["operation"] in _read(CHALLENGE) or producer["operation"] in combined
    assert "union Resources, InsightResources, SecurityResources, PolicyResources" in combined
    assert "Auto-provisioning settings and settings must not be invented" in combined


def test_guides_enforce_participant_role_scope_and_cleanup_boundaries() -> None:
    """Require narrow participant access and facilitator-only cleanup."""
    combined = _read(CHALLENGE) + _read(SOLUTION)
    for value in (
        "Security Reader",
        "assigned resource group",
        "Owner or Security Admin",
        "facilitator-authorized only",
        "must not disable plans",
        "delete agents/extensions/policies",
        "another participant scope",
    ):
        assert value.casefold() in combined.casefold()
    assert "participants stop after validation" in combined.casefold()


def test_solution_exposes_digest_bound_raw_capture_workflow() -> None:
    """Require hashes, raw envelopes, exact identity, and renderer-only output."""
    solution = _read(SOLUTION)
    for value in (
        "sha256sum",
        "schemaVersion: \"1.1.0\"",
        "containerRegistryRoleAssignments",
        "imageAssessment",
        "securityContext",
        "healthStatus:200",
        "readinessStatus:200",
        '> "$RAW/vm-before.json"',
        '> "$RAW/vm-after.json"',
        "Do not manually create, normalize, patch, or \"fix\"",
        "validator replays",
    ):
        assert value in solution
    assert "passwordSecretRef" in solution
    assert "IMAGE_DIGEST" in solution


def test_guides_reject_fabrication_and_unsupported_attack_path_get() -> None:
    """Reject fabricated findings and unsupported direct attack-path reads."""
    combined = _read(CHALLENGE) + _read(SOLUTION)
    lowered = _normalized(combined).casefold()
    for value in (
        "fabricated findings",
        "never insert free text",
        "direct attack-path get",
        "manually normalized json",
        "do not manually create or edit",
    ):
        assert value in lowered
    direct_get = re.compile(
        r"az rest\s+--method get[^\n]+Microsoft\.Security/attackPaths",
        re.IGNORECASE,
    )
    assert not direct_get.search(combined)
    assert "ATTACK_PATH_RESPONSE=$(az rest --method post" in _read(SOLUTION)
