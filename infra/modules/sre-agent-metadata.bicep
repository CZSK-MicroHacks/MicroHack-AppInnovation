targetScope = 'resourceGroup'

@description('Existing handoff Application Insights resource name.')
param applicationInsightsName string

@description('Exact existing handoff Application Insights resource ID.')
param applicationInsightsResourceId string

@description('Existing handoff Log Analytics workspace name.')
param logAnalyticsWorkspaceName string

@description('Exact existing handoff Log Analytics workspace resource ID.')
param logAnalyticsWorkspaceResourceId string

@description('Existing handoff Container App name.')
param containerAppName string

@description('Exact existing handoff Container App resource ID.')
param containerAppResourceId string

assert applicationInsightsIsExact = toLower(applicationInsightsResourceId) == toLower(resourceId('Microsoft.Insights/components', applicationInsightsName))
assert workspaceIsExact = toLower(logAnalyticsWorkspaceResourceId) == toLower(resourceId('Microsoft.OperationalInsights/workspaces', logAnalyticsWorkspaceName))
assert containerAppIsExact = toLower(containerAppResourceId) == toLower(resourceId('Microsoft.App/containerApps', containerAppName))

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: applicationInsightsName
}

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logAnalyticsWorkspaceName
}

resource containerApp 'Microsoft.App/containerApps@2025-01-01' existing = {
  name: containerAppName
}

output applicationInsightsAppId string = applicationInsights.properties.AppId
output applicationInsightsName string = applicationInsights.name
output applicationInsightsResourceId string = applicationInsights.id
output logAnalyticsWorkspaceName string = logAnalyticsWorkspace.name
output logAnalyticsWorkspaceResourceId string = logAnalyticsWorkspace.id
output containerAppName string = containerApp.name
output containerAppResourceId string = containerApp.id
