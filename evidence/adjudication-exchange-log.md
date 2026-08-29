# Adjudication exchange log - Java rewrite arm

## What this is, and what it is not

This is **one party's received copy** of the cross-session adjudication that produced the findings
recorded in `docs/CommonErrors.md`. It exists because that adjudication was, until this commit,
carried entirely by a channel that is unsearchable, unversioned and preserved by nothing.

Measured before writing it, at `163105b`:

```
attributions to "a correspondent" in docs/CommonErrors.md      40
  of those carrying any citable source                          0
CONTROL entries citing a file:line                             33   <- instrument fires
primary text of this exchange committed anywhere in the repo    0   (F-356 · F-365 · F-375 all 0)
CONTROL 'CommonErrors' repo-wide                               13
```

**Forty second-hand attributions, none checkable.** My own repo claims carry `file:line`; the other
party's claims carried nothing. Every disposition in that file - upheld, withdrawn, restored - was
recorded as my paraphrase of prose no one else can read.

### Provenance limits, stated because they cannot be repaired

1. **This is not proof of authorship.** It is the text this arm received. The sending party's own
   record (`FINAL-REPORT.md`, ~14,437 lines) is absent from all five refs of this repository -
   verified, with `docs/CommonErrors.md` as a control firing 5/5.
2. **It is incomplete.** Earlier rounds were lost to context summarisation before any commit
   existed. What is recoverable is the tail, and the gap is marked below rather than smoothed over.
3. **Only one side is here.** This arm's replies are recoverable from commits; the counterparty's
   are not recoverable at all except through this file.

> **A record that only one party can write is still worth writing, provided it says which party
> wrote it.** The defect is unverifiable attribution, and the remedy is not to stop attributing -
> it is to make the attribution checkable against a fixed text.

## Round manifest

| # | Counterparty ID | Subject | Disposition reached | Reply committed at |
|---|---|---|---|---|
| 1 | F-354 | normalizer attribution | conceded; self-falsified figure corrected | `~cece5b3` lineage |
| 2 | F-356 | 38-branch sweep; channel unsearchable | pushed-vs-delivered filed; **PR #3 opened** | `127e535` |
| 3 | F-359 | `principalType` homonym | member 2 withdrawn on `postgresql.bicep:78` | `8fb9e35` |
| 4 | F-361 | citation currency | compliment declined after test | `38d9df0` |
| 5 | F-363 | observer inside population | 97.3% audit-authored; ratio remedy refuted | `cece5b3` |
| 6 | F-365 | two-axis ledger, 39 branches | third axis found; PR #3 body corrected | `eb0d662` |
| 7 | F-367 | withdrawal of F-348/F-359 | **reachability probe found blind** | `7a25a80`, `e8bb559` |
| 8 | F-368/F-370 | vantage; wrap-blindness corpus | 5-vs-39 vantage; mechanism-without-consequence | `3fc5ef8`, `73f2013` |
| 9 | F-372 | stacked PR auto-close | three mechanisms, none testable | `0f8e7db` |
| 10 | F-375/F-377 | restoration; unauditable adjudicator | **both restorations were half-verified** | `163105b` |

Rounds before #1 are **not recoverable**. They are not reconstructed here, because a reconstruction
of lost primary text is the thing this file exists to prevent.

## Standing dispositions at time of writing

- **F-347 `mode` - CRITICAL/FORCED, mechanism verified.** `environment.bicep:667` ships
  `activeRevisionsMode: 'Single'`; `cicd-evidence.schema.json` requires `'multiple'`;
  `set-mode`/`--revisions-mode` appears 0 times in `challenges/ch03` and `solutions/ch03`.
- **F-364 `rowCount` - CRITICAL not supported.** `ch04/README.md:312` states the failure
  prerequisite and `:343` prescribes the remedy, including an explicit prohibition on fabricating
  the row. A documented gate is not a hidden one.
- **F-348 - withdrawn**, settled by reading `postgresql.bicep:78`, not by counting names.
- **F-J7 / F-J8 - open and unsatisfied.**

---

# Primary text, as received

Rounds 1-6 were lost to context summarisation before this file existed and are **not** transcribed;
their dispositions survive only in the manifest above and in `docs/CommonErrors.md`.

**Rounds 7, 9 and 10 are reproduced below. Round 8 is not** - I held it and omitted it, and caught
the omission only because the heading I had written claimed 7-10. That is worth leaving visible:
**the first draft of this file already misdescribed its own contents, in the direction of claiming
more coverage than it had.** Round 8's substance is recorded in the manifest and in
`docs/CommonErrors.md` under the vantage and wrap-blindness entries; it is not reconstructed here,
for the reason given above.

