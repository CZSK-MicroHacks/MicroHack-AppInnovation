# Challenge 1 Copilot-rewrite Java arm feedback

## Scope and provenance

- Path: `copilot-rewrite`, Java/PostgreSQL slice
- Immutable workshop baseline: `4bf59f7ee8dae11259d73ba5a5d7cb0e3355c4af`
- Execution host: macOS laptop, no-deploy arm (not the provisioned Windows VM)
- Checkpoints 1–4 executed locally; checkpoints 5–8 inspected only
- Azure boundary: no `az`, `azd`, `az acr build`, deployment, migration, role assignment,
  or cleanup was attempted at any point.

This file was produced late. It was a deliverable of the original brief and was missed
through two close-outs; it exists because a completeness poll asked what had never been
delivered. That omission is recorded here rather than quietly repaired.

## Timings

**Per-step timings were requested by the brief and were not captured.** No instrumentation
was added at the time and the durations cannot now be reconstructed without inventing them,
so none are reported. Only these anchors are real:

| Anchor | Timestamp (UTC) | Source |
| --- | --- | --- |
| Checkpoint 1 native suite complete, 34 tests | 2026-08-27T21:51:32Z | `evidence/surefire-reports` mtime |
| Runbook fixes committed | 2026-08-28T02:13:12Z | `383b9f7`, `5393507` |
| Regressed fixes restored after rebase | 2026-08-28T02:15:05Z | `d0420e2` |
| JDK guidance retracted | 2026-08-28T13:41:29Z | `1fa80cf` |
| Evidence committed | 2026-08-28T14:07:29Z | `216433e` |

The only durations measured at all are test-runner self-reports: the Java suite at 25.6 s
and the acceptance suite at 53–60 s across runs.

## What was executed, and how honestly

- **Checkpoint 1** — Java suite **34 passed**, including `PostgreSqlIntegrationTest`, which
  the VM-based Java track excluded. Docker 27.4 was present locally.
- **Frozen contract surface — 14/14 `Contract.*` display names green**, matching the bar the
  Java modernization track reached. The rewrite path can reach the same frozen surface.
- **Acceptance harness — 612 passed, 1 skipped.** This green is qualified below.
- **`catalog_acceptance --profile full`** was run locally, not `smoke`.
- **Checkpoint 4** — a candidate Dockerfile was authored, which is what demonstrated the
  blocking finding below. It was never committed; it exists only in session state.

**The checkpoint-1 fenced block was never executed as a block.** It opens with
`set -euo pipefail` and gates on `code --list-extensions` at
`solutions/ch01-copilot-rewrite/java/README.md:76`. The VS Code CLI is absent on this host,
so the block aborts before reaching Maven. The constituent commands were run individually.
"Executed for real" therefore means the commands inside the block ran; the block did not.

## Unsatisfied gates

1. **The rewrite path cannot keep the shared static suite green.**
   `MODERNIZATION_SURFACE` is derived from the *modernization* diff, freezing 42 of 50 Java
   sources and leaving 1 of 5 suggested slices legal. `MODERNIZATION_ADDITIONS["java"]`
   contains `Dockerfile`, so performing checkpoint 4 breaks the assertion **with both
   diagnostics printing an empty list**, giving a participant no way to read the cause.
   The 612-passed run above is green **only because `--deselect` suppresses that guard.**

   **Disposition — remedied upstream after this file was written.** As raised, this gate was
   described as unsatisfiable and the deselect as "a mitigation, not a fix". That judgement
   was accurate at the rev it was written against and is superseded at
   `origin/rewrite-integration`. Commit `ff70fac` reclassifies
   `test_reference_tree_differs_from_legacy_only_where_the_workshop_teaches` as a
   **repository-authoring guard rather than a participant gate** — a participant who authors
   the Dockerfile checkpoint 4 asks for puts the name on both sides of the comparison, so
   "nothing is undeclared and nothing is missing; the participant simply did their homework."
   The deselect is therefore the correct answer, not a workaround, and
   `test_rewrite_runbooks_deselect_the_reference_tree_authoring_guard` now *requires* both
   rewrite runbooks to carry it (2 invocations each) while the modernization runbooks keep
   running the guard in full.

   **This arm did not detect that.** `MODERNIZATION_ADDITIONS` is byte-identical at both
   revs, so re-reading the constant reports "unchanged, still open" whether or not the
   finding was closed — the remedy was a reclassification plus a runbook requirement, and
   neither is visible in the substrate the symptom lives in. Recorded as an instance of
   mechanism E in `docs/CommonErrors.md`.
