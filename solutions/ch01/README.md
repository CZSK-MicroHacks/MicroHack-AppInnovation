# Challenge 1 solution: select the matching stack and path

Challenge 1 has six bounded reference implementations. Choose the solution that matches
both values in `evidence/ch00-selection.json` and the participant's selected path:

| Path | .NET/SQL Server | Java/PostgreSQL |
| --- | --- | --- |
| Manual rebuild | [Manual .NET](../ch01-manual/dotnet/README.md) | [Manual Java](../ch01-manual/java/README.md) |
| GitHub Copilot-assisted rewrite | [Copilot rewrite .NET](../ch01-copilot-rewrite/dotnet/README.md) | [Copilot rewrite Java](../ch01-copilot-rewrite/java/README.md) |
| GitHub Copilot modernization | [Copilot modernization .NET](../ch01-copilot-modernization/dotnet/README.md) | [Copilot modernization Java](../ch01-copilot-modernization/java/README.md) |

Do not combine artifacts from different cells. All six solutions consume the shared
target in `infra/main.bicep` and must finish by validating
`evidence/modernization-contract.json` with the common handoff CLI.

When a participant uses a facilitator-provided golden rejoin bundle, select the bundle
for the same stack, validate it unchanged, and continue at Challenge 2. A golden bundle
does not retroactively complete the participant's path-specific evidence.
