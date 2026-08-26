# Cost and capacity estimate

**Before you book a date, do three things:** run the capacity preflight (it now prices the
network footprint too), set a subscription budget alert, and put a teardown date in the
calendar with an owner's name on it. The single largest cost risk in this workshop is not
the workshop — it is the week after it, when nobody destroys anything.

## How to read these numbers

| Label | Means |
| --- | --- |
| **Retail API** | Taken from the public Azure Retail Prices API on **2026-08-24**, `currencyCode=USD`, region `swedencentral` unless the meter says otherwise. The exact meter name is given so you can re-query it. |
| **Derived** | Arithmetic on a Retail API price plus a quantity taken from this repository's infrastructure code. The quantity's source file is cited. |
| **Estimated** | An assumption about participant behaviour (how many hours a database is active, how much telemetry an app emits). The assumption is stated so you can substitute your own. |
| **UNVERIFIED** | Could not be confirmed from the Retail Prices API. **Confirm with the Azure Pricing Calculator** before you quote it to anyone who signs invoices. |
| **Pricing page** | Taken from Microsoft's own pricing page for the service, which states billing periods that the Retail Prices API does not carry. Cited with the URL — and, where the live page has since dropped the statement, with the dated snapshot that still has it. |

Line items are rounded to cents for display and subtotals are computed from the unrounded
values, so a subtotal does not always equal the column as printed; where the gap is larger
than rounding explains, the row's Basis cell gives the arithmetic that reproduces it.

Prices are list retail without any Enterprise Agreement, CSP, MACC, or reservation
discount. They exclude tax. Re-derive them for your own region and agreement — a Sweden
Central number is not a West Europe number.

To re-query any meter yourself:

```bash
curl -s "https://prices.azure.com/api/retail/prices?currencyCode=USD&\$filter=serviceName%20eq%20'Azure%20Bastion'%20and%20armRegionName%20eq%20'swedencentral'"
```

## Unit prices

### Per-participant base infrastructure (facilitator-provisioned, always on)

| Meter | Price | Source |
| --- | --- | --- |
| Windows VM `Standard_D2as_v5` | **$0.184 / hr** | Retail API — `Virtual Machines` / `Dasv5 Series Windows` / `D2as v5`. Windows rate; the Linux rate for the same size is $0.092 |
| Premium SSD P10 (127 GiB OS disk) | **$21.68 / month** (≈ $0.0297 / hr) | Retail API — `Storage` / `Premium SSD Managed Disks` / `P10 LRS Disk`. Disk size from `baseInfra/terraform` `os_disk_size_gb = 127`, which lands in the P10 tier |
| Azure Bastion, Basic gateway | **$0.19 / hr** | Retail API — `Azure Bastion` / `Basic` / `Basic Gateway` |
| NAT gateway | **$0.045 / hr** | Retail API — `NAT Gateway` / `Standard` / `Standard Gateway`. Billed from a **global** meter (`armRegionName = Global`), not a regional one |
| NAT gateway data processed | $0.045 / GB | Retail API — same product, `Standard Data Processed`. Volume is workload-dependent and excluded below |
| Standard static public IP | **$0.005 / hr** | Retail API — `Virtual Network` / `IP Addresses` / `Standard IPv4 Static Public IP` |
| Bastion data transfer out | $0.087 / GB | Retail API — `Azure Bastion` / `Basic Data Transfer Out`, highest tier. Excluded below |

**Quantities per participant** (from `baseInfra/terraform/modules/user_environment/`): 2 VMs,
2 OS disks, 1 Bastion host, 1 NAT gateway, **2** Standard public IPs — one for Bastion
(`pip-userNNN`) and one for the NAT gateway (`pip-nat-userNNN`).

### Per-participant modernized workload (created during Challenge 1)

