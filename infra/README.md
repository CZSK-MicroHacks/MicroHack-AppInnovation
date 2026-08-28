# Shared Azure target

`main.bicep` is the authoritative standalone resource-group-scope template for the
approved Sweden Central workshop profile. Each deployment fills one participant/team
resource group that already exists — the one the facilitator created at T-1 — and
supports:

- `.NET / Azure SQL` with Entra-only administration and workload managed identity;
- `Java / PostgreSQL` with a local restore administrator plus facilitator Entra
  administrator and either a password application role or workload managed identity;
- Blob images with workload-identity reads, or the Azure Files compatibility mount;
- ACR managed-identity pulls, a VNet-integrated Container Apps environment, private
  data endpoints, Log Analytics, Application Insights, and direct Azure Monitor
  OpenTelemetry export for traces, metrics, and logs.

The target VNet is deterministic and does not overlap the Challenge 0 participant
`10.<participant>.0.0/22` ranges: .NET uses `172.20.0.0/16` and Java uses
`172.21.0.0/16`.

## Stages

`bootstrap` creates infrastructure only. It emits a schema-valid target document
whose `containerImage` and `application` fields are null. It does not create a
placeholder Container App.

`application` requires a lowercase 40-hex source commit, a full sha256 image
digest, and secure application inputs: `performanceApiKey` is asserted non-empty for
this stage, and the Java password-secret path additionally requires
`postgresqlApplicationPassword`. Both are stored as Container Apps secrets. The
Container App revision suffix is the first 12 commit characters and the URL uses the
environment's actual `defaultDomain`.

## Build

Every Azure CLI invocation must use the isolated facilitator profile:

```bash
AZURE_CONFIG_DIR="$HOME/.azure-365" az bicep version
AZURE_CONFIG_DIR="$HOME/.azure-365" az bicep build --file infra/main.bicep
for file in infra/modules/*.bicep; do
  AZURE_CONFIG_DIR="$HOME/.azure-365" az bicep build --file "$file"
done
for file in infra/parameters/*.bicepparam; do
  AZURE_CONFIG_DIR="$HOME/.azure-365" az bicep build-params --file "$file"
done
```

### The experimental-feature banner is expected, not breakage

Every Bicep command run against this directory prints:

```text
WARNING: The following experimental Bicep features have been enabled: Asserts.
Experimental features should be enabled for testing purposes only...
```

That banner is correct and expected. It is produced by `"assertions": true` in
`infra/bicepconfig.json`, which is enabled **on purpose**: these templates carry 48
`assert` statements that fail the deployment at submission time rather than halfway
through it. They are the guard rails behind the workshop's frozen contract — that the
location really is `swedencentral` (`main.bicep:99`), that `sourceCommit` really is a
lowercase 40-hex commit and `imageDigest` a full `sha256:` digest (`main.bicep:101-102`),
that application-stage secrets are non-empty (`main.bicep:103-105`), and that the
migration source VNet and VM resource IDs are well-formed and in the same subscription
(`main.bicep:111-113`).

Removing the flag to silence the banner would silently disable all 48 checks and let a
mistyped commit deploy the wrong source. So the banner stays, and this is the trade:
**an advisory line of output in exchange for 48 fail-fast contract checks.**

Participants and facilitators will see this banner on `az bicep build`,
`az deployment group what-if`, and `az deployment group create`. It is not an error, it
does not affect the deployment, and nothing needs to be done about it. `az bicep build`
should otherwise report **zero warnings and zero errors** on every template here — if you
see anything besides this banner, that is a real finding.

The checked-in parameter files contain conspicuous sanitized values and are for
template compilation only. For what-if, create a protected parameter file
outside the repository, replace every secure value, and set `resourceGroupName` to the
resource group you are deploying into — the template asserts the two agree:

```bash
: "${RESOURCE_GROUP:?Set the resource group you are running what-if against}"

AZURE_CONFIG_DIR="$HOME/.azure-365" az deployment group what-if \
  --resource-group "$RESOURCE_GROUP" \
  --template-file infra/main.bicep \
  --parameters @/protected/path/scenario.json \
  --parameters sourceCommit="$(git rev-parse HEAD)"
```

