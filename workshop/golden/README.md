# Golden handoffs

A *golden handoff* is a validated `modernization-contract.json` produced by a facilitator
who has completed Challenge 1 end to end. It is the rejoin path: at the 15:15 cut on day
one, any participant who has not finished modernizing takes the golden handoff for their
stack and continues into Challenges 2 through 6 with everyone else.

Without it, a participant who is behind at 15:15 is finished for the workshop. With it,
they lose Challenge 1 and keep the other five.

## The repository cannot ship these, and that is not an oversight

A handoff is not a document about a deployment — it *is* the deployment, in the sense that
every field in it is a live identifier. It carries the Azure resource IDs of a real
container app and a real database, the digest of an image in a real registry, and the
commit SHA of source in a real GitHub repository. `catalog-migrate render-handoff` reads
those values out of a deployment that exists; it cannot invent them.

So a checked-in golden handoff would be one of two things: a fabrication that fails
validation the moment anyone runs it, or a pointer at Azure resources that were deleted
when whoever built it tore down their subscription. Both are worse than an empty
directory, because both look like a rejoin path right up until 15:15, when there isn't one.

What this directory gives you instead is the exact place the artifacts go, the exact
procedure that produces them, and the exact command that proves they are good.

## Budget

**One to two days, once per delivery**, and it is the single largest item of facilitator
preparation. You are performing Challenge 1 twice — once for `dotnet-sqlserver`, once for
`java-postgresql` — and the chapter's own estimate is 5–12 hours per stack. Do it at
**T-4**, not the night before: you need room for the deployment to be wrong the first time.

This is also the best use of that time you will get, because it is the only preparation
that makes you fluent in the exercise you are about to supervise. Facilitators who skip it
discover Challenge 1's rough edges at the same moment their participants do.

## Build them

For each stack, work through Challenge 1 exactly as a participant would, using whichever
path you intend to recommend in the room. Deploy into a **facilitator-owned** resource
group, not a participant's.

Then render into the bundle. A golden bundle is **its own validation root**: the
validator resolves every artifact relative to `--repository-root`, and the path registry
requires the contract at `evidence/modernization-contract.json`. Pointing
`--repository-root` at this repository instead makes that path
`workshop/golden/<stack>/…`, which matches no slice and can never exit `0`.

```text
workshop/golden/dotnet-sqlserver/
└── evidence/
    ├── modernization-contract.json
    ├── acceptance-report.json
    ├── azure-target-output.json
    ├── migration-report.json
    ├── rollback-runbook.md
    ├── runtime-test-report.json
    └── telemetry-report.json
```

```bash
cd tests/acceptance
uv --no-config run python -m catalog_acceptance.handoff_cli \
  ../../workshop/golden/dotnet-sqlserver/evidence/modernization-contract.json \
  --contracts ../../workshop/contracts \
  --repository-root ../../workshop/golden/dotnet-sqlserver
```

Run from the repository root. Repeat for `java-postgresql`. **Both must exit `0`.** A
non-zero exit means the handoff and the deployment disagree; fix the deployment, re-render,
and run it again. Do not hand out a contract that has not exited `0` on the machine you are
standing at.

### Rehearse the failure before the room does

`golden-dryrun` walks the same checks in the T-4 order and stops at the *first* defect
with one line naming it, rather than emitting a schema error set you have to read
backwards at 09:00 on day one:

```bash
cd tests/acceptance
uv --no-config run golden-dryrun ../../workshop/golden/dotnet-sqlserver
```

Run it against an empty directory once, deliberately, so you know what "no rejoin path"
looks like before it matters.

## Keep them alive

The resources a golden handoff points at must still exist when a participant uses it, and
must keep existing until the workshop ends. Two consequences:

- **Do not tear down the facilitator environment between the build and the delivery.** If
  you build at T-4 and clean up at T-2, you have no rejoin path.
- **Re-validate on the morning of day one.** The day-of checklist
  ([`docs/DayOfCard.md`](../../docs/DayOfCard.md)) has this as a pre-09:00 red line for
  exactly this reason. A handoff that validated four days ago is not evidence that it
  validates now.

## Why these files are not committed

`workshop/golden/*/evidence/` is ignored by Git — the whole directory, not just the
contract, because every artifact in it carries the same live identifiers. It is specific
to one facilitator's subscription and one delivery, it goes stale the moment those
resources are deleted, and committing it would put a stranger's resource IDs on a rejoin
path that no longer resolves. Build your own; they are cheap to re-render once the
environment exists.

The shape you are producing is documented in
[`workshop/contracts/README.md`](../contracts/README.md), and a complete, correctly
structured instance is checked in at
[`workshop/contracts/modernization-contract.example.json`](../contracts/modernization-contract.example.json).
Read that file if you want to know what `render-handoff` is going to emit before you run
it — but do not copy it here and edit the values by hand. Hand-edited contracts pass
schema validation and fail the cross-field checks that make the artifact worth anything.

## Handing one out

Give the participant the contract for **their** stack, and tell them what they are
receiving: a working deployment that is not theirs. From Challenge 2 onward they operate
against the facilitator environment, which means their evidence is real but their
Challenge 1 scorecard rows come from someone else's run. Say that out loud when you hand
it over — [`docs/DayOfCard.md`](../../docs/DayOfCard.md) treats half the room taking a
golden handoff as a normal outcome, not a failure, and participants take it much better
when it was announced at 14:00 than when it arrives as a surprise at 15:15.
