# The ten-minute demo

The [agenda](Agenda.md) opens day one with a ten-minute, facilitator-driven demo, and the
[day-of card](DayOfCard.md) schedules it at 09:00. This is the script for it: six steps,
each with the command to run, the output to expect, and what to say while it is on screen.

The demo answers one question — *what does two days of this buy?* — and answers it with
numbers the workshop actually produces. Do not explain the architecture. Show the
destination and stop.

## Before you start

**Where you drive this from.** Your own laptop, in **bash**, from a clone of the delivery
whose `evidence/` you kept — not from a participant VM. Every command block below is bash:
they use `\` line continuations, `time`, and multi-line `jq` programs, none of which
survive a PowerShell session, and PowerShell is what a VM gives you by default. Have `az`
and `jq` on your PATH and `az login` done against the subscription that owns the
resources.

Two steps deliberately happen elsewhere, and say so where they appear: step 1 opens the
catalog in the VM's own browser over RDP, and step 5 is the Azure portal.
Everything else is your laptop. This is the first ten minutes in front of the room — a
block that fails because you were in the wrong shell looks exactly like an application
that does not work.

**Most of this needs a prepared environment.** Six of the six steps read artifacts a
participant produces during the workshop, which means you must have run the workshop
yourself at least once and kept the results. Specifically:

| Step | Runs cold from a fresh clone? | What it needs |
| --- | --- | --- |
| 1. The legacy catalog | **No** | A running `vm-dotnet-*` or `vm-java-*` from [Challenge 0](../challenges/ch00/README.md), plus its `evidence/ch00-pain-<stack>.json` |
| 2. The modernization plan | **No** | `evidence/modernization-plan.md` from [Challenge 1C](../challenges/ch01-copilot-modernization/README.md), open in VS Code |
| 3. Replicas under load | Yes, from the checked-in fixture | For live data: `evidence/load/raw/replicas.json` from [Challenge 2](../challenges/ch02/README.md) |
| 4. The rollback | **No** | A live Container App with two healthy revisions, from [Challenge 3](../challenges/ch03/README.md) |
| 5. The application map | **No** | Application Insights with traffic in the window, from [Challenge 4](../challenges/ch04/README.md) |
| 6. The scorecard | Yes, from the checked-in example | For live data: your own `evidence/` files |

The reason is the same one [`workshop/golden/README.md`](../workshop/golden/README.md)
gives for shipping no golden handoff: these artifacts are not documents *about* a
deployment, they carry live resource IDs, image digests, and commit SHAs. A checked-in
copy would be a fabrication or a pointer at deleted resources.

Practical consequence: **build the demo environment once and keep it.** It is the same
environment you need for the golden handoffs anyway, so the marginal cost is small. If
you have not, steps 3 and 6 still run from the repository's contract fixtures, and steps
1, 2, 4, and 5 become screenshots.

Every command below is either quoted from a chapter or is a chapter's command with a
`--query` projection added for screen readability. The provenance is given per step.

---

## 1. The legacy catalog, and its baseline (00:00 – 01:45)

Open the catalog in the VM's own browser after connecting over RDP — `http://localhost:5000` for
`dotnet-sqlserver`, `http://localhost:8080` for `java-postgresql`
([Challenge 0, step 1](../challenges/ch00/README.md), the stack table). Search for a
figure, filter a category, open one detail page and let its photograph load.

Then put the baseline on screen. This file is written by the PowerShell block in
[Challenge 0, step 2](../challenges/ch00/README.md):

```bash
jq -r '
  "catalog median            : \(.catalogMedianMs) ms",
  "app + database on one box : \((.applicationHosts + .databaseServices) | join(", "))",
  "runningInstances          : \(.runningInstances)",
  "autoscale                 : \(.autoscale)",
  "distributedTraces         : \(.distributedTraces)",
  "the only diagnostics      : \(.onlyDiagnostics)",
  "the database credential   : \(.configurationFile)"
' evidence/ch00-pain-dotnet.json
```

Expected output — a sample legacy VM, so read your own numbers:

```text
catalog median            : 412.7 ms
app + database on one box : dotnet, MSSQL$SQLEXPRESS=Running
runningInstances          : 1
autoscale                 : false
distributedTraces         : false
the only diagnostics      : C:\MicroHack\logs\dotnet-app.log
the database credential   : C:\MicroHack\secrets\dotnet.json
```

`runningInstances: 1` and `distributedTraces: false` are constants written by that block,
not measurements — they are true for every legacy VM in the room.

> Say: "This is a real retail catalog — 198 products, search, photographs — and it works
> fine. Everything that is wrong with it is in those seven lines: one instance, no
> autoscale, the database on the same box as the web tier, the credential in a file on
> the server, and one text log as the entire answer to *why was it slow last Tuesday?*"
>
> "Nobody is going to rewrite this application. The question is what you can do to it in
> two days."

## 2. The modernization plan, not the code (01:45 – 02:15)

Thirty seconds, no more. In VS Code on the VM, show the GitHub Copilot app modernization
panel — the unified assess/plan/execute experience
([Challenge 1C, step 1](../challenges/ch01-copilot-modernization/README.md)) — then show
the reviewed plan that came out of it:

```bash
grep -n '^#\{2,3\} ' evidence/modernization-plan.md | head -12
```

Expected output — the plan's own outline: task headings at `##`, and whatever structure
the reviewer kept under each one at `###`. A representative plan prints:

```text
3:## Task 1 — Retarget the runtime to .NET 10
4:### Files in scope
5:### Validation
6:## Task 2 — Externalize configuration
7:### Files in scope
8:## Task 3 — Prepare managed-identity data access
```

Task 1 is the move the whole path exists for: the VM runs .NET 8, and the modernized
container runs .NET 10 — `sourceSdk` and `targetSdk` in
[`workshop/toolchain.lock.json`](../workshop/toolchain.lock.json). The headings vary per
run, which is the point — this is the artifact a human edited. Each task records its file
scope, its preflight, its expected artifacts, its build/test/security validation, and its
stop/replan trigger
([Challenge 1C, step 1](../challenges/ch01-copilot-modernization/README.md) lists all
five). Scroll one task's detail rather than reading the whole file.

> Say: "The tool did not hand anyone a ten-thousand-line diff. It produced a plan, and a
> human edited it before a line of code moved. Reviewing a plan is much cheaper than
> reviewing a diff."
>
> "That is the whole difference between an AI demo and an AI you would let near
> production."

## 3. The same app under load, scaling itself (02:15 – 04:15)

Run the load test's replica series. This is the metric captured by
[Challenge 2, step 4](../challenges/ch02/README.md) — the `az monitor metrics list
--metric Replicas --aggregation Maximum --interval PT1M` call in
[the Challenge 2 solution](../solutions/ch02/README.md), filtered to one revision:

```bash
jq -r '.value[0].timeseries[0].data[] | "\(.timeStamp)  \(.maximum // "-")"' \
  evidence/load/raw/replicas.json
```

Run against the repository's own fixture — substitute
`workshop/contracts/fixtures/load/replicas.json` for the path above if you have no live
run — this prints:

```text
2026-08-20T11:50:00Z  1
2026-08-20T11:59:00Z  1
2026-08-20T12:00:00Z  1
2026-08-20T12:02:00Z  2
2026-08-20T12:04:00Z  3
2026-08-20T12:05:00Z  2
2026-08-20T12:07:00Z  2
2026-08-20T12:10:00Z  1
2026-08-20T12:15:00Z  1
```

> Say: "Forty concurrent users arrive at 12:00. By 12:04 there are three copies of the
> application serving them, and by 12:10 there is one again. Nobody was paged, and
> nobody is paying for three at 12:15."
>
> "On the VM you saw a moment ago, `runningInstances` was one, forever. That is the same
> application."

## 4. Rolling a bad revision back, timed (04:15 – 06:15)

This is the beat the agenda asks for: *roll a bad revision back in about ninety seconds*.
Show the two revisions first, then move the traffic while a clock is on screen.

The revision listing is the workflow's own capture
([`.github/workflows/catalog-dotnet.yml`](../.github/workflows/catalog-dotnet.yml),
`capture_revisions`) with a `--query` projection added so it fits a screen:

```bash
CICD=evidence/cicd-report.json
APP_RESOURCE_ID=$(jq -er '.subject.containerAppResourceId' "$CICD")
RESOURCE_GROUP=$(cut -d/ -f5 <<<"$APP_RESOURCE_ID")
APP_NAME=$(cut -d/ -f9 <<<"$APP_RESOURCE_ID")

az containerapp revision list \
  --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --query "[].{revision:name, weight:properties.trafficWeight, health:properties.healthState}" \
  --output table
```

The four names come from `evidence/cicd-report.json` — the same file the scorecard reads
two beats from now — so the app you list is provably the one the pipeline promoted, and
nothing has to be typed while the room is watching. `jq -er` stops if the file is missing
rather than running `az` with an empty `--name`.

Expected output — the bad revision is live. Names below are the sanitized ones from
`workshop/contracts/fixtures/cicd/promotion-revisions.json`; yours carry your app name:

```text
Revision                             Weight    Health
-----------------------------------  --------  -------
ca-mh-example--release-000000000000  0         Healthy
ca-mh-example--ci-000000000000       100       Healthy
```

Now roll it back. This is verbatim the `rollback()` trap the pipeline installs before it
ever promotes, in the same workflow file, with `time` wrapped around it so the room can
see the clock:

```bash
PREVIOUS_REVISION=$(jq -er '.revisions.previous' "$CICD")
CANDIDATE_REVISION=$(jq -er '.revisions.candidate' "$CICD")

time az containerapp ingress traffic set \
  --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --revision-weight "${PREVIOUS_REVISION}=100" "${CANDIDATE_REVISION}=0" \
  --output none
```

Expected output: `az` prints nothing at all — `--output none` is what the workflow uses —
and the shell prints a `real 0mN.NNNs` line. Do not promise a specific figure from the
stage; read whatever `real` says out loud. Re-run the listing above and `release` is back
at `100`, `ci` at `0`.

Then show that the pipeline measured the rollback for you, without anybody holding a
stopwatch. This is [Challenge 3, step 5](../challenges/ch03/README.md), trimmed to two of
its four lines:

```bash
jq -r '
  (.workflow.jobs.staging.startedAt | fromdateiso8601) as $dispatched
  | (.traffic.promotion.observedAt | fromdateiso8601) as $live
  | (.traffic.safety.rollbackAttemptedAt | fromdateiso8601) as $undoStart
  | (.traffic.safety.rollbackCompletedAt | fromdateiso8601) as $undoEnd
  | "pipeline lead time (dispatch to live): \(((($live - $dispatched) / 60) * 10 | round) / 10) min",
    "rollback duration:                     \(((($undoEnd - $undoStart) / 60) * 10 | round) / 10) min"
' "$CICD"
```

Expected output. Every block in this step reads `$CICD`, so one substitution covers all
three: set `CICD=workshop/contracts/cicd-evidence.example.json` at the top of the step to
rehearse without a live run, and it prints:

```text
pipeline lead time (dispatch to live): 45 min
rollback duration:                     2 min
```

> Say: "That was one command, and the whole application is back on the known-good build.
> The pipeline installs it as a trap *before* it promotes, so the undo exists before the
> risk does."
>
> "The clock there starts when the pipeline was dispatched, not at a commit — this
> workshop is careful about that distinction, and so should you be when somebody quotes
> DORA at you."

## 5. Why it was slow (06:15 – 08:00)

Portal, not CLI. Open **Application Insights → Application map**
([Challenge 4, step 3](../challenges/ch04/README.md)). The Container App and its database
are separate nodes with call volume and average dependency latency on the edge:

![Application Insights application map showing the catalog Container App node with two instances, 205 calls and 1.3 s average duration, connected by an arrow labelled 1.7 ms and 402 calls to a separate MSSQL database node](../images/ch04-map.png)

Then click through to **Performance** and show that it leads with p50/p95/p99 and a
per-operation breakdown rather than an average, with individual sample traces you can
open ([Challenge 4, step 3](../challenges/ch04/README.md)).

