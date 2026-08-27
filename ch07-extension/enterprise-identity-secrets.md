# Challenge 7 — Enterprise: Identity and secrets (menu item 2)

**Stack chosen:** `Java/PostgreSQL` (Azure Database for PostgreSQL Flexible Server).
**Control chosen:** #2, *Identity and secrets* — replace every remaining human-managed
runtime secret with Entra workload identity or a Key Vault reference.

This is a **design** deliverable. It is deliberately produced **outside** `evidence/`, and it
deploys nothing: per the chapter, the required handoff and every chapter report must stay
byte-identical. Everything below is validated against the *real* `rg-user001` resources by
read-only `az` calls, not invented.

## Current state (read from Azure, 2026-08-27)

| Resource | Name | Fact observed |
| --- | --- | --- |
| Container Apps env | `cae-mh-user001-java` | `vnetConfiguration.internal = true` (F-47: app URL is VNet-private) |
| Container App | `ca-cicd-user001-java` | `identity.type = None`, no `registries`, no `secrets` block |
| Workload identity | `id-mh-user001-java` | principalId `2710ce5a-d69d-4aea-b1bd-06b4cd7396cd` |
| Deployer identity | `id-catalog-github` | principalId `223831a3-f621-45ff-9dfe-44c7deb96ffe` (GitHub OIDC) |
| Registry | `acruser001java5yruws2l` | ACR |
| Database | `psql-mh-user001-java-5yruws2l` | PostgreSQL Flexible Server, private DNS `private.postgres.database.azure.com` linked to the VNet |
| Key Vault | `kv-cat-uxd57ffjbgfma` | `enableRbacAuthorization = true`, `publicNetworkAccess = Enabled`, holds secret `PERFTEST-API-KEY` |
| Observability | `appi-mh-user001-java`, `log-mh-user001-java` | App Insights + Log Analytics |

Two gaps fall straight out of the read:

1. **The workload identity `id-mh-user001-java` has no Key Vault role and no PostgreSQL
   Entra grant.** Its only assignments are `Storage Blob Data Reader` on
   `stuser001java5yruws2l/catalog-images` and `AcrPull` on the registry. So the app as
   deployed *cannot* read `PERFTEST-API-KEY` through managed identity + RBAC, and cannot
   authenticate to Postgres as a token identity. Any secret it uses today is therefore
   coming from app settings / a container secret, i.e. a human-managed secret — exactly
   what this control must remove.
2. The container app currently shows `identity.type = None`, so *no* identity is even
   attached to bind a Key Vault reference to. The first design step is attaching
   `id-mh-user001-java` as a user-assigned identity.

## The trade (the five boxes the chapter demands)

| Control you want | What it breaks | How you keep that working | How you prove it works | How you undo it at 3am |
| --- | --- | --- | --- | --- |
| Every runtime secret becomes an Entra token or a Key Vault reference resolved by managed identity | (a) App can't read the secret until the role assignment + attachment both exist; (b) Postgres password auth stops if you flip to Entra-only; (c) Key Vault is `publicNetworkAccess=Enabled` today — tightening it to the VNet cuts the deployer's route | (a) Attach `id-mh-user001-java`, grant `Key Vault Secrets User` at the secret scope; (b) keep a break-glass SQL admin during cutover, add the identity as an Entra role on the DB *before* removing the password; (c) add a Key Vault private endpoint + the same private DNS pattern already used for Postgres, and give CI an approved egress or a `Key Vault Secrets Officer` grant on the deployer identity | `az containerapp show ... secretRef` resolves; app `/readyz` green; `SELECT current_user` returns the identity; a negative test: remove the role → startup fails with a *named* 403, not a silent fallback | Re-grant the password secret as a container secret and detach the identity; role assignments are one `az role assignment delete` each; documented in the rollback block below |

## Identity → resource matrix (target state)

`<uai>` = `id-mh-user001-java` (workload), `<dep>` = `id-catalog-github` (deployer).

| Identity | Resource (real name) | Role | Role definition ID | Scope | Justification |
| --- | --- | --- | --- | --- | --- |
| `<uai>` | `kv-cat-uxd57ffjbgfma` secret `PERFTEST-API-KEY` | Key Vault Secrets User | `4633458b-17de-408a-b874-0445c86b69e6` | secret-level | App reads the perf-test key at runtime via a Key Vault reference; no secret in config |
| `<uai>` | `psql-mh-user001-java-5yruws2l` | (Entra DB role, not Azure RBAC) | n/a — Postgres `azure_pg_admin`/login role mapped to the identity's `clientId` `7de25695-…` | database login | Token auth replaces the password in the JDBC URL |
| `<uai>` | `acruser001java5yruws2l` | AcrPull *(already present)* | `7f951dda-4ed3-4680-a7ca-43fe172d538d` | registry | Image pull; keep |
| `<uai>` | `stuser001java5yruws2l/catalog-images` | Storage Blob Data Reader *(already present)* | `2a2b9908-6ea1-4ae2-8e65-a410df84e7d1` | container | Image bytes; keep |
| `<dep>` | `ca-cicd-user001-java` | Container Apps Contributor *(already present)* | `358470bc-b998-42bd-ab17-a7e34c199c0f` | app | Deploy revisions; keep |
| `<dep>` | `acruser001java5yruws2l` | AcrPush *(already present)* | `8311e382-0749-4cb8-b61a-304f252e45ec` | registry | Push images; keep |
| `<dep>` | `kv-cat-uxd57ffjbgfma` | Key Vault Secrets Officer *(new, only if CI seeds the secret)* | `b86a8fe4-44ce-4948-aee5-eccb2c155cd7` | vault | Lets the pipeline create/rotate `PERFTEST-API-KEY`; scoped to the vault, time-boxed |

