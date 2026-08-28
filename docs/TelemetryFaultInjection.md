# Inducing the telemetry failure signals

The handoff validator checks the eight log signals named in
`workshop/contracts/behavior-contract.json` under `telemetry.logs`, and it compares your
collected signal names with the contract using **set equality**. A signal that never
appears fails the gate.

Four of the eight are *failure* signals:

- `catalog.database.failed`
- `catalog.import.failed`
- `catalog.query.failed`
- `catalog.performance.failed`

They are logged from `catch` blocks, so an application that behaves correctly never emits
them. **Driving more traffic at a healthy application cannot produce them.** You have to
make the application fail on purpose, observe the failure, and then put it back.

This page is that step. Do it after the release revision is live and before you collect
telemetry evidence.

> Every fault here is reversible and touches no schema. Restore and verify after each
> one, in the order given. Do not run steps 2 and 3 at the same time.

## Two traps that come before the faults

**Query the right table.** The failure signals are logged with an exception attached, and
the Azure Monitor OpenTelemetry exporter routes those records to **`AppExceptions`**. The
success signals, logged without an exception, go to **`AppTraces`**. Querying only
`AppTraces` returns zero rows for all four failure signals and looks exactly like missing
instrumentation.

The signal name also lives in a different place in each table, **and in a different form**:

| Table | Where the signal name is | What the value actually looks like |
| --- | --- | --- |
| `AppTraces` | `Message` | `catalog.query.completed` — the bare signal name |
| `AppExceptions` | `Properties['OriginalFormat']` | `catalog.query.failed filter={Filter}` — the **message template**, placeholders included |

**This is the third trap, and it defeats the fix for the first two.** `OriginalFormat` is
the *unformatted* template, so the obvious query still returns zero:

```kusto
// Returns 0 rows even when the signal is present.
AppExceptions | where tostring(Properties['OriginalFormat']) == "catalog.query.failed"
```

Match the prefix, or split off the first token — never `==`:

```kusto
AppExceptions
| extend sig = tostring(split(tostring(Properties['OriginalFormat']), ' ')[0])
| where sig == "catalog.query.failed"
```

Measured values at the time of writing: `catalog.query.failed filter={Filter}`,
`catalog.performance.failed workFactor={WorkFactor}`,
`catalog.import.failed rejected={Rejected}`, and `catalog.database.failed` with no
placeholder. **Do not rely on any given signal being bare** — the presence of a suffix
depends on whether that call site had structured parameters.

**Resolve the workspace by name.** The resource group holds a workspace for each stack,
so `az monitor log-analytics workspace list ... --query "[0].customerId"` may hand you the
other stack's workspace. It answers every query successfully and with plausible volumes,
because both stacks emit the same contract signal names. Ask for the one you want:

```bash
az monitor log-analytics workspace show -g <your-resource-group> -n <your-workspace-name> \
  --query customerId -o tsv
```

Then confirm it is yours before trusting anything it returns:

```kusto
AppMetrics
| where TimeGenerated > ago(1h)
| extend svc = tostring(Properties['service.name'])
| summarize by svc
```

**Two of the four trace signals do not exist as literal strings.** `db.client` and
`http.server` are OpenTelemetry span names that Application Insights maps onto its own
tables, so `AppDependencies | where Name == 'db.client'` returns **count 0** — not an
error. Identity is table membership plus a type discriminator:

| Contract signal | Where it actually is |
| --- | --- |
| `http.server` | `AppRequests` |
| `db.client` | `AppDependencies` where `DependencyType == 'SQL'` |

**`AppRequests` stores the route template in a column, not an attribute.** The telemetry
gate requires a matched-route probe (`http.request.method=GET`, `http.route=/figure/{id}`,
`http.response.status_code=200`). On `AppRequests` none of those three is an attribute:
the exporter folds the route template into `Name` (as `GET /figure/{id}`) and the status
into `ResultCode`. Querying `customDimensions` for `http.route` returns zero rows on a
perfectly instrumented app, and exercising the route again cannot change that. Derive the
probe from the columns:

```kusto
AppRequests
| where Name == "GET /figure/{id}" and ResultCode == "200"
| project TimeGenerated, Name, ResultCode, AppRoleInstance
```

The same three values *are* stored as real attributes on the metrics and logs carriers, so
only the trace carrier needs this derivation.

The full measured mapping for all 25 contract signals — table, selector, and storage
form for each — is `workshop/contracts/telemetry-signal-map.json`.

Only the five metric names match verbatim. Every wrong query here returns zero rows
rather than failing, so the natural reading is "the application is not emitting this"
and the natural next step is instrumenting code that is already correct.

**Filter every query to one revision, and to the revision under test.** Container Apps
health-probes every *provisioned* revision, so revisions serving no traffic keep emitting
resource attributes indefinitely. Measured over two hours on one environment:

| Revision | Resource-attribute records | User traffic |
| --- | --- | --- |
| `--0000001` (placeholder) | 1400 | none |
| `--release-<digest>` | 1378 | all of it |
| `--fixup1-<digest>` | 1342 | none |

`| take 1` is therefore not merely unreliable — the plurality answer is the placeholder
revision, with all six attributes present and correctly formatted. Resolve the revision
first and filter on it:

```bash
az containerapp revision list -g <your-resource-group> -n <your-container-app> \
  --query "[?properties.trafficWeight>\`0\`].name" -o tsv
```

```kusto
| where AppRoleInstance startswith "<the revision that carries traffic>"
```

