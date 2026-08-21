# Troubleshooting

Use the narrowest failing contract to find the owning layer. Do not repair evidence,
change a schema locally, or mutate Azure until the producer failure is understood.

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
UV_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple \
  uv --no-config run pytest -q
UV_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple \
  uv --no-config lock --check --offline
```

Common causes:

- running outside `tests/acceptance`, so relative contract paths are wrong;
- using a global Python environment instead of `uv`;
- editing a generated fixture, normalized report, or lock file;
- consuming a branch, tag, or short SHA where a full immutable commit is required; or
- implementing stack-specific behavior that disagrees with shared vectors.

Fix the producer or contract owner. Do not weaken a validator to accept one local
output.

## 3. Workshop VM failures

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

Start with the validated handoff, not portal discovery:

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
