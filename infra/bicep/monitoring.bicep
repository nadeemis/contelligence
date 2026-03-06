// ============================================================================
// Contelligence Monitoring — Application Insights & Log Analytics
// ============================================================================
// Provisions the Log Analytics workspace and Application Insights resource
// for the Contelligence agent observability stack.
//
// Usage:
//   az deployment group create \
//     --resource-group <rg> \
//     --template-file monitoring.bicep \
//     --parameters workspaceName=<name>
// ============================================================================

@description('Name of the Log Analytics workspace.')
param workspaceName string = 'contelligence-logs'

@description('Name of the Application Insights resource.')
param appInsightsName string = 'contelligence-insights'

@description('Azure region.')
param location string = resourceGroup().location

@description('Retention period in days for Log Analytics.')
param retentionDays int = 90

// ---------------------------------------------------------------------------
// Log Analytics Workspace
// ---------------------------------------------------------------------------
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: retentionDays
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

// ---------------------------------------------------------------------------
// Application Insights (workspace-based)
// ---------------------------------------------------------------------------
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    IngestionMode: 'LogAnalytics'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------
@description('Application Insights connection string (set as APPLICATIONINSIGHTS_CONNECTION_STRING).')
output appInsightsConnectionString string = appInsights.properties.ConnectionString

@description('Application Insights instrumentation key.')
output appInsightsInstrumentationKey string = appInsights.properties.InstrumentationKey

@description('Log Analytics workspace ID.')
output logAnalyticsWorkspaceId string = logAnalytics.id