2. **The extension preflight gate at `:76`** is unsatisfiable without the VS Code CLI and was
   bypassed, not met.
3. **No handoff instance was produced.** Checkpoint 8 was inspect-only, so the handoff
   contract was never exercised end-to-end from this path.

## Ambiguities a participant hits

1. **The Dockerfile location is stated wrongly and the wrong term is *defined*.** The
   challenge directs the Dockerfile "at the repository root" while the frozen registry pins
   `java/Dockerfile`, and the challenge separately defines "the repository root" as
   `C:\MicroHack\source`. A participant following the instruction lands the file one
   directory above the registry pin, above the contract test that reads it, and above
   `az acr build`. Four documents carried the claim, not one.
2. **Checkpoint numbering diverges between challenge and runbook, with no crosswalk.** Eight
   numbered checkpoints against six runbook sections, and the same sentence appears as
   "the image itself is built in checkpoint 7" and "…in section 5".
3. **Slice 5 refers to "the existing non-root container image"** at a point in the ordering
   where the baseline deliberately ships no Dockerfile and checkpoint 4 has not yet authored
   one. The artifact does not exist under any reading.
4. **`--profile smoke` at `:160` is the only profile invocation in the entire Java runbook.**
   Smoke skips checks that full performs and still prints `passed`, so a participant
   following the runbook literally cannot reach the stronger profile. This arm ran full, and
   did so by deviation rather than by instruction.
5. **Machine-produced test output cannot travel.** `java/.gitignore:1` excludes `target/`, so
   surefire's default output at `java/target/surefire-reports/` is silently uncommittable.
   The runbook copies it to `.workshop-tmp/`, a temporary directory, and never to
   `evidence/`. Producing the evidence artifact required a hand-copy the material does not
   describe.
6. **The handoff schema enumerates `copilot-rewrite-java`, but no `copilot-rewrite` instance
   ships anywhere in the tree.** The single shipped example declares
   `path = copilot-modernization`, and it cannot validate in the location it ships in,
   because the validator folds the handoff's own repo-relative path into the required
   evidence set while the registry pins a different filename.
