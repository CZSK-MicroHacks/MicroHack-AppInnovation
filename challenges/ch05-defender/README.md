# Challenge 5: compare and remediate Defender posture

## Goal

Use the selected `evidence/modernization-contract.json` and the frozen Defender contract
`workshop/contracts/defender.json` version `1.1.0`. Compare the selected retained VM with
its modernized Azure Container Apps, Azure Container Registry, and selected managed
database stack, while also confirming Defender for Servers P2 coverage for the sibling
retained VM.

This challenge is posture and evidence work. Azure Container Apps has platform-managed
hosts and receives serverless-container posture context; it has no participant-visible
host and no host/runtime Defender sensor. Do not claim Defender host or runtime sensor
coverage for ACA.

## Authoritative inputs

All declared artifact paths are repository-root-relative. Start only when these inputs
exist and their recorded SHA-256 values validate:

- `evidence/modernization-contract.json`, including its exact `sliceId`,
  `source.commitSha`, application resource ID, revision, URLs, ACR resource ID,
  repository, immutable image digest, selected database resource ID/family, and
  `deployment.targetOutput`;
- the target output named by `deployment.targetOutput`, including
  `network.migrationSourceVmResourceId` and the workload managed identity;
- `workshop/defender/lab-profile.json`;
- facilitator-provided live foundation captures for pricings, budget, Serverless
  Containers portal preflight, both retained VM identities, and cleanup inventory;
- the distinct pre-warmed Defender seed snapshot; and
- the facilitator-authorized cleanup manifest.

The selected source VM is exactly `network.migrationSourceVmResourceId`. The coverage
artifact must contain exactly the `dotnet` and `java` retained VMs under Defender for
Servers P2, including the selected VM and its sibling. Never substitute a VM discovered
by name or portal search.

The checked-in files under `workshop/contracts/fixtures/defender/` and
`workshop/contracts/defender-evidence-capture.example.json` are sanitized examples.
They describe structure only. Their zero IDs, example URLs, timestamps, hashes, and
findings are never live participant evidence.

## Coverage comparison

| Subject | Required interpretation |
| --- | --- |
| Selected retained VM | Defender for Servers P2; customer-managed OS, host, management ports, NSG exposure, and optional JIT policy |
| Sibling retained VM | Its exact identity and successful P2 coverage must remain in the two-VM coverage artifact |
| Azure Container App | Defender CSPM Serverless Containers posture only; platform-managed host, no host/runtime Defender sensor |
| Azure Container Registry image | Query the frozen subassessment path for the exact handoff repository and immutable digest |
| Azure SQL | Selected `azure-sql` database is protected by `SqlServers`; assess the parent SQL server network posture |
| PostgreSQL | Selected `postgresql-flexible` database is protected by `OpenSourceRelationalDatabases`; assess the parent flexible server |
| Security context | Query recommendations, Secure Score, MCSB controls, and Resource Graph attack paths at the handoff subscription |

Current image findings, recommendations, Secure Score updates, and attack paths are
asynchronous. A current live query can legitimately return zero records. The graded
signal is the exact query attempt and provenance, not a newly generated finding or
alert. Use the distinct pre-warmed seed snapshot for deterministic learning evidence;
never relabel the snapshot as current state and never wait for or manufacture a new
recommendation or alert during class.

## Permission and scope boundary

Participants operate only in the assigned resource group with `Security Reader` plus
the existing resource-group permissions required by the selected modernization path.
Participants must not:

- enable or disable paid Defender plans;
- change Defender policy, auto-provisioning, subscription settings, agents, VM
  extensions, or Data Collection Rule associations;
- delete policies, agents, extensions, or shared resources;
- query or alter another participant resource group or subscription; or
- perform post-workshop cleanup.

Owner or Security Admin at the dedicated workshop subscription is facilitator-only.
The Serverless Containers portal preflight requires Owner. Cleanup is
facilitator-authorized only.

## The four bounded controls

Remediate or record the contract-approved disposition for exactly these controls:

1. `acr-admin-authentication`: disable ACR admin authentication. Preserve the exact
   handoff workload managed identity, its ACR-scoped `AcrPull` role
   `7f951dda-4ed3-4680-a7ca-43fe172d538d`, and the exact digest-qualified image.
2. `container-app-ingress`: `allowInsecure` must be `false`. Internal ingress may be
   remediated/already compliant; intentional public HTTPS ingress must be `justified`
   with compensating controls.
