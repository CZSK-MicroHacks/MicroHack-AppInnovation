# Challenge 1, Path 1C (.NET Copilot modernization) — run feedback

**Run conditions.** macOS arm64 laptop. No Bastion, no Windows desktop, no VS Code, none of
the three pinned extensions. All modernization work was done by the **GitHub Copilot CLI
agent** in a terminal. Azure work targeted the real subscription
`7bc68c68-f434-49ad-ab3e-b883ec39da86` / `rg-user001`; the migration and handoff were driven
on `vm-dotnet-user001` through `az vm run-command invoke`, because they are IMDS-gated and
cannot run anywhere else.

Archive provenance of the source modernized: `4bf59f7ee8dae11259d73ba5a5d7cb0e3355c4af`.
Published modernized commit: `8834e25f86b833d3bb0db33b05ce5a61a763d0f2`.

This is deliberately **not** a step recap. It is weighted toward defects that produce
*wrong but plausible* results — steps where I could have generated convincing evidence that
meant nothing, and shipped it.

---

## The headline question

> Does Path 1C's value survive the loss of the IDE tooling, or was the tooling the whole
> point?

**The value survives almost entirely — and the fact that it does is itself the most
useful finding this run produced.**

Consider what the chapter actually asks Path 1C to hand in. Its path-specific evidence is
`assessment.md`, `modernization-plan.md`, `task-results.json`, `build-test-cve-summary.md`.
All four are prose and hand-authored JSON. **None of them is validated by anything.** There
is no `task-results.schema.json` in `workshop/contracts/`. No downstream step parses the
assessment. Every one of these four artifacts is exactly as forgeable as
`evidence/ide-extensions.txt` — the file I refused to write on the grounds that it was
forgeable.

Meanwhile the chapter's *required* evidence — `azure-target-output.json`,
`migration-report.json`, `acceptance-report.json`, `runtime-test-report.json`,
`telemetry-report.json`, `modernization-contract.json` — is machine-generated, and at least
one piece of it is genuinely unforgeable (see "What is well designed", below). **The
IDE-specific deliverables carry no verification weight at all.** Removing the IDE therefore
removed nothing that was being checked.

So what did produce correctness in this run? Three things:

1. Capturing the baseline by running the real test suite on the **real .NET 8 runtime**,
   rather than taking the one-line shortcut that would have run it on .NET 10.
2. Reading `infra/modules/environment.bicep` to discover the environment-variable contract
   the application must implement — which the instructions never state.
3. **Re-running** the CVE scan after the upgrade instead of trusting the assessment's
   prediction that the upgrade would clear it. It didn't.

None of those three is an IDE feature. Two of them are actively *undermined* by the
material — one by an omission, one by the absence of any instruction to verify.

And the extension's headline capability, automated framework upgrade, is the one task that
went most smoothly by hand: two build errors, both mechanical, both fixed in minutes.

**Conclusion.** The tooling was not the point, but the chapter is written as though it
were. `challenges/ch01/README.md:114-125` spends its instructional budget pinning three
extension versions and instructing the attendee to *halt* if a version differs — while
never once naming an environment variable the application must read in order to function.
The chapter guards the thing that does not matter and leaves the thing that does
undocumented. That inversion is the single most valuable observation from this run.

---

## Defects that produce wrong-but-plausible results

Ranked by how easily an attendee ships them. (Finding U was written last and outranks
finding 1; the numbering below is left as originally recorded.)

### U. Telemetry evidence has no provenance binding, so the entire artifact can be hand-authored

**Severity: highest in the chapter. This one does not merely permit fabrication — it
rewards it.**

Every other fabrication surface in this material is a *shortcut*: the honest path and the
dishonest path both work, and the dishonest one is faster. This one inverts that. The
honest path is hard, undocumented, and unsupported by any tooling; the dishonest path is
straightforward and reliably passes. An attendee who fabricates finishes the chapter. An
attendee who does not, very likely does not finish.

**What the validator demands.** `catalog_acceptance/handoff.py:234-325` requires four
normalized result files whose contents satisfy, in aggregate:

- exact set equality of signal names against `behavior-contract.json` — 1 resource
  signal, 6 trace signals, 5 metric signals, 8 log signals, with no extras and no
  duplicates (`:270`);
- for every signal, an `observedAttributes` array that is a **superset** of that signal's
  frozen attribute list (`:281-286`);
- exact `unit` strings per metric — `s`, `s`, `{record}`, `s`, `s` (`:287-292`);
- at least one `catalog.import.records` measurement carrying
  `catalog.import.outcome == "rejected"` whose value is a **positive, finite, integral**
  number (`:293-309`);
- and a route probe — `http.request.method: GET`, `http.route: /figure/{id}`,
  `http.response.status_code: 200` — present independently in **three** of the four files,
  under a different key in each: `observations` for traces, `measurements` for metrics,
  `observations` again for logs (`:310-325`).

None of that is written down anywhere an attendee reads. It is discoverable only by
reading the validator.

**What the material provides to get there.** The chapter brief says "collect runtime,
acceptance, and telemetry evidence" (`challenges/ch01/README.md:286`). The reference
solution — the fallback for someone already behind — gives it three sentences
(`solutions/ch01-copilot-modernization/dotnet/README.md:493-499`):

> Exercise normal, import, performance, and controlled failure paths. Query Azure Monitor
> and write normalized nonempty results to `evidence/telemetry/*.json`. Build
> `evidence/telemetry-report.json` exactly from
> `workshop/contracts/telemetry-evidence.schema.json`.

No KQL. No worked example of a single row. No description of the normalization. And
**no tool.** `catalog-migrate` exposes `sql export|import`, `postgresql export|import`,
`images copy`, `verify`, and `render-handoff` — there is no `collect-telemetry`, and
nothing anywhere converts a Log Analytics result into the required shape. The attendee is
asked to hand-transcribe roughly 20 normalized signal rows, with exact attribute sets and
units, from queries they must also invent.

**Why fabrication passes.** `telemetry-query-result.schema.json` requires exactly
`schemaVersion`, `queryId`, and `rows` — and sets **`additionalProperties: false`** over
them. It carries **no timestamp, no workspace ID, no Application Insights resource ID, no
operation or correlation ID, and no ingestion metadata.** The `query` field in the report
is validated as `minLength: 10` — any string of eleven characters satisfies it.

**This is a prohibition, not an omission**, and that distinction is the whole finding.
Because `additionalProperties: false` closes the object, an attendee who *wants* to record
which workspace they queried and when **cannot**: the schema rejects the key. The honest
attendee has no escape hatch. It is not merely that the format fails to ask for
provenance; it is that the format forbids supplying it.

So the shape is fully specified and the provenance is impossible to state. Both inputs
needed to synthesize a passing bundle — `telemetry-evidence.example.json` and
`behavior-contract.json` — are **checked into the repository the attendee already has
open**. Producing convincing, complete, entirely fictional telemetry evidence is perhaps
twenty minutes of careful copying, requires no Azure access, and is indistinguishable
from the real thing in the delivered artifact.

**The missing renderer is an inconsistency, not a design stance.** It would be one thing
if this workshop had decided evidence is hand-authored throughout. It did not.
`catalog_acceptance` ships **three dedicated evidence renderers** —
`defender_evidence_cli.py`, `load_evidence_cli.py`, `sre_evidence_cli.py` — and two of
them expose **both** `render_main` and `validate_main`. Challenges 2, 5 and 6 each get a
tool that produces their evidence. Challenge 1's telemetry evidence ships **validation
only**. The authors demonstrably knew renderers were needed and built three; telemetry is
the single evidence domain left hand-authored, and it is also the one with the most
intricate contract.

**Why this compounds with F-74 rather than merely resembling it.** F-74 tells the
attendee, correctly, that four signals cannot appear unless they deliberately break their
own working application. Now published guidance (`docs/TelemetryFaultInjection.md`) makes
that achievable — but it ends at "confirm all eight signal names are present". The
remaining work, turning observations into the normalized bundle, is the larger half and is
still entirely unsupported. An attendee who has just been told that the correct behaviour
of their application is what is blocking them, and who then finds no tooling for the next
step, is being led toward the conclusion that the evidence is a formality to be satisfied
rather than a measurement to be taken.

**Why I can speak to this specifically.** I did the honest version. Reconstructing these
requirements took reading the validator source, the behavior contract, and two JSON
schemas, and produced constraints — the `{record}` unit, the positive-integral rejected
measurement, the `/figure/{id}` probe needed in three files under two different key
names — that I would not have guessed and that no attendee will guess. Every one of them
is trivially satisfiable by typing the value in.

**Recommended fixes, in order of value:**

1. **Ship a `catalog-migrate collect-telemetry` command** that runs the queries, resolves
   the workspace **by name** (see finding on the two-workspace trap), and emits all five
   files. This removes the fabrication incentive and the transcription burden together,
   and is the only fix that addresses the real problem: the honest path currently costs
   more than the dishonest one.
2. **Bind the evidence to its source.** Require `workspaceId`, `capturedAt` per query, and
   a time range in the result schema; have the validator check that `capturedAt` falls
   after the release revision's creation timestamp. This does not make fabrication
   impossible, but it stops being *accidental* and starts requiring deliberate intent —
   which is the correct bar. **Implementation note: this requires relaxing
   `additionalProperties: false` first.** Anyone who adds `capturedAt` without touching
   that keyword will watch the schema reject their honest evidence, which is a
   particularly demoralizing way to discover the constraint.
3. **Publish the four KQL queries**, as `docs/TelemetryFaultInjection.md` §5 already does
   for the union query. Half the difficulty here is that the attendee does not know what
   to ask for.

**Related: an attendee cannot self-check any of this.** Every constraint above surfaces
only as a `ValueError` from `handoff_cli`, at the very end of the chapter, one at a time.
There is no `--dry-run`, no schema-only mode, no way to validate a telemetry bundle before
the handoff gate. The feedback loop is a single boolean arriving after all the work is
done — which is precisely the condition under which people start editing evidence to
satisfy validators rather than re-measuring.

**Update — this was fixed while the run was in progress, and I have read the fix.** A
renderer now exists (`catalog_acceptance.telemetry_evidence_cli`), and
`telemetry-query-result.schema.json` now *requires* `workspaceId`, `capturedAt` and
`queryText` where it previously *forbade* them. I tested the renderer's central claim
rather than taking it on trust: given a capture manifest with fields missing it refuses to
default them and reports every problem at once, which is exactly the property that was
missing. It also supplies `unit` from the contract, so `{record}` is never hand-typed.

**Two things are worth stating precisely, because the fix is better than it looks in one
respect and does not do something people will assume it does.**

*What it genuinely fixed:* the **inversion**. The honest path is now dramatically cheaper —
one capture manifest instead of five hand-authored documents, provenance filled in
automatically, and every unmet requirement reported in a single run instead of one
`ValueError` per iteration. That inversion was the substance of this finding and it is
gone. Sequencing the renderer before tightening the schema was also the right call: adding
three more mandatory hand-typed fields *first* would have made the inversion worse before
it got better.

*What it did not fix, and cannot:* **nothing reads the provenance.** `handoff.py` contains
zero references to `workspaceId` or `capturedAt`. They are required to be present and
unconstrained in value — `minLength: 1` on the workspace, and a `format: date-time`
annotation that most validators do not enforce by default. The gate still cannot
distinguish a measured bundle from an invented one, which was this finding's core claim and
remains exactly as true. Worse in one narrow sense: the fabrication surface shrank from
five files to one, and the renderer now fills in the units and provenance for the
fabricator too. Recording provenance is necessary but not sufficient; something has to
*read* it.

*A cheap way to close it, requiring no Azure call.* The evidence tree already contains the
answer: `evidence/azure-target-output.json` names the real workspace
(`log-mh-user001-dotnet`, line 57 in mine). The gate could cross-check the capture's
`workspaceId` against it, and `capturedAt` against the release deployment timestamp it
already validates elsewhere. That is a purely offline consistency check between two
artifacts the attendee already has, and it would catch a bundle that names the wrong
workspace or claims a capture from before the revision existed. It would not stop a
determined forger — nothing offline will — but it converts provenance from decoration into
something with a failure mode.

### W. The F-89 renderer reports success while writing a document its own gate rejects

**Found by testing the fix, not by reading it.** This is a defect *in* the remedy for
finding U, and it reintroduces the exact failure mode that remedy exists to remove.

**What happens.** `catalog_acceptance.telemetry_evidence_cli` validates neither its input
capture manifest nor its rendered output against any schema. For `traces` and `logs` it
copies `observations` straight through:

```python
if query_id in ("traces", "logs"):
    row["observations"] = list(signal.get("observations", []))
```

Nothing requires that list to be non-empty. The only observation check is
`_check_route_probe`, and it inspects **one** carrier signal per query — `http.server` for
traces, `http.server.request` for logs. Every other signal may carry an empty list.

But `telemetry-query-result.schema.json` requires `observations` with `minItems: 1` for
exactly those two query IDs. So the renderer writes a document that violates the contract
it is rendering to, and reports success:

```
RENDERER_EXIT=0
{ "status": "rendered", "signalCounts": { "resources": 1, "traces": 6, "metrics": 5, "logs": 8 } }
```

while the file it just wrote fails validation:

```
traces: SCHEMA VIOLATION
   path: ['rows', 1, 'observations']
   msg : [] should be non-empty
```

**Where the attendee finds out.** `handoff.py:263-264` validates every telemetry query
result against that schema. So the failure surfaces at the handoff gate, at the end of the
chapter, as a single `jsonschema.ValidationError` — which is, verbatim, the feedback loop
the renderer's own docstring says it was built to eliminate:

> *It reports every problem at once. The handoff gate raises one `ValueError` at the end
> of the chapter. Iterating against that is what pushes people toward editing evidence
> instead of re-measuring.*

