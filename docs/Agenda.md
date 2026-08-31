# Two-day agenda

**Read this before you publish a schedule.** The required chapters do not fit in two
days at their own stated durations. That is not a defect you can plan around by starting
earlier — it is a property of the content, and it means you must decide *in advance*
which chapters are hands-on, which are timeboxed, and which you demo. This page gives you
the schedule, the arithmetic behind it, and the levers.

## The honest arithmetic

Every chapter states its own estimate. Summed for the required chapters (0 through 6 plus
the wrap-up):

| Chapter | Chapter's own estimate | Allocated below | Gap |
| --- | --- | --- | --- |
| 0 — Select a baseline | 50–60 min | 60 min | none |
| 1 — Modernize | 5–12 h (300–720 min) | 225 min | **−75 to −495 min** |
| 2 — Load and autoscaling | 75–110 min | 75 min | 0 to −35 min |
| 3 — CI/CD and revisions | 120–180 min | 120 min | 0 to −60 min |
| 4 — Observability | 90–150 min | 75 min | −15 to −75 min |
| 5 — Cloud security posture | 120–180 min | 90 min | −30 to −90 min |
| 6 — SRE Agent | 90–150 min | 60 min | −30 to −90 min |
| Wrap-up | 20–30 min | 25 min | 0 to −5 min |
| **Total** | **14 h 25 min – 26 h 20 min** | **12 h 10 min** | **−2 h 15 min to −14 h 10 min** |

An independent review of the same content put the required work at 20–29 hours against a
12–14 usable-hour window, which is the same conclusion from a slightly harsher starting
point. Either way: **at best you are two hours short, at worst fourteen.**

Challenge 1 is the overrun. On its own it consumes 40–75% of the entire two-day window,
and its three paths differ by more than a working day:

| Challenge 1 path | Chapter's own estimate | Realistic in a 3¾-hour block? |
| --- | --- | --- |
| Manual rebuild (1A) | 5–8 h | No — expect a golden handoff |
| Copilot-assisted rewrite (1B) | 8–12 h | No — the longest path by a wide margin |
| Copilot modernization (1C) | 5–7 h | Closest, but still short |

Challenges 3, 4, 5, and 6 each overrun their slot by 30–90 minutes at the top of their
range. Those gaps are recoverable with the levers below; Challenge 1's is not.

## The schedule

Assumes 09:00–17:00 both days with a 45-minute lunch and two 15-minute breaks.

### Day 1

