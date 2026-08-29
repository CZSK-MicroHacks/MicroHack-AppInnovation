# Challenge 1 Copilot-rewrite Java arm feedback

## Scope and provenance

- Path: `copilot-rewrite`, Java/PostgreSQL slice
- Immutable workshop baseline (the **subject** of every claim): `4bf59f7ee8dae11259d73ba5a5d7cb0e3355c4af`
- **Observation ref (where measurements in this file were taken): `68ef499`.** Any figure below
  that is a property of a moving object -- suite counts above all -- is true at that commit and
  nowhere else by default. These are two different refs and the distinction is load-bearing:
  this file stated its baseline from the first revision and still published a suite count that
  the baseline does not produce. Anchoring the subject does not anchor the measurement.
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
| Runbook fixes committed | 2026-08-27T16:37:17Z .. 2026-08-27T21:54:55Z | `383b9f7`, `5393507` |

> **This row previously read `2026-08-28T02:13:12Z`. That value is the true UTC of neither
> commit it cites (`16:37:17Z`, `21:54:55Z`), is neither commit's local time, is on the wrong
> day, and matches no commit on any ref in this repository -- 0 exact matches, CONTROL-POS the
> same search finds row 3's value. It was unsourced. The other four rows were re-measured and
> are true UTC, honouring the column header. Corrected to the span the two cited commits
> actually bound.**

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
- **Acceptance harness — 639 passed, 1 skipped, observed at `68ef499`.** This green is
  qualified below. (An earlier revision of this file said **612 passed, 1 skipped** and gave
  no observation ref. That figure was accurate when written and is now stale: the suite grows
  as the integration branch adds tests -- 403 test functions at the stated baseline `4bf59f7`,
  476 at `216433e`, 503 at `68ef499`. Both numbers are right at their own commit, which is why
  the commit, not the number, is the part that had to be written down. See the note below.)
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
   The green run above (612 at the time of writing, 639 at `68ef499`) is green **only because
   `--deselect` suppresses that guard.**

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
   ships anywhere in the tree.** **Both** shipped examples --
   `fixtures/sre-agent/handoff.json` and `fixtures/defender/handoff.json` -- declare
   `path = copilot-modernization`, and neither can validate in the location it ships in,
   because the validator folds the handoff's own repo-relative path into the required
   evidence set while the registry pins a different filename.

   > **This read "the single shipped example" until it was re-measured: there are two, and both
   > declare the same path, so the conclusion strengthens and the count was wrong. A count
   > written as a determiner is not searchable as a count.**
7. **Prerequisite recovery off the VM is documented, but described as something else where
   it is linked.** The answers exist as `docs/CommonErrors.md` entries 45 and 101. Every
   challenge README routes troubleshooting to `docs/Troubleshooting.md` (12 links), which
   never mentions `javac`, a JDK or a JRE, and nothing under `challenges/` references the
   error registry at all (0 references across the 13 files git tracks under
   `challenges/`; CONTROL-POS the string `Troubleshooting` matches 12 of those same 13, so the
   instrument reaches the population). One hop does exist —
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
   - Track coverage in that router is **symmetric**: 4 lines mention `java`, 4 mention
     `dotnet`, and they are the *same* four lines — `java-smoke.json`, `provision-java.log`
     and `java-app.log` sit directly beside their .NET counterparts at `:82-:87`, and the
     two target links are adjacent at `:109-:110`. There is no Java-side gap here.

     *Unit stated because the two natural ones disagree.* By word occurrence it is `java`
     **5** to `dotnet` 4, the extra coming from `:110 [Java target](../java/README.md)`,
     where the label and the path are both the word. **The pairing is exact on every line;
     the asymmetry is an artifact of counting a markdown link twice.** An earlier revision
     of this report gave "4 mentions" without saying what a mention was — true on lines,
     false on occurrences, and the reader had no way to tell which had been counted.
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

