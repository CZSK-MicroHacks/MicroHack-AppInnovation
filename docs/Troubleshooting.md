# Troubleshooting

## Start here: find your symptom

| What you are seeing | Most likely cause | Go to |
| --- | --- | --- |
| `pytest` fails on a contract or fixture | Wrong working directory, or an edited generated file | [Contract and repository failures](#2-contract-and-repository-failures) |
| `uv` cannot resolve packages | A global uv config is overriding the project — add `--no-config` | [Contract and repository failures](#2-contract-and-repository-failures) |
| `error: --base-url or CATALOG_BASE_URL is required` | The shell predates provisioning, so the Machine-scope catalog variables are not loaded | [Application health failures](#4-application-health-failures) |
| The catalog will not load on the VM | Provisioning did not finish its health checks | [Workshop VM failures](#3-workshop-vm-failures) |
| `/healthz` or `/readyz` returns non-200 | Application or database not ready | [Application health failures](#4-application-health-failures) |
| Wrong number of figures, categories, or images | Corpus or migration mismatch | [Migration or corpus failures](#5-migration-or-corpus-failures) |
| Container App will not start, or has no revision | Image, identity, or configuration problem in the target | [Azure target failures](#6-azure-target-failures) |
| `az deployment` is rejected for a missing required parameter, before anything is created | `sourceCommit` and `imageDigest` are deliberately absent from the protected parameter files | [Azure target failures](#6-azure-target-failures) |
| `az deployment` fails with `AuthorizationFailed` | Wrong scope or insufficient role — this is a facilitator gate | [Authorization and cleanup failures](#8-authorization-and-cleanup-failures) |
| The handoff validator rejects your evidence | A producer step did not complete; the evidence is a symptom, not the bug | [Challenge evidence failures](#7-challenge-evidence-failures) |
| `docker` is "not recognized" on the VM | No Docker daemon — deliberate; builds run in ACR | [Workshop VM failures](#3-workshop-vm-failures) |
| A commit SHA does not match what a validator expects | Two different SHAs exist on the VM | [Workshop VM failures](#3-workshop-vm-failures) |
| A command needs a resource that does not exist | Facilitator prerequisite not provisioned | Ask your facilitator; see [`Facilitator.md`](Facilitator.md) |
| `az vm run-command` returns `Conflict: Run command extension execution is in progress` | One command at a time per VM — possibly your own orphaned invocation. **Do not deallocate before reading this** | [Workshop VM failures](#3-workshop-vm-failures) |

## How to think about a failure

Use the narrowest failing contract to find the owning layer. Do not repair evidence,
change a schema locally, or mutate Azure until the producer failure is understood.

**Never hand-edit an evidence document to make a validator pass.** The validator is
telling you a step upstream did not do its job; editing the output hides the bug and
breaks every downstream chapter that consumes it.

## 1. Confirm the execution boundary

Before diagnosing, record:

- selected stack and Challenge 1 path;
- repository full commit SHA and clean/dirty status;
- command, working directory, and actual exit code;
- whether the data is a checked-in fixture, local runtime result, or live Azure result;
- exact Azure subscription, resource group, resource ID, revision, and UTC window when
  applicable; and
- whether the proposed next command is read-only, state changing, paid, or destructive.

Stop if the subscription or resource scope is not the assigned workshop environment.

## 2. Contract and repository failures

Run the shared gate from its managed environment:

```bash
cd tests/acceptance
uv --no-config run pytest -q
uv --no-config lock --check --offline
```

Common causes:

- running outside `tests/acceptance`, so relative contract paths are wrong;
- using a global Python environment instead of `uv`;
- a machine-level `uv` configuration overriding the project — `--no-config` avoids it;
- editing a generated fixture, normalized report, or lock file;
- consuming a branch, tag, or short SHA where a full immutable commit is required; or
- implementing stack-specific behavior that disagrees with shared vectors.

Fix the producer or contract owner. Do not weaken a validator to accept one local
output.

## 3. Workshop VM failures

The source tree lives at `C:\MicroHack\source`, extracted from a downloaded archive.
Pinned Git for Windows **is** installed, and provisioning seeds that directory with a
single baseline commit, so `git status`, `git add`, `git commit`, and `git rev-parse HEAD`
all work. **`docker` is not installed**, and that is deliberate — container images are
built with `az acr build`, which builds inside Azure Container Registry.

Two SHAs exist and they are not interchangeable. `git rev-parse HEAD` identifies the
participant's own work and is what image tags, revisions, and handoffs bind to.
`C:\MicroHack\source\.source-commit` records which upstream archive was provisioned. If a
handoff is rejected for a commit mismatch, this confusion is the first thing to check.

On the affected VM, inspect only its matching stack:

```powershell
Get-Content C:\MicroHack\status\dotnet-smoke.json
Get-Content C:\MicroHack\status\java-smoke.json
Get-Content C:\MicroHack\logs\provision-dotnet.log
Get-Content C:\MicroHack\logs\provision-java.log
Get-Content C:\MicroHack\logs\dotnet-app.log
Get-Content C:\MicroHack\logs\java-app.log
Get-ScheduledTask -TaskName 'MicroHack-*'
```

Only one stack marker/log set exists on each VM. A missing marker means provisioning did
not complete its native database, health, readiness, image, and corpus checks. The
facilitator owns repair or replacement. Participants must not reseed, install alternate
tool versions, expose a public IP, or bypass Bastion.

### `az vm run-command` returns `Conflict: Run command extension execution is in progress`

A VM accepts **one** run-command at a time. Three different situations produce this
message, and **two of them look identical**, so read this before taking any recovery
action.

| `provisioningState` | Situation | What to do |
| --- | --- | --- |
| `Succeeded` | Another run-command, or an extension update, is genuinely in flight | Wait; retry with backoff |
| `Updating` | Either a platform operation **or an orphaned run-command** — not distinguishable from this field alone | Run the probe below |

**An orphaned run-command is the case that catches people.** Stopping the local `az`
process — `Ctrl-C`, closing the terminal, losing the Bastion session — **does not cancel
the invocation on the VM.** It keeps executing until it finishes or hits the service-side
execution limit, holding the channel the whole time with nothing attached to it. This has
been observed blocking a VM for over 35 minutes.

The only way to tell the two `Updating` cases apart is to ask whether anything other than
run-command has actually touched the VM:

```powershell
az monitor activity-log list -g <your-resource-group> --offset 12h `
  --query "[?contains(to_string(resourceId),'<your-vm-name>') && !contains(operationName.value,'runCommand')].operationName.value" -o tsv
```

- **Output is empty** → nothing is operating on the VM. You are waiting on your own
  orphaned command. **Wait for it. Do not deallocate.**
- **Output lists operations** → a real platform operation is in progress. Wait and retry.

Scope the query to the VM as shown. Filtering only on `operationName` will also match your
PostgreSQL server and Azure Policy evaluations in the same resource group, which makes an
orphan look like a busy platform. `to_string(resourceId)` is required, or the query errors
on entries where that field is null.

**Why deallocating the VM is the wrong reflex.** Deallocation clears a genuinely wedged
extension, but it also **kills whatever the orphaned command was doing** — which is
normally your own long-running job, the work you were trying to rescue. An orphan looks
exactly like a wedge (nothing progressing, many minutes elapsed), so deallocate feels
correct and is destructive. Run the probe first.

**Avoid the situation entirely for anything long-running.** Do not invoke a multi-minute
command inline. Have run-command register a scheduled task and return immediately, then
poll the log file:

```powershell
az vm run-command invoke -g <your-resource-group> -n <your-vm-name> `
  --command-id RunPowerShellScript --scripts @'
  $a = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument '-NoProfile -File C:\MicroHack\scripts\longjob.ps1'
  Register-ScheduledTask -TaskName 'MicroHack-LongJob' -Action $a `
    -User 'SYSTEM' -RunLevel Highest -Force | Out-Null
  Start-ScheduledTask -TaskName 'MicroHack-LongJob'
'@
```

Then check progress with a separate, fast invocation reading
`C:\MicroHack\logs\longjob.log`. The channel is never held, so this cannot wedge — and it
sidesteps the 4096-byte run-command output cap as well.

## 4. Application health failures

Interpret the routes separately:

- `/healthz` proves process liveness only.
- `/readyz` proves database connectivity and completed startup migration/import state.
- `/perftest/catalog` requires the non-default API key and performs bounded database
  work.

A healthy liveness route with failed readiness usually indicates database or startup
publication state, not a web-process outage. Inspect the selected runtime README and
structured logs:

- [.NET target](../dotnet/README.md)
- [Java target](../java/README.md)

Verify the database family, host, port, authentication mode, SSL requirements, image
provider, seed path, and exact managed identity. Never print a password, API key, or
connection string while debugging.

### `--base-url or CATALOG_BASE_URL is required`

The acceptance CLI reads `CATALOG_BASE_URL` from the environment. Provisioning persists
it — along with `CATALOG_DATABASE_HOST`, `_PORT`, `_NAME`, `_USERNAME`, and the corpus
paths — at Machine scope, so only shells started *after* provisioning finished inherit
them. A console left open across the provisioning run sees none of them.

Open a new PowerShell session. To confirm the values arrived:

```powershell
$env:CATALOG_BASE_URL
$env:CATALOG_DATABASE_HOST
```

`CATALOG_DATABASE_PASSWORD` is deliberately never persisted; it stays in
`C:\MicroHack\secrets` and is passed explicitly where a command needs it.

## 5. Migration or corpus failures

The expected corpus is always 198 figures, 20 categories, and 198 canonical images.
Check in this order:

1. Canonical source manifest and image hashes.
2. Native backup/export identity.
3. Empty target database and applied migration identity.
4. Transactional import result.
5. Native database counts and representative rows.
6. Shared acceptance report and digest chain.

Legacy databases created outside the rewrite migration history are reset boundaries.
Back up non-canonical data and obtain explicit authorization before deleting or
recreating a database. Do not add an adoption adapter.

## 6. Azure target failures

A deployment rejected before any resource is created is almost always a missing parameter,
not a broken parameter file. `sourceCommit` — and, at the two application stages,
`imageDigest` — are deliberately absent from the protected files under `C:\protected\`.
Neither value existed when provisioning wrote those files, and a placeholder that satisfied
`infra/main.bicep`'s 40-hex and `sha256:` format asserts would deploy the wrong source
silently, so a forgotten override has to fail instead. Supply both on the command line
after the `@file` argument, where a later `--parameters` overrides an earlier one.

Once resources exist, start with the validated handoff, not portal discovery:

1. Validate `evidence/modernization-contract.json`.
2. Confirm subscription/resource-group relationships and exact resource IDs.
3. Confirm image digest, active revision, traffic, health probes, and target port.
4. Confirm workload identity assignments at exact scopes.
5. Confirm managed database state and network reachability.
6. Confirm image provider and canonical keys.
7. Confirm Application Insights/Log Analytics resource identity.

If the observed resource differs from the handoff, stop downstream work and regenerate
the handoff from actual producer outputs.

## 7. Challenge evidence failures

Preserve this sequence:

```text
raw response -> capture manifest -> renderer -> normalized report -> validator
```

Check request URL/body, API version, time window, resource ID, pagination, response
shape, file digest, and capture timestamp. Do not wrap a flattened CLI response to look
like a native ARM response. Do not edit normalized observations. Recapture the native
producer response and rerun the renderer.

Asynchronous Azure signals can be legitimately delayed:

- metric and log ingestion;
- Container App revision/replica convergence;
- cloud security recommendations;
- SRE Agent investigation;
- Cost Management data.

Use the documented bounded wait and freshness window. Do not substitute an old fixture
or self-asserted success.

## 8. Authorization and cleanup failures

Classify the command before running it:

| Class | Examples | Required owner |
| --- | --- | --- |
| Read-only | ARM GET/list, log query, validator | Assigned participant or facilitator scope |
| State changing | VM deallocate, revision traffic, deployment | Explicit chapter authorization |
| Paid | Pricing enablement, SRE Agent capacity | Subscription owner |
| Destructive | Database reset, resource deletion, Terraform destroy | Named cleanup owner and protected-resource review |

There is no repository-wide "delete all resource groups" operation. Cleanup follows the
participant, cloud security, and SRE chapter boundaries. Preserve provider
registrations, shared telemetry, evidence, canonical data, and the Terraform backend.

Resolved implementation pitfalls are recorded in [CommonErrors.md](CommonErrors.md).
Use only entries that match the current frozen contract and verified toolchain.
