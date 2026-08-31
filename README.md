# MicroHack: Application Innovation

**Two legacy applications are running on virtual machines. In two days you will move one
of them to Azure — and prove, with evidence, that it is faster to deploy, safer to
change, and able to survive an incident.**

> **Before you start — confirm you have the integrated material.** This repository has been
> delivered in two forms, and only one of them is the workshop described below. Rather than
> naming a branch (which goes stale the moment it merges), verify it directly:
>
> ```bash
> ls -d tests/acceptance workshop/contracts infra/observability-workbook.bicep
> ```
>
> **All three must exist.** If any is missing, your checkout predates the integrated workshop:
> the acceptance suite, the contract layer, and Challenge 4 are all materially different, and
> the challenge instructions will not match what you have. Fetch the revision that contains
> them before continuing. This check is deliberately written against the *content* rather than
> against a branch name or commit count, so it stays correct after the integration lands.

## The situation

A specialty retailer sells collectible figures. Its product catalog — 198 items across
20 categories, each with a photograph — runs the way it has run for years: one Windows
Server virtual machine, with the application and its database installed side by side on
the same box.

![The catalog application: a grid of collectible figures with names, categories, and photographs](images/catalog.png)

It works. That is the problem, because nobody can justify touching it.

- **Scaling means buying a bigger machine.** There is one instance. A traffic spike is
  survived by hoping.
- **Releases are a weekend activity.** Someone remotes into the server, stops the
  service, copies files, and starts it again. There is no rollback that isn't a restore.
- **The database shares a host with the web tier.** A runaway query takes the site down.
- **Nobody can explain last Tuesday.** There are no traces, no metrics, and the only log
  is a text file on the server.
- **Patching, backup, and certificate renewal are all somebody's personal calendar
  reminder.**

Your job is not to admire the problem. It is to move the catalog to Azure Container Apps
and a managed database — and to leave with proof that the move was worth it.

## What you will build

| | Before (day 1, 09:00) | After (day 2, 17:00) |
| --- | --- | --- |
| **Compute** | One Windows VM you patch yourself | Azure Container Apps, scaled by rules |
| **Database** | Local SQL Server / PostgreSQL on the app server | Azure SQL Database / PostgreSQL Flexible Server |
| **Images** | Files on the VM disk | Azure Blob Storage behind the app's identity |
| **Secrets** | Connection strings in config files | Managed identity — no passwords in the app |
| **Deployment** | Manual, out of hours, no rollback | GitHub Actions, approval gate, one-click rollback |
| **Diagnosis** | A text file on the server | Distributed traces, metrics, and logs you can query |
| **An incident** | Someone notices, eventually | An agent detects it, proposes a fix, and asks permission |

## What you will prove

This workshop is evidence-driven. You do not claim the migration worked — you produce a
validated document that says so. By the end you will have measured:

- **Catalog response time** — a median you take on the legacy VM in Challenge 0 and put
  next to the median the load engine reports in Challenge 2.
- **Pipeline lead time** — dispatch to live: from the moment the release pipeline is
  dispatched to the moment the new revision serves traffic. Its "before" is the manual
  release you count step by step in Challenge 0, so the comparison is steps against
  minutes.
- **Scale-out under load** — replicas responding to real traffic, with the database
  signal to match.
- **Rollback time** — how long it takes to undo a bad release.
- **Mean time to recovery** — how long an incident lasts when an agent is watching.

Every one of those lands in the [wrap-up scorecard](challenges/wrapup/README.md), which
you fill in yourself from your own evidence files.

Cost is the one claim this workshop does not put a meter on, so it is stated as an
estimate rather than a result. The modernized workload is priced against the VM it
replaces, at list price, in [the cost estimate](docs/CostEstimate.md); the short version
is that the database tier decides the answer, with the Java/PostgreSQL target running at
roughly half the legacy VM per day and the .NET/Azure SQL target at roughly 30% more.
Carry that comparison, not a slogan.

## Why these tools specifically

Containers, a managed database, and a deployment pipeline exist on every cloud. Four
things here are specific enough to be worth naming, and each one is a chapter you can
check rather than a claim you have to accept.

- **The modernization lands in your repository as reviewable history.** On both Copilot
  paths — [assisted rewrite](challenges/ch01-copilot-rewrite/README.md) and
  [framework modernization](challenges/ch01-copilot-modernization/README.md) — GitHub
  Copilot works on the source tree on your own VM, and you take one bounded unit of work
  at a time: read its diff, run the stack's build and tests, then commit it or revert it.
  The upgrade arrives as a series of accepted commits ending in one clean commit that every
  later artifact — image tag, revision, evidence — is bound to, rather than as a branch
  somebody has to trust.