3. `database-public-network`: evaluate the selected family only. Disable public network
   access, retain an already-compliant state, or use `documented-exception` with a
   specific justification and compensating controls.
4. `legacy-vm-management-ingress`: bind every NIC and effective NSG response to the
   exact selected source VM. Remove public SSH/RDP exposure, prove an exact bound
   Defender JIT policy covers the public management port, retain an already-segmented
   state, or use `documented-exception`.

Do not weaken a secure baseline just to create a before/after transition. An
`already-compliant` disposition is valid when the captured state proves it.

## Required live capture

Create `evidence/defender/capture.json` version `1.1.0`. It must digest-bind:

- the selected handoff, its exact target output, lab profile, and cleanup manifest;
- facilitator foundation artifacts, including both retained VM identities and the
  distinct pre-warmed seed snapshot;
- before/after raw state for the exact ACR, ACA, selected database server, and selected
  source VM;
- the exact ACR-scoped managed-identity `AcrPull` assignment;
- the three explicit decision records;
- current image assessment, recommendations, Secure Score, MCSB, and attack-path query
  envelopes;
- exact handoff revision health/readiness URLs with HTTP `200`; and
- the final capture time after every referenced observation.

The frozen current-query provenance is:

| Signal | Method, path, API version |
| --- | --- |
| Image assessment | `GET providers/Microsoft.Security/assessments/c0b7cfc6-3172-465a-b378-53c7ff2cc0d5/subAssessments`, `2019-01-01-preview`, exact handoff ACR scope |
| Recommendations | `GET providers/Microsoft.Security/assessments`, `2020-01-01`, handoff subscription |
| Secure Score | `GET providers/Microsoft.Security/secureScores`, `2020-01-01`, handoff subscription |
| MCSB | `GET providers/Microsoft.Security/regulatoryComplianceStandards/Microsoft-cloud-security-benchmark/regulatoryComplianceControls`, `2019-01-01-preview`, handoff subscription |
| Attack paths | `POST providers/Microsoft.ResourceGraph/resources`, `2022-10-01`, exact `securityresources` query and one subscription |

Attack paths are available only through that complete Azure Resource Graph POST
envelope. An unsupported direct `GET` to a `Microsoft.Security/attackPaths` collection
is not evidence. The response must be untruncated and complete, but `data: []` is valid.

## Cleanup provenance

The refrozen cleanup inventory is a facilitator-owned composite captured before paid
plan enablement and, if cleanup is completed, again after restoration:

- one complete Resource Graph `POST providers/Microsoft.ResourceGraph/resources`
  response at `2022-10-01`, using exactly
  `union Resources, InsightResources, SecurityResources, PolicyResources`;
- `Resources` produces VM and Arc machine extensions;
- `InsightResources` produces Data Collection Rule associations;
- `SecurityResources` produces Defender pricings;
- `PolicyResources` produces policy assignments;
- exact ARM list `GET providers/Microsoft.Security/autoProvisioningSettings` at
  `2017-08-01-preview`, operation
  `subscription-defender-auto-provisioning-settings`; and
- exact ARM list `GET providers/Microsoft.Security/settings` at `2021-06-01`.
  Its operation is `subscription-defender-settings`.

Auto-provisioning settings and settings must not be invented as Resource Graph rows.
Participants inspect the digest-bound cleanup manifest but do not execute cleanup.
Facilitators restore the prior pricing/enforce/extension state and prior inventory
exactly, then run the cost query; billing data may lag.

## Render and validate

Do not manually create or edit `evidence/defender-report.json` or any normalized
Defender result. From `tests/acceptance`, run the exact frozen registry commands:

```bash
uv --no-config run catalog-render-defender-evidence --capture evidence/defender/capture.json --handoff evidence/modernization-contract.json --output evidence/defender-report.json --repository-root ../..
uv --no-config run catalog-validate-defender-evidence --capture evidence/defender/capture.json --handoff evidence/modernization-contract.json --report evidence/defender-report.json --contracts workshop/contracts --repository-root ../..
```

The validator replays every digest-bound raw input. Empty asynchronous current results
do not fail by themselves. Wrong scopes, paths, API versions, identities, database
family, VM/NIC/NSG binding, mutable images, missing `AcrPull`, altered raw files,
aliased seed/current artifacts, incomplete Resource Graph responses, fabricated
findings, or manually normalized JSON fail closed.

[Solution steps](../../solutions/ch05-defender/README.md)
