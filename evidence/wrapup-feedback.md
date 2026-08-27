# Wrap-up — attendee feedback (the honest scorecard test)

**Attendee run:** worktree `michalmar-ch07-and-wrapup`. 2026-08-27 CEST.
**Method:** attempt the scorecard from the evidence that *genuinely exists* across all
worktrees, and observe empirically what the wrap-up tooling does with the missing rows.

> **UPDATE (21:45 CEST) — real delivery outcome folded in.** The facilitator delivery log
> plus my own read-only `az` verification now show **.NET completed the central challenge**
> and **Java is live-but-empty**. The candidate scorecard is
> [`candidate-scorecard.md`](candidate-scorecard.md). This changes rows 9–10 for the .NET arm
> from *design* to *real deployed outcome*; rows 1–8 remain *not measured* because no
> Ch2–Ch6 evidence files exist anywhere. See "Real delivery outcome" below.

## Real delivery outcome (verified where I could)

- **.NET / Azure SQL — complete.** `ca-mh-user001-dotnet`, active revision `--0000001`,
  digest `sha256:647e2500…` (**`az`-verified**). The ACR tag on that digest is
  `47acf263d3320fa3bb41d5469fc3c7428a393fca` — a modernized pushed commit **distinct** from
  the baseline `4bf59f7e…` (F-29), so the image is genuinely modernized, not a rebuilt
  baseline. 198/20 migrated, `topologyValidated: true`, first 2xx `2026-08-27T19:21:21.921Z`
  (**facilitator-attested**). I could not corroborate live serving from my host (`/readyz` →
  `000`, likely scaled-to-zero or no egress).
- **Java / PostgreSQL — partial.** Live but **empty catalog**, blocked on a migration
  verification failure. Deploy milestone reached, data-migration milestone not.
- **Honest headline: one of two stacks completed the workshop's central challenge.** Not
  rounded up.

Two honest sibling artifacts corroborate the "not measured" rows rather than contradict them:
`michalmar-cautious-disco/evidence/ch06-mttr.BLOCKED.md` ("cannot be produced honestly, no
file written") and `michalmar-psychic-memory/evidence/cicd/identity-summary.json` (self-labels
"NOT a cicd-report.json — no workflow run occurred"). Multiple attendees independently chose
the blocked-but-honest path over a fabricated number. That is the workshop's honesty culture
working — but note it works because of *attendee* discipline, not because of any check.

## The single most important finding