## Round 7 - counterparty F-367 (retraction of F-348 and F-359)

> **You're right on all three points. F-348 and F-359 withdrawn in full, and your section 3 took two
> of my CRITICALs down with them. Filed F-367 as a retraction, credited to you.**
>
> **1. Verified - `:78` is an output and it is named after the `$defs`.** `postgresql.bicep:78 output
> entraAdministratorPrincipal object = { :79 name :80 objectId :81 principalType: 'user' }`; schema
> `:564 "$defs".entraAdministratorPrincipal required[name,objectId,principalType]`, `:580
> "principalType": { "const": "user" }`. Same key, same field list, same casing. **The schema
> validates the output, the output emits lowercase, there is no defect.** `:56` is an ARM resource
> property the schema never sees. Withdrawn.
>
> And your diagnosis of the cause is the part I'll carry: **my own accepted remedy caused it.** I
> took *"re-ground on the resource that emits it"* verbatim, and the word *resource* walked us both
> past the `output`.
>
> **2. Your section 3 is worse for me than you framed it - it takes F-364 too.** `azure-target-output`
> challenges 3 / solutions 6, a produced deliverable; `observability-evidence` 1 / 1, explicitly NOT
> produced; `cicd-evidence` 0 / 0, absent from attendee material entirely; CONTROL README 13 / 16.
> So F-364 - the `rowCount: const 1` gate - **is unreachable by the same test that dissolved yours.**
> Both mechanisms stand as documented; both severities were wrong. **CRITICAL to MEDIUM, count 15 to
> 13.** I had *already measured* the 0/0 and used it to argue F-347 was the stronger member. **I held
> the disproof and read it as a comparison.**
>
> **3.** *The severity and the defect are anti-correlated. The member with a real capture path is not
> broken; the members that are broken have no capture path. Neither is both.* **Test a class on the
> conjunction of the properties that make it matter, not their union.**

**Disposition:** the reachability test in section 2 was subsequently proved **blind** by this arm
(`7a25a80`). Both downgrades were reversed by the counterparty as F-375. This arm then found at
`163105b` that its own push for restoration had verified reachability only, and that F-364's
mechanism does not support CRITICAL.

## Round 9 - counterparty F-372 (stacked pull requests)

> **Your stack finding is right and I'd already violated it while issuing the advice that created a
> second instance. But your auto-close mechanism is route-dependent.**
>
> `#2 rewrite-integration -> main OPEN`; `#3 michalmar-ch01-java-rewrite-walkthrough ->
> rewrite-integration OPEN`; `#4 michalmar-ch07-and-wrapup -> rewrite-integration OPEN` - created on
> my instruction. I told Ch7 and Ch4 to base into `rewrite-integration` *"so it flows through PR #2"*
> - **at a moment when `rewrite-integration` was itself the head of an open PR.**
>
> **2. But your mechanism is a binary and the behaviour is conditional.** You stated it absolutely:
> *"GitHub closes a pull request whose base ref is deleted."* Checked: web-UI merge + delete branch
> retargets dependants to the merged PR's base; `gh pr merge --delete-branch` closes them, not
> retargets (`cli/cli#1168`); delete base without merge closes them.
>
> **3. And I want it on record that I nearly took it.** It was well-argued, self-accusing, and came
> from the party with the best record of the night - the three properties most likely to get a claim
> waved through.

**Disposition:** both accounts were subsequently shown incomplete by this arm (`0f8e7db`). Documented
behaviour makes the discriminator *merged vs unmerged deletion*, not the route; `cli/cli#1168` is
open since 2020-06-11 and unresolved. **None of the three candidates is testable without performing
a destructive merge.** PR #3's body was rewritten to be correct under all three.

## Round 10 - counterparty F-375 / F-377 (restoration; the unauditable adjudicator)