Readiness cannot detect schema loss. `java/…/web/HealthController.java:49-55` implements
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
  `1fa80cf` **deletes** that block. **CORRECTED FOUR TIMES. The three superseded readings
  were: the term is absent at HEAD; its presence is a surviving defect; the count is 1 at
  every commit. All three are false.** Re-measured at every ref:

      e48f3c3 1 | 1fa80cf^ 1 | 1fa80cf 1 | 8033b29 0 | f113283 1 | HEAD 2
      prohibitive sentence present only at 1fa80cf

  `1fa80cf` deleted the block and added a prohibition. `8033b29`, *retract an overreach
  about entry 101's JDK prohibition*, removed the prohibition and left **no** mention.
  **The block returned at the merge `f113283`, not at any commit that authored it** -- so
  the reconciled text at HEAD, prose permitting a pinned host JDK above a block that pins
  explicitly, **has no authoring commit.** It was assembled by conflict resolution. That is
  why four measurements by two parties disagreed: **there is no single commit to read.**
  HEAD is 2 because the repair in this arm's own fix commit adds the word again. It cherry-picks **cleanly**, and on its
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

**But not every disagreement about a number is skew, and assuming it is costs a real check.**
A count is a function of two things, and only one of them is the revision. Two counts of the
tarball block over the *same* bytes:

| pattern | `8033b29` | `b779325` | tip | `origin/rewrite-integration` |
|---|---:|---:|---:|---:|
| the three prescriptive lines (`mkdir` / URL / `export`) | 3 | 3 | 3 | 3 |
| that, plus incidental re-mentions (`cd`, `tar`) | 5 | 5 | 5 | 5 |

**Both are correct; neither is stale.** The narrow count is flat across every revision the
block has existed at, so a 3-vs-5 disagreement carries no information about *when* either
party looked. **Before attributing a numeric disagreement to rev-skew, re-run both numbers at
one revision** — if they still differ, the instrument differed, not the substrate. This is the
positive control for skew claims specifically, and it is cheap.

### A correction I got wrong in the safe direction, and the defect it exposed

This arm reported that `8033b29` *narrowed* entry 101's "unpinned" to "not digest-pinned".
**That is false as stated, and the disproof is one command:** entry 101's resolution line is
**byte-identical at `4bf59f7` and at this branch's tip.** The commit never touched it.

What it actually added was a **gloss in a different entry** — the non-TTY cask entry, ~245
lines away — asserting how entry 101's sentence should be read. So the reinterpretation is
real, but it lives somewhere the sentence it reinterprets does not point to.

**That is a residual defect in this arm's own fix, and it is this report's dominant theme
turned on its author.** A reader routed to entry 101 — which is where the material sends
them — reads an unqualified *"Do not install an unpinned JDK"* and has no way to learn it is
scoped to the build image. The pointer ran cask-entry → 101 and never 101 → cask-entry, so
the contradiction was only resolved for someone who had already read both. **Knowledge
correct, routing one-directional.** Fixed by scoping the phrase in place and adding the
return pointer; no test pinned that wording.

The general form is worth more than the instance: **describing an added gloss as an edit to
the original is the same operand error as the rest of this record.** Both artefacts contain
the words; only one of them is the one a reader reaches.

**Two properties of the repair are worth naming, because they are what made it safe.** The
original sentence survives *verbatim ahead of* the qualifier, so every existing citation of it
still matches — a routing gap can be closed without invalidating the quotations that
diagnosed it, and appending is what buys that. And the guard that found the gap was the
counterparty's refusal to confirm a claim they could not reproduce: **"unconfirmed, not
refuted" is a disposition worth having**, because it returns the burden to the claimant
without asserting a counter-fact the checker also cannot support.

### The theme, in its concluded form

This item is not an isolated finding. Across the delivery the same defect was instantiated
independently in **every artifact class the exercise contains** — the workshop material, the
audit report about it, and an arm's own remediation of that report, this one:

| artifact | knowledge | routing |
|---|---|---|
| workshop material (`CommonErrors.md`, `Troubleshooting.md`) | present and correct | thin or one-way |
| the audit report | six corrections recorded | no forward pointer at the superseded text |
| this arm's own fix to entry 101 | qualification existed in a sibling entry | one-directional, cask → 101 never back |

**In no case was the knowledge missing, stale, or wrong. In every case the party who needed it
was not routed to it.** That is why "document it better" is the wrong remedy and never the
one to reach for: the documentation already existed and was already correct. **The remedy is
bidirectional linking, checked mechanically** — a link asserted in one direction should fail a
test if its return leg is absent, in exactly the way this repo already fails a build for an
unbound variable in a shell block.

The corollary for anyone *authoring* a remedy: **search the shipping branch for prior work on
the same identifier before writing a new fix** — `git log -S'<identifier>' origin/<your-branch>`.
A re-derived remedy is not merely wasted effort; it can be a strict subset of an existing one
and therefore a regression, while presenting as new work.

### The fourth instance: this file, and it is about how the audit reads

The theme has one more instantiation, and it concerns the intake path rather than any
document's contents. Two findings authored here — that Java HTTP spans discard the URL
(`30c5a05`, 21:10) and that Ch4's database-dependency gate is weaker on Java by construction
(`fb74cf2`, 20:56) — were reported by the coordinating party as never having reached it.

Measured: both commits touch **this file and nothing else**, and both are ancestors of the
published branch tip.

```
30c5a05   1 file   evidence/ch01-feedback-java-rewrite.md   ancestor of published tip: YES
fb74cf2   1 file   evidence/ch01-feedback-java-rewrite.md   ancestor of published tip: YES
```

The content was in the arm's designated deliverable, on the remote,
hours before it was described as undelivered.

**So the failure is not delivery; it is ingestion.** The deliverable is a file on a branch;
the intake path was the message channel beside it. Anything written to the first and not
narrated into the second is invisible to a reader who reads only the second — and it presents
identically to work that was never done.

This distinction decides the remedy, which is why it is worth the paragraph. *"Arms should
report their findings more completely"* is unenforceable and would not have helped: the
findings were complete, written down, and published. **"Read the deliverable at its tip
before concluding anything about its contents"** is one command and would have. A file whose
job is to be the record cannot also depend on being summarised to be read.

### Verify a confession exactly as you verify a claim

The sharpest instance in this record runs the other way, and it is this arm's: **a
self-accusation that this file did not exist**, sent while the file stood at 558 lines and
had been on the remote for over six hours. Its own line 12 says it *"was produced late … it
exists because a completeness poll asked what had never been delivered."* **The artifact
documented the failure mode that was then re-enacted against the artifact.**

Cause, measured: a claim about HEAD made from a commit **24 behind it**. Same error as
everywhere else in this record — describing state rather than reading it — but pointed
inward, and it is the inward direction that made it durable:

> **An over-claim invites scrutiny; a self-accusation disarms it.** A confession is costly to
> its speaker, so it reads as credible, and no counterparty is inclined to argue someone out
> of taking blame. It therefore survives unchecked in exactly the way an unflattering claim
> never does.

**The asymmetry is in the checking, not in the error rate.** Both directions are ordinary
unverified assertions about a measurable artifact; only one of them attracts a reviewer.
So the guard is not a new technique — it is the *removal of an exemption*: **run the same
check on a claim of failure that you would run on a claim of success**, because they are the
same class of statement and are wrong in the same ways.

The narrower operational form, for anyone reporting on their own work: **a claim about your
own tree is a measurement, not a memory.** Past a few dozen commits your branch is an
external artifact you are recalling rather than reading, and it deserves `git log`, not
recollection. The 24-commit gap here is the whole cause; nothing about the reasoning was
faulty, only its input.

### The duplicate source tree, and why a line number is not an address here

