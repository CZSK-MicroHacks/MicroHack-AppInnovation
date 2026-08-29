param location string
param serverName string
param databaseName string
param facilitatorPrincipalName string
param facilitatorPrincipalObjectId string
param workloadIdentityName string
param workloadIdentityPrincipalId string
param dataSubnetResourceId string
param privateDnsZoneResourceId string

resource server 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: serverName
  location: location
  properties: {
    administrators: {
      administratorType: 'ActiveDirectory'
      principalType: 'User'
      login: facilitatorPrincipalName
      sid: facilitatorPrincipalObjectId
      tenantId: tenant().tenantId
      azureADOnlyAuthentication: true
    }
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Disabled'
    restrictOutboundNetworkAccess: 'Disabled'
  }
}

resource database 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: server
  name: databaseName
  location: location
  sku: {
    name: 'GP_S_Gen5'
    tier: 'GeneralPurpose'
    family: 'Gen5'
    capacity: 1
  }
  properties: {
    autoPauseDelay: 60
    minCapacity: json('0.5')
    readScale: 'Disabled'
    zoneRedundant: false
  }
}

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-${serverName}'
  location: location
  properties: {
    subnet: {
      id: dataSubnetResourceId
    }
    privateLinkServiceConnections: [
      {
        name: 'sql'
        properties: {
          privateLinkServiceId: server.id
          groupIds: [
            'sqlServer'
          ]
        }
      }
    ]
  }
}

resource privateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: privateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'sql'
        properties: {
          privateDnsZoneId: privateDnsZoneResourceId
        }
      }
    ]
  }
}

output databaseResourceId string = database.id
// environment().suffixes.sqlServerHostname already carries a leading dot ('.database.windows.net'),
// unlike suffixes.storage. Concatenating it after an explicit '.' produced a hostname with an empty
// DNS label that no resolver accepts. The server resource publishes the authoritative name instead.
output serverHost string = server.properties.fullyQualifiedDomainName
output databaseName string = database.name
output authentication string = 'managed-identity'
output localAdministratorPrincipal object? = null
output entraAdministratorPrincipal object? = null
output applicationPrincipal object = {
  name: workloadIdentityName
  kind: 'managed-identity'
  principalId: workloadIdentityPrincipalId
}
