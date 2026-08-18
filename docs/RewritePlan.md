# MicroHack Application Innovation Rewrite Plan

## Problem and proposed approach

The repository currently teaches modernization through a .NET 8 Blazor Server and
SQL Server Express catalog application running on one Windows VM. The first challenge
combines database migration, containerization, and Azure deployment; later challenges
cover load testing, CI/CD, OpenTelemetry, and optional security/AI work.

The rewrite will:

1. Preserve and stabilize the current .NET/SQL Server monolith.
2. Add a functionally equivalent Java/PostgreSQL monolith as a second legacy baseline.
3. Provision both baselines on separate VMs so each participant can select one.
4. Add a common characterization and acceptance contract across both applications.
5. Replace the single modernization challenge with three alternative paths that start
   from either baseline and converge on equivalent deployable outcomes.
6. Retain and repair the load, CI/CD, and observability progression.
7. Add required Microsoft Defender for Cloud and Azure SRE Agent challenges.
8. Make every baseline/path combination produce a path-neutral handoff artifact so
   downstream challenges work regardless of the modernization approach selected.

Implementation should proceed as a sequence of small, reviewable PRs. Independent
modernization paths and downstream challenge work can be delegated to coordinated
child sessions after the shared foundation is merged.

## Access from other Copilot sessions

This repository document is the durable cross-session copy. Any future Copilot session
opened on this repository can read it directly with:

```text
Review docs/RewritePlan.md and continue from the dependency-tracked implementation plan.
```

Keep this document synchronized when planning decisions change.

## Research summary

### Current workshop and repository

- The intended story is a VM-hosted monolith modernized to Azure Container Apps and its
  corresponding managed database, then load-tested, continuously delivered, and observed.
- The current application supports catalog browsing, category filtering, name search,
  detail views, local images, startup seed import, an import upload surface, and an
  API-key-protected performance endpoint.
- The checked-in data is the canonical source: 198 catalog records, 20 categories, and
  198 images using UUID identifiers. `docs/Design.md` still describes an obsolete
  `LF-####` shape and approximately 200 items.
- Current implementation and documentation drift includes:
  - A referenced `dotnet/Dockerfile` does not exist; the only Dockerfile is under
    `solutions/ch01/`.
  - Challenge 4's Bicep solution is explicitly a duplicate placeholder.
  - API-key defaults disagree across code and documentation.
  - The app has two competing `/import` implementations.
  - The current SQL-heavy load amplifier is SQL Server specific.
  - Bicep parameter files and provisioning scripts contain weak or hard-coded training
    credentials.
  - Provisioning downloads mutable content from a raw `main` branch.
  - Base-infrastructure documentation no longer matches the Terraform variables.
- The current target uses Azure Files rather than the Blob Storage target described in
  the design document. The revised contract should allow an external durable image
  store without forcing all three paths to use identical internals.

### GitHub Copilot modernization

- The current official product name is **GitHub Copilot modernization**.
- The IDE experiences for supported .NET and Java upgrades and migration scenarios are
  generally available.
- The Modernization Agent/Modernize CLI assessment and planning experience is public
  preview and must not be a required dependency for this workshop.
- The GA IDE experience supports both .NET and Java migration scenarios. It can assess
  and apply supported runtime/framework upgrades, cloud-readiness changes, local-file
  externalization, managed identity changes, containerization, IaC generation,
  validation, and Azure deployment.
- It does not promise arbitrary application rewrites, microservice decomposition, or a
  turnkey homogeneous SQL Server/Azure SQL or PostgreSQL schema/data cutover. Database
  migration remains an explicit workshop responsibility for both stacks.
- The required product path should use a pinned and preflighted VS Code IDE extension.
  The preview CLI can be an optional facilitator appendix.

### Microsoft Defender for Cloud

- Azure Container Apps receives posture-only coverage through paid Defender CSPM
  Serverless Containers; it does not receive host/runtime sensor coverage.
- Full serverless-container coverage requires Registry access and can take up to 24
  hours to appear.
- ACR image vulnerability assessment is available through relevant Defender container
  and/or Defender CSPM registry capabilities.
- PostgreSQL Flexible Server is covered by Defender for Open-Source Relational Databases;
  Azure SQL uses the corresponding Defender database protection.
- Both legacy VMs can be covered by Defender for Servers P2 for useful before/after
  comparisons.
- Live recommendations and alerts are asynchronous, so challenge grading must use
  pre-warmed findings and deterministic ARM/IaC state rather than wait for a new alert.

### Azure SRE Agent

- Azure SRE Agent can investigate Azure Container Apps, Azure SQL, PostgreSQL,
  Azure Monitor, Application Insights, Log Analytics, and deployment context.
