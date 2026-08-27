targetScope = 'resourceGroup'

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

@description('Exact source VNet resource ID used by the migration runner.')
param migrationSourceVirtualNetworkResourceId string

@description('Exact stack-specific source VM resource ID used by catalog-migrate.')
param migrationSourceVmResourceId string

@description('Application revision role. Bootstrap requires an empty value.')
@allowed([
  ''
  'baseline'
  'release'
])
param applicationRevisionRole string

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

@description('Set true when the subscription blocks public IP creation (for example the Microsoft.Network/AllowBringYourOwnPublicIpAddress feature is not registered). An internal Container Apps environment is fronted by an internal load balancer and never allocates a public IP, so the catalog is then reachable only from inside the peered virtual network.')
param containerAppsEnvironmentInternal bool = false

var isApplication = deploymentStage == 'application'
var isJava = stack == 'java-postgresql'
var sourceCommitNonHex = replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(sourceCommit, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '')
var imageDigestHash = last(split(imageDigest, ':'))
var imageDigestNonHex = replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(imageDigestHash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '')
var sourceVirtualNetworkSegments = split(migrationSourceVirtualNetworkResourceId, '/')
var sourceVmSegments = split(migrationSourceVmResourceId, '/')
var sourceSubscriptionId = sourceVirtualNetworkSegments[2]
var sourceResourceGroupName = sourceVirtualNetworkSegments[4]
var sourceVirtualNetworkName = last(sourceVirtualNetworkSegments)

assert locationIsFrozen = location == 'swedencentral'
assert teamNameIsLowercase = teamName == toLower(teamName) && !contains(teamName, ' ')
assert sourceCommitIsImmutable = length(sourceCommit) == 40 && sourceCommit == toLower(sourceCommit) && empty(sourceCommitNonHex)
assert applicationDigestIsImmutable = !isApplication || (length(imageDigest) == 71 && startsWith(imageDigest, 'sha256:') && empty(imageDigestNonHex))
assert applicationSecretsArePresent = !isApplication || !empty(performanceApiKey)
assert postgresqlAdministratorSecretIsPresent = !isJava || !empty(postgresqlAdministratorPassword)
assert postgresqlApplicationSecretIsModeSpecific = !isJava || deploymentStage == 'bootstrap' || postgresqlAuthentication == 'managed-identity' || !empty(postgresqlApplicationPassword)
assert dotnetAuthenticationIsFixed = isJava || postgresqlAuthentication == 'managed-identity'
assert revisionRoleMatchesStage = isApplication ? contains([
  'baseline'
  'release'
], applicationRevisionRole) : empty(applicationRevisionRole)
assert sourceVirtualNetworkIdIsTyped = length(sourceVirtualNetworkSegments) == 9 && sourceVirtualNetworkSegments[1] == 'subscriptions' && sourceVirtualNetworkSegments[3] == 'resourceGroups' && sourceVirtualNetworkSegments[5] == 'providers' && toLower(sourceVirtualNetworkSegments[6]) == 'microsoft.network' && toLower(sourceVirtualNetworkSegments[7]) == 'virtualnetworks'
assert sourceVmIdIsTyped = length(sourceVmSegments) == 9 && sourceVmSegments[1] == 'subscriptions' && sourceVmSegments[3] == 'resourceGroups' && sourceVmSegments[5] == 'providers' && toLower(sourceVmSegments[6]) == 'microsoft.compute' && toLower(sourceVmSegments[7]) == 'virtualmachines'
assert migrationResourcesShareSubscription = toLower(sourceVirtualNetworkSegments[2]) == toLower(subscription().subscriptionId) && toLower(sourceVmSegments[2]) == toLower(subscription().subscriptionId)
assert migrationResourcesShareSourceScope = toLower(sourceVmSegments[4]) == toLower(sourceResourceGroupName)
assert migrationVmMatchesStack = startsWith(toLower(last(sourceVmSegments)), isJava ? 'vm-java-' : 'vm-dotnet-')

// The participant's resource group is created before the workshop, together with the two
// legacy VMs, and the participant holds Owner on it. Creating it here would require
// subscription-level rights nobody in the room has, so this template only fills it.
assert deploysIntoTheParticipantResourceGroup = toLower(resourceGroupName) == toLower(resourceGroup().name)

// The legacy VMs being migrated from live in that same group, so peering can only ever
// reach the participant's own network. Without this, a mistyped or copied resource id
// would aim the peering at somebody else's environment.
assert migratesFromTheParticipantResourceGroup = toLower(sourceResourceGroupName) == toLower(resourceGroupName)

module environment 'modules/environment.bicep' = {
  name: 'environment-${uniqueString(resourceGroup().id, stack, imageProvider)}'
  params: {
    deploymentStage: deploymentStage
    stack: stack
    imageProvider: imageProvider
    postgresqlAuthentication: postgresqlAuthentication
    teamName: teamName
    sourceCommit: sourceCommit
    migrationSourceVirtualNetworkResourceId: migrationSourceVirtualNetworkResourceId
    migrationSourceVmResourceId: migrationSourceVmResourceId
    applicationRevisionRole: applicationRevisionRole
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
    containerAppsEnvironmentInternal: containerAppsEnvironmentInternal
  }
}

module sourcePeering 'modules/source-peering.bicep' = {
  name: 'source-peering-${uniqueString(migrationSourceVirtualNetworkResourceId, resourceGroupName, stack)}'
  scope: az.resourceGroup(sourceSubscriptionId, sourceResourceGroupName)
  params: {
    sourceVirtualNetworkName: sourceVirtualNetworkName
    targetVirtualNetworkResourceId: environment.outputs.virtualNetworkResourceId
    peeringName: 'to-${last(split(environment.outputs.virtualNetworkResourceId, '/'))}'
  }
}

@description('Frozen shared Azure target-output document.')
output targetOutput object = union(environment.outputs.targetOutput, {
  network: union(environment.outputs.targetOutput.network, {
    migrationSourceToTargetPeeringResourceId: sourcePeering.outputs.resourceId
  })
})
