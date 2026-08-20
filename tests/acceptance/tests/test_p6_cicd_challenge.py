"""Executable ownership and frozen-input checks for Challenge 3."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_cicd_challenge_consumes_the_frozen_registry() -> None:
    """Keep workflow implementation anchored to exact files and least privilege."""
    registry = json.loads(
        (ROOT / "workshop/contracts/shared-challenges.json").read_text(
            encoding="utf-8"
        )
    )
    challenge = next(
        item for item in registry["challenges"] if item["id"] == "cicd-revisions"
    )

    assert challenge["artifacts"] == [
        ".github/workflows/catalog-dotnet.yml",
        ".github/workflows/catalog-java.yml",
        "infra/github-cicd.bicep",
        "tests/acceptance/tests/test_p6_cicd_challenge.py",
    ]
    assert "catalog-validate-challenge-evidence cicd" in challenge[
        "evidenceValidationCommand"
    ]
    assert registry["cicdIdentity"]["roles"] == [
        {
            "name": "AcrPush",
            "roleDefinitionId": "8311e382-0749-4cb8-b61a-304f252e45ec",
            "scope": "registry",
        },
        {
            "name": "Container Apps Contributor",
            "roleDefinitionId": "358470bc-b998-42bd-ab17-a7e34c199c0f",
            "scope": "container-app",
        },
    ]
