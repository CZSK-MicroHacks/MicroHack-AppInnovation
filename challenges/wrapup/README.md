# Wrap-up: what you proved

**By the end of this chapter you will have one page that answers the question your
manager will ask on Monday: was it worth it?**

## Why this matters

Two days ago the catalog ran on a single Windows Server virtual machine with its
database installed beside it. Nobody wanted to touch it, because touching it meant a
weekend, and breaking it meant a restore.

You did not just move it. You measured it. Every required chapter produced a number, and
this chapter puts them side by side — because "we modernized the app" convinces nobody,
and "rollback went from a four-hour restore to ninety seconds" convinces everybody.

**Estimated time:** 20–30 minutes.

## Before you start

You should have completed Challenges 0 through 6 and have your `evidence/` directory
with the validated handoff and each chapter's output. If your facilitator gave you a
golden handoff partway through, use the numbers from the chapters you completed
yourself and mark the rest as *not measured*.

## Fill in your scorecard

Copy this table and complete it from your own evidence. Nothing is pre-filled on purpose:
a scorecard somebody else wrote proves nothing, and the two days were spent producing
exactly these numbers. The last two columns name the file, field, or step each value comes
from, so no cell needs a guess. Where `<stack>` appears, use `dotnet` or `java` —
whichever you selected in Challenge 0.

| What you measured | Legacy baseline | After modernization | Where the baseline comes from | Where the result comes from |
| --- | --- | --- | --- | --- |
| Catalog response, median | | | `evidence/ch00-pain-<stack>.json` → `catalogMedianMs` | `evidence/load/raw/test-run.json` → `.testRunStatistics.Total.medianResTime`, Challenge 2 |
| Pipeline lead time — dispatch to live | | | `evidence/ch00-pain-<stack>.json` → `manualDeploySteps` and `manualDeployWindow`, recorded at the end of Challenge 0, step 2 | `evidence/cicd-report.json` → `.workflow.jobs.staging.startedAt` to `.traffic.promotion.observedAt`, printed by the Challenge 3, step 5 `jq` |
| Human steps to ship a one-line fix | | | `evidence/ch00-pain-<stack>.json` → `manualDeploySteps`, and `manualRollbackSteps` for the undo | `evidence/cicd-report.json` → the two human actions it records, `.workflow.jobs.staging.startedAt` (you dispatched it) and `.approval.approvedAt` (a named reviewer approved it); the undo is one more, `.traffic.safety.rollbackAttemptedAt` |
| Rollback — bad release to known-good | | | `evidence/ch00-pain-<stack>.json` → `manualRollbackSteps`, the steps in that same list that undo the release | `evidence/cicd-report.json` → `.traffic.safety.rollbackAttemptedAt` to `.traffic.safety.rollbackCompletedAt`, printed by the same Challenge 3, step 5 `jq` |
| Behaviour under load | | | `evidence/ch00-pain-<stack>.json` → `runningInstances` and `autoscale` | `evidence/load-test-report.json`, Challenge 2 |
| Time to answer "why was it slow?" | | | `evidence/ch00-pain-<stack>.json` → `onlyDiagnostics` and `distributedTraces` | Challenge 4, step 3 — the two clock readings you took either side of naming the slow dependency, and the difference in minutes |
| Mean time to recovery from an incident | | | `evidence/ch00-pain-<stack>.json` → `applicationHosts`, `databaseServices`, and `runningInstances` — one box, one instance, one text file | `evidence/ch06-mttr.json` → `minutesToRecovery`, Challenge 6, Task 7 |
| Security posture of what the migration touched | | | Challenge 0 ran no security assessment, so the honest baseline is *not assessed*; `evidence/ch00-pain-<stack>.json` → `configurationFile` is the one exposure it did record | `evidence/defender-report.json` → `.controls.containerRegistry`, `.controls.containerApp`, `.controls.database`, and `.controls.legacyVm`, each with its `disposition`, Challenge 5, step 3 |
| Secrets in application configuration | | | `evidence/ch00-pain-<stack>.json` → `configurationFile` | Challenge 1 |
| Patching the host | | | `evidence/ch00-pain-<stack>.json` → `applicationHosts` and `databaseServices`, both installed on the machine you connect to | Challenge 1 |
| Cost to run, per day | | | [`docs/CostEstimate.md`](../../docs/CostEstimate.md) → *Legacy VM versus modernized workload*, the legacy row | The same table, the row for your stack |

