locals {
  padded                  = format("%03d", var.user_index)
  rg_name                 = "rg-user${local.padded}"
  pip_name                = "pip-user${local.padded}"
  nat_pip_name            = "pip-nat-user${local.padded}"
  vnet_name               = "vnet-user${local.padded}"
  vms_subnet_name         = "vms"
  bastion_subnet_name     = "AzureBastionSubnet"
  nsg_name                = "nsg-user${local.padded}"
  nat_gateway_name        = "nat-user${local.padded}"
  bastion_name            = "bastion-user${local.padded}"
  derived_vnet_cidr       = "10.${var.user_index}.0.0/22"
  vnet_cidr               = local.derived_vnet_cidr
  derived_vms_subnet_cidr = "10.${var.user_index}.0.0/24"
  derived_bastion_cidr    = "10.${var.user_index}.1.0/26"
  vms_subnet_cidr         = local.derived_vms_subnet_cidr
  source_archive_url      = "https://github.com/CZSK-MicroHacks/MicroHack-AppInnovation/archive/${var.source_commit}.zip"
  provisioner_path        = "${path.module}/../../../scripts/provision-vm.ps1"
  provisioner_sha256      = filesha256(local.provisioner_path)
  stacks = {
    dotnet = {
      vm_name       = "vm-dotnet-user${local.padded}"
      computer_name = "dotnet-u${local.padded}"
      nic_name      = "nic-dotnet-user${local.padded}"
    }
    java = {
      vm_name       = "vm-java-user${local.padded}"
      computer_name = "java-u${local.padded}"
      nic_name      = "nic-java-user${local.padded}"
    }
  }
}
