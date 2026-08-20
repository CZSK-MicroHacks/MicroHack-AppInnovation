# Challenge 5 solution: digest-bound Defender evidence

Run these commands from the repository root in Bash unless a section explicitly says
to run from `tests/acceptance`. They bind only the selected handoff resources. Never run
the Azure commands in this guide against another participant scope.

## 1. Validate and bind the selected handoff

Validate the handoff before reading values from it:

```bash
set -euo pipefail
umask 077

(
  cd tests/acceptance
  uv --no-config run python -m catalog_acceptance.handoff_cli \
    ../../evidence/modernization-contract.json \
    --contracts ../../workshop/contracts \
    --repository-root ../..
)

HANDOFF=evidence/modernization-contract.json
TARGET_OUTPUT=$(jq -er '.deployment.targetOutput' "$HANDOFF")
test -f "$TARGET_OUTPUT"

SLICE_ID=$(jq -er '.sliceId' "$HANDOFF")
SOURCE_COMMIT=$(jq -er '.source.commitSha' "$HANDOFF")
SUBSCRIPTION_ID=$(jq -er '.application.resourceId | split("/")[2]' "$HANDOFF")
SUBSCRIPTION_SCOPE="/subscriptions/$SUBSCRIPTION_ID"
RESOURCE_GROUP=$(jq -er '.application.resourceGroup' "$HANDOFF")
APP_RESOURCE_ID=$(jq -er '.application.resourceId' "$HANDOFF")
APP_NAME=$(jq -er '.application.containerAppName' "$HANDOFF")
APP_REVISION=$(jq -er '.application.revisionName' "$HANDOFF")
HEALTH_URL=$(jq -er '.application.healthUrl' "$HANDOFF")
READINESS_URL=$(jq -er '.application.readinessUrl' "$HANDOFF")
ACR_RESOURCE_ID=$(jq -er '.containerImage.registryResourceId' "$HANDOFF")
ACR_LOGIN_SERVER=$(jq -er '.containerImage.registry' "$HANDOFF")
IMAGE_REPOSITORY=$(jq -er '.containerImage.repository' "$HANDOFF")
IMAGE_DIGEST=$(jq -er '.containerImage.digest' "$HANDOFF")
DATABASE_RESOURCE_ID=$(jq -er '.database.resourceId' "$HANDOFF")
DATABASE_FAMILY=$(jq -er '.database.family' "$HANDOFF")

SOURCE_VM_ID=$(jq -er '.network.migrationSourceVmResourceId' "$TARGET_OUTPUT")
WORKLOAD_IDENTITY_ID=$(jq -er '.workloadIdentity.resourceId' "$TARGET_OUTPUT")
WORKLOAD_PRINCIPAL_ID=$(jq -er '.workloadIdentity.principalId' "$TARGET_OUTPUT")

test "$(jq -er '.application.resourceId' "$TARGET_OUTPUT")" = "$APP_RESOURCE_ID"
test "$(jq -er '.containerRegistry.resourceId' "$TARGET_OUTPUT")" = "$ACR_RESOURCE_ID"
test "$(jq -er '.database.resourceId' "$TARGET_OUTPUT")" = "$DATABASE_RESOURCE_ID"
test "$(jq -er '.sourceCommit' "$TARGET_OUTPUT")" = "$SOURCE_COMMIT"
test "$(jq -er '.containerImage.digest' "$TARGET_OUTPUT")" = "$IMAGE_DIGEST"
[[ "$SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]]
[[ "$IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]]
```

Do not replace any value with a portal search result. The selected VM is exactly
`SOURCE_VM_ID`; the sibling VM comes only from the facilitator's two-VM coverage
artifact.

## 2. Verify facilitator-owned foundation artifacts

The facilitator supplies these live, repository-root-relative artifacts:

