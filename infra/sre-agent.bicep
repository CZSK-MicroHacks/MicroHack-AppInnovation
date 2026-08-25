targetScope = 'subscription'

@description('Short lowercase participant or team identifier.')
@minLength(2)
@maxLength(20)
param teamName string

@description('Exact Container App resource ID from the validated modernization handoff.')
param containerAppResourceId string

@description('Exact Application Insights resource ID from the validated modernization handoff.')
param applicationInsightsResourceId string

@description('Exact Log Analytics workspace resource ID from the validated modernization handoff.')
param logAnalyticsWorkspaceResourceId string

@description('Facilitator object ID that receives SRE Agent Administrator at the exact agent.')
param facilitatorPrincipalObjectId string

@description('Participant object ID that receives SRE Agent Standard User at the exact agent.')
param participantPrincipalObjectId string

@description('Microsoft Entra group object ID used as the initial SRE Agent sponsor group.')
param initialSponsorGroupId string

@description('Supported Azure SRE Agent deployment region.')
param location string = 'swedencentral'

@description('Dedicated resource group name for the participant SRE Agent.')
param agentResourceGroupName string = 'rg-sre-${teamName}'

@description('Azure SRE Agent resource name.')
@minLength(2)
@maxLength(32)
param agentName string = 'sre-catalog-${teamName}'

@description('Optional resource tags applied to the dedicated SRE Agent resources.')
param tags object = {}

var sreContract = loadJsonContent('../workshop/contracts/sre-agent.json')
var containerAppSegments = split(containerAppResourceId, '/')
var applicationInsightsSegments = split(applicationInsightsResourceId, '/')
var workspaceSegments = split(logAnalyticsWorkspaceResourceId, '/')
var participantResourceGroupName = containerAppSegments[4]
var participantResourceGroupId = '/subscriptions/${subscription().subscriptionId}/resourceGroups/${participantResourceGroupName}'
var containerAppName = containerAppSegments[8]
var applicationInsightsName = applicationInsightsSegments[8]
var workspaceName = workspaceSegments[8]
var monitoringContributorRoleDefinitionId = sreContract.rbac.knowledgeAndConnectorRoles[3].roleDefinitionId
var rollbackRoleDefinitionGuid = guid(
  subscription().id,
  participantResourceGroupId,
  sreContract.rbac.customRollbackRole.name
)

assert contractVersionIsFrozen = sreContract.schemaVersion == '1.2.0'
assert locationIsFrozen = location == 'swedencentral'
assert teamNameIsLowercase = teamName == toLower(teamName) && !contains(teamName, ' ')
assert principalIdsAreExplicit = !empty(facilitatorPrincipalObjectId) && !empty(participantPrincipalObjectId) && !empty(initialSponsorGroupId)
assert containerAppIdIsTyped = length(containerAppSegments) == 9 && containerAppSegments[1] == 'subscriptions' && containerAppSegments[3] == 'resourceGroups' && containerAppSegments[5] == 'providers' && toLower(containerAppSegments[6]) == 'microsoft.app' && toLower(containerAppSegments[7]) == 'containerapps'
assert applicationInsightsIdIsTyped = length(applicationInsightsSegments) == 9 && applicationInsightsSegments[1] == 'subscriptions' && applicationInsightsSegments[3] == 'resourceGroups' && applicationInsightsSegments[5] == 'providers' && toLower(applicationInsightsSegments[6]) == 'microsoft.insights' && toLower(applicationInsightsSegments[7]) == 'components'
assert workspaceIdIsTyped = length(workspaceSegments) == 9 && workspaceSegments[1] == 'subscriptions' && workspaceSegments[3] == 'resourceGroups' && workspaceSegments[5] == 'providers' && toLower(workspaceSegments[6]) == 'microsoft.operationalinsights' && toLower(workspaceSegments[7]) == 'workspaces'
assert handoffResourcesShareSubscription = toLower(containerAppSegments[2]) == toLower(subscription().subscriptionId) && toLower(applicationInsightsSegments[2]) == toLower(subscription().subscriptionId) && toLower(workspaceSegments[2]) == toLower(subscription().subscriptionId)
assert handoffResourcesShareResourceGroup = toLower(applicationInsightsSegments[4]) == toLower(participantResourceGroupName) && toLower(workspaceSegments[4]) == toLower(participantResourceGroupName)
assert dedicatedAgentResourceGroupIsSeparate = toLower(agentResourceGroupName) != toLower(participantResourceGroupName)
assert frozenAgentShapeIsConsumed = sreContract.resources.agentApiVersion == '2026-01-01' && sreContract.resources.connectorApiVersion == '2026-01-01' && sreContract.resources.identityMode == 'SystemAssigned,UserAssigned' && sreContract.responsePlan.autonomyMode == 'Review' && sreContract.responsePlan.actionAccessLevel == 'Low'

