# F-74 — Fault injection procedure for the telemetry failure signals

**Purpose.** `workshop/contracts/behavior-contract.json` `telemetry.logs` requires eight
log signals, four of which are *failure* signals, and
`catalog_acceptance/handoff.py:270` compares the returned signal set with **set
equality** — a missing signal fails the gate. No step anywhere in `challenges/`,
`solutions/ch01*/` or `docs/` induces any of those failures. This file is the missing
step, written by having actually been run.

- Stack: .NET / Azure SQL, `ca-mh-user001-dotnet`
- Release revision: `ca-mh-user001-dotnet--release-47acf263d332`
- `sourceCommit`: `47acf263d3320fa3bb41d5469fc3c7428a393fca`
- Archive provenance: `4bf59f7ee8dae11259d73ba5a5d7cb0e3355c4af`
- Executed from `vm-dotnet-user001` via `az vm run-command invoke`, because the
  Container Apps environment is internal and the app URL is not reachable from a laptop.

---

## 0. The trap that comes first: `AppTraces` vs `AppExceptions`

The four failure signals are logged with `_logger.LogError(exception, "...")`. The Azure
Monitor OpenTelemetry exporter routes a log record **that carries an exception** to
**`AppExceptions`**, not `AppTraces`. The success signals, logged without an exception,
go to `AppTraces`.

An attendee who queries `AppTraces` — the obvious table, and the only one a search for
"log" suggests — gets **zero rows for all four failure signals** and concludes the
instrumentation is missing. The material gives no KQL guidance at all. I made exactly
this mistake and caught it only by dumping raw rows.

The signal name also lives in a different place per table:

| Table | Where the signal name is | Extraction |
| --- | --- | --- |
| `AppTraces` | `Message` | `split(Message,' ')[0]` |
| `AppExceptions` | `Properties['OriginalFormat']` | `split(tostring(Properties['OriginalFormat']),' ')[0]` |

## 0a. The trap that comes before *that*: there are two workspaces

`rg-user001` contains **`log-mh-user001-dotnet`** and **`log-mh-user001-java`**. The
natural discovery command

```bash
az monitor log-analytics workspace list -g rg-user001 --query "[0].customerId" -o tsv
```

returns **`log-mh-user001-java`** — the *other stack's* workspace. It answers every query
successfully, with plausible volumes and a plausible `http.server.request` signal, because
the Java arm emits the same contract signal names. Nothing in the result identifies the
stack unless you inspect `Properties.LoggerName` (`com.microsoft.microhack.catalog...`)
or `AppMetrics` `service.name`.

I hit this and spent four queries interpreting the Java arm's telemetry as my own. Always
resolve the workspace **by name**:

```bash
az monitor log-analytics workspace show -g rg-user001 -n log-mh-user001-dotnet \
  --query customerId -o tsv
# 9523ac07-57a2-44d0-bebc-00fb52336e1d
```

and sanity-check it before trusting anything:

```kusto
AppMetrics | where TimeGenerated > ago(1h)
| extend svc = tostring(Properties['service.name'])
| summarize by svc
// must be exactly: mh-catalog-dotnet
```

---

## 1. `catalog.import.failed` (+ `exception`)

POST a multipart form to `/import` whose catalog file is valid JSON but violates the
import contract. Windows PowerShell 5.1 has no `Invoke-WebRequest -Form`, so the body is
built with `System.Net.Http`.

```powershell
Add-Type -AssemblyName System.Net.Http
$bad = '{"figures":[{"id":"not-a-guid","name":""}],"categories":[]}'
$client  = [System.Net.Http.HttpClient]::new()
$content = [System.Net.Http.MultipartFormDataContent]::new()
$part = [System.Net.Http.StringContent]::new($bad)
$part.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse('application/json')
$content.Add($part, 'catalogFile', 'catalog.json')
foreach ($i in 1..2) {
  $resp = $client.PostAsync("$base/import", $content).GetAwaiter().GetResult()
  Write-Output "import$i=$([int]$resp.StatusCode)"      # expect 400
}
```

Observed: `400` × 2. Nothing to undo — the import is rejected before it writes.

## 2. `catalog.database.failed` + `catalog.performance.failed`

Remove the managed identity's data-plane role membership. This is reversible and touches
no schema.

```powershell
$S = 'sql-mh-user001-dotnet-kurep3z6.database.windows.net'
sqlcmd -S $S -d catalog -G -b -Q `
  "ALTER ROLE db_datareader DROP MEMBER [id-mh-user001-dotnet];
   ALTER ROLE db_datawriter DROP MEMBER [id-mh-user001-dotnet];"
