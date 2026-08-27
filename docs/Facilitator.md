# Facilitator guide

**This workshop needs about five working days of your hands-on time, spread across roughly
three calendar weeks, before the first participant signs in.** Most of that calendar time
is other people's approvals; most of the hands-on time is waiting for Microsoft Defender
for Cloud and building things that cannot be built on the day.

Read this page end to end before you agree to a date. Two of the blockers below are
decisions you cannot make on the morning of the workshop.

> **On the day itself, work from [the day-of card](DayOfCard.md), not from this page.** It
> is one printable page: the timeline with its decision points, the go/no-go checks, the
> commands that tell you whether one participant is healthy, the named file every
> participant should have at each checkpoint, and what to cut when the room is behind. This
> guide is preparation; that card is delivery.

**Where you work.** Everything in this guide runs on **your own laptop, in bash** — macOS
or Linux, or WSL or Git Bash on Windows — from the repository root unless a block says
otherwise. You need `az`, `terraform`, `git`, `jq`, `curl`, `unzip`, `shasum`, and `uv` on
your PATH. The command blocks use `\` line continuations and pipe JSON straight into `jq`,
so a PowerShell session parses them as errors rather than running them; there is no
half-working middle state to notice late.

Five blocks are deliberately not bash, and each says so where it appears. The capacity
preflight and the Defender seed capture are PowerShell scripts, and the legacy-VM capture that
feeds the seed capture is a PowerShell block, so all three need **PowerShell 7**
(`pwsh`), which is cross-platform and which you need anyway. Two blocks under
[the cached-credential section](#the-facilitator-credential-sitting-on-every-participant-vm)
run **on a participant VM**, in the ordinary Windows PowerShell session the participant
already has. [`baseInfra/README.md`](../baseInfra/README.md) gives the same Terraform steps
in PowerShell throughout — either shell reaches the same state, but pick one per block and
do not blend the two forms.

---

## Decide these before you book a date

| Blocker | What is missing | What you must decide |
| --- | --- | --- |
| **Challenge 2 needs a Load Testing resource and a Key Vault secret** | Challenge 2 reads `LOAD_TEST_RESOURCE_ID` and `PERFTEST_API_KEY_SECRET_URI`. `infra/perf-testing.bicep` creates the Azure Load Testing resource, the Key Vault, and the role assignments — but **it does not create the secret value itself**, and it is a separate deployment from `infra/main.bicep`. | Who deploys `infra/perf-testing.bicep` for each participant, and who sets the API-key secret. **The count is not yours to decide: thirty, one per participant, never shared.** Challenge 2 puts the whole room under load inside the same 35-minute window, so a shared resource turns the chapter into a queue — and a serialised wait is the one thing the chapter *about autoscaling under load* cannot absorb. The fee is **monthly and charged for any part of a month**, so keep provisioning and teardown inside one calendar month or you pay it twice ([cost estimate](CostEstimate.md#cohort-of-30)). |
| **Challenge 3's approval gate needs GitHub environment protection** | Deployment protection rules — the required-reviewers gate the whole chapter is built around — are **not available on private repositories on the GitHub Free plan**. `baseInfra/github/main.py` creates participant repositories with `private=True`, and `baseInfra/github/README.md` tells you to create a free organization. Those two facts are incompatible. | Either make the workshop repositories **public** (Free is then sufficient), or buy **GitHub Team or Enterprise Cloud** for the organization. If you do neither, the `production` job runs without ever pausing and there is no approval to record. |

Both are prerequisites, not risks. Resolve them at the point where you are still choosing a
date, not at the point where thirty people are waiting.

---

## Lead time and what it is based on

| Stage | Duration | Why it takes that long |
| --- | --- | --- |
| Subscription, quota, plan, and seat approvals | **2–3 calendar weeks** | Other people's processes. Azure quota increases are support tickets; a GitHub plan change is a purchase; Copilot seats need an administrator. None is under your control. |
| Terraform remote-state bootstrap and preflight | ~2 hours | One-off per subscription |
| Publishing and re-pinning the workshop source commit | ~30 minutes | The commit must be pushed to GitHub and its archive verified before any VM is provisioned |
| Golden environment and Defender enablement | **≥24 hours of waiting** | Defender for Cloud assessments, Secure Score, and attack paths are generated asynchronously. This is documented in the repository as "up to 24 hours" and it is not negotiable |
| Building both golden handoffs | **1–2 days** | The repository ships none — see [`workshop/golden/README.md`](../workshop/golden/README.md). You must complete Challenge 1 end to end for *both* stacks. The chapter's own estimate is 5–12 hours per stack, so budget two days unless two of you split the stacks — and [rehearse the cut](#rehearse-the-1515-cut-before-you-have-to-perform-it) while you are still in that environment |
| SRE Agent foundation | **45–60 minutes per team** | The chapter states this. At 30 teams that is 22–30 hours — see the sizing decision below |
| Participant provisioning and smoke checks | ~4 hours plus a settle day | Terraform apply, then wait for every VM's provisioning to report healthy |

**Total hands-on: about five working days.** The independent review of this repository
reconstructed 3–5 working days from the code alone; the higher end is right once you
include building golden handoffs for both stacks, which is the step people forget.

---

## Who holds what rights, and when

Get this wrong in the obvious direction — granting twenty people subscription Owner so that
"the deployment works" — and you have handed the room your whole subscription. You do not
need to. The boundary is clean, and it is the one the infrastructure already builds.

| Who | Scope | When | What it is for |
| --- | --- | --- | --- |
| You | **Subscription Owner** | T-15 through T-1, and teardown | Creating one resource group per participant, assigning roles inside each of them, subscription-wide Defender plans, the subscription budget, and `infra/sre-agent.bicep` |
| Participant | **Owner on their own resource group**, and nothing at subscription scope | The workshop itself | Everything in Challenges 0 through 6 |
| Each VM's managed identity | Owner on the same resource group | Provisioned at T-2 | The VM-side automation in Challenges 0 and 1 |

**Every subscription-scope action happens before anyone arrives**, and the last of them is
the T-2 Terraform apply. `baseInfra/terraform` creates one resource group per participant,
puts **two legacy VMs in it** — one .NET, one Java — and grants Owner on that resource group
to the participant (`rg_owner_role_assignment`) and to each VM's managed identity
(`vm_identity_owner`). By the time the room fills, there is nothing left for a participant to
do above their own resource group.

Challenge 1 then deploys the modernized environment **into that same resource group**. The
shape below is what you would run to reproduce it from your own machine; the participant's
copy of it is PowerShell, on the VM:

```bash
: "${RESOURCE_GROUP:?Set the participant resource group you are reproducing into}"

az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --template-file infra/main.bicep \
  --parameters @<your-parameter-file>