resource participantResourceGroup 'Microsoft.Resources/resourceGroups@2024-11-01' existing = {
  name: participantResourceGroupName
}

resource agentResourceGroup 'Microsoft.Resources/resourceGroups@2024-11-01' = {
  name: agentResourceGroupName
  location: location
  tags: union(tags, {
    workload: 'microhack-appinnovation'
    participant: teamName
    challenge: sreContract.challenge.id
  })
}

module targetMetadata 'modules/sre-agent-metadata.bicep' = {
  name: 'sre-target-${uniqueString(participantResourceGroup.id, agentName)}'
  scope: participantResourceGroup
  params: {
    applicationInsightsName: applicationInsightsName
    applicationInsightsResourceId: applicationInsightsResourceId
    containerAppName: containerAppName
    containerAppResourceId: containerAppResourceId
    logAnalyticsWorkspaceName: workspaceName
    logAnalyticsWorkspaceResourceId: logAnalyticsWorkspaceResourceId
  }
}

resource rollbackRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: rollbackRoleDefinitionGuid
  properties: {
    roleName: sreContract.rbac.customRollbackRole.name
    description: 'Allows only reading Container App state and changing traffic weights for the selected workshop app.'
    type: 'CustomRole'
    permissions: [
      {
        actions: sreContract.rbac.customRollbackRole.actions
        notActions: sreContract.rbac.customRollbackRole.notActions
        dataActions: sreContract.rbac.customRollbackRole.dataActions
        notDataActions: sreContract.rbac.customRollbackRole.notDataActions
      }
    ]
    assignableScopes: [
      participantResourceGroup.id
    ]
  }
}

module foundation 'modules/sre-agent-foundation.bicep' = {
  name: 'sre-foundation-${uniqueString(agentResourceGroup.id, agentName)}'
  scope: agentResourceGroup
  params: {
    agentName: agentName
    applicationConnectorAppId: targetMetadata.outputs.applicationInsightsAppId
    applicationInsightsName: targetMetadata.outputs.applicationInsightsName
    applicationInsightsResourceId: targetMetadata.outputs.applicationInsightsResourceId
    facilitatorPrincipalObjectId: facilitatorPrincipalObjectId
    initialSponsorGroupId: initialSponsorGroupId
    location: location
    logAnalyticsWorkspaceName: targetMetadata.outputs.logAnalyticsWorkspaceName
    logAnalyticsWorkspaceResourceId: targetMetadata.outputs.logAnalyticsWorkspaceResourceId
    participantPrincipalObjectId: participantPrincipalObjectId
    participantResourceGroupId: participantResourceGroup.id
    sreContract: sreContract
    tags: union(tags, {
      workload: 'microhack-appinnovation'
      participant: teamName
      challenge: sreContract.challenge.id
    })
  }
}

module workloadRbac 'modules/sre-agent-workload-rbac.bicep' = {
  name: 'sre-rbac-${uniqueString(participantResourceGroup.id, agentName)}'
  scope: participantResourceGroup
  params: {
    containerAppName: targetMetadata.outputs.containerAppName
    customRollbackRoleDefinitionId: rollbackRole.id
    sreContract: sreContract
    systemAssignedPrincipalId: foundation.outputs.systemAssignedPrincipalId
    userAssignedPrincipalId: foundation.outputs.userAssignedPrincipalId
  }
}

resource monitoringContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, agentResourceGroupName, agentName, monitoringContributorRoleDefinitionId)
  properties: {
    principalId: foundation.outputs.userAssignedPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      monitoringContributorRoleDefinitionId
    )
  }
}

