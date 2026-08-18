resource "random_password" "database" {
  for_each = local.stacks

  length           = 32
  special          = true
  override_special = "!#%+-_="
  min_upper        = 1
  min_lower        = 1
  min_numeric      = 1
  min_special      = 1
}

resource "random_password" "performance_api_key" {
  for_each = local.stacks

  length  = 48
  special = false
}

resource "terraform_data" "provisioner" {
  input = local.provisioner_sha256
}

resource "azapi_resource" "vm" {
  for_each = local.stacks

  type      = "Microsoft.Compute/virtualMachines@2024-11-01"
  name      = each.value.vm_name
  location  = var.location
  parent_id = azapi_resource.rg.id
  body = {
    properties = {
      hardwareProfile = { vmSize = var.vm_size }
      storageProfile = {
        osDisk = {
          createOption = "FromImage"
          deleteOption = "Delete"
          diskSizeGB   = var.os_disk_size_gb
          managedDisk  = { storageAccountType = "Premium_LRS" }
        }
        imageReference = {
          publisher = "MicrosoftWindowsServer"
          offer     = "WindowsServer"
          sku       = "2025-datacenter-azure-edition"
          version   = "26100.7456.251206"
        }
      }
      osProfile = {
        computerName  = each.value.computer_name
        adminUsername = var.admin_username
        adminPassword = var.admin_password
        customData    = local.provisioner_custom_data[each.key]
        windowsConfiguration = {
          enableAutomaticUpdates = true
          patchSettings          = { patchMode = "AutomaticByPlatform" }
        }
      }
      networkProfile = {
        networkInterfaces = [
          {
            id         = azapi_resource.nic[each.key].id
            properties = { primary = true }
          }
        ]
      }
    }
    identity = {
      type = "SystemAssigned"
    }
  }

  lifecycle {
    replace_triggered_by = [
      terraform_data.provisioner,
      random_password.database[each.key],
      random_password.performance_api_key[each.key]
    ]
  }

  depends_on = [azapi_resource.nic]
}

resource "azapi_resource" "vm_setup" {
  for_each = local.stacks

  type      = "Microsoft.Compute/virtualMachines/extensions@2024-11-01"
  name      = "provision-${each.key}"
  location  = var.location
  parent_id = azapi_resource.vm[each.key].id
  body = {
    properties = {
      publisher               = "Microsoft.Compute"
      type                    = "CustomScriptExtension"
      typeHandlerVersion      = "1.10"
      autoUpgradeMinorVersion = false
      forceUpdateTag          = "${local.provisioner_sha256}-${var.source_commit}"
      protectedSettings = {
        commandToExecute = "powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command \"$script = 'C:\\AzureData\\provision-vm.ps1'; if (-not (Test-Path -LiteralPath $script)) { Copy-Item -LiteralPath 'C:\\AzureData\\CustomData.bin' -Destination $script -Force }; & $script -Stack ${each.key} -SourceCommit ${var.source_commit} -SourceArchiveUrl ${local.source_archive_url} -SourceArchiveSha256 ${var.source_archive_sha256}\""
      }
    }
  }

  depends_on = [azapi_resource.vm]
}
