# Challenge 3 solution: OIDC, immutable revisions, and evidence

The checked-in workflows implement the bounded lifecycle. Do not turn them into a
general deployment platform and do not use the example JSON as behavioral proof.

## 1. Provision the bounded identity

Deploy `infra/github-cicd.bicep` at resource-group scope with the exact ACR and
Container App resource IDs from `evidence/modernization-contract.json`. The two
resources and deployment identity must be in the same subscription and resource group.
The template creates only:

- one user-assigned managed identity;
- `staging` and `production` federated credentials;
- `AcrPush` on the exact ACR; and
- `Container Apps Contributor` on the exact Container App.

Create GitHub environments named `staging` and `production`, with required reviewers
only on `production`, and set these variables in both environments:

| Variable | Bicep/account value |
| --- | --- |
| `AZURE_CLIENT_ID` | `identityClientId` |
| `AZURE_TENANT_ID` | tenant containing the UAMI |
| `AZURE_SUBSCRIPTION_ID` | subscription shared by the UAMI, ACR, and app |

Retain `identityResourceId` for the facilitator capture.

## 2. Run the stack-selected workflow

Use `.github/workflows/catalog-dotnet.yml` for `dotnet-sqlserver` or
`.github/workflows/catalog-java.yml` for `java-postgresql`. Both expose only
`workflow_dispatch`.

The staging job first reads and hashes the handoff at the workflow control
`github.sha`. That control commit must be later than and distinct from the handoff
application source commit. A second checkout at `handoff.source.commitSha` supplies
only the tests and image build. The job deploys the digest-qualified candidate with
zero traffic, probes the exact candidate base/health/readiness URLs, and records raw
revision state.

The protected production environment establishes this order:

`staging complete -> approval recorded -> production starts -> promotion -> rollback`

The production shell trap is armed before promotion. Both the normal success path and
failure path attempt rollback; successful evidence additionally proves promotion and
rollback while both revisions remain active and healthy.

## 3. Capture GitHub evidence after the run completes

Run the following read-only observation commands from the repository root. Set every
placeholder to the exact successful attempt. Never use a production job that is still
running.

```bash
set -Eeuo pipefail
REPO="<owner>/<repository>"
RUN_ID="<run-id>"
RUN_ATTEMPT="<run-attempt>"
STACK="<dotnet|java>"
WORKFLOW=".github/workflows/catalog-${STACK}.yml"
ARTIFACT="catalog-${STACK}-cicd-${RUN_ID}-${RUN_ATTEMPT}-production"

mkdir -p evidence/cicd
gh api "repos/${REPO}/actions/runs/${RUN_ID}" \
  > evidence/cicd/workflow-run.raw.json
gh api "repos/${REPO}/actions/runs/${RUN_ID}/attempts/${RUN_ATTEMPT}/jobs?per_page=100" \
  > evidence/cicd/workflow-jobs.raw.json
gh api "repos/${REPO}/actions/runs/${RUN_ID}/approvals" \
  > evidence/cicd/approvals.raw.json
gh run download "$RUN_ID" --repo "$REPO" --name "$ARTIFACT" --dir evidence/cicd

jq -e \
  --argjson runId "$RUN_ID" \
  --argjson runAttempt "$RUN_ATTEMPT" \
  --arg repository "$REPO" \
  --arg workflow "$WORKFLOW" \
  '
    .id == $runId
    and .run_attempt == $runAttempt
    and .repository.full_name == $repository
    and .path == $workflow
    and .event == "workflow_dispatch"
    and .status == "completed"
    and .conclusion == "success"
  ' evidence/cicd/workflow-run.raw.json >/dev/null

jq -e '
  [.jobs[] | select(.name == "staging" or .name == "production")] as $jobs
  | ($jobs | length) == 2
  and all($jobs[];
    .id > 0
    and .status == "completed"
    and .conclusion == "success"
    and .started_at < .completed_at
  )
' evidence/cicd/workflow-jobs.raw.json >/dev/null

jq -e '
  any(.[];
    .state == "approved"
    and any(.environments[]; .name == "production")
    and .user.login != ""
    and .created_at != null
  )
' evidence/cicd/approvals.raw.json >/dev/null
```

Normalize the exact control SHA, source SHA, run attempt, job IDs, positive windows,
and recorded approval:

