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
  bootstrapper_path       = "${path.module}/../../../scripts/bootstrap-provision-vm.ps1"
  provisioner_sha256 = sha256(join(":", [
    filesha256(local.provisioner_path),
    filesha256(local.bootstrapper_path),
    "custom-data-v2",
    "gzip-bootstrap-v1"
  ]))
  provisioner_custom_data = {
    for stack in keys(local.stacks) : stack => base64encode(join("\n", [
      "MICROHACK_CUSTOM_DATA_V2",
      base64encode(jsonencode({
        databasePassword  = random_password.database[stack].result
        performanceApiKey = random_password.performance_api_key[stack].result
      })),
      "MICROHACK_PROVISIONER_START",
      file(local.provisioner_path)
    ]))
  }
  bootstrapper_gzip_base64 = base64gzip(file(local.bootstrapper_path))
  provisioner_bootstrap_wrapper = {
    for stack in keys(local.stacks) : stack => join("\n", [
      "$ErrorActionPreference='Stop'",
      "$b=[Convert]::FromBase64String('${local.bootstrapper_gzip_base64}')",
      "$m=New-Object IO.MemoryStream(,$b)",
      "$g=New-Object IO.Compression.GZipStream($m,[IO.Compression.CompressionMode]::Decompress)",
      "$r=New-Object IO.StreamReader($g)",
      "try{$s=$r.ReadToEnd()}finally{$r.Dispose();$g.Dispose();$m.Dispose()}",
      ". ([ScriptBlock]::Create($s))",
      "Invoke-ProvisioningBootstrap -Stack '${stack}' -SourceCommit '${var.source_commit}' -SourceArchiveSha256 '${var.source_archive_sha256}'"
    ])
  }
  provisioner_command_to_execute = {
    for stack in keys(local.stacks) : stack => join(" ", [
      "powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand",
      textencodebase64(local.provisioner_bootstrap_wrapper[stack], "UTF-16LE")
    ])
  }
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