// The agent's incident response plan (incident filter + handler + autonomy level) is not
// declared here because the Azure SRE Agent control plane does not expose it. Verified
// 2026-08-25 against api-version 2026-01-01:
//
//   * Azure/azure-rest-api-specs, path specification/app/resource-manager/Microsoft.App/
//     SreAgent/stable/2026-01-01/sreagent.json, exposes exactly four PUT-able resource
//     paths - Microsoft.App/agentSpaces, Microsoft.App/agentSpaces/connectors,
//     Microsoft.App/agents and Microsoft.App/agents/connectors. Its AgentProperties
//     definition carries no response-plan property, so a plan cannot be nested on the
//     agent either.
//   * `az provider show --namespace Microsoft.App` returns no response-plan child type.
//   * Bicep resolves Microsoft.App/agents/connectors at this api-version but reports
//     BCP081 "does not have types available" for Microsoft.App/agents/responsePlans,
//     .../incidentResponsePlans, .../plans and .../customAgents, confirming those types
//     do not exist rather than merely lacking a type definition locally.
//   * https://learn.microsoft.com/azure/sre-agent/incident-response-plans and
//     https://learn.microsoft.com/azure/sre-agent/response-plan (both read 2026-08-25)
//     document creation only through the portal Builder > Incident response plans page
//     or the Agent Canvas wizard. The single programmatic surface is the agent data
//     plane, reached through `azmcp sreagent incidents plans create` - see
//     https://learn.microsoft.com/azure/developer/azure-mcp-server/tools/azure-sre-agent
//     - which is not ARM and therefore cannot be expressed in this template.
//
// The frozen contract encodes the same conclusion: responsePlan.producer is
// `azure-portal-facilitator-export` and responsePlan.opaqueIncidentFiltersInIaCAllowed is
// false, so the plan is captured as reviewed portal evidence rather than opaque filter
// JSON. What this template does own in code is every part of the plan that is an agent
// property: actionConfiguration.mode (Review), actionConfiguration.accessLevel (Low), the
// Azure Monitor incident-management connection, and the bounded traffic-only rollback
// role. The facilitator must still create one Azure Monitor plan named
// `catalog-reviewed-rollback` covering the Challenge 6 signal/remediation pair - a Sev2
// `MH-SRE-` failed-request alert on the bad Container App revision, remediated by shifting
// traffic weight back to the retained healthy revision - delete the auto-created quickstart
// plan, run the reject-path test incident, and export
// evidence/sre-agent/response-plan-preflight.json. That procedure is
// workshop/sre-agent/README.md, section "Configure and preflight the response plan".
// Revisit this flag when Microsoft.App ships a response-plan resource type.
@description('Non-secret facilitator handoff for SRE Agent foundation capture.')
output sreAgentFoundation object = {
  contractVersion: sreContract.schemaVersion
  participantResourceGroupId: participantResourceGroup.id
  containerAppResourceId: targetMetadata.outputs.containerAppResourceId
  agentResourceGroupId: agentResourceGroup.id
  agentResourceId: foundation.outputs.agentResourceId
  agentName: agentName
  location: location
  userAssignedIdentityResourceId: foundation.outputs.userAssignedIdentityResourceId
  userAssignedPrincipalId: foundation.outputs.userAssignedPrincipalId
  systemAssignedPrincipalId: foundation.outputs.systemAssignedPrincipalId
  agentApplicationInsightsResourceId: foundation.outputs.agentApplicationInsightsResourceId
  agentLogAnalyticsWorkspaceResourceId: foundation.outputs.agentLogAnalyticsWorkspaceResourceId
  connectorResourceIds: foundation.outputs.connectorResourceIds
  customRollbackRoleDefinitionId: rollbackRole.id
  participantRoleAssignmentResourceIds: workloadRbac.outputs.roleAssignmentResourceIds
  monitoringContributorRoleAssignmentResourceId: monitoringContributor.id
  humanRoleAssignmentResourceIds: foundation.outputs.humanRoleAssignmentResourceIds
  // False is verified, not aspirational - see the response-plan note above this output.
  responsePlanConfiguredInIaC: false
}