- Availability is region-, subscription-, and tenant-dependent. Facilitators must
  validate registration and a supported region before offering the workshop.
- Azure infrastructure changes can be held for human approval using Review mode.
  Response plans must be explicitly configured for Review because per-plan defaults may
  differ from the agent-level default.
- A bad Azure Container Apps revision is the strongest deterministic workshop scenario:
  it creates deployment, revision, request, dependency, exception, and alert evidence
  while allowing a safe traffic rollback to a retained healthy revision.

## Confirmed decisions

- The current .NET/SQL Server application remains an active, supported baseline.
- The Java baseline UI will use Spring Boot MVC and Thymeleaf.
- Each baseline remains one application plus its local database on its own VM.
- Every participant environment contains two VMs: one .NET/SQL Server and one
  Java/PostgreSQL. The participant selects one track and the unused VM can be
  deallocated after selection.
- The GitHub Copilot rewrite path may use a similar stack, but it must separate the
  database and produce a containerized application ready for Azure Container Apps.
- Every path preserves the selected database family:
  - .NET/SQL Server modernizes to Azure SQL Database.
  - Java/PostgreSQL modernizes to Azure Database for PostgreSQL Flexible Server.
- All six baseline/path combinations converge on Azure Container Apps and Azure
  Container Registry with the appropriate managed database.
- Azure SRE Agent is a required challenge; facilitators must guarantee availability,
  provisioning, permissions, telemetry, and incident seeding.
- The Defender challenge assumes all relevant paid plans are enabled, including
  serverless-container posture/image assessment, Azure SQL and PostgreSQL database
  protection, and Defender for Servers P2.
- The required GitHub Copilot modernization path uses the GA IDE experience. The preview
  Modernize CLI is optional.
- Windows Server, Bastion, the per-participant resource-group model, and the existing
  Terraform facilitator foundation are retained unless a compatibility spike proves a
  blocker.

### Provisioning ownership

“Provision both legacy VMs” is actual repository implementation work in
`baseInfra/terraform`, not a student challenge:

- The rewrite will extend the facilitator Terraform so each participant environment
  contains two prebuilt VMs before the workshop starts.
- The .NET VM will already contain SQL Server Express, the .NET application, data, and
  tools.
- The Java VM will already contain PostgreSQL, the Java application, data, and tools.
- Facilitators deploy and validate both VMs. Students do not create either legacy VM.
- Challenge 0 only asks students to connect to both, compare them, select one, run its
  acceptance checks, and record the chosen stack.
- Facilitators may deallocate the unselected VM after selection to control cost, while
  retaining it for reset/fallback if desired.

## Target architectures

### Starting legacy environments

```text
Participant environment
├── Windows VM: .NET track
│   ├── SQL Server Express
│   ├── .NET 8 Blazor Server application
│   └── local catalog.json and images
└── Windows VM: Java track
    ├── PostgreSQL service
    ├── Spring Boot/Thymeleaf application JAR
    └── local catalog.json and images
```

Both VMs use Bastion access, private NICs, deterministic start/diagnostic workflows, and
the same functional seed and acceptance contract. They remain separate to preserve an
authentic technology choice and avoid co-hosting two database engines on one machine.

Recommended Java application stack:

- A preflight-selected, security-supported Spring Boot baseline that produces meaningful
  GitHub Copilot modernization findings.
- Candidate baseline: Java 17 plus Spring Boot 3.5.
- Candidate modernization target: Java 21 plus Spring Boot 4.0 or the newest extension-
  supported pinned release.
- Maven Wrapper, one Maven module, Spring MVC, Thymeleaf, Spring Data JPA/JDBC, Flyway,
  Actuator, Micrometer/OpenTelemetry, and PostgreSQL JDBC.
- No Node, React, microservices, Dapr, or Kubernetes in the legacy baseline.

The exact Java/Spring pair is a Phase 0 gate. Do not choose an obsolete or vulnerable
version solely to make the modernization report more interesting.

### Shared modernized outcomes

```text
GitHub Actions / student deployment
             │
             ▼
Azure Container Registry ──managed identity──► Azure Container Apps
                                                     │
                         ┌───────────────────────────┼──────────────────────┐
                         ▼                           ▼                      ▼
       Selected managed database            External image store    Azure Monitor /
       ├── Azure SQL (.NET track)            (Files or Blob)         App Insights
       └── PostgreSQL Flexible Server
           (Java track)
```

Common requirements:

- One application container with immutable image tags.
- The selected database is no longer hosted in its legacy VM.
- No runtime dependency on the VM filesystem.
- Secrets are externalized; none are committed.
- ACR pull uses managed identity.
- The application exposes stable health, readiness, catalog, image, and performance
  contracts.
- Standard OpenTelemetry resource attributes identify service, version, environment,
  and deployment revision.