The renderer had every piece of information needed to report this up front and did not.

**How I established it.** I built a synthetic capture manifest satisfying every check the
renderer performs, set `db.client`'s `observations` to `[]`, rendered, then validated the
output with `Draft202012Validator` plus `FormatChecker` — the same configuration
`handoff.py:140` uses. The renderer exited `0`; `traces.json` failed. I did **not** run the
full handoff gate end to end, because that needs a complete evidence tree; the claim is
that the emitted document violates the schema the gate validates against, proven with the
gate's own validator, and that is what I assert. The synthetic manifest was clearly marked
`SYNTHETIC-NOT-EVIDENCE`, kept outside the repository, and deleted.

**Why it happened, and it is the same cause as finding U.** The three sibling renderers —
`defender_evidence.py`, `load_evidence.py`, `sre_evidence.py` — all import `jsonschema` and
validate against checked-in schemas. `telemetry_evidence.py` imports no schema machinery at
all; its only `schema` references are the literal `"schemaVersion": "1.0.0"` strings it
writes into output. The new renderer ships **fifteen** tests and not one validates rendered
output against `telemetry-query-result.schema.json`. The contract that was fabricable
because nobody tested it now has a producer that is unchecked against it for the same
reason.

**The input side has the same gap, one level down.** Challenges 5 and 6 each ship
`*-evidence-capture.schema.json` *and* `*-evidence-capture.example.json`. Telemetry ships
**neither**. The capture manifest's shape is enforced only by ad-hoc
`if not capture.get(field)` checks, and is documented nowhere — so the attendee must
reverse-engineer it from `telemetry_evidence.py`. That is the same reverse-engineering
burden finding U was about, moved from the output format to the input format.

**Two smaller things found in the same session, both real:**

1. **An out-of-repository `--output` crashes with a raw traceback**, not a handled error:
   `ValueError: '/tmp/.../resources.json' is not in the subpath of '<root>'` from
   `relative_to` at `telemetry_evidence.py:224`. The CLI documents the flag as
   "repository-relative", so this is user error — but it should be a message, not a stack
   trace.
2. **`--repository-root` is `resolve()`d while `--output` is not**, so any path crossing a
   symlink fails the same way. On macOS `/tmp` is a symlink to `/private/tmp`, so this
   fires on the most obvious scratch directory on the platform.

**The fix is small and the pattern already exists in the tree.** Validate each rendered
document against `telemetry-query-result.schema.json` before writing, fold any violations
into `problems`, and let the existing accumulate-and-report-everything path carry them.
Then add a capture schema and example to match the other three renderers. Both are what
`defender_evidence.py` already does.



**Severity: highest. This is the defect most likely to be shipped undetected.**

`infra/modules/environment.bicep:499-588` is the *only* definition of the variables the
container receives: `CATALOG_DATABASE_AUTHENTICATION`, `CATALOG_IMAGE_PROVIDER`,
`CATALOG_BLOB_SERVICE_ENDPOINT`, `CATALOG_BLOB_CONTAINER`, `AZURE_CLIENT_ID`,
`CATALOG_SEED_PATH`, `CATALOG_STARTUP_IMPORT_ENABLED`, `OTEL_SERVICE_VERSION`,
`CONTAINER_APP_REVISION`, `DEPLOYMENT_ENVIRONMENT`, `APPLICATIONINSIGHTS_CONNECTION_STRING`.

Neither `challenges/ch01/README.md`, nor the path guide, nor
`solutions/ch01-copilot-modernization/dotnet/README.md` names a single one. The runbook says
only that the image "takes database, Blob, and telemetry configuration from the
environment."

**Why this is the worst kind of defect.** An attendee modernizing by hand will invent
plausible names — `ConnectionStrings__Catalog`, `AZURE_STORAGE_ACCOUNT`,
`ApplicationInsights__ConnectionString`. The result:

- the build is clean;
- all 42 tests pass, because no test constructs `CatalogRuntimeOptions` from environment;
- the Bicep deployment **succeeds**, because the template sets its variables regardless of
  whether anything reads them;
- the application starts and reports healthy;
- managed identity and Blob Storage are silently inert.

Nothing anywhere says no. I hit this personally: my first attempt at the managed-identity
task **inferred** the auth mode from the database hostname suffix and used
`SqlAuthenticationMethod.ActiveDirectoryDefault`. That is a defensible, professional-looking
implementation. It matches no contract. I caught it only because I went and read the Bicep,
which nothing instructed me to do.

**Recommendation.** Publish the contract as a table in the challenge README, or better, as
a `workshop/contracts/application-environment.json` that a test asserts against.

### 2. The .NET 10 upgrade does not clear the CVE, and hiding it is the same size as fixing it

`evidence/assessment.md` predicted GHSA-2m69-gcr7-jv3q would clear when EF Core moved to 10.
**It did not.** EF Core 10.0.1 resolves `SQLitePCLRaw.lib.e_sqlite3` **2.1.11**, still
vulnerable. (I left the wrong prediction visible in the assessment with a correction
appended, rather than editing it away.)

The compounding problem: **NuGet audit is on by default from .NET 10.** An advisory that the
.NET 8 build never mentioned becomes a hard `NU1903` build failure at the exact moment the
attendee changes the target framework. The build is red, they are mid-task, and two
one-line fixes are available:

```xml
<PackageReference Include="SQLitePCLRaw.lib.e_sqlite3" Version="2.1.13" />   <!-- fixes -->
<NoWarn>$(NoWarn);NU1903</NoWarn>                                            <!-- hides -->
```

The second is faster, turns the build green, and **permanently disables a security gate for
the life of the repository**. In a diff the two are visually comparable, and both are
followed by 42/42 passing tests and a successful deployment.

The material's own success criteria ("dependency/CVE result" in the summary) are satisfied
identically by both. Nothing catches the suppression.

### 3. The baseline can be manufactured with one environment variable

`dotnet test` fails on a machine that has the .NET 10 runtime but not ASP.NET Core 8. The
obvious fix, and the one most people will reach for, is `DOTNET_ROLL_FORWARD=Major`. It
produces a green 42/42 baseline immediately.

It also runs the *pre-upgrade* suite **on the .NET 10 runtime**. The "before" and "after"
runs then share a runtime, and the comparison between them measures nothing. The resulting
`evidence/dotnet-baseline-net8.trx` is byte-plausible: same 42 tests, same names, same
green, correct filename.

I rejected the shortcut and installed SDK 8.0.424 privately to `~/.dotnet-workshop`
instead. Nothing in the material would have stopped me doing otherwise, and nothing
downstream inspects which runtime produced the baseline TRX.

### 4. `evidence/ide-extensions.txt` cannot fail — and the runbook pressures you into forging it

The three pinned versions are published in `workshop/toolchain.lock.json`.
`workshop/contracts/challenge-paths.json` lists `ide-extensions.txt` in **neither**
`requiredEvidence` nor `pathEvidence`. A perfect-looking inventory is a two-minute
transcription by someone who has never opened an IDE, and nothing downstream will ever
contradict it.

I declined to write it. **That decision breaks the runbook.**
`solutions/ch01-copilot-modernization/dotnet/README.md:162-164` includes
`evidence\ide-extensions.txt` in its `git add`, so the documented commit step fails with
`pathspec did not match any files` for anyone who does not create the file.

This is worse than an unvalidated artifact. The material *actively pressures* the attendee
to produce it, and the cheapest way past the error message is to type one out. An evidence
artifact that cannot fail is not evidence; an evidence artifact that cannot fail and whose
absence breaks your build is a trap.

### 5. Container base tags have drifted off the locked digests

`workshop/toolchain.lock.json` pins:

| Image | Locked digest | Tag resolves today to |
| --- | --- | --- |
| `sdk:10.0.400-azurelinux3.0-amd64` | `sha256:679e7b7e…` | `sha256:7a440c18…` |
| `aspnet:10.0.11-azurelinux3.0-amd64` | `sha256:d21a49ce…` | `sha256:33a753f8…` |

**Both locked digests still resolve (HTTP 200)**, so digest-pinning remains correct. But a
tag-only `FROM` now builds successfully on a base that is *not* the pinned one, with no
signal. `toolchain.lock.json:346` requires verifying the lock digest "before every installer
or archive executes" — and **no step in the .NET runbook performs that check for container
bases**. `dotnet/Dockerfile` in this delivery pins by digest.

### 6. The image traversal control is invisible to the test suite

`ImageSecurityTests` exercises `LocalImageStore.IsCanonicalImageKey` only as a **static**
method, never through the `IImageStore` seam. The blob task replaces the store entirely.

A `AzureBlobImageStore` that omitted the canonical-key check would leave **all six security
tests green**. The suite cannot detect its own most important regression. I re-applied the
check explicitly and said so in the commit message, but the control now rests on code review
alone.

### 7. Telemetry has no failing signal

No test asserts that any exporter is registered. The application is entirely healthy with
telemetry disabled. The specific trap here: `Program.cs` already had a `hasOtlpExporter`
gate, and folding the Azure Monitor exporter into it is the natural-looking edit — but the
deployment sets `APPLICATIONINSIGHTS_CONNECTION_STRING` and **no** OTLP endpoint, so the
shared gate would leave Azure Monitor permanently unconfigured while everything looked
correct. I gated it independently.

### 8. The checked-in `infra/parameters/*.bicepparam` are a trap without `C:\protected\`