```bash
LAB_PROFILE=workshop/defender/lab-profile.json
PRICINGS=evidence/defender/foundation/pricings.json
BUDGET=evidence/defender/foundation/budget.json
VM_COVERAGE=evidence/defender/foundation/legacy-vm-coverage.json
SEED_SNAPSHOT=evidence/defender/foundation/seed-snapshot.json
MANUAL_PREFLIGHT=evidence/defender/foundation/manual-preflight.json
CLEANUP_MANIFEST=evidence/defender/cleanup-manifest.json

for artifact in \
  "$LAB_PROFILE" "$PRICINGS" "$BUDGET" "$VM_COVERAGE" \
  "$SEED_SNAPSHOT" "$MANUAL_PREFLIGHT" "$CLEANUP_MANIFEST"; do
  test -f "$artifact"
done

jq -e --arg subscription "$SUBSCRIPTION_ID" --arg selected "$SOURCE_VM_ID" '
  .schemaVersion == "1.0.0"
  and .apiVersion == "2024-11-01"
  and ([.virtualMachines[].workload] | sort) == ["dotnet", "java"]
  and any(.virtualMachines[];
    (.request.resourceId | ascii_downcase) == ($selected | ascii_downcase)
    and (.response.body.id | ascii_downcase) == ($selected | ascii_downcase)
    and .response.statusCode == 200
  )
  and all(.virtualMachines[];
    .request.method == "GET"
    and .response.body.properties.provisioningState == "Succeeded"
    and (.request.resourceId | split("/")[2] | ascii_downcase)
      == ($subscription | ascii_downcase)
  )
' "$VM_COVERAGE" >/dev/null
```

Confirm with the facilitator that `PRICINGS` proves `CloudPosture`, `Containers`,
`SqlServers`, `OpenSourceRelationalDatabases`, and subscription-enforced
`VirtualMachines` P2. Confirm `MANUAL_PREFLIGHT` records the Owner-only
`azure-portal-owner-preflight` for Serverless Containers. Participants must not change
these subscription settings.

The seed snapshot must be distinct from every current query artifact. It must precede
the current observations and point to separate pre-warmed, non-empty image,
recommendation, Secure Score, and MCSB files. Those seed files are deterministic
learning context, not current participant evidence.

## 3. Capture exact before-state resources

Create the live evidence area:

```bash
RAW=evidence/defender/raw
mkdir -p "$RAW" evidence/defender/foundation
```

Capture ACR and ACA before state with explicit ARM versions:

```bash
az rest --method get \
  --url "https://management.azure.com${ACR_RESOURCE_ID}?api-version=2023-07-01" \
  > "$RAW/acr-before.json"

az rest --method get \
  --url "https://management.azure.com${APP_RESOURCE_ID}?api-version=2024-03-01" \
  > "$RAW/container-app-before.json"
```

The database control is server-scoped even though the handoff is database-scoped:

```bash
DATABASE_SERVER_ID=${DATABASE_RESOURCE_ID%/databases/*}
case "$DATABASE_FAMILY" in
  azure-sql)
    [[ "$DATABASE_SERVER_ID" == */providers/Microsoft.Sql/servers/* ]]
    DATABASE_API_VERSION=2023-08-01
    ;;
  postgresql-flexible)
    [[ "$DATABASE_SERVER_ID" == */providers/Microsoft.DBforPostgreSQL/flexibleServers/* ]]
    DATABASE_API_VERSION=2024-08-01
    ;;
  *)
    printf 'Unsupported selected database family: %s\n' "$DATABASE_FAMILY" >&2
    exit 1
    ;;
esac

az rest --method get \
  --url "https://management.azure.com${DATABASE_SERVER_ID}?api-version=${DATABASE_API_VERSION}" \
  > "$RAW/database-before.json"
```

For the selected VM, preserve one composite containing the exact VM, every attached
NIC, each NIC resource, its complete effective NSG response, and either the exact bound
Defender JIT policy or JSON `null`. The commands remain selected-VM-bounded:

