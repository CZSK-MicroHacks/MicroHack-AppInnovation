# Day-of card

Print this. Everything on it is decided in advance in [the facilitator guide](Facilitator.md)
and [the agenda](Agenda.md); this page is only what you need while the room is full.

## Before 09:00: go/no-go

Anything red is fixed before 09:00, or that participant starts the day on a golden rejoin.

| Check | Where you look | Red means |
| --- | --- | --- |
| Both VMs built correctly | `C:\MicroHack\status\dotnet-smoke.json` and `java-smoke.json` | Rerun provisioning on that stack — see [Reset one participant](Facilitator.md#reset-one-participant) |
| Source tree is the one you pinned | `type C:\MicroHack\source\.source-commit` | Do not re-pin now. Re-pinning re-images every VM |
| Both golden handoffs validate | `handoff_cli` against `workshop/golden/dotnet-sqlserver/` and `workshop/golden/java-postgresql/` — the command is in [`workshop/golden/README.md`](../workshop/golden/README.md) | You have no rejoin path at 15:15 |
| Delivery baseline recorded | Your run log: the `git rev-parse HEAD` you captured at T-4, next to the rehearsal result — see [Rehearse the 15:15 cut](Facilitator.md#rehearse-the-1515-cut-before-you-have-to-perform-it), step 5 | You cannot say which tree the room ran, so nothing that goes wrong today is reproducible afterwards |
| Seed snapshot valid | `evidence/defender/foundation/seed-snapshot.json` | Challenge 5 has nothing to investigate |
| SRE foundation built, plan in Review | Portal, response plan `catalog-reviewed-rollback` | Challenge 6 is a talk, not a drill |
| Approval gate is real | `production` environment on one repo offers required reviewers | Challenge 3 never pauses |
| A push from a VM works | You pushed a throwaway commit from a provisioned VM yesterday | Challenge 1 stalls at its publish gate — before anyone's first migration command — for everyone at once |
| Every participant can copy their repository URL | Wherever you put their resource group name | You dictate URLs across a room at 14:00 |

The baseline is captured, not printed here. A commit cannot contain its own hash, so a SHA
written into this card always names the commit *before* the tree you are delivering — wrong
by exactly one, and it looks right. It is also a fact about one delivery rather than about
the repository, and it would go stale the moment anything lands with nothing failing to tell
you. Recorded in the run log beside the rehearsal result, the pair is what you actually need:
which tree the room ran, and the evidence it was known-good when it ran.

## The clock, and where you decide

| Time | Block | What you decide |
| --- | --- | --- |
| 09:00 d1 | [Demo](Demo.md), orientation | Announce the 15:15 cut now, not at 15:00 |
| 10:45 d1 | Challenge 1 starts | Steer the path: 1C is shortest, 1B will not finish |
| 14:00 d1 | Challenge 1, block 2 | **Poll the room.** See below |
| 14:45 d1 | Challenge 1, block 2 | Warn everyone who will not finish by 15:15 |
| 15:15 d1 | Golden-handoff cut + **Challenge 1 debrief** | Hard stop. Hand out golden handoffs, and run the [five debrief questions](../challenges/ch01/README.md#debrief-compare-the-three-paths) while you do. Never cut the debrief |
| 15:45 d1 | Challenge 2 | 35 minutes of waiting. Run the filler content |
| 09:00 d2 | Kickoff | Nobody starts Challenge 3 on a handoff that does not validate |
| 15:00 d2 | End of Challenge 5 | **Poll the room.** Demo-only fallbacks from here |
| 16:15 d2 | Wrap-up | Never cut this |

## Who is behind right now

One named file per checkpoint. Walk the room, look at `evidence\` on each screen, and note
the newest file each person has. Do not ask how it is going.

| By | Every participant should have |
| --- | --- |
| 10:30 d1 | `evidence/ch00-selection.json` |
| 12:30 d1 | `evidence/azure-target-output.json` |
| 14:00 d1 | `evidence/migration-report.json` |
| 14:45 d1 | `evidence/acceptance-report.json` |
| 15:15 d1 | `evidence/modernization-contract.json`, validated — or a golden handoff |
| 17:00 d1 | `evidence/load-test-report.json` |
| 11:15 d2 | `evidence/cicd-report.json` |
| 12:45 d2 | `evidence/observability-report.json` |
| 15:00 d2 | `evidence/defender-report.json` |
| 16:15 d2 | `evidence/sre-agent-report.json` |

Every file above is shared by all three Challenge 1 paths, so the ladder works whoever you
are standing next to. On the manual path `azure-target-output.json` is step 2 of eleven,
`migration-report.json` step 4, `acceptance-report.json` step 9, `modernization-contract.json`
step 11. Publishing to GitHub is a gate before step 1 on every path, not a final step, so
somebody pushing at 11:00 is on schedule rather than finishing. Between steps 4 and 9 no
shared file is written, so at 14:45 ask which numbered step they are on rather than looking
at `evidence\`. Anyone still on step 2 at 14:00 has nine steps left in seventy-five minutes
— tell them then that they are taking the golden handoff, so they spend the time learning
rather than racing.

Count the room, not the person. More than about a third behind a checkpoint is a room
problem, and you pull a lever instead of helping one table.

## Is this participant healthy?

Three commands, in this order. Stop at the first that fails.

```text
Get-Content C:\MicroHack\status\dotnet-smoke.json   # or java-smoke.json — every check must pass
Get-Content C:\MicroHack\source\.source-commit      # must equal your pinned source_commit
```

Then, from `tests/acceptance`, prove their evidence rather than trusting it:

```powershell
Push-Location tests\acceptance
uv --no-config run python -m catalog_acceptance.handoff_cli ..\..\evidence\modernization-contract.json --contracts ..\..\workshop\contracts --repository-root ..\..
Pop-Location
```

After Challenge 1 the equivalent is `uv --no-config run catalog-validate-challenge-evidence
<load|cicd|observability> <that chapter's report> --handoff evidence/modernization-contract.json
--contracts workshop/contracts --repository-root ../..`.

**If they say their commands are hanging, check this before anything else.** A VM accepts one
run-command at a time, and a *named* one left behind — by you, from an earlier inspection —
holds the channel forever without ever running. The participant sees
`Conflict: Run command extension execution is in progress` and nothing else; every status
field on the VM still reads `Succeeded`.

```powershell
az vm run-command list -g rg-user007 --vm-name vm-java-user007 --show-details `
  --query "[].{name:name, exec:instanceView.executionState}" -o table
```

A row reading `exec: Pending` is the blockage. Delete it and the participant's next command
works immediately; see [Facilitator](Facilitator.md#clean-up-after-yourself-on-a-participant-vm).
Empty output means you are in the orphaned-`invoke` case instead, which clears on its own in
about an hour — [Troubleshooting](Troubleshooting.md#az-vm-run-command-returns-conflict-run-command-extension-execution-is-in-progress)
has both. In the pilot this cost one participant two days, because nothing on their side could
show them the cause.

## What to cut, in what order

Pull these from the top. Every one is set out in [the agenda](Agenda.md).

1. **Steer the Challenge 1 path at 10:45.** Free, and the only lever that prevents the
   overrun rather than absorbing it.
2. **Treat the 15:15 cut as scheduled.** Half the room taking a golden handoff is the
   design working, not a failure.
3. **Timebox Challenges 4, 5, and 6.** Announce the finish time at the start of the block
   and hold it.
4. **Run Challenge 6 facilitator-led** above roughly ten teams. Decide this before the day;
   the reasoning exercise works as a group exercise.
5. **Demo-only, if behind at 15:00 on day 2,** in this order: Challenge 5 (saves ~50 min),
   Challenge 4 (~45 min), Challenge 6 (~40 min).
6. **Drop Challenge 7** without discussion. Offer it as homework.

Never demo-only Challenge 2 or the wrap-up. Challenge 2 produces the numbers the wrap-up
compares against, and the wrap-up is the only thing a participant can show their manager.

## Two things not to forget

- **Sign the facilitator CLI profile out** of every VM once Challenge 1 ends. It holds your
  Azure credentials — see
  [the credential section](Facilitator.md#the-facilitator-credential-sitting-on-every-participant-vm).
- **Say the teardown date out loud** at the closing debrief: what disappears, and when.