Four rows need a caveat, and saying them is part of doing this properly.

- **Catalog response** is the only row where both numbers are yours, and they were not
  measured the same way: one is a quiet loopback request on the VM, the other is 40
  concurrent users arriving over public HTTPS. Record both, and record what each measured.
- **Pipeline lead time** starts at the `workflow_dispatch` that began the run, not at a
  commit — Challenge 3 says so in its own labels. Against the legacy column, which is a
  whole release window, the comparison is directional rather than like-for-like. If
  someone at the table quotes DORA's *lead time for changes*, that is a different,
  longer measurement this workshop never observed.
- **Security posture** is deliberately not a count. Challenge 5 is explicit that "the
  value is not the count of things you fixed", so this row takes that chapter's own
  wording: the legacy answer is *unknown — never measured*, and yours is *enumerated,
  each with a disposition*. Write the four dispositions out if you want the detail;
  a headline number here would reward whoever started from the worst baseline.
- **Cost to run** is the one row you did not measure. It is a list-price estimate for this
  workshop's shapes and assumptions, and the answer depends on which database your stack
  uses. Quote it as an estimate, or re-derive it for your own region and agreement. And
  say which way it moves: on .NET / Azure SQL the modernized figure is *higher* — $5.13 to
  $6.67, about 30% more — and that is the expected outcome, not a failed migration. The
  legacy figure prices a machine; it does not price the patching, the backup, the
  certificate renewal, or the out-of-hours release window that every other row on this
  scorecard just removed. Hand over the +30% without that sentence and it reads as a loss.

## Discuss

Work through these with your table. They matter more than the commands you ran.

1. **Which path did you take in Challenge 1, and would you take it again?** Manual
   rebuild, Copilot-assisted rewrite, and Copilot modernization each cost different
   amounts of time and taught different things. Compare with someone who chose
   differently.
2. **Which number would persuade your organization?** Not the one you find most
   technically interesting — the one your business would care about.
3. **What did the SRE Agent get wrong, or nearly get wrong?** You were asked to reject a
   plausible hypothesis. What would have happened if you had accepted it?
4. **What is still manual?** Be specific. This is the honest edge of the workshop.
5. **What would you have to add before this ran a real product?** Backups, DR, cost
   controls, network isolation, on-call. Name the gaps rather than pretending they
   closed.

**Facilitators:** before you close the room, collect one number from every table — the
`minutesToRecovery` field in each team's `evidence/ch06-mttr.json` — and read out the
median. A single team's figure is an anecdote; "the median team in this room recovered in
eleven minutes, and none of them had a runbook for it" is the line people repeat back at
their own organizations. Read out the spread as well, and ask the fastest and slowest
tables what differed.

## What this did not cover

Being straight about the boundary is part of the value:

- **No in-place production migration.** The workshop rebuilds onto a clean target and
  reseeds from the canonical corpus. Real migrations carry data, users, and downtime
  constraints this workshop deliberately excludes.
- **No multi-region or disaster recovery design.** Single region throughout.
- **No cost optimization pass.** You proved it runs; you did not right-size it.
- **No production security review.** Challenge 5 shows you posture management; it is not
  a threat model.
- **A disposable database.** Workshop databases are reseeded, not migrated with history.

The optional [Challenge 7 extensions](../ch07-enterprise/README.md) start on several of
these.

## Take it home

- The [reference implementation](../../solutions/reference/README.md) is the finished
  target for both stacks — read it next to your own work.
- The [handoff contract](../../workshop/contracts/README.md) is the pattern worth
  stealing: make the boundary between two phases an explicit, validated document rather
  than tribal knowledge.
- The three Challenge 1 paths are a real decision you will face again. You now have data
  on which one suits which kind of change.

## What you just proved

You took an application nobody wanted to touch and gave it a deployment pipeline with a
rollback, an autoscaler, distributed tracing, a security posture baseline, and an agent
that spots incidents before a human does — and you have the evidence to show each one.

The scorecard above is the deliverable. Everything else was practice.

---

**Previous:** [Challenge 6: SRE Agent](../ch06-sre-agent/README.md) ·
**Optional next:** [Challenge 7 — Enterprise](../ch07-enterprise/README.md) or
[Innovation](../ch07-innovation/README.md) ·
**Back to** [workshop overview](../../README.md)