```

`infra/main.bicep` is `targetScope = 'resourceGroup'`. It does not create a resource group
and it writes nothing at subscription scope — its `deploysIntoTheParticipantResourceGroup`
assertion fails the deployment outright if the `resourceGroupName` parameter is not the
group it is being deployed into. The VNet peering it configures targets the participant's
own resource group, because the legacy VMs and their network are in there too. Owner on that
one resource group is genuinely sufficient. See [`infra/README.md`](../infra/README.md).

**The one exception is `infra/sre-agent.bicep`,** which is deliberately subscription-scoped
because it defines a custom role, and a custom role definition cannot be scoped to a
resource group. It is facilitator-only work you do at T-3, and no participant ever runs it.
It does not contradict the rule above.

If a participant reports `AuthorizationFailed` on a Challenge 1 deployment, the fix is not a
broader role. Check that they are running `az deployment group create` against their own
resource group, and that the signed-in identity is the one you provisioned.

---

## T-minus runbook

### T-15 working days — order and approve

Nothing below this line can be rushed later.

| Item | Owner | Notes |
| --- | --- | --- |
| A **disposable** Azure subscription with no production workload | Subscription owner | The workshop enables subscription-wide Defender plans and creates a subscription budget. Do not use a shared subscription |
| Subscription Owner rights for you | Subscription owner | Needed for role assignments, Defender pricing, and the Serverless Containers portal preflight. Yours alone, and only through T-1 — see [Who holds what rights, and when](#who-holds-what-rights-and-when). Participants never need it |
| Quota increases | You | See the preflight section. Request VM-family vCPU, Standard public IP, and NAT gateway increases together — public IPs are the one people forget |
| GitHub plan decision | You | See the Challenge 3 blocker above. **Team or Enterprise Cloud if the repositories are private** |
| GitHub Copilot Business seats | GitHub org admin | One per participant who will use either Copilot path |
| Defender for Cloud paid plans authorized | Subscription owner | Five pricing resources plus a subscription budget. Costs are in [the cost estimate](CostEstimate.md) |
| SRE Agent region confirmed | You | Confirm the Azure SRE Agent is available in your chosen region and that the four-agent-unit hourly charge is authorized |
| Teardown date and owner | You | Put it in a calendar with a person's name on it. An un-destroyed cohort costs $11,700–$15,900 per month |

### T-7 working days — foundations

**1. Bootstrap the Terraform remote state.** Terraform state contains every generated
secret in clear text — participant passwords, database passwords, performance keys. A
local `terraform.tfstate` is not acceptable for a real cohort.

```bash
LOCATION=swedencentral
RG=rg-microhack-tfstate
SA=stmhtfstate$RANDOM$RANDOM          # must be globally unique, 3-24 lowercase alphanumerics

az group create --name "$RG" --location "$LOCATION"

az storage account create \
  --name "$SA" --resource-group "$RG" --location "$LOCATION" \
  --sku Standard_LRS --kind StorageV2 \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false \
  --allow-shared-key-access false \
  --https-only true

az storage account blob-service-properties update \
  --account-name "$SA" --resource-group "$RG" \
  --enable-versioning true --enable-delete-retention true --delete-retention-days 30

az storage container create \
  --name baseinfra --account-name "$SA" --auth-mode login

az role assignment create \
  --role "Storage Blob Data Contributor" \
  --assignee "$(az ad signed-in-user show --query id -o tsv)" \
  --scope "$(az storage account show --name "$SA" --resource-group "$RG" --query id -o tsv)"
```

`--allow-shared-key-access false` is deliberate: it forces Microsoft Entra authentication
so that a leaked storage key cannot read your state. Then:

```bash
cd baseInfra/terraform
cp backend.hcl.example backend.hcl        # backend.hcl is git-ignored
# edit backend.hcl: set storage_account_name to $SA
terraform init -backend-config=backend.hcl
```

Give the same Storage Blob Data Contributor role to any co-facilitator who will run
Terraform. Do not put the storage account in the workshop subscription you plan to destroy.

**2. Run the capacity preflight.** It now counts the network footprint, which earlier
versions excluded. This is the one facilitator step that is not bash — it is a PowerShell
script, so run it in `pwsh`:

```pwsh
./baseInfra/scripts/preflight-capacity.ps1 `
  -SubscriptionId '<facilitator-provided-subscription-guid>' `
  -Locations @('swedencentral', 'germanywestcentral') `
  -ParticipantCount 30 `
  -VmSize 'Standard_D2as_v5' `
  -OsDiskSizeGiB 127 `
  -MaximumEstimatedMonthlyCostUsd 20000
