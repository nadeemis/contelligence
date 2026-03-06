// ============================================================================
// HikmaForge Alerts — Azure Monitor Metric Alerts
// ============================================================================
// Configures alerts for the HikmaForge agent based on Application Insights
// custom metrics.  Requires the Application Insights resource ID as input.
//
// Usage:
//   az deployment group create \
//     --resource-group <rg> \
//     --template-file alerts.bicep \
//     --parameters appInsightsResourceId=<id> actionGroupId=<id>
// ============================================================================

@description('Resource ID of the Application Insights instance.')
param appInsightsResourceId string

@description('Resource ID of the Action Group for alert notifications.')
param actionGroupId string

@description('Azure region.')
param location string = resourceGroup().location

// ---------------------------------------------------------------------------
// Alert: High Error Rate (> 50 errors in 5 min)
// ---------------------------------------------------------------------------
resource errorBurstAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'contelligence-error-burst'
  location: 'global'
  properties: {
    description: 'Fires when total errors exceed 50 in a 5-minute window.'
    severity: 2
    enabled: true
    scopes: [appInsightsResourceId]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'ErrorBurstCriteria'
          metricName: 'contelligence.errors'
          metricNamespace: 'Azure.ApplicationInsights'
          operator: 'GreaterThan'
          threshold: 50
          timeAggregation: 'Total'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [
      {
        actionGroupId: actionGroupId
        webHookProperties: {}
      }
    ]
  }
}

// ---------------------------------------------------------------------------
// Alert: Long Running Session (p95 > 3600s over 30 min)
// ---------------------------------------------------------------------------
resource longSessionAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'contelligence-long-session'
  location: 'global'
  properties: {
    description: 'Fires when session p95 duration exceeds 1 hour.'
    severity: 3
    enabled: true
    scopes: [appInsightsResourceId]
    evaluationFrequency: 'PT15M'
    windowSize: 'PT30M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'LongSessionCriteria'
          metricName: 'contelligence.session.duration'
          metricNamespace: 'Azure.ApplicationInsights'
          operator: 'GreaterThan'
          threshold: 3600
          timeAggregation: 'Average'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [
      {
        actionGroupId: actionGroupId
        webHookProperties: {}
      }
    ]
  }
}

// ---------------------------------------------------------------------------
// Alert: High Rate Limit Wait (p95 > 5s over 10 min)
// ---------------------------------------------------------------------------
resource rateLimitAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'contelligence-rate-limit-wait'
  location: 'global'
  properties: {
    description: 'Fires when rate limit wait p95 exceeds 5 seconds.'
    severity: 2
    enabled: true
    scopes: [appInsightsResourceId]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT10M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'RateLimitWaitCriteria'
          metricName: 'contelligence.rate_limit.wait_duration'
          metricNamespace: 'Azure.ApplicationInsights'
          operator: 'GreaterThan'
          threshold: 5000
          timeAggregation: 'Average'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [
      {
        actionGroupId: actionGroupId
        webHookProperties: {}
      }
    ]
  }
}