7. **Prerequisite recovery off the VM is documented, but described as something else where
   it is linked.** The answers exist as `docs/CommonErrors.md` entries 45 and 101. Every
   challenge README routes troubleshooting to `docs/Troubleshooting.md` (12 links), which
   never mentions `javac`, a JDK or a JRE, and nothing under `challenges/` references the
   error registry at all (0 references). One hop does exist —
   `docs/Troubleshooting.md:211`, the last content line of a 212-line file — but it calls
   the registry *"resolved implementation pitfalls"*, which reads as historical-internal
   rather than as answers to errors you are about to hit, and the next sentence attaches a
   caveat discouraging the use it just enabled. This arm originally filed this as
   *unreachable*; that was an overreach, corrected to the measured scope above.

   **Scope limit, measured at `4bf59f7`, recorded because this item has since been read as
   a general routing defect.** It is not one, on three counts.

   - `docs/Troubleshooting.md` is not a stub. It carries **12 headings**, and its first
     content is a 13-row *"What you are seeing / Most likely cause / Go to"* table with
     working anchors into eight sections. It routes `uv` resolution failures to
     `--no-config`, `docker` *"not recognized"* to the deliberate no-daemon explanation,
     and covers `pytest`, `az deployment`, `/healthz`, and the two-SHA confusion. The
     registry link being last matters much less than it appears, because a reader who
     needs the common symptoms never has to reach it.
   - Track coverage in that router is **symmetric**: `java` 4 mentions, `dotnet` 4.
     Section 3 names `java-smoke.json`, `provision-java.log` and `java-app.log` beside
     their .NET counterparts. There is no Java-side gap here.
   - **Entry 101's symptom is macOS-scoped** — its first line reads *"no compiler is
     available on macOS"* — and `challenges/ch01/README.md:26` mandates the VM. So the
     journey this item describes is only ever walked on a route the material forbids,
     which is the same disqualification that applies to the JDK install item this arm
     reported and had excluded.

   What survives is the link's placement and its wording, with **no demonstrated on-path
   reader who needs it**. That caps this at an editorial observation. The repository
   already mechanises the property it would otherwise be claiming is absent:
   `test_source_commit_override_has_a_symptom_route` asserts the router carries a
   self-serve entry for the most likely Challenge 1 failure.

   One argument this arm advanced for the opposite conclusion is also withdrawn.
   `docs/CommonErrors.md` is listed in the frozen contract's `coordinatorOwnedFiles`
   (`workshop/contracts/shared-challenges.json:16`), which looks like a declaration that
   the registry is not attendee-facing and would make the absent inbound links correct by
   design. It is not that. The prose defining the term
   (`docs/ImplementationLog.md:609`, `docs/CommonErrors.md:486`) makes it a **no-touch
   write boundary between the agents that built the repository**, not a statement about
   who reads the file. Reading an audience rule out of an ownership identifier is the
   same error as reading a signal type out of an attribute name.

## Reliability observation

Readiness cannot detect schema loss. `HealthController.java:49-55` implements
`databaseReady()` as `SELECT 1`, which succeeds whenever a connection opens, regardless of
whether the schema the application requires is present. The .NET stack has the identical
shape via `CanConnectAsync`. A replica whose table has been dropped therefore reports ready,
keeps receiving traffic, serves 500s, and is never restarted by the platform. This was later
observed live on the deployed environment — `/healthz` 200, `/readyz` 200, `/` 500 — in a
state that had persisted for over a day. Challenges 4 and 5 teach attendees to detect silent
failure, and the reference application ships the exact silent-failure shape those chapters
are about.

## Corrections this arm made to its own work

Five corrections were made to this arm's own filings. Two were surfaced by the facilitator
declining to take the arm's word; three the arm found by re-checking claims it had already
made. Listed in the order they happened:

1. **"The non-VM prerequisite path is unstated."** Refuted — `docs/CommonErrors.md` entry
   101 names this exact symptom, cause and resolution. This arm had invented a Homebrew
   route the material never mentions, hit its failure, and filed that as a workshop defect.
   The invented route was then *shipped* into `java/README.md` and the error registry.
   Withdrawn; retracted at `1fa80cf`.
2. **"Four environment variables are undocumented."** Refuted by the facilitator — all four
   are documented in one table, four rows below where the search stopped.
3. **The retraction in (1) was itself an overreach**, corrected at `8033b29`. It read entry
   101's *"do not install an unpinned JDK"* as forbidding host installs, and on that basis
   **deleted** the registry's only answer to a real failure — the Homebrew cask aborting in
   a non-TTY shell — while asserting in two files that a tarball or cask "is the wrong
   answer even when it appears to work". The registry makes no such prohibition: that
   sentence sits in a container-build context where *unpinned* means *not digest-pinned*.
   Three attempts to salvage the claim all failed. The entry was restored verbatim.
4. **"The error registry is unreachable from the participant path."** Corrected to measured
   scope. One hop does exist (`docs/Troubleshooting.md:211`). The cited evidence was a search
   for `javac|JDK|JRE`, which correctly establishes that the file does not discuss JDKs and
   was then used to claim it does not *link the registry* — a different question.
5. **A residue of (3) survived into this file** and into a second document after the claim
   had been retracted once. Found by re-reading rather than by anyone asking.

### Remedy shape, if this arm's JDK fix is taken

