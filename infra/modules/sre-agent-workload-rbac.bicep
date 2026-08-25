targetScope = 'resourceGroup'

@description('Frozen SRE Agent registry loaded by the subscription entry point.')
param sreContract object

@description('Existing handoff Container App name.')
param containerAppName string

@description('Agent user-assigned identity principal ID.')
param userAssignedPrincipalId string

@description('Agent system-assigned identity principal ID.')
param systemAssignedPrincipalId string

@description('Full resource ID of the frozen custom rollback role definition.')
param customRollbackRoleDefinitionId string

var participantReaderRoles = [
  sreContract.rbac.knowledgeAndConnectorRoles[0]
  sreContract.rbac.knowledgeAndConnectorRoles[1]
  sreContract.rbac.knowledgeAndConnectorRoles[2]
]

assert participantRolesAreExact = participantReaderRoles[0].name == 'Reader' && participantReaderRoles[1].name == 'Log Analytics Reader' && participantReaderRoles[2].name == 'Monitoring Reader'
assert customRoleIsExact = sreContract.rbac.customRollbackRole.scope == 'exact-container-app' && sreContract.rbac.customRollbackRole.principal == 'user-assigned'

resource containerApp 'Microsoft.App/containerApps@2025-01-01' existing = {
  name: containerAppName
}

resource userAssignedReaderRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for role in participantReaderRoles: {
    name: guid(resourceGroup().id, userAssignedPrincipalId, role.roleDefinitionId)
    properties: {
      principalId: userAssignedPrincipalId
      principalType: 'ServicePrincipal'
      roleDefinitionId: subscriptionResourceId(
        'Microsoft.Authorization/roleDefinitions',
        role.roleDefinitionId
      )
    }
  }
]

resource systemAssignedReaderRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for role in participantReaderRoles: {
    name: guid(resourceGroup().id, systemAssignedPrincipalId, role.roleDefinitionId)
    properties: {
      principalId: systemAssignedPrincipalId
      principalType: 'ServicePrincipal'
      roleDefinitionId: subscriptionResourceId(
        'Microsoft.Authorization/roleDefinitions',
        role.roleDefinitionId
      )
    }
  }
]

resource rollbackAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerApp.id, userAssignedPrincipalId, customRollbackRoleDefinitionId)
  scope: containerApp
  properties: {
    principalId: userAssignedPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: customRollbackRoleDefinitionId
  }
}

output roleAssignmentResourceIds array = concat(
  [
    userAssignedReaderRoles[0].id
    userAssignedReaderRoles[1].id
    userAssignedReaderRoles[2].id
  ],
  [
    systemAssignedReaderRoles[0].id
    systemAssignedReaderRoles[1].id
    systemAssignedReaderRoles[2].id
  ],
  [
    rollbackAssignment.id
  ]
)
