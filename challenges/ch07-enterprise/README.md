# Optional Challenge 7: enterprise hardening

## Objective

Extend the validated Azure target with enterprise controls while preserving the exact
application, migration, handoff, and evidence behavior from required Challenges 0
through 6. This track is architecture-led and intentionally has no canonical solution.

Choose either validated stack:

- `.NET/SQL Server` with Azure SQL Database; or
- `Java/PostgreSQL` with Azure Database for PostgreSQL Flexible Server.

## Boundaries

- Start from a valid `evidence/modernization-contract.json`.
- Work in a disposable extension environment, not the evidence-producing required
  deployment.
- Do not change catalog identities, routes, corpus, import semantics, health, or
  telemetry resource attributes.
- Do not broaden participant or workload roles beyond the reviewed design.
- Subscription policy, DNS, networking, key lifecycle, or encryption changes require
  facilitator and subscription-owner approval before deployment.
- Cloud finding investigation remains required Challenge 5 and is out of scope here.

## Design tasks

### 1. Private networking

Design private ingress and egress boundaries for:

- the Container App environment;
- Azure Container Registry;
- Azure SQL Database or PostgreSQL Flexible Server;
- the selected image storage provider;
- Key Vault;
- Application Insights and Log Analytics; and
- operator access.

Include private endpoints or delegated subnets where supported, private DNS zones and
links, approved egress, build/deployment connectivity, and a break-glass diagnostic
path. Explain how probes, CI/CD, telemetry, and managed identity continue to work.

### 2. Identity and secrets

Replace every remaining human-managed runtime secret with Microsoft Entra workload
identity or a Key Vault reference where the target service supports it. Produce an
exact identity-to-resource matrix with role name, role definition ID, scope, and
justification.

Keep the database-specific authentication boundary explicit:

- Azure SQL Database uses the selected user-assigned managed identity and contained
  database permissions.
- PostgreSQL Flexible Server uses Microsoft Entra authentication and the pinned JDBC
  authentication plugin.

No secret may appear in source, image layers, workflow variables, logs, evidence, or
Terraform state newly introduced by this challenge.

### 3. Edge protection

Place an approved Azure edge service with Web Application Firewall in front of the
application. Define:

- TLS and custom-domain ownership;
- origin authentication and direct-origin blocking;
- managed and custom WAF rules;
- rate limits compatible with the bounded load challenge;
- health-probe routing; and
- false-positive review and rollback.

Do not claim protection from a service that remains bypassable through the Container
App ingress.

### 4. Customer-managed keys

Assess customer-managed key support separately for the database, registry, storage,
and observability services. For every selected integration, document:

- Key Vault or managed HSM boundary;
- key type, rotation, versioning, and recovery settings;
- the service identity and exact key permissions;
- deployment ordering and failure behavior; and
- the restore or rollback procedure.

Do not assert that one key or one API applies uniformly across both database families.

### 5. Policy and governance

Propose an Azure Policy initiative that audits before it denies. Cover allowed regions,
required tags, public network access, private connectivity, diagnostic settings,
managed identity, TLS, and approved SKUs. Identify exemptions required by the workshop
and give every exemption an owner and expiry.

Add a management-group/subscription/resource-group placement diagram, resource locks,
budget/alert ownership, and evidence-retention classification. Do not deploy
subscription-wide policy from a participant identity.

## Deliverables

Create architecture artifacts outside the required evidence directory:

1. A current-state and proposed-state diagram.
2. A data-flow and trust-boundary diagram.
3. An identity/RBAC matrix.
4. A private DNS and endpoint matrix.
5. A customer-managed-key support and lifecycle matrix.
6. A WAF/routing policy with an origin-bypass test.
7. An audit-first Azure Policy plan with exemptions.
8. An implementation sequence, cost estimate, rollback, and cleanup plan.
9. A stack-specific validation plan that reruns the handoff and shared acceptance
   contracts without altering their expected output.

## Success criteria

- The proposal supports both shared architecture and the selected database-specific
  authentication/network requirements.
- Every control names its owner, Azure scope, dependency, failure mode, verification,
  and cleanup.
- Workload and operator permissions remain least privilege.
- Private networking does not silently break deployment, telemetry, probes, or image
  access.
- WAF origin bypass, key unavailability, DNS failure, and policy-denial scenarios have
  executable tests.
- The unchanged application passes the original runtime, migration, acceptance,
  telemetry, and handoff validators after the extension.