```bash
WORKFLOW_CAPTURED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
jq -n \
  --slurpfile run evidence/cicd/workflow-run.raw.json \
  --slurpfile jobs evidence/cicd/workflow-jobs.raw.json \
  --slurpfile context evidence/cicd/context.json \
  --arg capturedAt "$WORKFLOW_CAPTURED_AT" \
  '
    ($run[0]) as $r
    | ($context[0]) as $c
    | {
        schemaVersion: "1.1.0",
        runId: $r.id,
        runAttempt: $r.run_attempt,
        githubRepository: $r.repository.full_name,
        workflowPath: $r.path,
        headSha: $r.head_sha,
        ref: $c.ref,
        status: $r.status,
        conclusion: $r.conclusion,
        event: $r.event,
        jobs: [
          $jobs[0].jobs[]
          | select(.name == "staging" or .name == "production")
          | {
              jobId: .id,
              name: .name,
              environment: .name,
              status,
              conclusion,
              startedAt: .started_at,
              completedAt: .completed_at
            }
        ],
        capturedAt: $capturedAt
      }
  ' > evidence/cicd/workflow-run.json

jq -n \
  --slurpfile approvals evidence/cicd/approvals.raw.json \
  --slurpfile context evidence/cicd/context.json \
  '
    ($context[0]) as $c
    | (
        $approvals[0]
        | map(select(.state == "approved" and any(.environments[]; .name == "production")))
        | sort_by(.created_at)
        | last
      ) as $approval
    | {
        schemaVersion: "1.1.0",
        runId: $c.runId,
        runAttempt: $c.runAttempt,
        githubRepository: $c.githubRepository,
        workflowPath: $c.workflowPath,
        headSha: $c.controlCommit,
        ref: $c.ref,
        environment: "production",
        reviewer: $approval.user.login,
        approvedAt: $approval.created_at,
        state: $approval.state
      }
  ' > evidence/cicd/approval.json
```

Before continuing, verify the normalized timestamps prove
`staging.completedAt <= approval.approvedAt <= production.startedAt` and that production
is already complete.

## 4. Capture UAMI and RBAC from a facilitator session

The deployment UAMI deliberately cannot audit itself. Use a separate facilitator
session with Reader-equivalent
`Microsoft.Authorization/roleAssignments/read`. Select the subscription from the UAMI
resource ID before issuing the exact unscoped role query:

```bash
IDENTITY_RESOURCE_ID="<identityResourceId>"
SUBSCRIPTION_ID="$(cut -d/ -f3 <<<"$IDENTITY_RESOURCE_ID")"
IDENTITY_RESOURCE_GROUP="$(cut -d/ -f5 <<<"$IDENTITY_RESOURCE_ID")"
IDENTITY_NAME="$(cut -d/ -f9 <<<"$IDENTITY_RESOURCE_ID")"
az account set --subscription "$SUBSCRIPTION_ID"
test "$(az account show --query id --output tsv)" = "$SUBSCRIPTION_ID"

az identity show --ids "$IDENTITY_RESOURCE_ID" --output json \
  > evidence/cicd/identity.raw.json
az identity federated-credential list \
  --identity-name "$IDENTITY_NAME" \
  --resource-group "$IDENTITY_RESOURCE_GROUP" \
  --output json > evidence/cicd/federated-credentials.raw.json

PRINCIPAL_ID="$(jq -er '.principalId' evidence/cicd/identity.raw.json)"
az role assignment list --all --include-inherited \
  --assignee-object-id "$PRINCIPAL_ID" \
  --fill-principal-name false \
  --fill-role-definition-name false \
  --output json > evidence/cicd/role-assignments.raw.json
```

Do not add `--scope`, `--query`, or another filter. The raw `roleDefinitionId` values
must remain full ARM IDs. Fail closed unless the complete response contains exactly the
two expected assignments:

```bash
ACR_SCOPE="$(jq -er '.registryResourceId' evidence/cicd/context.json)"
APP_SCOPE="$(jq -er '.containerAppResourceId' evidence/cicd/context.json)"
jq -e \
  --arg principalId "$PRINCIPAL_ID" \
  --arg acrScope "$ACR_SCOPE" \
  --arg appScope "$APP_SCOPE" \
  '
    length == 2
    and all(.[];
      .principalId == $principalId
      and (.roleDefinitionId | test("^/subscriptions/[^/]+/providers/Microsoft.Authorization/roleDefinitions/[0-9a-fA-F-]{36}$"))
    )
    and any(.[];
      (.roleDefinitionId | endswith("/8311e382-0749-4cb8-b61a-304f252e45ec"))
      and (.scope | ascii_downcase) == ($acrScope | ascii_downcase)
    )
    and any(.[];
      (.roleDefinitionId | endswith("/358470bc-b998-42bd-ab17-a7e34c199c0f"))
      and (.scope | ascii_downcase) == ($appScope | ascii_downcase)
    )
  ' evidence/cicd/role-assignments.raw.json >/dev/null

ROLE_RAW_SHA256="$(sha256sum evidence/cicd/role-assignments.raw.json | cut -d' ' -f1)"
PERFORMED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
ROLE_COMMAND="az role assignment list --all --include-inherited --assignee-object-id ${PRINCIPAL_ID} --fill-principal-name false --fill-role-definition-name false --output json"

jq -n \
  --slurpfile context evidence/cicd/context.json \
  --slurpfile identity evidence/cicd/identity.raw.json \
  --slurpfile credentials evidence/cicd/federated-credentials.raw.json \
  --slurpfile roles evidence/cicd/role-assignments.raw.json \
  --arg subscriptionId "$SUBSCRIPTION_ID" \
  --arg command "$ROLE_COMMAND" \
  --arg rawSha256 "$ROLE_RAW_SHA256" \
  --arg performedAt "$PERFORMED_AT" \
  '
    ($context[0]) as $c
    | ($identity[0]) as $i
    | {
        schemaVersion: "1.1.0",
        runId: $c.runId,
        runAttempt: $c.runAttempt,
        githubRepository: $c.githubRepository,
        workflowPath: $c.workflowPath,
        headSha: $c.controlCommit,
        ref: $c.ref,
        identityKind: "user-assigned-managed-identity",
        resourceId: $i.id,
        clientId: $i.clientId,
        principalId: $i.principalId,
        stagingFederatedSubject: ("repo:" + $c.githubRepository + ":environment:staging"),
        productionFederatedSubject: ("repo:" + $c.githubRepository + ":environment:production"),
        acrRoleDefinitionId: "8311e382-0749-4cb8-b61a-304f252e45ec",
        acrScope: $c.registryResourceId,
        containerAppRoleDefinitionId: "358470bc-b998-42bd-ab17-a7e34c199c0f",
        containerAppScope: $c.containerAppResourceId,
        clientSecretUsed: false,
        registryAdminUsed: false,
        federatedCredentials: [
          $credentials[0][]
          | select(.name == "staging" or .name == "production")
          | {
              environment: .name,
              resourceId: .id,
              subject,
              issuer,
              audiences
            }
        ],
        roleAssignments: [
          $roles[0][]
          | {
              resourceId: .id,
              principalId,
              roleDefinitionId: (.roleDefinitionId | split("/") | last),
              scope
            }
        ],
        roleAssignmentEnumeration: {
          assigneeObjectId: $i.principalId,
          executionBoundary: "facilitator-session",
          subscriptionId: $subscriptionId,
          requiredPermission: "Microsoft.Authorization/roleAssignments/read",
          minimumBuiltInRole: "Reader",
          command: $command,
          rawResultFile: "evidence/cicd/role-assignments.raw.json",
          rawResultSha256: $rawSha256,
          performedAt: $performedAt,
          all: true,
          includeInherited: true,
          fillPrincipalName: false,
          fillRoleDefinitionName: false,
          filtered: false
        },
        observedAt: $performedAt
      }
  ' > evidence/cicd/identity.json
```

