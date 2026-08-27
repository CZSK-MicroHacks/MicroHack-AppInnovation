# Challenge 1 · Path 1C · modernization plan — .NET / SQL Server

**Produced by:** GitHub Copilot CLI acting as the modernization agent.
**Not produced by:** `vscjava.migrate-java-to-azure@1.23.26081703`. No VS Code exists in this
delivery, so no extension-generated task plan was reviewed or accepted. The task
decomposition, preflight gates and rollback steps below are mine.

**Baseline this plan is measured against:** SDK `8.0.424`, ASP.NET Core `8.0.30`,
**42 passed / 0 failed / 0 skipped**, TRX at `evidence/dotnet-baseline-net8.trx`.

**Archive provenance:** `4bf59f7ee8dae11259d73ba5a5d7cb0e3355c4af`.
**`sourceCommit`:** the commit of *this* modernized work once pushed — deliberately **not**
the archive provenance above. `challenges/ch01/README.md:195-197` states the two "are never
interchangeable", and `solutions/…/dotnet/README.md:159` forbids using the starting commit
for any build, migration, deployment or evidence. See *Provenance* at the end.

---

## Boundaries that hold for every task

Taken from `challenges/ch01-copilot-modernization/README.md` (Working Rules) and the
"Stop and replan" list at `solutions/ch01-copilot-modernization/dotnet/README.md:152-155`.

**Preserve, in all cases:**

- Azure SQL as the database family. Never Azure Files for images; `azure-blob` is required
  by `challenge-paths.json` for this slice.
- The frozen HTTP contract: `/healthz`, `/readyz`, `/images/{fileName}`, `/figure/{id}`,
  `POST /import`, `/perftest/catalog`, with existing status codes and JSON shapes.
- Telemetry identity: service `mh-catalog-dotnet`, namespace `app-innovation`, meter and
  activity source `LegoCatalog.App`, instrument names unchanged.
- The image-key security control in `LocalImageStore.IsCanonicalImageKey` and its path
  containment behaviour.
- All 42 tests green. The 14 frozen contract identities are a subset and are separately
  re-verified from the TRX by the handoff validator.

**Stop and replan immediately if a task:** touches files outside its declared scope,
changes the database family, puts a SQL credential in source, weakens TLS, alters a frozen
contract, replaces an immutable image reference, skips tests, or cannot be completed
without an unsupported transformation.

**Universal rollback:** every task is a single commit against a clean worktree.
`git checkout -- <declared scope>` before commit, `git revert <sha>` after. No task depends
on an uncommitted predecessor.

**Universal validation gate:**

```bash
export DOTNET_ROOT="$HOME/.dotnet-workshop"; export PATH="$DOTNET_ROOT:$PATH"   # tasks 1 only
dotnet build dotnet/LegoCatalog.sln   # TreatWarningsAsErrors=true, so warnings fail
dotnet test  dotnet/LegoCatalog.sln   # must stay 42/42
```

---

## Task 1 — Target .NET 10

| | |
| --- | --- |
| **Capability** | Framework version upgrade (the supported transformation Path 1C is built around) |
| **File scope** | `dotnet/src/LegoCatalog.App/LegoCatalog.App.csproj`, `dotnet/tests/LegoCatalog.App.Tests/LegoCatalog.App.Tests.csproj` |
| **Preflight** | worktree clean; baseline 42/42 recorded on 8.0.30 |
| **Change** | `net8.0` → `net10.0` in both projects; ASP.NET Core / EF Core / `Microsoft.AspNetCore.Mvc.Testing` 8.0.22 → 10.x; OpenTelemetry family as required by the 10.x stack |
| **Artifacts** | the two `.csproj` diffs; a fresh TRX |
| **Validation** | build clean under `TreatWarningsAsErrors`; **42/42**; re-run `dotnet list package --vulnerable --include-transitive` and confirm `SQLitePCLRaw.lib.e_sqlite3` GHSA-2m69-gcr7-jv3q has cleared |
| **Expected friction** | `TreatWarningsAsErrors=true` plus `GenerateDocumentationFile=true` turns any new analyzer diagnostic into a build failure. Fix the code, do not relax the setting — suppressing warnings to force a green build is a silent quality regression and is out of scope. |
| **Rollback** | `git checkout -- dotnet/src/**/*.csproj dotnet/tests/**/*.csproj` |
| **Stop if** | a test changes behaviour rather than merely compiling differently |

