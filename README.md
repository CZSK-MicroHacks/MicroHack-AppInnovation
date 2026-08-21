# MicroHack: Application Innovation

This workshop starts from two behaviorally equivalent legacy catalog applications and
finishes with one contract-verified Azure deployment. Each participant selects one
baseline, completes one modernization path, and then rejoins the shared operational
challenges.

The repository is intentionally bounded:

- **.NET/SQL Server** starts on .NET 8 and SQL Server 2022 Express, then targets
  .NET 10 and Azure SQL Database.
- **Java/PostgreSQL** starts on Microsoft OpenJDK 17 and PostgreSQL 18, then targets
  Microsoft OpenJDK 21 and Azure Database for PostgreSQL Flexible Server.
- Both stacks preserve the same catalog identities, routes, import transaction,
  health model, image corpus, performance endpoint, and telemetry contract.
- There is no in-place production migration or compatibility adapter. Workshop
  databases are disposable and reseeded from the canonical corpus.

## Choose one baseline and one path

Challenge 0 compares both baselines. Challenge 1 then offers three implementation
paths. All six cells converge on the same Azure handoff contract.

| Baseline | Manual rebuild | GitHub Copilot-assisted rewrite | GitHub Copilot modernization |
| --- | --- | --- | --- |
| `.NET/SQL Server` (`dotnet-sqlserver`) | [Manual path](challenges/ch01-manual/README.md) | [Copilot rewrite](challenges/ch01-copilot-rewrite/README.md) | [Copilot modernization](challenges/ch01-copilot-modernization/README.md) |
| `Java/PostgreSQL` (`java-postgresql`) | [Manual path](challenges/ch01-manual/README.md) | [Copilot rewrite](challenges/ch01-copilot-rewrite/README.md) | [Copilot modernization](challenges/ch01-copilot-modernization/README.md) |

Path-specific implementation is complete only when
`evidence/modernization-contract.json` passes the shared handoff validator. Downstream
chapters consume that validated file rather than rediscovering resources from the
portal. If a path cannot complete during the workshop, the facilitator may provide a
prevalidated golden handoff for the same stack; do not fabricate or partially edit an
evidence document.

## Chapter sequence

| Chapter | Outcome | Participant guide | Reference solution |
| --- | --- | --- | --- |
| **0. Select a baseline** | Compare both provisioned applications, verify the common behavioral baseline, select one stack, and deallocate the other VM with facilitator approval | [Challenge 0](challenges/ch00/README.md) | [Solution 0](solutions/ch00/README.md) |
| **1. Modernize** | Implement one of the six stack/path cells and publish a validated Azure handoff | [Shared target](challenges/ch01/README.md) plus the selected path above | [Shared solution](solutions/ch01/README.md) plus the matching stack/path solution |
| **2. Load and autoscaling** | Prove bounded load, revision scale-out, database signal, and recovery | [Challenge 2](challenges/ch02/README.md) | [Solution 2](solutions/ch02/README.md) |
| **3. CI/CD and revisions** | Deploy an immutable revision with GitHub OIDC, approval, promotion, and rollback evidence | [Challenge 3](challenges/ch03/README.md) | [Solution 3](solutions/ch03/README.md) |
| **4. Observability** | Deploy one handoff-bound workbook and prove five frozen queries | [Challenge 4](challenges/ch04/README.md) | [Solution 4](solutions/ch04/README.md) |
| **5. Cloud security posture** | Investigate the facilitator-prepared paid-plan snapshot without creating attack traffic | [Challenge 5](challenges/ch05-defender/README.md) | [Solution 5](solutions/ch05-defender/README.md) |
| **6. SRE Agent** | Investigate and recover an approved revision-traffic incident, audit the bounded action, and verify cleanup billing | [Challenge 6](challenges/ch06-sre-agent/README.md) | [Solution 6](solutions/ch06-sre-agent/README.md) |
| **7. Optional extensions** | Explore enterprise hardening or an AI-enabled catalog after all required chapters | [Enterprise](challenges/ch07-enterprise/README.md) or [Innovation](challenges/ch07-innovation/README.md) | Open-ended; no canonical implementation |

Challenges 0 through 6 are required. Challenge 7 is optional and must not change the
frozen handoff or evidence produced by required chapters.

## Participant prerequisites

- A workshop identity assigned to exactly one participant resource group.
- GitHub access and, for either Copilot path, an active GitHub Copilot entitlement.
- Azure Bastion access to the two private Windows workshop VMs.
- The repository at the facilitator-provided immutable commit.
- Familiarity with PowerShell, Git, JSON, and the selected application stack.

Do not request or share a common administrator password. The facilitator distributes
temporary access through an approved secret channel, rotates or revokes it after the
workshop, and keeps credentials out of source, shell history, evidence, and screenshots.

## Facilitator go/no-go matrix

The facilitator records each gate before participants begin. A missing or failed gate
blocks the dependent chapter; it is not permission to weaken a contract.

