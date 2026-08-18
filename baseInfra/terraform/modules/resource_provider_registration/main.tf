resource "azurerm_resource_provider_registration" "providers" {
  for_each = toset(local.resource_providers)

  name = each.value

  lifecycle {
    prevent_destroy = true
  }
}