```bash
az vm show --ids "$SOURCE_VM_ID" --output json > "$RAW/vm.resource.before.json"
jq -er '.networkProfile.networkInterfaces[].id' \
  "$RAW/vm.resource.before.json" > "$RAW/vm-nic-ids.before.txt"

VM_LOCATION=$(jq -er '.location' "$RAW/vm.resource.before.json")
VM_RESOURCE_GROUP=$(cut -d/ -f5 <<<"$SOURCE_VM_ID")
VM_NAME=$(cut -d/ -f9 <<<"$SOURCE_VM_ID")

while IFS= read -r nic_id; do
  nic_name=$(cut -d/ -f9 <<<"$nic_id")
  az network nic show --ids "$nic_id" --output json \
    > "$RAW/${nic_name}.resource.before.json"
  az network nic list-effective-nsg \
    --ids "$nic_id" --output json \
    > "$RAW/${nic_name}.effective-nsg.before.json"
  jq -n \
    --slurpfile resource "$RAW/${nic_name}.resource.before.json" \
    --slurpfile effective "$RAW/${nic_name}.effective-nsg.before.json" '
    {
      resource: $resource[0],
      effectiveNetworkSecurityGroups: $effective[0]
    }
  ' > "$RAW/${nic_name}.capture.before.json"
done < "$RAW/vm-nic-ids.before.txt"

az rest --method get \
  --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${VM_RESOURCE_GROUP}/providers/Microsoft.Security/locations/${VM_LOCATION}/jitNetworkAccessPolicies?api-version=2020-01-01" \
  > "$RAW/jit-policies.before.json"

jq -s '.' "$RAW"/*.capture.before.json > "$RAW/vm-nics.before.json"
jq --arg vm "$SOURCE_VM_ID" '
  [
    .value[]?
    | select(any(.properties.virtualMachines[]?;
        (.id | ascii_downcase) == ($vm | ascii_downcase)))
  ] as $matches
  | if ($matches | length) == 0 then null
    elif ($matches | length) == 1 then $matches[0]
    else error("multiple JIT policies contain the selected VM")
    end
' "$RAW/jit-policies.before.json" > "$RAW/vm-jit.before.json"
jq -n \
  --slurpfile vm "$RAW/vm.resource.before.json" \
  --slurpfile nics "$RAW/vm-nics.before.json" \
  --slurpfile jit "$RAW/vm-jit.before.json" '
  {
    vm: $vm[0],
    networkInterfaces: $nics[0],
    jitPolicy: $jit[0]
  }
' > "$RAW/vm-before.json"
```

The resulting `evidence/defender/raw/vm-before.json` has shape
`{"vm": <VM>, "networkInterfaces": [{"resource": <NIC>,
"effectiveNetworkSecurityGroups": <effective NSG response>}], "jitPolicy": <one exact
policy or null>}`. This is a raw multi-request capture, not normalized evidence. The
JIT policy, when present, must be
`Microsoft.Security/locations/jitNetworkAccessPolicies`, live in the selected VM's
subscription/resource group/location, contain the selected VM exactly once, and cover
the exposed management port `22` or `3389`.

## 4. Apply only the four bounded controls

### ACR admin authentication

Disable admin authentication on the exact handoff registry:

```bash
az acr update --ids "$ACR_RESOURCE_ID" --admin-enabled false --output none
```

Do not change the ACA registry credential. It must remain the exact workload managed
identity with no username or `passwordSecretRef`, and the image must remain:

```text
<handoff registry>/<handoff repository>@<handoff sha256 digest>
```

### ACA HTTPS-only ingress

Keep the selected app and revision and reject insecure HTTP:

```bash
az containerapp ingress update \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --allow-insecure false \
  --output none
```

If ingress remains external, record `justified` and a specific 40-character-or-longer
justification plus compensating controls. Do not claim that public HTTPS is internal.

### Selected database family

Prefer disabling public network access when the selected topology supports it:

```bash
az rest --method patch \
  --url "https://management.azure.com${DATABASE_SERVER_ID}?api-version=${DATABASE_API_VERSION}" \
  --headers Content-Type=application/json \
  --body '{"properties":{"publicNetworkAccess":"Disabled"}}' \
  --output none
```

This same bounded operation applies to the parent `Microsoft.Sql/servers` resource for
`azure-sql` and the parent `Microsoft.DBforPostgreSQL/flexibleServers` resource for
`postgresql-flexible`. If public access must remain, do not invent a remediation:
record `documented-exception`, a specific justification, and compensating controls.

### Selected VM management exposure

If an effective rule exposes SSH/RDP publicly, update only the exact approved rule:

```bash
: "${VM_MANAGEMENT_RULE_ID:?Set the exact public SSH/RDP NSG rule ID from before-state}"
az network nsg rule update \
  --ids "$VM_MANAGEMENT_RULE_ID" \
  --source-address-prefixes VirtualNetwork \
  --output none
```

Alternatively, retain an existing exact Defender JIT policy that covers the exposed
management port. Do not fabricate JIT state and do not create subscription-wide
policy. If exposure must remain and is not covered by JIT, record
`documented-exception` with a specific justification and compensating controls.

## 5. Capture after state and immutable pull authorization

Repeat the exact ACR, ACA, database, VM, NIC, effective NSG, and JIT reads:

```bash
az rest --method get \
  --url "https://management.azure.com${ACR_RESOURCE_ID}?api-version=2023-07-01" \
  > "$RAW/acr-after.json"
az rest --method get \
  --url "https://management.azure.com${APP_RESOURCE_ID}?api-version=2024-03-01" \
  > "$RAW/container-app-after.json"
az rest --method get \
  --url "https://management.azure.com${DATABASE_SERVER_ID}?api-version=${DATABASE_API_VERSION}" \
  > "$RAW/database-after.json"

az vm show --ids "$SOURCE_VM_ID" --output json > "$RAW/vm.resource.after.json"
jq -er '.networkProfile.networkInterfaces[].id' \
  "$RAW/vm.resource.after.json" > "$RAW/vm-nic-ids.after.txt"

while IFS= read -r nic_id; do
  nic_name=$(cut -d/ -f9 <<<"$nic_id")
  az network nic show --ids "$nic_id" --output json \
    > "$RAW/${nic_name}.resource.after.json"
  az network nic list-effective-nsg \
    --ids "$nic_id" --output json \
    > "$RAW/${nic_name}.effective-nsg.after.json"
  jq -n \
    --slurpfile resource "$RAW/${nic_name}.resource.after.json" \
    --slurpfile effective "$RAW/${nic_name}.effective-nsg.after.json" '
    {
      resource: $resource[0],
      effectiveNetworkSecurityGroups: $effective[0]
    }
  ' > "$RAW/${nic_name}.capture.after.json"
done < "$RAW/vm-nic-ids.after.txt"

az rest --method get \
  --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${VM_RESOURCE_GROUP}/providers/Microsoft.Security/locations/${VM_LOCATION}/jitNetworkAccessPolicies?api-version=2020-01-01" \
  > "$RAW/jit-policies.after.json"

jq -s '.' "$RAW"/*.capture.after.json > "$RAW/vm-nics.after.json"
jq --arg vm "$SOURCE_VM_ID" '
  [
    .value[]?
    | select(any(.properties.virtualMachines[]?;
        (.id | ascii_downcase) == ($vm | ascii_downcase)))
  ] as $matches
  | if ($matches | length) == 0 then null
    elif ($matches | length) == 1 then $matches[0]
    else error("multiple JIT policies contain the selected VM")
    end
' "$RAW/jit-policies.after.json" > "$RAW/vm-jit.after.json"
jq -n \
  --slurpfile vm "$RAW/vm.resource.after.json" \
  --slurpfile nics "$RAW/vm-nics.after.json" \
  --slurpfile jit "$RAW/vm-jit.after.json" '
  {
    vm: $vm[0],
    networkInterfaces: $nics[0],
    jitPolicy: $jit[0]
  }
' > "$RAW/vm-after.json"
```

Then capture only the selected identity's exact ACR-scoped `AcrPull` assignment:

```bash
az role assignment list \
  --scope "$ACR_RESOURCE_ID" \
  --assignee-object-id "$WORKLOAD_PRINCIPAL_ID" \
  --role AcrPull \
  --all \
  --output json |
  jq '{value: .}' > "$RAW/acr-role-assignments.json"

jq -e --arg principal "$WORKLOAD_PRINCIPAL_ID" --arg scope "$ACR_RESOURCE_ID" '
  (.value | length) == 1
  and .value[0].properties.principalId == $principal
  and (.value[0].id | ascii_downcase | startswith(($scope + "/providers/Microsoft.Authorization/roleAssignments/") | ascii_downcase))
  and (.value[0].properties.roleDefinitionId | endswith("/7f951dda-4ed3-4680-a7ca-43fe172d538d"))
' "$RAW/acr-role-assignments.json" >/dev/null
```

Verify ACR admin is false, ACA `allowInsecure` is false, the identity is still assigned,
the registry entry has no password/username, the exact digest is still deployed, and
the selected revision remains ready.

## 6. Capture current Defender query provenance

Current responses may be empty. Preserve the exact request and response together in
each envelope; do not replace an empty response with seed data.

### ACR image assessment