| Gate | Required state | Owner and evidence |
| --- | --- | --- |
| Repository | One immutable public source commit exists and all participants use that commit | Facilitator records the full SHA and archive digest |
| Toolchain | Terraform `1.13.3`, Azure CLI `2.80.0`, Bicep `0.43.8`, uv `0.8.22`, Python `3.12.10`, Docker Engine `27.4.0`, .NET SDKs `8.0.424`/`10.0.400`, Microsoft OpenJDK `17.0.20+8`/`21.0.12`, and Maven `3.9.16`; exact images, packages, and hashes remain those in [`workshop/toolchain.lock.json`](workshop/toolchain.lock.json) | Facilitator runs lock and package checks before provisioning |
| Subscription isolation | A disposable workshop subscription contains no production workload; participant resources use isolated `rg-userNNN` groups and the SRE lab uses its dedicated resource group | Subscription owner records subscription and tenant IDs outside participant evidence |
| Providers and regions | Required providers are registered; both participant regions support the selected VM size; the SRE Agent region is supported | Facilitator captures preflight output and provider state |
| Quotas and budget | Two Windows VMs per participant, Premium disk, Container Apps, managed database, ACR, Log Analytics, Application Insights, load-test, and optional paid-service capacity fit the approved budget | Subscription owner approves the recorded capacity/cost estimate |
| Facilitator roles | Infrastructure deployment identity has the subscription/resource-group rights documented by each module, including role-assignment permission; no participant receives subscription Owner | Subscription owner reviews assignments before provisioning |
| Participant roles | Each participant receives Owner only on their resource group, plus the bounded chapter-specific read or operator roles documented by Challenges 5 and 6 | Facilitator verifies effective scope and cross-participant denial |
| Copilot | Required participants can sign in to GitHub Copilot and the pinned VS Code extensions are healthy on both VM images | Facilitator tests one disposable identity before image freeze |
| Baseline pre-warm | Both VMs per participant pass their native database count, `/healthz`, `/readyz`, canonical image, and `198/20/198` corpus checks | `C:\MicroHack\status\dotnet-smoke.json` and `java-smoke.json` |
| Golden rejoin | One validated handoff exists for each stack and references immutable image, source, Azure resource, migration, runtime, acceptance, and telemetry evidence | Facilitator validates both golden handoffs before Challenge 1 |
| Challenge 5 paid services | The subscription owner explicitly opts in to the five frozen pricing resources and budget, authorizes cost, pre-warms the required Serverless Containers portal state, and allows up to 24 hours for asynchronous findings | Facilitator preserves before-state and seed-snapshot evidence; participants never enable plans |
| Challenge 6 paid services | The approved SRE Agent region, fixed four-agent-unit capacity, identities, response plan, telemetry connectors, drill revision, test-alert rejection, and cleanup/billing windows pass preflight | Facilitator preserves foundation and incident seed evidence |
| Cleanup | Protected provider registrations, shared telemetry, evidence, and canonical data are identified before participant destroy; paid plans and SRE resources have explicit restoration/deletion owners | Subscription owner runs the chapter cleanup validators and final inventory/cost review |

See [base infrastructure](baseInfra/README.md) for the exact capacity command,
Terraform workflow, state boundary, and participant cleanup sequence. Paid-service or
live-incident actions require explicit authorization from the subscription owner.

## Repository map

| Path | Purpose |
| --- | --- |
| [`workshop/contracts`](workshop/contracts/README.md) | Frozen schemas, registries, conformance vectors, and sanitized fixtures |
| [`data/manifest.json`](data/manifest.json) | Canonical 198-figure, 20-category, 198-image corpus manifest |
| [`dotnet`](dotnet/README.md) | .NET/SQL Server baseline and modernized implementation |
| [`java`](java/README.md) | Java/PostgreSQL baseline and modernized implementation |
| [`tests/acceptance`](tests/acceptance/README.md) | Shared executable conformance, migration, evidence, and repository gates |
| [`baseInfra`](baseInfra/README.md) | Facilitator-owned workshop VM and optional paid-service foundation |
| [`infra`](infra/README.md) | Shared Azure target, CI/CD, observability, and SRE Bicep |
| [`challenges`](challenges) | Participant instructions |
| [`solutions`](solutions) | Facilitator/reference solutions for required chapters |
| [`docs/Design.md`](docs/Design.md) | End-to-end architecture and ownership boundaries |
| [`docs/Troubleshooting.md`](docs/Troubleshooting.md) | Contract-first diagnostic workflow |

## Run the local contract gate

The shared Python environment is managed only with `uv` and
`tests/acceptance/pyproject.toml`:

```bash
cd tests/acceptance
UV_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple \
  uv --no-config run pytest -q
UV_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple \
  uv --no-config lock --check --offline
```

Run native .NET or Java commands from the selected component README. Live application,
Azure, GitHub approval, paid-plan, incident, and cleanup gates require the corresponding
environment and authorization; a local fixture cannot substitute for live evidence.

## Safety boundaries

- Never run this workshop in a production or shared business subscription.
- Do not apply paid plans, role assignments, traffic changes, deletion, or broad cleanup
  without the named owner and exact scope required by the chapter.
- Keep Terraform state encrypted and access controlled; it contains secrets.
- Never edit normalized evidence by hand. Preserve raw producer output, render through
  the frozen command, and run the common validator.
- Do not delete provider registrations, shared telemetry, canonical input, or evidence.
- Treat `docs/CommonErrors.md` as resolved implementation history, not permission to
  bypass current contracts.
