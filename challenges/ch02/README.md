# Challenge 2: prove load and autoscaling

## Goal

Use the checked-in Azure Load Testing plan against the application already
bound by `evidence/modernization-contract.json`. Prove that its existing
Container Apps revision:

- serves one sampler: HTTPS `GET /perftest/catalog`;
- completes 40 virtual users for 300 seconds with zero errors;
- has one replica before load, two or three during the observed run timestamps,
  and one after load;
- remains within the authoritative P4 scale contract: rule `http`, type `http`,
  minimum `1`, maximum `3`, and `concurrentRequests` `50`;
- produces database load above baseline; and
- returns exact HTTP `200` responses from the handoff `/healthz` and `/readyz`
  URLs after recovery.

Do not deploy or update the application, create a replacement revision, change
traffic, or edit infrastructure. Delayed post-run scale-out does not satisfy the
challenge.

## Frozen protocol

Consume these interfaces directly:

- `workshop/contracts/shared-challenges.json` schema `1.2.0`;
- `loadEvidenceProtocol` in that registry;
- `workshop/contracts/load-evidence-capture.schema.json` version `1.0.0`;
- `workshop/contracts/load-test-evidence.schema.json` version `1.1.0`;
- `evidence/modernization-contract.json` version `1.4.0`;
- `tests/load/load-test.yaml`; and
- `tests/load/catalog-load.jmx`.

The two contract examples and the raw fixtures are sanitized structure only.
Their zero identities, timestamps, URLs, hashes, and observations are not live
proof.

The same producer rejoins all six handoff slices:

| Slice IDs | Stack | Required database signal |
| --- | --- | --- |
| `manual-dotnet`, `copilot-rewrite-dotnet`, `copilot-modernization-dotnet` | `dotnet-sqlserver` | `app_cpu_billed`, `Total` |
| `manual-java`, `copilot-rewrite-java`, `copilot-modernization-java` | `java-postgresql` | `cpu_percent`, `Maximum` |

## Evidence boundary

Capture the exact Azure responses without rewriting them:

- `evidence/load/raw/test-run.json`;
- `evidence/load/raw/container-app.json`;
- `evidence/load/raw/replicas.json`, queried for the `Replicas` metric with
  `Maximum`, `PT1M`, and the exact handoff `revisionName` dimension; and
- `evidence/load/raw/database.json`, using the metric selected above.

Hash every raw response and both checked-in load assets into the canonical
`evidence/load/capture.json`. Include the exact Load Testing resource ID,
baseline time, metric resource IDs/windows, scale observation time, recovery
time, recent Container App ARM `etag`, and exact handoff health/readiness URLs
and statuses.

Do not manually create or edit `evidence/load-test-report.json` or any of the
five normalized observations. The frozen renderer must produce them:

```bash
cd tests/acceptance
uv --no-config run catalog-render-load-evidence --capture ../../evidence/load/capture.json --handoff ../../evidence/modernization-contract.json --output ../../evidence/load-test-report.json --repository-root ../..
```

Then run the common fail-closed validator:

```bash
uv --no-config run catalog-validate-challenge-evidence load ../../evidence/load-test-report.json --handoff ../../evidence/modernization-contract.json --contracts ../../workshop/contracts --repository-root ../..
```

The challenge fails on any missing or changed raw file, digest drift, redirect,
non-`DONE` run, nonzero error count, wrong duration/users, stale or mismatched
ARM configuration, unfiltered replica series, delayed scale-out, out-of-bounds
replica, wrong database signal, database peak not above baseline, manual
normalized evidence, or unsuccessful recovery.

The API key must enter Azure Load Testing only through `GetSecret`. Never store
it in YAML, JMX, commands, raw responses, the capture manifest, or rendered
evidence.

[Solution steps](/solutions/ch02/README.md)
