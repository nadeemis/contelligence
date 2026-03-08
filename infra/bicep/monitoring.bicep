// ============================================================================
// Contelligence Monitoring — Application Insights & Log Analytics (AVM)
// ============================================================================
// Wraps AVM modules for Log Analytics and Application Insights.
// ============================================================================

@description('Name of the Log Analytics workspace.')
param workspaceName string = 'contelligence-logs'

@description('Name of the Application Insights resource.')
param appInsightsName string = 'contelligence-insights'

@description('Azure region.')
param location string = resourceGroup().location

@description('Retention period in days for Log Analytics.')
param retentionDays int = 90

@description('Tags to apply.')
param tags object = {}

// ---------------------------------------------------------------------------
// Log Analytics Workspace (AVM)
// ---------------------------------------------------------------------------
module logAnalytics 'br/public:avm/res/operational-insights/workspace:0.15.0' = {
  name: '${workspaceName}-deploy'
  params: {
    name: workspaceName
    location: location
    tags: tags
    skuName: 'PerGB2018'
    dataRetention: retentionDays
  }
}

// ---------------------------------------------------------------------------
// Application Insights (AVM)
// ---------------------------------------------------------------------------
module appInsights 'br/public:avm/res/insights/component:0.7.1' = {
  name: '${appInsightsName}-deploy'
  params: {
    name: appInsightsName
    location: location
    tags: tags
    workspaceResourceId: logAnalytics.outputs.resourceId
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------
@description('Application Insights connection string (set as APPLICATIONINSIGHTS_CONNECTION_STRING).')
output appInsightsConnectionString string = appInsights.outputs.connectionString

@description('Application Insights instrumentation key.')
output appInsightsInstrumentationKey string = appInsights.outputs.instrumentationKey

@description('Log Analytics workspace resource ID.')
output logAnalyticsWorkspaceId string = logAnalytics.outputs.resourceId
