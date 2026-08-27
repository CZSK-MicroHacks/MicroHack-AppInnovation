# Challenge 1 · Path 1C · assessment — .NET / SQL Server

**Produced by:** GitHub Copilot CLI acting as the modernization agent, on a macOS arm64
laptop.
**Not produced by:** `vscjava.migrate-java-to-azure@1.23.26081703`, the extension Path 1C
requires. No VS Code, no Bastion and no VM desktop exist in this delivery, so the pinned
IDE experience was never run. Everything below was derived by reading the source directly
and by executing the build, test and dependency tooling. Where the extension would have
contributed something this method cannot, that is stated rather than glossed.

**Archive provenance:** `4bf59f7ee8dae11259d73ba5a5d7cb0e3355c4af`.
`C:\MicroHack\source\.source-commit` does not exist here; the published workshop commit is
used in its place, and `git rev-parse HEAD` of the delivery branch is deliberately **not**
substituted for it.

**Scope assessed:** `dotnet/` (43 source files, 3,766 lines of C#), read against the
repository contracts in `workshop/contracts/` and the shared target in `infra/`.

---

## Baseline — measured, not assumed

| Property | Value | How established |
| --- | --- | --- |
| Source SDK | `8.0.424` | installed privately to `~/.dotnet-workshop`; matches the lock exactly |
| Source runtime | ASP.NET Core `8.0.30` | `dotnet --list-runtimes`; matches `toolchain.lock.json` `sourceRuntime` exactly |
| Build | clean, `TreatWarningsAsErrors=true` on both projects | `dotnet build` |
| Tests | **42 passed, 0 failed, 0 skipped** | `dotnet test`, TRX at `evidence/dotnet-baseline-net8.trx` |

This green baseline is the referee for every task that follows. It is the measurement the
path depends on and the one most at risk of being faked — see the note on roll-forward
under *Findings*.

---

## Observed facts

### 1. Runtime and framework

- `dotnet/src/LegoCatalog.App/LegoCatalog.App.csproj` and
  `dotnet/tests/LegoCatalog.App.Tests/LegoCatalog.App.Tests.csproj` both target `net8.0`.
- The application pins ASP.NET Core and EF Core at `8.0.22` and the whole OpenTelemetry
  family at `1.17.0`.
- `TreatWarningsAsErrors` is `true` in **both** projects, and
  `GenerateDocumentationFile` is `true` in the application. Any analyzer behaviour that
  changes between major versions becomes a build failure rather than a warning.
- `Program.cs:117` uses a file-scoped `public partial class Program;` so the test project's
  `WebApplicationFactory` can bind to it.

### 2. Cloud readiness, process model, health

- Health and readiness already exist and are contract-shaped: `/healthz` returns
  `{"status":"healthy"}` unconditionally; `/readyz` (`CatalogEndpoints.cs:60-104`) probes
  the database *and* the startup import, returning `503` with a `checks` object when
  either is not ready. **No work needed here** — this is unusually well prepared for ACA.
- The process is stateless apart from the two local-disk dependencies below.
- `StartupImportHostedService` performs a seed import at boot, and `/readyz` reports
  `not_ready` until it completes. On ACA this interacts with revision readiness probes and
  must be understood before the first deployment, not after.
- No `Dockerfile` exists anywhere under `dotnet/`. Authoring one is in scope and its
  content must be in the published commit, because Challenge 3 checks that commit out and
  builds it.

### 3. Configuration and secret handling

- `CatalogRuntimeOptions.Load` (`Configuration/CatalogRuntimeOptions.cs:25-106`) is a
  single, strict, fail-fast reader. It is already environment-first, with
  `Catalog:*` JSON keys only as fallback. This is genuinely good and should be preserved
  rather than replaced.
- **No secret is committed.** `appsettings.json` carries host `.\SQLEXPRESS` and database
  `LegoCatalog` but no username and no password, and `PERFTEST_API_KEY` has no default —
  `Required(configuration, "PERFTEST_API_KEY")` throws when it is absent.
- The credential model is already conditional (`:66-74`): with no
  `CATALOG_DATABASE_USERNAME` it sets `IntegratedSecurity = true`; with one it sets
  `UserID`/`Password`. The username/password pair is validated as all-or-nothing at
  `:45-49`.
- `Encrypt` is derived from the host name (`:52-60`): `true` only when the host ends
  `.database.windows.net`, otherwise `TrustServerCertificate = true`. Correct for the
  legacy VM, and it means TLS turns itself on when the host becomes Azure SQL — but it is
  *inferred*, not asserted.

### 4. Dependency security

`dotnet list package --vulnerable --include-transitive` against the restored baseline:

| Package | Version | Severity | Path | Advisory |
| --- | --- | --- | --- | --- |
| `SQLitePCLRaw.lib.e_sqlite3` | 2.1.6 | **High** | transitive, via `Microsoft.EntityFrameworkCore.Sqlite` 8.0.22 in the **test** project | [GHSA-2m69-gcr7-jv3q](https://github.com/advisories/GHSA-2m69-gcr7-jv3q) |

The application project has no vulnerable packages, and neither project has deprecated
ones. The single finding is test-only and does not ship in the container, but it rides on
EF Core 8 and is expected to clear when EF Core moves to 10. That expectation is a
prediction, and the task that performs the upgrade must re-run the scan to confirm it.

> **Correction, added after Task 1 executed.** The prediction above was **wrong**, and is
> left in place rather than edited away so the error is visible. EF Core 10.0.1 resolves
> `SQLitePCLRaw.lib.e_sqlite3` **2.1.11**, which still carries GHSA-2m69-gcr7-jv3q. The
> upgrade moved the version but did not clear the advisory. It was resolved instead by an
> explicit direct pin to 2.1.13 in the test project.
>
> Two things this exposes. First, an assessment's *expectations* are not findings, which
> is why the re-scan is mandatory rather than optional. Second, NuGet audit is enabled by
> default from .NET 10, so what was an advisory the .NET 8 build never mentioned becomes a
> hard `NU1903` build failure. That is a genuine improvement, but the fastest way to make
> the build green again is `<NoWarn>$(NoWarn);NU1903</NoWarn>`, which silences a security
> gate permanently and leaves a passing build behind. The remediation and the concealment
> are the same size and look equally plausible in a diff.

### 5. Database connectivity, schema ownership, transactions

- SQL Server is reached through EF Core with `UseSqlServer`, `CommandTimeout(15)` and
  `EnableRetryOnFailure()` (`Program.cs:19-24`). The retry policy is already appropriate
  for a managed service.
- Schema is owned by EF Core migrations: `Data/Migrations/202608180001_ContractBaseline.cs`
  plus a model snapshot. Ownership is explicit and versioned.
- `CatalogDbContextFactory` exists for design-time commands and injects a
  `design-time-only` value for `PERFTEST_API_KEY` so `Load` does not throw during
  `dotnet ef`. Non-obvious, and worth preserving through the upgrade.
- `Microsoft.Data.SqlClient` is referenced directly in `CatalogRuntimeOptions.cs:1` for
  `SqlConnectionStringBuilder`, but only transitively supplied through EF Core.
  Introducing token-based authentication makes that dependency explicit.

### 6. Local-file access — the machine coupling

Two hard couplings to the VM's disk, both configured at
`appsettings.json` as paths relative to the content root:

- **Images.** `CATALOG_IMAGES_PATH` → `../../../data/images`, read by `LocalImageStore`
  (`Services/LocalImageStore.cs`), served by `GET /images/{fileName}`
  (`CatalogEndpoints.cs:26-31`) via `Results.File(path, "image/png")`. 198 files.
- **Seed.** `CATALOG_SEED_PATH` → `../../../data/catalog.json`, read at boot by
  `StartupImportHostedService`.

`LocalImageStore` is already behind an `IImageStore` interface exposing exactly
`GetImageUrl` and `TryResolvePath`, and it is registered once
(`Program.cs:35`). The seam for a blob-backed implementation already exists.

`LocalImageStore.IsCanonicalImageKey` is a genuine security control, not incidental
validation: it requires a 40-character name, a `.png` suffix, and a round-trippable
canonical `D`-format GUID, then re-checks the resolved path stays under the root and the
file exists. **Any replacement must preserve this behaviour** — `ImageSecurityTests.cs`
exists to enforce it, and traversal protection is easy to lose when moving to a blob
client that has no concept of a path root.

### 7. Telemetry

- `CatalogTelemetry` owns one `ActivitySource` and one `Meter`, both named
  `LegoCatalog.App`, with four instruments including `db.client.operation.duration`.
- Service identity is already exactly what the frozen design wants: `mh-catalog-dotnet`,
  namespace `app-innovation`, `service.version` from `OTEL_SERVICE_VERSION`, plus
  `deployment.environment` and `azure.containerapps.revision.name` resource attributes.
- Export is **OTLP only, and conditional**: `hasOtlpExporter` (`Program.cs:42-48`) is true
  only when one of four `OTEL_EXPORTER_OTLP_*` variables is set; otherwise traces, metrics
  and logs are collected and dropped. Silent by design, and a trap for the telemetry
  evidence step — an application that exports nothing looks identical to one that is
  merely idle.

---

## Recommendations

Ordered so the cheapest validation comes first and every step is independently revertible.

| # | Change | Rationale | Validation |
| --- | --- | --- | --- |
| 1 | Retarget both projects to `net10.0`; move ASP.NET Core / EF Core to `10.x` | the version move is the point of Path 1C | build clean under `TreatWarningsAsErrors`; 42/42 still pass; re-run the CVE scan |
| 2 | Token-based Azure SQL auth via `Azure.Identity` `1.21.0` | Azure SQL is Entra-only; no application password may exist | 42/42; assert no password path remains reachable for a `.database.windows.net` host |
| 3 | `AzureBlobImageStore` on `Azure.Storage.Blobs` `12.29.1` with managed identity | removes the disk coupling; `azure-blob` is mandatory for this slice | 42/42, **including the existing `ImageSecurityTests`**, which must pass unchanged |
| 4 | Add `Azure.Monitor.OpenTelemetry.Exporter` `1.8.3` | telemetry evidence requires nonempty traces, metrics and logs in Azure Monitor | 42/42; exporter registers when a connection string is present |
| 5 | Author `dotnet/Dockerfile`, non-root, port 8080, digest-pinned bases | no image exists; it must be in the published commit | image builds; runs as non-root |

**Assert TLS rather than infer it (recommendation, not required by the contract).**
`Encrypt` is currently a side effect of the host name. Once the target is Azure SQL, a
typo in `CATALOG_DATABASE_HOST` silently downgrades to
`TrustServerCertificate = true` instead of failing. The workshop's own house style —
48 Bicep asserts that fail at submission rather than halfway through — argues for making
this explicit.

---

## Findings the extension would have owned, and what was lost

Path 1C's claim is that the tooling *assesses the whole application at once* and
*surfaces security work you would otherwise miss*. Judged against this run:

- **Assessment content: no loss.** Every area the path enumerates was assessable by
  reading 3,766 lines of well-organised C# and running two commands. The CVE finding came
  from `dotnet list package --vulnerable`, which is in the SDK and needs no extension.
- **Task plan: no loss, and arguably a gain.** The plan below is bounded, ordered and
  revertible because the codebase already has clean seams (`IImageStore`, a single
  configuration loader, EF migrations). The plan is only as good as those seams, and the
  tooling cannot create them.
- **The framework transformation: unmeasured.** Whether the extension's .NET 8→10 upgrade
  is faster or more accurate than doing it by hand cannot be judged from here. This is the
  one claim this delivery genuinely cannot test, and it should not be reported as if it
  had been.
- **What the extension would *not* have supplied either:** the green pre-upgrade baseline.
  That required installing the exact pinned SDK, and nothing in Path 1C's step 1 asks for
  it.

## Explicitly not measured

- The pinned IDE extension's own behaviour, its plan output, and its preflight refusals.
  Path 1C treats those refusals as the most interesting artifact of the path; this run
  produces none.
- `evidence/ide-extensions.txt`. **Deliberately not written.** No extension inventory
  exists to capture. The three pinned versions are published in
  `workshop/toolchain.lock.json`, so a convincing file is a two-minute forgery, and
  `workshop/contracts/challenge-paths.json` lists it in neither `requiredEvidence` nor
  `pathEvidence` — nothing downstream would ever detect the fake.

## Findings

1. **A roll-forward shortcut here would have produced a perfect-looking, meaningless
   baseline.** With only ASP.NET Core 10 installed, `dotnet test` on `net8.0` fails to
   launch its test host. Setting `DOTNET_ROLL_FORWARD=Major` makes all 42 tests pass
   immediately — on the *target* runtime. The "before" measurement would then be taken on
   the runtime being migrated to, so it could never detect a .NET 8→10 regression, while
   looking indistinguishable from a real baseline in every artifact. The correct fix was
   to install the pinned `8.0.424` SDK, which carries ASP.NET Core `8.0.30` — exactly the
   locked `sourceRuntime`.
2. **Telemetry export fails silently by default.** `hasOtlpExporter` gates all three
   signals on four environment variables. An application deployed before Application
   Insights is wired collects and discards everything, and looks healthy doing it. The
   chapter's own troubleshooting table lists the resulting symptom but not this cause.
3. **The lock's target SDK is not reachable.** `toolchain.lock.json` pins target SDK
   `10.0.400` with runtime `10.0.11`; the .NET 10 available to this machine is SDK
   `10.0.101` / runtime `10.0.1`. Both pinned *container* images do resolve in MCR, so the
   container build is unaffected — but a local `net10.0` build cannot reproduce the pinned
   SDK, and the source pin `8.0.424` installed without complaint, so the drift is
   target-side only.