- Repeatable IaC and a rollback/runbook artifact exist.

Azure Files may remain the manual path's transitional image store to preserve the
current exercise. Copilot-driven paths may select Azure Blob Storage. The shared
contract records the chosen provider and tests behavior, not implementation.

## Revised challenge map

| Order | Directory | Purpose | Requirement |
| --- | --- | --- | --- |
| 0 | `challenges/ch00/` | Compare the two legacy applications, select .NET/SQL or Java/PostgreSQL, run it, and record the behavioral contract | Required |
| 1A | `challenges/ch01-manual/` | Manually move the selected database, containerize the selected app, publish to ACR, and deploy to ACA | Choose one |
| 1B | `challenges/ch01-copilot-rewrite/` | Use standard GitHub Copilot to reimplement the app against the contract and deploy it | Choose one |
| 1C | `challenges/ch01-copilot-modernization/` | Use GitHub Copilot modernization IDE assessment/tasks, plus an explicit selected-database cutover | Choose one |
| 2 | `challenges/ch02/` | Load test and validate application/database autoscaling behavior | Required |
| 3 | `challenges/ch03/` | Build OIDC-based CI/CD, multiple revisions, approval, promotion, and rollback | Required |
| 4 | `challenges/ch04/` | Send traces, metrics, and logs through OpenTelemetry and build evidence in Azure Monitor | Required |
| 5 | `challenges/ch05-defender/` | Compare and remediate Defender posture across the selected VM, ACA, ACR, and managed database | Required |
| 6 | `challenges/ch06-sre-agent/` | Investigate and human-approve rollback of a bad ACA revision with Azure SRE Agent | Required |
| 7 | `challenges/ch07-enterprise/` | Optional advanced network, identity, key, WAF, and policy hardening | Optional |
| 7 | `challenges/ch07-innovation/` | Optional AI/innovation extensions for either application stack | Optional |

`solutions/` mirrors the same directory names, with `dotnet/` and `java/` subfolders
where stack-specific artifacts are required. Root documentation must state that teams
first choose one baseline, then choose exactly one Challenge 1 path, producing six
supported combinations before rejoining the shared sequence.

Facilitators must maintain two validated golden modernized deployments, one for each
baseline/database family. A team that does not finish its chosen path can use the
matching golden deployment to continue with required Defender and SRE Agent content.

## Common modernization handoff contract

Add a checked-in JSON Schema and participant template, for example:

```text
workshop/contracts/modernization-contract.schema.json
workshop/contracts/modernization-contract.example.json
```

Required non-secret fields:

- Source stack (`dotnet-sqlserver` or `java-postgresql`), modernization path identifier,
  runtime/framework version, and source commit SHA.
- Deployed application URL and health/readiness URLs.
- ACA, ACR, selected managed database, and external image-store resource IDs.
- Container image repository and immutable digest/tag.
- Database engine/family, database name, migration mechanism/version
  (EF migration/SqlPackage or Flyway), seed-data manifest version, and verified row
  counts.
- Image storage provider and verification result.
- Authentication modes by dependency, without credentials.
- OpenTelemetry service name, environment, and revision/version attributes.
- Acceptance-test report location/result.
- Deployment mechanism/IaC location.
- Rollback target and concise runbook.

Downstream challenges consume this artifact rather than assuming a particular source
stack, database family, directory, IaC language, or image-store provider.

## Prioritized implementation plan

### P0 — Product and compatibility gates

**Goal:** prevent the repository from being designed around unsupported product,
subscription, or version assumptions.

Work:

1. Build minimal compatibility samples for the current .NET/SQL application and the new
   Java/Spring/PostgreSQL application.
2. Pin and test VS Code, .NET/Java tooling, GitHub Copilot, and GitHub Copilot
   modernization.
3. Confirm both source stacks generate useful, supported assessment and transformation
   tasks without introducing intentionally vulnerable dependencies.
4. Verify Docker builds, application tests, containerization, and IaC generation through
   the IDE extension for both stacks.
5. Verify the workshop subscription can enable the required Defender plans and
   components.
6. Register and deploy Azure SRE Agent in a supported region; validate pricing/budget,
   provider registration, RBAC, Review-mode approval, Azure Monitor incident delivery,
   and cleanup.
7. Record a facilitator preflight matrix and hard go/no-go criteria.

Exit criteria:

- Exact tool and extension versions are pinned.
- The .NET and Java baseline/target version matrices are approved.
- Required Defender coverage is visible in a disposable environment.
- An Azure Monitor test incident reaches Azure SRE Agent and a Review-mode action can be
  approved.
- The workshop is not scheduled if any required SRE Agent gate fails.

### P1 — Freeze behavior and create the acceptance harness

**Goal:** make functional parity measurable across both active legacy applications and
all six modernization combinations.

