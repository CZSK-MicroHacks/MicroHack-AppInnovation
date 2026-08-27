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

## Answering the facilitator's Ch7-specific asks (instruction quality / invented / knew-Azure)

- **Instruction quality:** Ch7 is the best-specified chapter I touched — it grades on a review
  rubric, not a green check, so there is no automation to satisfy and nothing to game. Both
  variants state their deliverable clearly. The one real gap is **D-2**: the enterprise variant
  consumes `evidence/modernization-contract.json` as an unstated precondition — and (see
  `wrapup-feedback.md`, F-73) that file is *never emitted on the honest path* because the Ch1
  handoff gate hard-stops on Envoy-normalised traversal probes. So Ch7-enterprise's input
  literally cannot exist for an attendee who did Ch1 by the book. I proceeded design-only, which
  is legitimate for this chapter, but a stricter reading of the enterprise variant is blocked
  upstream.
- **Ambiguities:** the `-k` acceptance selector (D-1) matches **zero** tests, which reads as "no
  coverage" but is actually "design-only, nothing to run." Mildly confusing; not a defect.
- **Anything I had to invent:** nothing. Both artifacts are grounded in real reads (`az` for
  identity/roles, `data/catalog.json` for the corpus). Where I *tried* to shortcut from memory,
  I was **wrong twice** (a citation phrase that lives in `imagePrompt` not the index; two
  role-definition GUIDs) — both caught only by round-tripping through the real source. That is
  the honest signal: the chapter is safe *because* it forces you to ground claims, and unsafe
  the moment you trust recall.
- **Anything that only worked because I already knew Azure:** the enterprise variant assumes
  fluency in RBAC role-definition names, managed-identity vs. service-principal semantics, and
  RBAC-vs-access-policy Key Vault. An attendee without that background could hand-wave a
  plausible-but-wrong identity matrix and nothing in Ch7 would catch it — the review is the only
  gate. F-48 (KV object `PERFTEST-API-KEY` vs env `PERFTEST_API_KEY`) is a live trap that only
  surfaces if you know KV names cannot contain underscores.