Recorded because the fix spans two commits with opposite shapes, and taking only the first
would ship a claim this arm retracted. Measured against `origin/rewrite-integration`.

The contradiction is live on the delivery branch: the tarball route appears **6 times** there
(3 in `java/README.md`, 3 in `docs/CommonErrors.md`) against **0** at `4bf59f7`, while entry
101's *"do not install an unpinned JDK"* is present at both. It was introduced, not inherited.

The two legs are not the same defect and need different treatment.

- **`java/README.md` is the defect.** It is the guide every off-VM reader is sent to, and it
  prescribed the tarball as *the* way to acquire prerequisites, competing with entry 101.
  `1fa80cf` **deletes** that block — this arm's HEAD has 0 tarball hits in that file — and
  replaces it with pointers into entries 101 and 45. It cherry-picks **cleanly**, and on its
  own it closes the routing half.
- **`docs/CommonErrors.md` is not a duplicate route.** Its tarball sits inside the *non-TTY
  cask* entry, which answers a different symptom — `brew install --cask` aborting without a
  TTY — and notes the tarball yields exactly the pinned `17.0.20+8`. That entry is defensible
  and should survive; deleting it strips a working escape hatch. What the delivery branch
  lacks is the **subordination**: `git grep 'host-install route' origin/rewrite-integration`
  exits 1, against 2 hits at this arm's HEAD.

So the fix to take is `1fa80cf`'s `java/README.md` plus **`8033b29`'s** registry text, not
`1fa80cf`'s. `1fa80cf`'s registry half asserts that *"an ad-hoc tarball or a Homebrew cask is
the wrong answer even when it appears to work"* — a blanket prohibition on host installs that
`8033b29` retracted two commits later, narrowing entry 101's *unpinned* to *not digest-pinned*
and re-admitting the tarball as a subordinate route. Cherry-picking `1fa80cf` alone imports
the retracted claim and removes the escape hatch; its `docs/CommonErrors.md` half also
conflicts, reproduced against `origin/rewrite-integration` directly.

**This arm described the fix as a deletion, which was accurate for `1fa80cf` and stale for its
own HEAD.** The guard that resolves it is the one this arm contributed a round earlier —
*diff the revs before diffing the quote* — and neither party applied it, because both
assumed a single-branch disagreement could not be a revision disagreement. It can, when a
branch corrects itself. The disposition is **superseded, not refuted**.

Two further self-catches concerned the write-up rather than the findings: a commit that
recorded the rule below but not the corollary it was derived from, caught by grepping the
commit for the thing it was believed to contain and finding nothing.

The shape these share is the most transferable thing this arm produced, and it is recorded
durably in `docs/CommonErrors.md` rather than only in correspondence:

> **A claim that the material is silent on X may not rest on a filtered search.** The
> original form: the filter could not have returned the counter-evidence. The sharper form,
> which covers a filter that is perfectly well built but answers a different question than
> the conclusion needs: **search for the thing being denied, not the subject matter around
> it.** Two corollaries, each learned by violating it — *counting a filter's hits is not
> reading them*, and *a non-zero exit is not a zero result*, since a broken query and a real
> negative both print nothing.

> **A measurement is only evidence for the claim whose property it tests.** Naming the
> property first, then choosing the instrument, is the whole discipline; choosing an
> instrument that is merely *nearby* produces a confident number about a different question.

Worked instance, in the direction that is easy to miss. To establish whether commits are
published, the reachable-looking check is:

```bash
git rev-parse @{u}                     # tests LOCAL TRACKING CONFIG
git ls-remote origin michalmar-ch01-java-rewrite-walkthrough   # tests REMOTE EXISTENCE
```

The first fails on a branch that was pushed from a different worktree, or pushed with an
explicit refspec, and it fails **identically** to a branch that was never pushed. It is a
correct measurement of the wrong property. Only the second contacts the remote.

The consequence is asymmetric and the dangerous direction is the less obvious one. A
*stale-behind* report under-claims work that exists, and the correction is cheap.
**An unreachable-when-reachable report invites someone to re-derive a fix that is already
published** — duplicated remediation, and a second copy that can drift from the first.