Work:

1. Define the canonical data manifest from the checked-in 198 records, 20 categories,
   and 198 images.
2. Resolve behavior drift in favor of explicit contracts:
   - Case-insensitive name-only search.
   - Category filter by stable slug/name.
   - `GET /`, `GET /figure/{id}`, image access, working `/import`, and
     `GET /perftest/catalog`.
   - Startup import is idempotent insert-new when enabled.
   - Unknown figure/image paths return 404.
   - Image traversal attempts are rejected.
   - One canonical performance API-key environment variable with no production default.
3. Define stable DTO/HTML assertions, database-family-specific invariants, health
   semantics, and telemetry assertions.
4. Implement a path-neutral acceptance harness under `tests/acceptance/` using Python,
   `uv`, Pydantic models, and pytest.
5. Add a contract schema and modernization handoff template.
6. Freeze Windows workshop-VM, coordinator-host, runtime, database, CLI, container,
   installer-integrity, and immutable source-archive requirements in a schema-validated
   toolchain lock. Existing provisioning is non-conformant until P3 consumes this lock;
   it must not be used as accepted workshop evidence before then.

Exit criteria:

- The current implementation's intended behavior is documented.
- The harness can run against either application URL and query either SQL Server/Azure
  SQL or PostgreSQL when database-level verification is required.
- The same harness grades both baselines and all three modernization paths.
- Full reports contain the exact required check set, verify complete database/image
  state, and cannot use sampling or skipped checks.
- A handoff validator parses native runtime-test artifacts and normalized telemetry query
  results, validates canonical manifest hashes and exact Azure resource types, and rejects
  unbound, incomplete, empty, or path-escaping evidence.

### P2A — Stabilize the existing .NET/SQL Server legacy monolith

**Goal:** retain the current application while making its behavior deterministic and
compatible with the shared contract.

Work:

1. Keep .NET 8 Blazor Server, EF Core, SQL Server Express, and the current visual
   experience.
2. Resolve the competing `/import` surfaces into one working, tested route.
3. Standardize configuration and the performance API key without a committed production
   default.
4. Add safe image-path handling, `/healthz`, `/readyz`, deterministic database/import
   behavior, and explicit SQL Server load-test semantics.
5. Verify and repair OpenTelemetry traces, metrics, and logs.
6. Add unit/integration tests and make the application pass the shared acceptance suite.
7. Update `dotnet/README.md` without adding the student-facing container solution.

Exit criteria:

- The .NET app remains recognizable and functionally compatible with the current
  workshop.
- It passes the same behavior and security contract as the Java baseline.
- SQL Server Express remains local to the .NET legacy VM.
- No container/IaC solution is exposed in the active baseline application folder.

### P2B — Build the Java/PostgreSQL legacy monolith

**Goal:** deliver a deterministic, intentionally monolithic baseline without adding
cloud-native complexity prematurely.

Application work:

1. Create one Maven module under `java/`.
2. Implement Spring MVC/Thymeleaf pages for catalog, filtering, search, detail, import,
   and error states.
3. Add a safe local image-store abstraction and `/images/{filename}` route.
4. Use Flyway-owned PostgreSQL migrations and JPA validation; never use runtime schema
   auto-creation.
5. Use UUID figure IDs, explicit constraints, `timestamptz`, category/name indexes, and
   case-insensitive search.
6. Implement transactional startup/upload import with validation, duplicate skipping,
   clear failure behavior, and import metrics.
7. Reimplement `/perftest/catalog` with API-key validation and a bounded,
   PostgreSQL-safe work factor.
8. Add `/healthz` liveness and `/readyz` database/import readiness.
9. Add structured console logging, HTTP/JDBC instrumentation, custom import/query/perf
   metrics, and standard OTLP configuration.
10. Add unit, MockMvc, PostgreSQL Testcontainers, image-security, import-idempotency, and
    health tests.
11. Write concise run/test/configuration instructions in `java/README.md`.

Exit criteria:

- The Java app passes the P1 acceptance suite.
- Fresh PostgreSQL plus Flyway plus seed import is deterministic.
- Liveness remains healthy during a database outage while readiness fails.
- The Java baseline has no .NET or SQL Server runtime dependency.
- The baseline runs as a JAR and does not include the student-facing Docker solution.

### P3 — Implement facilitator dual-VM provisioning

**Goal:** provision reproducible, separate .NET/SQL Server and Java/PostgreSQL legacy
VMs for every participant.

Work:

1. Extend `baseInfra/terraform` so a facilitator deployment creates two Windows VMs per
   participant sharing the existing Bastion/VNet/NAT foundation before the workshop.
2. Preserve and pin SQL Server Express/.NET provisioning on the .NET VM.
3. Add a pinned PostgreSQL Windows service plus Java runtime/JDK/Maven Wrapper workflow
   on the Java VM.
