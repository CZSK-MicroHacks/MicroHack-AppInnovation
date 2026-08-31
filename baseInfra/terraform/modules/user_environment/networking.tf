############################################
# Networking & Security Resources (HCL body)
############################################

# One public IP per legacy VM.
#
# The workshop deliberately models a pre-cloud deployment: a single VM hosting the frontend,
# the API, the database and the image files. The address exists so participants can RDP into
# the VM and work there; the catalog itself is browsed at localhost *inside* the VM, which is
# part of the point — the application is bound to one machine and being on that machine is
# the only way to reach it.
resource "azapi_resource" "vm_public_ip" {
  for_each = local.stacks

  type      = "Microsoft.Network/publicIPAddresses@2023-04-01"
  name      = each.value.pip_name
  location  = var.location
  parent_id = azapi_resource.rg.id
  body = {
    sku = { name = "Standard" }
    properties = {
      publicIPAllocationMethod = "Static"
    }
  }

  response_export_values = ["properties.ipAddress"]
}

# Network Security Group
#
# This is a content workshop, not a security workshop, and the environment is created
# immediately before a delivery and destroyed after it with no private data in it. The rules
# below are intentionally open so that nothing about reachability can block a participant.
resource "azapi_resource" "nsg" {
  type      = "Microsoft.Network/networkSecurityGroups@2023-04-01"
  name      = local.nsg_name
  location  = var.location
  parent_id = azapi_resource.rg.id
  body = {
    properties = {
      securityRules = [
        {
          name = "rdp"
          properties = {
            priority                 = 300
            protocol                 = "Tcp"
            access                   = "Allow"
            direction                = "Inbound"
            sourceAddressPrefix      = "Internet"
            sourcePortRange          = "*"
            destinationAddressPrefix = "*"
            destinationPortRange     = "3389"
          }
        }
      ]
    }
  }
}

# Virtual Network with a single VM subnet.
#
# There is no AzureBastionSubnet: access is direct over the public IP above, so Bastion and
# the NAT Gateway it depended on are not deployed at all. Outbound traffic uses the public IP
# attached to each NIC, which is an explicit outbound path and therefore unaffected by the
# retirement of Azure default outbound access.
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
          properties = {
            addressPrefix        = local.vms_subnet_cidr
            networkSecurityGroup = { id = azapi_resource.nsg.id }
          }
        }
      ]
    }
  }
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
          publicIPAddress           = { id = azapi_resource.vm_public_ip[each.key].id }
        }
      }]
      networkSecurityGroup        = { id = azapi_resource.nsg.id }
      enableAcceleratedNetworking = false
    }
  }

  # azapi only populates `output` for explicitly exported paths, and the module's
  # private_ip_addresses output reads the allocated address back off the NIC.
  response_export_values = ["properties.ipConfigurations"]
  depends_on             = [azapi_resource.vnet, azapi_resource.vm_public_ip]
}
