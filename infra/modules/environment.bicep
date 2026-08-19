targetScope = 'resourceGroup'

param deploymentStage string
param stack string
param imageProvider string
param postgresqlAuthentication string
@minLength(2)
@maxLength(20)
param teamName string
param sourceCommit string
param facilitatorPrincipalName string
param facilitatorPrincipalObjectId string
param imageRepository string
param imageDigest string
param postgresqlAdministratorName string
param postgresqlApplicationName string
@secure()
param postgresqlAdministratorPassword string
@secure()
param postgresqlApplicationPassword string
@secure()
param performanceApiKey string
param location string

var isApplication = deploymentStage == 'application'
var isJava = stack == 'java-postgresql'
var isBlob = imageProvider == 'azure-blob'
var stackName = isJava ? 'java' : 'dotnet'
var suffix = take(uniqueString(resourceGroup().id, stackName), 8)
var baseName = 'mh-${teamName}-${stackName}'
var compactName = take(replace('${teamName}${stackName}${suffix}', '-', ''), 20)
var virtualNetworkName = 'vnet-${baseName}'
var registryName = take('acr${compactName}', 50)
var identityName = 'id-${baseName}'
var environmentName = 'cae-${baseName}'
var containerAppName = 'ca-${baseName}'
var storageAccountName = take('st${compactName}', 24)
var imageLocationName = 'catalog-images'
var workspaceName = 'log-${baseName}'
var insightsName = 'appi-${baseName}'
var databaseName = 'catalog'
var sqlServerName = take('sql-${baseName}-${suffix}', 63)
var postgresqlServerName = take('psql-${baseName}-${suffix}', 63)
var revisionSuffix = take(sourceCommit, 12)
var revisionName = '${containerAppName}--${revisionSuffix}'
var acrPullRole = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
var blobDataReaderRole = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1')
var blobDataContributorRole = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
var fileDataPrivilegedContributorRole = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '69566ab7-960f-475b-8e7c-b3118f30c6bd')

resource virtualNetwork 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: virtualNetworkName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.42.0.0/16'
      ]
    }
    subnets: [
      {
        name: 'container-apps'
        properties: {
          addressPrefix: '10.42.0.0/23'
          delegations: [
            {
              name: 'container-apps'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: 'private-endpoints'
        properties: {
          addressPrefix: '10.42.2.0/24'
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
      {
        name: 'postgresql'
        properties: {
          addressPrefix: '10.42.3.0/24'
          delegations: [
            {
              name: 'postgresql'
              properties: {
                serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers'
              }
            }
          ]
        }
      }
    ]
  }
}

resource containerAppsSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' existing = {
  parent: virtualNetwork
  name: 'container-apps'
}

resource privateEndpointSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' existing = {
  parent: virtualNetwork
  name: 'private-endpoints'
}

resource postgresqlSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' existing = {
  parent: virtualNetwork
  name: 'postgresql'
}

resource storagePrivateDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: isBlob ? 'privatelink.blob.${environment().suffixes.storage}' : 'privatelink.file.${environment().suffixes.storage}'
  location: 'global'
}

resource storageDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: storagePrivateDnsZone
  name: 'storage-vnet'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: virtualNetwork.id
    }
  }
}

resource sqlPrivateDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = if (!isJava) {
  name: 'privatelink.${environment().suffixes.sqlServerHostname}'
  location: 'global'
}

resource sqlDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = if (!isJava) {
  parent: sqlPrivateDnsZone
  name: 'sql-vnet'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: virtualNetwork.id
    }
  }
}

resource postgresqlPrivateDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = if (isJava) {
  name: 'private.postgres.database.azure.com'
  location: 'global'
}

resource postgresqlDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = if (isJava) {
  parent: postgresqlPrivateDnsZone
  name: 'postgresql-vnet'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: virtualNetwork.id
    }
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: registryName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    anonymousPullEnabled: false
    dataEndpointEnabled: false
    publicNetworkAccess: 'Enabled'
    zoneRedundancy: 'Disabled'
  }
}

