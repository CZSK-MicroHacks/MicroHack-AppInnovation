# Path 1C: GitHub Copilot modernization

Modernize one P3 catalog stack with the pinned GitHub Copilot modernization IDE
experience, then rejoin the shared Challenge 1 target. Choose exactly one stack:

- [.NET 8.0.30 and SQL Server 2022](../../solutions/ch01-copilot-modernization/dotnet/README.md)
- [Java 17.0.20+8, Spring Boot 3.5.16, and PostgreSQL 18](../../solutions/ch01-copilot-modernization/java/README.md)

The destination is the frozen P4 design: one non-root Azure Container Apps
application, the matching managed database, immutable ACR image identity,
managed identity, direct Azure Monitor OpenTelemetry export, and 198 images in
Azure Blob Storage. Use `infra/main.bicep`, the selected stack's existing
Dockerfile, `catalog-migrate`, and the shared acceptance harness. Do not replace
or reinterpret those interfaces.

## Required IDE product

Both P3 VMs must expose these exact signed Visual Studio Marketplace packages
from `C:\ProgramData\MicroHack\vscode-extensions`:

| Extension | Locked version |
| --- | --- |
| `github.copilot` | `1.388.0` |
| `github.copilot-chat` | `0.48.1` |
| `vscjava.migrate-java-to-azure` | `1.23.26081703` |

`vscjava.migrate-java-to-azure` is the unified GitHub Copilot modernization
extension for this workshop and is required on both the .NET and Java VMs.
Historical Java or .NET upgrade extensions might also be installed on a
stack-specific VM, but they are not the required Path 1C modernization product.

From the repository root on the selected P3 VM, capture the exact inventory:

```powershell
New-Item -ItemType Directory -Force evidence | Out-Null
$ExtensionRoot = 'C:\ProgramData\MicroHack\vscode-extensions'
code --list-extensions --show-versions --extensions-dir $ExtensionRoot |
  Sort-Object |
  Tee-Object evidence\ide-extensions.txt
```

Stop if any required ID or version differs. Do not install a newer package,
switch to a mutable source ref, or continue with an unsigned VSIX.

## Working rules

1. Record `git rev-parse HEAD` as the exact lowercase 40-hex source commit.
   Work on a branch and keep secrets outside Git.
2. Use the IDE experience in guided mode. Assessment, plan, and task output is
   evidence, never proof that runtime behavior, deployment, or cutover works.
3. Review and edit every generated plan before execution. A human owns the
   target runtime, database family, image provider, authentication, and rollback
   decisions.
4. Preflight each proposed task against the installed product. Run only a
   supported task with a bounded file scope and explicit validation command.
5. After every task, review `git diff`, reject unrelated edits, and run the
   stack build and tests. Commit or revert the bounded task before proceeding.
6. Stop and replan if a task changes a frozen contract, changes database
   family, selects Azure Files, weakens managed identity, introduces a mutable
   image or dependency, commits a secret, deletes source data, or cannot name
   its validation.
7. Azure execution requires the facilitator-approved P4 bootstrap output.
   Path 1C does not authorize creation, deletion, or mutation outside that
   target.

## Assessment and reviewed plan

Open the selected repository root in VS Code and use the unified modernization
experience to assess all of these areas:

- source and target runtime/framework compatibility;
- cloud readiness, process model, health endpoints, and container suitability;
- configuration externalization and secret handling;
- dependency security and CVE findings;
- database connectivity, authentication, schema ownership, and transaction use;
- local-file reads/writes, especially `data/images`, seed data, and file logs.

Save the reviewed result as `evidence/assessment.md`. The document must separate
observed facts from recommendations and identify unsupported or irrelevant
findings.

Generate a task plan, review it line by line, and save the approved version as
`evidence/modernization-plan.md`. It must preserve the selected database family
and require `azure-blob` with managed identity. For each proposed task, record:

- supported IDE capability and exact files in scope;
- prerequisites and a clean-diff preflight;
- expected generated or modified artifacts;
- build, test, and security validation;
- stop/replan triggers and rollback of that task.

Use supported runtime/framework, managed-identity code preparation,
containerization, IaC, and deployment capabilities only where their preflight
matches this repository. The final container and IaC are still the frozen
repository-relative `dotnet/Dockerfile` or `java/Dockerfile` and
`infra/main.bicep`; generated alternatives must not silently replace them.

## Required boundary

The extension can assess code, prepare supported application transformations,
and produce reviewed modernization artifacts. It does **not** prove behavior
and it does **not** perform the database schema/data cutover for this workshop.

Database export, import, principal creation, corpus verification, and image copy
are always explicit native `catalog-migrate` commands run from the selected P3
source VM. Mutating commands require a bootstrap-stage target output, the exact
target resource ID repeated in `--confirm-target-resource-id`, and `--execute`.
They reject nonempty targets. Images must be copied to the `azure-blob`
resource declared by the bootstrap output.

## Evidence and exit criteria

Path-specific evidence is exact:

- `evidence/assessment.md`
- `evidence/modernization-plan.md`
- `evidence/task-results.json`
- `evidence/build-test-cve-summary.md`

The shared handoff bundle is also required:

- `evidence/azure-target-output.json`
- `evidence/migration-report.json`
- `evidence/acceptance-report.json`
- `evidence/runtime-test-report.json`
- `evidence/telemetry-report.json`
- `evidence/modernization-contract.json`
- `evidence/rollback-runbook.md`

Finish only when:

1. every approved task has a reviewed diff and passing stack validation;
2. native runtime evidence contains all fourteen frozen tests;
3. the image commit tag resolves to the exact deployed digest and the retained
   baseline revision is healthy, inactive, distinct, and uses that same digest;
4. full acceptance passes against the managed database and all 198 Blob images;
5. telemetry evidence has nonempty resources, traces, metrics, and logs;
6. the rollback runbook is executable and repository-contained; and
7. native `catalog-migrate render-handoff --path copilot-modernization
   --rollback-runbook evidence/rollback-runbook.md ...` creates handoff `1.3.0`,
   which passes `python -m catalog_acceptance.handoff_cli`.

## Optional appendix: preview orchestration

The Modernize CLI is public preview and optional. A facilitator may demonstrate
its portfolio assessment and planning flow separately, but it is not a
prerequisite, required task, evidence producer, deployment tool, or replacement
for the signed IDE extension in this challenge.
