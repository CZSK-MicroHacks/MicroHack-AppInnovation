# Manual .NET control-arm feedback

## Scope and provenance

- Path: `manual-dotnet`
- Immutable workshop baseline: `4bf59f7ee8dae11259d73ba5a5d7cb0e3355c4af`
- Execution boundary: local build, test, and evidence preparation only; no Azure resource
  deployment or mutation was authorized for this control arm.
- Start: 2026-08-27 18:12 CEST

## Timing

| Activity | Elapsed | Result |
| --- | ---: | --- |
| Read shared and manual path material, establish constraints | 4 min | Complete |
| First native test attempt | 7 s | Blocked by missing ASP.NET Core 8 runtime |
| Install session-local .NET SDK 8.0.424 | 2 min | Complete |
| Native .NET test rerun | 10 s | 42 passed |
| Acceptance contract/reconciliation checks | 21 s | 106 passed; 3 participant-tree assertions failed |
| Build the local amd64 container | 5 min 44 s | Complete |
| Inspect the container contract | <1 s | User, port, seed, image path, and health client passed |

These measurements cover only the local control-arm work. Time to a running Container App
is **not measured** because deployment was explicitly out of scope.

## Material feedback

1. The instructions assume the participant is on the provisioned Windows VM. A control
   runner on macOS needs to infer that VM-only baseline, SQL Server acceptance, migration,
   and protected-parameter steps cannot be reproduced locally.
2. The publish instructions conflict with the workshop provenance requirement. Recording
   `git rev-parse HEAD` as `sourceCommit` would identify the delivery branch rather than
   the immutable workshop baseline; this run records
   `4bf59f7ee8dae11259d73ba5a5d7cb0e3355c4af`.
3. The local prerequisite says .NET SDK 8.0.424, but the host may resolve a newer SDK and
   still fail at test execution because the ASP.NET Core 8 shared runtime is absent. The
   repository's Common Errors entry provides the necessary session-local SDK workaround.
4. The manual path says to author a digest-pinned Dockerfile but does not explain how to
   resolve trusted MCR digests. That is a nontrivial manual step and should include an
   explicit `docker buildx imagetools inspect` example.
5. The repository reconciliation suite assumes `dotnet/Dockerfile` exists only in the
   reference tree, so the documented participant action of adding that file makes the
   full repository guard fail by design. The participant validation command should exclude
   this maintainer-only topology assertion or provide a participant mode.
6. The pinned ASP.NET runtime image does not contain `curl`, although the required health
   check invokes it. The Dockerfile must install a health-check client or use a different
   probe strategy.
7. Deployment material currently implies the Container Apps environment can be created.
   In this subscription, policy prevents every public IP allocation, so the deployment
   fails before application validation. This should be called out as a known environment
   limitation rather than diagnosed by each participant.
8. The manual path's useful learning is concentrated in understanding ordering and safety
   gates. Most elapsed time is operational setup, protected-input handling, and waiting on
   Azure rather than application modernization.

## Comparison notes

- Roughly typed by the participant for the local portion: one Dockerfile plus evidence
  notes; no application code changes were required.
- Tests caught an environment/runtime mismatch before any container or Azure work.
- Container inspection caught the missing health-check client before ACR or deployment.
- I would keep infrastructure deployment, database import, identity assignment, and
  traffic changes behind explicit human approval even when using an assistant.
- I would use this sequence on a real estate migration, but automate repeatable evidence
  capture and preflight subscription policy before the workshop starts.