The last exchange of this audit was a correction that turned out to be no correction: this
arm cited `AddSqlClientInstrumentation()` at `Program.cs:86`, the coordinating party
measured `:86` as `AddAspNetCoreInstrumentation()` and put SqlClient at `:107`. **Both are
right.** The application exists in two trees, and they have drifted:

| | `dotnet/src/…/Program.cs` | `solutions/reference/dotnet/src/…/Program.cs` |
|---|---:|---:|
| lines | 117 | 148 |
| `AddAspNetCoreInstrumentation` | `:70`, `:83` | `:86`, `:104` |
| `AddSqlClientInstrumentation` | **`:86`** | **`:107`** |

**`:86` is a real OpenTelemetry registration in both files and a different one in each.** That
is the worst available case: not a citation that fails to resolve, but one that resolves
**silently and plausibly** to the wrong call. A reader checking either claim finds
instrumentation at the cited line and confirms.

The scale, measured rather than estimated **at `9bfd9a1` (this branch's tip), 2026-08-28
23:13 CEST**: **81 `.cs`/`.java` sources live under `solutions/reference/`; 75 of them have a
path-identical twin outside it; 64 of those 75 are byte-identical and 11 have drifted.** The
64 are harmless — same bytes, so a line number resolves the same way in either tree. **The
entire hazard is the 11**, and it is concentrated in exactly the files this audit kept citing:

```
dotnet/src/LegoCatalog.App/Program.cs                          117 -> 148
dotnet/src/LegoCatalog.App/Configuration/CatalogRuntimeOptions.cs   187 -> 271
java/.../config/CatalogRuntimeOptions.java                     141 -> 284
java/.../config/TomcatPathConfiguration.java                    22 -> 22
java/.../PostgreSqlIntegrationTest.java                        345 -> 347   [see note]
```

**Note, because this one line is rev-sensitive and the rest are not.**
`PostgreSqlIntegrationTest.java` reads **340 -> 342** at the `4bf59f7` baseline *and* at
`origin/rewrite-integration`, and **345 -> 347** here. The +5 in each tree is `0879b2f`, the
`@Testcontainers(disabledWithoutDocker = true)` fix, which is on this branch and not in the
shipping branch's tree. **A reader measuring at baseline will get different numbers and
should not read that as an error.** The drift *delta* is +2 at every revision, so the finding
is stable even though the pair is not — which is the general shape: **quote the delta when
the claim is about drift, and the absolute pair only with the rev that produced it.**

`TomcatPathConfiguration.java` is the case worth naming: **it drifts at an identical line
count.** Even a reader who thinks to sanity-check the file length gets a match. The single
differing line is an `import`.

**Reconciliation, so this count is not later quoted against the runbook's.** The Java runbook
says `java/` and `solutions/reference/java/` "differ only in the nine files the modernization
path edits". **That is exact** — `diff -rq java solutions/reference/java` reports **9**
differing files, plus 5 present only in the reference (`Dockerfile`, `ImageStore.java`,
`AzureBlobImageStore.java`, `AzureConfigurationTest.java`, the `service` test package) and 1
only in `java/` (`target/`, untracked build output). The **11** above is a different
population: *both* stacks, tracked `.cs`/`.java` only, so it excludes `README.md`, `pom.xml`
and `application.properties` and includes the .NET side. Two correct numbers over two
populations — the same trap as the `:86` disagreement, caught this time by measuring both at
one revision before writing either down.

And that import is what turns an addressing nuisance into a substantive finding.

### The reference tree is across a major-version fork the rewrite path never crosses

The drifted imports are not edits. They are **Spring Boot 4 package relocations**:

| | `java/` | `solutions/reference/java/` |
|---|---|---|
| `spring-boot-starter-parent` | **3.5.16** | **4.0.7** |
| `java.version` / `maven.compiler.release` | **17** | **21** |
| Tomcat factory import | `…boot.web.embedded.tomcat` | `…boot.tomcat.servlet` |
| MockMvc autoconfigure | `…boot.test.autoconfigure.web.servlet` | `…boot.webmvc.test.autoconfigure` |
| `TestRestTemplate` | `…boot.test.web.client` | `…boot.resttestclient` |
| Dockerfile base | *(authored by participant)* | `openjdk/jdk:21-azurelinux`, digest-pinned |

**This fork is contracted, not accidental.** `workshop/toolchain.lock.json` declares
`sourceRuntime 17.0.20+8` / `sourceSpringBoot 3.5.16` and `targetRuntime 21.0.12` /
`targetSpringBoot 4.0.7`. The reference tree is the *target* state, and the modernization
tracks are supposed to arrive there. Nothing is wrong with the reference existing.

**What is wrong is that it is unreachable and unmarked from where this path stands.**
`challenge-paths.json` binds `copilot-rewrite-java` to `sourcePath: "java"` and declares **no
target runtime at all**. So the rewrite participant stays on 17/3.5 for the whole exercise —
correctly, and this arm reached the frozen surface that way. But the JDK the lock ships an
installer for cannot even *parse* the reference:

```
$ javac --release 21 …   # on the pinned Microsoft OpenJDK 17.0.20+8
error: release version 21 not supported          → exit 2
$ javac --release 17 …   # positive control
                                                  → exit 0
```

So a rewrite participant who does the most natural thing available to them — open
`solutions/reference/java/` to see what "finished" looks like — gets a tree that is
~~path-identical for 75 files, byte-identical for 64 of them~~ **path-identical for 54
files, byte-identical for 45 of them, and will not build on their machine.** Nothing in
the rewrite guidance says the reference is a different major version. The failure
surfaces as import errors in files whose paths they recognise.

> **Corrected against the original figure, which reproduces nowhere.** `54 / 45` is
> `git ls-tree -r` over `solutions/reference/java` against `java`, blob-hash compared,
> and it is stable at `4bf59f7` **and** at this arm's HEAD. The struck `75 / 64` was
> published without a ref or a command and could not be reproduced at either ref or
> under any other comparison scope tried (`solutions/reference` whole, and the rewrite
> track's own `java/` copy, both of which share only 1 path). Because it was published
> bare, **there is no way to tell whether it was drift, a different instrument, or an
> error** — which is this document's own rule about bare figures, arriving against this
> document. The direction of the finding is unchanged: 54 of the 54 files under `java/`
> are path-shared with the reference, so a participant still recognises essentially the
> whole tree. The magnitude was overstated by roughly two fifths.

**The installer asymmetry is the aggravator, and it is workshop-wide rather than Java-only.**
The lock carries ~~five installer keys~~ **eleven Windows-bound acquisitions** — nine artifacts whose
URL is a `.msi`, `.exe`, a `winget` reference or a `win32` channel, plus two components acquired by a
string naming the Windows installer:

```
runtimes.dotnet · runtimes.java                        source-runtime installers, x64
databases.sqlserver.windowsService · .client           server .exe and go-sqlcmd .msi
databases.postgresql.windowsService                    server .exe
tools.azureCli · tools.git · tools.jq · tools.vscode   no platforms array at all
databases.postgresql.client · .migrationTools          source = "bundled-with-postgresql-installer"
```

There are **zero** target-runtime installers (verified across the 772 files git tracks: the string `targetRuntimeInstaller` has
1 occurrence, which is this sentence quoting it, and 0 in the material;
CONTROL-POS the sibling term `installer` matches 15 tracked files). Both stacks contract a target runtime (.NET 8→10, Java 17→21) that has **no
pinned, hash-verified acquisition path**, while every JAR, NuGet package, Maven distribution and
database image in the same file is pinned by hash or signature — counted as exact JSON keys:
**19 `sha256`, 5 `sha512`, 6 `digest`, 6 `signature`**, plus 10 `signaturePublisher` Authenticode
assertions.

> **Corrected upward from five, and the reason matters more than the number.** Five is the count of
> JSON nodes *named* `installer`; eleven is the count of *artifacts bound to Windows*. Six components
> — `azureCli`, `git`, `jq`, `vscode` and both PostgreSQL client entries — carry no key called
> `installer` anywhere, so **no name-keyed count at any sensitivity could reach them.** The population
> is defined by the artifact's platform and the original figure selected by key name. Recorded because
> an earlier revision of this section had already been corrected once along that same wrong axis.

**The container digests do not close the gap, and only one of the five closes at all.** It is natural
to answer this with *"the databases ship container images, so non-Windows hosts are covered."* Measured:

```
sqlserver.localContainer   platforms [linux/amd64]              indexDigest == the amd64 digest
postgresql.localContainer  platforms [linux/amd64, linux/arm64] indexDigest == neither
```

A genuine multi-platform index **never equals any of its platform digests — it is a list of them**, so
the SQL Server entry is a single-platform pin carrying an index-shaped key name, and on `arm64` there
is no pinned SQL Server digest at all. The two client entries fail on the lock's own prose:
`sqlserver.client.installer` is a go-sqlcmd `.msi` that is a *sibling* of `localContainer` rather than
inside it, and both PostgreSQL client components declare `bundled-with-postgresql-installer`. **The
file models client tooling as acquired from the Windows installer, never from the container.** Coverage
is **1 of 5 fully, 1 partially (amd64 only), 3 not at all** — a sibling key is not a substitute path.

**And the one cross-platform pin is a gap in the opposite direction.** `tools.terraform.platforms` is
`darwin/arm64` and `darwin/amd64` — **Darwin only, with no Windows entry** — while `ch01/README.md:26`
mandates a Windows VM with the source tree at `C:\MicroHack\source`. The single component pinned for a
non-Windows host is pinned *exclusively* for non-Windows hosts. **Any reading of platform coverage that
counts the array's length rather than its contents gets this backwards in both directions at once.**

**A positive result, recorded because an audit that reports only defects is not a measurement.**
`baseInfra/terraform/README.md` makes a universal claim — *"Every tool/database installer is the
exact URL from `workshop/toolchain.lock.json`, with digest verification and Authenticode publisher
verification where the lock declares a publisher."* Tested by walking the parsed lock for every
object carrying a `url` key and checking each for a sibling integrity key: **15 objects carry a
URL, 15 have integrity, zero are bare.** The claim holds, and its hedge — *where the lock declares
a publisher* — is exactly the right one, since only 6 objects declare `signature`. This is the
strongest universal assertion the material makes about the lock and it survives contact with it.

*(An earlier revision of this paragraph said "exactly two installer entries" and gave the
integrity figures as 27 / 5 / 6 / 16. Both were instrument defects. The installer `grep` for
`"[a-zA-Z]*Installer"` piped through `sort -u` requires a capital `I`, so it never matched the
three keys named literally `installer`, then deduplicated by key name rather than path,
collapsing three distinct `databases.*.installer` entries into one. Worse, the four integrity
figures came from **three different instruments**: 27 is raw string occurrences of `sha256`,
which counts the `sha256:` prefix inside every digest **value**; 6 is exact keys named `digest`;
16 is key names *containing* `signature`, i.e. 6 `signature` plus 10 `signaturePublisher`. Only
`sha512` was instrument-independent at 5 — and that agreement is exactly what made the list look
homogeneous. **A single token on which every instrument agrees is a false control.** All figures
above are now one instrument: occurrences of an exactly-named key in the parsed JSON.)*

**Correction to an earlier draft of this section, because the causal claim was wrong.** This
document previously called that target gap "the direct cause" of the hand-rolled JDK install
behind `docs/CommonErrors.md` entry 101. It is not. The JDK installed by hand here is
**`17.0.20+8` — the `sourceRuntime`**, which *does* have a pinned installer entry. That entry
is **Windows-only**, and this host is macOS. **The platform axis is what bit; the target axis
never applied**, and the paragraphs above say why in advance: `challenge-paths.json` binds
`copilot-rewrite-java` to `sourcePath` with no target runtime, so this path never crosses to
the target at all. **The finding two paragraphs up refutes the causal claim two paragraphs
down** — written in one sitting, by one author, in one file.

**And the platform gap is stronger than an omission, because macOS is a declared host.** The
lock's own `hosts` block contracts two of them:

| | `coordinator` | `workshopVm` |
|---|---|---|
| OS | **macOS ≥ 13.0**, arm64 + x86_64 | Windows Server 2025 Datacenter |
| Docker | **pinned** — Desktop 4.37.1, Engine 27.4.0 | **none pinned** |
| *runtime* installers | **zero** | 2, both `windowsSource…` |

So macOS is not an unsupported platform whose absence is out of contract — **it is a
first-class host that the same file provisions carefully enough to pin a Docker engine for,
and then ships no runtime installer for.** That is an internal inconsistency within one
document, not a gap at its edge. Measured on this machine: `sw_vers` 26.6.2 arm64, Docker
Engine **27.4.0** — matching `hosts.coordinator.dockerEngineVersion` exactly.

**Resist the tempting stronger version of this claim, because the same file refutes it.**
"All five installers are Windows" invites the reading that the lock is simply a Windows
artifact. An earlier revision of this paragraph answered that with *"cross-platform acquisition
is solved twice, for a tool and for a database"* — citing `tools.terraform.platforms` and
`databases.postgresql.localContainer.platforms`. **The Terraform half of that was wrong.** Its
platforms are `darwin/arm64` and `darwin/amd64`: two *architectures* of one OS family, macOS
only, with no Windows entry at all. That is cross-**architecture**, not cross-platform, and the
evidence was in the output I read when I wrote it.

**The database half stands, and it is the whole contrast.** Both databases genuinely span two OS
families — a Windows `installer` under `windowsService` *and* a Linux `localContainer` image
(`sqlserver` `linux/amd64`; `postgresql` `linux/amd64` **and** `linux/arm64`). Two acquisition
routes, two OS families, both pinned. The runtimes have one route and one family.

**The `linux/arm64` digest is the load-bearing detail.** An `arm64` image can only serve an
`arm64` host, and the only host in the file declaring `arm64` is `hosts.coordinator` — this
machine. `hosts.workshopVm` declares `architecture: "x64"`, so it is not merely unstated as
`arm64`; it is **explicitly excluded** from it. So the lock does not merely tolerate this host; it
**provisions the application's database to run on it**, at a pinned digest, and that is the route
this walkthrough actually used. What it does not provision for the same host is a runtime to build
the application that would talk to that database.

An earlier revision of this paragraph said `workshopVm` *"declares no `architectures` key at all"*.
That was literally true and materially wrong: the key is spelled `architecture`, singular. **12
objects in this lock use the singular form; exactly one — `hosts.coordinator` — uses the plural
`architectures`,** because it is the only one with more than one value. The two forms also carry
different vocabularies for the same architecture: the 12 singular values are all `x64`, and the
sole plural list says `x86_64`. `tools.uv` holds both spellings in one object, `architecture:
"x64"` beside a URL named `uv-x86_64-pc-windows-msvc.zip`. Nothing reconciles them — the frozen
suite pins the majority form (`tools.git.architecture == "x64"`) and **never reads
`hosts.coordinator` at all**, so the outlier is unguarded by construction.

| | routes | OS families | serves the coordinator |
|---|---|---|---|
| `databases.postgresql` | installer + container | Windows + Linux | **yes** — `linux/arm64` |
| `databases.sqlserver` | installer + container | Windows + Linux | no — `linux/amd64` only |
| `tools.terraform` | download | **macOS only** | yes |
| `runtimes.dotnet` / `runtimes.java` | installer | Windows only | **no** |

So the inconsistency is not "macOS is unsupported" and not "nothing is cross-platform". It is
narrower and harder to answer: **the file expects this host to run the database and gives it no
way to build the application.**

**That same block also predicts the Testcontainers asymmetry this delivery treated as an
anomaly.** `coordinator` pins a Docker engine; `workshopVm` pins none. `PostgreSqlIntegrationTest`
passing on this host and being excluded on the VM is therefore **contracted behaviour, not an
environment surprise** — the runbook's "six skipped is the correct VM result" is consistent
with the lock, and the lock said so first. The workshop prose discusses the asymmetry as
something to warn about; the lock already encodes it.

**Answering the question this arm was set:** *does the rewrite guidance reach the same frozen
contract surface as modernization, or quietly assume divergence?* It reaches it — 14/14
frozen contract tests and 639/1 acceptance at `68ef499` (612/1 when this was written), all on
JDK 17. **But not via the reference.** The
guidance does not assume divergence; it is **silent about a divergence already present in the
tree**, and the silence is maximally plausible because the two trees share their paths, their
class names, and most of their bytes. That is this delivery's recurring defect in its most
literal form yet: *two artefacts carry the identifier, only one is the one you opened* — here
not two files, but two entire trees.

**Remedy, and it is documentation-cheap:** state in the rewrite runbook that
`solutions/reference/` is the **post-modernization** target state on Spring Boot 4 / Java 21
and is not buildable with the pinned source JDK. One sentence. The alternative — a reader
discovering it from a relocated `import` — costs an hour and looks like their own mistake.

**Consequences, in order of how much they cost:**

1. **A line number is not an address in this repo; a path plus a line number is.** Any finding
   in this audit citing `Program.cs:NN` without its tree is ambiguous, and the ambiguity is
   invisible because both resolutions look correct.
2. **Two parties can verify contradictory claims and both be right**, which reads as one of
   them being careless and is neither. That happened here at the very end, after both sides
   had adopted every guard in this document.
3. It is the same defect as everything else in this record — **two artefacts carry the
   identifier, only one is the one you opened** — but with the operand hidden inside a number
   rather than a name, so none of the earlier guards fire on it.

**The guard that would have caught it** is the cheapest yet and belongs with the rest: when a
citation is disputed, `git ls-tree -r --name-only <rev> | grep '<basename>$'` **before**
re-reading the line. If the file has two homes, the disagreement is about addressing and not
about content — and no amount of re-reading either copy will surface that.

**And this document was carrying an instance of it.** Sweeping every line citation here
against the duplicated basenames turned up two *adjacent bullets* in the telemetry section
that resolved to different trees: `CatalogApplication.java:33` was the `java/` copy (the
reference's line 33 is blank), while `Program.cs:80` was the **`solutions/reference/`** copy —
in `dotnet/` that same statement is `:64`, and `:80` there is an unrelated lambda. Both
citations were correct; the pair was incoherent, and nothing in either one showed it. Fixed
by prefixing the tree. Worth stating plainly: **I wrote the section describing this hazard
and had already committed two instances of it in the same file**, which is the same result as
every other finding here — naming a defect does not confer immunity from it, and only the
mechanical sweep found them.

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
`AddSqlClientInstrumentation()` (`dotnet/src/LegoCatalog.App/Program.cs:86`; the same call is
`:107` in the `solutions/reference/` copy — see the duplicate-tree note below), so every
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
(`java/…/web/HealthController.java:25,30`) and so set Spring's `BEST_MATCHING_PATTERN`. But it does
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
  (`config/CatalogResourceIdentity.java:20` — same line in both trees — applied at
  `java/…/CatalogApplication.java:33`).
* .NET sets it inside `ConfigureResource(...).AddAttributes(...)`
  (`dotnet/src/LegoCatalog.App/Program.cs:64`; the same statement is `:80` in the
  `solutions/reference/` copy).
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
still emitted as a resource attribute only (`java/…/config/CatalogResourceIdentity.java:20` at
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
