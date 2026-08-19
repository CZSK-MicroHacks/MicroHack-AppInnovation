targetScope = 'resourceGroup'

param sourceVirtualNetworkName string
param targetVirtualNetworkResourceId string
param peeringName string

resource sourceVirtualNetwork 'Microsoft.Network/virtualNetworks@2024-05-01' existing = {
  name: sourceVirtualNetworkName
}

resource sourceToTargetPeering 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2024-05-01' = {
  parent: sourceVirtualNetwork
  name: peeringName
  properties: {
    allowForwardedTraffic: false
    allowGatewayTransit: false
    allowVirtualNetworkAccess: true
    remoteVirtualNetwork: {
      id: targetVirtualNetworkResourceId
    }
    useRemoteGateways: false
  }
}

output resourceId string = sourceToTargetPeering.id