Start-Sleep -Seconds 8
```

Then drive both surfaces (the perftest endpoint needs its API key header):

```powershell
foreach ($i in 1..6) {
  try { Invoke-WebRequest "$base/?search=fault$i" -UseBasicParsing -TimeoutSec 45 }
  catch { Write-Output "root$i=$([int]$_.Exception.Response.StatusCode)" }   # 500
  try { Invoke-WebRequest "$base/perftest/catalog" -UseBasicParsing -TimeoutSec 60 `
          -Headers @{ 'x-api-key' = $apiKey } }
  catch { Write-Output "perf$i=$([int]$_.Exception.Response.StatusCode)" }   # 503
  Start-Sleep -Seconds 5
}
```

**Restore — always, and verify:**

```powershell
sqlcmd -S $S -d catalog -G -b -Q `
  "ALTER ROLE db_datareader ADD MEMBER [id-mh-user001-dotnet];
   ALTER ROLE db_datawriter ADD MEMBER [id-mh-user001-dotnet];"

sqlcmd -S $S -d catalog -G -b -h -1 -W -Q `
  "SELECT r.name FROM sys.database_role_members m
     JOIN sys.database_principals p ON p.principal_id = m.member_principal_id
     JOIN sys.database_principals r ON r.principal_id = m.role_principal_id
    WHERE p.name = N'id-mh-user001-dotnet';"
# must print db_datareader and db_datawriter

Invoke-WebRequest "$base/readyz" -UseBasicParsing    # 200 {"status":"ready",...}
```

Observed: `500` × 6 on `/`, `503` × 6 on `/perftest/catalog`; both roles restored;
`/readyz` `200`.

## 3. `catalog.query.failed` — needs a *narrower* fault than step 2

**Step 2 does not produce this signal, and the reason is the most useful thing in this
document.**

`/` renders `Pages/Index.razor`, which resolves its **category** list before it calls
`FigureCatalogService.ListAsync`. Removing `db_datareader` denies `Categories` as well as
`Figures`, so the request fails *outside* the try block at
`FigureCatalogService.cs:37-73` and never reaches the catch that logs
`catalog.query.failed`. Verified from the exception table:

```
Microsoft.Data.SqlClient.SqlException
  The SELECT permission was denied on the object 'Categories', ...   n=32
System.InvalidOperationException
  A suitable constructor for type '...RazorPages.PageModel' could not be located ... n=8
```

`/perftest/catalog` does not reach it either: `PerformanceCatalogService` runs
`ExecuteSqlRawAsync` **before** `_catalog.ListAsync`, so it throws one statement early.

The fault therefore has to deny **exactly one table** — `Figures` — leaving `Categories`
readable so the page gets far enough in:

```powershell
sqlcmd -S $S -d catalog -G -b -Q "DENY SELECT ON OBJECT::dbo.Figures TO [id-mh-user001-dotnet];"
Start-Sleep -Seconds 8
foreach ($i in 1..4) {
  try { Invoke-WebRequest "$base/?search=deny$i" -UseBasicParsing -TimeoutSec 45 }
  catch { Write-Output "root$i=$([int]$_.Exception.Response.StatusCode)" }   # 500
  Start-Sleep -Seconds 5
}
```

**Restore — `REVOKE` removes the `DENY`; it does not remove the role grant:**

```powershell
sqlcmd -S $S -d catalog -G -b -Q "REVOKE SELECT ON OBJECT::dbo.Figures TO [id-mh-user001-dotnet];"
Invoke-WebRequest "$base/"       -UseBasicParsing   # 200, ~147 KB
Invoke-WebRequest "$base/readyz" -UseBasicParsing   # 200 {"status":"ready",...}
```

Observed: `500` × 4, then `/` back to `200` (147,492 bytes) and `/readyz` ready.

### Side finding — the readiness probe is too shallow

Throughout step 2, with **every** catalog read returning `500`, `/readyz` kept returning
`200 {"status":"ready","checks":{"database":"ready","import":"ready"}}`. The database
check proves only that a connection can be opened and `SELECT 1` executed; the fault
removed *data-plane* role membership, which `SELECT 1` does not exercise. A load balancer
would have kept routing to a totally broken app. This is the mirror image of the
"container healthy while `/readyz` 503" trap the workshop already teaches, and the
material does not warn about it.

---

## 4. Ingestion delay — plan for it

**~200 seconds** wall clock from the last request to the signals being queryable, measured
across three separate injection rounds. Nothing appeared at 60 s. Query at **300 s** to be
safe. An attendee who queries immediately, sees zero rows and starts "fixing" the app will
waste the rest of the session.

## 5. KQL, per signal, per table

Resolve the workspace by name first (§0a). Then:

```kusto
// success signals — AppTraces
AppTraces
| where TimeGenerated > ago(3h)
| extend sig = tostring(split(Message, ' ')[0])
| where sig in ('http.server.request','catalog.import.completed','catalog.performance.completed')
| summarize recordCount = count(), lastSeen = max(TimeGenerated) by sig
```

```kusto
// failure signals — AppExceptions
AppExceptions
| where TimeGenerated > ago(3h)
| extend sig = tostring(split(tostring(Properties['OriginalFormat']), ' ')[0])
| where sig in ('catalog.import.failed','catalog.database.failed',
                'catalog.query.failed','catalog.performance.failed','exception')
| summarize recordCount = count(), lastSeen = max(TimeGenerated) by sig
```

```kusto
// all eight at once, across both tables
union withsource = SrcTable AppTraces, AppExceptions
| where TimeGenerated > ago(3h)
| extend fmt = tostring(Properties['OriginalFormat'])
| extend sig = iff(isempty(fmt), tostring(split(Message, ' ')[0]), tostring(split(fmt, ' ')[0]))
| summarize recordCount = count(), lastSeen = max(TimeGenerated) by SrcTable, sig
| order by recordCount desc
```

### KQL gotchas that cost me round trips

- **`$table` is not resolvable** in this workspace — use `union withsource = T ...`.
- **`of` and `last` are reserved words.** `extend of = ...` and `summarize last = ...`
  both fail with `SYN0002 … could not be parsed`. Use `fmt` / `lastSeen`.
- `Properties` is a dynamic column in `AppTraces`/`AppExceptions` but a JSON **string**
  in some views — `tostring(Properties['x'])` is safe either way.

## 6. Diagnostic-settings prerequisite

None of the above returns anything unless the Container App's diagnostic settings ship
`ContainerAppConsoleLogs`/`ContainerAppSystemLogs` **and** the app is exporting via the
Azure Monitor OpenTelemetry distro to the `dotnet` workspace's Application Insights
resource. Verify before injecting faults, not after:

```kusto
AppMetrics | where TimeGenerated > ago(30m)
| extend svc = tostring(Properties['service.name']) | summarize by svc
```

## 7. Order of operations that worked

1. Confirm the app is healthy and the correct workspace resolves to `mh-catalog-dotnet`.
2. Step 1 (import) — no undo needed.
3. Step 2 (role removal) — **restore and verify before moving on.**
4. Step 3 (single-table `DENY`) — **`REVOKE` and verify `/` returns 200.**
5. Wait 300 s.
6. Run the union query; confirm all eight signal names are present.
7. Only then render telemetry evidence.

Steps 2 and 3 must not overlap. Running them together exhausts the connection pool, at
which point the failures surface as
`InvalidOperationException: Timeout expired … obtaining a connection from the pool`
instead of `SqlException`, `catalog.database.failed` stops firing (it is guarded by
`exception is DbException` at `FigureCatalogService.cs:53`), and the evidence is worse
than if you had injected nothing.

---

## 8. Verified outcome

Measured `2026-08-27T20:52Z` (UTC), workspace `log-mh-user001-dotnet`
(`9523ac07-57a2-44d0-bebc-00fb52336e1d`), window `ago(180m)`, using the union query in §5.
All eight `telemetry.logs` signal names are present, so `handoff.py:270` set equality is
satisfiable:

| signal | table | recordCount | last seen (UTC) |
| --- | --- | --- | --- |
| `http.server.request` | AppTraces | 4203 | 20:48:24 |
| `catalog.import.completed` | AppTraces | 2 | 19:46:14 |
| `catalog.performance.completed` | AppTraces | 1632 | 20:28:00 |
| `catalog.import.failed` | AppExceptions | 3 | 20:29:12 |
| `catalog.database.failed` | AppExceptions | 7 | 20:46:39 |
| `catalog.performance.failed` | AppExceptions | 2 | 20:29:19 |
| `catalog.query.failed` | AppExceptions | 4 | 20:46:39 |
| `exception` | AppExceptions | 10 | 20:46:39 |

`catalog.query.failed` = 4 and the `catalog.database.failed` increment from 3 to 7 are
both attributable to step 3 alone. Before step 3 the signal had **zero** records after two
full rounds of the step-2 fault, which is the evidence for the §3 claim that the coarse
fault cannot reach it.

**Post-conditions confirmed:** `db_datareader` and `db_datawriter` both present for
`id-mh-user001-dotnet`; no `DENY` remaining on `dbo.Figures`; `/` returns `200` with a
147,492-byte body; `/readyz` returns `200 {"status":"ready","checks":{"database":"ready","import":"ready"}}`.