4. Deploy the corresponding application, seed manifest, JSON, and images to each VM.
5. Provide clear stack-specific start and diagnostic workflows.
6. Add outputs/naming that unambiguously identify `dotnet` and `java` VMs.
7. Preflight doubled VM/vCPU/storage quota and cost; document deallocation of the
   unselected VM after Challenge 0.
8. Keep Bastion/VNet/NAT structure but fix Terraform formatting and documentation drift.
9. Stop downloading mutable raw `main` content; use a release or immutable commit.
10. Remove committed passwords/keys and source them from sensitive facilitator inputs or
   generated per-environment values.
11. Preinstall pinned VS Code, .NET, Java, and Copilot tooling needed by Challenge 1C.
12. Register providers needed by ACA, ACR, Azure SQL, PostgreSQL, Monitor, Defender, and
    SRE Agent.
13. Add post-provision smoke checks for both VMs, applications, images, and databases.

Exit criteria:

- A clean Terraform deployment produces both usable VMs without hidden manual setup.
- Students are not required to provision or configure either legacy VM.
- Restarting either VM does not corrupt or duplicate data.
- Facilitators can deallocate the unselected VM without affecting the selected track.
- No weak shared secret is committed to Git.
- Provisioning is pinned and repeatable.

### P4 — Build the shared Azure target and path contract

**Goal:** provide one shared compute/operations model with database-specific target
modules, without coupling students to one migration method.

Work:

1. Retain and repair the Azure SQL target for the .NET track.
2. Add Azure Database for PostgreSQL Flexible Server for the Java track.
3. Define shared reference Bicep modules for ACR, ACA, managed identities, external
   image storage, Log Analytics, and Application Insights plus database-specific modules.
4. Use immutable image tags, ACR managed-identity pulls, HTTPS-only ingress, health
   probes, bounded scaling, and secure parameters.
5. Support password-in-ACA-secret for the simplest path and managed identity/Entra
   authentication as the preferred advanced mode; prohibit source-code secrets.
6. Provide deterministic database migration/verification workflows:
   - SQL Server Express to Azure SQL Database.
   - PostgreSQL to PostgreSQL Flexible Server.
7. Add deployment outputs that populate the common modernization contract.
8. Validate templates with Bicep build/what-if and enforce a clean bootstrap when the
   initial app image has not yet been pushed.

Exit criteria:

- Both golden deployments can be created from scratch and pass the acceptance suite.
- All required outputs are available without exposing secrets.
- The reference architecture works with either Azure Files or Blob-backed images.

### P5 — Author the three alternative modernization paths

These workstreams start after P1-P4. Each path applies to both source stacks. Implement
stack-specific solution slices in parallel child sessions and integrate them under one
shared challenge README and acceptance rubric.

#### Path 1A — Manual modernization

1. Baseline characterization and backup.
2. Provision the selected managed database:
   - Azure SQL for .NET/SQL Server.
   - PostgreSQL Flexible Server for Java/PostgreSQL.
3. Migrate schema/data with engine-native tools and verify counts/constraints.
4. Point the VM app at the managed database and prove separation before changing
   compute.
5. Create a non-root multi-stage container for the selected runtime.
6. Externalize images using Azure Files as the compatibility-first reference solution.
7. Push to ACR, deploy to ACA, and verify health/scale.
8. Produce IaC, test evidence, modernization contract, and rollback runbook.

This is the lowest-variance reference path and retains the spirit of the current
Challenge 1.

#### Path 1B — Complete rewrite with standard GitHub Copilot

1. Run the shared characterization suite and treat it as the behavioral oracle.
2. Have students ask GitHub Copilot to plan a bounded reimplementation.
3. Permit a similar stack; preserve the selected database family and require one app
   container, a separated managed database, preserved behavior, and ACA readiness.
4. Generate/review code in slices, running tests after each slice.
5. Require explicit human review of schema, security, configuration, generated
   dependencies, and error handling.
6. Migrate data, deploy, and prove parity through the shared harness.
7. Record the architecture delta and Copilot decisions rather than grading prompt style.

The solution should provide checkpoints, prompts, and a reference slice—not a
copy/paste complete implementation.

#### Path 1C — GitHub Copilot modernization

1. Use the pinned GA VS Code IDE extension.
2. Assess the selected .NET or Java runtime/framework, cloud readiness, configuration,
   security/CVE, database connectivity, and local-file findings.
3. Review and edit the generated plan before execution.
4. Run only preflighted supported tasks, then review diffs and validate build/tests.
5. Use supported containerization/IaC/deployment capabilities.
6. Perform the selected SQL Server/Azure SQL or PostgreSQL schema/data migration
   explicitly; never claim the extension completes the cutover automatically.