resource workloadIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, workloadIdentity.id, acrPullRole)
  scope: registry
  properties: {
    principalId: workloadIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: acrPullRole
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2025-01-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowCrossTenantReplication: false
    allowSharedKeyAccess: !isBlob
    defaultToOAuthAuthentication: isBlob
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Disabled'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2025-01-01' = if (isBlob) {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: false
    }
  }
}

resource blobContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-01-01' = if (isBlob) {
  parent: blobService
  name: imageLocationName
  properties: {
    publicAccess: 'None'
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2025-01-01' = if (!isBlob) {
  parent: storage
  name: 'default'
}

resource fileShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2025-01-01' = if (!isBlob) {
  parent: fileService
  name: imageLocationName
  properties: {
    enabledProtocols: 'SMB'
    accessTier: 'TransactionOptimized'
    shareQuota: 512
  }
}

resource storagePrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-${storage.name}-${isBlob ? 'blob' : 'file'}'
  location: location
  properties: {
    subnet: {
      id: privateEndpointSubnet.id
    }
    privateLinkServiceConnections: [
      {
        name: isBlob ? 'blob' : 'file'
        properties: {
          privateLinkServiceId: storage.id
          groupIds: [
            isBlob ? 'blob' : 'file'
          ]
        }
      }
    ]
  }
}

resource storagePrivateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: storagePrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: isBlob ? 'blob' : 'file'
        properties: {
          privateDnsZoneId: storagePrivateDnsZone.id
        }
      }
    ]
  }
}

resource blobRead 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (isBlob) {
  name: guid(blobContainer.id, workloadIdentity.id, blobDataReaderRole)
  scope: blobContainer
  properties: {
    principalId: workloadIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: blobDataReaderRole
  }
}

resource facilitatorBlobMigration 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (isBlob) {
  name: guid(blobContainer.id, facilitatorPrincipalObjectId, blobDataContributorRole)
  scope: blobContainer
  properties: {
    principalId: facilitatorPrincipalObjectId
    principalType: 'User'
    roleDefinitionId: blobDataContributorRole
  }
}

resource facilitatorFileMigration 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!isBlob) {
  name: guid(fileShare.id, facilitatorPrincipalObjectId, fileDataPrivilegedContributorRole)
  scope: fileShare
  properties: {
    principalId: facilitatorPrincipalObjectId
    principalType: 'User'
    roleDefinitionId: fileDataPrivilegedContributorRole
  }
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  properties: {
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: insightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    Flow_Type: 'Bluefield'
    IngestionMode: 'LogAnalytics'
    WorkspaceResourceId: workspace.id
    DisableIpMasking: false
  }
}

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2024-10-02-preview' = {
  name: environmentName
  location: location
  properties: {
    appInsightsConfiguration: {
      connectionString: applicationInsights.properties.ConnectionString
    }
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspace.properties.customerId
        sharedKey: workspace.listKeys().primarySharedKey
      }
    }
    openTelemetryConfiguration: {
      tracesConfiguration: {
        destinations: [
          'appInsights'
        ]
      }
      logsConfiguration: {
        destinations: [
          'appInsights'
        ]
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: containerAppsSubnet.id
      internal: false
    }
    zoneRedundant: false
  }
}

resource environmentStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = if (!isBlob) {
  parent: containerAppsEnvironment
  name: 'catalog-images'
  properties: {
    azureFile: {
      accessMode: 'ReadOnly'
      accountKey: storage.listKeys().keys[0].value
      accountName: storage.name
      shareName: fileShare.name
    }
  }
}

module sql 'sql.bicep' = if (!isJava) {
  name: 'sql'
  params: {
    location: location
    serverName: sqlServerName
    databaseName: databaseName
    facilitatorPrincipalName: facilitatorPrincipalName
    facilitatorPrincipalObjectId: facilitatorPrincipalObjectId
    workloadIdentityName: workloadIdentity.name
    workloadIdentityPrincipalId: workloadIdentity.properties.principalId
    dataSubnetResourceId: privateEndpointSubnet.id
    privateDnsZoneResourceId: sqlPrivateDnsZone.id
  }
}

