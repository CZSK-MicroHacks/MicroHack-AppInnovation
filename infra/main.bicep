targetScope = 'subscription'

@description('Deployment stage. Bootstrap never creates a Container App.')
@allowed([
  'bootstrap'
  'application'
])
param deploymentStage string

@description('Modernized application and database stack.')
@allowed([
  'dotnet-sqlserver'
  'java-postgresql'
])
param stack string

@description('External image provider.')
@allowed([
  'azure-blob'
  'azure-files'
])
param imageProvider string = 'azure-blob'

@description('Java application database authentication.')
@allowed([
  'password-secret'
  'managed-identity'
])
param postgresqlAuthentication string = 'managed-identity'

@description('Participant or team resource group.')
param resourceGroupName string

@description('Short lowercase participant/team name used in deterministic resource names.')
@minLength(2)
@maxLength(20)
param teamName string

@description('Exact lowercase 40-hex source commit represented by this target.')
param sourceCommit string

@description('Facilitator signed-in user principal name.')
param facilitatorPrincipalName string

@description('Facilitator signed-in user object ID.')
param facilitatorPrincipalObjectId string

@description('Immutable application image repository within the target ACR.')
param imageRepository string = stack == 'dotnet-sqlserver' ? 'catalog-dotnet' : 'catalog-java'

@description('Exact sha256 image manifest digest for application-stage deployments.')
param imageDigest string = ''

@description('Local PostgreSQL administrator principal.')
param postgresqlAdministratorName string = 'catalogadmin'

@description('PostgreSQL password-mode application role.')
param postgresqlApplicationName string = 'catalog_app'

@secure()
@description('Required for Java infrastructure; never emitted.')
param postgresqlAdministratorPassword string = ''

@secure()
@description('Required only for Java password-secret application stage; stored as an ACA secret.')
param postgresqlApplicationPassword string = ''

@secure()
@description('Required only for application stage; stored as an ACA secret.')
param performanceApiKey string = ''

param location string = 'swedencentral'

var isApplication = deploymentStage == 'application'
var isJava = stack == 'java-postgresql'
var sourceCommitNonHex = replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(sourceCommit, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '')
var imageDigestHash = last(split(imageDigest, ':'))
var imageDigestNonHex = replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(imageDigestHash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '')

assert locationIsFrozen = location == 'swedencentral'
assert teamNameIsLowercase = teamName == toLower(teamName) && !contains(teamName, ' ')
assert sourceCommitIsImmutable = length(sourceCommit) == 40 && sourceCommit == toLower(sourceCommit) && empty(sourceCommitNonHex)
assert applicationDigestIsImmutable = !isApplication || (length(imageDigest) == 71 && startsWith(imageDigest, 'sha256:') && empty(imageDigestNonHex))
assert applicationSecretsArePresent = !isApplication || !empty(performanceApiKey)
assert postgresqlAdministratorSecretIsPresent = !isJava || !empty(postgresqlAdministratorPassword)
assert postgresqlApplicationSecretIsModeSpecific = !isJava || deploymentStage == 'bootstrap' || postgresqlAuthentication == 'managed-identity' || !empty(postgresqlApplicationPassword)
assert dotnetAuthenticationIsFixed = isJava || postgresqlAuthentication == 'managed-identity'

resource resourceGroup 'Microsoft.Resources/resourceGroups@2024-11-01' = {
  name: resourceGroupName
  location: location
  tags: {
    workload: 'microhack-appinnovation'
    participant: teamName
    stack: stack
  }
}

module environment 'modules/environment.bicep' = {
  name: 'environment-${uniqueString(resourceGroup.id, stack, imageProvider)}'
  scope: resourceGroup
  params: {
    deploymentStage: deploymentStage
    stack: stack
    imageProvider: imageProvider
    postgresqlAuthentication: postgresqlAuthentication
    teamName: teamName
    sourceCommit: sourceCommit
    facilitatorPrincipalName: facilitatorPrincipalName
    facilitatorPrincipalObjectId: facilitatorPrincipalObjectId
    imageRepository: imageRepository
    imageDigest: imageDigest
    postgresqlAdministratorName: postgresqlAdministratorName
    postgresqlApplicationName: postgresqlApplicationName
    postgresqlAdministratorPassword: postgresqlAdministratorPassword
    postgresqlApplicationPassword: postgresqlApplicationPassword
    performanceApiKey: performanceApiKey
    location: location
  }
}

@description('Frozen shared Azure target-output document.')
output targetOutput object = environment.outputs.targetOutput