Least privilege holds: the workload identity gets **read** on one secret, not vault-wide;
the deployer gets **officer** only if it seeds secrets, otherwise it gets nothing new.

## The F-48 landmine, made explicit

Key Vault object names may not contain underscores. The real secret is
`PERFTEST-API-KEY` (hyphens). The application, however, wants an environment variable
`PERFTEST_API_KEY` (underscores — env vars can't contain hyphens cleanly in all shells).
The Key Vault reference must therefore **rename** on the way in:

```
env:
  - name: PERFTEST_API_KEY                 # what the app reads
    secretRef: perftest-api-key            # container secret name (lower-hyphen)
# container secret bound to:
#   keyVaultUrl: https://kv-cat-uxd57ffjbgfma.vault.azure.net/secrets/PERFTEST-API-KEY
#   identity:    id-mh-user001-java
```

Skip the rename and the app looks up `PERFTEST_API_KEY` in the vault, gets a 404, and —
if the code has any fallback — reads an empty key and *looks* healthy. That is the
"green but wrong" failure this whole workshop is about; it is called out here as a test
case, not a footnote.

## Deployment ordering (this control fails at startup, not at deploy)

1. Attach `id-mh-user001-java` to `ca-cicd-user001-java` (`identity.type` → `UserAssigned`).
2. Grant `Key Vault Secrets User` on the secret **before** the revision that references it.
3. Add the Postgres Entra login for the identity **before** removing the password secret.
4. *Then* roll the revision that swaps app-setting secrets for `secretRef`s.
5. Only after `/readyz` is green on the new revision, delete the plaintext app settings.

Reverse the order and the app pulls a revision that references a secret it has no role to
read; Container Apps marks the revision failed and holds traffic on the old one — safe, but
confusing at 3am, which is why the order is written down.

## Verification tests (executable)

| # | Test | Expected |
| --- | --- | --- |
| T1 | `az containerapp revision show` → env `PERFTEST_API_KEY` resolves via `secretRef` | non-empty, sourced from KV |
| T2 | Remove `Key Vault Secrets User`, restart revision | startup fails with an explicit KV 403 in logs; `/readyz` red — **not** a blank-key success |
| T3 | `SELECT current_user` over the app's connection | returns the identity, no password in the JDBC URL |
| T4 | `git grep -iE "password|api.?key|secret" src/ | grep -v secretRef` | no plaintext secret in source, image layers, workflow vars, or logs |
| T5 | Rename mismatch check: bind `PERFTEST_API_KEY` (underscore) as the KV object name | KV 404 — proves F-48 is guarded |

## Rollback and cleanup

```bash
# undo: re-attach a container secret with the raw value, detach identity role
az role assignment delete --assignee 2710ce5a-d69d-4aea-b1bd-06b4cd7396cd \
  --role "Key Vault Secrets User" \
  --scope <vault>/secrets/PERFTEST-API-KEY
# revert Postgres to password auth (break-glass admin), then:
az containerapp identity remove -g rg-user001 -n ca-cicd-user001-java --user-assigned id-mh-user001-java
```

No shared resource is deleted (the VMs, the env, ACR, Postgres, the vault, `lt-catalog`
all stay). Only two role assignments and one identity attachment are added, and both are
one-command reversible.

## Validation plan (unchanged app still passes)

The chapter's hard rule: the required runtime, migration, acceptance, telemetry, and
handoff validators must produce byte-identical output afterwards. Because this design
deploys nothing here, that is satisfied trivially — but the plan for a real deployment is:

1. `cd tests/acceptance && uv --no-config run pytest -q` — full suite, unchanged.
2. Re-run the handoff validator against `evidence/modernization-contract.json` — the
   contract is unchanged (identity attachment and role grants are not handoff fields).
3. Diff `evidence/` before/after: must be empty.

## Honest gap found while doing this

The chapter's **"Before you start"** says *"Start from a valid
`evidence/modernization-contract.json`."* That file **does not exist** in this worktree,
nor in any sibling arm's `evidence/` — only `workshop/contracts/modernization-contract.example.json`
(all-zero placeholder SHAs/subscriptions) and the schema. A design-only chapter that opens
by requiring an artifact the no-deploy arms never produced is reachable only because it has
no validator to enforce that precondition. I designed against the **example** contract's
shape and the **real** `rg-user001` resources instead, and recorded the substitution here.