```bash
IMAGE_PATH='providers/Microsoft.Security/assessments/c0b7cfc6-3172-465a-b378-53c7ff2cc0d5/subAssessments'
IMAGE_API=2019-01-01-preview
IMAGE_QUERIED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
IMAGE_RESPONSE=$(az rest --method get \
  --url "https://management.azure.com${ACR_RESOURCE_ID}/${IMAGE_PATH}?api-version=${IMAGE_API}")
jq -n \
  --arg scope "$ACR_RESOURCE_ID" --arg path "$IMAGE_PATH" \
  --arg api "$IMAGE_API" --arg queriedAt "$IMAGE_QUERIED_AT" \
  --argjson response "$IMAGE_RESPONSE" '
  {
    schemaVersion: "1.0.0",
    request: {
      method: "GET",
      operation: "registry-image-subassessments",
      scopeResourceId: $scope,
      resourcePath: $path,
      apiVersion: $api,
      queriedAt: $queriedAt
    },
    response: $response
  }
' > "$RAW/image-assessment.json"
```

Set current status to `completed` only when the response contains a structured
`Microsoft.Security/assessments/subAssessments` record beneath the exact assessment
path whose `artifactDetails.repositoryName` and `artifactDetails.digest` match the
handoff. Otherwise use `pending` or `unavailable`; never insert free text or a seed
record to claim completion.

### Recommendations, Secure Score, and MCSB

Use these exact frozen requests:

```bash
RECOMMENDATIONS_PATH='providers/Microsoft.Security/assessments'
RECOMMENDATIONS_API=2020-01-01
RECOMMENDATIONS_QUERIED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
RECOMMENDATIONS_RESPONSE=$(az rest --method get \
  --url "https://management.azure.com${SUBSCRIPTION_SCOPE}/${RECOMMENDATIONS_PATH}?api-version=${RECOMMENDATIONS_API}")
jq -n --arg scope "$SUBSCRIPTION_SCOPE" --arg path "$RECOMMENDATIONS_PATH" \
  --arg api "$RECOMMENDATIONS_API" --arg queriedAt "$RECOMMENDATIONS_QUERIED_AT" \
  --argjson response "$RECOMMENDATIONS_RESPONSE" '
  {schemaVersion:"1.0.0",request:{method:"GET",operation:"subscription-recommendations",scopeResourceId:$scope,resourcePath:$path,apiVersion:$api,queriedAt:$queriedAt},response:$response}
' > "$RAW/recommendations.json"

SECURE_SCORE_PATH='providers/Microsoft.Security/secureScores'
SECURE_SCORE_API=2020-01-01
SECURE_SCORE_QUERIED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SECURE_SCORE_RESPONSE=$(az rest --method get \
  --url "https://management.azure.com${SUBSCRIPTION_SCOPE}/${SECURE_SCORE_PATH}?api-version=${SECURE_SCORE_API}")
jq -n --arg scope "$SUBSCRIPTION_SCOPE" --arg path "$SECURE_SCORE_PATH" \
  --arg api "$SECURE_SCORE_API" --arg queriedAt "$SECURE_SCORE_QUERIED_AT" \
  --argjson response "$SECURE_SCORE_RESPONSE" '
  {schemaVersion:"1.0.0",request:{method:"GET",operation:"subscription-secure-score",scopeResourceId:$scope,resourcePath:$path,apiVersion:$api,queriedAt:$queriedAt},response:$response}
' > "$RAW/secure-score.json"

MCSB_PATH='providers/Microsoft.Security/regulatoryComplianceStandards/Microsoft-cloud-security-benchmark/regulatoryComplianceControls'
MCSB_API=2019-01-01-preview
MCSB_QUERIED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
MCSB_RESPONSE=$(az rest --method get \
  --url "https://management.azure.com${SUBSCRIPTION_SCOPE}/${MCSB_PATH}?api-version=${MCSB_API}")
jq -n --arg scope "$SUBSCRIPTION_SCOPE" --arg path "$MCSB_PATH" \
  --arg api "$MCSB_API" --arg queriedAt "$MCSB_QUERIED_AT" \
  --argjson response "$MCSB_RESPONSE" '
  {schemaVersion:"1.0.0",request:{method:"GET",operation:"subscription-mcsb-controls",scopeResourceId:$scope,resourcePath:$path,apiVersion:$api,queriedAt:$queriedAt},response:$response}
' > "$RAW/mcsb.json"
```

### Resource Graph attack paths

Attack paths use Resource Graph `POST`, never a direct attack-path `GET`:

```bash
ATTACK_PATH_API=2022-10-01
ATTACK_PATH_QUERIED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
ATTACK_PATH_QUERY=$(printf 'securityresources\n| where type == "microsoft.security/attackpaths"\n| where subscriptionId == "%s"' "$SUBSCRIPTION_ID")
ATTACK_PATH_BODY=$(jq -n \
  --arg subscription "$SUBSCRIPTION_ID" \
  --arg query "$ATTACK_PATH_QUERY" '
  {subscriptions:[$subscription],query:$query,options:{resultFormat:"objectArray"}}
')
ATTACK_PATH_RESPONSE=$(az rest --method post \
  --url "https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=${ATTACK_PATH_API}" \
  --body "$ATTACK_PATH_BODY")
jq -n \
  --arg scope "$SUBSCRIPTION_SCOPE" \
  --arg api "$ATTACK_PATH_API" \
  --arg queriedAt "$ATTACK_PATH_QUERIED_AT" \
  --argjson body "$ATTACK_PATH_BODY" \
  --argjson response "$ATTACK_PATH_RESPONSE" '
  {
    schemaVersion: "1.0.0",
    request: {
      method: "POST",
      operation: "subscription-attack-paths",
      scopeResourceId: $scope,
      resourcePath: "providers/Microsoft.ResourceGraph/resources",
      apiVersion: $api,
      queriedAt: $queriedAt,
      body: $body
    },
    response: $response
  }
' > "$RAW/attack-paths.json"
```

Require `resultTruncated == "false"`, no `$skipToken`, `count == totalRecords ==
(.data | length)`, and every returned resource in the selected subscription. A complete
empty response is successful query evidence.

## 7. Prove the selected revision still works

```bash
HEALTH_STATUS=$(curl --silent --show-error --output /dev/null \
  --write-out '%{http_code}' "$HEALTH_URL")
READINESS_STATUS=$(curl --silent --show-error --output /dev/null \
  --write-out '%{http_code}' "$READINESS_URL")
test "$HEALTH_STATUS" = 200
test "$READINESS_STATUS" = 200
HEALTH_OBSERVED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
```

## 8. Build the digest-bound capture manifest

Choose the three decisions from observed state. `containerAppIngress` allows
`remediated`, `already-compliant`, or `justified`; database and VM use
`remediated`, `already-compliant`, or `documented-exception`. A justification must
describe the exact selected resource and compensating controls, not generic text.

Compute a SHA-256 for every referenced file and create
`evidence/defender/capture.json` matching
`workshop/contracts/defender-evidence-capture.schema.json` version `1.1.0`. Use the
exact repository-root-relative paths below; substitute actual decision values:

```bash
CAPTURE=evidence/defender/capture.json
IMAGE_STATUS=pending
CAPTURED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
BUDGET_QUERIED_AT=$(jq -er '.request.queriedAt' "$BUDGET")

jq -n \
  --arg capturedAt "$CAPTURED_AT" \
  --arg handoffSha "$(sha256sum "$HANDOFF" | cut -d' ' -f1)" \
  --arg targetSha "$(sha256sum "$TARGET_OUTPUT" | cut -d' ' -f1)" \
  --arg labSha "$(sha256sum "$LAB_PROFILE" | cut -d' ' -f1)" \
  --arg cleanupSha "$(sha256sum "$CLEANUP_MANIFEST" | cut -d' ' -f1)" \
  --arg subscription "$SUBSCRIPTION_ID" \
  --arg pricingsSha "$(sha256sum "$PRICINGS" | cut -d' ' -f1)" \
  --arg budgetSha "$(sha256sum "$BUDGET" | cut -d' ' -f1)" \
  --arg coverageSha "$(sha256sum "$VM_COVERAGE" | cut -d' ' -f1)" \
  --arg seedSha "$(sha256sum "$SEED_SNAPSHOT" | cut -d' ' -f1)" \
  --arg preflightSha "$(sha256sum "$MANUAL_PREFLIGHT" | cut -d' ' -f1)" \
  --arg acrBeforeSha "$(sha256sum "$RAW/acr-before.json" | cut -d' ' -f1)" \
  --arg acrAfterSha "$(sha256sum "$RAW/acr-after.json" | cut -d' ' -f1)" \
  --arg rolesSha "$(sha256sum "$RAW/acr-role-assignments.json" | cut -d' ' -f1)" \
  --arg appBeforeSha "$(sha256sum "$RAW/container-app-before.json" | cut -d' ' -f1)" \
  --arg appAfterSha "$(sha256sum "$RAW/container-app-after.json" | cut -d' ' -f1)" \
  --arg dbBeforeSha "$(sha256sum "$RAW/database-before.json" | cut -d' ' -f1)" \
  --arg dbAfterSha "$(sha256sum "$RAW/database-after.json" | cut -d' ' -f1)" \
  --arg vmBeforeSha "$(sha256sum "$RAW/vm-before.json" | cut -d' ' -f1)" \
  --arg vmAfterSha "$(sha256sum "$RAW/vm-after.json" | cut -d' ' -f1)" \
  --arg imageSha "$(sha256sum "$RAW/image-assessment.json" | cut -d' ' -f1)" \
  --arg imageAt "$IMAGE_QUERIED_AT" --arg imageStatus "$IMAGE_STATUS" \
  --arg digest "$IMAGE_DIGEST" --arg acr "$ACR_RESOURCE_ID" \
  --arg recSha "$(sha256sum "$RAW/recommendations.json" | cut -d' ' -f1)" \
  --arg scoreSha "$(sha256sum "$RAW/secure-score.json" | cut -d' ' -f1)" \
  --arg mcsbSha "$(sha256sum "$RAW/mcsb.json" | cut -d' ' -f1)" \
  --arg attackSha "$(sha256sum "$RAW/attack-paths.json" | cut -d' ' -f1)" \
  --arg revision "$APP_REVISION" --arg healthAt "$HEALTH_OBSERVED_AT" \
  --arg healthUrl "$HEALTH_URL" --arg readinessUrl "$READINESS_URL" \
  --arg targetOutput "$TARGET_OUTPUT" \
  --arg budgetAt "$BUDGET_QUERIED_AT" \
  --arg recommendationsAt "$RECOMMENDATIONS_QUERIED_AT" \
  --arg secureScoreAt "$SECURE_SCORE_QUERIED_AT" \
  --arg mcsbAt "$MCSB_QUERIED_AT" \
  --arg attackPathsAt "$ATTACK_PATH_QUERIED_AT" '
  {
    schemaVersion: "1.1.0",
    capturedAt: $capturedAt,
    identity: {
      handoff: {file:"evidence/modernization-contract.json",sha256:$handoffSha},
      targetOutput: {file:$targetOutput,sha256:$targetSha},
      labProfile: {file:"workshop/defender/lab-profile.json",sha256:$labSha},
      cleanupManifest: {file:"evidence/defender/cleanup-manifest.json",sha256:$cleanupSha}
    },
    foundation: {
      subscriptionId:$subscription,
      dedicatedWorkshopSubscription:true,
      facilitatorChangeApproval:"facilitator-approved participant Defender exercise",
      pricings:{file:"evidence/defender/foundation/pricings.json",sha256:$pricingsSha},
      budget:{file:"evidence/defender/foundation/budget.json",sha256:$budgetSha,queriedAt:$budgetAt,scopeResourceId:("/subscriptions/"+$subscription),apiVersion:"2023-11-01"},
      legacyVmCoverage:{file:"evidence/defender/foundation/legacy-vm-coverage.json",sha256:$coverageSha},
      seedSnapshot:{file:"evidence/defender/foundation/seed-snapshot.json",sha256:$seedSha},
      manualPreflight:{file:"evidence/defender/foundation/manual-preflight.json",sha256:$preflightSha}
    },
    resources: {
      containerRegistry:{before:{file:"evidence/defender/raw/acr-before.json",sha256:$acrBeforeSha},after:{file:"evidence/defender/raw/acr-after.json",sha256:$acrAfterSha}},
      containerRegistryRoleAssignments:{file:"evidence/defender/raw/acr-role-assignments.json",sha256:$rolesSha},
      containerApp:{before:{file:"evidence/defender/raw/container-app-before.json",sha256:$appBeforeSha},after:{file:"evidence/defender/raw/container-app-after.json",sha256:$appAfterSha}},
      database:{before:{file:"evidence/defender/raw/database-before.json",sha256:$dbBeforeSha},after:{file:"evidence/defender/raw/database-after.json",sha256:$dbAfterSha}},
      legacyVm:{before:{file:"evidence/defender/raw/vm-before.json",sha256:$vmBeforeSha},after:{file:"evidence/defender/raw/vm-after.json",sha256:$vmAfterSha}}
    },
    decisions: {
      containerAppIngress:{disposition:"justified",justification:"Public HTTPS remains required for this exact participant catalog endpoint.",compensatingControls:["HTTPS-only ingress","No insecure HTTP transport"]},
      databaseNetwork:{disposition:"remediated",justification:null,compensatingControls:[]},
      legacyVmExposure:{disposition:"remediated",justification:null,compensatingControls:[]}
    },
    imageAssessment:{file:"evidence/defender/raw/image-assessment.json",sha256:$imageSha,queriedAt:$imageAt,status:$imageStatus,digest:$digest,registryResourceId:$acr,apiVersion:"2019-01-01-preview"},
    securityContext:{
      recommendations:{file:"evidence/defender/raw/recommendations.json",sha256:$recSha,queriedAt:$recommendationsAt,scopeResourceId:("/subscriptions/"+$subscription),apiVersion:"2020-01-01"},
      secureScore:{file:"evidence/defender/raw/secure-score.json",sha256:$scoreSha,queriedAt:$secureScoreAt,scopeResourceId:("/subscriptions/"+$subscription),apiVersion:"2020-01-01"},
      mcsb:{file:"evidence/defender/raw/mcsb.json",sha256:$mcsbSha,queriedAt:$mcsbAt,scopeResourceId:("/subscriptions/"+$subscription),apiVersion:"2019-01-01-preview"},
      attackPaths:{file:"evidence/defender/raw/attack-paths.json",sha256:$attackSha,queriedAt:$attackPathsAt,scopeResourceId:("/subscriptions/"+$subscription),apiVersion:"2022-10-01"}
    },
    health:{observedAt:$healthAt,revisionName:$revision,healthUrl:$healthUrl,healthStatus:200,readinessUrl:$readinessUrl,readinessStatus:200}
  }
' \
  > "$CAPTURE"
```

