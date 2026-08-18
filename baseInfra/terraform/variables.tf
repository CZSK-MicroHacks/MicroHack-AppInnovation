variable "n" {
  type        = number
  default     = 5
  description = <<EOT
Number of user environments to provision.
Each environment consists of a resource group containing:
 - Two independent Windows Server 2025 VMs: dotnet/SQL Server and java/PostgreSQL
 - Public IP (for Bastion) and separate Public IP for NAT Gateway
 - NAT Gateway for outbound SNAT
 - Network Security Group
 - Virtual Network (derived CIDR 10.<index>.0.0/22)
 - Subnets: 'vms' plus 'AzureBastionSubnet'
Set to a reasonable small number for demos. Must be >=1.
EOT

  validation {
    condition     = var.n >= 1 && var.n <= 254 && floor(var.n) == var.n
    error_message = "n must be a whole number from 1 through 254."
  }
}

variable "locations" {
  type        = list(string)
  description = <<EOT
List of Azure regions to distribute per-user environments across (round-robin).
Assignment rule: environment index i (1-based) is placed in
  locations[(i - 1) % length(locations)].
All regions must support the required resource types (VM size, Bastion, NAT Gateway).
Changing the region assigned to an existing index forces recreation of that environment's resource group and all contained resources.
Provide at least one region; empty list is invalid.
EOT
  validation {
    condition = (
      length(var.locations) > 0 &&
      length(distinct(var.locations)) == length(var.locations) &&
      alltrue([for location in var.locations : length(trimspace(location)) > 0])
    )
    error_message = "Provide at least one non-empty, unique region name in locations."
  }
}

variable "admin_username" {
  type        = string
  default     = "azureuser"
  description = <<EOT
Administrative username configured on both Windows VMs in every participant environment.
Avoid reserved names (Administrator, admin, etc.).
EOT
}

variable "admin_password" {
  type        = string
  sensitive   = true
  description = <<EOT
Administrative password for all facilitator-created Windows VMs.
Provide through the sensitive TF_VAR_admin_password environment variable.
Do NOT commit real secrets to version control.
Password must satisfy Windows complexity requirements.
EOT
}

variable "vm_size" {
  type        = string
  default     = "Standard_D2as_v5"
  description = <<EOT
SKU/size of the Windows VM per user environment.
The deployment creates two VMs of this size per participant.
The default is a two-vCPU SKU; update vm_vcpus when selecting another size.
EOT
}

variable "vm_vcpus" {
  type        = number
  default     = 2
  description = <<EOT
Number of vCPUs exposed by vm_size, used only to calculate the doubled deployment footprint.
The facilitator preflight script obtains the authoritative value from Azure.
Set this input to that reported value before plan/apply when vm_size is changed.
EOT

  validation {
    condition     = var.vm_vcpus >= 1 && floor(var.vm_vcpus) == var.vm_vcpus
    error_message = "vm_vcpus must be a positive whole number."
  }
}

variable "os_disk_size_gb" {
  type        = number
  default     = 127
  description = <<EOT
Size in GiB of each Premium_LRS operating-system disk.
Two disks of this size are created per participant, one for each independent VM.
The value is included in the required capacity and cost preflight.
EOT

  validation {
    condition     = var.os_disk_size_gb >= 127 && floor(var.os_disk_size_gb) == var.os_disk_size_gb
    error_message = "os_disk_size_gb must be a whole number of at least 127 GiB for the pinned Windows image."
  }
}

variable "source_commit" {
  type        = string
  default     = "fd298de6ded4e55b5208fe3f6d8e81fbcdf836c9"
  description = <<EOT
Immutable Git commit used to download the application, canonical manifest, catalog, and images.
The frozen P3 baseline is the exact default. Overrides must remain full lowercase 40-hex commit IDs;
branches, tags, main, and other mutable references are rejected.
EOT

  validation {
    condition     = can(regex("^[0-9a-f]{40}$", var.source_commit))
    error_message = "source_commit must be a full lowercase 40-hex Git commit ID."
  }
}

variable "source_archive_sha256" {
  type        = string
  description = <<EOT
Expected SHA-256 digest of the immutable GitHub source archive for source_commit.
Provisioning verifies this digest before expanding the archive. Supply the reviewed digest through
TF_VAR_source_archive_sha256; it is integrity metadata, not a secret.
EOT

  validation {
    condition     = can(regex("^[0-9a-f]{64}$", var.source_archive_sha256))
    error_message = "source_archive_sha256 must be a lowercase 64-hex SHA-256 digest."
  }
}

variable "capacity_preflight_confirmed" {
  type        = bool
  default     = false
  description = <<EOT
Explicit facilitator acknowledgement that baseInfra/scripts/preflight-capacity.ps1 completed for the
selected subscription, locations, participant count, VM size, vCPU count, disk size, and cost ceiling.
Azure resource creation is blocked until this value is true.
EOT
}

variable "manage_entra_users" {
  type        = bool
  default     = true
  description = <<EOT
Flag controlling whether temporary Entra ID (Azure AD) user accounts are provisioned and granted Owner on each user resource group.
When true: an additional module creates n users and their object IDs are passed to each user_environment module which performs the RBAC assignment.
When false: no Entra users are created and no role assignments are added (user_environment skips RBAC if no user object id provided).
EOT
}

variable "entra_user_domain" {
  type        = string
  default     = ""
  description = <<EOT
Custom domain (e.g. example.onmicrosoft.com) to append to generated user UPNs (user<index>@domain). Required if manage_entra_users is true.
Leave empty to disable user creation implicitly or set manage_entra_users=false.
EOT
}

variable "entra_user_password" {
  type        = string
  sensitive   = true
  default     = ""
  description = <<EOT
Password to assign to all provisioned Entra ID users (lab scenario). Provide via TF_VAR_entra_user_password env var.
If empty while manage_entra_users=true Terraform apply will fail in user module preconditions.
EOT
}

variable "subscription_id" {
  type        = string
  description = <<EOT
Azure Subscription ID where all resources will be deployed.
Provide via tfvars file (e.g. config.auto.tfvars), CLI -var flag, or environment variable TF_VAR_subscription_id.
Externalizing this value avoids editing provider configuration when switching target subscriptions.
If omitted, provider authentication will attempt to infer a default subscription from the Azure CLI / Managed Identity context (not recommended for reproducible workshop setups).
EOT
}

variable "manage_azure_resources" {
  type        = bool
  default     = true
  description = <<EOT
Flag controlling whether user environments (Azure resources) should be deployed.
When true: user environments with VMs, networking, and associated resources are provisioned.
When false: only Entra ID users are created (if manage_entra_users is true), but no Azure infrastructure is deployed.
This allows for scenarios where user accounts are needed but the workshop environment is provided separately.
EOT
}

variable "manage_sub_providers" {
  type        = bool
  default     = true
  description = <<EOT
Flag controlling whether Azure resource providers should be registered in the subscription.
When true: registers all required resource providers (AI, containers, databases, networking, etc.) before deploying resources.
When false: skips provider registration (assumes providers are already registered or will be registered separately).
This is useful for workshop scenarios where users don't have subscription-level permissions to register providers.
EOT
}
