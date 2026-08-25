"""Executable checks for the bounded Challenge 3 CI/CD implementation."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

from catalog_acceptance import shared_challenges


ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = {
    "dotnet-sqlserver": ROOT / ".github/workflows/catalog-dotnet.yml",
    "java-postgresql": ROOT / ".github/workflows/catalog-java.yml",
}
REMOTE_ACTION = re.compile(r"uses:\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@(\S+)")


def _read(path: Path) -> str:
    """Read one repository asset as UTF-8 text."""
    return path.read_text(encoding="utf-8")


def _squash(value: str) -> str:
    """Collapse whitespace for exact multiline command assertions."""
    return " ".join(value.replace("\\\n", " ").split())


def test_cicd_assets_follow_the_frozen_registry() -> None:
    """Keep owned paths, stack mapping, roles, protocol, and output frozen."""
    registry = json.loads(
        _read(ROOT / "workshop/contracts/shared-challenges.json")
    )
    challenge = next(
        item for item in registry["challenges"] if item["id"] == "cicd-revisions"
    )

    assert registry["schemaVersion"] == "1.2.0"
    assert challenge["artifacts"] == [
        ".github/workflows/catalog-dotnet.yml",
        ".github/workflows/catalog-java.yml",
        "infra/github-cicd.bicep",
        "tests/acceptance/tests/test_ch03_cicd_challenge.py",
    ]
    assert challenge["evidenceOutput"] == "evidence/cicd-report.json"
    assert registry["cicdProtocol"] == {
        "evidenceVersion": "1.1.0",
        "trigger": "workflow_dispatch",
        "workflowHead": "control-commit",
        "handoffCheckout": "workflow-head",
        "applicationCheckout": "handoff-source-commit",
        "sourceIdentity": "handoff.source.commitSha",
        "roleAudit": {
            "executionBoundary": "facilitator-session",
            "requiredPermission": "Microsoft.Authorization/roleAssignments/read",
            "minimumBuiltInRole": "Reader",
            "command": (
                "az role assignment list --all --include-inherited "
                "--assignee-object-id <principal-id> "
                "--fill-principal-name false "
                "--fill-role-definition-name false --output json"
            ),
        },
        "approvalOrdering": [
            "staging-complete",
            "production-approved",
            "production-started",
            "promotion",
            "rollback",
        ],
        "revisionStateSource": "azure-container-app-revision-list",
        "rollbackGuard": "shell-trap",
    }


def test_workflows_are_manual_stack_specific_and_immutable() -> None:
    """Require two dispatch-only stack workflows with pinned toolchains/actions."""
    dotnet = _read(WORKFLOWS["dotnet-sqlserver"])
    java = _read(WORKFLOWS["java-postgresql"])

    for stack, workflow in WORKFLOWS.items():
        content = _read(workflow)
        assert content.startswith(f"name: Catalog {'Java' if stack.startswith('java') else '.NET'} CI/CD")
        assert re.search(r"^on:\n  workflow_dispatch:\n", content, re.M)
        assert not re.search(r"^\s{2}(push|pull_request|workflow_call|schedule):", content, re.M)
        assert "jobs:\n  staging:" in content
        assert "\n  production:" in content
        assert "needs: staging" in content
        assert content.count("environment: staging") == 1
        assert content.count("environment: production") == 1

    assert "EXPECTED_STACK: dotnet-sqlserver" in dotnet
    assert "IMAGE_REPOSITORY: catalog-dotnet" in dotnet
    # Both SDKs, each exactly pinned. The handoff contract does not pin a target
    # framework, so participants arrive on net8.0 (manual, copilot-rewrite) or
    # net10.0 (copilot-modernization) and dotnet test needs the matching runtime.
    assert "8.0.424" in dotnet
    assert "10.0.400" in dotnet
    assert "application-source/dotnet/LegoCatalog.sln" in dotnet
    assert "application-source/dotnet/Dockerfile" in dotnet
    assert "EXPECTED_STACK: java-postgresql" in java
    assert "IMAGE_REPOSITORY: catalog-java" in java
    assert "java-version: 21.0.12" in java
    assert "./mvnw --batch-mode --no-transfer-progress test" in java
    assert "application-source/java/Dockerfile" in java

    matches = REMOTE_ACTION.findall(dotnet + "\n" + java)
    assert matches
    assert all(re.fullmatch(r"[0-9a-f]{40}", revision) for _, revision in matches)
    assert not re.search(r"uses:\s+\S+@(?:main|master|v\d)", dotnet + "\n" + java)


def test_workflow_permissions_and_authentication_are_minimal() -> None:
    """Reject broad GitHub permissions, client secrets, and registry admin."""
    for workflow in WORKFLOWS.values():
        content = _read(workflow)
        assert re.search(
            r"^permissions:\n  contents: read\n  id-token: write\n", content, re.M
        )
        assert content.count("uses: azure/login@") == 2
        assert "${{ vars.AZURE_CLIENT_ID }}" in content
        assert "${{ vars.AZURE_TENANT_ID }}" in content
        assert "${{ vars.AZURE_SUBSCRIPTION_ID }}" in content
        assert "secrets." not in content
        assert "client-secret" not in content.casefold()
        assert "admin-enabled" not in content.casefold()
        assert "az role assignment" not in content


def test_control_handoff_and_application_source_are_separate() -> None:
    """Bind the control handoff hash before the exact application checkout."""
    for workflow in WORKFLOWS.values():
        content = _read(workflow)
        control = content.index("Check out the workflow control commit")
        digest = content.index('HANDOFF_SHA256="$(sha256sum "$HANDOFF_FILE"')
        distinct = content.index('test "$GITHUB_SHA" != "$SOURCE_COMMIT"')
        ancestry = content.index(
            'git merge-base --is-ancestor "$SOURCE_COMMIT" "$GITHUB_SHA"'
        )
        source = content.index("Check out the exact application source")
        build = content.index("docker build")
        assert control < digest < distinct < ancestry < source < build
        assert "ref: ${{ steps.handoff.outputs.source_commit }}" in content
        assert "path: application-source" in content
        assert (
            'test "$(git -C application-source rev-parse HEAD)" = '
            '"$(jq -er \'.sourceCommit\' evidence/cicd/context.json)"'
        ) in content
        assert "headSha: $c.controlCommit" in content
        assert "sourceCommit: $c.sourceCommit" in content
        assert 'event == "workflow_dispatch"' in content


def test_image_candidate_and_label_derive_only_from_source_sha() -> None:
    """Require the full source tag, resolved digest, candidate suffix, and label FQDN."""
    for workflow in WORKFLOWS.values():
        content = _read(workflow)
        required = (
            'TAGGED_IMAGE="${REGISTRY_LOGIN_SERVER}/${REPOSITORY}:${SOURCE_COMMIT}"',
            "az acr manifest show-metadata",
            'select(test("^sha256:[0-9a-f]{64}$"))',
            'IMAGE_REFERENCE="${REGISTRY_LOGIN_SERVER}/${REPOSITORY}@${DIGEST}"',
            'CANDIDATE_REVISION="${CONTAINER_APP_NAME}--ci-${SOURCE_COMMIT:0:12}"',
            'CANDIDATE_URL="https://${CONTAINER_APP_NAME}---candidate.${ENVIRONMENT_SUFFIX}"',
            '--image "$IMAGE_REFERENCE"',
            '--revision-suffix "ci-$(jq -er \'.sourceCommit[0:12]\' "$CONTEXT")"',
            "--mode multiple",
            "--label candidate",
        )
        assert all(item in content for item in required)
        assert content.index("docker push") < content.index(
            "az acr manifest show-metadata"
        )
        assert content.index("az acr manifest show-metadata") < content.index(
            "az containerapp revision copy"
        )


def test_raw_revision_state_drives_all_normalized_observations() -> None:
    """Hash three raw revision lists and derive state instead of hardcoding it."""
    for workflow in WORKFLOWS.values():
        content = _read(workflow)
        for phase in ("before", "promotion", "rollback"):
            raw = f"evidence/cicd/{phase}-revisions.raw.json"
            assert raw in content
            assert f'rawResultFile: "evidence/cicd/{phase}-revisions.raw.json"' in content
        assert content.count("az containerapp revision list") >= 3
        assert "sha256sum evidence/cicd/before-revisions.raw.json" in content
        assert "sha256sum evidence/cicd/promotion-revisions.raw.json" in content
        assert "sha256sum evidence/cicd/rollback-revisions.raw.json" in content
        for field in (
            "previousWeight: $previous.properties.trafficWeight",
            "candidateWeight: $candidate.properties.trafficWeight",
            "previousActive: $previous.properties.active",
            "candidateActive: $candidate.properties.active",
            "previousHealthState: $previous.properties.healthState",
            "candidateHealthState: $candidate.properties.healthState",
        ):
            assert field in content
        assert "source: \"azure-container-app-revision-list\"" in content


def test_probes_approval_promotion_and_rollback_fail_closed() -> None:
    """Require staging smoke, protected production, and a pre-promotion trap."""
    for workflow in WORKFLOWS.values():
        content = _read(workflow)
        staging = content.index("jobs:\n  staging:")
        smoke = content.index('probe_exact_200 "$CANDIDATE_URL"', staging)
        production = content.index("\n  production:")
        approval_gate = content.index("environment: production", production)
        guard = content.index("trap rollback EXIT", production)
        promotion = content.index(
            '"${PREVIOUS_REVISION}=0" "${CANDIDATE_REVISION}=100"', guard
        )
        rollback = content.index("\n          rollback\n          trap - EXIT", promotion)
        assert staging < smoke < production <= approval_gate < guard < promotion < rollback
        for url in (
            'probe_exact_200 "$CANDIDATE_URL"',
            'probe_exact_200 "${CANDIDATE_URL}/healthz"',
            'probe_exact_200 "${CANDIDATE_URL}/readyz"',
            'probe_exact_200 "$APPLICATION_URL"',
            'probe_exact_200 "$HEALTH_URL"',
            'probe_exact_200 "$READINESS_URL"',
        ):
            assert url in content
        assert "executesOnFailure: true" in content
        assert "promotionSucceeded: true" in content
        assert "rollbackSucceeded: true" in content


def test_bicep_creates_only_frozen_oidc_and_resource_roles() -> None:
    """Constrain Bicep to one UAMI, two subjects, and two exact assignments."""
    content = _read(ROOT / "infra/github-cicd.bicep")
    declarations = re.findall(
        r"resource\s+\w+\s+'([^']+)'(\s+existing)?\s*=", content
    )
    created_types = [
        resource_type.split("@", maxsplit=1)[0]
        for resource_type, existing in declarations
        if not existing
    ]
    assert created_types.count(
        "Microsoft.ManagedIdentity/userAssignedIdentities"
    ) == 1
    assert created_types.count(
        "Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials"
    ) == 2
    assert created_types.count("Microsoft.Authorization/roleAssignments") == 2
    assert set(created_types) == {
        "Microsoft.ManagedIdentity/userAssignedIdentities",
        "Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials",
        "Microsoft.Authorization/roleAssignments",
    }
    assert "repo:${githubRepository}:environment:staging" in content
    assert "repo:${githubRepository}:environment:production" in content
    assert "scope: registry" in content
    assert "scope: containerApp" in content
    assert "resourcesShareDeploymentSubscription" in content
    assert "8311e382-0749-4cb8-b61a-304f252e45ec" in content
    assert "358470bc-b998-42bd-ab17-a7e34c199c0f" in content
    assert "8e3af657-a8ff-443c-a75c-2fe8c4bcb635" not in content
    assert "b24988ac-6180-42a0-ab88-20f7382dd24c" not in content


def test_facilitator_guide_uses_exact_external_rbac_boundary() -> None:
    """Keep RBAC evidence external, complete, unscoped, hashed, and fail-closed."""
    challenge = _read(ROOT / "challenges/ch03/README.md")
    solution = _read(ROOT / "solutions/ch03/README.md")
    normalized = _squash(solution)
    exact_command = (
        'az role assignment list --all --include-inherited '
        '--assignee-object-id "$PRINCIPAL_ID" '
        "--fill-principal-name false --fill-role-definition-name false "
        "--output json > evidence/cicd/role-assignments.raw.json"
    )

    assert "facilitator-session" in solution
    assert "Microsoft.Authorization/roleAssignments/read" in solution
    assert "Reader-equivalent" in solution
    assert 'az account set --subscription "$SUBSCRIPTION_ID"' in solution
    assert exact_command in normalized
    command_block = normalized.split("az role assignment list", maxsplit=1)[1].split(
        "role-assignments.raw.json", maxsplit=1
    )[0]
    assert "--scope" not in command_block
    assert "--query" not in command_block
    assert "sha256sum evidence/cicd/role-assignments.raw.json" in solution
    assert "length == 2" in solution
    assert "split(\"/\") | last" in solution
    assert "full ARM `roleDefinitionId`" in challenge + solution


def test_guides_require_post_completion_attempt_bound_validation() -> None:
    """Require final GitHub/RBAC capture and common CLI only after success."""
    challenge = _read(ROOT / "challenges/ch03/README.md")
    solution = _read(ROOT / "solutions/ch03/README.md")
    combined = challenge + "\n" + solution
    for token in (
        "evidence/cicd-report.json",
        "evidence/cicd/workflow-run.json",
        "evidence/cicd/approval.json",
        "evidence/cicd/identity.json",
        "evidence/cicd/report-fragment.json",
        "catalog-validate-challenge-evidence cicd",
        "evidence/modernization-contract.json",
        "--contracts workshop/contracts",
        "RUN_ATTEMPT",
        "jobId",
        "started_at < .completed_at",
        '.status == "completed"',
        '.conclusion == "success"',
        "staging.completedAt <= approval.approvedAt <= production.startedAt",
    ):
        assert token in combined
    assert "Never use a production job that is still\nrunning" in solution
    assert solution.index('and .status == "completed"') < solution.index(
        "> evidence/cicd/workflow-run.json"
    )
    assert solution.index("> evidence/cicd/workflow-run.json") < solution.index(
        "> evidence/cicd-report.json"
    )
    assert "structure only and is never behavioral proof" in challenge


def test_owned_slice_executes_common_validator_integration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Run the shared validator against its complete CI/CD fixture bundle."""
    contracts_test_path = ROOT / "tests/acceptance/tests/test_challenge_contracts.py"
    spec = importlib.util.spec_from_file_location(
        "_p6_contract_fixture_builder", contracts_test_path
    )
    assert spec is not None and spec.loader is not None
    contract_tests = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract_tests)
    package_root, evidence_path, evidence, handoff, _ = (
        contract_tests._prepare_validator_bundle("cicd", tmp_path, ROOT)
    )
    monkeypatch.setattr(
        shared_challenges,
        "validate_handoff",
        lambda *_: handoff,
    )

    assert (
        shared_challenges.validate_shared_challenge_evidence(
            "cicd",
            evidence_path,
            package_root / "evidence/modernization-contract.json",
            ROOT / "workshop/contracts",
            package_root,
        )
        == evidence
    )