The illustrative `jq` block deliberately requires you to replace the decision values
with captured truth before running it. It creates only the raw capture manifest. It
does not create normalized evidence.
Never copy fixture IDs, hashes, timestamps, findings, or example decisions.

## 9. Render and validate

From `tests/acceptance`, run the exact frozen registry commands:

```bash
uv --no-config run catalog-render-defender-evidence --capture evidence/defender/capture.json --handoff evidence/modernization-contract.json --output evidence/defender-report.json --repository-root ../..
uv --no-config run catalog-validate-defender-evidence --capture evidence/defender/capture.json --handoff evidence/modernization-contract.json --report evidence/defender-report.json --contracts workshop/contracts --repository-root ../..
```

Do not manually create, normalize, patch, or "fix" `evidence/defender-report.json`.
The renderer derives it from digest-bound raw captures; the validator replays the same
state independently.

False success includes: copying sanitized examples; aliasing seed and current files;
declaring an empty image query `completed`; inserting free text instead of a structured
subassessment; treating empty recommendations, Secure Score, MCSB, or attack paths as a
query failure; fabricating non-empty results; using a direct attack-path GET; omitting
the sibling VM; capturing a different VM/NIC/NSG; retaining ACR admin credentials;
losing exact ACR-scoped `AcrPull`; deploying a mutable tag; changing the image digest;
or manually writing normalized JSON.

## 10. Facilitator-only cleanup provenance

Participants stop after validation. They must not run cleanup. The facilitator-authorized
cleanup manifest digest-binds a before and optional post-cleanup composite. Its Resource
Graph producer is exactly:

```text
POST providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01
union Resources, InsightResources, SecurityResources, PolicyResources | where type in~ ('microsoft.compute/virtualmachines/extensions', 'microsoft.hybridcompute/machines/extensions', 'microsoft.insights/datacollectionruleassociations', 'microsoft.security/pricings', 'microsoft.authorization/policyassignments') | project id, name, type, properties, identity, location | order by id asc
```

The exact ARM list producers are:

```text
GET providers/Microsoft.Security/autoProvisioningSettings?api-version=2017-08-01-preview
GET providers/Microsoft.Security/settings?api-version=2021-06-01
```

`Resources` owns VM/Arc extensions, `InsightResources` owns Data Collection Rule
associations, `SecurityResources` owns pricings, and `PolicyResources` owns policy
assignments. Auto-provisioning and settings come only from their ARM list endpoints.
Their operations are `subscription-defender-auto-provisioning-settings` and
`subscription-defender-settings`.
Only an authorized facilitator may restore prior paid-plan pricing, subplan, enforce,
extension, agent, and policy state, verify the post-cleanup inventory, and issue the
cost query. Participants must not disable plans, delete agents/extensions/policies, or
inspect or alter another participant scope.