> Say: "The VM could not draw this picture, because the app and the database were the
> same process on the same box. The number on that edge — how many database calls one
> page view really makes — is new information, not a better-looking version of old
> information."
>
> "Challenge 4 asks participants to time themselves getting from *it was slow* to naming
> the dependency. On the VM that clock never stops, because the data does not exist."

## 6. The scorecard (08:00 – 10:00)

Close on the numbers. [The wrap-up](../challenges/wrapup/README.md) is a before/after
scorecard where every cell names the file and field it came from, so nothing on it is a
claim anybody has to take on trust:

```bash
jq -rn \
  --slurpfile legacy evidence/ch00-pain-dotnet.json \
  --slurpfile cicd evidence/cicd-report.json \
  --slurpfile mttr evidence/ch06-mttr.json \
  '
    "catalog median, legacy : \($legacy[0].catalogMedianMs) ms on \($legacy[0].runningInstances) instance, autoscale \($legacy[0].autoscale)",
    "pipeline lead time     : \(((($cicd[0].traffic.promotion.observedAt | fromdateiso8601) - ($cicd[0].workflow.jobs.staging.startedAt | fromdateiso8601)) / 60 | floor)) min, dispatch to live",
    "rollback duration      : \(((($cicd[0].traffic.safety.rollbackCompletedAt | fromdateiso8601) - ($cicd[0].traffic.safety.rollbackAttemptedAt | fromdateiso8601)) / 60 | floor)) min",
    "minutes to recovery    : \($mttr[0].minutesToRecovery) min"
  '
```

Expected output — the figures below are from a sample environment, so read your own:

```text
catalog median, legacy : 412.7 ms on 1 instance, autoscale false
pipeline lead time     : 45 min, dispatch to live
rollback duration      : 2 min
minutes to recovery    : 13 min
```

Run against the repository's own fixtures if you have no delivered session behind you —
substitute `workshop/contracts/fixtures/wrapup/ch00-pain-dotnet.json`,
`workshop/contracts/fixtures/sre-agent/cicd-evidence.json`, and
`workshop/contracts/fixtures/wrapup/ch06-mttr.json` for the three paths above. They
produce exactly the four lines printed here.

The last line is the one to land on. It comes from `evidence/ch06-mttr.json`, written in
[Challenge 6, Task 7](../challenges/ch06-sre-agent/README.md) from two timestamps the
participant did not choose — an agent's own audit trail and an Azure Monitor alert's
`resolvedDateTime`.

> Say: "Everything on this scorecard is measured by the person who will quote it, from a
> file they can hand to their manager. The left column is their estimate of today. The
> right column is what they did in two days."
>
> "The last row is the one to take away. Detection to recovery, on a real incident, with
> an agent proposing the fix and a human approving it — and it is written to a file, so
> the room can compare medians rather than anecdotes."

---

## One slide

Six bullets, paste-ready:

- **A real legacy application, not a toy.** 198 products, search, photographs, a database
  and a web tier on one Windows VM — one instance, no autoscale, no traces, a credential
  in a file on the server.
- **Copilot app modernization produces a plan a human edits, not a diff nobody reads.**
  Every task carries its file scope, its validation command, and its rollback.
- **Elasticity is demonstrated, not asserted.** One replica becomes three under 40
  concurrent users and falls back to one, measured from Azure Monitor at one-minute
  grain.
- **The undo exists before the risk does.** The pipeline installs a rollback trap before
  it promotes; recovering the whole application is one `az containerapp ingress traffic
  set` and about two minutes.
- **"Why was it slow?" becomes an answerable question.** An application map with
  per-dependency latency, p50/p95/p99 per operation, and individual traces — none of
  which the VM could produce.
- **It ends with a scorecard where every number cites its source file.** Median response,
  pipeline lead time, rollback duration, and detection-to-recovery — measured by the
  person who will quote them.

---

**See also:** [Agenda](Agenda.md) · [Day-of card](DayOfCard.md) ·
[Facilitator guide](Facilitator.md) · [Glossary](Glossary.md) ·
[Cost estimate](CostEstimate.md) · [Troubleshooting](Troubleshooting.md)
