targetScope = 'resourceGroup'

@description('Frozen SRE Agent registry loaded by the subscription entry point.')
param sreContract object

@description('Azure SRE Agent resource name.')
param agentName string

@description('Exact participant resource-group ID managed by the agent.')
param participantResourceGroupId string

@description('Existing handoff Application Insights resource ID.')
@secure()
param applicationInsightsResourceId string

@description('Existing handoff Application Insights resource name.')
param applicationInsightsName string

@description('Existing handoff Application Insights application ID.')
param applicationConnectorAppId string

@description('Existing handoff Log Analytics workspace resource ID.')
@secure()
param logAnalyticsWorkspaceResourceId string

@description('Existing handoff Log Analytics workspace name.')
param logAnalyticsWorkspaceName string

@description('Facilitator object ID for exact-agent administration and approval.')
param facilitatorPrincipalObjectId string

@description('Participant object ID for exact-agent standard access.')
param participantPrincipalObjectId string

@description('Microsoft Entra group object ID used as the initial sponsor group.')
param initialSponsorGroupId string

@description('Supported agent deployment region.')
param location string

@description('Tags applied to dedicated SRE Agent resources.')
param tags object

var userAssignedIdentityName = 'id-${agentName}'
var agentWorkspaceName = 'log-${agentName}'
var agentApplicationInsightsName = 'appi-${agentName}'
var facilitatorRoleDefinitionId = sreContract.rbac.humanRoles[0].roleDefinitionId
var participantRoleDefinitionId = sreContract.rbac.humanRoles[1].roleDefinitionId
var applicationConnector = sreContract.connectors[0]
var workspaceConnector = sreContract.connectors[1]

assert contractShapeIsFrozen = sreContract.resources.agentType == 'Microsoft.App/agents' && sreContract.resources.connectorType == 'Microsoft.App/agents/connectors'
assert connectorShapeIsFrozen = applicationConnector.name == 'application-insights' && applicationConnector.dataConnectorType == 'AppInsights' && workspaceConnector.name == 'log-analytics' && workspaceConnector.dataConnectorType == 'LogAnalytics'
assert humanRolesAreExact = sreContract.rbac.humanRoles[0].scope == 'agent-resource' && sreContract.rbac.humanRoles[1].scope == 'agent-resource'

resource actionIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: userAssignedIdentityName
  location: location
  tags: tags
}

resource agentWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: agentWorkspaceName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource agentApplicationInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: agentApplicationInsightsName
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: agentWorkspace.id
  }
}

resource agent 'Microsoft.App/agents@2026-01-01' = {
  name: agentName
  location: location
  tags: {
    'hidden-link:${agentApplicationInsights.id}': 'Resource'
  }
  identity: {
    type: sreContract.resources.identityMode
    userAssignedIdentities: {
      '${actionIdentity.id}': {}
    }
  }
  properties: {
    actionConfiguration: {
      accessLevel: sreContract.responsePlan.actionAccessLevel
      identity: actionIdentity.id
      mode: sreContract.responsePlan.autonomyMode
    }
    agentIdentity: {
      initialSponsorGroupId: initialSponsorGroupId
    }
    incidentManagementConfiguration: {
      connectionName: 'azure-monitor'
      type: sreContract.resources.incidentManagementType
    }
    knowledgeGraphConfiguration: {
      identity: actionIdentity.id
      managedResources: [
        participantResourceGroupId
      ]
    }
    logConfiguration: {
      applicationInsightsConfiguration: {
        appId: agentApplicationInsights.properties.AppId
        connectionString: agentApplicationInsights.properties.ConnectionString
      }
    }
    upgradeChannel: sreContract.resources.upgradeChannel
  }
}

resource appInsightsConnector 'Microsoft.App/agents/connectors@2026-01-01' = {
  name: applicationConnector.name
  parent: agent
  properties: {
    dataConnectorType: applicationConnector.dataConnectorType
    dataSource: applicationInsightsResourceId
    extendedProperties: {
      armResourceId: applicationInsightsResourceId
      'resource.name': applicationInsightsName
      appId: applicationConnectorAppId
    }
    identity: applicationConnector.identity
  }
}

resource logAnalyticsConnector 'Microsoft.App/agents/connectors@2026-01-01' = {
  name: workspaceConnector.name
  parent: agent
  properties: {
    dataConnectorType: workspaceConnector.dataConnectorType
    dataSource: logAnalyticsWorkspaceResourceId
    extendedProperties: {
      armResourceId: logAnalyticsWorkspaceResourceId
      'resource.name': logAnalyticsWorkspaceName
    }
    identity: workspaceConnector.identity
  }
}

resource facilitatorAdministrator 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(agent.id, facilitatorPrincipalObjectId, facilitatorRoleDefinitionId)
  scope: agent
  properties: {
    principalId: facilitatorPrincipalObjectId
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      facilitatorRoleDefinitionId
    )
  }
}

resource participantStandardUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(agent.id, participantPrincipalObjectId, participantRoleDefinitionId)
  scope: agent
  properties: {
    principalId: participantPrincipalObjectId
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      participantRoleDefinitionId
    )
  }
}

output agentResourceId string = agent.id
output userAssignedIdentityResourceId string = actionIdentity.id
output userAssignedPrincipalId string = actionIdentity.properties.principalId
output systemAssignedPrincipalId string = agent.identity.principalId
output agentApplicationInsightsResourceId string = agentApplicationInsights.id
output agentLogAnalyticsWorkspaceResourceId string = agentWorkspace.id
output connectorResourceIds array = [
  appInsightsConnector.id
  logAnalyticsConnector.id
]
output humanRoleAssignmentResourceIds array = [
  facilitatorAdministrator.id
  participantStandardUser.id
]