## Task 2 — Managed-identity authentication to Azure SQL

| | |
| --- | --- |
| **Capability** | Credential removal / Azure SQL readiness |
| **File scope** | `dotnet/src/LegoCatalog.App/Configuration/CatalogRuntimeOptions.cs`, `dotnet/src/LegoCatalog.App/Program.cs`, app `.csproj` |
| **Preflight** | Task 1 accepted and committed |
| **Change** | add `Azure.Identity` `1.21.0`; when the host is `*.database.windows.net` **and** no username is configured, acquire a token for `https://database.windows.net/.default` via `DefaultAzureCredential` and attach it to the `SqlConnection`. Keep `IntegratedSecurity` for the legacy local host so the source path still works. |
| **Artifacts** | connection-configuration diff; `.csproj` diff |
| **Validation** | 42/42; grep the tree to confirm no password literal and no `Password=` in any tracked file; existing `RuntimeIdentityConfigurationTests` stay green |
| **Rollback** | `git checkout --` the three files |
| **Stop if** | making this work needs a password anywhere in source, or needs `TrustServerCertificate=true` against an Azure host |

**Design note.** `CatalogRuntimeOptions.Load` already derives `Encrypt` from the host
suffix, so TLS turns itself on for Azure SQL without a code change. I will keep that
behaviour rather than restructure the loader — the smaller diff is easier to review and the
existing tests already pin it. The assessment recommends asserting TLS explicitly instead
of inferring it; that is a **recommendation, not part of this plan**, because it changes
behaviour the frozen tests do not currently require.

## Task 3 — `AzureBlobImageStore`

| | |
| --- | --- |
| **Capability** | Remove local-disk coupling; mandatory `azure-blob` provider |
| **File scope** | new `dotnet/src/LegoCatalog.App/Services/AzureBlobImageStore.cs`, `Program.cs`, `Endpoints/CatalogEndpoints.cs`, app `.csproj` |
| **Preflight** | Task 1 accepted |
| **Change** | add `Azure.Storage.Blobs` `12.29.1`; implement `IImageStore` against a container, authenticating with the same `DefaultAzureCredential`; select it when blob configuration is present, else keep `LocalImageStore` |
| **Artifacts** | new service file; DI and endpoint diffs |
| **Validation** | 42/42 **including `ImageSecurityTests` unchanged** |
| **Rollback** | delete the new file, `git checkout --` the rest |
| **Stop if** | the blob path cannot enforce the canonical-key rule, or Azure Files is proposed |

**The risk in this task, stated plainly.** `IImageStore` exposes `TryResolvePath`, which is
a filesystem idea: it returns a path that `CatalogEndpoints.cs:26-31` hands to
`Results.File`. Blob storage has no local path. The shape of the interface therefore has to
change, and that is the one place in this plan where a frozen contract is adjacent to the
work. The HTTP contract — `GET /images/{fileName}` returns the PNG or `404` — must not
move; only the internal seam may. **`IsCanonicalImageKey` must be applied before any blob
request**, or the traversal protection is silently lost while all six `ImageSecurityTests`
that only exercise the local store keep passing. That is the most likely way this task
produces a green build with a real regression.

## Task 4 — Azure Monitor OpenTelemetry exporter

| | |
| --- | --- |
| **Capability** | Telemetry to a managed backend |
| **File scope** | `dotnet/src/LegoCatalog.App/Program.cs`, app `.csproj` |
| **Preflight** | Task 1 accepted |
| **Change** | add `Azure.Monitor.OpenTelemetry.Exporter` `1.8.3`; register it for traces, metrics and logs when `APPLICATIONINSIGHTS_CONNECTION_STRING` is present, **alongside** the existing conditional OTLP exporter |
| **Artifacts** | `Program.cs` diff |
| **Validation** | 42/42; `TelemetryContractTests` unchanged; confirm resource attributes still carry `deployment.environment` and `azure.containerapps.revision.name` |
| **Rollback** | `git checkout -- dotnet/src/LegoCatalog.App/Program.cs` and the `.csproj` |
| **Stop if** | adding the exporter changes instrument or service names |

