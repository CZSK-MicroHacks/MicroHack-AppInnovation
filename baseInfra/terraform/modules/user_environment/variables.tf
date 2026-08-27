variable "user_index" {
  type        = number
  description = <<EOT
One-based numeric index (1..n in root loop) used to derive:
 - Naming (rg-userNNN, vm-dotnet-userNNN, vm-java-userNNN, etc.)
 - Address space segments (10.<index>.0.0/22)
Must align with the range passed from root module.
EOT
}

variable "location" {
  type        = string
  description = <<EOT
Azure region where all resources for this per-user environment are created.
Should match root `location` for consistency.
EOT
}

variable "admin_username" {
  type        = string
  description = <<EOT
Local administrator account name configured on both Windows VMs.
Avoid reserved names (Administrator, admin) to prevent provisioning errors.
EOT
}

variable "admin_password" {
  type        = string
  sensitive   = true
  description = <<EOT
Local administrator password for both Windows VMs.
Inherited from root; provided once for all environments.
Meets Windows complexity rules; not logged due to `sensitive=true`.
EOT
}

variable "vm_size" {
  type        = string
  description = <<EOT
Azure compute SKU (for example Standard_D2as_v5) applied independently to both VMs.
Changing it after initial apply can recreate both VMs.
EOT
}

variable "os_disk_size_gb" {
  type        = number
  description = <<EOT
Operating-system disk size in GiB for each VM.
The dotnet and java VMs receive separate Premium_LRS disks of this size.
EOT
}

variable "source_commit" {
  type        = string
  description = <<EOT
Full immutable 40-hex Git commit used for the application and canonical data archive.
The root module validates this before passing it to the environment.
EOT
}

variable "source_archive_sha256" {
  type        = string
  description = <<EOT
Reviewed lowercase SHA-256 digest for the immutable source archive.
The VM provisioner verifies it before extraction.
EOT
}

variable "capacity_preflight_confirmed" {
  type        = bool
  description = <<EOT
Whether the facilitator completed the exact doubled-capacity and cost preflight.
Resource-group creation is blocked when this acknowledgement is false.
EOT
}

variable "assigned_user_object_id" {
  type        = string
  default     = null
  description = <<EOT
Optional Entra ID user object ID to receive Owner role on this resource group.
If null, no role assignment resource is created (labs without managed users).
Supplied by root when `manage_entra_users=true`.
EOT
}

variable "create_role_assignment" {
  type        = bool
  default     = false
  description = <<EOT
Explicit switch controlling creation of the Owner role assignment.
Set true only when an assigned_user_object_id is also provided.
Decoupling the boolean avoids unknown value propagation issues in count.
EOT
}

variable "facilitator_principal_name" {
  type        = string
  description = <<EOT
Facilitator user principal name written into this environment's protected deployment
parameter files as `facilitatorPrincipalName`. Validated by the root module.
EOT
}

variable "facilitator_principal_object_id" {
  type        = string
  description = <<EOT
Facilitator Entra ID object ID written into this environment's protected deployment
parameter files as `facilitatorPrincipalObjectId`. Validated by the root module.
EOT
}

variable "enable_public_ip_resources" {
  type        = bool
  default     = true
  description = <<EOT
Controls whether this environment provisions public IP addresses and the resources that
require them (Azure Bastion Basic and the NAT Gateway).

Leave at the default `true` for a normal delivery. Set to `false` only when the target
subscription is governed such that public IP addresses cannot be created at all -- some
managed/sandbox tenants revoke `Microsoft.Network/AllowBringYourOwnPublicIpAddress` and
continuously revert attempts to re-register it.

When `false`:
  * VM outbound internet relies on Azure default outbound access instead of the NAT
    Gateway. This is verified working in the delivery subscription: both participant VMs
    downloaded a 327 MB archive and the container app pulled from MCR with no NAT Gateway
    and no public IP anywhere in the resource group. The retirement of default outbound
    access applies to virtual networks created after 2026-03-31, and only when the subnet
    sets `defaultOutboundAccess`, which this module never does.
  * Azure Bastion downgrades from Basic to the Developer SKU, which needs no public IP and
    no AzureBastionSubnet. Interactive RDP through the portal still works, so the challenge
    0 instruction to connect through Bastion stays accurate. The Developer SKU serves one
    VM per session, offers no native `az network bastion rdp` client, and cannot reach
    peered virtual networks; the challenge 0 flow needs none of those.
EOT
}