7. Capture assessment, plan, task results, test/CVE results, modernization contract, and
   rollback runbook.

The preview Modernize CLI appears only in an optional appendix. The required challenge
must not depend on it.

Exit criteria for every path:

- Same application behavior and seed-data invariants.
- The matching managed database, one ACA application container, immutable ACR image,
  external durable images, externalized configuration, and no committed secrets.
- Acceptance suite passes.
- Modernization contract and rollback runbook are complete.

### P6 — Repair and adapt shared load, CI/CD, and observability challenges

These can proceed as separate parallel workstreams after both golden P4 deployments are
stable.

#### Challenge 2: load and autoscaling

- Support both SQL Server/Azure SQL and PostgreSQL metrics/queries based on the selected
  contract.
- Keep the stable performance endpoint and one canonical API key.
- Check in a repeatable Azure Load Testing/JMeter artifact rather than portal-only
  instructions.
- Validate ACA replica scaling, the selected database load signal, bounds, and recovery.

#### Challenge 3: CI/CD and revisions

- Provide stack-specific triggers/templates for `dotnet/` and `java/` plus relevant IaC.
- Build/test with the appropriate .NET or Maven toolchain, produce an immutable image,
  and push to ACR.
- Use GitHub OIDC and least-privilege Azure roles; no registry admin or long-lived
  credentials.
- Deploy a zero/low-traffic revision, smoke-test it, require environment approval,
  promote traffic, and document rollback.
- Ensure all workflow files are placed or copied to the actual repository workflow
  location.

#### Challenge 4: observability

- Preserve vendor-neutral app instrumentation.
- Configure ACA/OpenTelemetry/Azure Monitor integration.
- Require evidence for traces, metrics, and logs, including HTTP, SqlClient or
  JDBC/PostgreSQL, exceptions, imports, and deployment revision.
- Standardize:
  - `service.name=mh-catalog-dotnet` or `mh-catalog-java`
  - `service.namespace=app-innovation`
  - `service.version=<commit-or-image-tag>`
  - `deployment.environment=lab`
  - an ACA revision identifier
- Add KQL queries and a small dashboard/workbook covering error rate, latency, database
  dependency failures, replica count, and cold starts.

### P7 — Add required Defender for Cloud challenge

**Facilitator foundation**

1. Use a dedicated workshop subscription.
2. Enable and budget:
   - Defender CSPM with Serverless Containers and Registry access.
   - Defender for Containers/image vulnerability assessment.
   - Defender for Azure SQL/database protection.
   - Defender for Open-Source Relational Databases.
   - Defender for Servers P2 on both retained legacy VMs.
3. Pre-warm ACA and ACR coverage; allow for the documented serverless-container delay.
4. Assign students Security Reader/Reader and keep plan/policy administration with
   facilitators.
5. Seed and snapshot deterministic findings before the workshop.
6. Add post-workshop plan/agent cleanup and cost verification.

**Student challenge**

1. Compare Defender coverage for the selected legacy VM and its modernized
   ACA/ACR/managed-database stack.
2. Explain why ACA has posture/image context but no host/runtime Defender sensor.
3. Inspect VM, ACA, image, database, MCSB, recommendation, and attack-path evidence.
4. Remediate a controlled set of issues:
   - Disable ACR admin and preserve pull through managed identity.
   - Enforce HTTPS-only ACA ingress.
   - Restrict or document Azure SQL/PostgreSQL network exposure as appropriate.
   - Restrict VM management exposure or validate JIT where configured.
5. Capture before/after ARM/IaC state, recommendation evidence, image digest/scan, and
   Secure Score/MCSB context.

Grading must not wait for a new live recommendation or attack alert.

### P8 — Add required Azure SRE Agent challenge

**Facilitator foundation**

1. Provision an agent in a supported subscription/region for every isolated participant
   or team environment.
2. Scope its managed identity to the participant/team resource group using Reader,
   Log Analytics Reader, Monitoring Reader, and only the narrow write permission needed
   for the approved rollback.
3. Keep facilitators as SRE Agent Administrators/approvers.
4. Connect the app's Log Analytics and Application Insights resources.
5. Configure an Azure Monitor incident response plan explicitly in Review mode.
6. Retain a known-good ACA revision.
7. Seed a bad revision with a harmless non-secret selected-database endpoint/configuration
   error and a deliberately incorrect readiness routing setup so traffic produces
   observable failures while rollback remains immediate.
8. Create and preflight an alert that reaches the response plan.
9. Add a short knowledge/runbook document stating topology, safe rollback, forbidden
   actions, and verification steps.
10. Verify agent audit events reach its Application Insights instance.

**Student challenge**

