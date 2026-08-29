locals {
  padded                  = format("%03d", var.user_index)
  rg_name                 = "rg-user${local.padded}"
  team_name               = "user${local.padded}"
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
    "gzip-bootstrap-v1",
    "gzip-provisioner-v1"
  ]))
  # infra/main.bicep needs the exact ARM ID of each stack's legacy VM. It is composed from
  # the resource group rather than read from azapi_resource.vm, because it travels in that
  # same VM's custom data and a resource cannot reference itself.
  source_vm_resource_ids = {
    for stack, config in local.stacks :
    stack => "${azapi_resource.rg.id}/providers/Microsoft.Compute/virtualMachines/${config.vm_name}"
  }
  provisioner_payload = {
    for stack in keys(local.stacks) : stack => {
      databasePassword                        = random_password.database[stack].result
      performanceApiKey                       = random_password.performance_api_key[stack].result
      facilitatorPrincipalName                = var.facilitator_principal_name
      facilitatorPrincipalObjectId            = var.facilitator_principal_object_id
      resourceGroupName                       = local.rg_name
      teamName                                = local.team_name
      adminUsername                           = var.admin_username
      migrationSourceVirtualNetworkResourceId = azapi_resource.vnet.id
      migrationSourceVmResourceId             = local.source_vm_resource_ids[stack]
    }
  }
  # Azure decodes osProfile.customData into a binary array of at most 65,535 bytes and the
  # provisioner alone is larger than that, so it travels gzipped. bootstrap-provision-vm.ps1
  # still finds plain PowerShell between the markers: this wrapper takes the same four
  # parameters, expands the real script to disk, and runs it from there, which keeps
  # $PSCommandPath pointing at a real file. Compressing this way mirrors how the bootstrapper
  # itself is already shipped through the extension command.
  provisioner_body_path = "C:\\AzureData\\provision-vm-body.ps1"
  provisioner_wrapper = join("\n", [
    "param(",
    "    [Parameter(Mandatory)][ValidateSet('dotnet', 'java')][string]$Stack,",
    "    [Parameter(Mandatory)][string]$SourceCommit,",
    "    [Parameter(Mandatory)][string]$SourceArchiveUrl,",
    "    [Parameter(Mandatory)][string]$SourceArchiveSha256",
    ")",
    "$ErrorActionPreference='Stop'",
    "$b=[Convert]::FromBase64String('${base64gzip(file(local.provisioner_path))}')",
    "$m=New-Object IO.MemoryStream(,$b)",
    "$g=New-Object IO.Compression.GZipStream($m,[IO.Compression.CompressionMode]::Decompress)",
    "$r=New-Object IO.StreamReader($g)",
    "try{$s=$r.ReadToEnd()}finally{$r.Dispose();$g.Dispose();$m.Dispose()}",
    "[IO.File]::WriteAllText('${local.provisioner_body_path}',$s,(New-Object Text.UTF8Encoding($false)))",
    "& powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File '${local.provisioner_body_path}' -Stack $Stack -SourceCommit $SourceCommit -SourceArchiveUrl $SourceArchiveUrl -SourceArchiveSha256 $SourceArchiveSha256",
    "exit $LASTEXITCODE"
  ])
  provisioner_custom_data = {
    for stack in keys(local.stacks) : stack => base64encode(join("\n", [
      "MICROHACK_CUSTOM_DATA_V2",
      base64encode(jsonencode(local.provisioner_payload[stack])),
      "MICROHACK_PROVISIONER_START",
      local.provisioner_wrapper
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
      # `exit 0` only normalises the success path. The protection against a green extension
      # over a failed bootstrap is not here: it is `$ErrorActionPreference='Stop'` above,
      # combined with the `$LASTEXITCODE` throw at the end of Invoke-ProvisioningBootstrap
      # in baseInfra/scripts/bootstrap-provision-vm.ps1. Either one throwing halts this
      # command before `exit 0` is reached, so the extension reports failure.
      "Invoke-ProvisioningBootstrap -Stack '${stack}' -SourceCommit '${var.source_commit}' -SourceArchiveSha256 '${var.source_archive_sha256}'",
      "exit 0"
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
