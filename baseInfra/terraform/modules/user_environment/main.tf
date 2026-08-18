data "azurerm_client_config" "current" {}

resource "azapi_resource" "rg" {
  type      = "Microsoft.Resources/resourceGroups@2022-09-01"
  name      = local.rg_name
  location  = var.location
  parent_id = "/subscriptions/${data.azurerm_client_config.current.subscription_id}"
  tags      = { SecurityControl = "ignore" }
  body      = {}

  lifecycle {
    precondition {
      condition     = var.capacity_preflight_confirmed
      error_message = "Run preflight-capacity.ps1 for the exact deployment inputs, then set capacity_preflight_confirmed=true."
    }
  }
}
