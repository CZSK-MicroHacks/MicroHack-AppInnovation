############################################
# Networking & Security Resources (HCL body)
############################################

# Public IP for Bastion
resource "azapi_resource" "public_ip" {
  count     = var.enable_public_ip_resources ? 1 : 0
  type      = "Microsoft.Network/publicIPAddresses@2023-04-01"
  name      = local.pip_name
  location  = var.location
  parent_id = azapi_resource.rg.id
  body = {
    sku        = { name = "Standard" }
    properties = { publicIPAllocationMethod = "Static" }
  }
}

# Public IP for NAT Gateway
resource "azapi_resource" "nat_public_ip" {
  count     = var.enable_public_ip_resources ? 1 : 0
  type      = "Microsoft.Network/publicIPAddresses@2023-04-01"
  name      = local.nat_pip_name
  location  = var.location
  parent_id = azapi_resource.rg.id
  body = {
    sku        = { name = "Standard" }
    properties = { publicIPAllocationMethod = "Static" }
  }
}

# NAT Gateway
resource "azapi_resource" "nat_gw" {
  count     = var.enable_public_ip_resources ? 1 : 0
  type      = "Microsoft.Network/natGateways@2023-04-01"
  name      = local.nat_gateway_name
  location  = var.location
  parent_id = azapi_resource.rg.id
  body = {
    sku = { name = "Standard" }
    properties = {
      idleTimeoutInMinutes = 4
      publicIpAddresses    = [{ id = azapi_resource.nat_public_ip[0].id }]
    }
  }
  depends_on = [azapi_resource.nat_public_ip]
}

# Network Security Group
resource "azapi_resource" "nsg" {
  type      = "Microsoft.Network/networkSecurityGroups@2023-04-01"
  name      = local.nsg_name
  location  = var.location
  parent_id = azapi_resource.rg.id
  body = {
    properties = {
      securityRules = [{
        name = "rdp-from-vnet"
        properties = {
          priority                 = 300
          protocol                 = "Tcp"
          access                   = "Allow"
          direction                = "Inbound"
          sourceAddressPrefix      = "VirtualNetwork"
          sourcePortRange          = "*"
          destinationAddressPrefix = "VirtualNetwork"
          destinationPortRange     = "3389"
        }
      }]
    }
  }
}

# Virtual Network with subnets 
resource "azapi_resource" "vnet" {
  type      = "Microsoft.Network/virtualNetworks@2023-04-01"
  name      = local.vnet_name
  location  = var.location
  parent_id = azapi_resource.rg.id
  body = {
    properties = {
      addressSpace = { addressPrefixes = [local.vnet_cidr] }
      subnets = [
        {
          name = local.vms_subnet_name
          properties = merge(
            {
              addressPrefix        = local.vms_subnet_cidr
              networkSecurityGroup = { id = azapi_resource.nsg.id }
            },
            var.enable_public_ip_resources ? { natGateway = { id = azapi_resource.nat_gw[0].id } } : {}
          )
        },
        {
          name = local.bastion_subnet_name
          properties = merge(
            { addressPrefix = local.derived_bastion_cidr },
            var.enable_public_ip_resources ? { natGateway = { id = azapi_resource.nat_gw[0].id } } : {}
          )
        }
      ]
    }
  }
  depends_on = [azapi_resource.nat_gw]
}

resource "azapi_resource" "nic" {
  for_each = local.stacks

  type      = "Microsoft.Network/networkInterfaces@2023-04-01"
  name      = each.value.nic_name
  location  = var.location
  parent_id = azapi_resource.rg.id
  body = {
    properties = {
      ipConfigurations = [{
        name = "ipconfig"
        properties = {
          subnet                    = { id = "${azapi_resource.vnet.id}/subnets/${local.vms_subnet_name}" }
          privateIPAllocationMethod = "Dynamic"
        }
      }]
      networkSecurityGroup        = { id = azapi_resource.nsg.id }
      enableAcceleratedNetworking = false
    }
  }

  # azapi only populates `output` for explicitly exported paths, and the module's
  # private_ip_addresses output reads the allocated address back off the NIC.
  response_export_values = ["properties.ipConfigurations"]
  depends_on             = [azapi_resource.vnet]
}