**Why this ordering matters.** The assessment recorded that all telemetry export today is
gated behind four `OTEL_EXPORTER_OTLP_*` variables, so an unconfigured app collects and
discards everything while looking healthy. The Azure Monitor registration must be gated on
its *own* variable, independently — if it is folded into the existing `hasOtlpExporter`
flag, Application Insights stays empty whenever OTLP is unset, and the Challenge 1
telemetry evidence step then produces an empty-but-successful result.

## Task 5 — Author `dotnet/Dockerfile`

| | |
| --- | --- |
| **Capability** | Containerization |
| **File scope** | new `dotnet/Dockerfile`, new `dotnet/.dockerignore` |
| **Preflight** | Tasks 1–4 accepted; 42/42 |
| **Change** | multi-stage build on the locked digest-pinned bases (`sdk:10.0.400-azurelinux3.0-amd64` → `aspnet:10.0.11-azurelinux3.0-amd64`); non-root user; `EXPOSE 8080`; `ASPNETCORE_URLS=http://+:8080`; all configuration from the environment |
| **Artifacts** | `dotnet/Dockerfile` |
| **Validation** | built by `az acr build`, not locally — this laptop is arm64 and the pinned bases are `amd64`; a local build would either fail or silently produce an arm64 image that ACA cannot run |
| **Rollback** | delete the file |
| **Stop if** | the image needs a secret baked in, or must run as root |

---

## Evidence produced after the tasks

- `evidence/task-results.json` — one record per task: name, capability, files changed, the
  human decision, command, exit code, artifact paths.
- `evidence/build-test-cve-summary.md` — exact SDK and runtime, test result, dependency and
  CVE result, unresolved findings.
- `evidence/dotnet-modernization.trx` — force-added, because `*.trx` is gitignored and
  Challenge 3 must read the run.
- `evidence/runtime-test-report.json` — the 14 frozen identities, per
  `runtime-test-evidence.schema.json`, bound to the final `sourceCommit`.

**`evidence/ide-extensions.txt` will not be written.** There is no extension inventory to
capture. Writing a plausible one from the versions published in
`workshop/toolchain.lock.json` would take two minutes and nothing downstream would ever
detect it — `challenge-paths.json` lists the file in neither `requiredEvidence` nor
`pathEvidence`, and no validator reads it.

Contrast that with `evidence/runtime-test-report.json`, which **cannot** be faked the same
way: the schema fixes all fourteen `id` values and pins each to an exact `testIdentity`
string, and `catalog_acceptance/handoff.py:211-228` re-parses the TRX and rejects the
handoff unless every one of those identities is present with outcome `passed`. The workshop
plainly knows how to build an unforgeable evidence artifact. That is what makes the
unvalidated one a defect rather than a limitation.

## Provenance

Two distinct fields, which this plan keeps separate:

| Field | Value | Why |
| --- | --- | --- |
| archive provenance (`.source-commit`) | `4bf59f7ee8dae11259d73ba5a5d7cb0e3355c4af` | the legacy baseline handed to me; absent on this laptop, so the published workshop commit is used |
| `sourceCommit` (deploy parameter, ACR tag, handoff `source.commitSha`) | the pushed commit of this modernized work | the identity of my own work |

`infra/main.bicep:104` asserts only that `sourceCommit` is 40 lowercase hex characters. It
never checks the commit exists, is reachable, or contains a `dotnet/Dockerfile`. Passing
the archive provenance there would deploy cleanly, tag a real image, and produce a handoff
that validates — then fail in Challenge 3, which checks the source out at that SHA and
builds `dotnet/Dockerfile` from it. `4bf59f7` contains no Dockerfile, because authoring one
is this challenge's exercise.
