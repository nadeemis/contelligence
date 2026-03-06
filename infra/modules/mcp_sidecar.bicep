// ---------------------------------------------------------------------------
// Azure MCP Server — sidecar container for HTTP-mode deployment
// ---------------------------------------------------------------------------
// Deploy alongside the main Contelligence agent in Azure Container Apps.
// The MCP server is exposed via internal-only ingress on port 5008.
// ---------------------------------------------------------------------------

@description('Name of the Container App Environment')
param containerAppEnvironmentId string

@description('Azure region for the resource')
param location string = resourceGroup().location

@description('Application Insights connection string (secret reference)')
@secure()
param appInsightsConnectionString string = ''

@description('Disable Microsoft-collected telemetry')
param collectTelemetryMicrosoft string = 'false'

@description('MCP server image')
param mcpImage string = 'mcr.microsoft.com/azure-sdk/azure-mcp:latest'

@description('CPU allocation')
param cpu string = '0.5'

@description('Memory allocation')
param memory string = '1Gi'

// ---------------------------------------------------------------------------

resource mcpSidecar 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'azure-mcp-server'
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppEnvironmentId
    configuration: {
      ingress: {
        external: false
        targetPort: 5008
        transport: 'http'
      }
      secrets: !empty(appInsightsConnectionString) ? [
        {
          name: 'appinsights-connection'
          value: appInsightsConnectionString
        }
      ] : []
    }
    template: {
      containers: [
        {
          name: 'azure-mcp'
          image: mcpImage
          command: [
            'azmcp'
            'server'
            'start'
            '--transport'
            'http'
            '--port'
            '5008'
          ]
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: concat(
            [
              {
                name: 'AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT'
                value: collectTelemetryMicrosoft
              }
            ],
            !empty(appInsightsConnectionString) ? [
              {
                name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
                secretRef: 'appinsights-connection'
              }
            ] : []
          )
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

@description('FQDN of the MCP sidecar (internal only)')
output mcpFqdn string = mcpSidecar.properties.configuration.ingress.fqdn

@description('Managed identity principal ID for RBAC assignments')
output mcpPrincipalId string = mcpSidecar.identity.principalId