They carry `sourceCommit = '0'×40`, `imageDigest = 'sha256:' + '0'×64`, and
`performanceApiKey = 'SANITIZED-SECURE-VALUE-REPLACE-FOR-WHAT-IF'`. `infra/README.md:77-80`
says they are compile-only — but neither the challenge README nor the .NET runbook repeats
that, and both assume `C:\protected\` exists. `'0'×40` satisfies the template's format
assert. The exact documented failure mode ("a placeholder that satisfied the format assert
would silently deploy the wrong source", runbook:349-352) is **checked into the repository
as a working file**.

### 9. `sourceCommit` is asserted for shape, never for existence

`infra/main.bicep:104` asserts only that `sourceCommit` is 40 lowercase hex characters. A
wrong-but-well-formed SHA therefore deploys successfully, tags the image, writes a
schema-valid handoff — and fails a chapter later in Challenge 3, which checks out that SHA
and builds `dotnet/Dockerfile` from it, with no diagnostic pointing back to Challenge 1.

**Note on a related near-miss.** The facilitator channel relayed an instruction to record
`sourceCommit` as the archive provenance `4bf59f7…` rather than the pushed modernized
commit. That is precisely the wrong-but-plausible failure above, and it would have deployed
cleanly. `challenges/ch01/README.md:195-197` in fact says the two "are never
interchangeable", which is how it was caught. The guidance was retracted. Worth recording
because the defect class this workshop teaches was reproduced *by the workshop's own
support channel*, live — which is strong evidence that the two-fields-one-shape design is
genuinely confusing rather than merely under-documented.

**Recommendation.** One line — reject a `sourceCommit` equal to the archive provenance —
converts a silent Challenge-3 failure into an immediate one.

### 10. Nothing verifies you started from the right source

This run began against commit `93887ab`, an old ancestor, because the worktree was created
from `main`. The `challenges/ch01/README.md` at that commit is a complete, well-formed brief
with Goal / Actions / Success Criteria. **Nothing in it says it is stale.** I read it and
built an entirely wrong model of the chapter. It was caught only by an out-of-band
correction; unattended, it would have run for hours and produced coherent, worthless output.

There is no preflight source-provenance check anywhere in the material. Given that two other
defects in this list concern commit provenance being recorded wrongly, a check the attendee
runs *before starting* is a conspicuous gap.

### 11. The telemetry bundle has no internal consistency binding, so it can attest to a revision that never emitted the signals

F-89 established that the telemetry bundle has no binding to the *world* — nothing checks
that the recorded workspace is your workspace. There is a second, sharper gap: **nothing
binds the parts of the bundle to each other.**

`resources.json` names exactly one revision in `azure.containerapps.revision.name`. The
trace, metric and log results carry no revision at all. `handoff.py:234-325` validates
signal-name set equality, `recordCount >= 1` and the required attribute set — and never
compares the revision named in `resources.json` against the origin of any signal, because
the signals do not record one. **A bundle whose resource attributes name the release
revision and whose signals were emitted by a different revision entirely is
indistinguishable from a correct one.**

This is not hypothetical on this deployment. Measured, offline:

| Log signal | Revision that emitted it | Window |
| --- | --- | --- |
| `http.server.request`, `catalog.import.completed`, `catalog.import.failed`, `catalog.performance.completed`, `exception` | `--release-47acf263d332` | 20:55 → 22:53 |
| `catalog.database.failed` (7) | `--0000001` | 19:59 → 20:46 |
| `catalog.query.failed` (4) | `--0000001` | 20:46 |
| `catalog.performance.failed` (2) | `--0000001` | 20:29 |

The fault injection ran against `--0000001` and stopped at **20:46**. The release revision
began serving at **20:55** — nine minutes later. Three of the eight required log signals
have therefore *never* been emitted by the revision under test.

The tempting move is obvious and would work: query without a revision filter, get all eight
signals, pair them with release resource attributes, pass the gate. The result is a document
asserting the release revision emits telemetry it demonstrably does not. **I have not built
that bundle.** The claim here rests on the schema and on `handoff.py` containing no revision
comparison, which is checkable without running anything.

The honest alternative costs a re-run of fault injection under the release revision, which
needs the run-command channel — unavailable for the whole window (see the F-90 section). So
the practical position an attendee lands in is: *the correct capture is blocked, and the
incorrect one is one omitted `where` clause away and passes.*

**Recommendation.** Have the renderer stamp the revision it observed on every query result
and have `handoff.py` reject a bundle whose signals disagree with `resources.json`. This
needs no new measurement from the attendee — the revision is already present in
`AppRoleInstance` on every row.

### 12. Three concurrent revisions emit resource attributes, and the naive query picks the wrong one

The six required resource attributes exist on exactly one record type — the synthetic
`AppMetrics` row named `_APPRESOURCEPREVIEW_`. The obvious query is
`... | where Name == '_APPRESOURCEPREVIEW_' | take 1`.

Over the last two hours that returns one of **three** answers:

| Revision | resource-attribute records | user traffic |
| --- | --- | --- |
| `ca-mh-user001-dotnet--0000001` | **1400** | none — placeholder revision |
| `ca-mh-user001-dotnet--release-47acf263d332` | 1378 | all of it |
| `ca-mh-user001-dotnet--fixup1-47acf263d332` | 1342 | none |

Container Apps health-probes every *provisioned* revision, not just the active one, so
inactive revisions keep emitting resource attributes indefinitely. The revision with the
**plurality** is `--0000001`, which serves nothing. An attendee who deployed baseline then
release — exactly what the runbook instructs — has a roughly one-in-three chance of
recording the right revision, and the single most likely answer is wrong.

Nothing signals this. All six attributes are present, correctly formatted, and real.

**This is the third instance of one shape in this chapter.** In each case a multi-valued
result is consumed as if it were single-valued, and the wrong element is plausible:

1. `az monitor log-analytics workspace list ... [0]` returns the **Java** arm's workspace.
2. `az containerapp revision list` without `--all` omits inactive revisions, so the
   baseline revision looks deleted and the rollback evidence looks impossible.
3. `_APPRESOURCEPREVIEW_ | take 1` returns whichever revision the shard yields.

**Recommendation.** Treat this as one defect with three sites rather than three defects.
Every query in the material that indexes into a list should either filter to a value the
attendee supplies or assert the result count is 1 and fail otherwise.

### 13. The telemetry signal names in the contract do not exist in the telemetry store

`behavior-contract.json` freezes 25 signal names. Six are trace names, five metric names,
eight log names, six resource attributes. The natural reading — and the one the material
never corrects — is that these are values you can search for.

For the metrics that is true: all five appear verbatim in `AppMetrics.Name`. For the other
twenty it is false or partly false. Measured, offline, against the live workspace:

**`db.client` and `http.server` appear nowhere as literal strings.**
`AppDependencies | where Name in ('db.client','http.server')` returns **count 0**. Their
identity is table membership plus a type discriminator, not a name:

| Trace signal | Where it actually lives |
| --- | --- |
| `http.server` | `AppRequests` — every row, no name match |
| `db.client` | `AppDependencies` where `DependencyType == 'SQL'` |
| `catalog.query` / `catalog.performance` / `catalog.import` | `AppDependencies`, `DependencyType == 'InProc'`, exact `Name` |
| `exception` | `AppExceptions` |

The eight log signals are worse, because they need **four different extraction rules**, and
the split does not follow the signal name:

| Signal | Table | Column | Form |
| --- | --- | --- | --- |
| `http.server.request` | `AppTraces` | `Message` | exact |
| `catalog.import.completed`, `catalog.performance.completed` | `AppTraces` | `Message` | **interpolated** — `catalog.import.completed inserted=0 skipped=1` |
| `catalog.database.failed`, `exception` | `AppExceptions` | `Properties['OriginalFormat']` | exact |
| `catalog.import.failed`, `catalog.query.failed`, `catalog.performance.failed` | `AppExceptions` | `Properties['OriginalFormat']` | **raw template** — `catalog.import.failed rejected={Rejected}` |

The signal name is the message-template *prefix* of the `logger.LogX(...)` call, not an
`EventId` or `EventName`. And the same logging call is stored two different ways depending
on which table it lands in: `AppTraces` keeps the interpolated string, `AppExceptions` keeps
the uninterpolated template. So `Message == "catalog.import.completed"` returns **zero
rows** — you must use `has` or `startswith`, and for the exception-backed signals you must
look in a different column of a different table.

**Why this is wrong-but-plausible rather than merely hard.** Every one of these queries
returns zero rows rather than an error. An attendee who writes the obvious query for
`db.client` gets an empty result and the entirely reasonable conclusion that *the
application is not emitting the signal* — and goes off to instrument code that is already
correct. That is the same false-negative shape as the internal-URL `curl` timeout, and it
costs more, because the "fix" is a code change to a working application.

This is, I think, the concrete reason F-74 was hard to verify: the gap is not that
telemetry is missing, it is that the contract and the store speak different vocabularies
and nothing translates between them.

**Recommendation.** Ship the mapping table above alongside `behavior-contract.json`. It is
twenty rows and it converts the hardest part of the chapter into a lookup. The renderer
landed in `ce491f7` is the right place for it — a `--discover` mode that emits the capture
manifest from the workspace would remove the whole problem, and the queries are already
written here.

### 14. The provenance cross-check silently disables itself, so a skipped check is indistinguishable from a passing one

`46f2a1f` implements the offline workspace cross-check I proposed: the capture's
`workspaceId` is compared against `logAnalyticsWorkspaceResourceId` in
`azure-target-output.json`. The comparison itself is correct and the failure message is
good. **The problem is how it decides whether to run.**

`telemetry_evidence.py:211-220` locates the sibling artifact as
`output_path.parent / "azure-target-output.json"` and returns silently on three separate
conditions: the file is absent, it fails to parse, or the field is missing or not a string.
None of the three produces any output. **A skipped provenance check and a passing
provenance check look exactly the same** — `"status": "rendered"`, exit 0.

Measured, same renderer and same capture, twice:

| `--output` | sibling artifact present | result |
| --- | --- | --- |
| `./_f91out` | no | **exit 0, `"status": "rendered"`** |
| `./_f91out` | yes (copied to repo root) | **exit 1**, workspace mismatch reported |

The capture in both runs was `telemetry-evidence-capture.example.json` unmodified, whose
`workspaceId` names workspace `w` — against a deployment whose real workspace is
`log-mh-user001-dotnet`. The first run rendered a complete, green bundle carrying a
placeholder workspace ID from a contract example file.

There is a second, smaller inconsistency that makes it harder to notice: the code resolves
the sibling relative to `--output`, but the failure message hardcodes
`"from evidence/azure-target-output.json"`. Whenever `--output` is not inside `evidence/`,
the message names a path the check did not read.

**Why this matters more than its size suggests.** The documented invocation puts `--output`
in `evidence/`, so the check does fire on the happy path, and I want to be clear that the
fix works as intended when used as documented. But iterating on a capture — rendering to a
scratch path to inspect the output before committing it — is the natural thing to do, and
it silently turns the check off. The attendee sees `"rendered"` and reasonably concludes
provenance was verified.

This is the F-89 shape one level further in. F-89 was *provenance that nothing reads*. The
fix made something read it. The residue is *a reader that can decline to read without
saying so* — and the whole argument for the cross-check was that it "gives provenance a
failure mode instead of leaving it decorative". A check that no-ops silently is decorative
again, just harder to see.

**Recommendation.** One line. When the sibling artifact is absent or unusable, either
append a problem, or emit `"provenanceCheck": "skipped"` alongside `"status"` in the
rendered report so the difference is visible in the artifact itself. The second is
probably better: rendering to a scratch path is legitimate, and the attendee should be
able to tell which of the two things happened.

---

### Finding 15 — the VM's only version signal is confidently wrong in both directions

**Where.** `C:\MicroHack\source` on `vm-dotnet-user001`, and any attendee instruction of
the form "check the VM is on the right commit".

**What happens.** `C:\MicroHack\source` looks exactly like a git clone. `git log` works,
`git status` works, `git rev-parse HEAD` returns a real SHA. It is not a clone: it is an
archive extraction with a single synthetic commit, `4da1797 "Workshop baseline 4bf59f7…"`,
and thereafter files are updated **by copy**. HEAD never moves. On my run it sat at that
one commit with 32 modified files.

The consequence is that every git-based version question answers wrongly:

```
git merge-base --is-ancestor 53e3706 HEAD  -> False
git merge-base --is-ancestor 46f2a1f HEAD  -> False
git merge-base --is-ancestor e78bd49 HEAD  -> False
```

All three of those commits' content **was** present in the working tree. There is no shared
history, so `--is-ancestor` cannot be anything but `False`, for a current tree and a stale
one alike.

**Why this is the wrong-but-plausible class and not the loud class.** I hit this while
verifying my own acceptance run. The answer I got was a clean, unambiguous `False` from a
tool nobody distrusts, and my first interpretation was the natural one: *the VM is stale,
the 22/22 I just collected was produced by old code, throw it away.* That would have
discarded a valid result. Flip the situation — an attendee whose VM genuinely is stale
runs the same check after a copy that did not happen, and gets `False` too, which they may
equally well read as "the check is just broken here, ignore it". The signal is not missing.
It is **present, confident, and uncorrelated with the truth**, which is worse, because a
missing signal makes you go and look.

**What I used instead.** Content, not metadata:

```powershell
Get-FileHash -Algorithm SHA256 C:\MicroHack\source\tests\acceptance\catalog_acceptance\runner.py
```

`B6F93F1F…`, byte-identical to the same file in my merged tree, and the F-81 marker string
`body_is_unstable` present in it. That settles the question the git command could not.

**The generalisation, which is the part worth keeping.** *Prefer content to metadata when
the metadata is not maintained by the thing it describes.* This is the third time the same
idea has come up in this chapter — `.source-commit` (a file describing a tree, written by
neither), the run-command provenance work, and now this. In all three, a metadata field
sits next to the artifact and is trusted because it is *adjacent*, not because anything
keeps it true.

**Recommendation.** Either make `C:\MicroHack\source` a real clone and `git pull` it, or —
cheaper and honest — put a `.git`-free marker in it (`REVISION.txt` written by the same
copy step that updates the files) and tell the attendee to hash-compare specific files.
Do not leave a working `git` in a directory whose history is fiction.

---

### Finding 16 — the docs linter fails the build on the attendee's own deliverable, for a convention it never taught

**Where.** `tests/docs/` — the markdown lint suite — versus `challenges/ch01/README.md`,
which asks the attendee to write up their run.

**What happens.** I ran the full suite at merged HEAD and got three failures. One of them
was the docs linter rejecting **my feedback file** — the deliverable the chapter asks for —
because it contained the string `<vm-mi-principal-id>` inside a command example. The rule
wants attendee-supplied placeholders to be prefixed `your-`; `<your-vm-mi-principal-id>`
passes, `<vm-mi-principal-id>` does not.

That convention is not documented anywhere the attendee reads. It is not in
`challenges/ch01/README.md`, not in the runbook, not in `CONTRIBUTING`. I only learned it
by reading the test.

**Why it matters more than it looks.** The failure is not attributed. The suite reports a
docs-lint failure with a count, and the attendee — who has just spent an afternoon
modernizing an application — reasonably concludes their *code* change broke something. The
fix is in a file they authored freehand, five minutes ago, in prose. I diagnosed this in
about two minutes because I had just written the line. Someone who wrote it an hour earlier
will not.

Note the shape: this is the workshop's quality gate firing on the workshop's own
instruction to write prose. Two correct behaviours, no shared contract between them.

**Recommendation.** Either exclude attendee-authored deliverables from the docs lint by
path, or state the placeholder convention in the same paragraph that asks for the write-up.
The second is better — the convention is a good one, it just needs to be reachable from
where the work is done.

*(The other two failures at merged HEAD were mine and correct: my Track A modernization
trips two guards that pin the frozen legacy baseline. Those are the guards working.)*

---

### Finding 17 — the fault-injection procedure omits the two things you cannot guess

**Where.** `docs/TelemetryFaultInjection.md`, §1 and §2. This is my own procedure, lifted
into the material, so this finding is partly against myself.

**Two gaps, and they cost differently.**

**§1 supplies no command.** It says to drive an import that fails validation. It does not
say the endpoint is `POST /import`, that the body is `multipart/form-data`, or that the
field name is `catalogFile`. Every one of those is discoverable from the source in a couple
of minutes; the section reads as if it had been written by someone with the controller open
in another window. Cost: minutes, and it fails loudly (400 with a clear message) while you
work it out.

**§2 names a header without naming it.** It says the perf endpoint "needs its API key
header". The header is `x-api-key`. I guessed `X-Perftest-Key` — a reasonable guess, since
the *key* is called `performanceApiKey` and the endpoint is `/perftest/catalog` — and lost
a full injection pass to it.

**This one is in the wrong-but-plausible class and the first is not.** A wrong header
returns **401**. The script keeps going, the run completes, no error is raised anywhere, and
`PERFDONE` is written. Then the union query shows `catalog.performance.failed` still
missing, and the natural next move is to conclude *the application does not emit that
signal* and go looking in application code for a bug that is not there. The remedy the
attendee is being steered toward is **modifying a correct application**. That is strictly
worse than the `curl` timeout case elsewhere in this material, where the failure at least
points outward.

The confirmation, from the corrected pass: with `x-api-key` set, the same requests return
**503** under the injected fault and **200** after restore. 401 → 503 is the whole
difference between a pass that generates the signal and one that silently does not.

**Recommendation.** Name the header. One word — `x-api-key` — in §2, and the literal
`curl`/`Invoke-WebRequest` line in §1. If a section's failure mode is a 401 that looks like
a successful run, it does not get to leave its parameters implicit.

---

### Finding 18 — `python -m catalog_migrate.cli` exits 0, prints nothing, and does nothing

**This is the worst defect I found in the entire chapter.** It is a silent success.

**Reproduction, no Azure required, from `tests/acceptance/`:**

```
$ uv run python -m catalog_migrate.cli render-handoff
<frozen runpy>:128: RuntimeWarning: 'catalog_migrate.cli' found in sys.modules ...
$ echo $?
0
```

That invocation is missing **nine required arguments**. It exits **0**. It writes no file,
prints no JSON, raises nothing.

Compare the correct form:

```
$ uv run python -m catalog_migrate render-handoff
{"command": null, "error": {"code": "invalid-input", "message": "argument error: the
following arguments are required: --target-output, --migration-report, ..."},
"exitCode": 2, "schemaVersion": "1.0.0", "status": "failed"}
```

**Cause.** `catalog_migrate/cli.py` has no `if __name__ == "__main__":` block.
`catalog_migrate/__init__.py` does `from catalog_migrate.cli import main`, so `-m
catalog_migrate.cli` imports the package (which imports `cli`), then re-executes `cli.py`
as `__main__` — defining functions and falling off the end. `catalog_migrate/__main__.py`
exists and is correct, so `-m catalog_migrate` works, as does the `catalog-migrate` console
script.

**Why the wrong form is the natural one.** Every other CLI in this repository is invoked as
`python -m <package>.<module>`:

```
python -m catalog_acceptance.handoff_cli ...
python -m catalog_acceptance.telemetry_evidence_cli ...
```

Both of those modules **do** carry `__main__` guards (`handoff_cli.py:40`,
`telemetry_evidence_cli.py:79`). So the attendee learns `package.module` from the two CLIs
they use most, applies it to the third, and gets silence. The one module in the trio that
needs the guard is the one that does not have it.

**Why it is the wrong-but-plausible class at its purest.** Exit code 0. No stderr except a
`RuntimeWarning` that reads like Python noise. In a script — `set -e`, a CI step, a
scheduled task, a `&&` chain — this is indistinguishable from success. It *is* success, as
far as anything downstream can tell. I lost two full remote round-trips to it, and I only
caught it because I checked `Test-Path` on the output file rather than trusting the exit
code. An attendee who trusts the exit code proceeds to the next step believing the handoff
contract exists.

Worse: this is the **last** command in the chapter. Its output, `modernization-contract.json`,
is what Challenges 2–6 consume. A silent no-op here produces a green Challenge 1 and a
Challenge 2 that fails on a missing file, one step removed from its cause.

**Recommendation.** Add `if __name__ == "__main__": raise SystemExit(main())` to
`catalog_migrate/cli.py`. Three lines. There is no argument for leaving a module importable
as `__main__` that does nothing when it is. If the intent is that `-m catalog_migrate.cli`
be unsupported, make it *fail*, not succeed.

---

### Finding 19 — every IMDS-gated command fails when run through the documented remote-execution route

**Where.** `validate_migration_topology` (`catalog_migrate/azure.py`) versus
`az vm run-command invoke`, which is the only way to reach the VM in this delivery.

**What happens.** Run `catalog-migrate render-handoff` *inside* a `run-command` script and
it returns:

```
{"command": "render-handoff", "error": {"code": "precondition-failed",
 "message": "Azure resource is not provisioned: /subscriptions/.../virtualMachines/
 vm-dotnet-user001 (provisioningState=Updating)"}, "exitCode": 3, ...}
```

The VM is `Updating` **because the run-command that is executing this very script is what
puts it there.** The extension's execution is a VM-level operation; for its whole duration
the VM's `provisioningState` is `Updating`. So a topology check that requires `Succeeded`
can never pass from inside the thing that makes it fail. The command is unable to run
itself.

**Why this is wrong-but-plausible rather than merely broken.** The error names the VM and a
provisioning state. Everything about it says *your infrastructure is in a bad state, wait
or fix it*. It says nothing about how the command was invoked. Combined with F-90 — where
an orphaned run-command genuinely does wedge the VM in `Updating` for an hour — the
attendee has every reason to read this as the wedge recurring, and to sit and wait for a
condition that will never clear, because it is caused by their own act of looking.

I had already seen the real F-90 wedge earlier in this run. When this error appeared I read
it as the wedge returning. It is not. It is self-inflicted and instantaneous.

**The workaround, which is also the fix.** Do not run IMDS-gated commands *in* the
run-command channel. Detach them:

```powershell
schtasks /Create /TN MHJob /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\...\job.ps1" `
         /SC ONCE /ST 23:59 /RU SYSTEM /RL HIGHEST /F
schtasks /Run /TN MHJob
```

`run-command` returns in seconds, the VM goes back to `Succeeded`, and the detached task
then sees a provisioned host. My job sleeps 90 s first so the registering run-command has
certainly finished. This is the same pattern that lets the migration and acceptance steps
work, and the reason those steps succeeded earlier while this one did not is simply that I
had already been detaching them.

**Recommendation.** Two things, and the first matters more. **Name the invocation in the
error**: if `validate_migration_topology` sees `provisioningState=Updating` on *its own
host*, it should say so — "this host is itself mid-operation; if you are running inside `az
vm run-command`, detach the command". The gate has the information; it just does not use
it. Second, document the scheduled-task pattern in the runbook as *the* way to drive
`catalog-migrate` remotely, rather than leaving `az vm run-command invoke ...` as the
worked example, since that example cannot work for five of the tool's commands.

---

## Defects that block the .NET stack outright

Both were hit on the first real bootstrap deployment. Both fail loudly, which makes them
less dangerous than the section above — but the first means **Challenge 1 cannot be
completed on the .NET stack with the template as shipped**.

### A. `privatelink..database.windows.net` — the SQL private DNS zone name is malformed

`infra/modules/environment.bicep:179` built the zone name as:

```bicep
name: 'privatelink.${environment().suffixes.sqlServerHostname}'
```

`environment().suffixes.sqlServerHostname` already carries a **leading dot** —
`.database.windows.net`. The result is `privatelink..database.windows.net`, and Azure
rejects it:

```
BadRequest: The domain name 'privatelink..database.windows.net' is invalid.
```

The neighbouring storage zone at line 149 is correct, because
`environment().suffixes.storage` returns `core.windows.net` with **no** leading dot. The two
suffixes do not behave alike, and the template assumes they do.

**Why this survived review: the zone is declared `if (!isJava)`.** It exists only for the
`dotnet-sqlserver` stack. The Java/PostgreSQL path never evaluates it, so a Java track can
deploy this template end to end and report success while the .NET path is unshippable. A
green Java run is not evidence for the .NET run, and in this delivery it actively masked
the defect.

Fixed here as `'privatelink${environment().suffixes.sqlServerHostname}'`.

### B. Private DNS vnet link names collide between the two stacks

`storage-vnet` (line 155) and `sql-vnet` (line 185) were fixed string literals. The blob
zone name is also a fixed string, so **both stacks deployed into one resource group share
the same zone** — and the workshop deliberately places both legacy VMs, and therefore both
stacks, in the same `rg-user001`. The second stack to deploy fails:

```
BadRequest: Virtual network associated with the link cannot be changed.
```

Confirmed by inspection rather than inferred — the zone already carried the Java track's
link:

| Link | Virtual network |
| --- | --- |
| `migration-source-pkjpzftb` | `vnet-user001` |
| `storage-vnet` | `vnet-mh-user001-java` |

Note the first name. **The template already uniquifies the migration link on the very same
zone** (`migrationDnsLinkName`, line 63) for exactly this reason. The pattern was understood
and applied inconsistently one resource later. Fixed here by deriving a matching suffix from
the stack's own virtual network name.

---

### C. The same suffix bug also corrupts `CATALOG_DATABASE_HOST` — and this one does not fail

Defect A and this one are the *same typo* in two places, and they are worth separating because
they behave completely differently. `infra/modules/sql.bicep:84` built the server hostname the
same way:

```bicep
output serverHost string = '${server.name}.${environment().suffixes.sqlServerHostname}'
```

That output is consumed at `environment.bicep:498`, where it becomes both
`targetOutput.database.server` and the `CATALOG_DATABASE_HOST` environment variable injected
into the container app. My first bootstrap deployment **succeeded**, and emitted:

```
sql-mh-user001-dotnet-kurep3z6..database.windows.net
```

against a real server whose `fullyQualifiedDomainName` is
`sql-mh-user001-dotnet-kurep3z6.database.windows.net`. The doubled dot is not merely a wrong
name — it is not a legal name:

```
$ nslookup sql-mh-user001-dotnet-kurep3z6..database.windows.net
nslookup: '...' is not a legal name (empty label)
```

This is the most dangerous single defect I found, because of what it does *not* do:

- the deployment reports `Succeeded`;
- `evidence/azure-target-output.json` is written and is schema-valid;
- every gate in the runbook's step 5 (`deploymentStage`, `stack`, `images.provider`,
  `sourceCommit`) passes on it;
- the migration would then be pointed at a `database.resourceId` that is correct, so the
  cutover itself succeeds;
- the failure surfaces only when the container app starts and cannot resolve its database —
  in a different challenge, with a DNS error that points nowhere near a Bicep output.

An attendee would reasonably conclude their *application* code is wrong. The fix is to use the
value Azure already publishes, `server.properties.fullyQualifiedDomainName`.

Both A and C are `if (!isJava)` paths, and `postgresql.bicep:71` hardcodes its own suffix
correctly. **A completely green Java run proves nothing about either.** Anyone validating this
material on one stack will ship both.

The root cause is worth stating plainly, because it will recur:
`environment().suffixes.sqlServerHostname` returns `.database.windows.net` **with a leading
dot**, while `environment().suffixes.storage` — used correctly ten lines away — returns
`core.windows.net` **without one**. The two neighbouring, apparently parallel usages are not
parallel at all.

---

### D. `az acr build .` uploads the working tree, and the tag claims a commit it may not contain

The runbook builds the image as `catalog-dotnet:$SourceCommit` and treats that tag as
provenance: Challenge 3 checks the source out at `$SourceCommit` and rebuilds from it. But
`az acr build` tars the *working directory*, not the committed tree, and the runbook never
asks for a clean tree before step 4 — the per-task `git status --short` at line 130 belongs to
step 3 and is not repeated.

I hit this for real. My first successful image was built from a working tree that contained two
uncommitted `Dockerfile` fixes. The tag named a commit that did not, and could not, produce it.
Nothing anywhere would have caught that: the digest is immutable, the tag is well-formed, the
manifest exists, and `evidence/container-registry.json` validates. The lie only surfaces in
Challenge 3, as an unreproducible build.

I resolved it the honest way — committed and pushed the fixes, then rebuilt and re-derived the
digest so the tag genuinely corresponds to its commit. One line in the runbook
(`if (git status --porcelain) { throw }` before `az acr build`) closes it permanently.

---

### E. `catalog-migrate` cannot invoke `az` on Windows at all

`catalog_migrate/process.py:77` runs child processes with `subprocess.run(list(argv), ...)`,
`shell=False`, and sixteen call sites pass `"az"` as `argv[0]`. On Windows the Azure CLI is
installed **only** as `az.cmd`; there is no `az.exe`. Python's `subprocess` uses
`CreateProcess`, which searches `PATH` and appends `.exe` but never consults `PATHEXT`, so
`"az"` cannot be executed. Measured on the provisioned VM:

```
shutil.which("az") = C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.CMD
az     : OSError -> FileNotFoundError: [WinError 2] The system cannot find the file specified
az.cmd : returncode=0
az.exe : OSError -> FileNotFoundError: [WinError 2] The system cannot find the file specified
```

This is not a portability problem. It is broken on the exact platform the material mandates,
for every migration subcommand. Note that `shutil.which("az")` — already imported nowhere, but
one line away — resolves it correctly, so the fix is `shutil.which(argv[0]) or argv[0]`.

The diagnostic makes it much worse. `process.py:87` collapses every `OSError` into
`external tool could not complete: az` and discards the exception, so the attendee is told a
tool "could not complete" with no errno, no path, and no indication that the executable was
never found. I only identified it by reproducing the `subprocess` call by hand.

I worked around it by compiling a ten-line C# forwarder named `az.exe` and putting it ahead of
the real CLI on `PATH`.

---

### F. The two migration guard-rails are mutually exclusive, so the migration cannot be automated

This is the finding I would act on first, because it is structural rather than a typo.

`catalog-migrate` protects the cutover with two independent preconditions, both applied to
`export`, `import`, `images copy`, `verify` **and `render-handoff`**:

1. `azure.py:208-210` — the host's own IMDS identity must equal `migrationSourceVmResourceId`.
   IMDS is read with `trust_env=False`, so it cannot be proxied. **The migration must run on
   the source VM.**
2. `azure.py:81` — that VM's `provisioningState` must be `Succeeded`.

Individually both are sound. Together they are unsatisfiable for any non-interactive delivery,
because the only headless way onto a VM with no Bastion, no public IP and no desktop is
`az vm run-command invoke` — **and run-command puts the VM into `Updating` for the duration of
the invocation.** Measured from the laptop while a run-command slept:

```
IDLE   state: Succeeded
DURING run-command: Updating
DURING run-command (2nd sample): Updating
AFTER  run-command: Succeeded
```

So gate 1 forces the code onto the VM, and the only mechanism that can put it there trips
gate 2. Driven through run-command, `catalog-migrate` fails with
`precondition-failed: Azure resource is not provisioned` **100% of the time**, regardless of
the VM's actual health.

The material never states that an interactive desktop session on the source VM is a hard
requirement, but it is one, and this delivery has no Bastion host to provide it. I worked
around it by having run-command register a Windows scheduled task and exit, so the migration
executes while the VM is idle and genuinely `Succeeded`.

Two things follow for the authors:

- If headless operation is ever intended, gate 2 must exclude the running operation — check
  `PowerState/running`, or the VM's health, rather than `provisioningState`.
- The error text is actively misleading. `Azure resource is not provisioned` describes a VM
  that failed to deploy. The observed VM was running, healthy, and had been serving the
  workshop for hours. An attendee who trusts that message will go and investigate a VM that
  has nothing wrong with it.

---

### G. Path 1C never authenticates the isolated Azure CLI profile it depends on

`catalog_migrate/database.py:36` pins every child `az` invocation to a private profile:

```python
AZURE_CONFIG = str(Path.home() / ".azure-365")
```

and `azure_environment()` injects it into all sixteen call sites. `AZURE_CONFIG_DIR` is also
absent from `process.py`'s inherited-environment allowlist, so the caller cannot influence it.
That isolation is deliberate and reasonable.

But the Copilot runbook sets `AZURE_CONFIG_DIR` exactly **once, at line 456** — inside the
acceptance step, which runs *after* the migration (step 5, line 249) and after both
application deployments (step 6, line 382). Neither the Copilot runbook nor the manual one
ever contains an `az login` at all. The manual runbook at least sets the variable at line 123,
before it is first needed; Path 1C sets it 200 lines too late.

The failure this produces is the reason it belongs in this section rather than the loud one:

```
external tool failed: az: WARNING: Subscription '7bc68c68-...' not recognized.
ERROR: Please run 'az login' to setup account.
```

The message tells you to run `az login`. Doing so populates the **default** profile, which the
migration CLI has explicitly arranged never to read. The remedy the error recommends does not
work, and the attendee has no way to know that the tool is looking somewhere else. You must
know to run `az login` with `AZURE_CONFIG_DIR` already pointing at `~/.azure-365` — which no
attendee-facing document says.

---

### H. The Copilot path is missing the bootstrap deployment entirely

Step 5 of `solutions/ch01-copilot-modernization/dotnet/README.md` opens with:

> The bootstrap output must already exist at `evidence/azure-target-output.json`.

Nothing in that runbook ever produces it. It contains exactly two
`az deployment group create` invocations, at lines 382 and 391, and both are application-stage
(`baseline` and `release`); the only write of `azure-target-output.json` is the release one at
line 400, which the text itself describes as *replacing* the bootstrap document. There is no
bootstrap deployment anywhere on the path.

Both manual runbooks have it — `solutions/ch01-manual/dotnet/README.md:219` is the missing
block. Both Copilot-path runbooks, .NET and Java, omit it. This is a whole-path defect, not a
stack-specific one.

It is mostly a loud failure, but it has one quiet way to go wrong: an attendee blocked at step 5
will find the manual runbook's bootstrap block sitting in the same repository and adapt it —
and that block reads `C:\protected\manual-dotnet-bootstrap.json`, a *different* protected
parameter file, from a different path with a different `applicationRevisionRole`. Following the
nearest available instructions deploys the wrong slice.


### I. The migration harness decodes `sqlcmd` output with the Windows ANSI codepage, so export always fails

This one stops the .NET stack dead, on the intended VM, for every attendee, and no document
mentions it.

`catalog-migrate sql export` verifies the source database against the canonical corpus before
it exports anything. The verification compares full row *content*, not just counts
(`catalog_acceptance/database.py:741`). The rows come back from `sqlcmd` through
`CommandRunner.run`, which does this:

```python
completed = subprocess.run(list(argv), check=False, capture_output=True, text=True, ...)
```

`tests/acceptance/catalog_migrate/process.py:81`, and identically at
`catalog_acceptance/database.py:91`. **`text=True` with no `encoding=`** decodes the child's
bytes using `locale.getpreferredencoding(False)`. Measured on `vm-dotnet-user001`:

```
PY= 3.12.10
STDIO_ENC= cp1252   PREFERRED= cp1252
```

`sqlcmd -C` emits UTF-8. So every non-ASCII byte sequence is silently mojibaked. The canonical
corpus contains exactly one such character — U+2019, a curly apostrophe, in the description of
figure `83e9d76a-…` ("A steady hand in the ship's kitchen"). Its UTF-8 bytes `E2 80 99` decode
under cp1252 to `â€™`:

```
DB_FIGURES= 198  CANON= 198
DB_CATS= 20      CANON= 20
ONLY_IN_DB= 1    ONLY_IN_CANON= 1
CATS_MATCH= True
DB_CODEPOINTS=    ['0xe2', '0x20ac', '0x2122']
CANON_CODEPOINTS= ['0x2019']
```

Everything is correct — 198 figures, 20 categories, categories match exactly — and the command
still fails, with:

```
{"command": "sql export", "error": {"code": "verification-failed",
 "message": "database figure rows differ from the canonical corpus"}, "exitCode": 5}
```

That message names the right symptom and gives the attendee no way at all to reach the cause.
The counts match. The data is fine. One apostrophe, in one description, out of 198 rows, and
the only diagnostic offered is "rows differ".

**The fix requires no change to any workshop code.** Python honours UTF-8 mode as an
environment setting:

```powershell
$env:PYTHONUTF8 = '1'
```

Re-running the identical comparison with it set:

```
STDIO_ENC= utf-8   PREFERRED= utf-8
DB_FIGURES= 198  CANON= 198
ONLY_IN_DB= 0    ONLY_IN_CANON= 0
CATS_MATCH= True
```

Zero differences. This is how I unblocked the run.

Three things worth separating here:

1. **The bug is one keyword.** `encoding="utf-8"` on both `subprocess.run` calls fixes it
   permanently and cannot regress. Python 3.15 makes UTF-8 mode the default, so this defect
   has a shelf life — but the workshop pins 3.12, so today it is universal.
2. **It is stack-asymmetric, and that is why it survived review.** `psql` on the Java stack
   respects `PGCLIENTENCODING` and the Java track's canonical corpus is reached through a
   different client path. A green Java run does not exercise this at all. This is the *third*
   defect I have found in this chapter that is invisible to the Java stack (see A, B, C) —
   the pattern is now strong enough to be a process finding in its own right: **anything
   guarded only by `if (!isJava)` or reached only through the SQL Server client is
   effectively untested.**
3. **The error message is the real defect.** A verifier that compares 198×7 fields and reports
   "rows differ" is not much better than one that reports nothing. It knows exactly which row
   and which field mismatched. Printing the first differing tuple — even truncated, even
   redacted — converts a two-hour dead end into a ten-second fix. I only diagnosed it by
   importing the harness's own internals on the VM and diffing the two sets by hand, which is
   not a reasonable ask of an attendee.

**Recommended:** add `encoding="utf-8"` at both call sites; make the mismatch message include
the first differing row's identity and field name; and until then, put `PYTHONUTF8=1` in both
.NET runbooks next to the `AZURE_CONFIG_DIR` export.

### J. The verifier compares row *content*, and that is the only reason a corrupted `product_id` did not migrate

This is the counter-example to almost everything else in this document, and it deserves to be
recorded as a success rather than a defect — but it also exposes how narrow the margin was.

While diagnosing I, I ran the same comparison through `catalog_acceptance`'s *default*
executor rather than the migration runner. That executor passes `env=environment` where
`environment` is only `{"SQLCMDPASSWORD": …}` — so the child gets no `USERPROFILE`. Under that
environment `go-sqlcmd` writes a diagnostic **to standard output**, not standard error:

```
Error getting user's home directory: %userprofile% is not defined, will use current
directory "C:\MicroHack\source\tests\acceptance" as default
```

`_parse_rows` (`catalog_acceptance/database.py:108`) splits stdout on newlines and tabs. The
banner has no tab, so it does not change the column count — instead it is glued onto the front
of the first data row's first column. The resulting figure identity was:

```
Error getting user's home directory: %userprofile% is not defined, will use current
directory "C:\MicroHack\source\tests\acceptance" as default17d84a22-2f5e-4097-82dd-0066a23c84ff
```

A tool's error message became a primary key.

The row count was still exactly 198. The category count was still exactly 20. **Every
count-based check passes on this data.** If the verifier had compared `SELECT COUNT(*)` — which
is what most people write, and what the runbook's own success criterion ("198 figures, 20
categories, 198 images") invites you to check by hand — this would have exported clean,
imported clean, and put a corrupted identity into Azure SQL, where it would surface much later
as a 404 on one figure and nothing else.

It was caught only because `verify_database_connection` compares the full seven-field tuple of
all 198 rows. That is good engineering and it should be called out as such in the material,
because right now the design is invisible: the runbook presents the row counts as the success
criterion, which teaches exactly the weaker check that would have missed this.

Two follow-ups regardless:

- `catalog_acceptance/database.py:80-105` should pass through `USERPROFILE` the way
  `catalog_migrate/process.py:25-44` already does — the migration runner allowlists it, the
  acceptance runner does not, and they are used against the same client.
- `_parse_rows` should reject or skip lines that do not have exactly `width` tab-separated
  fields *before* treating them as data, rather than relying on the column count of a
  concatenated line coincidentally matching.

**Why this one matters most.** Every other finding in this document is a thing that broke.
This is a thing that *nearly didn't* — a corrupted database that satisfies every documented
success criterion. It is the cleanest illustration in the whole delivery of the difference
between checking that the numbers look right and checking that the data is right, and the
workshop currently teaches the first while its harness quietly does the second.

### K. `sqlcmd` reports T-SQL errors on stdout with exit code 0, and the harness parses them as rows

Immediately behind the encoding defect sits a second deterministic blocker, and it is a
sharper instance of the same underlying mistake.

Once the corpus comparison passed, export failed with:

```
{"command": "sql export", "error": {"code": "verification-failed",
 "message": "database client returned an unexpected row shape"}, "exitCode": 5}
```

I isolated it by running each verification query individually on the VM:

```
_table_names:     OK n=3
_schema_rows:     OK n=10
_constraint_rows: OK n=7
_index_rows:      OK n=6
_migration_rows:  OK n=1
_tls_detail:      FAIL ValueError: database client returned an unexpected row shape
```

`_tls_detail` (`catalog_acceptance/database.py:635-653`) queries
`sys.dm_exec_connections`, which requires `VIEW SERVER STATE`. The seeded `catalog` login
does not have it. The raw response:

```
Msg 300, Level 14, State 1, Server dotnet-u001\SQLEXPRESS, Line 1
VIEW SERVER PERFORMANCE STATE permission was denied on object 'server', database 'master'.
Msg 297, Level 16, State 1, Server dotnet-u001\SQLEXPRESS, Line 1
The user does not have permission to perform this action.
```

Two separable defects.

**K1 — the seed grants the wrong permissions.** The provisioning that creates the `catalog`
login gives it enough to read the catalog tables but not enough to satisfy a check the export
performs unconditionally. Nothing in the material mentions `VIEW SERVER STATE`. Every attendee
on the .NET stack hits this, on the intended VM, at the same step. I unblocked it with:

```sql
GRANT VIEW SERVER STATE TO [catalog];
```

issued as `NT AUTHORITY\SYSTEM`, which is `sysadmin` on this Express instance. That is a
permission grant only — it touches no catalog data and cannot affect the migrated corpus.

**K2 — and this is the one that matters — `sqlcmd` exited 0.** Neither `_run_client`
(`check=True`) nor `CommandRunner.run` (`returncode != 0`) raised, because `go-sqlcmd` does not
set a non-zero exit code for T-SQL errors unless `-b` is passed, and the connection built at
`catalog_acceptance/database.py:325-337` does not pass it:

```python
connection = ["sqlcmd", "-S", server, "-d", database, "-U", username, "-h", "-1", "-W", "-C"]
```

So a *server error message* was returned to the caller as if it were a successful result set,
and `_parse_rows` treated those four lines as candidate data rows. It rejected them only
because none of them happened to contain exactly one tab.

That is luck, not a check. `_parse_rows` accepts any line whose tab-separated field count
matches the expected width. A T-SQL error whose text happens to split into the right number of
fields is indistinguishable from data. This is the identical mechanism to finding J — where
`go-sqlcmd`'s missing-`%USERPROFILE%` banner was glued onto a `product_id` — arriving through a
different door. Twice in one command path, tool output that is not data was consumed as data.

**Recommended:** add `-b` to the sqlcmd argument vector so T-SQL errors become non-zero exits
and surface as `ToolError` with the server's own message, which would have made both K and J
diagnose themselves in one line. Add `VIEW SERVER STATE` to the seed grants, or drop the TLS
check for `target == "source"` where it is not asserted on anyway (`_tls_detail` only enforces
encryption when `target == "managed"`, so for the source database it is a pure read whose
result is discarded into a display string). And treat "the client's diagnostics land in the
same stream as its data" as a systemic property of this harness rather than three separate
bugs — every `_parse_rows` call site inherits it.

### L. The SQL logical server has no managed identity, so the import always fails *after* it has already imported the data

This is the most consequential finding in the chapter, and its failure mode is the worst kind:
the command reports failure after it has already made an irreversible change, and the state it
leaves behind cannot be recovered by re-running it.

`catalog-migrate sql import` does two things in sequence. First it runs SqlPackage to import the
bacpac. Then it grants the application's managed identity access
(`tests/acceptance/catalog_migrate/database.py:551-580`):

```sql
CREATE USER [id-mh-user001-dotnet] FROM EXTERNAL PROVIDER
  WITH OBJECT_ID='92355f34-9b47-461c-afe8-bfa26c020bb1';
ALTER ROLE db_datareader ADD MEMBER [id-mh-user001-dotnet];
ALTER ROLE db_datawriter ADD MEMBER [id-mh-user001-dotnet];
```

`FROM EXTERNAL PROVIDER` makes the logical server resolve the principal against Microsoft Entra.
That requires the server to have a managed identity, and that identity to hold the Entra
**Directory Readers** role. `infra/modules/sql.bicep` has no `identity:` block at all — the
server is created without one:

```
{"command": "sql import", "error": {"code": "tool-failed", "message":
 "external tool failed: sqlcmd: Msg 33134 … Principal '92355f34-…' could not be resolved.
  Error message: 'Server identity is not configured. …'"}, "exitCode": 4}
```

I assigned a system-assigned identity to the server myself (`262348b2-…`) and the error moved on
to the second half of the prerequisite:

```
Msg 37353, Level 16, State 1
Server identity does not have the Microsoft Entra Directory Readers permission.
```

Granting Directory Readers needs Privileged Role Administrator. The delivery account holds
Global Reader, so:

```
Authorization_RequestDenied: Insufficient privileges to complete the operation.
```

**Neither half of the prerequisite is created by the template, and neither is mentioned in any
document.** The template threads `workloadIdentityName` and `workloadIdentityPrincipalId`
through three module boundaries (`sql.bicep:6-7`) purely to echo them into
`output applicationPrincipal` — the value the import later tries, and fails, to turn into a real
grant.

**Why the failure mode is the dangerous part.** SqlPackage runs first and succeeds. I confirmed
from the VM, after the command reported `exitCode: 4`:

```
sys.tables      → __EFMigrationsHistory, Categories, Figures
COUNT(*) Figures    → 198
COUNT(*) Categories → 20
```

The migration is *done*. All 198 figures and 20 categories are in Azure SQL. The tool says it
failed. And the command is not idempotent — re-running it now aborts on its own
not-empty precondition, so the documented recovery ("fix the error, run it again") cannot work.
An attendee is left with a populated target database, a red exit code, no
`evidence/migration-report.json`, and no instruction that covers the state they are actually in.
The plausible response — dropping and recreating the database to get a clean run — destroys a
correct migration to chase an error in a step that has nothing to do with the data.

**The workaround, and why it is worth recording.** A contained user for a managed identity does
not need a directory lookup if you supply the SID yourself. The SID is the identity's *client*
ID in little-endian GUID byte order — `2b4a56de-7d44-4725-921f-0b0a26b8be17` becomes
`0xDE564A2B447D2547921F0B0A26B8BE17`:

```sql
CREATE USER [id-mh-user001-dotnet] WITH SID = 0xDE564A2B447D2547921F0B0A26B8BE17, TYPE = E;
ALTER ROLE db_datareader ADD MEMBER [id-mh-user001-dotnet];
ALTER ROLE db_datawriter ADD MEMBER [id-mh-user001-dotnet];
```

Verified afterwards:

```
id-mh-user001-dotnet  db_datareader
id-mh-user001-dotnet  db_datawriter
```

That is byte-for-byte the end state the tool intends, reached without Directory Readers and
without any elevated Entra role. **The template should use this form**, or the tool should fall
back to it — it removes an entire class of tenant-permission dependency from the workshop, and
the client ID is already in `targetOutput.workloadIdentity.clientId`.

**A second, separate access gap.** The migration must run on `vm-dotnet-user001` (finding F), so
it authenticates as *that* VM's managed identity — which is also not a database principal, and
which the template also never grants. `sql.bicep:15-22` configures exactly one Entra
administrator, `principalType: 'User'`, the facilitator, with `azureADOnlyAuthentication: true`
so there is no password fallback. Azure SQL permits one administrator, so making the VM identity
usable means **displacing** the facilitator:

```bash
az sql server ad-admin update -g rg-user001 -s sql-mh-user001-dotnet-kurep3z6 \
  --display-name vm-dotnet-user001 --object-id 8cc6db41-36da-4d9c-8134-2b5e70284db6
```

I did that, completed the migration, and restored the original administrator afterwards. It is a
destructive workaround for a missing grant and no attendee should be improvising it.

**Stack asymmetry, again.** `postgresql.bicep` has the same missing workload-identity grant, but
it also emits `localAdministratorPrincipal` with password authentication and takes
`authentication` as a parameter, so the Java stack retains a credential path that does not depend
on any of this. `sql.bicep:89` hardcodes `output authentication string = 'managed-identity'` and
line 21 disables password auth outright. The .NET stack has no fallback at all. Counting A, B,
C, I and L, that is five defects in this chapter that a green Java run cannot see.

**The security consequence, which is worse than the functional one.** `database.py:554-566` builds
the drop and the create as a *single* statement under `SET XACT_ABORT ON` inside one explicit
transaction:

```sql
SET XACT_ABORT ON; BEGIN TRANSACTION;
IF EXISTS (… WHERE name = N'catalog') BEGIN
  IF IS_ROLEMEMBER(N'db_owner', N'catalog') = 1 ALTER ROLE [db_owner] DROP MEMBER [catalog];
  DROP USER [catalog]; END;
CREATE USER [id-…] FROM EXTERNAL PROVIDER WITH OBJECT_ID='…';
ALTER ROLE db_datareader ADD MEMBER [id-…];
ALTER ROLE db_datawriter ADD MEMBER [id-…];
COMMIT TRANSACTION;
```

Atomicity is the right instinct, but it means the failure of `CREATE USER … FROM EXTERNAL PROVIDER`
also **rolls back the removal of the legacy `catalog` principal — which is `db_owner`.** So the
post-failure state is:

- the catalog data fully imported (SqlPackage ran before the transaction and is not transactional
  with it),
- the legacy privileged SQL-auth principal still present and still `db_owner`,
- the managed identity principal absent,
- exit code 4, and no report explaining any of it.

That is the *exact* security posture the modernization exists to eliminate — a `db_owner` password
principal on a production catalog — silently preserved by a rollback whose purpose was to keep
things safe. `verify` does catch it (`database.py:836-851`, "Azure SQL retains the privileged legacy
catalog principal"), which is genuinely good design, but only if the attendee gets as far as
`verify`; the natural reading of exit code 4 is "the import failed, nothing happened", and the
natural response is to fix something and retry — which the non-idempotent precondition then blocks.

I completed the drop separately after creating the app principal by SID, and confirmed the end
state: `catalog` gone, `id-mh-user001-dotnet` present with exactly `db_datareader,db_datawriter`.

**Recommendation, sharpened.** Split the statement into two transactions and run the *create*
first: creating the new principal before removing the old one is both idempotent-friendly and
fail-safe, whereas the current order makes a partial failure leave behind the one thing the chapter
is trying to remove.

**Recommended:** assign a system-assigned identity to the SQL server in `sql.bicep`; switch the
tool's `CREATE USER` to the `WITH SID … TYPE = E` form so Directory Readers is never needed;
create a principal for the migration identity rather than requiring the single admin slot to be
hijacked; and — independent of all of the above — **split the import into two commands, or make
the principal grant idempotent and re-runnable**, so that a failure in the grant step cannot
strand a successful data import behind a non-idempotent precondition.

---

### M. The migration's storage grant is made to a principal that the migration cannot run as

`catalog-migrate images copy` failed with:

```
external tool failed: az: ERROR: You do not have the required permissions needed to perform this
operation. Depending on your operation, you may need to be assigned one of the following roles:
"Storage Blob Data Owner" "Storage Blob Data Contributor" "Storage Blob Data Reader" ...
```

The template is not careless here — it anticipates this exactly. `environment.bicep:373-381`
declares a role assignment literally named `facilitatorBlobMigration`:

```bicep
resource facilitatorBlobMigration 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (isBlob) {
  scope: blobContainer
  properties: {
    principalId: facilitatorPrincipalObjectId
    principalType: 'User'
    roleDefinitionId: blobDataContributorRole
  }
}
```

Data-plane write access on the image container, granted to a **`principalType: 'User'`**, purely so
the migration can run. The application's own identity gets only `blobDataReaderRole`
(`:363-371`) — correctly, since it only reads. The separation is deliberate and right.

**The problem is that finding F makes that principal unusable.** `validate_migration_topology`
requires the migration to execute *on* `vm-dotnet-user001`, verified through IMDS with
`trust_env=False`. On that VM, in a delivery with no Bastion and no desktop, the only non-interactive
credential available is `az login --identity` — the VM's own system-assigned managed identity. And
the template grants that identity nothing.

So the two constraints are individually reasonable and jointly unsatisfiable:

| Constraint | Source | Requires |
| --- | --- | --- |
| Must run on the source VM | `catalog_migrate/azure.py:208-210` | IMDS host identity match |
| Must have blob data-plane write | `environment.bicep:373` | the *facilitator user* principal |

The only way to satisfy both simultaneously is an **interactive** `az login` on the VM desktop as the
facilitator user — which is precisely the capability this delivery does not have, and which
`challenges/ch01/README.md` never identifies as load-bearing. It reads as a convenience ("you'll be
signed in already"), not as the sole route through a hard gate.

**And `sql.bicep` makes the identical assumption.** Its single Entra administrator is
`principalType: 'User'`, the same facilitator object ID. Findings L and M are therefore one design
decision seen twice: **the migration is designed to be performed by a signed-in human on the VM
desktop.** Remove the desktop and the entire migration identity model collapses — both stores, both
independently.

**Why this costs so much time to diagnose.** The VM's managed identity is **Owner on
`rg-user001`**, so the natural conclusion — "the identity is Owner, it can do anything" — is wrong
in the most expensive possible way. Owner carries `Microsoft.Storage/storageAccounts/*` at the
control plane and **no blob data-plane permission at all**; Azure's data-plane RBAC is a disjoint
role set. Every control-plane probe you run while diagnosing succeeds. `az storage account show`
works. `az storage container list --auth-mode key` works. Only the specific data-plane call fails,
and the error names six roles without saying which principal lacks them or on which resource.

**Workaround:**

```bash
az role assignment create --assignee-object-id <your-vm-mi-principal-id> \
  --assignee-principal-type ServicePrincipal --role "Storage Blob Data Contributor" \
  --scope /subscriptions/…/storageAccounts/stuser001dotnekurep3z6
```

That requires **User Access Administrator or Owner at the scope** — a right the facilitator has
already established attendees do not hold (it is why the Challenge 2 prerequisites had to be
facilitator-deployed). The workaround for the missing grant needs the same elevated permission the
workshop assumes is unavailable. An attendee hitting this alone is stopped.

**Recommendation.** `migrationSourceVmResourceId` is already a required parameter, so the VM's
managed identity principal is derivable at deploy time with a single `existing` reference. Grant
**that** principal Storage Blob Data Contributor alongside the facilitator user, and add it as a
database principal alongside the Entra admin. It costs four lines, removes the desktop dependency
from the migration entirely, and makes `az login --identity` a complete answer rather than a
partial one.

---

### N. The acceptance gate reports correct security code as a failure, and the only change that makes the number go up is deleting the security control

**This chapter was unfinishable as shipped.** It required a harness change by the facilitator
before it could pass. That sentence is the honest headline and everything below is its
justification.

`catalog_acceptance` probes seven path-traversal targets and required all seven to return
`404`. On Azure Container Apps they cannot. ACA's Envoy ingress normalises the request target
— folding backslashes, percent-decoding, then removing dot segments — **before Kestrel ever
sees it**. I established this with a raw TCP + TLS socket probe rather than an HTTP client, so
that no client-side normalisation could be confused for the gateway's:

```
/images/../healthz              -> app receives /healthz
/images\..\healthz              -> app receives /healthz
/images/%2e%2e%2fhealthz        -> app receives /healthz
/images/%2e%2e%5chealthz        -> app receives /healthz
/perftest\catalog               -> app receives /perftest/catalog
/perftest%5ccatalog             -> app receives /perftest/catalog
/images/%252e%252e%252fhealthz  -> app receives it intact, and correctly 404s
```

Six of the seven never reach the application at all. The application's own
`OriginalRequestTargetMiddleware` is **correct** — 8/8 against `TestServer`, where no gateway
intervenes. The gate was failing an app that defends itself properly, deployed behind a gateway
that defends it a second time.

**Why this is the most dangerous defect I found.** Every other defect in this material
manufactures a *false positive* — evidence that looks good and means nothing. This one is a
**false negative**: it reports correct code as insecure, and it blames the attendee. And the
attendee's only lever is their own source. The single edit that moves the number from 21/22 to
22/22 is **deleting the traversal middleware** — because then `/images/../healthz` returns the
health page instead of a 404, which is *worse* security and a *better* score.

So the workshop actively teaches the wrong lesson here: it rewards removing a security control
and punishes keeping it. I want to be plain that I considered and rejected two "fixes" —
weakening the middleware, and hand-editing the report to say `passed`. The second is the exact
fabrication this workshop exists to catch, and it was available to me with no reviewer present.

**Remedy (facilitator's, from my report).** A `_classify_traversal` that sorts each probe into
`rejected` (a real 404), `normalized-upstream` (byte-identical to a direct request for the
gateway-resolved path, proving the app never saw the unsafe target), or `traversed` (anything
else, including any `image/*` response). No assertion was deleted. My verified map:

```
raw-forward-existing       -> /healthz          normalized-upstream
raw-backslash-existing     -> /healthz          normalized-upstream
encoded-forward-existing   -> /healthz          normalized-upstream
encoded-backslash-existing -> /healthz          normalized-upstream
double-encoded-existing    -> /healthz          rejected
raw-route-alias            -> /perftest/catalog normalized-upstream
encoded-route-alias        -> /perftest/catalog normalized-upstream
```

**Keep both artifacts.** `evidence/f73-traversal-gate-capture.md` preserves the 21/22 failure.
The later 22/22 is the *fix working* — it is not evidence that the defect was cosmetic. An
attendee on the real workshop would have been hard-stopped here with no path forward.

---

### O. The telemetry gate can only be satisfied by an attendee whose run went badly

The same class as N, from the opposite pole. N punishes correct work; this one **rewards
invented work**.

`behavior-contract.json` requires eight log signals, four of which are failure signals
(`catalog.query.failed`, `catalog.database.failed`, `catalog.import.failed`,
`catalog.performance.failed`). `handoff.py:270` compares with set **equality**, not superset:

```python
if set(rows) != set(expected_names) or len(rows) != len(result["rows"]):
    raise ValueError(f"telemetry {query_id} result set is incomplete or duplicated")
```

**Nothing in `challenges/`, `solutions/ch01*/` or `docs/` induces any of those four failures.**
A run that goes perfectly emits *none* of them and fails the gate hardest. My own run had two
of them only because my bootstrap went badly — they were accidents, not instruction.

That inverts the incentive the workshop exists to create: the attendee who did everything right
has strictly fewer honest options than the one who struggled, so the smoothest run is the one
under most pressure to hand-write JSON. And hand-written telemetry evidence is **undetectable**
— `_validate_telemetry_results` only checks that the contract's signal names are a subset of
what you *claim* in `observedAttributes`. It never cross-checks Azure.

**The requirement is right; the defect is that it is never taught.** Proving the error paths are
instrumented is arguably the most valuable thing the telemetry gate does — an app that only
emits telemetry on the happy path is exactly the app that goes dark during an incident. So the
fix is to teach fault injection as an explicit, reversible, documented step. I wrote that
procedure and it is now shipped as `docs/TelemetryFaultInjection.md`; my working copy is
`evidence/f74-fault-injection-procedure.md`. Three traps in it are worth repeating here:

1. **Table routing.** `LogError(exception, …)` routes to `AppExceptions`, not `AppTraces`. All
   four failure signals are therefore absent from the table an attendee would naturally query,
   and the material gives **no KQL guidance at all**. This alone looks exactly like missing
   instrumentation. It is a fifth hard stop hiding behind this one.
2. **The coarse fault cannot reach `catalog.query.failed`.** Revoking `db_datareader` wholesale
   does *not* work: `Pages/Index.razor` resolves the **category** list before calling
   `ListAsync`, so the request dies *outside* the instrumented `try`. Only a single-table
   `DENY SELECT ON OBJECT::dbo.Figures`, leaving `Categories` readable, drives execution into
   the catch. Nobody would derive that from the material; I got it from the exception table.
3. **Steps must not overlap.** Combined faults exhaust the connection pool, and the failure
   becomes `InvalidOperationException: Timeout expired…`, which is **not** a `DbException`, so
   the `if (exception is DbException)` guard at `FigureCatalogService.cs:53` silently stops
   emitting `catalog.database.failed`. Injecting two faults at once produces *worse* evidence
   than injecting one.

---

### P. `/readyz` reports the database ready while every catalog read returns 500

Found while inducing the faults above, and it is a defect in the application, not the material —
so I am reporting it against my own work.

With `SELECT` denied on `dbo.Figures`, every catalog page returned `500`, while `/readyz`
continued to return `200` with `database: ready`. The readiness probe opens a connection and
runs a trivial statement, so it is blind to a data-plane authorization failure on the tables the
application actually reads. A load balancer would keep routing traffic to an application that
cannot serve a single request.

A readiness probe should exercise a representative read. As written it answers "can I reach the
server", not "can I serve", and those diverge precisely during the incidents readiness exists to
detect.

---

### Q. The topology gate reads a control-plane property and calls a running, healthy VM "not provisioned"

`_require_resource_state` (`catalog_migrate/azure.py:59-82`) requires
`properties.provisioningState == "Succeeded"` and otherwise raises
`Azure resource is not provisioned`. That check runs inside `validate_migration_topology`, which
gates `export`, `import`, `images copy`, `verify` **and `render-handoff`**.

`provisioningState` describes the **control plane**. What the gate actually cares about is
whether the VM is *running*. During routine platform extension re-application the VM sits at
`provisioningState: Updating` with `PowerState: VM running` — perfectly healthy, serving fine —
and the gate fails with a message that says the resource does not exist in a usable form.

**Two failures at once, from one cause.** The same condition returns
`Conflict: Run command extension execution is in progress` from `az vm run-command`, which in a
delivery without Bastion is the *only* scriptable channel to the machine. So the attendee is
simultaneously locked out of the delivery channel **and** failed by the validator, for reasons
with no relationship to their work, with no diagnostic anywhere that says "wait". Observed
windows here ran to roughly 70 minutes. That makes it chapter-blocking-by-timeout.

It is not per-VM: the .NET and Java VMs were observed in this state simultaneously. On a real
delivery the platform takes out every attendee's control channel at once, while the workshop
tells all of them their resource is "not provisioned".

**One measurement I could not explain, recorded as observed rather than diagnosed.** At
21:28:11 the VM's own managed identity read `Updating` — three API versions, `get-instance-view`,
and `az rest` straight to `management.azure.com`, all agreeing. Eight seconds later my laptop
read `Succeeded` for the same resource, also stable across a multi-minute window. I could not
determine which view was authoritative, and later both agreed on `Updating`. Whatever the
mechanism, the practical consequence stands: **the machine that is required to run the gate is
the one that reads the failing value**, and a facilitator checking from elsewhere may see the
opposite and conclude the attendee is wrong.

`az vm run-command` is also **single-flight per VM**, so `Conflict` has two unrelated causes with
opposite remedies — `Updating` means a platform window, `Succeeded` means someone else is simply
on the channel and nothing is wrong. The expensive remedy for the first (deallocate + start) is
destructive if applied to the second. Checking `provisioningState` first is the only way to tell
them apart, and nothing in the material says so.

---

### R. The VM image ships machine-level `CATALOG_*` variables that hard-stop acceptance, and can silently point it at the wrong database

My first acceptance run on the VM died before contacting anything:

```
ValidationError: 1 validation error for AcceptanceSettings
  Value error, managed Azure SQL verification forbids username and password
```

I passed no username and no password. The cause is persisted at **Machine** scope on the
supplied VM image:

```
CATALOG_DATABASE_HOST = localhost      CATALOG_DATABASE_NAME = LegoCatalog
CATALOG_DATABASE_PORT = 1433           CATALOG_DATABASE_USERNAME = catalog
CATALOG_BASE_URL = http://localhost:5000
```

`cli.py:73` defaults `--database-username` from `CATALOG_DATABASE_USERNAME`, and
`contracts.py:370` then rejects the run. **The error names an argument the attendee never passed,
from a variable the material never mentions, in a shell they never polluted.** Blame-inverting,
and it hard-stops managed acceptance on the shipped image. The one-line fix is to clear the
variable first — `solutions/ch01-manual/dotnet/README.md:342-343` does exactly that, but at
*teardown*, so the codebase knows about the variable and simply never clears it *before*
acceptance.

**The half that matters more.** Those same variables are the defaults for `--database-host`
(`cli.py:53`) and `--database-name` (`cli.py:68`), and they name the **legacy source** SQL
Express, which holds the same canonical 198 figures / 20 categories. Any invocation that supplies
a password but omits host and name verifies the **source** database while reporting on the Azure
migration — counts match, `status: passed`, Azure SQL never touched.

*Scope:* I observed the hard stop and I observed the defaults resolving to
`localhost` / `LegoCatalog` / `catalog` on the VM. I did **not** run the silent-wrong-database
case end to end, because I do not hold the source database password. It is stated from those two
observations plus the two `cli.py` lines, not from an observed run.

---

### S. One challenge's deployment silently invalidated another challenge's evidence

A **Challenge 4** workbook deployment (`obs-workbook-dotnet-ch4`) redeployed the container app
with an **empty revision suffix**. That created two new revisions and **deactivated both the
baseline and release revisions** Challenge 1 had just produced — while leaving the application
healthy, serving correctly, on the correct image digest. Nothing looked wrong.

It matters because `handoff.py:709-715` requires
`revisionName == f"{applicationRevisionRole}-{sourceCommit[:12]}"`, and `:1239-1244` requires the
telemetry, observability and application revisions to agree. So every telemetry signal emitted
after that deployment was attributed to a revision the handoff will reject, and the *only*
symptom was a revision name in a JSON file. Challenges are not as independent as the material
presents them, and Challenge 1's evidence has a lifetime nobody states.

Recovering it surfaced two Azure Container Apps traps worth documenting:

- **`az containerapp revision list` hides inactive revisions** unless `--all` is passed.
  This is far more dangerous than it sounds, because of how it interacts with the handoff
  gate. `validate_release` (`catalog_migrate/azure.py:348-426`) requires the rollback
  revision to be named exactly `<app>--baseline-<sourceCommit[:12]>`, to **exist**, to be
  **`active: false`**, to report `healthState: Healthy`, to have no provisioning error,
  and to carry the release digest. So **the single revision the handoff depends on is
  required to be inactive — and inactive revisions are exactly the ones the default
  listing hides.** Running the obvious diagnostic shows three revisions, none of them the
  baseline, and the correct state is indistinguishable from the destroyed state.

  **I nearly acted on that myself.** Having seen a Challenge 4 deployment disturb my
  revisions once already, I ran `az containerapp revision list`, did not see
  `ca-mh-user001-dotnet--baseline-47acf263d332`, and concluded the handoff was
  unrenderable. I was one command from recreating a revision that already existed — which
  would either have collided on the suffix or produced a second baseline under a
  different name, corrupting the rollback evidence I was trying to protect. What stopped
  me was running `revision show` on the specific name before acting on the absence.
  `revision show` returned it immediately, `active: false`, `Healthy`, correct digest:
  perfectly valid, and invisible one command earlier.

  The general lesson is the one this workshop teaches everywhere else and does not apply
  here: **absence from a filtered listing is not evidence of absence.** A `--all` in the
  runbook would cost nothing and remove the trap entirely.

  A related consequence: a `--revision-suffix` collision reports "a revision with that
  suffix already exists" for a revision you cannot see in the list you just ran.
- **A failed revision update wedges every later write.** After that error the app sits in
  `provisioningState: Failed`, and *every* subsequent PATCH — including a pure
  `ingress traffic set`, and a minimal ARM `az rest` PATCH that returns exit 0 and silently
  no-ops — fails with the same stale-suffix error. The only exit I found was to provision
  once with a fresh unique suffix, then activate the intended revision and re-pin traffic.

---

### V. Aborting `az vm run-command` locally does not cancel it remotely, and silently holds the only channel to the VM

This cost me over half an hour and it is the third distinct cause of `Conflict` from
`az vm run-command`, alongside the two already catalogued (platform patch orchestration;
single-flight contention with a *live* caller). It is the worst of the three, because the
holder is invisible and there is nothing to wait for that any tool will show you.

**What I observed.** From 21:59 onward, every `az vm run-command invoke` against
`vm-dotnet-user001` returned `Conflict: Run command extension execution is in progress`,
continuously, for 35+ minutes. Concurrently:

| Probe | Result |
| --- | --- |
| `az vm get-instance-view` → `provisioningState` | `Updating` |
| `az vm get-instance-view` → extension runtime status | `CustomScriptExtension`, **status `null`, message `null`** |
| `az vm extension list` → `provisioningState` | **`Succeeded`** |
| VM power state | `running`, healthy |
| Activity log, 12 h, **scoped to the VM**, excluding `runCommand/action` | **zero operations** |
| Activity log, my own attempts | `Started` → `Failed`/`Conflict`, every time, instantly |

**The probe has to be scoped to the resource, and my first version was not.** I originally
filtered only on `operationName` across the whole resource group:

```bash
# WRONG - returns another attendee's work as if it were yours
az monitor activity-log list -g rg-user001 --offset 12h \
  --query "[?!contains(operationName.value,'runCommand')].operationName.value" -o tsv
```

At the moment I first ran it, that returned nothing, and I wrote the finding on that basis.
Re-run forty minutes later it returned **nineteen** operations — nine
`Microsoft.DBforPostgreSQL/flexibleServers/write` (the *other* arm working on their own VM)
and ten Azure Policy evaluations that fire on their own schedule. None of them touch
`vm-dotnet-user001`.

**This fails in the dangerous direction.** A non-empty result reads as "the platform is
busy, wait for it", which is the wrong advice for precisely the condition this finding is
about — and the noise is generated by an unrelated attendee whose activity you have no
reason to be looking at. The correct form:

```bash
az monitor activity-log list -g rg-user001 --offset 12h \
  --query "[?contains(to_string(resourceId),'vm-dotnet-user001') \
           && !contains(operationName.value,'runCommand')].operationName.value" -o tsv
```

`to_string(resourceId)` is required; without it JMESPath errors on entries whose
`resourceId` is null. I verified both forms back to back: unscoped returns 19, scoped
returns empty. **I am recording my own error here because it is the same class of mistake
the finding is about** — a diagnostic that looks authoritative, answers plausibly, and is
measuring the wrong thing.


So: nothing was being patched, no extension operation was in progress, no ARM operation
of any kind had touched the VM in twelve hours, and the one extension present reported
`Succeeded` at the resource level while reporting no runtime status at all.

**The leading explanation, stated as a hypothesis with its evidence.** Shortly before the
wall began I had started an `az vm run-command invoke` that hung — it was running
`az cache purge`, `az account clear` and `az login --identity` on the VM — and I killed
the **local** `az` process. Killing the local client does not cancel the remote
invocation: the extension keeps executing on the VM until it finishes or hits the
service-side execution limit, and it holds the single-flight channel for that whole
period. Everything above is consistent with an orphaned invocation that no longer has a
client.

I cannot *prove* that specific invocation is the holder, because there is no way to
enumerate in-flight run-commands — which is itself the finding. I record it as the
explanation that fits every observation, not as a demonstrated fact.

**Why it matters more than the other two `Conflict` causes:**

1. **The `provisioningState` check does not discriminate here.** The published guidance is
   that `Updating` means a patch window (wait) and `Succeeded` means a live caller holds
   the channel (wait, benign). This case reads `Updating` — so it is diagnosed as a patch
   window, and the attendee is told to wait for something that is not happening. The
   discriminator that works for the first two causes silently misclassifies the third.
2. **It defeats the F-82 fix.** That fix retries, bounded, over transient provisioning
   states. This state is not transient in any useful sense — it is held by an orphan with
   its own timeout, unrelated to anything the retry can observe. A bounded retry will
   exhaust its bound and fail, having correctly concluded nothing.
3. **It makes the destructive remedy look correct.** The standing advice is that
   deallocate + start is justified once a VM is wedged beyond ~20 minutes. This condition
   trips that threshold routinely and *looks* exactly like a genuine wedge: nothing
   running, nothing progressing, half an hour gone. Deallocating would destroy whatever
   the orphaned command was doing — which, since it is usually the attendee's own
   long-running job, is precisely the work they are trying to protect.
4. **There is no observability whatsoever.** No `az vm run-command list` for in-flight
   invocations, no cancel, no timeout visible, no correlation ID surfaced in the
   `Conflict` message. The error names the condition and nothing about the holder. With
   boot diagnostics off and Bastion interactive-only, there is no independent channel to
   go and look.

**Practical guidance that should be in the material:** if `run-command` returns `Conflict`
and the activity log shows **no non-`runCommand` operation** in the recent past, you are
almost certainly holding your own orphaned invocation. **Wait it out. Do not deallocate.**
And never `Ctrl-C` a long `az vm run-command invoke` expecting it to stop — it does not.
If you must abandon one, expect the channel to stay locked for the remainder of its
server-side execution limit.

**A cheap structural fix.** The pattern I adopted for long jobs — have `run-command` do
nothing but register a scheduled task, write progress to a log file, and return
immediately — avoids this entirely, because no invocation is ever long-lived. Every
invocation completes in seconds and the channel is never held. That pattern is worth
putting in the runbooks regardless of everything else here; it also solves the 4096-byte
output cap.

---

### T. There is no per-attendee identity, so no evidence is attributable to anyone

Checking who created a hand-made role assignment, I found that my principal, the facilitator's
principal and the other arm's principal are **the same Azure identity**
(`admin@MngEnvMCAP372348.onmicrosoft.com`). Every `createdBy` in the subscription resolves to it
by construction.

I could confirm I had made that change only from my own written record, not from Azure. For a
workshop whose entire premise is evidence provenance — and which asks attendees to record commit
SHAs, image digests and revision names precisely so claims can be checked — the environment
itself cannot answer "who did this". That undercuts the lesson at the infrastructure level, and
it also means a facilitator cannot distinguish an attendee's change from their own.


Checking who created a hand-made role assignment, I found that my principal, the facilitator's
principal and the other arm's principal are **the same Azure identity**
(`admin@MngEnvMCAP372348.onmicrosoft.com`). Every `createdBy` in the subscription resolves to it
by construction.

I could confirm I had made that change only from my own written record, not from Azure. For a
workshop whose entire premise is evidence provenance — and which asks attendees to record commit
SHAs, image digests and revision names precisely so claims can be checked — the environment
itself cannot answer "who did this". That undercuts the lesson at the infrastructure level, and
it also means a facilitator cannot distinguish an attendee's change from their own.

---

## Defects that fail loudly (lower value, but real)

- **Toolchain host pins are unreachable.** `workshop/toolchain.lock.json` pins SDK
  `10.0.400` / runtime `10.0.11`. Neither exists; the highest published .NET 10 SDK is
  `10.0.101`. Only the container digests are still obtainable.
- **The entire migration is IMDS-gated to the source VM.**
  `tests/acceptance/catalog_migrate/azure.py:42-56` reads IMDS with `trust_env=False` and
  requires host identity to equal `migrationSourceVmResourceId`. This gates `export`,
  `import`, `images copy`, `verify` **and `render-handoff`** (`cli.py` lines 160, 179, 205,
  259, 283). It is documented behaviour, not a defect — but it means no part of Challenge 1
  after the code work can be executed off the VM, including producing
  `evidence/modernization-contract.json`. Any delivery model that assumes otherwise is
  wrong for this chapter specifically.
- **`az vm run-command` mangles quoting.** Every runbook block is written for an interactive
  shell this delivery cannot obtain, and there is no `RunShellScript` on Windows. Reliable
  invocation requires base64-encoding the script and decoding it in-guest. This is a
  material-rewrite-sized issue for any non-desktop delivery, not a workaround.
- **`Conflict: Run command extension execution is in progress`** is usually transient
  serialization between consecutive invocations and clears on retry. A genuine wedge is
  different: it persisted ~55 minutes and was cleared only by `az vm deallocate` +
  `az vm start`. `az vm extension delete` hangs on the same wedge it is meant to clear, and
  `az vm restart` makes it worse by re-triggering the CSE.
- **Public IP allocation is denied subscription-wide**, so the frozen
  `internal: false` in `infra/modules/environment.bicep:423` fails deployment outright with
  `SubscriptionNotRegisteredForFeature … AllowBringYourOwnPublicIpAddress`. Patched here
  with an opt-in `containerAppsEnvironmentInternal` parameter defaulting to `false`, leaving
  the frozen template unchanged for a normal subscription. Consequence: with the internal
  environment, `applicationUrl` is VNet-private, so a laptop `curl` timeout is **not** a
  deployment failure — recording it as one would manufacture a false negative.
- **`az resource list -g rg-user001` returned `[]`** while Resource Graph returned 12
  resources in the same group. Graph is authoritative. An attendee trusting the empty list
  would conclude their environment was never provisioned.
- **No Bastion host exists** in this delivery, so the documented access route for the whole
  chapter is absent; and **`workshop/golden/dotnet-sqlserver/` is empty**, so the documented
  15:15 rejoin path does not exist either. A blocked participant has no fallback.

---

## What is well designed, and worth protecting

The contrast here is sharp and instructive.

**`evidence/runtime-test-report.json` is genuinely unforgeable.** The schema requires exactly
14 tests; the `id` values are a fixed enum; each id is pinned to an exact `testIdentity`
through a canonical map in `tests/acceptance/catalog_acceptance/handoff.py:20-75`; and
`handoff.py:211-228` **re-parses the TRX** and rejects the handoff unless every one of those
identities is present with outcome `passed`. You cannot hand-write it, and you cannot pass it
without actually having run the tests.

That is what a good evidence artifact looks like, and the workshop already contains one. The
gap is not that the authors don't know how — it is that the path-specific evidence for
Path 1C was never held to the same standard as the shared evidence.

**Recommendation.** Apply the `runtime-test-report.json` design to at least
`task-results.json` — a schema, plus one machine-checkable field (for example, the commit
SHA each task's validation actually ran against) would move it from "prose anyone can write"
to "claim that can be contradicted".

---

## Every hand-fix this run required that the material never mentions

Each of these was necessary to make a documented step work. None appears in any runbook,
README or troubleshooting table. I have separated the ones I found myself from the ones a
facilitator handed me, because the second group would have blocked me indefinitely without
out-of-band help — which an attendee does not have.

**Found and fixed by me, on the spot:**

| # | Hand-fix | What breaks without it |
| --- | --- | --- |
| 1 | Remove `--platform` from `FROM` in `dotnet/Dockerfile`, and exclude blob images from the build context | `az acr build` fails on an arm64 host; the image otherwise carries a 200 MB image directory that the blob store has just replaced |
| 2 | Correct the SQL hostname suffix and uniquify the private-DNS VNet link name per stack | The second stack's deployment collides with the first on a shared link name |
| 3 | `Remove-Item Env:CATALOG_DATABASE_USERNAME` / `…_PASSWORD` before every migration command | Machine-level variables baked into the VM image override managed-identity auth; acceptance then fails, or worse, silently targets a different database (finding R) |
| 4 | Grant `Storage Blob Data Contributor` on the target storage account to the source VM's system-assigned identity | `catalog-migrate images copy` cannot authenticate. Owner at the resource group is control plane and confers no blob data access (finding M / F-83) |
| 5 | Add the source VM's identity as SQL Entra admin | The logical server has no identity that can execute the import (finding L) |
| 6 | `--all` on `az containerapp revision list` | The rollback baseline is inactive by design, and inactive revisions are hidden by default — so the one revision the handoff depends on is exactly the one you cannot see (finding S) |
| 7 | gzip + base64 chunking for anything read back from `run-command` | Output is truncated at ~4096 bytes with no error and no marker |
| 8 | Register a scheduled task from `run-command` and poll a log file, instead of running long commands inline | Inline long commands hold the single-flight channel and, if abandoned, keep holding it invisibly (finding V) |

**Handed to me by the facilitator, and load-bearing:**

| # | Hand-fix | What breaks without it |
| --- | --- | --- |
| 9 | Patch `internal: false` → parameterised in `environment.bicep` and `main.bicep`, pass `containerAppsEnvironmentInternal=true` | Public IP allocation is denied subscription-wide; the bootstrap deployment fails outright (F-47) |
| 10 | `export AZURE_CONFIG_DIR="$HOME/.azure-365"` in **every** shell | `catalog_migrate/database.py:35` hardcodes that path; a mismatch splits credentials across two profiles and fails confusingly |
| 11 | `uv --no-config` on every invocation | The machine's `uv.toml` uses a key the installed uv rejects |
| 12 | `git rm .github/workflows/**` in a commit on top before pushing | The token lacks `workflow` scope; the REST Contents API returns a 404 that masks the denial (F-45) |
| 13 | A `PATHEXT`/`az` shim directory on the VM | `az` was unresolvable from the job context (F-65) — **since fixed upstream and confirmed no longer needed** |

**The pattern worth naming.** Eight of the thirteen are authentication or identity problems,
and every one of those failed with an error that pointed somewhere else: a control-plane
role that looks sufficient, a stale environment variable that looks like configuration, a
hidden revision that looks deleted. The workshop teaches managed identity as a *goal* and
never as a *failure mode*, and the failure modes are where all the time goes.

**On item 4 specifically, since it was asked.** I checked rather than recalled. The
assignment on `stuser001dotnekurep3z6` was created `2026-08-27T18:24:35Z`; my commit
writing up that exact problem (`2c26e8a`, "findings L and M") landed `2026-08-27T18:29:51Z`,
five minutes and sixteen seconds later. That is a record, not a memory. Azure's own
`createdBy` cannot confirm it, because every principal in this subscription is the same
identity (finding T).

## What this run did not measure

Listed so nothing here is inferred from what is present. Several of these are the *most*
important things about Path 1C, and I could not reach any of them.

**The path itself, as designed:**

- **VS Code and the three pinned extensions were never used.** There is no GUI in this
  delivery. I did the modernization as the Copilot CLI agent in a terminal. Everything I
  produced is labelled accordingly. Whether the extension-driven path is better, worse or
  equivalent is **not measured** — I can only report that the work was completable without
  it, which is a different claim.
- **The Bastion route was never exercised**, because no Bastion host exists here.
- **The 15:15 golden rejoin path was never exercised**, because
  `workshop/golden/dotnet-sqlserver/` is empty.
- **Wall-clock timings for the intended environment are unmeasured.** My numbers describe a
  macOS laptop driving a Windows VM through `run-command`, which is not the intended
  delivery and is slower in ways that are mine, not the workshop's.

**Evidence I did not produce:**

- **Zero screenshots.** Not "few" — none. No portal capture, no terminal capture, no
  application capture. There is no GUI, and `run-command`'s output cap plus the channel
  contention make image capture impractical. I would rather report zero than imply
  otherwise.
- **`evidence/modernization-contract.json` does not exist.** `render-handoff` is IMDS-gated
  to the source VM and the channel has been unavailable.
- **Telemetry under the release revision was not captured.** Every signal I have was
  emitted under `--0000001`, before the release deployment.
- **The published `docs/TelemetryFaultInjection.md` was not executed verbatim.** I ran my
  own draft, which the facilitator then published with edits. The shipped text remains
  formally unverified, and its step 1 supplies no actual command, which would block a
  literal execution regardless.
- **`evidence/ide-extensions.txt` was deliberately not written.** See the honesty note
  above: it is unvalidated and trivially forgeable, and writing one would have been the
  single most convincing false artifact available to me.

**Claims I deliberately did not try to strengthen:**

- **I did not fabricate a telemetry bundle to demonstrate F-89.** The schema text is
  sufficient and the demonstration would have been the wrong thing to leave in the record.
  My claim is the weaker, provable one: the gate cannot distinguish a real bundle from a
  hand-authored one. I have not run a fabricated bundle through the gate and I do not
  assert what would happen if I did.
- **Finding V's mechanism is a hypothesis, not a demonstration.** I cannot enumerate
  in-flight `run-command` invocations, so I cannot prove the orphan I describe is the one
  holding the channel. Every observation is consistent with it; none confirms it.
- **Whether `run-command` exclusivity is per-VM, per-extension or a subscription throttle
  is not measured.** Wording and timing point to per-VM. That is inference.
- **The source SQL Express seeding was not independently re-counted by me.** I used the
  VM's pre-seeded database and verified the *migrated* counts (198 / 20 / 198) against the
  canonical figures. The claim that the source was correct before I touched it rests on the
  verifier's row-content comparison, not on a separate count.

**Out of scope entirely:** the Java/PostgreSQL stack, and Challenges 2 through 6. Where I
have referred to them it is because a facilitator relayed it, and it is second-hand.

## Summary recommendation

**If only one change is made, make the telemetry evidence bindable to provenance
(finding U).** It is the only defect here where an attendee who does everything right and
an attendee who invents the file produce byte-identical artifacts, and the gate cannot tell
them apart. Everything else in this document costs time; this one costs the workshop its
premise, because Challenge 1 exists to teach that evidence must be checkable. Note that the
fix requires relaxing `additionalProperties: false` on `telemetry-query-result.schema.json`
first — otherwise the schema rejects the provenance keys you add. No digest guard pins that
schema, so no contract version bump is needed.

**If a second change is possible, publish the environment-variable contract in the challenge
README.** It is the difference between a modernization that works and one that merely
deploys, and today nothing in the attendee-facing material lets you tell those two outcomes
apart.

**And a structural suggestion that would have caught more than any single fix.** Two of the
sharpest findings in this run — the wrong source tree I started from, and the telemetry
provenance hole — are the same defect wearing different clothes: nothing verifies that the
thing you are working from is the thing you think you are working from. A source-provenance
check the attendee runs *before* starting, and a provenance field the evidence schema
*requires* rather than forbids, are the two ends of one guard. I lost time to the first and
found the second only by reading the validator source. An attendee will do neither.