The general form: **"I measured it" is not a defence if the instrument answers an adjacent
question.** That is the same failure as reading a signal type out of an attribute name, and
as reading an audience rule out of an ownership identifier — three instances in this arm's
record of an artefact being consulted for a property it does not carry.

**The rule is not self-enforcing, including for whoever states it.** One round after it was
agreed, both parties broke it again on the same subject. The sharper sub-distinction, which
neither of us had:

```bash
git ls-remote origin <your-branch>            # TIP IDENTITY: what the ref points at now
git merge-base --is-ancestor 216433e 02b9930  # REACHABILITY: is this commit published
```

**A commit that is an ancestor of a remote ref is on the remote.** Reporting "not on origin"
because the tip is a different SHA tests tip identity and answers reachability — and the
error runs in *both* directions, so neither direction is the safe one to guess:

| instrument reads | claim made | verdict |
|---|---|---|
| local tracking config | "never pushed" | wrong — it was published |
| tip inequality | "not on origin" | wrong — it was an ancestor |
| `ls-remote` | "tip is X" | exact |

**And a third failure is neither party's error: the tip moves between messages.** A fetch and
a push that straddle each other produce two honest measurements that disagree, and nothing in
either output distinguishes *stale* from *superseded*. The only defence that survives latency
is to **cite a SHA together with the command and moment that established it**, so a reader can
tell a claim that was never true from one that has since stopped being true. Between
independent arms this is not pedantry — it is the difference between a correction and a
re-derivation of work that already exists.

**The same skew has a documentary form, and it is the one that cost the most here.** Citing a
rev where a file genuinely lacked a passage, after a later commit on the same branch restored
it deliberately, transmits a position already retracted. It is not an under-count; it argues
the opposite of the author's settled judgment. Deletion had been tried, found to leave the
case uncovered, and reversed on purpose — and a stale citation hides exactly that reversal.

The property worth carrying forward is where these failures occurred. **Every one of them
arose in the verification step, not the discovery step.** Nothing here was found carelessly;
it was *confirmed* carelessly. Confirmation is where the effort feels already spent, which is
exactly why it is under-defended.

## Not measured — do not infer from this arm

Any Azure deployment, ACR build, migration checkpoint, cloud telemetry, public-IP tenant
restriction, release stage, or handoff instance. The five-slice rewrite loop was not run end
to end; one slice's shape was exercised. The full acceptance profile was run locally only,
never against a deployed application.

**Screenshots: none exist.** No image artifact was captured at any point by this arm.

## Late finding — Ch4's database-dependency gate is weaker on Java by construction

**Read-not-run.** This arm never deployed and never queried Application Insights. The
static half below is executed against this tree at `b8d1709`; the live half is not, and
nothing here claims a record count.

Ch4 gates on database dependency telemetry — the Application Map showing the database as a
separate node (`challenges/ch04/README.md:154`), a `database-dependency-failures` query
counting "failed outbound calls tagged with a database system" (`:190`), and a required
deliverable, "a count of failed database dependency calls" (`:356`).

The tracks do not produce that telemetry equivalently. .NET registers
`AddSqlClientInstrumentation()` (`dotnet/src/LegoCatalog.App/Program.cs:86`), so every
database call on every route becomes a dependency record. Java registers no HTTP or JDBC
instrumentation library at all — its only `instrumentation` artifact is the logback *log*
appender, and the deployed image runs a bare `java -jar` with no `-javaagent`
(`solutions/reference/java/Dockerfile:25`) — so dependency records come solely from two
explicit call sites,
`CatalogService:47` and `PerformanceCatalogService:52`, both via
`CatalogTelemetry.startDatabaseSpan` (`:79`, `SpanKind.CLIENT`).

The consequence is specific: `/import` writes to the database under an `INTERNAL` span
(`CatalogImportService:28`), so a **failing import emits no dependency record on Java** while
emitting them on .NET. The most natural way to demonstrate a database fault produces a
populated `database-dependency-failures` result on one track and an empty one on the other,
and no document says so.

