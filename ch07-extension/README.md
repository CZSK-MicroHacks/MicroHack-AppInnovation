# Challenge 7 extension workspace

Disposable design artifacts for **both** Challenge 7 variants. Produced **outside**
`evidence/` on purpose — Challenge 7's one hard rule is that the frozen handoff and every
required chapter's evidence stay byte-identical. Nothing here deploys or mutates a shared
Azure resource.

| Variant | Menu item | Artifact |
| --- | --- | --- |
| Enterprise hardening | #2 Identity and secrets (Java/PostgreSQL) | [`enterprise-identity-secrets.md`](enterprise-identity-secrets.md) |
| Innovation | #1 Grounded contract and index (Java/PostgreSQL) | [`innovation-grounded-index.md`](innovation-grounded-index.md) |

Both are grounded in **real, read-only** facts from `rg-user001` / `data/`, not invented.
Attendee feedback (clarity, defects, timings, gaps) is in
[`../evidence/ch07-feedback.md`](../evidence/ch07-feedback.md).
