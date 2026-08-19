# Challenge 1: Choose one modernization path

Modernize the .NET/SQL Server or Java/PostgreSQL application selected in Challenge 0.
Choose exactly one path below. All six combinations converge on the same Azure target,
acceptance suite, evidence bundle, and downstream challenges.

| Path | Use it to | Challenge | Stack-specific solution |
| --- | --- | --- | --- |
| 1A — Manual | Learn each database, container, storage, and deployment boundary directly | [Manual modernization](../ch01-manual/README.md) | `solutions/ch01-manual/{dotnet,java}/README.md` |
| 1B — Standard Copilot rewrite | Build a bounded replacement against the frozen behavioral oracle | [Copilot rewrite](../ch01-copilot-rewrite/README.md) | `solutions/ch01-copilot-rewrite/{dotnet,java}/README.md` |
| 1C — Copilot modernization | Use the pinned IDE assessment and reviewed task workflow | [Copilot modernization](../ch01-copilot-modernization/README.md) | `solutions/ch01-copilot-modernization/{dotnet,java}/README.md` |

## Shared entry gate

Before starting, record the selected stack and exact source commit, prove the matching
P3 VM baseline is healthy, and read:

- [`workshop/contracts/challenge-paths.json`](../../workshop/contracts/challenge-paths.json)
  for the exact path/stack target and evidence set.
- [`infra/README.md`](../../infra/README.md) for the shared P4 target and staged order.
- [`tests/acceptance/README.md`](../../tests/acceptance/README.md) for behavioral,
  database, image, runtime-test, telemetry, and handoff verification.

Stop rather than invent a workaround if the selected stack, database family, image
provider, source identity, or required tooling differs from the registry.

## Common exit and rejoin gate

Every path must produce the seven shared evidence artifacts and its four path-specific
artifacts listed in the registry. The final handoff must preserve the selected path,
reference a nonempty repository-contained rollback runbook, and validate before Challenge 2:

```bash
cd tests/acceptance
UV_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple \
  uv --no-config run python -m catalog_acceptance.handoff_cli \
  ../../evidence/modernization-contract.json \
  --contracts ../../workshop/contracts \
  --repository-root ../..
```

Passing requires the matching managed database, one non-root ACA application container,
an immutable ACR digest, the frozen external image provider, complete corpus verification,
full acceptance, native runtime tests, and correlated traces, metrics, and logs. Assessment,
prompts, or generated plans never replace executable proof.
