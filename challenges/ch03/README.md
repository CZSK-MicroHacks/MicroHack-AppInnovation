# Challenge 3: immutable CI/CD and revision promotion

## Goal

Implement the workflow selected by the frozen handoff stack:

| `source.stack` | Workflow | Application build |
| --- | --- | --- |
| `dotnet-sqlserver` | `.github/workflows/catalog-dotnet.yml` | .NET solution and `dotnet/Dockerfile` |
| `java-postgresql` | `.github/workflows/catalog-java.yml` | Maven Wrapper and `java/Dockerfile` |

The workflow is manual (`workflow_dispatch`) and has two immutable inputs with
different purposes:

- The workflow control commit is `github.sha`. Staging reads
  `evidence/modernization-contract.json` from this checkout and binds its SHA-256.
- The application source is then checked out separately at the older, distinct
  `handoff.source.commitSha`. Tests, the Docker build, the full 40-hex image tag, and
  `<app>--ci-<first12>` candidate name derive only from this source commit.

## Guardrails

- Grant only `contents: read` and `id-token: write`.
- Use one user-assigned managed identity with separate GitHub environment subjects
  `repo:<owner>/<repository>:environment:staging` and
  `repo:<owner>/<repository>:environment:production`.
- Give that deployment identity only `AcrPush` on the exact handoff ACR and `Container
  Apps Contributor` on the exact handoff Container App. The workflow must not enumerate
  its own RBAC.
- Do not use client secrets, registry admin, mutable action references, broad
  resource-group/subscription roles, or a mutable image deployment reference.
- Keep both the handoff revision and candidate active and healthy. The candidate starts
  at zero traffic in multiple-revision mode and owns the official label URL
  `https://<APP_NAME>---candidate.<ENVIRONMENT_SUFFIX>`.

## Required lifecycle

1. Staging binds and hashes the handoff from the control checkout, checks out and tests
   the separate source commit, builds and resolves the digest-qualified image, deploys
   the zero-traffic candidate, and probes its exact base, `/healthz`, and `/readyz`
   URLs.
2. Staging captures and hashes raw `az containerapp revision list` output before
   approval. Normalized active, health, weight, and image values must be derived from
   that raw response.
3. The protected `production` environment job starts only after staging succeeds and a
   reviewer records approval. It arms a shell rollback trap before promotion, captures
   and hashes raw revision-list output after promotion and after rollback, and proves
   both retained revisions are healthy.
4. After the successful run is fully completed, a facilitator with Reader-equivalent
   `Microsoft.Authorization/roleAssignments/read` captures GitHub metadata, UAMI
   details, and exhaustive RBAC. A currently running production job is never complete
   evidence.

## Evidence and success criteria

Produce `evidence/cicd-report.json` and every referenced
`evidence/cicd/<name>.json` or `.raw.json` file. Every normalized observation binds one
repository, workflow path, control head SHA, ref, run ID, and run attempt. Staging and
production jobs require positive immutable job IDs, successful conclusions, and
positive, correctly ordered time windows.

The facilitator first selects the UAMI/handoff subscription and then runs this exact
unfiltered command without `--scope` or JMESPath:

```bash
az role assignment list --all --include-inherited \
  --assignee-object-id "$PRINCIPAL_ID" \
  --fill-principal-name false \
  --fill-role-definition-name false \
  --output json
```

Preserve full ARM `roleDefinitionId` values in the raw response. Normalize them to UUIDs
only in `evidence/cicd/identity.json`; any assignment beyond the exact two roles fails.
The UAMI, ACR, and Container App must share the selected subscription.

Validate from `tests/acceptance`:

```bash
uv --no-config run catalog-validate-challenge-evidence cicd \
  evidence/cicd-report.json \
  --handoff evidence/modernization-contract.json \
  --contracts workshop/contracts \
  --repository-root ../..
```

The example JSON documents structure only and is never behavioral proof.

## Solution

[Solution steps](../../solutions/ch03/README.md)
