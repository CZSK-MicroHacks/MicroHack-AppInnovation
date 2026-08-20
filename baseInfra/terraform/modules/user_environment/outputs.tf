output "resource_group_name" { value = local.rg_name }
output "resource_group_id" { value = azapi_resource.rg.id }
output "vnet_name" { value = local.vnet_name }

output "dotnet_vm_name" { value = local.stacks.dotnet.vm_name }
output "java_vm_name" { value = local.stacks.java.vm_name }

output "vm_names" {
  value = { for stack, config in local.stacks : stack => config.vm_name }
}

output "private_ip_addresses" {
  value = {
    for stack, nic in azapi_resource.nic :
    stack => nic.output.properties.ipConfigurations[0].properties.privateIPAddress
  }
}