This matters most across steps rather than within one. Fault injection and traffic
generation happen minutes apart, and a release in between repoints traffic silently: the
happy-path signals come from the new revision and the failure signals from the old one.
The result is internally consistent and asserts behaviour the release never emitted. The
capture manifest records a `revision` per query for exactly this reason, and the renderer
refuses a capture whose four queries disagree.

## 1. `catalog.import.failed`

POST a catalog file that is valid JSON but violates the import contract. Two requests are
enough. The import is rejected before it writes, so there is nothing to undo.

Expect `400`.

## 2. `catalog.database.failed` and `catalog.performance.failed`

Remove the application identity's data-plane read access, drive both the catalog page and
the performance endpoint, then restore.

On Azure SQL:

```powershell
sqlcmd -S $Server -d catalog -G -b -Q `
  "ALTER ROLE db_datareader DROP MEMBER [<your-identity>];
   ALTER ROLE db_datawriter DROP MEMBER [<your-identity>];"
```

On PostgreSQL:

```bash
psql -c 'REVOKE SELECT ON ALL TABLES IN SCHEMA public FROM "<your-identity>";'
```

Wait a few seconds, then drive `/?search=...` and `/perftest/catalog` several times each.
The performance endpoint needs its API key header. Expect `500` and `503`.

**Restore, then verify — with the probe that failed, not a weaker one.** Re-add the role
membership or re-grant `SELECT`, confirm the grants are back by querying them, and then
re-drive **`/?search=...` and `/perftest/catalog`**, the two requests that returned `500`
and `503`. Both must return `200`.

Do not verify this restore with `/readyz`, and do not verify it with a bare `/`. Section
["A thing worth noticing"](#a-thing-worth-noticing-while-you-are-here) explains why
`/readyz` returns `200` throughout this fault: it never reads application data, so it
cannot observe the fault and therefore cannot observe its removal either. A bare `/` is
weaker than the request that failed. Verifying a fault is gone with a probe that could not
see it while it was present is not a verification.

## 3. `catalog.query.failed` needs a narrower fault

**Step 2 does not produce this signal.** The catalog page resolves its category list
before it calls the figure catalog service, so denying every table makes the request fail
*outside* the `try` block that logs `catalog.query.failed`. The performance endpoint runs
a raw statement before the catalog call and throws one statement early for the same
reason.

Deny exactly one table — the figures table — so the page gets far enough in:

```powershell
sqlcmd -S $Server -d catalog -G -b -Q "DENY SELECT ON OBJECT::dbo.Figures TO [<your-identity>];"
```

```bash
psql -c 'REVOKE SELECT ON TABLE figures FROM "<your-identity>";'
```

Drive `/?search=...` a few times and expect `500`.

**Restore.** On Azure SQL, `REVOKE SELECT ON OBJECT::dbo.Figures` removes the `DENY`
without removing the role grant. On PostgreSQL, re-`GRANT SELECT` on the table. Verify with
the request that failed: **`/?search=...` must return `200`**. A bare `/` is not sufficient
here for the same reason as in step 2 — it is a weaker probe than the one that surfaced the
fault.

## 4. Wait before you query

Allow **about 300 seconds** between the last request and your query. Nothing is visible at
60 seconds. Querying immediately, seeing zero rows and starting to "fix" the application
is the most expensive mistake available here.

## 5. Collecting all eight signals

```kusto
union withsource = SrcTable AppTraces, AppExceptions
| where TimeGenerated > ago(3h)
| extend fmt = tostring(Properties['OriginalFormat'])
| extend sig = iff(isempty(fmt), tostring(split(Message, ' ')[0]), tostring(split(fmt, ' ')[0]))
| summarize recordCount = count(), lastSeen = max(TimeGenerated) by SrcTable, sig
| order by recordCount desc
```

Query gotchas worth knowing in advance:

- `$table` is not resolvable here. Use `union withsource = ...`.
- `of`, `last` and `first` are reserved words. `extend of = ...`, `summarize last = ...`
  and `summarize first = ...` all fail to parse with `SYN0002 A recognition error
  occurred`. Use other names — `ofmt`, `lastSeen`, `firstSeen`.
- `tostring(Properties['x'])` is safe whether `Properties` arrives as a dynamic column or
  as a JSON string.

## 6. Order of operations

1. Confirm the application is healthy and the workspace you resolved is your stack's.
2. Step 1. No undo needed.
3. Step 2. Restore and verify with `/?search=...` and `/perftest/catalog` before moving on.
4. Step 3. Restore and verify `/?search=...` returns `200`.
5. Wait 300 seconds.
6. Run the union query and confirm all eight signal names are present.
7. Only then collect telemetry evidence.
8. Re-run the acceptance suite **last**, after every fault is restored and verified.
   The handoff contract pins the acceptance `result` to `passed`, so an acceptance run
   taken while any fault is active cannot satisfy it.

Steps 2 and 3 must not overlap. Together they exhaust the connection pool, the failures
surface as connection-pool timeouts rather than database exceptions,
`catalog.database.failed` stops firing because it is guarded on the exception being a
database exception, and the evidence ends up worse than if you had injected nothing.

## A thing worth noticing while you are here

Throughout step 2, with every catalog read returning `500`, `/readyz` keeps returning
`200` and reports the database as ready. Its database check opens a connection and runs a
trivial statement; it never reads application data, and the fault removed data-plane
access only. A load balancer would have kept sending traffic to a completely broken
application.

That is the mirror image of the "container healthy while `/readyz` returns 503" trap this
workshop already teaches, and it is a better argument for deep readiness checks than any
slide.

## Provenance

The Azure SQL procedure, the ingestion delay, the ordering constraint and the readiness
observation were established by running them against a live release revision. The
PostgreSQL statements are the direct equivalents of the Azure SQL ones and follow the same
structure.
