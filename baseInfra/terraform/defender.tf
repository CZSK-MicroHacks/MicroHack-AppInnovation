locals {
  subscription_resource_id             = "/subscriptions/${var.subscription_id}"
  defender_contract                    = jsondecode(file("${path.module}/../../workshop/contracts/defender.json"))
  defender_foundation                  = local.defender_contract.foundation
  defender_pricings                    = { for pricing in local.defender_foundation.requiredPricings : pricing.name => pricing }
  security_reader_role_definition_id   = "${local.subscription_resource_id}/providers/Microsoft.Authorization/roleDefinitions/39bc4728-0917-49c7-9d2c-d95423bc2eb4"
  security_reader_assignment_namespace = "39bc4728-0917-49c7-9d2c-d95423bc2eb4"
}

resource "azapi_resource" "defender_pricing" {
  for_each = var.enable_defender_foundation ? toset(keys(local.defender_pricings)) : toset([])

  type      = "Microsoft.Security/pricings@2024-01-01"
  name      = each.value
  parent_id = local.subscription_resource_id
  body = {
    properties = merge(
      {
        pricingTier = local.defender_pricings[each.value].pricingTier
        extensions  = local.defender_pricings[each.value].extensions
      },
      try(local.defender_pricings[each.value].subPlan, null) == null ? {} : {
        subPlan = local.defender_pricings[each.value].subPlan
      },
      try(local.defender_pricings[each.value].enforce, null) == null ? {} : {
        enforce = local.defender_pricings[each.value].enforce
      }
    )
  }

  lifecycle {
    precondition {
      condition     = var.defender_facilitator_authorized && local.defender_foundation.requiresFacilitatorAuthorization
      error_message = "Defender paid plans require explicit facilitator authorization."
    }
  }

  depends_on = [module.resource_providers]
}

resource "azapi_resource" "defender_budget" {
  count = var.enable_defender_foundation ? 1 : 0

  type      = "Microsoft.Consumption/budgets@${local.defender_foundation.budget.apiVersion}"
  name      = var.defender_budget_name
  parent_id = local.subscription_resource_id
  body = {
    properties = {
      amount    = var.defender_budget_amount
      category  = local.defender_foundation.budget.category
      timeGrain = local.defender_foundation.budget.timeGrain
      timePeriod = {
        startDate = var.defender_budget_start_date
        endDate   = var.defender_budget_end_date
      }
      notifications = {
        Actual_GreaterThan_80_Percent = {
          enabled       = true
          operator      = "GreaterThan"
          threshold     = local.defender_foundation.budget.maximumNotificationThreshold
          thresholdType = "Actual"
          contactEmails = sort(tolist(var.defender_budget_notification_emails))
          contactGroups = []
          contactRoles  = ["Owner"]
        }
      }
    }
  }

  lifecycle {
    precondition {
      condition     = var.defender_facilitator_authorized && local.defender_foundation.requiresFacilitatorAuthorization
      error_message = "The Defender subscription budget requires explicit facilitator authorization."
    }
  }

  depends_on = [module.resource_providers]
}

resource "azapi_resource" "participant_security_reader" {
  for_each = var.manage_entra_users && var.manage_azure_resources ? module.user_environment : {}

  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = uuidv5(local.security_reader_assignment_namespace, "${each.value.resource_group_id}/${module.entra_users[each.key].object_id}")
  parent_id = each.value.resource_group_id
  body = {
    properties = {
      roleDefinitionId = local.security_reader_role_definition_id
      principalId      = module.entra_users[each.key].object_id
      principalType    = "User"
    }
  }
}
