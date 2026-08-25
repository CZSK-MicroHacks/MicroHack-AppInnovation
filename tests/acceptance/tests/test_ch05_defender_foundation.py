"""Static acceptance tests for the Defender Terraform foundation."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


SECURITY_READER_ROLE_ID = "39bc4728-0917-49c7-9d2c-d95423bc2eb4"


def _load_json(path: Path) -> dict[str, Any]:
    """Load one checked-in JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _variable_body(source: str, name: str) -> str:
    """Return enough of one Terraform variable block for static assertions."""
    match = re.search(
        rf'variable "{re.escape(name)}" \{{(?P<body>.*?)(?=\nvariable "|\Z)',
        source,
        re.DOTALL,
    )
    assert match is not None, f"missing Terraform variable {name}"
    return match.group("body")


def test_pricings_consume_the_exact_frozen_contract(repo_root: Path) -> None:
    """Terraform consumes all and only the five frozen pricing definitions."""
    contract = _load_json(repo_root / "workshop/contracts/defender.json")
    defender = (repo_root / "baseInfra/terraform/defender.tf").read_text(
        encoding="utf-8"
    )
    pricings = contract["foundation"]["requiredPricings"]

    assert contract["schemaVersion"] == "1.1.0"
    assert pricings == [
        {
            "name": "CloudPosture",
            "pricingTier": "Standard",
            "extensions": [
                {
                    "name": "ContainerRegistriesVulnerabilityAssessments",
                    "isEnabled": "True",
                }
            ],
        },
        {"name": "Containers", "pricingTier": "Standard", "extensions": []},
        {"name": "SqlServers", "pricingTier": "Standard", "extensions": []},
        {
            "name": "OpenSourceRelationalDatabases",
            "pricingTier": "Standard",
            "extensions": [],
        },
        {
            "name": "VirtualMachines",
            "pricingTier": "Standard",
            "subPlan": "P2",
            "enforce": "True",
            "extensions": [],
        },
    ]
    assert (
        'jsondecode(file("${path.module}/../../workshop/contracts/defender.json"))'
        in defender
    )
    assert (
        "for pricing in local.defender_foundation.requiredPricings : "
        "pricing.name => pricing"
    ) in defender
    assert 'type      = "Microsoft.Security/pricings@2024-01-01"' in defender
    assert "pricingTier = local.defender_pricings[each.value].pricingTier" in defender
    assert "extensions  = local.defender_pricings[each.value].extensions" in defender
    assert "subPlan = local.defender_pricings[each.value].subPlan" in defender
    assert "enforce = local.defender_pricings[each.value].enforce" in defender


def test_budget_consumes_frozen_shape_and_requires_explicit_inputs(
    repo_root: Path,
) -> None:
    """The one budget uses the frozen API and bounded cost notification."""
    contract = _load_json(repo_root / "workshop/contracts/defender.json")
    defender = (repo_root / "baseInfra/terraform/defender.tf").read_text(
        encoding="utf-8"
    )
    variables = (repo_root / "baseInfra/terraform/variables.tf").read_text(
        encoding="utf-8"
    )
    budget = contract["foundation"]["budget"]

    assert budget == {
        "scope": "handoff-subscription",
        "apiVersion": "2023-11-01",
        "category": "Cost",
        "timeGrain": "Monthly",
        "maximumNotificationThreshold": 80,
        "notificationTargetRequired": True,
    }
    assert (
        'type      = "Microsoft.Consumption/budgets@'
        '${local.defender_foundation.budget.apiVersion}"'
    ) in defender
    assert "count = var.enable_defender_foundation ? 1 : 0" in defender
    assert "category  = local.defender_foundation.budget.category" in defender
    assert "timeGrain = local.defender_foundation.budget.timeGrain" in defender
    assert (
        "threshold     = "
        "local.defender_foundation.budget.maximumNotificationThreshold"
    ) in defender
    assert "amount    = var.defender_budget_amount" in defender
    assert "startDate = var.defender_budget_start_date" in defender
    assert "endDate   = var.defender_budget_end_date" in defender
    assert (
        "contactEmails = "
        "sort(tolist(var.defender_budget_notification_emails))"
    ) in defender
    assert "contactRoles  = [\"Owner\"]" in defender

    assert "default     = 0" in _variable_body(
        variables, "defender_budget_amount"
    )
    assert 'default     = ""' in _variable_body(
        variables, "defender_budget_start_date"
    )
    assert 'default     = ""' in _variable_body(
        variables, "defender_budget_end_date"
    )
    assert "default     = []" in _variable_body(
        variables, "defender_budget_notification_emails"
    )
    start_date = _variable_body(variables, "defender_budget_start_date")
    assert "^[0-9]{4}-(0[1-9]|1[0-2])-01T00:00:00Z$" in start_date
    assert '"2017-06-01T00:00:00Z"' in start_date
    assert start_date.count('formatdate("YYYY", plantimestamp())') == 2
    assert start_date.count('formatdate("MM", plantimestamp())') == 2
    assert ") >= 0" in start_date
    assert ") <= 12" in start_date
    assert (
        "depends_on = [module.resource_providers, "
        "azapi_resource.defender_budget]"
    ) in defender