- **Promotion and rollback are the same operation in opposite directions.** Container Apps
  deploys the new revision beside the old one at zero traffic; promoting it is a traffic
  weight change, and undoing it is that change reversed, with the previous revision still
  running the whole time. That is why [Challenge 3](challenges/ch03/README.md) asks you to
  *time* a rollback rather than write a rollback plan.
- **The pipeline stores no cloud credential.** GitHub Actions authenticates to Azure with
  OIDC federated credentials scoped to one repository and one environment, so the token is
  short-lived and there is no client secret or registry admin password sitting in a GitHub
  secret to rotate or leak. [Challenge 3](challenges/ch03/README.md) makes you show that
  the deployment identity holds exactly two role assignments and that no such credential
  was used.
- **The two days end with a security posture and an agent, not a passing deployment.**
  [Challenge 5](challenges/ch05-defender/README.md) reads what the migration actually
  exposed across the VM, registry, container app, and managed database, and makes you fix
  or consciously accept four specific findings.
  [Challenge 6](challenges/ch06-sre-agent/README.md) puts Azure SRE Agent on a live
  incident, then requires you to reject one of its plausible explanations with evidence
  before approving the single change it is allowed to make.

## Two baselines, three paths

Challenge 0 puts both legacy applications in front of you. You pick **one** baseline and
keep it for the rest of the workshop. Challenge 1 then offers **three** ways to modernize
it. All six combinations converge on the same Azure handoff contract, so every later
chapter works identically no matter what you chose.

| Baseline | Manual rebuild | GitHub Copilot-assisted rewrite | GitHub Copilot modernization |
| --- | --- | --- | --- |
| **.NET / SQL Server** (`dotnet-sqlserver`) | [Manual path](challenges/ch01-manual/README.md) | [Copilot rewrite](challenges/ch01-copilot-rewrite/README.md) | [Copilot modernization](challenges/ch01-copilot-modernization/README.md) |
| **Java / PostgreSQL** (`java-postgresql`) | [Manual path](challenges/ch01-manual/README.md) | [Copilot rewrite](challenges/ch01-copilot-rewrite/README.md) | [Copilot modernization](challenges/ch01-copilot-modernization/README.md) |

**Which should you pick?**

- **Manual rebuild** — you want to understand every moving part yourself. Slowest, and
  the best teacher.
- **Copilot-assisted rewrite** — you want to see how far an AI pair can take a
  greenfield rebuild when you supply the target architecture.
- **Copilot modernization** — you want the framework upgrade itself (.NET 8 → 10,
  Spring Boot 3 → 4) driven by the GitHub Copilot app modernization tooling. This is the
  path that most resembles a real upgrade backlog.

Whichever you choose, the path is complete only when `evidence/modernization-contract.json`
passes the shared handoff validator. Later chapters read that validated file instead of
rediscovering resources in the portal. If your path runs out of time, the facilitator can
hand you a prevalidated **golden handoff** for the same stack so you rejoin the group —
never fabricate or hand-edit an evidence document.

## Chapter sequence

| Chapter | Outcome | Participant guide | Reference solution |
| --- | --- | --- | --- |
| **0. Select a baseline** | Opened both legacy catalogs, measured how the one you keep behaves today, and committed to a single stack for the rest of the workshop — the other VM deallocated with facilitator approval | [Challenge 0](challenges/ch00/README.md) | [Solution 0](solutions/ch00/README.md) |
| **1. Modernize** | Got the catalog off the VM: running as a container on Azure Container Apps, against a managed database, with its images in Azure storage and no password anywhere in the application — and a validated handoff that proves it | [Shared target](challenges/ch01/README.md) plus the selected path above | [Shared solution](solutions/ch01/README.md) plus the matching stack/path solution |
| **2. Load and autoscaling** | Watched the catalog add capacity by itself under 40 concurrent users, serve every request without a single error, and give the capacity back when the traffic stopped — with the metrics for all three | [Challenge 2](challenges/ch02/README.md) | [Solution 2](solutions/ch02/README.md) |
| **3. CI/CD and revisions** | Shipped a release through an approved pipeline, measured how long it took from dispatch to live, and undid it on purpose — with a number for that too | [Challenge 3](challenges/ch03/README.md) | [Solution 3](solutions/ch03/README.md) |
| **4. Observability** | Answered five questions about your running catalog that were unanswerable on the VM, for one exact build, on one exact revision, in one exact window of time | [Challenge 4](challenges/ch04/README.md) | [Solution 4](solutions/ch04/README.md) |
| **5. Cloud security posture** | Read a real cloud security posture across your VM, container registry, container app, and managed database, then fixed or consciously accepted four specific findings — with the evidence to show which | [Challenge 5](challenges/ch05-defender/README.md) | [Solution 5](solutions/ch05-defender/README.md) |
| **6. SRE Agent** | Watched an AI agent diagnose a live catalog failure from telemetry alone, rejected one of its plausible explanations with evidence, approved the single change it was allowed to make, and wrote down how many minutes the incident lasted | [Challenge 6](challenges/ch06-sre-agent/README.md) | [Solution 6](solutions/ch06-sre-agent/README.md) |
| **7. Optional extensions** | Designed — and, if time allowed, deployed — one enterprise control your organization would demand before this app carried real customer data, or a catalog that answers natural-language questions about the 198 figures and refuses when it cannot back the claim up | [Enterprise](challenges/ch07-enterprise/README.md) or [Innovation](challenges/ch07-innovation/README.md) | Open-ended; no canonical implementation |
| **Wrap-up** | Put every chapter's number on one page that answers the question your manager will ask on Monday: was it worth it? | [Wrap-up](challenges/wrapup/README.md) | — |

