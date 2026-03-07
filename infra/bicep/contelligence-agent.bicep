// ============================================================================
// Contelligence Agent — Azure Container App
// ============================================================================
// Provisions the Container App with:
//   - Horizontal autoscaling (HTTP concurrency + CPU utilization)
//   - Sticky sessions for SSE stream affinity
//   - Phase 4 environment variables for all production-hardening components
//
// Usage:
//   az deployment group create \
//     --resource-group <rg> \
//     --template-file contelligence-agent.bicep \
//     --parameters acrName=<acr> containerAppEnvId=<cae-id>
// ============================================================================

@description('Name of the Container App.')
param containerAppName string = 'contelligence-agent'

@description('Azure region for the Container App.')
param location string = resourceGroup().location

@description('Name of the Azure Container Registry.')
param acrName string

@description('Container App Environment resource ID.')
param containerAppEnvId string

@description('Container image tag.')
param imageTag string = 'latest'

// --- Scaling parameters ---

@description('Minimum number of replicas (always-on).')
@minValue(0)
param minReplicas int = 1

@description('Maximum number of replicas.')
@minValue(1)
param maxReplicas int = 10

@description('HTTP concurrent requests threshold for scale-out.')
param httpConcurrency string = '10'

@description('CPU utilization percentage threshold for scale-out.')
param cpuThreshold string = '70'

// --- Authentication parameters ---

@description('Azure AD tenant ID for JWT auth.')
param azureAdTenantId string = ''

@description('Azure AD client (app registration) ID for JWT auth.')
param azureAdClientId string = ''

@description('Enable RBAC authentication.')
param authEnabled bool = true

// --- Rate limiting parameters ---

@description('OpenAI requests per minute.')
param rateLimitOpenaiRpm int = 60

@description('Document Intelligence requests per minute.')
param rateLimitDocIntelRpm int = 30

// --- Dependent resource references ---

@description('Application Insights connection string.')
@secure()
param appInsightsConnectionString string = ''

@description('Key Vault URI.')
param keyVaultUrl string = ''

// --- Retention / Caching ---

@description('Session retention in days.')
param sessionRetentionDays int = 365

@description('Cache TTL in days.')
param cacheTtlDays int = 30

// --- Copilot CLI ---

@description('Internal URL of the Copilot CLI headless server (host:port).')
param copilotCliUrl string = ''

// =========================================================================
// Container App
// =========================================================================

resource agentApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppEnvId
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        stickySessions: {
          affinity: 'sticky'
        }
      }
      registries: [
        {
          server: '${acrName}.azurecr.io'
          identity: 'system'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'agent'
          image: '${acrName}.azurecr.io/contelligence-agent:${imageTag}'
          resources: {
            cpu: json('2.0')
            memory: '4Gi'
          }
          env: [
            // --- Application Insights ---
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: appInsightsConnectionString
            }
            // --- Key Vault ---
            {
              name: 'KEY_VAULT_URL'
              value: keyVaultUrl
            }
            // --- Authentication ---
            {
              name: 'AZURE_AD_TENANT_ID'
              value: azureAdTenantId
            }
            {
              name: 'AZURE_AD_CLIENT_ID'
              value: azureAdClientId
            }
            {
              name: 'AUTH_ENABLED'
              value: string(authEnabled)
            }
            // --- Rate Limiting ---
            {
              name: 'RATE_LIMIT_OPENAI_RPM'
              value: string(rateLimitOpenaiRpm)
            }
            {
              name: 'RATE_LIMIT_DOC_INTEL_RPM'
              value: string(rateLimitDocIntelRpm)
            }
            // --- Retention / Caching ---
            {
              name: 'SESSION_RETENTION_DAYS'
              value: string(sessionRetentionDays)
            }
            {
              name: 'CACHE_TTL_DAYS'
              value: string(cacheTtlDays)
            }
            // --- Copilot CLI ---
            {
              name: 'CLI_URL'
              value: copilotCliUrl
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: httpConcurrency
              }
            }
          }
          {
            name: 'cpu-scaling'
            custom: {
              type: 'cpu'
              metadata: {
                type: 'Utilization'
                value: cpuThreshold
              }
            }
          }
        ]
      }
    }
  }
}

// =========================================================================
// Outputs
// =========================================================================

@description('Container App FQDN.')
output containerAppFqdn string = agentApp.properties.configuration.ingress.fqdn

@description('Container App name.')
output containerAppName string = agentApp.name

@description('Container App managed identity principal ID.')
output principalId string = agentApp.identity.principalId
