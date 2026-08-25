# Challenge 1 solution: select the matching stack and path

**Open this if** you are stuck on Challenge 1, you are out of time, or you finished and
want to compare your route against the reference one.

Challenge 1 has six bounded reference implementations — one per stack, per path. These
are complete runbooks: every command in executable form, with the guards, prompts, and
evidence steps that the challenge only describes. Reading one costs you the discovery, so
try the challenge first.

Choose the solution that matches both values in `evidence/ch00-selection.json` and the
participant's selected path:

| Path | .NET/SQL Server | Java/PostgreSQL |
| --- | --- | --- |
| Manual rebuild | [Manual .NET](../ch01-manual/dotnet/README.md) | [Manual Java](../ch01-manual/java/README.md) |
| GitHub Copilot-assisted rewrite | [Copilot rewrite .NET](../ch01-copilot-rewrite/dotnet/README.md) | [Copilot rewrite Java](../ch01-copilot-rewrite/java/README.md) |
| GitHub Copilot modernization | [Copilot modernization .NET](../ch01-copilot-modernization/dotnet/README.md) | [Copilot modernization Java](../ch01-copilot-modernization/java/README.md) |

Do not combine artifacts from different cells. All six solutions consume the shared
target in `infra/main.bicep` and must finish by validating
`evidence/modernization-contract.json` with the common handoff CLI.

Every path arrives at the same place, and that is the point of the chapter: a Container
Apps revision pinned to an immutable digest, a managed database holding 198 figures and
20 categories, 198 images served from Azure storage, a retained rollback revision, and a
validated handoff. What differs is what you learned getting there — which is the subject
of the [debrief](../../challenges/ch01/README.md#debrief-compare-the-three-paths).

If you want to see the finished shape rather than the route to it,
[`solutions/reference/`](../reference/README.md) holds the modernized application for
both stacks, including the container definitions.

## Rejoining with a golden handoff

When a participant uses a facilitator-provided golden rejoin bundle, select the bundle
for the same stack, validate it unchanged, and continue at Challenge 2. A golden bundle
does not retroactively complete the participant's path-specific evidence.

This is a normal outcome, not a failure. The realistic time estimates for all three paths
exceed the workshop schedule; the golden handoff exists so that running out of time in
Challenge 1 does not cost you Challenges 2 through 7.

---

**Challenge:** [Challenge 1: get the catalog off the virtual machine](../../challenges/ch01/README.md) ·
**Previous solution:** [Challenge 0](../ch00/README.md) ·
**Next solution:** [Challenge 2](../ch02/README.md)
