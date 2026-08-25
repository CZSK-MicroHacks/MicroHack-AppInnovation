targetScope = 'resourceGroup'

@description('Name of the Azure Load Testing resource used by the Challenge 2 performance gate.')
@minLength(1)
@maxLength(64)
param loadTestName string = 'lt-catalog'

@description('Globally unique name of the Key Vault holding the performance-test API key.')
@minLength(3)
@maxLength(24)
param keyVaultName string = 'kv-cat-${uniqueString(resourceGroup().id)}'

@description('''Principal ID of the user-assigned identity used only by the catalog workflows.
Leave empty in Challenge 2, where the identity does not exist yet: the load test and vault
are still created, and only the two workflow role assignments are skipped. Challenge 3
redeploys this template with the real principal ID to grant them.''')
param workflowIdentityPrincipalId string = ''

var grantWorkflowIdentity = !empty(workflowIdentityPrincipalId)

@description('Optional resource tags for the performance-testing resources.')
param tags object = {}

var loadTestContributorRoleDefinitionId = '749a398d-560b-491b-bb21-08924219302e'
var keyVaultSecretsUserRoleDefinitionId = '4633458b-17de-408a-b874-0445c86b69e6'

resource loadTest 'Microsoft.LoadTestService/loadTests@2022-12-01' = {
  name: loadTestName
  location: resourceGroup().location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    description: 'Catalog modernization performance gate.'
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2024-11-01' = {
  name: keyVaultName
  location: resourceGroup().location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enabledForDeployment: false
    enabledForTemplateDeployment: false
    enabledForDiskEncryption: false
    publicNetworkAccess: 'Enabled'
  }
}

resource workflowLoadTestContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (grantWorkflowIdentity) {
  name: guid(loadTest.id, workflowIdentityPrincipalId, loadTestContributorRoleDefinitionId)
  scope: loadTest
  properties: {
    principalId: workflowIdentityPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      loadTestContributorRoleDefinitionId
    )
  }
}

resource workflowSecretsRead 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (grantWorkflowIdentity) {
  name: guid(keyVault.id, workflowIdentityPrincipalId, keyVaultSecretsUserRoleDefinitionId)
  scope: keyVault
  properties: {
    principalId: workflowIdentityPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      keyVaultSecretsUserRoleDefinitionId
    )
  }
}

resource loadTestSecretsRead 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, loadTest.id, keyVaultSecretsUserRoleDefinitionId)
  scope: keyVault
  properties: {
    principalId: loadTest.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      keyVaultSecretsUserRoleDefinitionId
    )
  }
}

output loadTestResourceId string = loadTest.id
output loadTestName string = loadTest.name
output keyVaultResourceId string = keyVault.id
output keyVaultName string = keyVault.name
output keyVaultUri string = keyVault.properties.vaultUri
output loadTestContributorRoleAssignmentResourceId string = grantWorkflowIdentity
  ? workflowLoadTestContributor.id
  : ''
output workflowSecretsUserRoleAssignmentResourceId string = grantWorkflowIdentity
  ? workflowSecretsRead.id
  : ''
output loadTestSecretsUserRoleAssignmentResourceId string = loadTestSecretsRead.id