`sourceCommit` is required and is deliberately absent from every parameter file, so it
must be supplied on the command line. A placeholder in the file would satisfy the
template's format assertion while silently deploying the wrong source.

`infra/main.bicep` targets a **resource group**, and participants deploy it with
`az deployment group create` into the resource group they already own — the one the
facilitator created at T-1 alongside their two legacy VMs. Nothing in the participant
path creates a resource group or writes outside that one group, which is what keeps
"Owner on your own resource group, and nothing else" true.

`infra/sre-agent.bicep` is the exception and is deliberately subscription-scoped: it
defines a custom role, which cannot be scoped lower. It is facilitator-only work — see
[the SRE agent foundation](../workshop/sre-agent/README.md) — and no participant runs it.

That template provisions everything about the agent that the Azure control plane exposes:
the dedicated resource group, dual identities, telemetry connectors, the Azure Monitor
incident-management connection, Review mode with Low action access, and the bounded
traffic-only rollback role. It stops at the incident response plan, and the
`responsePlanConfiguredInIaC: false` output says so on purpose. As of 2026-08-25, at
api-version `2026-01-01`, the `Microsoft.App` provider exposes only `agentSpaces`,
`agentSpaces/connectors`, `agents` and `agents/connectors` as deployable resource types,
and `AgentProperties` has no response-plan property — so the plan is not expressible in
ARM or Bicep at all. Microsoft documents creation through the portal Builder wizard
([incident response plans](https://learn.microsoft.com/azure/sre-agent/incident-response-plans),
[create a plan](https://learn.microsoft.com/azure/sre-agent/response-plan)); the only
programmatic path is the agent data plane via `azmcp sreagent incidents plans create`.
The template carries the full citation trail above its output, the facilitator procedure
is in [the SRE agent foundation](../workshop/sre-agent/README.md), and the flag should
flip only when `Microsoft.App` ships a response-plan resource type.

Do not run either template live during local validation. Live creation
requires the Challenge 1 deployment gate and facilitator-approved subscription context.

## Challenge 2 performance-test prerequisites

`perf-testing.bicep` is a separate resource-group-scope template that creates the two
resources Challenge 2 consumes but `main.bicep` deliberately does not own: an Azure
Load Testing resource and a Key Vault holding the performance-test API key. It is kept
out of `github-cicd.bicep`, which is frozen to exactly one workflow identity, two
federated credentials, and two role assignments.

Deploy it after `github-cicd.bicep`, passing that template's `identityPrincipalId`
output:

```bash
: "${RESOURCE_GROUP:?Set the resource group holding the github-cicd deployment}"
: "${CICD_DEPLOYMENT:?Set the infra/github-cicd.bicep deployment name}"

WORKFLOW_IDENTITY_PRINCIPAL_ID=$(az deployment group show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$CICD_DEPLOYMENT" \
  --query properties.outputs.identityPrincipalId.value \
  --output tsv)

PERF_OUTPUTS=$(az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --template-file infra/perf-testing.bicep \
  --parameters workflowIdentityPrincipalId="$WORKFLOW_IDENTITY_PRINCIPAL_ID" \
  --query properties.outputs \
  --output json)
```

It grants the workflow identity `Load Test Contributor` on the load test and
`Key Vault Secrets User` on the vault, and grants the load test's own system-assigned
identity `Key Vault Secrets User` so it can resolve the secret reference passed to
`az load test create`.

The template creates the vault but **not** the secret, because the secret value is
environment-specific. The facilitator sets it once, using an identity that holds
`Key Vault Secrets Officer`:

```bash
KEY_VAULT_NAME=$(jq -er '.keyVaultName.value' <<<"$PERF_OUTPUTS")
: "${PERFTEST_API_KEY:?Set the performance-test API key; do not echo it or store it in the repository}"

az keyvault secret set \
  --vault-name "$KEY_VAULT_NAME" \
  --name PERFTEST-API-KEY \
  --value "$PERFTEST_API_KEY" \
  --output none
```

The secret is named `PERFTEST-API-KEY` with hyphens even though the environment variable
it feeds is `PERFTEST_API_KEY` with underscores. Key Vault object names accept only
alphanumerics and hyphens, so an underscore is rejected by the service with
`(BadParameter) The request URI contains an invalid name`. The two names are independent:
the vault stores `PERFTEST-API-KEY`, and `az load test create` binds that secret to the
`PERFTEST_API_KEY` alias the JMeter plan resolves through `${__GetSecret(...)}`.

`KEY_VAULT_NAME` is the `keyVaultName` output of the deployment above, so the secret
lands in the vault that deployment just created. It is guarded rather than defaulted — a
default would publish a known key into a vault the workflow identity can read.
`--output none` keeps the value off the terminal.

**`PERFTEST_API_KEY` is not a fresh value invented here.** It must be byte-identical to
the value already passed as `--performance-api-key` when the application was deployed,
because that argument becomes the Container App secret `performance-api-key` that the
application enforces on `/perftest/*`. This vault secret is only how the load test
*presents* that key; the application is the party that *checks* it. Two independent
write paths reach one logical value, and nothing in the deployment binds them, so
supplying a new value here produces a vault and an application that disagree.

The failure is silent until a load run, and then it is loud and misattributed: every
sample returns `401`, the error rate is 100%, `failureCriteria` trips, and the run
fails for a reason no error message names. Verify the two agree before the first run —
this compares them without printing either:

```bash
KEY_VAULT_NAME=$(jq -er '.keyVaultName.value' <<<"$PERF_OUTPUTS")
: "${RESOURCE_GROUP:?Set the workshop resource group}"
: "${CONTAINER_APP_NAME:?Set the deployed Container App name}"

aca=$(az containerapp secret show --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" --secret-name performance-api-key \
  --query value --output tsv)
kv=$(az keyvault secret show --vault-name "$KEY_VAULT_NAME" \
  --name PERFTEST-API-KEY --query value --output tsv)
[ "$aca" = "$kv" ] && echo "keys agree" || echo "KEYS DISAGREE - the load test will 401 on every sample"
```

If they disagree, set the vault secret to the value the application already enforces.
Changing the application's secret instead forces a new revision and restarts the app.

Challenge 2 reads two values from this deployment: `loadTestResourceId` becomes
`LOAD_TEST_RESOURCE_ID`, and the secret identifier
`<keyVaultUri>secrets/PERFTEST-API-KEY` becomes `PERFTEST_API_KEY_SECRET_URI`.

The vault uses RBAC authorization with soft delete enabled and a seven-day retention
window. Because soft delete is on, a redeployment after a delete requires either a
purge or a different vault name.

## Azure Files policy boundary

The Azure Files mode is deliberately limited to the Container Apps Azure Files
volume implementation. The storage key is passed only to the environment
storage resource and is never output. The approved validation subscription
denies shared-key storage, so this compatibility mode requires a policy
exemption or a different workshop subscription.

## The image store is private by design, so there is no public blob URL

`environment.bicep` gives the catalog images account `publicNetworkAccess: 'Disabled'`
and `allowBlobPublicAccess: false`, reaches it through a private endpoint, resolves it
through the `privatelink.blob.core.windows.net` zone, and reads it with a managed
identity. Every one of those is deliberate, and together they mean the container reads
images over the virtual network and nothing else can read them at all.

Say this to attendees before they go looking, because the posture is easy to mistake for
a misconfiguration. A tenant policy that forces public network access off is not
fighting this template, it is agreeing with it, so there is nothing to work around and
no exemption to request. Pasting a blob URL into a browser is expected to fail, and an
attendee who assumes otherwise will read a correct deployment as a broken one and start
debugging infrastructure that is behaving exactly as designed.

## Rollback boundary

The shared target does not add rollback orchestration. Keep the prior healthy Container Apps
revision and use the workshop's existing revision traffic procedure after
explicit facilitator approval. Database artifacts and source data remain
intact; this template performs no migration or deletion.

Challenge-local copies of this template are intentionally absent. All six Challenge 1
stack/path cells compile and deploy this authoritative artifact.
