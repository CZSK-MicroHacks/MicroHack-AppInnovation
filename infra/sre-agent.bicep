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

@description('Optional resource tags applied to the dedicated P8 resources.')
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

@description('Non-secret facilitator handoff for P8 foundation capture.')
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
  responsePlanConfiguredInIaC: false
}
