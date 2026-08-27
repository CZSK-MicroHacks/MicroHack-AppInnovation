# Candidate wrap-up scorecard — attendee submission

> **Reconcile against the facilitator delivery log before anything final.** This is a
> candidate, not a closed result. Every cell is either measured, facilitator-attested (and
> labelled so), or explicitly *not measured*. No cell is a guess.

## Evidence triple (per the observer tripwire)

For the stack that completed the central challenge, **.NET / Azure SQL**, all three fields
were captured — the first two independently verified by me via read-only `az`, the third
from an observational clock:

| Field | Value | How obtained |
| --- | --- | --- |
| `sourceCommit` | `47acf263d3320fa3bb41d5469fc3c7428a393fca` | ACR tag on the deployed digest (F-29: tag == pushed modernized commit; **distinct** from baseline `4bf59f7e…`, so this image is genuinely modernized, not a rebuilt baseline) |
| `imageDigest` | `sha256:647e2500591da30fcedc831ea787ed682aa7b5bd4389fbebdd041f034fe089ee` | `az containerapp revision list` — the **single active revision** `--0000001`; I cite the **digest, not the revision name**, per the `Multiple`-mode misattribution warning |
| `measurementInstant` | revision live `2026-08-27T19:36:21Z`; first 2xx `2026-08-27T19:21:21.921Z` (facilitator-attested) | revision `createdTime` via `az` (observational); first-2xx from the delivery log |

I could **not** corroborate live serving from my own host at ~21:40Z (curl to
`ca-mh-user001-dotnet.…azurecontainerapps.io/readyz` returned `000` — app likely scaled to
zero, or my host lacks egress). The digest and revision are `az`-verified; **serving and the
migration row-counts are facilitator-attested delivery-log facts**, labelled as such below.

## The honest headline

**One of two stacks completed the workshop's central challenge.** Do not round up.

- **.NET / Azure SQL — complete.** `ca-mh-user001-dotnet` deployed (external ingress), 198
  figures / 20 categories migrated from the source VM's SQL Server into Azure SQL, 198 images
  in Blob served through the workload managed identity, `catalog-migrate verify` exit 0 with
  `topologyValidated: true`. *(deploy/migration facts: facilitator delivery log; digest +
  modernized-commit: my `az` reads.)*
- **Java / PostgreSQL — partial.** `ca-cicd-user001-java` is live but its **catalog is
  empty**, blocked on a migration-verification failure. Reached *deploy-the-app* but **not**
  *migrate-the-data*. (Consistent with what I read directly: internal-only env, single
  revision, no seeded data.)

## The scorecard (.NET arm, filled honestly)

| # | What you measured | Legacy baseline | After modernization | Status / provenance |
| --- | --- | --- | --- | --- |
| 1 | Catalog response, median | *not measured* | *not measured* | No `ch00-pain-dotnet.json` (VM baseline never captured); no `evidence/load/raw/test-run.json` (Ch2 load run never produced) |
| 2 | Pipeline lead time | *not measured* | *not measured* | No `cicd-report.json` exists. The only Ch3 artifact (`psychic-memory/evidence/cicd/identity-summary.json`) **self-labels "NOT a cicd-report.json — no workflow run occurred"** |
| 3 | Human steps to ship a fix | *not measured* | *not measured* | Same — no workflow run, no `startedAt`/`approvedAt` to read |
| 4 | Rollback time | *not measured* | *not measured* | Same — no `rollbackAttemptedAt`/`rollbackCompletedAt` |
| 5 | Behaviour under load | *not measured* | *not measured* | No `load-test-report.json` |
| 6 | Time to answer "why slow?" | *not measured* | *not measured* | Ch4 clock readings never taken |
| 7 | MTTR | *not measured* | *not measured* | No `ch06-mttr.json`. A sibling arm wrote **`ch06-mttr.BLOCKED.md`** — "cannot be produced honestly, no file written" (no SRE Agent resource, no fired/resolved alert in the sub) |
| 8 | Security posture | *not assessed* (Ch0 ran none) | *not measured* | No `defender-report.json` |
| 9 | Secrets in application config | credential in `C:\MicroHack\secrets\dotnet.json` (Ch0 scenario) | **removed — managed identity + Key Vault on the deployed PaaS** *(real for .NET, not design)* | `ch00/README.md:130,156`; deployed `ca-mh-user001-dotnet` uses workload MI for Blob/DB |
| 10 | Patching the host | app + DB on one Windows VM (Ch0 scenario) | **no host to patch — Container Apps + managed Azure SQL** *(real for .NET)* | `ch00/README.md:150`; deployed managed PaaS |
| 11 | Cost to run, per day | **$5.13** | **$6.67** (.NET / Azure SQL) — *+30%, the expected direction* | `docs/CostEstimate.md:198-200` (list-price estimate, not measured) |
| ★ | **Central challenge: deploy + migrate + verify** *(not a scorecard row, but the actual goal)* | app+DB on a VM, no migration | **done — 198/20 migrated, `topologyValidated:true`** | facilitator delivery log; image is a modernized commit (`az`) |

### What this scorecard shows

- **8 of 11 defined rows are *not measured*** even though .NET completed the central
  challenge — because the scorecard's rows are weighted toward Ch2–Ch6 peripheral
  measurements that this delivery never produced, while the **actual central achievement
  (deploy + migrate + verify) is not even a row.** The closest proxies are rows 9–10, and for
  the .NET arm those flipped from *design* to *real deployed outcome*.
- Rows 9–10 are the only two that improved from my earlier design-only draft, and they did so
  because .NET genuinely deployed — not because anything new was measured.
- Row 11 (cost) is the one row fillable with clean provenance, and the chapter itself flags
  it as an estimate, correctly noting the +30% is expected, not a failed migration.

**A scorecard that is 8/11 blank is the honest artifact of a delivery where the central
challenge succeeded for one stack and the surrounding measurement chapters did not run. It
reads as visibly incomplete — which is correct.**
