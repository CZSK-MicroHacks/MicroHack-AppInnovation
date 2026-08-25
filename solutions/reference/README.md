# Reference implementation: the modernized target

This directory holds the **finished** version of both application stacks — what your
code should look like after Challenge 1. It exists so that facilitators can demonstrate
the target, and so that participants who get stuck have something concrete to compare
against.

| Stack | Legacy starting point | Modernized target here |
| --- | --- | --- |
| .NET / SQL Server | [`dotnet/`](../../dotnet/README.md) — .NET 8, SQL Server 2022 Express | [`dotnet/`](dotnet/README.md) — .NET 10, Azure SQL Database |
| Java / PostgreSQL | [`java/`](../../java/README.md) — OpenJDK 17, Spring Boot 3.5, PostgreSQL 18 | [`java/`](java/README.md) — OpenJDK 21, Spring Boot 4.0, PostgreSQL Flexible Server |

## Read this before you copy anything

Challenge 1 is the workshop. Copying this directory wholesale skips the only chapter
that teaches modernization, and it will not teach you anything about your own codebase
when you go home.

Use it the way you would use a worked answer at the back of a textbook:

- **You are stuck on one specific thing** — a connection string shape, a Dockerfile
  layer, how managed identity is wired. Look at that one file, understand why it is
  written that way, then write your own.
- **You have finished and want to compare** — diff your implementation against this one
  and work out why the choices differ. Both can be correct.
- **You are the facilitator** — this is your demo target and your fallback.

## What changed from legacy to modern

All three Challenge 1 paths converge here, so this is the same destination whether you
rebuilt by hand or drove the work with GitHub Copilot.

| Concern | Legacy baseline | Modernized target |
| --- | --- | --- |
| Framework | .NET 8 / Spring Boot 3.5 | .NET 10 / Spring Boot 4.0 |
| Hosting | Windows VM, in-process | Linux container on Azure Container Apps |
| Container image | none — you author the Dockerfile in Challenge 1 | `Dockerfile` present here, non-root, pinned base |
| Database | Local SQL Server / PostgreSQL | Azure SQL Database / PostgreSQL Flexible Server |
| Image storage | Local disk | Azure Blob Storage (`AzureBlobImageStore`) |
| Credentials | Connection strings in configuration | Managed identity; no application passwords |
| Telemetry | Local log file | Azure Monitor exporter alongside OTLP |

The Dockerfiles live here rather than in the legacy baselines on purpose: authoring the
container image is part of the Challenge 1 exercise.

## Behavior is frozen

The modernized application must remain behaviorally identical to the legacy one. Same
catalog identities, routes, import transaction, health endpoints, image corpus, and
telemetry contract. That is what the acceptance suite checks, and it is why a handoff
from any of the six stack/path combinations is interchangeable downstream.

Run the shared gate from the repository root:

```bash
cd tests/acceptance
uv --no-config run pytest -q
```

## Related

- [Challenge 1 shared target](../../challenges/ch01/README.md)
- [Solution 1 overview](../ch01/README.md)
- [Troubleshooting](../../docs/Troubleshooting.md)