module postgresql 'postgresql.bicep' = if (isJava) {
  name: 'postgresql'
  params: {
    location: location
    serverName: postgresqlServerName
    databaseName: databaseName
    authentication: postgresqlAuthentication
    administratorName: postgresqlAdministratorName
    administratorPassword: postgresqlAdministratorPassword
    applicationName: postgresqlApplicationName
    facilitatorPrincipalName: facilitatorPrincipalName
    facilitatorPrincipalObjectId: facilitatorPrincipalObjectId
    workloadIdentityName: workloadIdentity.name
    workloadIdentityPrincipalId: workloadIdentity.properties.principalId
    delegatedSubnetResourceId: postgresqlSubnet.id
    privateDnsZoneResourceId: postgresqlPrivateDnsZone.id
  }
}

var databaseOutput = isJava ? {
  resourceId: postgresql!.outputs.databaseResourceId
  family: 'postgresql-flexible'
  server: postgresql!.outputs.serverHost
  database: postgresql!.outputs.databaseName
  authentication: postgresql!.outputs.authentication
  localAdministratorPrincipal: postgresql!.outputs.localAdministratorPrincipal
  entraAdministratorPrincipal: postgresql!.outputs.entraAdministratorPrincipal
  applicationPrincipal: postgresql!.outputs.applicationPrincipal
} : {
  resourceId: sql!.outputs.databaseResourceId
  family: 'azure-sql'
  server: sql!.outputs.serverHost
  database: sql!.outputs.databaseName
  authentication: sql!.outputs.authentication
  localAdministratorPrincipal: sql!.outputs.localAdministratorPrincipal
  entraAdministratorPrincipal: sql!.outputs.entraAdministratorPrincipal
  applicationPrincipal: sql!.outputs.applicationPrincipal
}

var commonEnvironment = [
  {
    name: 'CATALOG_DATABASE_HOST'
    value: databaseOutput.server
  }
  {
    name: 'CATALOG_DATABASE_NAME'
    value: databaseOutput.database
  }
  {
    name: 'CATALOG_DATABASE_PORT'
    value: isJava ? '5432' : '1433'
  }
  {
    name: 'CATALOG_DATABASE_AUTHENTICATION'
    value: isJava ? postgresqlAuthentication : 'managed-identity'
  }
  {
    name: 'CATALOG_IMAGES_PATH'
    value: '/app/images'
  }
  {
    name: 'CATALOG_SEED_PATH'
    value: '/app/data/catalog.json'
  }
  {
    name: 'CATALOG_STARTUP_IMPORT_ENABLED'
    value: 'false'
  }
  {
    name: 'CATALOG_IMAGE_PROVIDER'
    value: isBlob ? 'azure-blob' : 'local'
  }
  {
    name: 'AZURE_CLIENT_ID'
    value: workloadIdentity.properties.clientId
  }
  {
    name: 'DEPLOYMENT_ENVIRONMENT'
    value: 'lab'
  }
  {
    name: 'OTEL_SERVICE_VERSION'
    value: sourceCommit
  }
  {
    name: 'OTEL_EXPORTER_OTLP_ENDPOINT'
    value: 'http://localhost:4317'
  }
  {
    name: 'CONTAINER_APP_REVISION'
    value: revisionName
  }
  {
    name: 'PERFTEST_API_KEY'
    secretRef: 'performance-api-key'
  }
]

var javaEnvironment = isJava ? concat([
  {
    name: 'CATALOG_DATABASE_USERNAME'
    value: databaseOutput.applicationPrincipal.name
  }
  {
    name: 'CATALOG_DATABASE_SSL_MODE'
    value: 'require'
  }
], postgresqlAuthentication == 'managed-identity' ? [
  {
    name: 'CATALOG_DATABASE_JDBC_AUTH_PARAMETER'
    value: '&authenticationPluginClassName=com.azure.identity.extensions.jdbc.postgresql.AzurePostgresqlAuthenticationPlugin'
  }
] : [
  {
    name: 'CATALOG_DATABASE_PASSWORD'
    secretRef: 'database-application-password'
  }
]) : []