| Meter | Price | Source |
| --- | --- | --- |
| Container Apps, active vCPU | $0.000024 / vCPU-second | Retail API — `Azure Container Apps` / `Standard vCPU Active Usage` |
| Container Apps, idle vCPU | $0.000003 / vCPU-second | Retail API — `Standard vCPU Idle Usage` |
| Container Apps, memory (active and idle) | $0.000003 / GiB-second | Retail API — `Standard Memory Active Usage` / `Standard Memory Idle Usage` |
| Container Apps, requests | $0.40 / million | Retail API — `Standard Requests` |
| Azure Container Registry, Basic | **$0.1666 / day** (≈ $5.00 / month) | Retail API — `Container Registry` / `Basic` / `Basic Registry Unit`. SKU from `infra/modules/environment.bicep:235` |
| Azure SQL, General Purpose serverless Gen5, 1 vCore | **$0.573934 / vCore-hour** | Retail API — `SQL Database` / `GP – Serverless – Compute Gen5` / `1 vCore`. SKU and `autoPauseDelay: 60` from `infra/modules/sql.bicep:33-40` |
| Azure SQL storage | $0.13685 / GB / month | Retail API — `General Purpose Data Stored` |
| PostgreSQL Flexible Server, Burstable `Standard_B1ms` | **$0.0199 / hr** | Retail API — `Azure Database for PostgreSQL` / `Flexible Server Burstable BS Series Compute` / `B1MS`. SKU from `infra/modules/postgresql.bicep:19-21` |
| PostgreSQL storage (32 GB configured) | $0.1369 / GB / month | Retail API — `Flex Server Storage` / `Storage Data Stored`. Size from `infra/modules/postgresql.bicep:45` |
| Private endpoint | **$0.01 / hr** each | Retail API — `Virtual Network` / `Virtual Network Private Link` / `Standard Private Endpoint` (global meter). Two per participant: storage and database |
| Blob storage, Hot LRS | $0.0184 / GB / month | Retail API — `Storage` / `General Block Blob v2` / `Hot LRS Data Stored`. The 198-image corpus is well under 1 GB, so this rounds to zero |
| Log Analytics ingestion | **$2.99 / GB** | Retail API — `Log Analytics` / `Analytics Logs Data Ingestion` |
| Log Analytics retention beyond the free period | $0.13 / GB / month | Retail API — `Analytics Logs Data Retention` |
| Application Insights | — | Workspace-based; its data is billed through the Log Analytics ingestion meter above, not separately |
| Azure Load Testing resource (`Azure App Testing`) | **$10.00 per resource per month** | Retail API — `Azure App Testing` / `JMeter` / `JMeter Load Testing Resource`, unit of measure `1`. The API does not carry the period; the **Pricing page** does, and it is monthly. See [The Load Testing fee is monthly](#the-load-testing-fee-is-monthly) |
| Load-test virtual-user hours, included | $0.00 / VU-hour | Retail API — `JMeter Virtual User Included Usage`. **50 VU-hours per resource per month**, per the Pricing page note below |
| Load-test virtual-user hours, additional | $0.15 / VU-hour | Retail API — `JMeter Virtual User Additional Usage` (drops to $0.06 above 10,000 VU-hours) |

The Challenge 2 run is 40 virtual users for 300 seconds — **3.33 VU-hours**, against 50
included per resource per month. The virtual-user meter is effectively free here; the
per-resource fee is not. Since 2026-03-01 a test run is billed a floor of 10 virtual users
per engine for a minimum of 10 minutes, which for this run works out to 1.67 VU-hours —
below the 3.33 actually used, so the floor does not bite and the figure above still stands.

#### The Load Testing fee is monthly

This line used to be labelled UNVERIFIED, and with thirty resources the label was no longer
survivable: the gap between "once" and "per month" is the gap between $300 and $300 *every
month the resources exist*, on a row you hand to a budget owner. It is resolved.

**The $10.00 is a monthly fee, per resource, charged in full for a resource that exists
during any part of a calendar month.** Microsoft's own pricing page said so in the row and
again in its FAQ:

> How am I charged for the initial 'Load Testing Resource' and how do the included Virtual
> User Hours (VUH) work? For each 'Load Testing Resource' that is active during **any part
> of a month** you will be charged the monthly fee, and have access to the included 50 VUH.

That wording is from the [Azure Load Testing pricing
page](https://azure.microsoft.com/en-us/pricing/details/load-testing/) as
[archived on 2024-08-14](https://web.archive.org/web/20240814151631/https://azure.microsoft.com/en-us/pricing/details/load-testing/),
where the table row reads `Load Testing Resource — $10.00 per month includes 50 Virtual
User Hours (VUH) per month`. Two things corroborate that it still describes today's
billing. The archived regional spread is *identical* to what the Retail API returns now —
$10.00 everywhere, $12.50 in `usgov-virginia`. And the `JMeter Virtual User Included Usage`
meter is still live at $0.00/hour with an effective date of 2025-03-01; an *included-usage*
meter is meaningless without the fee that buys the inclusion, so the whole
fee-plus-allowance model survived the rename to Azure App Testing.

**What is still open, stated plainly.** The live pricing page no longer shows that row or
that FAQ entry at all — the Azure Load Testing table on it now lists only the two VU-hour
tiers. So the possibility that the fee was quietly retired and the meter left behind cannot
be excluded from public sources, and if that is what happened the line is $0.00 rather than
$300.00/month. Everything above says it was not, but say so honestly rather than round it
away.

**The single check that settles it**, and it takes one minute once you have provisioned:
open Cost Analysis on the subscription, filter to meter `JMeter Load Testing Resource`
(meter ID `0dae6d10-8474-58f8-8439-26f7a005d8dd`), and look at the first day after the
`infra/perf-testing.bicep` deployments land. A charge there is the monthly fee; no charge
by the second day means it was retired. Record the answer in the run log — it is a repo
constant once someone has looked, and nobody should have to re-derive this.

**The consequence you must act on either way**: "any part of a month" is not prorated. A
delivery that provisions on 30 January and tears down on 4 February touches two calendar
months and is billed **twice — $600.00, not $300.00** — for five days of use. Schedule
provisioning and teardown inside one calendar month, or budget the second month
deliberately.

### Facilitator-level and subscription-wide

| Meter | Price | Source |
| --- | --- | --- |
| SRE Agent unit | **$0.11 per agent unit** | Retail API — `Foundry Tools` / `Azure Agent Unit` / `SRE Agent Unit`, `swedencentral`, effective 2026-01-01 |
| Defender for Servers, Plan 2 | **$0.02 / node / hr** | Retail API — `Microsoft Defender for Cloud` / `Defender for Servers` / `Standard P2 Node`. Subplan `P2` is required by `workshop/contracts/defender.json` |
| Defender for Servers, Plan 1 | $0.00672 / node / hr | Retail API — `Standard P1 Node`. Not the plan this workshop requires |
| Defender CSPM | $0.007 / node / hr | Retail API — `Defender CSPM` / `Standard Node`, meter region `Global` |
| Defender for Containers, vCore | $0.00941 / vCore / hr | Retail API — `Defender for Containers` / `Standard vCore vCore Pack` |
| Defender for Containers, image scan | **$0.29 / image** | Retail API — `Defender for Containers` / `Standard Images` |
| Defender for SQL | $15.00 / node / month (also exposed as $0.020161 / hr) | Retail API — `Defender for SQL` / `Standard Node` and `Standard Instance` |
| Defender for open-source relational databases | $15.00 / node / month | **UNVERIFIED for PostgreSQL Flexible Server specifically** — the `Defender for MySQL` node price is used as a proxy. Confirm with the Azure Pricing Calculator |
| GitHub Copilot Business seat | ~$19 / user / month | **UNVERIFIED** — not an Azure meter. Confirm on GitHub's pricing page |
| GitHub Team plan (needed for private-repo environment protection) | per-user monthly | **UNVERIFIED** — not an Azure meter. Confirm on GitHub's pricing page |

## Per participant, per 24-hour day

### Base infrastructure

This is one participant's environment for one day, and it is the foundation the rest of
this document stands on: the cohort figures scale it by participants and by hours at
*both* rates — 65.5 h with both VMs running, then 47.5 h with one deallocated — never at
a single rate across the whole 113 h window. An error here is an error in every figure
below it.

| Line | Quantity | Per day | Basis |
| --- | --- | ---: | --- |
| Windows VMs | 2 × 24 h @ $0.184 | **$8.83** | Derived |
| Premium OS disks | 2 × $21.68/month × 24/730 | **$1.43** | Derived |
| Bastion Basic gateway | 1 × 24 h @ $0.19 | **$4.56** | Derived |
| NAT gateway | 1 × 24 h @ $0.045 | **$1.08** | Derived |
| Standard public IPs | 2 × 24 h @ $0.005 | **$0.24** | Derived |
| **Total, both VMs running** | | **$16.14** | |
| **Total, after the Challenge 0 deallocation** | | **$11.72** | Derived: $16.14 − one VM's 24 h @ $0.184 = $16.14 − $4.42 = $11.72. That VM's compute stops; its disk keeps billing |

**The $4.42 between those two totals is the workshop's first cost lesson, and the
participant is the one who earns it.** Deallocating the legacy VM they did not choose is a
single command in [Challenge 0](../challenges/ch00/README.md), and it takes
$4.42 ÷ $16.14 ≈ 27% off the daily bill for the rest of the workshop — for a machine
nobody had opened. Nothing is deleted and nothing is lost: the disk keeps billing
precisely because the VM can be restarted. Every argument later in this document is that
same one at a larger scale.

Data transfer (Bastion egress, NAT processed GB) is excluded — it is workload-dependent
and small relative to the fixed hourly meters.

### Modernized workload, once Challenge 1 completes

Assumes the container app runs a single 0.5 vCPU / 1 GiB replica
(`infra/modules/environment.bicep:635-636`, `minReplicas: 1` at `:673`), active for 8
hours and idle for 16, and that the app emits about 0.2 GB of telemetry per day.

| Line | .NET / Azure SQL | Java / PostgreSQL | Basis |
| --- | ---: | ---: | --- |
| Container Apps compute | $0.69 | $0.69 | Derived; **before** the monthly free grant, which will absorb much of a single small replica |
| Managed database | $4.74 | $0.62 | Derived. SQL assumes 8 active vCore-hours/day; PostgreSQL Burstable has no auto-pause and bills 24 h |
| Container registry, Basic | $0.17 | $0.17 | Derived |
| Private endpoints (2) | $0.48 | $0.48 | Derived |
| Log Analytics ingestion | $0.60 | $0.60 | **Estimated** at 0.2 GB/day |
| **Total** | **$6.67** | **$2.56** | Unrounded: $0.6912 + $4.7354 + $0.1666 + $0.48 + $0.598 = $6.6712 ≈ $6.67; Java is the same less SQL: $6.6712 − $4.7354 + $0.6216 = $2.5574 ≈ $2.56 (rounding each row to cents makes the .NET column visibly sum to $6.68) |

**The database choice moves the number more than anything else a participant does.**
Serverless Azure SQL at 8 active hours costs roughly eight times the Burstable PostgreSQL
tier. It is not wrong — serverless bills nothing while paused, and 60 minutes of idle is
all it takes — but a room that leaves the app under load all day will see the SQL half of
the cohort cost noticeably more.

### Legacy VM versus modernized workload

The two tables above are the halves of the before-and-after cost question, and they are
only a comparison once they are put on the same page. Per participant, per 24-hour day,
counting only the compute and storage that carries the catalog:

| Line | Per day | Basis |
| --- | ---: | --- |
| **Legacy** — one Windows VM plus its Premium OS disk | **$5.13** | Derived: 24 h @ $0.184, plus $21.68/month × 24/730. Half of the two-VM and two-disk rows above |
| **Modernized** — Java / PostgreSQL | **$2.56** | The modernized-workload total above |
| **Modernized** — .NET / Azure SQL | **$6.67** | The modernized-workload total above |

Read that honestly, because it does not point one way:

- **Java / PostgreSQL runs at roughly half the legacy VM** — $2.57 per participant per
  day less.
- **.NET / Azure SQL runs at roughly 30% more than the legacy VM** — $1.54 per
  participant per day more, almost all of it the $4.74 serverless Azure SQL line under the
  8-active-hours assumption above. Move that assumption and the row moves with it.

Two exclusions apply in both directions. Bastion, the NAT gateway, and the public IPs are
workshop access scaffolding for private VMs, not something the legacy application needed
in the retailer's own datacentre. And the legacy figure prices only the machine — not the
patching, the backup, the certificate renewal, or the out-of-hours release window, which
are the costs Challenges 3, 5, and 6 measure in minutes and findings rather than in
dollars.

So the defensible claim is narrow, and it is the one to make to a room: at list price, on
this workload, the modernized catalog costs somewhere between half and about 1.3 times the
VM it replaces, and which end of that range you land on is decided by the database tier
rather than by the move to containers. Participants record their stack's row in the
[wrap-up scorecard](../challenges/wrapup/README.md).

### Cohort of 30

| Line | Per day |
| --- | ---: |
| Base infrastructure, both VMs (day 1 before Challenge 0 completes) | **$484.14** |
| Base infrastructure, after the Challenge 0 deallocation | **$351.66** |
| Modernized workload, assuming a 50/50 stack split | **$138.45** |
| Azure Load Testing resources, 30 × $10 — one per participant, [decided, not shared](Facilitator.md#decide-these-before-you-book-a-date) | **$300.00 per calendar month**, not per day — and **$600.00** if provisioning and teardown fall either side of a month end |

## Worked example: Friday provision → Wednesday teardown

The realistic window. You provision on Friday afternoon so that the VM images have the
weekend to settle and the Defender plans have their 24 hours; you run Monday and Tuesday;
you tear down Wednesday morning after the last person has exported their evidence.

**Provision Friday 17:00 → destroy Wednesday 10:00 = 113 hours.** The Challenge 0
deallocation lands around Monday 10:30, so both VMs run for the first 65.5 hours and one
runs for the remaining 47.5.

| Line | Per participant | × 30 | Basis |
| --- | ---: | ---: | --- |
| Windows VM compute | $32.84 | $985.20 | Derived from the split above |
| Premium OS disks (2 × 113 h) | $6.71 | $201.30 | Derived |
| Bastion (113 h) | **$21.47** | **$644.10** | Derived |
| NAT gateway (113 h) | $5.08 | $152.40 | Derived |
| Public IPs (2 × 113 h) | $1.13 | $33.90 | Derived |
| **Base subtotal** | **$67.24** | **$2,017.23** | 30 × the unrounded per-participant base of $67.2409 = $2,017.23; the rows above are rounded to cents for display, so they visibly sum to $2,016.90 |
| Modernized workload, .NET / Azure SQL | $12.90 | — | $3.4177 + $9.48 = $12.8977 ≈ $12.90; derived below |
| Modernized workload, Java / PostgreSQL | $4.53 | — | Derived over the same window: $2.56/day × 42.5/24 = $4.5333 ≈ $4.53. Burstable PostgreSQL never pauses, so there is no active-hour allowance to add |
| **Modernized subtotal, 50/50 split** | — | **$261.45** | 15 participants on each stack: 15 × ($12.90 + $4.53) = $261.45 |
| Azure Load Testing resources | $10.00 | $300.00 | Monthly fee, one resource per participant. Assumes Friday and Wednesday fall in the same calendar month |
| **Azure subtotal, excluding Defender and SRE Agent** | | **≈ $2,579** | $2,017.23 base + $261.45 modernized + $300.00 Load Testing = $2,578.68 ≈ $2,579 |

**Azure SQL is the one line that does not scale with wall-clock time.** Everything else in
the modernized stack bills by the hour, so the non-database half of the .NET row is just
$6.67 − $4.74 = $1.93 a day stretched over the window: $1.93 × 42.5/24 = **$3.4177**.
Serverless SQL bills only while active, at $4.74 ÷ 8 = **$0.5925** per active vCore-hour.
The window touches three calendar days, but [the agenda](Agenda.md#the-schedule) schedules
work on only two of them — Monday to 17:00, Tuesday from 09:00 to 17:00 — and Wednesday is
teardown only, so the database auto-pauses after its 60 idle minutes and accrues nothing.
Two days at the eight-hour allowance is 16 active vCore-hours, or **$9.48**, and $3.4177 +
$9.48 = **$12.8977 ≈ $12.90**.

Monday carries a whole day's allowance even though the window opens at 15:30, and that is
the assumption in this row most worth arguing with. It holds because the database is
created and worked during Challenge 1 itself, before the window opens, and because
Challenge 2 — a load test — is the last block of the day. Move it and the row moves with
it: charge Monday only the 1.5 hours that fall inside the window and the row is $9.05
instead of $12.90.

If that Friday and Wednesday straddle a month end, the Load Testing line doubles to
**$600.00** and the subtotal becomes **≈ $2,879** — the fee is charged for any part of a
month, so five days of use spanning two months costs two months. Nothing else in this table
changes, because everything else is billed by the hour.

Then the paid services the facilitator turns on:

| Line | Cohort total | Basis |
| --- | ---: | --- |
| Defender for Servers P2, over the same 113 h | **$107.10** | Derived: $0.02/node/hr × (30 × 2 VMs × 65.5 h + 30 × 1 VM × 47.5 h) |
| Defender for Containers image scans, ~3 images each | **$26.10** | Derived at $0.29/image; actual count depends on how many builds each participant pushes |
| Defender for SQL, 15 participants | ~$34.83 | Derived from the **monthly** $15.00 instance meter, prorated: 15 × 113 × $15.00 ÷ 730 = $34.83. **UNVERIFIED proration** if your subscription bills a whole month per node instead, in which case it is $225.00 |
| Defender for open-source relational databases, 15 participants | ~$34.83 | Same proration: 15 × 113 × $15.00 ÷ 730 = $34.83, and the price itself is UNVERIFIED |
| Defender CSPM | see note | **UNVERIFIED** — CSPM is billed per *billable resource*, not per VM, and the count depends on what else is in the subscription |
| SRE Agent, **one shared** agent for 8 hours | **$3.52** | Derived: 4 agent units × $0.11 × 8 h |
| SRE Agent, **one agent per team**, 30 teams, 8 hours | **$105.60** | Derived |

**Total for a 30-person, Friday-to-Wednesday delivery: roughly $2,750–$2,950**, assuming
Friday and Wednesday fall in the same calendar month, plus the GitHub plan and Copilot
seats, which are not Azure meters. Call it **$92–$98 per participant** for the Azure side.
Straddle a month end and the Load Testing line doubles: **$3,085–$3,190**, or **$102–$107**
each.

## Where the money actually goes

**Bastion, the NAT gateway, and the public IPs are provisioned once per participant and
cannot be turned off.** In the worked example they are $27.68 per participant — **41% of
the entire base infrastructure bill** — and, unlike the VMs, there is no deallocation that
stops them. They bill for every one of the 113 hours whether anyone is connected or not.

| Meter | Share of the base bill in the worked example |
| --- | ---: |
| VM compute | 49% |
| **Bastion** | **32%** |
| Premium OS disks | 10% |
| **NAT gateway** | **8%** |
| **Public IPs** | **2%** |

Three consequences for planning:

1. **Shortening the window is the cheapest saving available.** Every hour you cut removes
   $0.245 per participant of Bastion + NAT + IP charge that no deallocation can touch.
   Provisioning Saturday instead of Friday saves roughly $180 across a cohort of 30.
2. **The Challenge 0 deallocation saves less than people assume.** It removes $4.42 per
   participant per day — real, but under a third of the daily base cost. Do not let anyone
   conclude the environment is nearly free once the second VM is off.
3. **A shared Bastion in a hub network would be the largest structural saving.** The
   current design gives every participant their own Bastion host at $0.19/hr; a single
   hub-hosted Bastion peered to the participant networks would collapse $644 to roughly
   $21 plus peering charges across a 30-person cohort. That is an infrastructure change,
   not a facilitator decision, and it is recorded here as an observation rather than an
   instruction.

## The cost of forgetting teardown

This is the number to put in the budget alert.

| Left running for a month | Per participant | × 30 |
| --- | ---: | ---: |
| Base infrastructure, one VM still running | **$356.53** | **$10,695.90** |
| Base infrastructure, both VMs still running | **$490.85** | **$14,725.50** |
| Modernized workload, idle (Azure SQL auto-paused) | ~$28.59 | ~$428.85 (15 participants) |
| Modernized workload, idle (PostgreSQL Burstable, no auto-pause) | ~$43.12 | ~$646.80 (15 participants) |
| **SRE Agent, one per team, never deleted** | **$321.20** | **$9,636.00** |

Two of those deserve to be said plainly:

- **An un-destroyed cohort costs roughly $11,700–$15,900 per month.** The base
  infrastructure rows plus both idle modernized halves: $10,695.90 + $428.85 + $646.80 =
  $11,771.55 with one VM deallocated, $14,725.50 + $428.85 + $646.80 = $15,801.15 with
  both still running, and the SRE Agent line below is on top of that. Both bounds are
  rounded outward, so the band never flatters the table it summarises. It is more than the
  entire workshop, every month, for infrastructure nobody is using.
- **The SRE Agent bills for existing, not for working.** Four agent units at $0.11 each,
  every hour, for as long as the resource exists. Stopping the agent does not stop the
  charge; only `az resource delete` does. Thirty forgotten agents cost $9,636 a month —
  the single most expensive thing anyone can forget in this workshop.

### Set the budget alert before you provision

`baseInfra/terraform` already creates a subscription budget when the Defender foundation
is enabled (`defender_budget_amount`, `defender_budget_notification_emails`). If you are
not enabling that foundation, create the budget by hand anyway, before provisioning. Size
it at roughly **1.5× the worked-example total** with alert thresholds at 50%, 90%, and
100%, and put a human's mailbox on it — not a distribution list nobody reads.

The teardown procedure, including everything Terraform does not own, is in
[the facilitator guide](Facilitator.md).
