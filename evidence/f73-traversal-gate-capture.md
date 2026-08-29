# F-73 — verbatim capture, pre-fix harness

All output below was produced against the harness as shipped at archive commit
`4bf59f7ee8dae11259d73ba5a5d7cb0e3355c4af`, before any facilitator remedy landed.
Reproducible by checking out the commit that contains this file.

- Archive provenance: `4bf59f7ee8dae11259d73ba5a5d7cb0e3355c4af`
- `sourceCommit`: `47acf263d3320fa3bb41d5469fc3c7428a393fca`
- `imageDigest`: `sha256:647e2500591da30fcedc831ea787ed682aa7b5bd4389fbebdd041f034fe089ee`
- Release revision: `ca-mh-user001-dotnet--release-47acf263d332`
- Measurement instant: 2026-02-25T20:52:00Z (UTC)
- Executed on: `vm-dotnet-user001`, via `az vm run-command invoke --command-id RunPowerShellScript`

## 1. Acceptance result — 21 of 22, one failing check

From `evidence/acceptance-report.json` (`profile: full`, `status: failed`), the only
check not in `passed`:

```
name:   image-storage
status: failed
detail: invalid images=[], unknown=404, malformed=404, traversal={'raw-forward-existing': 200,
        'raw-backslash-existing': 200, 'encoded-forward-existing': 200,
        'encoded-backslash-existing': 200, 'double-encoded-existing': 404,
        'raw-route-alias': 401, 'encoded-route-alias': 401}
```

`runner.py:561-566` requires all seven traversal targets to return 404. Six cannot.

## 2. Raw TCP+TLS socket probe — proves the app never receives the unsafe target

Issued from `vm-dotnet-user001` by writing the HTTP request line literally over a
`SslStream`, so no client library could normalize the path on our behalf:

```
/images/../healthz        => HTTP/1.1 200 OK  {"status":"healthy"}
/images/../nosuchroute    => HTTP/1.1 404 Not Found
/perftest\catalog         => HTTP/1.1 401 Unauthorized {"status":"unauthorized","error":"invalid_api_key"}
/images/%2e%2e%2fhealthz  => HTTP/1.1 200 OK  {"status":"healthy"}
/healthz                  => HTTP/1.1 200 OK  {"status":"healthy"}
```

`/images/../healthz` returns the **healthz body** and `/perftest\catalog` returns a
response from the perftest endpoint's own auth filter. Both prove the request was
routed to a different path than the one requested: the dot-segment and the backslash
were resolved upstream of Kestrel by the Container Apps ingress.

## 3. The application rejects all seven targets when reached directly

`OriginalRequestTargetMiddleware` is registered first in the pipeline
(`Program.cs:140`) and is present in the deployed commit `47acf263`.
`OriginalRequestTargetMiddlewareTests` asserts 404 for these targets against a direct
Kestrel `TestServer`:

```
Passed!  - Failed: 0, Passed: 8, Skipped: 0, Total: 8, Duration: 24 ms
```

Identical inputs: **404 against Kestrel, 200/401 through Container Apps ingress.**

No mitigation exists at the application layer, because the application never sees the
unsafe target. No mitigation exists at the platform layer either:
`az containerapp ingress update` exposes only `--type`, `--transport`,
`--target-port`, `--exposed-port` and `--allow-insecure`. Envoy's `normalize_path`
and `merge_slashes` are not surfaced by the Container Apps API.

## 4. Consequence — the handoff cannot be produced

`tests/acceptance/catalog_acceptance/handoff.py:1180-1181`, inside `validate_handoff`:

```python
if report.profile != "full" or report.status != "passed":
    inconsistencies.append("acceptance evidence must be a full passing report")
```

`image-storage` can never pass on Container Apps, so `status` is permanently
`failed`, so `evidence/modernization-contract.json` can never validate, so
Challenges 2-6 have no input. **Challenge 1 is unfinishable as shipped.**

## 5. Two further gates fire before that one

Recorded because each is an independent defect, and because they mean the literal
string in section 4 is not reachable from a clean run even after the traversal
problem is understood.

**5a. `render-handoff` cannot find `az` on Windows.** With the stock `PATH`:

```
EXIT=4
{"command": "render-handoff", "error": {"code": "tool-failed",
 "message": "external tool could not complete: az"}, "exitCode": 4,
 "schemaVersion": "1.0.0", "status": "failed"}
```

`az` is installed as `az.cmd`; the subprocess launch does not honour `PATHEXT`, so the
interpreter cannot see it. Worked around locally with a shim directory prepended to
`PATH`.

**5b. The topology gate rejects a VM that is mid-extension-update.** With the shim in
place and the VM reporting `provisioningState: Updating` because a platform extension
was re-applying:

```
EXIT=3
{"command": "render-handoff", "error": {"code": "precondition-failed",
 "message": "Azure resource is not provisioned: /subscriptions/7bc68c68-f434-49ad-ab3e-b883ec39da86/
 resourceGroups/rg-user001/providers/Microsoft.Compute/virtualMachines/vm-dotnet-user001"},
 "exitCode": 3, "schemaVersion": "1.0.0", "status": "failed"}
```

The VM was running and healthy throughout; only its provisioning state was transient.
The same condition returns `Conflict: Run command extension execution is in progress`
from `az vm run-command`, which is the only channel available for driving the VM in
this delivery — so the chapter intermittently locks itself out for reasons unrelated
to the attendee's work.

**5c. Two required telemetry log signals can never be observed.** The telemetry
contract requires eight log signals including `catalog.query.failed` and
`catalog.performance.failed`. Both are emitted by the application only when a catalog
or performance query throws. Neither the acceptance harness nor any documented step
induces such a failure, so an attendee following the material cannot observe them —
and `validate_handoff` checks telemetry at `:1145`, before the acceptance gate at
`:1180`. The only way to satisfy the validator without inducing a fault by hand is to
write the telemetry evidence by hand, which is precisely the fabrication this
workshop exists to prevent.

## Honest statement of scope

This file records what was observed. The acceptance gate string in section 4 is
established by the combination of a real `status: failed` report and the quoted
source, not by a captured run that reached line 1180 — sections 5a-5c document why no
run could reach it. Nothing here is reconstructed or assumed.