var blobEnvironment = isBlob ? [
  {
    name: 'CATALOG_BLOB_SERVICE_ENDPOINT'
    value: 'https://${storage.name}.blob.${environment().suffixes.storage}'
  }
  {
    name: 'CATALOG_BLOB_CONTAINER'
    value: blobContainer.name
  }
] : []

var applicationSecrets = concat([
  {
    name: 'performance-api-key'
    value: performanceApiKey
  }
], isJava && postgresqlAuthentication == 'password-secret' ? [
  {
    name: 'database-application-password'
    value: postgresqlApplicationPassword
  }
] : [])

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = if (isApplication) {
  name: containerAppName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${workloadIdentity.id}': {}
    }
  }
  properties: {
    environmentId: containerAppsEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        allowInsecure: false
        external: true
        targetPort: 8080
        transport: 'auto'
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: workloadIdentity.id
        }
      ]
      secrets: applicationSecrets
    }
    template: {
      revisionSuffix: revisionSuffix
      containers: [
        {
          name: 'catalog'
          image: '${registry.properties.loginServer}/${imageRepository}@${imageDigest}'
          env: concat(commonEnvironment, javaEnvironment, blobEnvironment)
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/healthz'
                port: 8080
                scheme: 'HTTP'
              }
              initialDelaySeconds: 10
              periodSeconds: 10
              timeoutSeconds: 3
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/readyz'
                port: 8080
                scheme: 'HTTP'
              }
              initialDelaySeconds: 5
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 3
            }
          ]
          volumeMounts: !isBlob ? [
            {
              mountPath: '/app/images'
              volumeName: 'catalog-images'
            }
          ] : []
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
        rules: [
          {
            name: 'http'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
      volumes: !isBlob ? [
        {
          name: 'catalog-images'
          storageName: environmentStorage.name
          storageType: 'AzureFile'
        }
      ] : []
    }
  }
}

var environmentDomain = containerAppsEnvironment.properties.defaultDomain
var applicationUrl = isApplication ? 'https://${containerAppName}.${environmentDomain}' : ''
var imageResourceId = isBlob ? blobContainer.id : fileShare.id

output targetOutput object = {
  schemaVersion: '1.0.0'
  deploymentStage: deploymentStage
  sourceCommit: sourceCommit
  stack: stack
  location: location
  resourceGroup: {
    name: resourceGroup().name
    resourceId: resourceGroup().id
  }
  network: {
    virtualNetworkResourceId: virtualNetwork.id
  }
  containerRegistry: {
    resourceId: registry.id
    loginServer: registry.properties.loginServer
  }
  workloadIdentity: {
    resourceId: workloadIdentity.id
    clientId: workloadIdentity.properties.clientId
    principalId: workloadIdentity.properties.principalId
  }
  containerAppsEnvironmentResourceId: containerAppsEnvironment.id
  containerAppsEnvironmentDefaultDomain: environmentDomain
  database: databaseOutput
  images: {
    resourceId: imageResourceId
    provider: imageProvider
    location: imageLocationName
    authentication: isBlob ? 'managed-identity' : 'aca-volume-secret'
  }
  observability: {
    applicationInsightsResourceId: applicationInsights.id
    logAnalyticsWorkspaceResourceId: workspace.id
  }
  containerImage: isApplication ? {
    repository: imageRepository
    tag: sourceCommit
    digest: imageDigest
  } : null
  application: isApplication ? {
    resourceId: containerApp.id
    url: applicationUrl
    healthUrl: '${applicationUrl}/healthz'
    readinessUrl: '${applicationUrl}/readyz'
    containerAppName: containerAppName
    revisionName: revisionName
  } : null
}
