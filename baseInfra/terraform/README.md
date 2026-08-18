# Facilitator Terraform

This root module uses `azapi` for workshop resources and `azurerm` for authentication and explicit
provider registration. It creates two keyed VM resources per participant:

```text
module.user_environment["1"].azapi_resource.vm["dotnet"]
module.user_environment["1"].azapi_resource.vm["java"]
```

The matching NIC, extension, managed-identity role assignment, generated database password, and
generated performance key use the same `dotnet` or `java` key. The network, Bastion, NAT Gateway,
NSG, resource group, and outbound public IP remain single shared resources in that participant
module.

## Inputs

| Input | Default | Purpose |
| --- | --- | --- |
| `n` | `5` | Participant environments; creates `n * 2` VMs and OS disks |
| `locations` | required | Unique regions assigned round-robin |
| `subscription_id` | required | Target Azure subscription |
| `admin_username` | `azureuser` | Local administrator name on both VMs |
| `admin_password` | none, sensitive | Set with `TF_VAR_admin_password` |
| `vm_size` | `Standard_D2as_v5` | Size used by both VMs |
| `vm_vcpus` | `2` | Footprint value confirmed by preflight |
| `os_disk_size_gb` | `127` | Separate Premium OS disk size for each VM |
| `source_commit` | frozen 40-hex commit | Immutable application/data source |
| `source_archive_sha256` | required | Reviewed immutable archive digest |
| `capacity_preflight_confirmed` | `false` | Blocks resource creation until preflight succeeds |
| `manage_entra_users` | `true` | Creates participant Entra users when enabled |
| `entra_user_domain` | empty | Required when Entra user creation is enabled |
| `entra_user_password` | empty, sensitive | Set with `TF_VAR_entra_user_password` |
| `manage_azure_resources` | `true` | Enables participant infrastructure |
| `manage_sub_providers` | `true` | Enables explicit provider registration |

No secret belongs in `config.tfvars.example` or a committed `.tfvars` file. Generated secrets and
protected extension settings are still present in Terraform state; use an encrypted,
access-controlled remote backend for deployment.

## Commands

Run the exact preflight and source digest procedure in [`../README.md`](../README.md), then:

```pwsh
Set-Location baseInfra/terraform
terraform init
terraform validate
terraform plan -var-file local.tfvars -out tfplan
terraform apply tfplan
```

Do not use `terraform apply -auto-approve` for the facilitator environment. Review the doubled
compute/disk footprint, source digest, provider registrations, and all replacements in the saved
plan.

Useful outputs:

```pwsh
terraform output dotnet_vm_names
terraform output java_vm_names
terraform output vm_names_by_environment
terraform output private_ip_addresses_by_environment
terraform output deployment_footprint
```

## Immutable Custom Script Extension

The provisioner is embedded in each VM's custom data instead of downloaded from a branch. The
extension copies Azure's decoded `CustomData.bin` to a `.ps1` path before Windows PowerShell 5.1
executes it. Its command is stored only in `protectedSettings` and passes base64-encoded generated
credentials without printing them. Application/data content uses:

```text
https://github.com/CZSK-MicroHacks/MicroHack-AppInnovation/archive/<40-hex-commit>.zip
```

`source_archive_sha256` is verified before expansion. Every tool/database installer is the exact
URL from `workshop/toolchain.lock.json`, with digest verification and Authenticode publisher
verification where the lock declares a publisher.

VM image version, .NET, SQL Server Express, go-sqlcmd, Microsoft OpenJDK, PostgreSQL, Maven,
VS Code, Azure CLI, uv, Python, and VS Code extension versions are pinned. There are no raw branch
URLs, `latest` versions, or mutable package-manager fallbacks.

VM custom data cannot be updated in place. A `terraform_data.provisioner` replacement trigger makes
any provisioner-content change replace the two VMs rather than attempt an invalid Azure update.
Changing only `source_commit` reruns each extension in place through its force tag.

## Independent operation

Each database is a local automatic Windows service. Each application is published once and run by
an automatic scheduled task (`MicroHack-dotnet` or `MicroHack-java`). Provisioning creates a
stack-specific smoke marker only after the app, liveness, readiness, canonical image, canonical
manifest counts, and native database counts pass.

Deallocating `vm-dotnet-userNNN` does not affect `vm-java-userNNN`, and vice versa. Shared Bastion,
VNet, subnet, NSG, NAT Gateway, and outbound IP remain available while either VM is stopped.

## Provider registration lifecycle

The AzureRM provider sets `resource_provider_registrations = "none"`. The registration module owns
the approved namespace list and uses `prevent_destroy = true` to preserve the subscription-wide
boundary. Before participant cleanup, remove that module from this state without unregistering it:

```pwsh
terraform state rm 'module.resource_providers[0]'
terraform destroy -var-file local.tfvars
```

Use `import_existing_providers.ps1` when adopting existing registrations into a new state.