```

It fails closed on regional vCPU, VM-family vCPU, VM count, Premium managed disk, Standard
public IP, and NAT gateway quota. Per participant it counts **2 VMs, 2 OS disks, 1 Bastion
host, 1 NAT gateway, and 2 Standard public IPs**. Azure exposes no Bastion quota metric, so
the script counts Bastion hosts already deployed in each region and compares the total
against `-BastionHostsPerRegionLimit` (default 50).

Check two fields in the output before you move on:

- `quotaMetricsUnavailable` — metrics Azure did not return. Confirm those by hand in
  **Subscription → Usage + quotas**; the script cannot enforce what Azure will not report.
- `pricesUnavailable` — meters missing from the estimate. The total is understated by
  whatever is listed.

**3. Prepare the GitHub organization.** Follow `baseInfra/github/README.md`, then build the
roster:

```bash
cd baseInfra/github
cp users.yaml users.local.yaml            # users.local.yaml is git-ignored
# replace the placeholders with real GitHub logins
USERS_FILE=users.local.yaml uv run python main.py
```

`baseInfra/github/users.yaml` in the repository contains deliberately non-existent
placeholder handles so that an accidental run invites nobody. **Never commit a real
roster** — participant handles are personal data and this repository is public. Keep the
roster length equal to `n` in your Terraform variables so every GitHub repository has a
matching Azure resource group.

**4. Re-pin the VM source commit.**

> **Warning — the default `source_commit` is stale and will hand participants a broken
> tree.** The default pinned in `baseInfra/terraform/variables.tf` is a historical commit
> whose tree contains **no `infra/` directory**, no `catalog-migrate` tooling, and only a
> third of the challenge folders. Provisioning downloads a zip of exactly that commit to
> `C:\MicroHack\source`, so participants would be reading instructions that reference files
> their VM does not have. Re-pin it for every delivery.

The commit must be **published to GitHub before you provision**, because the provisioner
downloads a GitHub archive — a local-only SHA will fail the download, not just the digest
check.

1. Push the workshop commit to the source repository and record its full 40-hex SHA:

   ```bash
   COMMIT=$(git rev-parse HEAD)         # must already be pushed
   echo "$COMMIT"
   ```

2. Verify the published archive actually contains the workshop assets. Do this before you
   trust the SHA, not after thirty VMs have built from it:

   ```bash
   REPO=CZSK-MicroHacks/MicroHack-AppInnovation
   curl -fsSL -o source.zip "https://github.com/$REPO/archive/$COMMIT.zip"
   unzip -Z1 source.zip | sed 's|^[^/]*/||' | awk -F/ 'NF>1{print $1"/"$2}' | sort -u | head -40
   ```

   Confirm you can see `infra/`, `workshop/contracts/`, `tests/acceptance/`, and **all**
   challenge folders under `challenges/`. If any are missing, you picked the wrong commit.

3. Record the archive digest and set both values:

   ```bash
   shasum -a 256 source.zip          # or: sha256sum source.zip
   rm source.zip
   ```

   Put `source_commit = "<40-hex sha>"` in your tfvars and export the digest as
   `TF_VAR_source_archive_sha256`. Provisioning verifies the digest before expanding the
   archive, so a mismatch fails closed rather than silently installing the wrong tree.

Changing `source_commit` after provisioning **re-images every VM** — see the warning in
[Reset one participant](#reset-one-participant). Get this right before T-2.

### T-5 working days — the golden environment

This step exists to break a circular dependency, and it is the step most likely to be
skipped by someone reading the chapters in order.

**The problem.** Challenge 5 requires a seed snapshot containing four non-empty signals —
image vulnerability assessment, recommendations, Secure Score, and Microsoft cloud security
benchmark controls — with recommendation coverage across a .NET VM, a Java VM, a container
app, a container registry, and a database. Image vulnerability findings only exist after
Defender has scanned an image that has actually been pushed to a registry. Participants do
not push an image until Challenge 1, and Defender findings take **up to 24 hours**. The
snapshot therefore cannot be produced from participant environments during the workshop.

**The fix: build a facilitator-owned golden environment before participant environments
exist.**

1. **Provision one extra participant slot for yourself.** Run the base Terraform with `n`
   set to one more than your cohort and treat the last index as your own. That gives you a
   real `dotnet-vm` and `java-vm` under the subscription, which the recommendation coverage
   requires.
2. **Deploy the Azure target into that slot** from `infra/main.bicep`, exactly as a
   participant would in Challenge 1. Push the reference container image so the registry has
   real content to scan. Deploy the database. You now have all five resource kinds.
3. **Enable the Defender foundation** with `enable_defender_foundation=true`,
   `defender_facilitator_authorized=true`, a positive budget amount, and at least one
   notification email. Complete the Owner-only **Serverless Containers** portal preflight —
   the pricing API does not expose that switch, which is why Terraform does not model it.
4. **Wait at least 24 hours.** This is the reason the golden environment is a T-5 task and
   not a T-2 one.
5. **Record the two legacy VMs** in `evidence/defender/foundation/legacy-vm-coverage.json`.
   Nothing else in the repository produces this file, and both the capture in step 6 and the
   participant validator in `solutions/ch05-defender/README.md` refuse to run without it. Run
   this from the repository root, in `pwsh`. Both resource IDs belong to the golden slot you
   provisioned in step 1 — `az vm list --resource-group <facilitator-provided-golden-rg>
   --query '[].id' --output tsv` prints them — and the VM your golden handoff names at
   `network.migrationSourceVmResourceId` has to be one of the two, because the participant
   validator matches it by resource ID:

   ```pwsh
   & {
     $ErrorActionPreference = 'Stop'
     $Vms = @(
       @{ workload = 'dotnet'; resourceId = '<facilitator-provided-dotnet-vm-resource-id>' },
       @{ workload = 'java'; resourceId = '<facilitator-provided-java-vm-resource-id>' }
     )
     $Captured = foreach ($Vm in $Vms) {
       $Body = az resource show `
         --ids $Vm.resourceId `
         --api-version 2024-11-01 `
         --output json | ConvertFrom-Json
       if (-not $Body -or $Body.properties.provisioningState -ne 'Succeeded') {
         throw "The $($Vm.workload) VM returned no provisioned body: $($Vm.resourceId)"
       }
       [ordered]@{
         workload = $Vm.workload
         request = [ordered]@{ method = 'GET'; resourceId = $Vm.resourceId }
         response = [ordered]@{ statusCode = 200; body = $Body }
       }
     }
     if (@($Captured).Count -ne 2) { throw 'Both VMs must be captured.' }
     New-Item -ItemType Directory -Force -Path 'evidence/defender/foundation' | Out-Null
     [ordered]@{
       schemaVersion = '1.0.0'
       observedAt = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
       apiVersion = '2024-11-01'
       virtualMachines = @($Captured)
     } | ConvertTo-Json -Depth 64 |
       Set-Content -Path 'evidence/defender/foundation/legacy-vm-coverage.json' -Encoding utf8
   }
   ```

   The `& { … }` wrapper makes the whole capture one unit, so a VM that returns nothing —
   wrong subscription, wrong ID, or one that never finished provisioning — stops the block
   before anything is written, instead of leaving a half-file that step 6 fails on with a
   message about the artifact rather than about the capture that produced it. Note that
   `az vm show` has no `--api-version`, which is why this issues the GET through
   `az resource show`.
   `workshop/contracts/defender-legacy-vm-coverage.schema.json` is the authority and
   `workshop/contracts/fixtures/defender/legacy-vm-coverage.json` shows the exact shape. No CLI
   in this repository validates this one artifact against that schema offline, so its first
   real check is step 6, which reads it and refuses any VM outside the golden subscription.
6. **Capture the seed snapshot with the script**, from the repository root. This is the one
   step you should not do by hand:

   ```pwsh
   ./baseInfra/scripts/seed-defender-findings.ps1 `
     -SubscriptionId '<facilitator-provided-golden-subscription-guid>' `
     -HandoffPath 'workshop/golden/dotnet-sqlserver/modernization-contract.json' `
     -LegacyVmCoveragePath 'evidence/defender/foundation/legacy-vm-coverage.json'
   ```

   It issues the four Azure Resource Manager GETs at exactly the scopes and API versions the
   frozen Defender contract names, writes each verbatim response into a digest-bound envelope
   under `evidence/defender/foundation/` — `seed-recommendations.json`,
   `seed-secure-score.json`, `seed-mcsb.json`, and `seed-image-assessment.json` — then writes
   `seed-snapshot.json` and prints a JSON summary of what it captured. Both path parameters
   are resolved against your working directory, which is why the block says repository root.

   Four things are worth knowing before you run it:

   - **It needs the golden handoff**, because it binds the snapshot to that handoff's
     registry, repository, image digest, container app, and database server, and it refuses
     any resource outside the golden subscription. The handoff is the T-4 task below, built
     in this same environment — so let the 24-hour wait and the handoff build overlap, and
     come back to this step once the handoff exists.
   - **It fails closed on every assertion the participant validator later makes**: the pinned
     Azure CLI (`2.80.0`, from `workshop/toolchain.lock.json`), the frozen contract version,
     four non-empty responses, recommendation coverage of all five resource kinds with at
     least one unhealthy finding, the subscription `ascScore` record, and an image
     subassessment bound to the exact handoff repository and `sha256:` digest. A snapshot
     that would not survive grading is never written at all. That is the whole reason to
     prefer this over five GETs typed into a terminal at the end of a long week.
   - **It does not capture attack paths.** That signal is a Resource Graph POST and the
     script accepts only GET query contracts. Take it by hand from the table below.
     `workshop/contracts/defender.json` marks its results optional, so an empty response is
     fine — but the query still has to have been made.
   - **It changes nothing.** No plan is enabled, no resource is modified, no credential is
     printed.
7. **Validate and distribute.** Check the snapshot against
   `workshop/contracts/defender-seed-snapshot.schema.json`, then ship it with the participant
   materials next to the other foundation artifacts. Participants investigate your snapshot;
   they never enable a plan and never wait 24 hours.

**If the script will not run** — most often a different Azure CLI than the pinned one, or a
finding that has not surfaced yet — capture the artifacts by hand instead, and use this same
table for the attack-paths query in either case. Each is a plain Azure Resource Manager GET,
plus one Resource Graph query:

| Signal | Request |
| --- | --- |
| Image assessment | `GET {ACR_RESOURCE_ID}/providers/Microsoft.Security/assessments/c0b7cfc6-3172-465a-b378-53c7ff2cc0d5/subAssessments?api-version=2019-01-01-preview` |
| Recommendations | `GET {SUBSCRIPTION_SCOPE}/providers/Microsoft.Security/assessments?api-version=2020-01-01` |
| Secure Score | `GET {SUBSCRIPTION_SCOPE}/providers/Microsoft.Security/secureScores?api-version=2020-01-01` |
| Benchmark controls | `GET {SUBSCRIPTION_SCOPE}/providers/Microsoft.Security/regulatoryComplianceStandards/Microsoft-cloud-security-benchmark/regulatoryComplianceControls?api-version=2019-01-01-preview` |
| Attack paths | `POST https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01` with a `securityresources \| where type == 'microsoft.security/attackpaths'` query |

The exact commands, with their fail-closed assertions, are in
`solutions/ch05-defender/README.md`. Attack paths may legitimately return empty; the
other four may not.

By hand you must also write `evidence/defender/foundation/seed-snapshot.json` yourself. For
each artifact it records the file path, its SHA-256, the timestamp it was queried at, the
scope resource ID, and the API version — plus, for the image assessment, a `completed` status
and the `sha256:` image digest.

**Verify before you stop:** the recommendations artifact must cover all five resource kinds
and contain at least one unhealthy recommendation. The script enforces this and refuses to
write a snapshot without it; by hand, nothing checks it but you. Either way, if a resource
kind is missing then your golden environment is missing a resource — fix that and re-capture,
do not hand-edit the snapshot.

### T-4 working days — build the golden handoffs

> **These do not exist in the repository.** `docs/Design.md` calls a prevalidated
> stack-matched golden handoff "the only supported workshop rejoin mechanism", and the
> root README promises participants that you can hand them one. The `evidence/` directory
> is empty, and `workshop/golden/*/modernization-contract.json` is gitignored precisely
> because it is specific to one delivery. **You must produce both of them yourself, ahead of
> the workshop.** If you skip this, any participant who falls behind in Challenge 1 is stuck
> there for the rest of the two days.
> [`workshop/golden/README.md`](../workshop/golden/README.md) is the short version of
> everything below, including the validation command and the requirement to keep the
> environment alive until the workshop ends.

They cannot be faked. A handoff is rendered by `catalog-migrate render-handoff` from real
evidence files, and the validator checks file digests, producer identities, resource
relationships, and the live-vs-fixture boundary. A hand-edited handoff is the one failure
mode this workshop treats as fatal — and the same rule applies to you.

**Complete one full Challenge 1 run per stack**, in a facilitator-owned environment, and
preserve the result. Two runs, one for `dotnet-sqlserver` and one for `java-postgresql`.
**Budget two full days, or split the two stacks across two facilitators.** The chapter's own
estimate is 5–12 hours per stack, so two stacks is 10–24 hours — the lead-time table above
says 1–2 days for the same reason, and a single day only works if both runs land at the
bottom of that range. The golden environment you built at T-5 is the natural place to do
this.

Any of the three Challenge 1 paths produces a valid handoff. Use **manual** unless you have
a reason not to — `solutions/ch01-manual/<stack>/README.md` contains every command in
executable form, and the resulting `path` value (`manual`) is legal for every downstream
chapter.

#### What to capture, and where

Store each completed run under `workshop/golden/<stack>/`. Both directories already exist,
named with the schema's own stack identifiers so there is no ambiguity about which one a
participant is being given:

```
workshop/golden/dotnet-sqlserver/
  modernization-contract.json      # the handoff itself
  azure-target-output.json
  migration-report.json
  acceptance-report.json
  telemetry-report.json
  runtime-test-report.json
  rollback-runbook.md
  README.md                        # which environment, when, by whom
workshop/golden/java-postgresql/
  ...same set...
```

Everything the go/no-go matrix's **Golden rejoin** row demands is already inside the
contract. Before you call a run "golden", open `modernization-contract.json` and confirm
each of these is populated with values from your real run:

| Requirement | Contract fields |
| --- | --- |
| Immutable image | `containerImage.registryResourceId`, `.registry`, `.repository`, `.tag`, `.digest` — the digest must be a `sha256:` value, never a tag |
| Immutable source | `source.stack`, `.runtimeVersion`, `.frameworkVersion`, `.commitSha` — `commitSha` must match the commit you re-pinned at T-7 |
| Azure resource IDs | `application.resourceId`, `.url`, `.healthUrl`, `.readinessUrl`, `.region`, `.resourceGroup`, `.containerAppName`, `.revisionName`; plus `database.resourceId` and `images.resourceId` |
| Migration evidence | `database.migrationMechanism`, `.migrationVersion`, `.seedManifestVersion`, `.verifiedRowCounts`, `.applicationPrincipal`; `evidence.migrationReport` |
| Runtime evidence | `evidence.runtimeTestReport` |
| Acceptance evidence | `acceptance.report`, `.profile`, `.result` |
| Telemetry evidence | `observability.applicationInsightsResourceId`, `.logAnalyticsWorkspaceResourceId`, `.serviceName`, `.revision`; `evidence.telemetryReport` |
| Rollback | `rollback.targetRevision`, `.runbook` — the baseline revision must still exist and still be a valid rollback target |
| Identity | `authentication.containerRegistry`, `.database`, `.imageStore`, `.telemetry` |

`sliceId` will be one of `manual-dotnet`, `manual-java`, `copilot-rewrite-dotnet`,
`copilot-rewrite-java`, `copilot-modernization-dotnet`, `copilot-modernization-java`. It
encodes both the path and the stack, so it is the fastest way to check you are handing a
participant the right file.

#### Validate before the workshop, not during it

Run the shared handoff validator against both. It is the same validator the participants
use, so a green result here is a green result on the day:

```bash
cd tests/acceptance
uv --no-config run python -m catalog_acceptance.handoff_cli \
  ../../workshop/golden/dotnet-sqlserver/modernization-contract.json \
  --contracts ../../workshop/contracts \
  --repository-root ../..
```

Repeat for `java-postgresql`. Both must exit `0`. Re-run this at T-1 as part of the smoke
checks — a golden handoff can go stale if you deleted the environment it points at.

#### How a participant rebinds a golden handoff

A golden handoff points at **your** Azure resources. Handing it over unchanged is only half
the job: Challenges 2 through 6 read the handoff *and* act on the resources it names, so a
participant with your handoff would be driving your environment.

Give the participant a golden handoff **plus** access, in one of two ways:

| Model | What you do | Trade-off |
| --- | --- | --- |
| **Shared golden environment** (recommended) | Grant the participant `Reader` on the golden resource group, plus the specific roles the next chapter needs. They use the handoff as-is | Fastest. Several participants share one environment, so Challenge 3's deployments and Challenge 6's drills will collide if more than one person is rejoining |
| **Rebound copy** | Redeploy `infra/main.bicep` into the participant's own resource group, redo the migration and image push, then **re-render** the handoff with `catalog-migrate render-handoff` against their outputs | Clean isolation, but it is most of Challenge 1 again — roughly an hour of your time per participant |

Whichever you choose, **never hand-edit the JSON to swap resource IDs**. The validator
checks digests and resource relationships and will reject it, and even if it did not, the
participant would be carrying a document that lies about what it observed. If a resource ID
must change, re-render.

Tell the receiving participant explicitly which model they are on, and that their Challenge
1 evidence is the facilitator's rather than their own — Challenge 6's honesty exercise
depends on people knowing which claims they can personally vouch for.

#### Rehearse the 15:15 cut before you have to perform it

The golden-handoff cut is the only lever you have against the overrun the
[agenda](Agenda.md#the-honest-arithmetic) discloses, and until you pull it once it is a
lever nobody in this repository has ever pulled. Rehearse it in the same sitting you build
the handoffs, while the environment is fresh and what it tells you is still cheap to fix.

`golden-dryrun` validates the *bundle* for you. It walks the same seven checks in T-4 order,
stops at the first defect, and is the same command the T-1 smoke table requires to exit `0`
before the room arrives — see
[T-1 working day](#t-1-working-day--smoke-and-distribute). Run it here as well as there, so
that a defect you can still fix cheaply is found in this sitting rather than the night before.

What it does not do is time the *cut*. The wall clock below, the transcript, and the note
about what needed a second attempt are yours to keep, and nothing automates any of them.
Keep them anyway. The 1–2 days in the lead-time table is the chapter's estimate inherited,
not a figure anybody measured, and yours would be the first.

**1. Time the build while you do it.** Wall clock, not effort — the waiting is the part
that surprises people:

| Step | `dotnet-sqlserver` | `java-postgresql` |
| --- | --- | --- |
| Bootstrap and baseline deployments | | |
| Database migration and verified row counts | | |
| Image build and push, then the release deployment | | |
| Render the handoff and get the validator to exit `0` | | |
| **Total wall clock** | | |

Write both totals into `workshop/golden/<stack>/README.md`, next to which environment and
which date. The next delivery then plans from a measurement instead of from this page.

**2. Prove the handoff still describes something alive.** The validator checks the
document; this checks the deployment the document points at:

```bash
jq -r '.application.healthUrl, .application.readinessUrl' \
  workshop/golden/dotnet-sqlserver/modernization-contract.json \
  | xargs -n1 curl -fsS -o /dev/null -w '%{http_code}  %{url_effective}\n'
```

Two `200` lines, and repeat for `java-postgresql`. Anything else means the handoff points
at resources that have been scaled to zero, moved, or deleted — the failure a participant
would otherwise meet at 15:16, when you have no second answer for them.

**3. Rehearse the handover as the person receiving it.** Sign in as a *second* identity
holding only what a rejoining participant will hold under the model you chose above, and
read the handoff the way the next chapter does:

```bash
HANDOFF=workshop/golden/dotnet-sqlserver/modernization-contract.json
az containerapp show \
  --name "$(jq -r .application.containerAppName "$HANDOFF")" \
  --resource-group "$(jq -r .application.resourceGroup "$HANDOFF")" \
  --query "properties.latestRevisionName" -o tsv
```

`AuthorizationFailed` here means your grant is short, and you have found it at T-4 rather
than in front of somebody at 15:15. Fix the grant, never the handoff.

**4. Write down what needed a second attempt.** Whatever went wrong once will go wrong
again next delivery, and three honest lines in `workshop/golden/<stack>/README.md` are
worth more to the next facilitator than the timings are.

**5. Record the tree you rehearsed against.** A rehearsal result is only evidence if you can
say which repository produced it. From the repository root:

```bash
git rev-parse HEAD
```

Write that commit into `workshop/golden/<stack>/README.md` beside the timings and the
rehearsal outcome, and carry it into your run log. It is what makes anything that goes wrong
on the day reproducible; without it, "it worked at T-4" is a claim nobody can check
afterwards.

Do not go looking for a delivery baseline committed somewhere in this repository, and do not
add one. A commit cannot contain its own hash, so a SHA written into a tracked file always
names the commit *before* the tree you are delivering — wrong by exactly one, and it looks
right. The baseline is a fact about one delivery, not about the repository, which is the same
reason `TF_VAR_source_archive_sha256` is captured at run time and `sourceCommit` appears in
no parameter file.

### T-3 working days — SRE Agent foundation

**Decide the model first, because it changes your workload by an order of magnitude.**

The code supports **one agent per team**: `infra/sre-agent.bicep` takes a `teamName`
parameter, derives `rg-sre-${teamName}` and `sre-catalog-${teamName}` from it, and asserts
that the agent resource group is separate from the workload's. Challenge 6 tells the
participant that "one dedicated agent resource exists for your team".

This is the one template you deploy at subscription scope, for the reason given in
[Who holds what rights, and when](#who-holds-what-rights-and-when): it defines a custom
role, and a custom role definition cannot be scoped to a resource group. It is yours to run,
never a participant's.

| Model | Facilitator build time | Hourly cost | Use when |
| --- | --- | --- | --- |
| **One agent per team** | 45–60 min × N teams | $0.44 per team per hour (4 agent units × $0.11) | Up to about ten teams |
| **One shared agent, facilitator-led** | 45–60 min once | $0.44 per hour total | Above about ten teams |

At 30 teams the per-team model is **22–30 hours** of facilitator hand-work and **$13.20 an
hour** while the cohort runs. That does not fit into a delivery plan. For a typical
30-person cohort, build **one** foundation and run Challenge 6 as a facilitator-led
investigation — the reasoning exercise in Task 3, where participants argue against the
agent's hypothesis, works at least as well as a group exercise.

For each foundation you build, the manual portal work is:

1. Deploy `infra/sre-agent.bicep` for the team, after reviewing the what-if and explicitly
   authorizing the four-agent-unit hourly cost.
2. Configure the Azure Monitor response plan `catalog-reviewed-rollback` in **Review** mode
   with **Low** action access, quickstart disabled, alert titles prefixed `MH-SRE-`,
   participant approval disabled, and facilitator approval required. The Bicep reports
   `responsePlanConfiguredInIaC: false` because this is portal-only work.
3. Create and bind one Sev2 log alert.
4. Send a harmless test incident and **Reject** it. Export the portal state to
   `evidence/sre-agent/response-plan-preflight.json` with producer
   `azure-portal-facilitator-export`.
5. Create the drill revision at zero traffic, before the incident window.

During Challenge 6, **only you** click **Approve**. Participants hold SRE Agent Standard
User; you hold SRE Agent Administrator.

### T-2 working days — provision participants

Before you plan, put the facilitator identity in your tfvars. `infra/main.bicep` requires
`facilitatorPrincipalName` and `facilitatorPrincipalObjectId` on every Challenge 1
deployment, and Terraform is what carries them to the participant VMs. Both are required
inputs with no defaults, so a missing one fails at plan instead of in the room:

```bash
az ad signed-in-user show --query id -o tsv        # the object ID, when you use your own account
az ad group show --group '<facilitator group>' --query id -o tsv   # or the group's
```

```hcl
facilitator_principal_name      = "you@yourcompany.onmicrosoft.com"
facilitator_principal_object_id = "00000000-0000-0000-0000-000000000000"
```

Neither is a secret, so keep them in the tfvars file next to `source_commit` rather than in
an environment variable. Changing either one after provisioning **replaces both VMs** — the
values travel in VM custom data, which Azure will not let you update in place.

```bash
cd baseInfra/terraform
export TF_VAR_admin_password='<strong-facilitator-secret>'
export TF_VAR_capacity_preflight_confirmed=true
export TF_VAR_source_archive_sha256='<facilitator-recorded digest from re-pinning the source commit>'

terraform init -backend-config=backend.hcl
terraform plan -var-file local.tfvars -out tfplan
terraform show tfplan            # review the doubled footprint and every replacement
terraform apply tfplan
```

Never use `-auto-approve` here.

Terraform generates a **separate initial password for every participant** and sets
`force_password_change = true`, so each participant changes it at first sign-in. Read them
only when you are ready to hand them out:

```bash
terraform output -json entra_user_credentials | jq .
```

Send one row per participant over a private channel. Do not paste the whole map into a chat
room: the user principal names are predictable (`userNNN@<domain>`) and every participant
holds Owner on their own resource group, so one leaked password is enough to sign in as
somebody else.

#### The deployment parameter files provisioning writes for you

You do not hand-write Bicep parameter files. Every Challenge 1 runbook deploys with
`--parameters '@C:\protected\<path>-<stack>-<stage>.json'`, and
`baseInfra/scripts/provision-vm.ps1` writes those files on each VM, for that VM's own stack
only — nine files, one per path and stage:

```
C:\protected\manual-dotnet-{bootstrap,baseline,release}.json
C:\protected\copilot-rewrite-dotnet-{bootstrap,baseline,release}.json
C:\protected\copilot-modernization-dotnet-{bootstrap,baseline,release}.json
```

and the matching `-java-` set on the java VM. They are standard ARM parameter documents
carrying everything that is knowable before the workshop: the deployment stage and revision
role, the stack, the frozen `imageProvider` and PostgreSQL authentication mode for that
path, the participant's own `resourceGroupName` and `teamName`, the exact source VNet and VM
resource IDs, your `facilitatorPrincipalName` and `facilitatorPrincipalObjectId`, and the
generated `performanceApiKey`.

Two things are deliberately **not** in them. `sourceCommit` and `imageDigest` are not
knowable at T-1, and a placeholder would satisfy the template's format asserts while
deploying the wrong source, so the runbooks pass them as `--parameters` overrides on the
command line and a forgotten one fails loudly. The Java database passwords stay on the
interactive protected prompt.

The files carry no participant work and are rewritten on every provisioning run, so
re-provisioning a VM is safe. `C:\protected` is SYSTEM/Administrators FullControl plus
**Read for the VM's own admin account**, which is what lets a participant deploy from the
ordinary PowerShell session they already have open. That grant is not a loosening: the
account is a local administrator and could read the folder by elevating anyway. It exists
because `azureuser` is a *custom* admin, so UAC hands an unelevated shell a filtered token
— without the Read ACE the first `az deployment group create` of Challenge 1 dies on
`Access is denied`, in a session the participant has no reason to suspect is under-
privileged. The database passwords under `C:\MicroHack\secrets` do **not** get this grant
and stay administrators-only.

#### `performanceApiKey` — the one parameter that spans two deployments

Of everything in those files, this is the value most likely to bite you, because it is the
only one that has to agree across two deployments nobody runs at the same time.

`infra/main.bicep` declares it `@secure()` and then asserts on it:

```bicep
assert applicationSecretsArePresent = !isApplication || !empty(performanceApiKey)
```

So an application-stage deployment — every `baseline` and `release` in Challenge 1 — **fails
at deploy time** if the key is empty. It is not optional and it has no working default. When
present, `infra/main.bicep` stores it as the `performance-api-key` Container Apps secret and
surfaces it to the application as `PERFTEST_API_KEY`; that is the shared secret Challenge 2's
load test authenticates with.

Terraform generates a distinct 48-character key per participant *per stack* and the
provisioner writes it into all nine parameter files on that VM, so Challenge 1 needs nothing
from you. Challenge 2 is where the two halves have to meet: `infra/perf-testing.bicep`
creates the Key Vault and the role assignments but **not the secret value**, and the load
test reads the key from that secret. If you invent a Key Vault value instead of copying the
generated one, Challenge 1 deploys fine and every load-test sampler comes back
`401 {"status":"unauthorized","error":"invalid_api_key"}` — the app compares the `x-api-key`
header against its own secret, so nothing in the deployment looks wrong. Read the real keys
and use them:

```bash
terraform output -json performance_api_keys | jq .
```

The output is marked sensitive, keyed by participant index, then by stack. Treat it like the
credential map: read it when you are ready to set the secrets, not before.

### T-1 working day — smoke and distribute

| Check | How |
| --- | --- |
| Every VM provisioned healthy | `C:\MicroHack\status\dotnet-smoke.json` and `java-smoke.json` on each VM; both must pass `/healthz`, `/readyz`, the canonical image, the `198/20/198` corpus, and the native database counts |
| **Source tree is the one you pinned** | On one VM, read `C:\MicroHack\source\.source-commit` and confirm it matches your `source_commit`. Confirm `C:\MicroHack\source\infra` and every `challenges\*` folder exist |
| **Deployment parameter files exist** | On one VM, in an ordinary **non-elevated** PowerShell — the session a participant has — `(Get-ChildItem C:\protected\*-<stack>-*.json).Count` returns `9`, and `$p = (Get-Content C:\protected\manual-<stack>-baseline.json \| ConvertFrom-Json).parameters; $p.facilitatorPrincipalObjectId.value; [bool]$p.performanceApiKey.value` shows your object ID and `True`. Run it unelevated on purpose: that is the session Challenge 1 deploys from, so it also proves the Read ACE landed. `Access is denied` here means the grant is missing and every participant stops on their first deployment |
| Bastion access works | Connect to at least one VM per region |
| **A participant can write where the work happens** | In that same non-elevated session, `New-Item C:\MicroHack\source\.t1-probe -ItemType File` must **succeed** and `New-Item C:\protected\.t1-probe -ItemType File` must **fail** with `Access is denied`. Remove the probe afterwards. The first proves Challenge 1 can commit and build in the tree it was given; the second proves the parameter files cannot be edited into something that no longer matches the deployment they describe. A VM that passes the read check above and fails this one has the wrong ACL rather than a missing one |
| **A participant can create the migration export directory** | **Confirmation, not discovery.** `baseInfra/scripts/provision-vm.ps1` now creates `C:\ProgramData\MicroHack\migration` itself and places an explicit **Modify** ACE for `admin_username` on it (`New-MigrationExportDirectory`, using the same `Set-ProtectedAcl` call that grants read on `C:\protected`), so the permission is asserted at provisioning time instead of inherited from a folder created as SYSTEM. Confirm it held: in that same non-elevated session, `New-Item C:\ProgramData\MicroHack\migration\.t1-probe -ItemType File` must **succeed**. Remove the probe but **leave the directory** — deleting it discards the ACE that makes this work. All six Challenge 1 path documents create the directory with `New-Item -Force` before writing the database export, so on a correctly provisioned VM that line is now a no-op. If the probe fails with `Access is denied`, do not re-image — [editing a provisioning script re-provisions every VM](#reset-one-participant) — fix the ACL in place, per VM: `az vm run-command invoke -g <rg> -n <vm> --command-id RunPowerShellScript --scripts 'New-Item -ItemType Directory -Force C:\ProgramData\MicroHack\migration > $null; icacls C:\ProgramData\MicroHack\migration /grant azureuser:(OI)(CI)M'`, substituting your own `admin_username` if you changed it from `azureuser`. Left unfixed, every participant loses their database export, which is the artifact Challenge 1 exists to produce |
| Load Testing prerequisites exist | Deploy `infra/perf-testing.bicep` and set the performance-test API-key secret in the Key Vault it creates to the value `terraform output -json performance_api_keys` reports for that participant and stack. A secret that does not match the generated key fails Challenge 2 with a 401, not a deployment error |
| GitHub repositories exist and the plan supports environment protection | Create the `staging` and `production` environments on one repository and confirm the required-reviewers setting is actually available |
| **Each participant knows their repository HTTPS URL** | Challenge 1 ends with `git push` from the VM, and every runbook asks for a *facilitator-provided* HTTPS URL. Put each participant's URL somewhere they can copy it without typing — the same place you put their resource group name. A URL that has to be dictated across a room costs more time than it sounds like, and a mistyped one fails at the push, after the work is done |
| **A test push succeeds from one VM** | Do this yourself before the room arrives. Push a throwaway commit from a provisioned VM to a scratch repository in the same organization. This proves Git Credential Manager opens its browser sign-in on the VM, that the network permits it, and that your organization's SSO or device policy does not block it — the three things that turn Challenge 1's last step into a room-wide stall |
| Copilot seats are assigned | Have one participant sign in and confirm the extension is healthy |
| **Both golden handoffs validate** | `uv --no-config run golden-dryrun ../../workshop/golden/dotnet-sqlserver` from `tests/acceptance`, then the same for `java-postgresql`. Both must exit `0`, and both `healthUrl`s must still answer `200` — see [Rehearse the 15:15 cut](#rehearse-the-1515-cut-before-you-have-to-perform-it), step 2 |
| Seed snapshot validates | Re-run the schema validation |
| Budget alert is live | Confirm it sends mail to a human |

---

## What the participant VMs do and do not have

Two questions come up on the morning of every delivery. Answer them before they are asked.

**There is `git` on the VMs, and it is pinned like everything else.**
`baseInfra/scripts/provision-vm.ps1` installs Git for Windows `2.55.0.windows.5` from
`workshop/toolchain.lock.json`, verifying its SHA-256 and its `Johannes Schindelin`
Authenticode publisher before installing — the same treatment VS Code, Azure CLI and uv
get. Pinning it is what makes it consistent with the frozen toolchain rather than a
source of drift.

The source tree is still delivered as an immutable GitHub archive expanded to
`C:\MicroHack\source`, so it carries no history of its own. Provisioning therefore runs
`git init` there and makes one baseline commit, which is what makes the Copilot paths'
commit-per-slice method actually executable on the VM.

**This creates two different SHAs, and confusing them is the single most likely support
question of the day:**

| SHA | Where it comes from | What it means |
| --- | --- | --- |
| `git rev-parse HEAD` | The participant's own commits in `C:\MicroHack\source` | Identity of *their* modernization work. Image tags, Container Apps revisions, migration reports and handoffs all bind to this. |
| `C:\MicroHack\source\.source-commit` | Written by the provisioner at extraction time | Which upstream archive this VM was built from. Provenance only. |

They are unrelated values. A participant who pastes `.source-commit` where their own
commit belongs will get a handoff rejection that looks like a validator bug and is not.

Practical consequences to relay:

- Participants **can** `git add`, `git commit`, `git status` and `git rev-parse` locally.
  They **cannot** `git log` into upstream history or `git clone` from the archive — there
  is only the one baseline commit, because the source never was a clone.
- The participant's *own* work is pushed to their GitHub repository **from the VM**, on the
  `workshop` branch. Git Credential Manager is installed with Git, so the first `git push`
  opens a browser sign-in rather than stalling on a credential prompt. Expect that prompt
  around late morning and tell the room it is normal. Challenge 3 depends on this: the
  catalog workflow checks the application source out of GitHub at the commit the handoff
  names, so work that exists only on the VM cannot be built.
- If someone needs the provisioned archive SHA, it is one line:
  `type C:\MicroHack\source\.source-commit`.

**There is no Docker daemon on the VMs either.** Container images are built with
`az acr build`, which uploads the build context to Azure Container Registry and builds it
there. That is not a workaround for the missing daemon — it is the intended mechanism, and
it is why Challenge 1 works identically from a Windows Server VM with no container runtime.
It also means:

- `docker build`, `docker run`, and `docker push` will all fail. The reference solutions
  never use them.
- The image digest a participant records in their handoff comes back from ACR, not from a
  local build. That is the digest they must pin — resolve the tag to a `sha256:` value once
  and use it for both the baseline and the release deployment.
- Nothing runs the container locally. Verification happens against the deployed Container
  App revision's `/healthz` and `/readyz`.

---

## The facilitator credential sitting on every participant VM

Read this before you deliver. It is the one exposure in this workshop that nothing in the
repository currently mitigates, and it is not visible from any participant-facing page.

Every Challenge 1 runbook opens with
`$env:AZURE_CONFIG_DIR = Join-Path $HOME '.azure-365'` and describes it as "an
authenticated isolated facilitator profile". The isolation is real, but what it isolates is
that profile from the machine's *other* Azure CLI profiles. It does not isolate it from the
participant.

**What is actually on the VM.** `$HOME` in that line resolves to the Windows profile of the
account the participant signed in as through Bastion — the VM's local administrator,
`admin_username` from `baseInfra/terraform/variables.tf`, default `azureuser`. So
`C:\Users\azureuser\.azure-365` holds a signed-in Azure CLI profile: `azureProfile.json`
plus an MSAL token cache holding access and refresh tokens for whichever identity you signed
in as. Nothing constrains which identity that is, and the obvious convenience — signing in
as the subscription Owner account the T-15 table already tells you to hold — puts your
subscription-wide rights on a machine where the participant is local administrator.

That convenience buys you nothing. As set out in
[Who holds what rights, and when](#who-holds-what-rights-and-when), Challenge 1 runs
`az deployment group create` against `infra/main.bicep`, which is
`targetScope = 'resourceGroup'` and writes only inside the participant's own resource group.
The chapter does not need a subscription-scope identity at all.

**What a participant can do with it.** Nothing has to be cracked, extracted, or guessed.
Both lines below run **on the VM, in Windows PowerShell** — not in your own bash session.
The first is copied verbatim from the runbooks; the second is the same
`az account get-access-token` the runbooks already use to mint a database token, with its
`--resource` argument removed:

```powershell
$env:AZURE_CONFIG_DIR = Join-Path $HOME '.azure-365'
az account get-access-token
```

That returns a bearer token for that identity with no sign-in prompt and, unless a
conditional-access policy forces re-authentication, no second factor — the cached refresh
token has already satisfied both. The token carries whatever the identity holds. If you
signed in as subscription Owner, a participant can read, modify, or delete another
participant's resource group, change Defender pricing, edit the budget, or grant themselves
a role. The runbooks require facilitator approval before every state-changing command.
Nothing enforces that.

Two consequences are worth stating separately from the access itself:

- **Attribution is destroyed.** Every Activity Log entry made through that profile records
  *you* as the caller. If a resource group disappears, Azure's own record says the
  facilitator deleted it, and there is nothing in the platform that says otherwise.
- **It outlives the chapter.** The cache stays on disk once Challenge 1 is finished.
  No chapter after Challenge 1 references the profile, and neither the provisioning scripts
  nor any runbook removes it.

Set this against the participant-password concern in
[T-2 — provision participants](#t-2-working-days--provision-participants): a leaked password
grants Owner on one resource group and requires someone to leak something. A cached
subscription-Owner profile grants your rights across the whole subscription and requires
nobody to do anything at all.

**Mitigation, in the order that removes the most exposure.**

1. **Do not sign that profile in as your subscription Owner account.** Sign it in as an
   identity that holds Owner on that one participant resource group and nothing above it.
   `infra/main.bicep` is resource-group-scoped, so that is sufficient for the whole chapter,
   including the role assignments `modules/environment.bicep` creates and the VNet peering,
   which targets the participant's own resource group. Prove it with
   `az deployment group what-if --resource-group <their group>` before the workshop, not on
   the day. The cached token then grants exactly what the participant already has.
2. **Sign in when the Challenge 1 block starts, not at provisioning time.** A profile signed
   in at T-2 is exposed for the whole workshop instead of for one block.
3. **Sign it out as soon as the block ends,** on every VM you signed in on.

**The sign-out step.** Run this **on the VM, in Windows PowerShell**, in the participant's
own session — this is the second of the two blocks that run on a participant VM rather than
on your laptop. `az logout` drops the account from the token cache; deleting the directory is what
guarantees no token, no profile, and no CLI residue is left behind:

```powershell
$env:AZURE_CONFIG_DIR = Join-Path $HOME '.azure-365'
az logout
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $env:AZURE_CONFIG_DIR
```

Confirm it worked before you move on. `az account show` under the same
`AZURE_CONFIG_DIR` must fail rather than print a subscription.

**When to do it.**

| Moment | Why then |
| --- | --- |
| At the 15:15 golden-handoff cut on day 1 | Challenge 1 is over for everyone at that point, scheduled or not, and no later chapter uses the profile |
| Immediately, on any VM whose participant finishes Challenge 1 early | The exposure is per VM and does not need to wait for the cut |
| Before a VM is rebuilt, reassigned, imaged, or left running past teardown | The cache survives everything except destroying the disk |

If you find a profile still signed in after day 1, treat the subscription as exposed for
that window rather than assuming nothing happened: pull the Activity Log for the period and
confirm every caller entry is an action you can account for.

---

## Reset one participant

> **Warning — editing a provisioning script re-images every VM.**
> Azure VM custom data is immutable. The VM resources use `replace_triggered_by` on the
> provisioner data, so changing either provisioning script under `baseInfra/scripts/` —
> **or changing `source_commit` or `source_archive_sha256`** — replaces **both VMs for
> every participant**, destroying all of their local work. If you think you need to edit a
> script or re-pin the commit mid-workshop, you almost certainly want one of the targeted
> commands below instead. Always run `terraform plan` and read the replacement list before
> applying.

All commands below run from `baseInfra/terraform`. Substitute the participant's index for
`7`; the map key is the participant number as a string.

**Rerun provisioning on one stack, without replacing the VM** — the first thing to try when
an application will not start:

```bash
terraform apply -var-file local.tfvars \
  -replace='module.user_environment["7"].azapi_resource.vm_setup["dotnet"]'
```

**Rebuild one VM completely** — the machine is unrecoverable. This destroys everything on
that VM's disk:

```bash
terraform apply -var-file local.tfvars \
  -replace='module.user_environment["7"].azapi_resource.vm["dotnet"]'
```

**Confine the blast radius to one participant.** Add `-target` so that unrelated drift in
other participants' environments cannot be applied by accident:

```bash
terraform apply -var-file local.tfvars \
  -target='module.user_environment["7"]' \
  -replace='module.user_environment["7"].azapi_resource.vm["java"]'
```

**Rebuild a participant's whole environment** — network, Bastion, NAT gateway, both VMs.
Expect 30–45 minutes before the VMs report healthy:

```bash
terraform apply -var-file local.tfvars -target='module.user_environment["7"]'
```

**Reissue one participant's password.** Replacing the generated password forces a new one
and a fresh change-at-sign-in:

```bash
terraform apply -var-file local.tfvars \
  -replace='module.entra_users["7"].random_password.this'
terraform output -json entra_user_credentials | jq '."7"'
```

**Restore a VM a participant deallocated by mistake.** Use the Azure CLI, not Terraform —
power state is not managed by Terraform and starting the VM will not cause drift:

```bash
az vm start --resource-group rg-user007 --name vm-dotnet-user007
```

Restoring the *other* stack's VM after Challenge 0 is only appropriate for a stack-matched
golden rejoin. It is bounded to power state; it does not authorize replacing or deleting
anything.

Always finish a `-target` or `-replace` session with a full untargeted plan
(`terraform plan -var-file local.tfvars`) so you can see what the targeted runs left behind.

### Clean up after yourself on a participant VM

If you use `az vm run-command **create**` to inspect or repair a participant VM, **delete the
named command when you are finished.** A named run-command is a persistent child resource of
the VM, and a VM accepts one run-command at a time. One left behind in
`executionState: Pending` holds the participant's channel **indefinitely — unlike an orphaned
`invoke`, it does not self-clear.** The participant then sees
`Conflict: Run command extension execution is in progress` on every command they try, with no
indication that a facilitator action caused it. This happened during the pilot and cost the
participant an hour before the cause was found.

```bash
az vm run-command list -g rg-user007 --vm-name vm-java-user007 --show-details \
  --query "[].{name:name, exec:instanceView.executionState}" -o table
az vm run-command delete -g rg-user007 --vm-name vm-java-user007 \
  --run-command-name <your-stuck-command-name> --yes
```

Deleting is non-destructive — it removes the registration, not the VM or its extensions — and
the participant's next command works immediately. Prefer `az vm run-command invoke` for
one-shot facilitator inspection: it leaves nothing behind to forget. Add the `list` above to
your end-of-day sweep.

---

## Teardown

Terraform destroys the base infrastructure. It does not own most of the money.

### 1. Before you destroy anything

- Confirm every participant has exported their `evidence/` directory. Once the resource
  group is gone, it is gone.
- Capture the final cost query and record the time you ran it. Cost data lags; you will
  need to repeat it.

### 2. Things Terraform does not own — do these first

| Item | Action | Why it matters |
| --- | --- | --- |
| **SRE Agent resources** | `az resource delete` on every `Microsoft.App/agents` resource and its `rg-sre-*` resource group | **Stopping the agent does not stop billing — only deletion does.** Four agent units at $0.11 an hour, per agent, forever. Thirty forgotten agents cost $9,636 a month |
| **Defender for Cloud paid plans** | Restore every prior pricing tier, subplan, enforce value, and extension **through the portal**, plus the Serverless Containers switch. Verify the restored state, then detach the pricing objects from Terraform state: `terraform state rm 'azapi_resource.defender_pricing'` | `Microsoft.Security/pricings` DELETE is *valid only for resource scope* — it cannot remove subscription pricing objects, which is why they carry `prevent_destroy`. Terraform cannot do this for you |
| **Azure Load Testing resources and Key Vaults** | Delete the resources created by `infra/perf-testing.bicep`. Purge the Key Vaults or they occupy the name for the soft-delete retention period | Soft-deleted vaults block a re-run with the same name |
| **GitHub repositories** | Delete or archive each participant repository. `baseInfra/github/main.py` has no teardown mode, so this is manual or a `gh repo delete` loop | Participant repositories may contain workshop credentials in workflow logs |
| **GitHub Copilot seats** | Unassign every seat in **Organization → Copilot → Access** | Seats bill monthly per assigned user whether or not anyone signs in |
| **GitHub paid plan** | Downgrade the organization if you upgraded it for Challenge 3 | Per-user monthly charge |
| **Entra users** | `terraform destroy` removes them if `manage_entra_users = true`. If you created any by hand, delete those too | Predictable UPNs left active in a tenant are a standing risk |
| **Terraform state storage** | Delete `rg-microhack-tfstate` **last**, after the destroy has succeeded | It holds the secrets; it is also the only record of what existed |

### 3. Then destroy the base infrastructure

Provider registrations are protected with `prevent_destroy` and must never be
unregistered. Detach that module first:

```bash
cd baseInfra/terraform
terraform state rm 'module.resource_providers[0]'
terraform plan -destroy -var-file local.tfvars -out destroyplan
terraform show destroyplan          # read it
terraform apply destroyplan
```

### 4. Verify

```bash
: "${SUBSCRIPTION_ID:?Set the subscription you just destroyed, to verify it is empty}"

az resource list --subscription "$SUBSCRIPTION_ID" --query "length(@)"
az consumption budget list --subscription "$SUBSCRIPTION_ID" -o table
```

Repeat the cost query a few days later. Charges continue to land after resources are gone,
and a plan you thought you disabled will show up here if you did not.

### Budget alert

Create a subscription budget **before** provisioning, not after. If you are enabling the
Defender foundation, `baseInfra/terraform` creates one for you from
`defender_budget_amount` and `defender_budget_notification_emails`. If you are not, create
it by hand:

```bash
: "${SUBSCRIPTION_ID:?Set the workshop subscription the budget will guard}"

az consumption budget create \
  --subscription "$SUBSCRIPTION_ID" \
  --budget-name mh-workshop \
  --amount 5000 \
  --category Cost \
  --time-grain Monthly \
  --start-date 2026-09-01 \
  --end-date 2027-09-01
```

Then add alert thresholds at 50%, 90%, and 100% in the portal, addressed to a named
mailbox rather than a distribution list. Size it at roughly 1.5× the total in
[the cost estimate](CostEstimate.md).

---

## Per-chapter preparation at a glance

| Chapter | What you must have ready | When |
| --- | --- | --- |
| 0 — Select a baseline | Both VMs healthy per their smoke files; you available to approve each deallocation as it is requested | T-1 |
| 1 — Modernize | **Both golden handoffs built, validated, and the 15:15 cut rehearsed once** — the repository ships none, so this is real work you must do; participants steered toward a path that can finish; the timebox announced in advance; the isolated CLI profile signed out of every VM when the block ends | T-4 |
| 2 — Load and autoscaling | Load Testing resource deployed, API-key secret set in Key Vault; the filler content for 35 minutes of waiting ready to deliver | T-1 |
| 3 — CI/CD and revisions | GitHub plan and repository visibility confirmed to support environment protection; `staging` and `production` environments creatable; you or a second person available to approve | T-15 for the plan, T-1 for the check |
| 4 — Observability | Nothing beyond a validated handoff. Have the workbook deployment ready to demonstrate if you fall behind | — |
| 5 — Cloud security posture | **You** run `baseInfra/scripts/seed-defender-findings.ps1` against the golden subscription — [T-5 working days](#t-5-working-days--the-golden-environment), step 6 — never a participant. It writes `evidence/defender/foundation/seed-snapshot.json` and the four digest-bound envelopes beside it, and prints a JSON summary; the snapshot existing and validating against `workshop/contracts/defender-seed-snapshot.schema.json` is what proves it worked. Two conditions gate it: the paid plan must have been enabled 24 hours earlier, and the golden handoff must already exist, because the script binds the snapshot to it — which is why this straddles T-5 and T-4. Attack paths are a Resource Graph POST the script will not make; take that one signal by hand. Then distribute the snapshot; participants investigate yours and hold `Security Reader` | T-5 to T-4 |
| 6 — SRE Agent | Foundation built for the chosen model; response plan in Review mode; test incident sent and rejected; drill revision created at zero traffic; you holding SRE Agent Administrator | T-3 |
| Wrap-up | Nothing. Protect the time slot instead — it is the only chapter that produces something a participant can show their manager | — |

## Related pages

- [Day-of card](DayOfCard.md) — the one printable page to deliver from, with the checkpoints and cut order
- [Agenda](Agenda.md) — the two-day schedule, the timeboxes, and what to demo if you fall behind
- [Cost and capacity estimate](CostEstimate.md) — per-meter pricing and the teardown run rate
- [Glossary](Glossary.md) — vocabulary, for the orientation slot
- [Base infrastructure](../baseInfra/README.md) — the exact Terraform workflow and state boundary
- [Troubleshooting](Troubleshooting.md) — the contract-first diagnostic workflow