Challenges 0 through 6 are required. Challenge 7 is optional and must not change the
frozen handoff or evidence produced by required chapters.

See [the agenda](docs/Agenda.md) for how these chapters fit into two days, including the
points where the facilitator may hand out a golden handoff to keep the group together.

## Participant prerequisites

- A workshop identity assigned to exactly one participant resource group.
- GitHub access and, for either Copilot path, an active GitHub Copilot entitlement.
- RDP access to the two Windows workshop VMs over their public IP addresses.
- The repository at the facilitator-provided immutable commit.
- Familiarity with PowerShell, JSON, and the selected application stack.

New to the vocabulary? Start with the [glossary](docs/Glossary.md).

Do not request or share a common administrator password. The facilitator distributes
temporary access through an approved secret channel, rotates or revokes it after the
workshop, and keeps credentials out of source, shell history, evidence, and screenshots.

## For facilitators

Delivery planning — lead times, cost, capacity, seeding, and the per-chapter runbook —
lives in [the facilitator guide](docs/Facilitator.md) and
[the cost and capacity estimate](docs/CostEstimate.md). Read both before you commit to a
date; several gates below need **days**, not hours, of lead time.

Selling this internally, or showing stakeholders what the two days produce?
[The ten-minute demo](docs/Demo.md) is the script for it — six steps, each with the
command to run, the output to expect, and what to say while it is on screen, closing on a
one-slide summary you can take into the room.

### Facilitator go/no-go matrix

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
| [`challenges`](challenges) | Participant instructions — start here |
| [`solutions`](solutions) | Reference solutions, hints, and prompts for required chapters |
| [`solutions/reference`](solutions/reference/README.md) | The modernized target implementation of both stacks |
| [`dotnet`](dotnet/README.md) | .NET/SQL Server **legacy baseline** — the starting point you modernize |
| [`java`](java/README.md) | Java/PostgreSQL **legacy baseline** — the starting point you modernize |
| [`data/manifest.json`](data/manifest.json) | Canonical 198-figure, 20-category, 198-image corpus manifest |
| [`workshop/contracts`](workshop/contracts/README.md) | Frozen schemas, registries, conformance vectors, and sanitized fixtures |
| [`tests/acceptance`](tests/acceptance/README.md) | Shared executable conformance, migration, evidence, and repository gates |
| [`baseInfra`](baseInfra/README.md) | Facilitator-owned workshop VM and optional paid-service foundation |
| [`infra`](infra/README.md) | Shared Azure target, CI/CD, observability, and SRE Bicep |
| [`docs/Agenda.md`](docs/Agenda.md) | How the chapters fit into two days |
| [`docs/Demo.md`](docs/Demo.md) | The ten-minute opening demo, with narration and a one-slide summary |
| [`docs/Facilitator.md`](docs/Facilitator.md) | Delivery runbook, lead times, and seeding |
| [`docs/Glossary.md`](docs/Glossary.md) | Terms used throughout the workshop |
| [`docs/Design.md`](docs/Design.md) | End-to-end architecture and ownership boundaries |
| [`docs/Troubleshooting.md`](docs/Troubleshooting.md) | Contract-first diagnostic workflow |

## Run the local contract gate

The shared Python environment is managed only with `uv` and
`tests/acceptance/pyproject.toml`:

```bash
cd tests/acceptance
uv --no-config run pytest -q
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
