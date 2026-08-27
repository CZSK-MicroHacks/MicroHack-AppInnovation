# Bastion Host
resource "azapi_resource" "bastion" {
  count     = var.enable_public_ip_resources ? 1 : 0
  type      = "Microsoft.Network/bastionHosts@2023-04-01"
  name      = local.bastion_name
  location  = var.location
  parent_id = azapi_resource.rg.id
  body = {
    sku = { name = "Basic" }
    properties = {
      ipConfigurations = [{
        name = "bastionIpConfig"
        properties = {
          subnet          = { id = "${azapi_resource.vnet.id}/subnets/${local.bastion_subnet_name}" }
          publicIPAddress = { id = azapi_resource.public_ip[0].id }
        }
      }]
    }
  }
  depends_on = [azapi_resource.vnet, azapi_resource.public_ip]
}

# Developer SKU fallback for subscriptions where public IP creation is blocked.
#
# The Developer SKU attaches straight to the virtual network: it needs no public IP and no
# AzureBastionSubnet, so it is the only Bastion shape that survives a policy which denies
# public IP addresses outright. It is free, and it keeps the challenge 0 instruction
# ("connect through Azure Bastion") true rather than forcing participants onto a different
# access path. Trade-offs versus Basic: one target VM per session, portal HTML5 only (no
# `az network bastion rdp` native client), and no access to peered virtual networks. The
# challenge 0 flow connects to one VM at a time through the portal, so none of those bind.
resource "azapi_resource" "bastion_developer" {
  count     = var.enable_public_ip_resources ? 0 : 1
  type      = "Microsoft.Network/bastionHosts@2024-05-01"
  name      = local.bastion_name
  location  = var.location
  parent_id = azapi_resource.rg.id
  body = {
    sku = { name = "Developer" }
    properties = {
      virtualNetwork = { id = azapi_resource.vnet.id }
    }
  }
  depends_on = [azapi_resource.vnet]
}