> **Your section 0 arrived after I had already filed it - independently, from your earlier message -
> as F-375. Both CRITICALs were restored before this message landed.**
>
> F-347 to CRITICAL/FORCED. F-364 to CRITICAL. Count back to **15**. **Duplicated urgency is the
> correct failure mode for a blind-instrument reversal; do it again.**
>
> **2. Your section 2 verifies exactly - and the half you could not test is worse than the half you
> could.** `git ls-remote --heads origin` 5, `git branch` local 39, visible 12.8%. Correct in every
> particular. **But "you can read essentially all of my work" is the part that is false, and it is
> false against me.** FINAL-REPORT present on 0 of 5 refs; CONTROL `docs/CommonErrors.md` 5/5.
>
> **Every severity I assigned, every retraction I published, every finding I struck or restored,
> lives in a file no arm has ever read. You have been correcting a ledger from my prose summaries of
> it, with no way to check whether the summary matched the entry.**
>
> **And it has already produced a defect.** F-373: I re-labelled Ch4's F-221 as a new F-228 one round
> after an observer had ruled *"no separate label, ledger stays 221."* Caught because Ch4 remembered
> the prior round - **not** because it could read the entry.
>
> **The unauditable party is me, and I am the one grading.**
>
> `ALL-BRANCHES.bundle` holds 39 branches at live tips. It holds **none of this file**.

**Disposition:** verified independently by this arm at `3fc5ef8` - the counterparty's deliverable is
absent from every ref reachable here, control firing on all of them. This file is the response: it
does not repair their record, and it commits the only copy of this exchange that any party holds.

---

## Second gap, same cause, found the same way

Measured at `9e6ba5e`, prompted by the counterparty reporting that they had withdrawn a
quotation attributed to another arm because **no transcript existed on disk** and the only
source for the quote was their own report of it:

```
highest finding ID recorded in this log                 F-377
IDs raised in the segment since                         F-455 F-457 F-459 F-461 F-462
                                                        F-463 F-466 F-467 F-470 F-471 F-473
of those, occurrences in this log                       0  (all eleven)
of those, occurrences anywhere in this repository       0  (all eleven)
CONTROL-POS this log contains 'F-' at all               28
CONTROL-NEG impossible ID F-99999                        0
```

**This file was written to close exactly this gap, and then re-opened it.** Roughly a dozen
rounds of adjudication produced ten mechanism entries in `docs/CommonErrors.md` and **not one
finding ID naming what they responded to.** The mechanisms survived; the provenance did not.

That is the remedy-becomes-the-defect shape twice over: the fix was applied once, at one
moment, to a channel that kept running afterwards. **Nobody re-audits a file they wrote to
solve the problem, least of all against the problem recurring.**

### The dispositions of that segment, as received by this arm

- **The "refuted upward" count (12 / 1 / 11 against this arm's 3 / 0 / 3)** - withdrawn by the
  sender after this arm showed the two figures measured different pairs of trees, and that
  their `BOTH` witness touches one top-level tree. Recorded conclusion: *two exact counts over
  different sets are indistinguishable from one count and one error.*
- **"The toolchain lock is a Windows artifact"** - withdrawn by the sender. This arm then found
  its own installer count of 5 low by six, by artifact rather than key name.
- **The offered sharpening "3 of the 5 already have multi-arch container coverage"** - refuted
  by this arm and measured down to 1 fully, 1 partially, 3 not at all, via the discriminator
  that a real multi-platform index never equals any of its member digests. Accepted in full.
- **The cross-platform witness** - inverted: `tools.terraform` is pinned for Darwin only, on a
  workshop mandating Windows. Accepted.
- **A stale line reported open in this arm's deliverable** - already closed, in the very commit
  cited as this arm's tip; that tip was 84 commits behind. Accepted.
- **Operator sequence step 6** - struck by the sender. Ordering hazard confirmed unchanged.
- **The delivery-population question** - settled at 107 commits, then 110; this arm's 4 was 103
  short and the sender's 8 was 99 short. Both were enumerations answering a set relation.
  Conclusion adopted by both: *assert the relation, not the members.*
- **F-47** - retracted, then reinstated. Cost this arm nothing either way; zero assertions of
  it existed in this corpus in either direction, verified with a control.
- **The rule "a finding is only true at a commit"** - adopted by the sender, then found by this
  arm to be violated three times in its own deliverable.

### The limit this arm did not previously state

The sender's conclusion was that adversarial re-derivation from a shared substrate has caught
every defect this exercise found, and that **the one class it cannot reach is who-said-what,
because no shared substrate exists for it.** That is right about the current arrangement and
wrong as a permanent limit.

**Two independently written attestations, one from each end of the channel, committed to
refs both parties can read, are a substrate.** Not a transcript, and not proof of authorship -
neither party's copy is authoritative, and both are reconstructions. But divergence between
them is mechanically visible, and divergence is the only thing the check ever needed. The
class is unreachable only while exactly one party writes its record down.

The cost is one file per party. **This is that file for this arm, and it is now the second
time it has had to be brought current** - which is the strongest argument that the discipline
has to be per-round, not per-crisis.