1. Ask the agent to scope the incident and identify the affected revision/time window.
2. Require it to correlate ACA revision/traffic, deployment history, request failures,
   exceptions, SqlClient or JDBC dependencies, and selected-database availability.
3. Challenge the hypothesis and request supporting evidence plus alternatives.
4. Review the exact rollback proposal, blast radius, and verification plan.
5. Have the facilitator approve the traffic shift to the retained healthy revision.
6. Verify recovery in the application, telemetry, alert state, Activity Log, and SRE
   Agent audit trail.
7. Produce a concise incident summary and prevention action.

Autonomous mode, destructive actions, secret changes, and subscription-wide permissions
are prohibited.

### P9 — Reconcile optional tracks, documentation, and repository cleanup

1. Move current optional tracks to `ch07-enterprise` and `ch07-innovation`.
2. Remove Defender duplication from enterprise content while retaining private
   networking, managed identity, Key Vault, WAF, CMK, policy, and advanced governance.
3. Adapt innovation examples to both .NET/SQL and Java/PostgreSQL.
4. Rewrite root, facilitator, dual-VM, .NET, Java, challenge, solution, and troubleshooting
   documentation.
5. Update `docs/Design.md`, `docs/ImplementationLog.md`, and, after confirmed fixes,
   `docs/CommonErrors.md`.
6. Retain both application sources and both database provisioning paths as first-class
   workshop assets.
7. Remove stale duplicate templates, weak parameter files, missing-file references, and
   mutable `main` downloads.
8. Add a facilitator matrix covering prerequisites, subscriptions, regions, roles,
   quotas, paid Defender plans, SRE Agent registration, Copilot entitlement, tool
   versions, pre-warm checks, and cleanup.

### P10 — End-to-end workshop validation

Validate in a clean, disposable workshop subscription:

1. Terraform facilitator infrastructure from scratch.
2. Startup, behavior, restart, and acceptance tests on both legacy VMs.
3. All six combinations: two baselines times three Challenge 1 paths.
4. Both golden deployments and modernization contracts.
5. Load test, autoscaling, and database recovery.
6. CI/CD revision, approval, promotion, and rollback.
7. Traces, metrics, logs, dashboards, and correlation attributes.
8. Defender paid-plan coverage and deterministic remediation evidence.
9. SRE Agent incident delivery, investigation, Review approval, rollback, recovery, and
   audit evidence.
10. Participant permission boundaries, cross-participant isolation, secret scanning,
    IaC validation, cleanup, and paid-service shutdown.

The rewrite is complete only when every required challenge has matching student
instructions, facilitator prerequisites, solution artifacts, and machine-verifiable
success criteria.

## Expected file/component changes

| Area | Action |
| --- | --- |
| `java/` | Add the new Spring Boot/Thymeleaf/PostgreSQL monolith, tests, config, migrations, and README |
| `dotnet/` | Retain and stabilize the .NET/SQL Server baseline, tests, config, telemetry, and README |
| `tests/acceptance/` | Add the path-neutral Python/uv acceptance harness |
| `workshop/contracts/` | Add seed and modernization contract schemas/examples |
| `data/` | Retain assets; add a canonical manifest and document the verified 198/20 counts |
| `baseInfra/scripts/` | Retain/pin SQL/.NET provisioning and add separate PostgreSQL/Java provisioning |
| `baseInfra/terraform/` | Provision two named VMs per participant and update providers, quota inputs, outputs, sensitive values, Defender/SRE prerequisites, and docs |
| `challenges/` | Add ch00, split ch01, retain/adapt ch02-ch04, add ch05/ch06, renumber optional tracks |
| `solutions/` | Mirror every required challenge and remove placeholder/duplicate solutions |
| `.github/workflows/` | Add validated .NET and Java CI/CD reference workflows where students expect them |
| `docs/` | Rewrite design/history and add confirmed operational pitfalls |
| Root `README.md` | Explain the two-baseline plus three-path selection matrix, rejoin flow, prerequisites, and facilitator gates |

## Coordinated implementation session graph

The coordinator owns the contract foundation and the first vertical slice. Child sessions
start only from an exact passing integration commit, own disjoint files, and may not create
nested sessions. At most three implementation sessions may run concurrently.

1. **Coordinator-owned foundation gate:** complete P0/P1 research artifacts, behavior
   contract, schemas, representative fixtures, acceptance harness, package/container
   requirements, and migration/reset boundaries. Freeze this gate only after contract
   tests and the contract/decomposition review pass.
2. **Coordinator-owned .NET vertical-slice gate:** implement P2A from input through
   transactional publication, database persistence, routes/UI/images, health,
   performance, telemetry, and full acceptance evidence. No consumer or deployment
   session starts before this integration commit passes.