| Time | Block | Notes |
| --- | --- | --- |
| 09:00–09:10 | **[Opening demo](Demo.md)** | 10 minutes, facilitator-driven, day 1 only. Show the legacy catalog running on a Windows VM, then show the finished modernized app and roll a bad revision back in about ninety seconds. Do not explain the architecture — show the destination and stop. The six steps, their exact commands, the output to expect, and what to say are in that script, which also lists which steps need a prepared environment. |
| 09:10–09:30 | Orientation | Requesting Just-in-Time RDP access (Challenge 0, step 2 — the NSG ships closed on purpose), RDP sign-in to the chosen VM's public IP, resource-group boundaries, the immutable source commit, the evidence rules, and the [glossary](Glossary.md). Say explicitly: never hand-edit evidence, and ask for a golden handoff rather than fabricating one. |
| 09:30–10:30 | **Challenge 0 — select a baseline** | Pick a stack, connect to that one VM via JIT, run the `198/20/198` corpus check, and record the selection. Be available to unblock JIT access. |
| 10:30–10:45 | Break | |
| 10:45–12:30 | **Challenge 1 — block 1** | Path choice happens here. Steer the room: see the path table above. |
| 12:30–13:15 | Lunch | |
| 13:15–15:15 | **Challenge 1 — block 2** | Circulate. Identify who will not finish by 15:15 and warn them at 14:45, not at 15:14. |
| 15:15–15:30 | **Golden-handoff cut + Challenge 1 debrief** | Hard stop. Anyone without a validated `evidence/modernization-contract.json` receives the golden handoff for their stack. This is a scheduled event, not a failure. Run the five questions from [challenges/ch01/README.md](../challenges/ch01/README.md#debrief-compare-the-three-paths) while the handoffs are being distributed — this is the only moment all three paths are live in the room. Never cut the debrief. |
| 15:30–15:45 | Break | |
| 15:45–17:00 | **Challenge 2 — load and autoscaling** | Contains at least 35 minutes of unavoidable waiting. Run the filler below. |

### Day 2

| Time | Block | Notes |
| --- | --- | --- |
| 09:00–09:15 | Day 2 kickoff | Confirm everyone's handoff and Challenge 2 evidence validate before anyone starts Challenge 3. One broken handoff here costs the whole day. |
| 09:15–11:15 | **Challenge 3 — CI/CD and revisions** | About 40 minutes is identity and GitHub environment setup. Verify the repository plan and visibility before the session (see [the facilitator guide](Facilitator.md)) or the approval gate will not exist. |
| 11:15–11:30 | Break | |
| 11:30–12:45 | **Challenge 4 — observability** | Timeboxed from 90–150 minutes. Deploy the workbook first, prove the queries second; if time runs out, the workbook alone is the deliverable. |
| 12:45–13:30 | Lunch | |
| 13:30–15:00 | **Challenge 5 — cloud security posture** | Timeboxed from 120–180 minutes. Runs against your pre-warmed seed snapshot, not live findings. |
| 15:00–15:15 | Break | |
| 15:15–16:15 | **Challenge 6 — SRE Agent** | Facilitator-led for cohorts above roughly ten teams; see the lever below. |
| 16:15–16:40 | **Wrap-up scorecard** | Participants fill in the before/after table from their own evidence. Do not cut this — it is what they take back to their manager. |
| 16:40–17:00 | **Closing debrief** | Two questions, round the room: what surprised you, and what will you do differently on Monday. Then the teardown notice: what disappears, and when. |

## Your levers, in the order you should pull them

1. **Steer the Challenge 1 path choice at 10:45.** The Copilot modernization path (1C) is
   the shortest at 5–7 hours and the closest to a real upgrade backlog. Say out loud that
   the Copilot-assisted rewrite (1B, 8–12 hours) will not finish inside the workshop and
   that choosing it means planning on a golden handoff. Participants who choose it
   knowingly are fine; participants who discover it at 15:15 are not.
2. **Treat the 15:15 golden-handoff cut as scheduled, not exceptional.** Announce it at
   09:10 on day 1. If half the room takes it, the workshop is working as designed:
   Challenge 1 teaches modernization, and Challenges 2–6 teach operating what was
   modernized. Both are worth a day; neither is worth losing the other.
3. **Timebox Challenges 4, 5, and 6 rather than letting them slide.** Each is allocated
   below its own minimum in the table above. Announce the finish time at the start of the
   block and hold it. A partially completed Challenge 5 with an honest write-up is a
   better outcome than a complete Challenge 5 that eats the wrap-up.
4. **Make Challenge 6 a facilitator-led demo for large cohorts.** The SRE Agent foundation
   costs 45–60 minutes of facilitator hand-work *per team* to build, plus a per-team hourly
   charge. Above roughly ten teams the arithmetic stops working. Build **one** shared
   foundation, drive the investigation on screen, and have participants do the reasoning —
   Task 3, challenging the agent's hypothesis, is the part that matters and it works fine
   as a group exercise.
5. **Demo-only fallbacks, if you are running behind at 15:00 on day 2.** In order of what
   to sacrifice first:
   - Challenge 5 → facilitator runs the five capture queries on screen against the seed
     snapshot; participants write only the assessment. Saves ~50 minutes.
   - Challenge 4 → facilitator deploys the workbook live and walks the five queries;
     participants confirm their own telemetry appears. Saves ~45 minutes.
   - Challenge 6 → facilitator-led as above. Saves ~40 minutes.
   Never demo-only Challenge 2 or the wrap-up: Challenge 2 produces the numbers the
   wrap-up compares against, and the wrap-up is the takeaway.
6. **Drop Challenge 7 without hesitation.** It is optional, open-ended, and budgeted at
   60–120 minutes that this schedule does not contain. Offer it as homework.

## The Challenge 2 dead time

Challenge 2 contains **at least 35 minutes of unavoidable waiting**, in three stretches:

| Wait | Length | Why it exists |
| --- | --- | --- |
| Quiet baseline | ~10 min | Azure Monitor must record the single-replica point before load starts |
| Load run | ~10 min | Provisioning the load engine, the 300-second run, and deprovisioning |
| Scale-down | up to 15 min | Replica count falling back to one after load stops |

Nobody learns anything watching a progress bar, and a room of thirty people going quiet
for fifteen minutes is where a workshop loses its energy. Fill it deliberately:

- **During the 10-minute baseline wait** — deliver the Challenge 3 concept briefing live:
  what a revision is, why traffic weights exist, and why OIDC replaces a stored secret.
  This is 10 minutes of content that day 2 otherwise spends reading.
- **During the 10-minute load run** — have everyone open the Container App's **Metrics**
  blade and pin `Replicas` split by revision, so they watch the scale-out happen rather
  than reading it out of JSON afterwards.
- **During the 15-minute scale-down wait** — table discussion: *which scale rule would you
  use for your own application at work, and what would it cost you to be wrong?* Ask two
  tables to report back. This is the most transferable conversation in the workshop and it
  costs you nothing.

## If you have three days

The content fits comfortably in three days, and the shape changes only in one place: give
Challenge 1 a full day, keep the golden-handoff cut at the end of it, and run Challenges
2–6 hands-on at their own estimates across days two and three. Nothing else needs to
change.