def test_subscription_pricings_are_protected_from_unsupported_delete(
    repo_root: Path,
) -> None:
    """Terraform never deletes subscription pricing resources during teardown."""
    defender = (repo_root / "baseInfra/terraform/defender.tf").read_text(
        encoding="utf-8"
    )
    readme = (repo_root / "baseInfra/terraform/README.md").read_text(
        encoding="utf-8"
    )

    pricing = re.search(
        r'resource "azapi_resource" "defender_pricing" \{(?P<body>.*?)'
        r'\nresource "azapi_resource" "defender_budget"',
        defender,
        re.DOTALL,
    )
    assert pricing is not None
    assert "prevent_destroy = true" in pricing.group("body")
    assert "Valid only for resource scope" in readme
    assert "terraform state rm 'azapi_resource.defender_pricing'" in readme


def test_paid_foundation_is_default_off_and_double_authorized(
    repo_root: Path,
) -> None:
    """Paid resources require opt-in plus explicit facilitator authorization."""
    contract = _load_json(repo_root / "workshop/contracts/defender.json")
    defender = (repo_root / "baseInfra/terraform/defender.tf").read_text(
        encoding="utf-8"
    )
    variables = (repo_root / "baseInfra/terraform/variables.tf").read_text(
        encoding="utf-8"
    )

    assert contract["foundation"]["requiresFacilitatorAuthorization"] is True
    for name in (
        "enable_defender_foundation",
        "defender_facilitator_authorized",
    ):
        assert "default     = false" in _variable_body(variables, name)
    assert (
        "!var.enable_defender_foundation || "
        "var.defender_facilitator_authorized"
    ) in _variable_body(variables, "defender_facilitator_authorized")
    assert (
        "for_each = var.enable_defender_foundation ? "
        "toset(keys(local.defender_pricings)) : toset([])"
    ) in defender
    assert defender.count(
        "var.defender_facilitator_authorized && "
        "local.defender_foundation.requiresFacilitatorAuthorization"
    ) == 2


def test_participants_receive_security_reader_only_on_assigned_rg(
    repo_root: Path,
) -> None:
    """Security Reader is deterministic and scoped to each participant RG."""
    defender = (repo_root / "baseInfra/terraform/defender.tf").read_text(
        encoding="utf-8"
    )
    module_outputs = (
        repo_root / "baseInfra/terraform/modules/user_environment/outputs.tf"
    ).read_text(encoding="utf-8")
    existing_rbac = (
        repo_root / "baseInfra/terraform/modules/user_environment/rbac.tf"
    ).read_text(encoding="utf-8")

    assert SECURITY_READER_ROLE_ID in defender
    assert (
        "for_each = var.manage_entra_users && var.manage_azure_resources ? "
        "module.user_environment : {}"
    ) in defender
    assert (
        'name      = uuidv5(local.security_reader_assignment_namespace, '
        '"${each.value.resource_group_id}/'
        '${module.entra_users[each.key].object_id}")'
    ) in defender
    assert "parent_id = each.value.resource_group_id" in defender
    assert "principalId      = module.entra_users[each.key].object_id" in defender
    assert "output \"resource_group_id\"" in module_outputs
    assert "value = azapi_resource.rg.id" in module_outputs

    assert "8e3af657-a8ff-443c-a75c-2fe8c4bcb635" in existing_rbac
    assert "rg_owner_role_assignment" in existing_rbac


def test_foundation_omits_unsupported_and_generalized_machinery(
    repo_root: Path,
) -> None:
    """The Terraform slice adds no portal switch, agents, policies, or rollback."""
    terraform = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((repo_root / "baseInfra/terraform").glob("defender*.tf"))
    ).lower()

    forbidden = (
        "serverless containers",
        "serverlesscontainers",
        "datacollectionrule",
        "datacollectionruleassociation",
        "policyassignment",
        "autoprovisioningsetting",
        "virtualmachines/extensions",
        "hybridcompute/machines/extensions",
        "rollback",
        "terraform destroy",
    )
    for value in forbidden:
        assert value not in terraform
