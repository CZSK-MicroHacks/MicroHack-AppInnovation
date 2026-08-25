@description('Existing Application Insights component resource ID from the validated handoff.')
param applicationInsightsResourceId string

@description('Existing Log Analytics workspace resource ID from the validated handoff.')
param logAnalyticsWorkspaceResourceId string

@description('Existing Container App resource ID from the validated handoff.')
param containerAppResourceId string

@description('Frozen telemetry service.name from the validated handoff.')
@allowed([
  'mh-catalog-dotnet'
  'mh-catalog-java'
])
param serviceName string

@description('Exact lowercase 40-hex source commit represented by the existing revision.')
@minLength(40)
@maxLength(40)
param sourceCommit string

@description('Exact existing Container Apps revision name from the validated handoff.')
@minLength(1)
param revisionName string

@description('Explicit inclusive UTC query-window start in ISO 8601 format.')
param queryStartTime string

@description('Explicit inclusive UTC query-window end in ISO 8601 format.')
param queryEndTime string

@description('Workbook deployment location.')
param location string = resourceGroup().location

@description('Stable workbook resource GUID.')
param workbookName string = guid(logAnalyticsWorkspaceResourceId, 'catalog-observability')

var applicationInsightsSegments = split(applicationInsightsResourceId, '/')
var workspaceSegments = split(logAnalyticsWorkspaceResourceId, '/')
var containerAppSegments = split(containerAppResourceId, '/')
var applicationInsightsName = applicationInsightsSegments[8]
var workspaceName = workspaceSegments[8]
var containerAppName = containerAppSegments[8]

assert applicationInsightsIdIsTyped = length(applicationInsightsSegments) == 9 && applicationInsightsSegments[1] == 'subscriptions' && applicationInsightsSegments[3] == 'resourceGroups' && applicationInsightsSegments[5] == 'providers' && toLower(applicationInsightsSegments[6]) == 'microsoft.insights' && toLower(applicationInsightsSegments[7]) == 'components'
assert workspaceIdIsTyped = length(workspaceSegments) == 9 && workspaceSegments[1] == 'subscriptions' && workspaceSegments[3] == 'resourceGroups' && workspaceSegments[5] == 'providers' && toLower(workspaceSegments[6]) == 'microsoft.operationalinsights' && toLower(workspaceSegments[7]) == 'workspaces'
assert containerAppIdIsTyped = length(containerAppSegments) == 9 && containerAppSegments[1] == 'subscriptions' && containerAppSegments[3] == 'resourceGroups' && containerAppSegments[5] == 'providers' && toLower(containerAppSegments[6]) == 'microsoft.app' && toLower(containerAppSegments[7]) == 'containerapps'
assert applicationInsightsIsSameScope = toLower(applicationInsightsResourceId) == toLower(resourceId('Microsoft.Insights/components', applicationInsightsName))
assert workspaceIsSameScope = toLower(logAnalyticsWorkspaceResourceId) == toLower(resourceId('Microsoft.OperationalInsights/workspaces', workspaceName))
assert containerAppIsSameScope = toLower(containerAppResourceId) == toLower(resourceId('Microsoft.App/containerApps', containerAppName))
assert sourceCommitIsLowercase = sourceCommit == toLower(sourceCommit)
assert queryWindowIsExplicit = !empty(queryStartTime) && !empty(queryEndTime) && queryStartTime != queryEndTime

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: applicationInsightsName
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: workspaceName
}

resource containerApp 'Microsoft.App/containerApps@2024-03-01' existing = {
  name: containerAppName
}

var workbookTemplate = loadTextContent('../workshop/observability/workbook.json')
var serializedData = replace(replace(replace(replace(replace(replace(replace(
  workbookTemplate,
  '__START_TIME__',
  queryStartTime
), '__END_TIME__', queryEndTime), '__APPLICATION_INSIGHTS_RESOURCE_ID__', applicationInsightsResourceId), '__CONTAINER_APP_RESOURCE_ID__', containerAppResourceId), '__SERVICE_NAME__', serviceName), '__SOURCE_COMMIT__', sourceCommit), '__REVISION_NAME__', revisionName)

resource metricsExport 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'all-metrics-to-workspace'
  scope: containerApp
  properties: {
    workspaceId: logAnalyticsWorkspaceResourceId
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
        retentionPolicy: {
          days: 0
          enabled: false
        }
      }
    ]
  }
}

resource workbook 'Microsoft.Insights/workbooks@2023-06-01' = {
  name: workbookName
  location: location
  kind: 'shared'
  properties: {
    category: 'workbook'
    displayName: 'Catalog observability'
    description: 'Four revision-filtered application panels and one app-total replica panel.'
    serializedData: serializedData
    sourceId: logAnalyticsWorkspaceResourceId
    version: 'Notebook/1.0'
  }
}

output workbookResourceId string = workbook.id
output workbookSourceId string = logAnalyticsWorkspaceResourceId
output diagnosticSettingResourceId string = metricsExport.id
output metricsDestinationTable string = 'AzureMetrics'
output metricsScope string = 'container-app-total'
output metricsDimensionHandling string = 'flattened'
output existingApplicationInsightsResourceId string = applicationInsights.id
output existingWorkspaceResourceId string = workspace.id
