targetScope = 'resourceGroup'

@description('Name of the user-assigned identity used only by the catalog workflows.')
@minLength(3)
@maxLength(128)
param identityName string = 'id-catalog-github'

@description('GitHub repository in exact owner/repository form.')
param githubRepository string

@description('Exact handoff Azure Container Registry resource ID.')
param containerRegistryResourceId string

@description('Exact handoff Azure Container App resource ID.')
param containerAppResourceId string

@description('Optional resource tags for the CI/CD identity.')
param tags object = {}

var registrySegments = split(containerRegistryResourceId, '/')
var containerAppSegments = split(containerAppResourceId, '/')
var registrySubscriptionId = registrySegments[2]
var registryResourceGroupName = registrySegments[4]
var registryName = registrySegments[8]
var containerAppSubscriptionId = containerAppSegments[2]
var containerAppResourceGroupName = containerAppSegments[4]
var containerAppName = containerAppSegments[8]
var repositorySegments = split(githubRepository, '/')
var acrPushRoleDefinitionId = '8311e382-0749-4cb8-b61a-304f252e45ec'
var containerAppsContributorRoleDefinitionId = '358470bc-b998-42bd-ab17-a7e34c199c0f'

assert repositoryIsOwnerAndName = length(repositorySegments) == 2 && !empty(repositorySegments[0]) && !empty(repositorySegments[1])
assert registryIdIsTyped = length(registrySegments) == 9 && registrySegments[1] == 'subscriptions' && registrySegments[3] == 'resourceGroups' && registrySegments[5] == 'providers' && toLower(registrySegments[6]) == 'microsoft.containerregistry' && toLower(registrySegments[7]) == 'registries'
assert containerAppIdIsTyped = length(containerAppSegments) == 9 && containerAppSegments[1] == 'subscriptions' && containerAppSegments[3] == 'resourceGroups' && containerAppSegments[5] == 'providers' && toLower(containerAppSegments[6]) == 'microsoft.app' && toLower(containerAppSegments[7]) == 'containerapps'
assert resourcesShareDeploymentSubscription = toLower(registrySubscriptionId) == toLower(subscription().subscriptionId) && toLower(containerAppSubscriptionId) == toLower(subscription().subscriptionId)
assert handoffResourcesShareDeploymentGroup = toLower(registryResourceGroupName) == toLower(resourceGroup().name) && toLower(containerAppResourceGroupName) == toLower(resourceGroup().name)

resource registry 'Microsoft.ContainerRegistry/registries@2025-04-01' existing = {
  name: registryName
}

resource containerApp 'Microsoft.App/containerApps@2025-01-01' existing = {
  name: containerAppName
}

resource workflowIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: identityName
  location: resourceGroup().location
  tags: tags
}

resource stagingCredential 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2024-11-30' = {
  name: 'staging'
  parent: workflowIdentity
  properties: {
    audiences: [
      'api://AzureADTokenExchange'
    ]
    issuer: 'https://token.actions.githubusercontent.com'
    subject: 'repo:${githubRepository}:environment:staging'
  }
}

resource productionCredential 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2024-11-30' = {
  name: 'production'
  parent: workflowIdentity
  properties: {
    audiences: [
      'api://AzureADTokenExchange'
    ]
    issuer: 'https://token.actions.githubusercontent.com'
    subject: 'repo:${githubRepository}:environment:production'
  }
  dependsOn: [
    stagingCredential
  ]
}

resource registryPush 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, workflowIdentity.id, acrPushRoleDefinitionId)
  scope: registry
  properties: {
    principalId: workflowIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      acrPushRoleDefinitionId
    )
  }
}

resource containerAppDeployment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerApp.id, workflowIdentity.id, containerAppsContributorRoleDefinitionId)
  scope: containerApp
  properties: {
    principalId: workflowIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      containerAppsContributorRoleDefinitionId
    )
  }
}

output identityResourceId string = workflowIdentity.id
output identityClientId string = workflowIdentity.properties.clientId
output identityPrincipalId string = workflowIdentity.properties.principalId
output stagingFederatedCredentialResourceId string = stagingCredential.id
output productionFederatedCredentialResourceId string = productionCredential.id
output acrPushRoleAssignmentResourceId string = registryPush.id
output containerAppsContributorRoleAssignmentResourceId string = containerAppDeployment.id
output containerRegistryScope string = registry.id
output containerAppScope string = containerApp.id
