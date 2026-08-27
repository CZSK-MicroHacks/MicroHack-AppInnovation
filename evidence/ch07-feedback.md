# Challenge 7 — attendee feedback (both variants)

**Attendee run:** worktree `michalmar-ch07-and-wrapup`, branch
`michalmar-ch07-and-wrapup`. Start 2026-08-27 18:41 CEST.
**Azure:** sub `7bc68c68-…`, `rg-user001`, `admin@MngEnvMCAP372348…`, read-only calls only.
**Both variants executed as design-only** (Ch07 ships no `solutions/` and no validator).

## Headline

Challenge 7 is the **most robust chapter in the workshop** precisely because it asks for
*design*, not for a green exit code. Both variants can be completed truthfully with no
deployment — which is why they were reachable on a day when the Azure release path was
blocked. The flip side, relevant to the wrap-up: **neither variant emits a single scorecard
row**, so a strong Ch07 answer adds nothing measurable to the before/after story.

## Provenance / environment note (not a workshop defect)

Ch07 + wrap-up content lives on branch `rewrite-integration`, but this worktree was cut
from `main` (which only carries ch01–ch05). I merged `rewrite-integration` in to obtain the
chapters, tests, and contracts. One acceptance test then fails —
`test_every_provisioning_script_is_reachable_from_a_document` (`assert len(readable) >= 200`;
the merged tree has 198 docs). This is a **branch-topology artifact of the merge**, not a
Ch07/wrap-up defect, and an attendee working on `rewrite-integration` would not see it. All
Ch07- and scorecard-relevant tests pass.

## Instruction clarity

Both READMEs are unusually good: they lead with the *trade* (control → what it breaks →
compensating path → proof → rollback) rather than a checklist, and the "If it goes wrong"
tables name real failure modes. The innovation README's insistence that *abstention is the
feature* is the sharpest single instruction in the whole workshop.

All cross-links in all three chapters resolve after the merge:
`ch06-sre-agent`, `infra/README.md`, `docs/Design.md`, `docs/Troubleshooting.md`,
`data/manifest.json`, `solutions/reference/README.md`, `docs/CostEstimate.md`,
`workshop/contracts/README.md` — checked, all present.

## Per-step timing

| Step | Elapsed | Result |
| --- | ---: | --- |
| Recon: merge content, verify links, locate tests/fixtures | 12 min | Content on `rewrite-integration`; merged in |
| Run `-k "ch07 or wrapup"` acceptance | 1 min | **0 tests selected** (see defect D-1) |
| Enterprise: read real `rg-user001` identities/roles/KV/Postgres | 8 min | Concrete matrix built from live reads |
| Enterprise design write-up (Control 2) | 15 min | `ch07-extension/enterprise-identity-secrets.md` |
| Verify role-definition GUIDs against `az` | 2 min | 2 GUIDs I had wrong, corrected |
| Innovation: read corpus schema (`catalog.json`, `manifest.json`) | 5 min | 198 figures, `productId`==filename stem |
| Innovation design write-up (Scope 1) | 15 min | `ch07-extension/innovation-grounded-index.md` |
| Verify a worked example against the corpus | 3 min | First example was wrong; corrected (see below) |

## Defects and dead ends

- **D-1 (acceptance selector is a no-op).** The assignment's own suggested gate,
  `uv --no-config run pytest -k "ch07 or wrapup"`, selects **0 of 517** tests — no test
  function or file contains "ch07" or "wrapup" in its name. Ch07 and the wrap-up have **no
  dedicated acceptance tests**. The scorecard fixtures are only exercised indirectly by
  `test_contract_assets.py::test_demo_steps_claimed_cold_runnable_have_a_checked_in_fixture`
  and friends (keyword `fixture`/`mttr`/`pain`), which pass. Net: an attendee who trusts the
  suggested command will believe they "ran the Ch07 tests" while running nothing.

- **D-2 (precondition artifact does not exist).** Both variants open with *"Start from a
  valid `evidence/modernization-contract.json`."* That file exists in **no** worktree —
  only `workshop/contracts/modernization-contract.example.json` (all-zero placeholder
  SHAs/subscriptions) and the schema. Because Ch07 has no validator, nothing enforces the
  precondition, so the chapter is reachable anyway — but the opening instruction is
  literally unsatisfiable for the no-deploy arms. `ch07-enterprise/README.md:27` and
  `ch07-innovation/README.md:31-34`.

- **D-3 (F-48 is a real, live trap on this subscription).** The Key Vault
  `kv-cat-uxd57ffjbgfma` holds `PERFTEST-API-KEY` (hyphens); the app wants
  `PERFTEST_API_KEY` (underscores). KV object names can't contain underscores, so a naive
  Key Vault reference 404s and a fallback-having app looks healthy with a blank key. The
  enterprise "Identity and secrets" control walks straight into this; I folded it in as an
  explicit negative test (T5) rather than a footnote.

- **D-4 (design gap surfaced by live reads).** The workload identity `id-mh-user001-java`
  has **no** Key Vault role and **no** Postgres Entra grant today (only `AcrPull` +
  `Storage Blob Data Reader`). So the app as deployed cannot read its secret via managed
  identity at all — meaning a human-managed secret must still be in play. Good news for the
  chapter: the control has real work to do; the current state is genuinely pre-hardening.

## Plausible-but-WRONG-that-looked-green moments (my own)

- While drafting the innovation worked example I wrote *"space explorer with a star-map
  tablet → Comet Trail Navigator"*. It reads fine, but "star map" lives in that figure's
  **`imagePrompt`** (which the design explicitly does **not** index) — the indexed
  description that actually contains "forbidden star maps" belongs to a **different** figure
  (`Nebula Chart Smuggler`, Space Pirates). Verified against `data/catalog.json` and
  corrected. This is exactly the failure the innovation chapter warns about: a fluent,
  confident citation that a set-membership check against *retrieved* records would reject.
  It is worth noting how easy it was to produce by hand.
- I cited two Azure role-definition GUIDs from memory (Container Apps Contributor, Key Vault
  Secrets Officer) and both were wrong; caught only by round-tripping through
  `az role definition list`. A reviewer skimming the matrix would not have caught them.

## Verdict

Ch07 (both variants) is completable and honest as design-only. The temptation to fabricate
is **low** here because there is no green light to chase — the review is the grade. The
opposite is true of the wrap-up (see `wrapup-feedback.md`).