## 5. Assemble and validate the frozen report

Merge only observed values and the artifact fragment:

```bash
REPORT_CAPTURED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
jq -n \
  --slurpfile fragment evidence/cicd/report-fragment.json \
  --slurpfile run evidence/cicd/workflow-run.json \
  --slurpfile approval evidence/cicd/approval.json \
  --slurpfile identity evidence/cicd/identity.json \
  --arg capturedAt "$REPORT_CAPTURED_AT" \
  '
    ($fragment[0]) as $f
    | ($run[0]) as $r
    | ($approval[0]) as $a
    | ($identity[0]) as $i
    | $f + {
        capturedAt: $capturedAt,
        workflow: $f.workflow + {
          jobs: {
            staging: (
              $r.jobs[] | select(.name == "staging") | {
                jobId,
                environment,
                federatedSubject: $i.stagingFederatedSubject,
                clientId: $i.clientId,
                principalId: $i.principalId,
                startedAt,
                completedAt
              }
            ),
            production: (
              $r.jobs[] | select(.name == "production") | {
                jobId,
                environment,
                federatedSubject: $i.productionFederatedSubject,
                clientId: $i.clientId,
                principalId: $i.principalId,
                startedAt,
                completedAt
              }
            )
          },
          resultFile: "evidence/cicd/workflow-run.json"
        },
        identity: {
          authentication: "github-oidc",
          identityKind: $i.identityKind,
          resourceId: $i.resourceId,
          clientId: $i.clientId,
          principalId: $i.principalId,
          stagingFederatedSubject: $i.stagingFederatedSubject,
          productionFederatedSubject: $i.productionFederatedSubject,
          federatedCredentialResourceIds: {
            staging: ($i.federatedCredentials[] | select(.environment == "staging") | .resourceId),
            production: ($i.federatedCredentials[] | select(.environment == "production") | .resourceId)
          },
          acrRoleDefinitionId: $i.acrRoleDefinitionId,
          acrScope: $i.acrScope,
          containerAppRoleDefinitionId: $i.containerAppRoleDefinitionId,
          containerAppScope: $i.containerAppScope,
          clientSecretUsed: $i.clientSecretUsed,
          registryAdminUsed: $i.registryAdminUsed,
          roleAssignmentEnumeration: $i.roleAssignmentEnumeration,
          resultFile: "evidence/cicd/identity.json"
        },
        approval: {
          environment: "production",
          reviewer: $a.reviewer,
          approvedAt: $a.approvedAt,
          resultFile: "evidence/cicd/approval.json"
        }
      }
  ' > evidence/cicd-report.json

cd tests/acceptance
uv --no-config run catalog-validate-challenge-evidence cicd \
  ../../evidence/cicd-report.json \
  --handoff ../../evidence/modernization-contract.json \
  --contracts ../../workshop/contracts \
  --repository-root ../..
```

The common CLI validates the control-commit handoff hash, immutable run/job identities,
external RBAC capture, raw revision hashes, source-tag/digest/candidate binding, and the
full staging-approval-production-promotion-rollback timestamp order.