**There is no wrap-up tooling.** The wrap-up scorecard is a Markdown table the attendee
**copies and fills in by hand** (`challenges/wrapup/README.md:27` — "Copy this table and
complete it from your own evidence"). Nothing reads a filled scorecard; nothing validates
that a cell's number came from a real measurement; nothing marks a row missing. I searched
the entire `tests/`, `workshop/`, `docs/`, and `challenges/` tree:

```
grep -rn "ch00-pain|minutesToRecovery|catalogMedianMs|scorecard" --include=*.py --include=*.sh
# → no script reads the real evidence/ch00-pain-<stack>.json at all
```

So the honest answer to *"does it tell you it is partial, or render a confident-looking
scorecard with silent gaps?"* is: **it does neither automatically — it produces exactly
what the human types, and there is no mechanism that could flag a gap.** The only thing that
*renders* a scorecard is a `jq` snippet in `docs/Demo.md` (the facilitator sales script),
and that is worse, not better — see the next finding.

## Empirical demonstration: confident, green, unmeasured

`docs/Demo.md` is the **facilitator sales script**, a *separate* artifact from the attendee
scorecard — but it is the one place anything mechanically renders scorecard numbers, so it is
worth testing. Its step 6 renders from `evidence/ch00-pain-dotnet.json` and
`evidence/ch06-mttr.json`. Those files **do not exist in any evidence directory** — but the
identically-named **fixtures** ship in `workshop/contracts/fixtures/wrapup/`, and Demo.md's
own honesty table (line 37) says step 6 runs "**from the checked-in example**." I copied the
fixtures into an `evidence/` dir and ran the snippet:

```
catalog median, legacy : 412.7 ms on 1 instance, autoscale false
manual deploy steps    : 14
minutes to recovery    : 13 min
```

Every one of those numbers is a **fixture constant that no one measured**. The command
prints them with total confidence and zero provenance warning. An attendee who `cp`s the
fixture into `evidence/` (a one-line, natural move when the real file is absent) ships a
green scorecard built entirely on fiction, and the acceptance suite stays fully green
because the only guard —
`test_contract_assets.py::test_demo_steps_claimed_cold_runnable_have_a_checked_in_fixture`
— asserts the demo's printed numbers **match the fixture**, i.e. it guards that the fiction
is self-consistent, not that it is true.

## How much of the wrap-up's authority rests on fiction-indistinguishable evidence?

Of the 11 scorecard rows, I could bind only **3** to evidence that genuinely exists, and
even those needed a caveat:

| # | Row | Bindable from real evidence? | Why |
| --- | --- | --- | --- |
| 1 | Catalog response, median | **No** | needs `ch00-pain` (VM, never run here) + `evidence/load/raw/test-run.json` (Ch2, absent) |
| 2 | Pipeline lead time | **No** | needs `ch00-pain` + `evidence/cicd-report.json` (Ch3, absent) |
| 3 | Human steps to ship a fix | **No** | same two files, absent |
| 4 | Rollback time | **No** | needs `evidence/cicd-report.json`, absent |
| 5 | Behaviour under load | **No** | needs `evidence/load-test-report.json` (Ch2, absent) |
| 6 | Time to answer "why slow?" | **No** | needs Ch4 clock readings, never taken |
| 7 | MTTR | **No** | needs `evidence/ch06-mttr.json` (Ch6, absent) |
| 8 | Security posture | **No** | needs `evidence/defender-report.json` (Ch5, absent) |
| 9 | Secrets in application config | **Partial** | legacy fact is baked into the fixed Ch0 scenario (`C:\MicroHack\secrets\<stack>.json` holds a credential — `ch00/README.md:130,156`); "after" is a Ch1 design outcome, not measured here |
| 10 | Patching the host | **Partial** | Ch0 scenario states app + DB on one VM (`ch00/README.md:150`); "after" = managed PaaS, design outcome |
| 11 | Cost to run, per day | **Yes** | fully static: `docs/CostEstimate.md` → legacy **$5.13**, Java/PostgreSQL **$2.56**, .NET/Azure SQL **$6.67** |

**8 of 11 rows are "not measured"** for every non-deploying arm, exactly as the independent
observer found. And rows 9–10 are only "partial" because their legacy facts are **fixed
scenario constants**, not something this arm produced — the file they formally cite
(`evidence/ch00-pain-<stack>.json`) does not exist here or in any sibling worktree. Row 11
is the one honest row that needed **no measurement at all**.

So: **~73% of the scorecard (8/11) cannot be filled truthfully from what exists, and the two
"partial" rows lean on fixed scenario text rather than measured evidence. Only the cost row
is both fillable and provenance-clean — and it is the one row the chapter itself flags as an
estimate, not a measurement.** The wrap-up's persuasive power rests almost entirely on
evidence that, per the fixture round-trip and the `st_size > 0` `pathEvidence` checks
(`handoff.py:1120`), cannot be distinguished from fiction.

## The honest scorecard I can actually stand behind

| What you measured | Legacy baseline | After modernization | Provenance |
| --- | --- | --- | --- |
| Catalog response, median | *not measured* | *not measured* | Ch0 VM baseline never captured by this arm; Ch2 load run never produced |
| Pipeline lead time | *not measured* | *not measured* | no `cicd-report.json` |
| Human steps to ship a fix | *not measured* | *not measured* | no `cicd-report.json` |
| Rollback time | *not measured* | *not measured* | no `cicd-report.json` |
| Behaviour under load | *not measured* | *not measured* | no `load-test-report.json` |
| Time to answer "why slow?" | *not measured* | *not measured* | Ch4 not run |
| MTTR | *not measured* | *not measured* | no `ch06-mttr.json` |
| Security posture | *not assessed* (Ch0 ran none) | *not measured* | no `defender-report.json` |
| Secrets in config | credential in `C:\MicroHack\secrets\<stack>.json` (Ch0 scenario) | Key Vault ref + managed identity — **design only**, not deployed | `ch00/README.md:130,156`; `ch07-extension/enterprise-identity-secrets.md` |
| Patching the host | app + DB on one Windows VM (Ch0 scenario) | managed PaaS (Container Apps + Flexible Server), no host to patch | `ch00/README.md:150` |
| Cost to run, per day | **$5.13** | **$2.56** (Java/PostgreSQL) / **$6.67** (.NET/Azure SQL) | `docs/CostEstimate.md:198-200` |

This version *tells you it is partial* — because I made it. The workshop does not force that
honesty; a less scrupulous attendee produces the confident version above and nothing stops
them.

## A speedup claim: the material does NOT invite one (correcting my own brief)

My briefing warned the wrap-up "may invite a Copilot-made-this-N×-faster claim." **I checked
and that is not true — reporting it would be a fabricated finding.** Grepping
`challenges/` and `solutions/` for `speedup|N× |[0-9]+x faster|orders of magnitude|reduced
by|times faster` returns **zero hits**. The wrap-up, `ch07-enterprise`, and `ch07-innovation`
contain no speedup framing whatsoever. The single cost comparison in the whole workshop
(`docs/CostEstimate.md:206`) is a cost *increase* (+30% on .NET/Azure SQL), written directly
**against** the reflexive "modernization = cheaper/faster" narrative, and both scorecard
rows that could be turned into ratios are disclaimed at `wrapup:49-56` as not like-for-like.
The material is, if anything, unusually disciplined about *not* inviting the claim.

What remains true is a **delivery-design limitation of this run** (not a material defect):
*if* someone at the table reaches for a manual-vs-Copilot ratio anyway, this delivery cannot
supply an honest one. Both manual control arms ran with the finished reference
implementation (`solutions/reference/`) and completed runbooks present in the same checkout —
a control that can read the answer is not a control — and both completed **locally only, no
Azure deploy** (`manual-dotnet-control-feedback.md`, `manual-java-control-feedback.md`), with
`runtime-test-report.json` pinned to `sourceCommit
4bf59f7ee8dae11259d73ba5a5d7cb0e3355c4af`, the immutable F-29 baseline — i.e. the "control"
never modernized anything. So any ratio would compare a primed, non-deploying run against a
deploying one on non-equivalent end states. That is a limitation of how the day was run, and
it is on the delivery, not on the chapter.

## The facilitator's three questions, answered

**Q1 — what makes an attendee *want* to write "not measured", and is the encouragement
strong enough and well-placed?** The permission exists but is **weak and mis-scoped**. It
lives at `wrapup:22-23`, and read in context it is *conditional on the golden-handoff case*:
"If your facilitator gave you a golden handoff partway through, use the numbers from the
chapters you completed yourself and mark the rest as *not measured*." An attendee like me —
who received **no** golden handoff but simply lacks evidence because the deploy path was
blocked — is not obviously covered by that sentence, and it sits under "Before you start,"
*above* the table, where a hurrying attendee has not yet hit the empty cells. By the time
they are staring at a blank "median" cell, the nearest text is the scorecard's confident
"the two days were spent producing exactly these numbers" (`:28`), which pushes *toward*
filling, not abstaining. **Recommendation:** move an unconditional "any row you did not
personally measure is *not measured* — an honest gap beats a plausible guess" line into the
table's immediate preamble, not the golden-handoff aside.

**Q2 — I am the natural experiment; does the honest result still read as a credible
outcome?** I filled it honestly: **8 of 11 rows are "not measured", 2 are partial (from fixed
scenario facts), 1 is real (cost).** The observer's independent "3 of 11" count matches mine
exactly. The resulting document reads as **obviously incomplete, and that is the correct and
valuable outcome** — it looks like what it is: a track that designed but did not deploy. It
does **not** read as a credible before/after business case, and it should not, because one
was not earned. The important corollary: an honest partial scorecard is *visibly* thin, so
the danger is not that honesty looks bad — it is that **a dishonest full scorecard looks
better than an honest partial one**, and nothing but a human reviewer can tell them apart.

**Q3 — would a validator even help, or does a reflective deliverable belong outside
automation?** Both, split by layer. The *numbers* should be machine-bound and are not: a row
that cites `evidence/cicd-report.json → .traffic.safety.rollbackCompletedAt` is a mechanical
extraction a validator could enforce (file present, field present, value transcribed) — and
because it isn't enforced, a hand-typed wrong value is invisible. That half **should** be
automated, and the fixtures/`pathEvidence` gaps (W-2) are exactly where the absence bites.
The *reflection* — the Discuss questions, "what is still manual", "which number would
persuade your organization" — is properly human and should stay outside automation; a
validator there would measure compliance, not thought. **The failure is that the chapter
mixes the two and validates neither**: it presents mechanically-derivable numbers as if they
were reflective judgement, inheriting the un-checkability of the second while losing the
enforceability of the first.

## Credit where it is due

The wrap-up author was unusually careful, and it deserves saying. `:49-69` explicitly
caveats four rows most self-measuring workshops would quietly inflate: catalog response as
*not like-for-like* (loopback vs 40 concurrent users over HTTPS), pipeline lead time as
`workflow_dispatch`-anchored rather than DORA lead-time, security posture as *deliberately
not a count* ("a headline number here would reward whoever started from the worst
baseline"), and — best of all — cost as **+30% higher on .NET/Azure SQL being the expected
outcome, not a failed migration** (`:62-69`). That paragraph argues *against* the workshop's
own success narrative, which is precisely the spot where workshops usually cheat. It is
genuinely good, honest technical writing and it is the reason the *prose* of this chapter
can be trusted even though its *mechanics* cannot.

## Instruction clarity (the chapter itself is good)

Credit where due: `challenges/wrapup/README.md` is honest *in prose*. It names four rows
that need caveats (catalog response measured two different ways; pipeline lead time is not
DORA lead time; security posture is deliberately not a count; cost is an estimate that moves
+30% on .NET and says so). The problem is not the writing — it is that **the honesty lives
in prose the attendee may skip, while the mechanics (copy a table, or `cp` a fixture) make
the dishonest path the path of least resistance.** The chapter asks for integrity it has no
way to check.

## Defects / observations

- **W-1:** No scorecard renderer or validator exists; the only automated render
  (`docs/Demo.md` `jq`) sources unmeasured fixtures and prints them as results.
- **W-2:** Fixtures `ch00-pain-dotnet.json` / `ch06-mttr.json` are validated only by
  round-trip against themselves (`test_contract_assets.py:2815-2825`); copy-and-edit is
  undetectable. The 10+ `pathEvidence` markdowns are validated at
  `handoff.py:1107-1121` on exactly three properties — **exists, is not a symlink, size > 0.
  One byte passes.** Content is never inspected.
- **W-3:** `-k "ch07 or wrapup"` selects 0 tests — the wrap-up has no acceptance coverage of
  its own output, only of its *assets*.
- **W-4:** The wrap-up's own "Facilitators" step tells the room to read out the median
  `minutesToRecovery` across teams. In this delivery that field exists in **zero** real
  evidence files and **one** fixture (13). A facilitator following the instruction literally
  would read out either "no data" or the fixture constant.

## Verdict

The wrap-up is where the workshop's "confident, green, wrong" failure mode peaks, because it
is the one deliverable with **no validator and the strongest incentive to look finished**.
The chapter's prose is admirably honest; its mechanics do nothing to enforce that honesty,
and a shipped fixture sits one `cp` away from a fabricated-but-green scorecard. Held the
line: every number above is either real (cost, scenario facts) or explicitly *not measured*.
Nothing was invented.

## Defect taxonomy (adopting the observer's classes — more useful than a flat list)

The wrap-up should teach the room *why* the defects clustered, not just enumerate them. Three
classes explain most of them:

1. **Topology-dependent silent-wrong, with green control-plane probes.** The artifact ships
   correct against Microsoft's permissive default subscription and silently wrong against a
   tenant-governed one — and the control-plane check *passes* while the data plane fails.
   Confirmed instances I touched or verified: public IP assumed (tenant policy forbids them,
   F-47); public DNS assumed (internal-only Container Apps env has none); a Blob role granted
   to `principalType: 'User'` that the automation VM identity can never be; Windows `PATHEXT`
   (`shutil.which('az')` succeeds while `subprocess.run(['az'])` fails); interactive
   `Read-Host -AsSecureString` under `az vm run-command` (F-58). Common property: **invisible
   until an actor in the real delivery topology used the artifact for its stated purpose.**
   The scorecard inherits this directly — my `az` reads confirmed the .NET *control plane*
   (revision, digest, ingress) while I could not confirm the *data plane* (serving) from my
   host. A scorecard row filled from a control-plane probe alone would read green and be
   unsupported.
2. **Diagnosability defects.** A failure message that names a set difference without emitting
   the difference. One such message hid another real defect for ~an hour. This class is
   *compounding* — it multiplies the time cost of every defect it wraps. W-4 is a wrap-up
   instance in miniature: "read out the median MTTR" with no data emits silence, not an error.
3. **Silent preservation under rollback.** A constraint whose failure path preserves the very
   object it exists to remove — e.g. the identity cutover wrapping `DROP USER` +
   `CREATE USER … FROM EXTERNAL PROVIDER` in one `XACT_ABORT ON` transaction, so a failed
   create rolls back the drop and the privileged legacy principal *survives* the security
   step, exit code reading "nothing happened." The scorecard analogue: a copied fixture
   (W-2) preserves an unmeasured number behind a green round-trip test.

## Process observations worth a slide

- **~68 defects in one delivery, a large fraction environmental not code** — the workshop was
  authored against a permissive default subscription and delivered into a governed one. This
  is the single most important thing to tell a room: most of what broke was the gap between
  *authoring topology* and *delivery topology*, not bugs in anyone's code.
- **Four facilitator false alarms, all the same shape:** applying a mechanism without applying
  the paired check. Three more were caught before firing. Worth telling the room because it is
  what happens to *anyone* working at speed — not a personal failing. It is, in fact, the same
  root cause as defect-class 1: a control-plane action without its data-plane verification.
- **Screenshots may be unobtainable in this topology.** Headless Edge on Windows Server as
  SYSTEM exits 1002 (`INVALID_SANDBOX_STATE`) even for `about:blank`, and Edge refuses
  `--no-sandbox` when elevated. If a screenshot can't be had, the honest finding is "browser
  screenshots are not obtainable in this delivery topology" — not a fabricated image. This is
  itself a scorecard-integrity point: any row whose evidence is a screenshot is unfillable
  here, and the honest response is *not measured*, not a stock image.

## Whole-workshop feedback (pacing, coherence, two-day realism)

- **Does it build coherently? Mostly yes, in intent.** Ch0 (pain) → Ch1 (lift + migrate) →
  Ch2–6 (measure the improvement) → Ch7 (extend) → wrap-up (score it) is a genuinely good
  arc, and the scorecard is a smart spine because every earlier chapter is supposed to emit
  one row. The design is better than most workshops.
- **But the arc is fragile: it is a chain, and Ch1 is a single point of failure for eight of
  eleven rows.** Every measurement chapter (Ch2–6) presupposes a deployed, migrated app. In
  this delivery only **.NET** reached that state; Java stalled at data migration; the four
  non-deploying arms never had an app to measure. So the scorecard's 8 measurement rows are
  gated on one milestone that half the tracks did not clear. A workshop whose final deliverable
  is 8/11 blank unless one specific early step fully succeeds is **too tightly coupled for a
  time-boxed event**. Consider making Ch2–6 independently reachable against a pre-seeded
  reference deployment, so a team that loses a day to Ch1 can still measure something.
- **Two-day framing is not realistic as delivered.** ~68 defects surfaced in one delivery,
  most environmental. An attendee hitting even a quarter of those spends the workshop
  debugging topology, not modernizing an app. The two-day estimate assumes the authoring
  subscription; in a governed tenant, budget for Ch1 alone to consume most of day one.
- **Does the wrap-up material match the workshop a real attendee experiences? Partly — and
  this is the sharpest gap.** The wrap-up *prose* is honest and even anticipates a mostly-empty
  scorecard (it authorises "not measured" and disclaims the ratios). But it is **written as if
  the measurement chapters ran**: it asks the room to read out a median MTTR, compare pipeline
  lead times, etc. For the delivery that actually happened, most of those prompts have no
  input. The wrap-up would match reality better if it opened by acknowledging that **a partial
  scorecard is the *expected* outcome of a governed-tenant delivery**, and treated 8/11 blank
  as a successful honest result rather than an incomplete one.
- **On the "Copilot made it N× faster" temptation:** the material does **not** invite it
  (grep-verified zero hits; the only cost row is a disclaimed +30% *increase*). If anyone
  reaches for such a ratio anyway, this delivery cannot supply one — the control arms had the
  finished runbook and the reference implementation, so they were not controls. That is a
  **delivery-design limitation (the facilitator's), not a material defect.** Credit to the
  wrap-up author: `:49-69` pre-empts exactly this by disclaiming both would-be ratios as not
  like-for-like and framing the cost increase as expected. That paragraph is the best writing
  in the chapter and should be held up as the model for how a self-measuring workshop avoids
  cheating.

## Verdict on the wrap-up as the workshop's closer

It is the right closing instrument and it is honestly written, but it measures the wrong
thing: it weights eight rows on peripheral measurement chapters that a governed-tenant
delivery rarely completes, while the **actual central achievement — deploy + migrate + verify,
which .NET genuinely reached — is not a scorecard row at all.** The most valuable change is to
make the scorecard reward the central milestone explicitly and to state up front that a mostly
"not measured" card is the honest, expected shape of this delivery — so the honest attendee's
card and the careless one's remain distinguishable *by design intent*, even though no
validator will ever tell them apart.