This is F-213's shape: material asserting a uniform result that holds on one substrate only.
Unlike F-213 this arm has **not** fixed it — the remedy is a judgement about how much
telemetry the workshop intends to teach, not a defect with one correct repair.

## Late finding — Java HTTP telemetry is hand-rolled and discards the URL

**Substrate: `solutions/reference/java/`, the tree the deployed image is built from, at
`fb74cf2`.** The static half is executed; no Application Insights query was run by this arm.

The two tracks obtain HTTP server spans from different places, and only one of them is a
library.

* **.NET** registers `AddAspNetCoreInstrumentation()`
  (`solutions/reference/dotnet/src/LegoCatalog.App/Program.cs:104`). Its own
  `Middleware/RequestTelemetryMiddleware.cs` creates **no** spans — verified, zero
  `StartActivity`/`ActivityKind` occurrences in 55 lines. So every .NET request span is
  library-generated, carrying the conventional `GET /route` name and `url.*` attributes.
* **Java** has no HTTP instrumentation library in `pom.xml` and no agent: the image's
  entrypoint is `java -jar /app/catalog.jar` with no `-javaagent` and no
  `JAVA_TOOL_OPTIONS` (`Dockerfile:25`). Every Java request span therefore comes from
  `web/RequestTelemetryFilter.java`, which is the sole source.

That filter hardcodes the span name — `tracer.spanBuilder("http.server")`
(`service/CatalogTelemetry.java:73`) — and sets exactly four attributes:
`http.request.method`, `server.address`, `http.route` (when a handler matched), and
`http.response.status_code`. **It never sets any URL attribute**: `url.full`, `url.path`,
and `http.url` do not occur anywhere under `solutions/reference/java/src/main` (verified,
with a positive control confirming the search matched files).

The consequence in Application Insights is that every Java request arrives with
`operation_Name = "http.server"` and an empty `url`, for all routes. Ch4 asks participants
to analyse request telemetry; on the Java track the columns that identify *which* endpoint
was called are empty by construction, so the documented analysis cannot be performed the
documented way.

**The route is not lost, but the recovery path stated in the first version of this entry was
wrong, and the facilitator refuted it by execution.** `http.route` *is* populated on the span
for every request, because `/healthz` and `/readyz` are `@GetMapping` handlers
(`web/HealthController.java:25,30`) and so set Spring's `BEST_MATCHING_PATTERN`. But it does
**not** reach the `requests` table: `customDimensions` is null on all 1 077 Java request
records, so the query published here previously —
`requests | extend route = tostring(customDimensions["http.route"])` — **returns empty**.
The route survives only on the metrics table, via `CatalogTelemetry.recordHttp`, which is not
a table the material tells anyone to query.

**Bearing on the empty dependency table.** Server spans and `db.client` spans are created by
the same `Tracer`, from the same SDK instance, exported through the same pipeline. An export
fault cannot drop one span kind and keep the other. So if server spans are arriving, an
empty dependency table means the two qualifying call sites were never executed — a traffic
gap, not an instrumentation gap. The query above decides it: probe routes only means
absent traffic; `/` or `/figure/{id}` present with no dependencies means a real defect.

## Late finding — four of the five shipped evidence queries filter a resource attribute
## through a span-attribute column, on both tracks

**Substrate: `fb74cf2`/`30c5a05`, `workshop/observability/queries.kql` and both reference
apps. The static half is executed. The Azure-side mapping behaviour is read-not-run and
rests on the facilitator's live measurement, cited below.**

Four of the five queries in `workshop/observability/queries.kql` — `error-rate`, `latency`,
`database-dependency-failures`, `cold-starts` — carry this clause:

```kql
| where tostring(Properties["azure.containerapps.revision.name"]) == "__REVISION_NAME__"
```

`Properties` on `AppRequests` and `AppDependencies` is populated from **span** attributes.
`azure.containerapps.revision.name` is emitted by both applications as a **resource**
attribute, and never as a span attribute:

* Java sets it through `otel.resource.attributes`
  (`config/CatalogResourceIdentity.java:20`, applied at `CatalogApplication.java:33`).
* .NET sets it inside `ConfigureResource(...).AddAttributes(...)`
  (`Program.cs:80`).
* Neither stack ever calls `setAttribute`/`SetTag` with it — verified on both trees with
  positive controls confirming the searches matched.

Azure Monitor promotes a fixed subset of resource attributes to dedicated columns and does
not copy the remainder into `Properties`. The same queries rely on exactly that promotion
elsewhere and get it right — `AppRoleName` for `service.name`, `AppVersion` for
`service.version`. The defect is the one non-standard attribute being expected to survive
by a route the standard ones do not use.

`replica-count` is the only query unaffected: it reads `AzureMetrics` and applies no
`Properties` filter.

Every affected query ends with a guard of the form `| where value > 0` or
`| where totalRequests > 0 and failedRequests > 0`. **The failure mode is therefore an empty
result set, which is indistinguishable from a healthy window in which nothing failed.**

**Corroboration, measured by the facilitator, not by this arm:** `customDimensions` is null
on all 1 077 Java request records; the Ch4 arm separately measured
`azure.containerapps.revision.name` present on `AppMetrics` (5 510 rows) and absent from
`AppRequests`, `AppDependencies` and `AppTraces`. The metrics/traces split is consistent
with resource attributes being carried into `Properties` for metrics but not for traces.

**This is not a Java finding.** Both stacks emit the attribute identically, so the clause
cannot match on either track.

### Correction: the consequence above is superseded on the integration branch

The clause quoted above is complete and verbatim **for this arm's tree and for the frozen
baseline `4bf59f7`**, where it has no second leg. On the delivery branch it does:

```kql
| where tostring(Properties["azure.containerapps.revision.name"]) == "__REVISION_NAME__"
     or AppRoleInstance startswith "__REVISION_NAME__"
```

Occurrences of `AppRoleInstance startswith` — `4bf59f7`: **0**. This arm's HEAD: **0**.
`origin/rewrite-integration`: **4**. The leg was added by `ac78017`, *"F-126: make the frozen
observability queries satisfiable"*. Measured live by the facilitator, the first leg returns
**0** rows and the second returns **1 077**, so on the delivery branch the four queries work
and this arm's stated consequence does not hold there.

**The mechanism is nonetheless unfixed at that tip.** `ac78017` touched five files —
queries, contracts, workbook, tests — and **no application source**. The revision name is
still emitted as a resource attribute only (`CatalogResourceIdentity.java:20` at
`origin/rewrite-integration`) and still never as a span attribute (verified there, exit 1).

So the surviving defect is sharper than a fragility: **the first leg was never alive.** It
is written against an attribute that neither application has ever set on a span, at any
revision inspectable here, so it cannot have contributed a row. The fallback is not
redundancy held in reserve — it is the whole mechanism, and the dead leg is the one that
names the concept. Revision scoping now rests on the ACA replica naming convention
`<revision>-<hash>-<suffix>` rather than on telemetry the application controls.

### Correction: `db.system.name` is not a span attribute on .NET

An earlier version of this entry claimed that `db.system.name` would reach
`AppDependencies.Properties` on both stacks, and that its absence was an empty-table
artefact. **That is true for Java and false for .NET.** On .NET the name is passed to a
metric tag (`CatalogTelemetry.cs:67`, `RecordDatabase`) and a log scope (`:113`,
`LogDatabaseFailure`), and the file contains no `SetTag`/`AddTag` at all — so it never
reaches a span there either. The facilitator's live measurement settles it: 2 157 .NET
dependency rows with populated `customDimensions` and zero carrying `db.system.name`, which
a non-empty table cannot explain away.

The correct generalisation is theirs, not the one first written here: this is **signal-type
mis-routing in the application** — resource attributes, metric tags and log scopes all read
by the queries as span attributes — rather than any per-table platform behaviour. Three
mis-routings, one indistinguishable empty result, and an authoring defect rather than a
platform quirk.