3. **Java application child session:** implement P2B from the exact passing vertical-slice
   commit, consuming the frozen contracts and conformance vectors. Stop and report rather
   than locally changing a shared interface.
4. **Dual-VM infrastructure child session:** implement P3 only after both baseline
   producers are runnable and their output passes the shared acceptance contract.
5. **Shared Azure target child session:** implement P4 after P3 and both baseline
   compatibility checks pass. Deployment and cutover automation must consume the frozen
   producer protocol, schemas, and evidence format.
6. **Six path slices:** implement the .NET and Java P5A/P5B/P5C slices in dependency-safe
   waves of at most three sessions from the same accepted shared-target commit. Integrate
   and retest each completed slice promptly.
7. **Downstream challenge sessions:** load, CI/CD, and observability may run in parallel
   only after both golden deployments and their handoff bundles pass full validation.
8. **Defender session:** facilitator paid-plan foundation plus Challenge 5, after the
   deployed resource contract is stable.
9. **SRE Agent session:** facilitator agent foundation plus Challenge 6; depends on
   accepted CI/CD, observability, and rollback contracts.
10. **Documentation/integration session:** optional tracks, root narrative, stale-content
   removal, and full matrix after implementation semantics are stable.
11. **Final validation session:** execute all six combinations and required challenges in
   a disposable environment; fix only verified integration defects.

Every child prompt must include the base commit, owned and forbidden files, frozen
interfaces, representative fixtures, exact tests, non-goals, expected commit/handoff
format, and an instruction to stop if the contract must change. The coordinator owns
dependency alignment, plan approvals, cross-session corrections, semantic integration,
and final review.

## Principal risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Copilot modernization produces no useful findings | Preflight the current .NET app and the candidate Java/Spring version; seed supported cloud-readiness findings without introducing known vulnerabilities |
| Two VMs per participant exceed quota or budget | Preflight doubled vCPU/storage limits, distribute regions/subscriptions, and deallocate the unselected VM after Challenge 0 |
| Path B becomes an unbounded rewrite | Enforce one app container, shared acceptance tests, selected-database invariants, and a fixed ACA output contract |
| Database migration is mistaken for an extension capability | Teach and grade SQL Server-to-Azure SQL or PostgreSQL cutover explicitly in every path |
| Stack-specific challenge content drifts | Keep one shared challenge contract and acceptance rubric with explicit `dotnet/` and `java/` solution slices |
| Paid Defender findings are not ready during class | Enable all plans in advance, pre-warm coverage, snapshot findings, and grade deterministic state |
| ACA Defender expectations imply runtime protection | State and test the posture-only boundary explicitly |
| SRE Agent unavailable or unregistered | Treat subscription/region/incident/approval preflight as a hard workshop go/no-go gate |
| SRE Agent makes unsafe changes | Review mode, narrow RG scope, facilitator approval, retained healthy revision, no autonomous/destructive operations |
| Added required challenges make incomplete paths block students | Maintain two golden modernized deployments and contracts so teams can rejoin shared challenges |
| Provisioning remains mutable or leaks secrets | Pin artifacts/releases, remove committed credentials, use sensitive/generated inputs, and run secret scans |
| Challenge solutions drift again | Every challenge receives executable artifacts and machine-verifiable acceptance criteria in the same PR |

## Key official references

- GitHub Copilot modernization overview and availability:
  https://learn.microsoft.com/azure/developer/github-copilot-app-modernization/overview
- GitHub Copilot modernization for Java:
  https://learn.microsoft.com/azure/developer/java/migration/migrate-github-copilot-app-modernization-for-java
- GitHub Copilot app modernization for .NET:
  https://learn.microsoft.com/dotnet/core/porting/github-copilot-app-modernization-overview
- Supported Java modernization tasks:
  https://learn.microsoft.com/azure/developer/java/migration/migrate-github-copilot-app-modernization-for-java-predefined-tasks
- Defender posture for serverless containers:
  https://learn.microsoft.com/azure/defender-for-cloud/posture-for-serverless-containers
- Defender for Containers:
  https://learn.microsoft.com/azure/defender-for-cloud/defender-for-containers-introduction
- Defender for Databases:
  https://learn.microsoft.com/azure/defender-for-cloud/defender-for-databases-introduction
- Defender for Servers:
  https://learn.microsoft.com/azure/defender-for-cloud/defender-for-servers-overview
- Azure SRE Agent overview:
  https://learn.microsoft.com/azure/sre-agent/overview
- Azure SRE Agent supported regions:
  https://learn.microsoft.com/azure/sre-agent/supported-regions
- Azure SRE Agent run modes:
  https://learn.microsoft.com/azure/sre-agent/run-modes
- Azure SRE Agent pricing and billing:
  https://learn.microsoft.com/azure/sre-agent/pricing-billing
