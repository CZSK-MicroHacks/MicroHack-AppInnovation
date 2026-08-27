// Private DNS for an internal Container Apps environment.
//
// This lives in its own module because `defaultDomain` is only known once the
// environment exists, and Bicep requires a private DNS zone name to be resolvable at
// the start of the deployment that declares it. Passing the domain into a nested
// deployment as a parameter satisfies that constraint.

@description('The environment defaultDomain, e.g. bluetree-675945f1.swedencentral.azurecontainerapps.io.')
param environmentDefaultDomain string

@description('The private static ingress IP of the internal Container Apps environment.')
param environmentStaticIp string

@description('The environment VNet that hosts the container apps infrastructure subnet.')
param virtualNetworkResourceId string

@description('The migration-source VNet holding the participant VMs.')
param migrationSourceVirtualNetworkResourceId string

@description('Deterministic link name for the migration-source VNet.')
param migrationDnsLinkName string

resource zone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: environmentDefaultDomain
  location: 'global'
}

resource environmentLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: zone
  name: 'container-apps-vnet'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: virtualNetworkResourceId
    }
  }
}

// The participant VMs are the only place the workshop asks anybody to open the
// application from, so without this link the emitted URL resolves from nowhere.
resource migrationSourceLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: zone
  name: migrationDnsLinkName
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: migrationSourceVirtualNetworkResourceId
    }
  }
}

// Wildcard covers every container app in the environment, so adding apps later needs
// no DNS change.
resource wildcard 'Microsoft.Network/privateDnsZones/A@2024-06-01' = {
  parent: zone
  name: '*'
  properties: {
    ttl: 3600
    aRecords: [
      {
        ipv4Address: environmentStaticIp
      }
    ]
  }
}

output privateDnsZoneResourceId string = zone.id
