// ============================================================================
// Contelligence Agent — Azure Container App (AVM)
// ============================================================================
// Wraps AVM br/public:avm/res/app/container-app:0.20.0 with:
//   - Horizontal autoscaling (HTTP concurrency + CPU utilization)
//   - Sticky sessions for SSE stream affinity
//   - All production environment variables
// ============================================================================

@description('Name of the Container App.')
param containerAppName string = 'contelligence-agent'

@description('Azure region for the Container App.')
param location string = resourceGroup().location

@description('Name of the Azure Container Registry.')
param acrName string

@description('ACR login server (e.g. crxxx.azurecr.io).')
param acrLoginServer string

@description('Container App Environment resource ID.')
param containerAppEnvId string

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

// --- Azure Service Endpoints ---

@description('Tags to apply to the Container App.')
param tags object = {}

@description('ACR admin password for registry authentication.')
@secure()
param acrPassword string = ''

@description('Container image (placeholder for initial provisioning).')
param containerImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('Azure Cosmos DB endpoint.')
param cosmosEndpoint string = ''

@description('Azure Storage account name.')
param storageAccountName string = ''

@description('Azure AI Search account name.')
param searchAccountName string = ''

@description('Azure Document Intelligence endpoint.')
param docIntelligenceEndpoint string = ''

@description('Azure OpenAI endpoint.')
param openAIEndpoint string = ''

@description('Azure OpenAI chat model deployment name.')
param openAIDeployment string = 'gpt-41'

@description('Azure OpenAI embedding model deployment name.')
param openAIEmbeddingsDeployment string = 'text-embedding-3-large'

@description('Azure MCP Server URL (HTTP mode).')
param mcpServerUrl string = ''

// =========================================================================
// Container App (AVM)
// =========================================================================

module agentApp 'br/public:avm/res/app/container-app:0.20.0' = {
  name: '${containerAppName}-deploy'
  params: {
    name: containerAppName
    location: location
    tags: union(tags, { 'azd-service-name': 'agent' })
    environmentResourceId: containerAppEnvId
    managedIdentities: {
      systemAssigned: true
    }
    ingressExternal: true
    ingressTargetPort: 8000
    ingressTransport: 'auto'
    stickySessionsAffinity: 'sticky'
    secrets: [
      {
        name: 'registry-password'
        value: acrPassword
      }
    ]
    registries: [
      {
        server: acrLoginServer
        username: acrName
        passwordSecretRef: 'registry-password'
      }
    ]
    containers: [
      {
        name: 'agent'
        image: containerImage
        resources: {
          cpu: '2'
          memory: '4Gi'
        }
        env: [
          { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
          { name: 'KEY_VAULT_URL', value: keyVaultUrl }
          { name: 'AZURE_AD_TENANT_ID', value: azureAdTenantId }
          { name: 'AZURE_AD_CLIENT_ID', value: azureAdClientId }
          { name: 'AUTH_ENABLED', value: string(authEnabled) }
          { name: 'RATE_LIMIT_OPENAI_RPM', value: string(rateLimitOpenaiRpm) }
          { name: 'RATE_LIMIT_DOC_INTEL_RPM', value: string(rateLimitDocIntelRpm) }
          { name: 'SESSION_RETENTION_DAYS', value: string(sessionRetentionDays) }
          { name: 'CACHE_TTL_DAYS', value: string(cacheTtlDays) }
          { name: 'CLI_URL', value: copilotCliUrl }
          { name: 'AZURE_COSMOS_ENDPOINT', value: cosmosEndpoint }
          { name: 'AZURE_STORAGE_ACCOUNT_NAME', value: storageAccountName }
          { name: 'AZURE_SEARCH_ACCOUNT_NAME', value: searchAccountName }
          { name: 'AZURE_DOC_INTELLIGENCE_ENDPOINT', value: docIntelligenceEndpoint }
          { name: 'AZURE_OPENAI_ENDPOINT', value: openAIEndpoint }
          { name: 'AZURE_OPENAI_DEPLOYMENT', value: openAIDeployment }
          { name: 'AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT', value: openAIEmbeddingsDeployment }
          { name: 'AZURE_MCP_SERVER_URL', value: mcpServerUrl }
        ]
      }
    ]
    scaleSettings: {
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

// =========================================================================
// Outputs
// =========================================================================

@description('Container App FQDN.')
output fqdn string = agentApp.outputs.fqdn

@description('Container App name.')
output containerAppName string = agentApp.outputs.name

@description('Container App managed identity principal ID.')
output principalId string = agentApp.outputs.systemAssignedMIPrincipalId
