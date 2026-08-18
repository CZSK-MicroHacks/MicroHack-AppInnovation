# Base infrastructure (facilitator only)

Terraform provisions one isolated participant resource group per index. Every group contains two
independent Windows Server 2025 legacy workstations before the workshop starts:

| Stack | VM | Native database | Application |
| --- | --- | --- | --- |
| .NET | `vm-dotnet-userNNN` | SQL Server 2022 Express | .NET SDK 8.0.424 catalog on port 5000 |
| Java | `vm-java-userNNN` | PostgreSQL 18.6-1 | Microsoft OpenJDK 17.0.20+8 catalog on port 8080 |

The VMs share `rg-userNNN`, `vnet-userNNN`, the `vms` subnet, `bastion-userNNN`,
`nsg-userNNN`, `nat-userNNN`, and `pip-nat-userNNN`. They have separate NICs, dynamic private
addresses, VM resources, Premium OS disks, managed identities, and Custom Script Extensions.
Either VM can be stopped or deallocated without changing the other.

## Frozen provisioning

The Windows image is exactly `MicrosoftWindowsServer:WindowsServer:2025-datacenter-azure-edition:26100.7456.251206`.
Application content defaults to immutable commit
`fd298de6ded4e55b5208fe3f6d8e81fbcdf836c9`. Terraform rejects branch, tag, short-SHA,
and other mutable source values.

`baseInfra/scripts/provision-vm.ps1` is embedded as VM custom data. The protected Custom Script
Extension command supplies only generated database and performance secrets plus reviewed source
integrity metadata. The provisioner verifies each locked digest and Authenticode publisher before
running an installer. It does not use `winget`, `latest`, package-manager fallback chains, or raw
branch URLs.

Both VMs receive pinned VS Code, Azure CLI, uv, uv-managed Python 3.12.10, and exact signed
Copilot extensions. The .NET VM additionally receives the pinned .NET modernization extensions.
The Java VM receives the pinned Java migration/upgrade extensions, Microsoft OpenJDK, and the
checksum-pinned Maven Wrapper workflow. The source archive is used directly, so provisioning does
not introduce an unpinned Git installer that is absent from the frozen lock.

## Facilitator preflight

Prerequisites:

- Terraform 1.13.3 and PowerShell 7
- Azure CLI 2.80.0 authenticated to the target subscription
- subscription permissions for resource groups, networking, Bastion, VMs, role assignments,
  provider registration, and optional Entra user creation

From the repository root, run the quota and cost gate for the exact participant count, regions,
VM size, and disk size:

```pwsh
./baseInfra/scripts/preflight-capacity.ps1 `
  -SubscriptionId '<subscription-guid>' `
  -Locations @('swedencentral', 'germanywestcentral') `
  -ParticipantCount 10 `
  -VmSize 'Standard_D2as_v5' `
  -OsDiskSizeGiB 127 `
  -MaximumEstimatedMonthlyCostUsd 3000
```

The command fails when the SKU is restricted or regional, VM-family, VM-count, or Premium managed
disk quota cannot cover two VMs per participant. Its estimate includes both Windows VMs and both
Premium OS disks and explicitly excludes the already-shared Bastion, NAT Gateway, and public IP
costs.

Download the immutable archive once to record the digest that every VM will enforce:

```pwsh
$commit = 'fd298de6ded4e55b5208fe3f6d8e81fbcdf836c9'
$archive = Join-Path $env:TEMP "$commit.zip"
Invoke-WebRequest `
  -Uri "https://github.com/CZSK-MicroHacks/MicroHack-AppInnovation/archive/$commit.zip" `
  -OutFile $archive
$env:TF_VAR_source_archive_sha256 = (Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant()
Remove-Item $archive
```

The commit must exist in the public repository before this command or VM provisioning can succeed.

## Initialize, plan, and apply

Copy `baseInfra/terraform/config.tfvars.example` to a git-ignored local file and set only non-secret
deployment values. Supply secrets and preflight acknowledgement through the facilitator process:

```pwsh
Set-Location baseInfra/terraform
$env:TF_VAR_admin_password = '<strong-facilitator-secret>'
$env:TF_VAR_entra_user_password = '<strong-temporary-user-secret>'
$env:TF_VAR_capacity_preflight_confirmed = 'true'

terraform init
terraform validate
terraform plan -var-file local.tfvars -out tfplan
terraform apply tfplan
```

Do not commit `.tfvars`, plan, or state files. Terraform state contains the Windows administrator
password, generated per-environment database passwords, generated performance API keys, and
protected extension settings. Use an encrypted, access-controlled remote backend for a real
facilitator deployment and restrict state access as tightly as the VMs.

## Outputs and access

The root outputs include:

- `dotnet_vm_names` and `java_vm_names`
- `vm_names_by_environment`
- `private_ip_addresses_by_environment`
- `resource_group_names`, `vnet_names`, and region distribution
- `deployment_footprint` with doubled VM, vCPU, OS-disk, and disk-GiB totals

Connect through Azure Bastion; there are no VM public IP addresses. After Challenge 0, deallocate
the unselected stack to stop its compute charges:

```pwsh
az vm deallocate --resource-group rg-user001 --name vm-java-user001
# Or, for the Java track:
az vm deallocate --resource-group rg-user001 --name vm-dotnet-user001
```

Use `az vm start` with the same resource group and VM name to restore a deallocated stack.

## Provisioning status and diagnostics

Provisioning succeeds only after `/healthz`, `/readyz`, one canonical lowercase UUID image, the
198/20/198 manifest, and the stack-native database counts pass locally. Inspect these files from
the selected VM:

```pwsh
Get-Content C:\MicroHack\status\dotnet-smoke.json
Get-Content C:\MicroHack\status\java-smoke.json
Get-Content C:\MicroHack\logs\provision-dotnet.log
Get-Content C:\MicroHack\logs\provision-java.log
Get-Content C:\MicroHack\logs\dotnet-app.log
Get-Content C:\MicroHack\logs\java-app.log
Get-ScheduledTask -TaskName 'MicroHack-*'
```

Only the matching stack files exist on each VM. SQL Server/PostgreSQL services and the
`MicroHack-dotnet`/`MicroHack-java` startup tasks are automatic, so ordinary VM restarts do not
reseed duplicate records or require student setup. The application import paths remain
transactional and insert-new/idempotent.

Changing `source_commit` updates the extension force tag and reruns verified provisioning in
place. Editing `provision-vm.ps1` replaces both VMs in each affected participant module because
Azure VM custom data is immutable; review that replacement plan carefully. To deliberately rerun
one stack without replacing its VM:

```pwsh
terraform apply `
  -replace='module.user_environment["1"].azapi_resource.vm_setup["dotnet"]'
```

## Provider registration and cleanup boundary

Provider registration explicitly includes ACA and SRE Agent (`Microsoft.App`), ACR
(`Microsoft.ContainerRegistry`), Azure SQL, PostgreSQL, Monitor, and Defender. The registration
resources use `prevent_destroy = true`; Terraform must never unregister shared subscription
providers during participant cleanup.

To destroy participant infrastructure while retaining the registrations, detach only the
registration module from this state first:

```pwsh
terraform state rm 'module.resource_providers[0]'
terraform destroy -var-file local.tfvars
```

Review the destroy plan carefully. Reducing `n`, changing assigned regions, VM size, image, or OS
disk settings can replace resources and discard their local ephemeral data.
