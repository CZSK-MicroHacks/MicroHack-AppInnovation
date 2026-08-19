param location string
param serverName string
param databaseName string
param authentication string
param administratorName string
@secure()
param administratorPassword string
param applicationName string
param facilitatorPrincipalName string
param facilitatorPrincipalObjectId string
param workloadIdentityName string
param workloadIdentityPrincipalId string
param delegatedSubnetResourceId string
param privateDnsZoneResourceId string

resource server 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: serverName
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '18'
    administratorLogin: administratorName
    administratorLoginPassword: administratorPassword
    authConfig: {
      activeDirectoryAuth: 'Enabled'
      passwordAuth: 'Enabled'
      tenantId: tenant().tenantId
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      delegatedSubnetResourceId: delegatedSubnetResourceId
      privateDnsZoneArmResourceId: privateDnsZoneResourceId
      publicNetworkAccess: 'Disabled'
    }
    storage: {
      storageSizeGB: 32
      autoGrow: 'Enabled'
    }
  }
}

resource entraAdministrator 'Microsoft.DBforPostgreSQL/flexibleServers/administrators@2024-08-01' = {
  parent: server
  name: facilitatorPrincipalObjectId
  properties: {
    principalName: facilitatorPrincipalName
    principalType: 'User'
    tenantId: tenant().tenantId
  }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: server
  name: databaseName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

output databaseResourceId string = database.id
output serverHost string = '${server.name}.postgres.database.azure.com'
output databaseName string = database.name
output authentication string = authentication
output localAdministratorPrincipal object = {
  name: administratorName
  authentication: 'password'
}
output entraAdministratorPrincipal object = {
  name: facilitatorPrincipalName
  objectId: facilitatorPrincipalObjectId
  principalType: 'user'
}
output applicationPrincipal object = authentication == 'managed-identity' ? {
  name: workloadIdentityName
  kind: 'managed-identity'
  principalId: workloadIdentityPrincipalId
} : {
  name: applicationName
  kind: 'database-role'
  principalId: null
}
