// ============================================================================
// Contelligence — Main Bicep Template (resource-group scoped)
// ============================================================================
// Orchestrates full provisioning for azd up using Azure Verified Modules (AVM):
//   - Container Registry (ACR)
//   - Log Analytics & Application Insights
//   - Container Apps Environment
//   - Storage Account + blob container + lifecycle policy
//   - Cosmos DB (sessions, conversation, outputs, cache, etc.)
//   - Key Vault
//   - Azure OpenAI + model deployments
//   - Azure AI Search
//   - Azure Document Intelligence
//   - Copilot CLI Container App (headless Copilot SDK backend)
//   - Agent Container App (FastAPI backend)
//   - Web Container App (React SPA)
//   - RBAC role assignments (managed identity, least privilege)
// ============================================================================

targetScope = 'resourceGroup'

// ---------------------------------------------------------------------------
// Parameters
// ---------------------------------------------------------------------------

@minLength(1)
@maxLength(64)
@description('Name of the azd environment — used to generate unique resource names.')
param environmentName string

@minLength(1)
@description('Primary Azure region for all resources.')
param location string

@description('Azure AD tenant ID for JWT authentication (optional).')
param azureAdTenantId string = ''

@description('Azure AD client ID for JWT authentication (optional).')
param azureAdClientId string = ''

@description('GitHub Copilot token for the Copilot CLI service (store in azd env as COPILOT_GITHUB_TOKEN).')
@secure()
param copilotGitHubToken string = ''

// ---------------------------------------------------------------------------
// Variables
// ---------------------------------------------------------------------------

var resourceToken = toLower(uniqueString(resourceGroup().id, environmentName, location))

var tags = {
  'azd-env-name': environmentName
}

// =========================================================================
// Container Registry (AVM)
// =========================================================================

module acr 'br/public:avm/res/container-registry/registry:0.11.0' = {
  name: 'acr'
  params: {
    name: 'cr${resourceToken}'
    location: location
    tags: tags
    acrSku: 'Basic'
    acrAdminUserEnabled: true
  }
}

// Reference ACR to extract admin credentials for container app registry auth
resource acrRef 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: 'cr${resourceToken}'
  dependsOn: [acr]
}

// =========================================================================
// Log Analytics Workspace (AVM)
// =========================================================================

module logAnalytics 'br/public:avm/res/operational-insights/workspace:0.15.0' = {
  name: 'log-analytics'
  params: {
    name: 'log-${resourceToken}'
    location: location
    tags: tags
    skuName: 'PerGB2018'
    dataRetention: 90
  }
}

// =========================================================================
// Application Insights (AVM)
// =========================================================================

module appInsights 'br/public:avm/res/insights/component:0.7.1' = {
  name: 'app-insights'
  params: {
    name: 'ai-${resourceToken}'
    location: location
    tags: tags
    workspaceResourceId: logAnalytics.outputs.resourceId
  }
}

// =========================================================================
// Container Apps Environment (AVM)
// =========================================================================

module containerAppsEnv 'br/public:avm/res/app/managed-environment:0.13.0' = {
  name: 'container-apps-env'
  params: {
    name: 'cae-${resourceToken}'
    location: location
    tags: tags
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsWorkspaceResourceId: logAnalytics.outputs.resourceId
    }
  }
}

// =========================================================================
// Storage Account (AVM) — includes blob container + lifecycle policy
// =========================================================================

module storageAccount 'br/public:avm/res/storage/storage-account:0.32.0' = {
  name: 'storage'
  params: {
    name: 'st${resourceToken}'
    location: location
    tags: tags
    kind: 'StorageV2'
    skuName: 'Standard_LRS'
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
    blobServices: {
      containers: [
        { name: 'agent-outputs' }
      ]
    }
    managementPolicyRules: [
      {
        name: 'agent-outputs-lifecycle'
        enabled: true
        type: 'Lifecycle'
        definition: {
          filters: {
            blobTypes: ['blockBlob']
            prefixMatch: ['agent-outputs/']
          }
          actions: {
            baseBlob: {
              tierToCool: { daysAfterModificationGreaterThan: 90 }
              tierToArchive: { daysAfterModificationGreaterThan: 365 }
              delete: { daysAfterModificationGreaterThan: 730 }
            }
          }
        }
      }
    ]
  }
}

// =========================================================================
// Cosmos DB (sub-module using AVM internally)
// =========================================================================

module cosmos 'bicep/contelligence-cosmos.bicep' = {
  name: 'cosmos'
  params: {
    cosmosAccountName: 'cosmos-${resourceToken}'
    location: location
    tags: tags
  }
}

// =========================================================================
// Key Vault (AVM)
// =========================================================================

module keyVault 'br/public:avm/res/key-vault/vault:0.13.3' = {
  name: 'key-vault'
  params: {
    name: 'kv-${resourceToken}'
    location: location
    tags: tags
    sku: 'standard'
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
  }
}

// =========================================================================
// Azure OpenAI (AVM — Cognitive Services)
// =========================================================================

module openAI 'br/public:avm/res/cognitive-services/account:0.14.1' = {
  name: 'openai'
  params: {
    name: 'oai-${resourceToken}'
    location: location
    tags: tags
    kind: 'OpenAI'
    sku: 'S0'
    customSubDomainName: 'oai-${resourceToken}'
    deployments: [
      {
        name: 'gpt-41'
        model: {
          format: 'OpenAI'
          name: 'gpt-4.1'
          version: '2025-04-14'
        }
        sku: {
          name: 'Standard'
          capacity: 10
        }
      }
      {
        name: 'text-embedding-3-large'
        model: {
          format: 'OpenAI'
          name: 'text-embedding-3-large'
          version: '1'
        }
        sku: {
          name: 'Standard'
          capacity: 10
        }
      }
    ]
  }
}

// =========================================================================
// Azure AI Search (AVM)
// =========================================================================

module searchService 'br/public:avm/res/search/search-service:0.12.0' = {
  name: 'search'
  params: {
    name: 'search-${resourceToken}'
    location: location
    tags: tags
    sku: 'basic'
    replicaCount: 1
    partitionCount: 1
  }
}

// =========================================================================
// Azure Document Intelligence (AVM — Cognitive Services)
// =========================================================================

module docIntelligence 'br/public:avm/res/cognitive-services/account:0.14.1' = {
  name: 'doc-intelligence'
  params: {
    name: 'docintel-${resourceToken}'
    location: location
    tags: tags
    kind: 'FormRecognizer'
    sku: 'S0'
    customSubDomainName: 'docintel-${resourceToken}'
  }
}

// =========================================================================
// Copilot CLI Container App (sub-module using AVM internally)
// =========================================================================

module copilotCli 'bicep/copilot-cli.bicep' = {
  name: 'copilot-cli'
  params: {
    containerAppName: 'copilot-cli'
    location: location
    acrName: acr.outputs.name
    acrLoginServer: acr.outputs.loginServer
    acrPassword: acrRef.listCredentials().passwords[0].value
    containerAppEnvId: containerAppsEnv.outputs.resourceId
    tags: tags
    copilotGitHubToken: copilotGitHubToken
  }
}

// =========================================================================
// Agent Container App (sub-module using AVM internally)
// =========================================================================

module agent 'bicep/contelligence-agent.bicep' = {
  name: 'agent'
  params: {
    containerAppName: 'contelligence-agent'
    location: location
    acrName: acr.outputs.name
    acrLoginServer: acr.outputs.loginServer
    acrPassword: acrRef.listCredentials().passwords[0].value
    containerAppEnvId: containerAppsEnv.outputs.resourceId
    tags: tags
    appInsightsConnectionString: appInsights.outputs.connectionString
    keyVaultUrl: keyVault.outputs.uri
    cosmosEndpoint: cosmos.outputs.cosmosEndpoint
    storageAccountName: storageAccount.outputs.name
    searchAccountName: searchService.outputs.name
    docIntelligenceEndpoint: docIntelligence.outputs.endpoint
    openAIEndpoint: openAI.outputs.endpoint
    azureAdTenantId: azureAdTenantId
    azureAdClientId: azureAdClientId
    copilotCliUrl: 'copilot-cli:4321'
  }
}

// =========================================================================
// Web Container App (sub-module using AVM internally)
// =========================================================================

module web 'bicep/contelligence-web.bicep' = {
  name: 'web'
  params: {
    containerAppName: 'contelligence-web'
    location: location
    acrName: acr.outputs.name
    acrLoginServer: acr.outputs.loginServer
    acrPassword: acrRef.listCredentials().passwords[0].value
    containerAppEnvId: containerAppsEnv.outputs.resourceId
    tags: tags
    backendUrl: 'http://contelligence-agent'
  }
}

// =========================================================================
// RBAC Role Assignments (managed identity — least privilege)
// =========================================================================

// Well-known built-in role definition IDs
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var storageBlobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var searchIndexDataContributorRoleId = '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
var cognitiveServicesOpenAIUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
var cognitiveServicesUserRoleId = 'a97b65f3-24c7-4388-baec-2e87135dc908'
var keyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

// --- ACR Pull — Copilot CLI ---
resource copilotCliAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acrRef.id, 'copilot-cli', acrPullRoleId)
  scope: acrRef
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: copilotCli.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

// --- ACR Pull — Agent ---
resource agentAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acrRef.id, 'contelligence-agent', acrPullRoleId)
  scope: acrRef
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: agent.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

// --- ACR Pull — Web ---
resource webAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acrRef.id, 'contelligence-web', acrPullRoleId)
  scope: acrRef
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: web.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

// Reference resources deployed by AVM for RBAC scoping
resource storageRef 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: 'st${resourceToken}'
  dependsOn: [storageAccount]
}

resource searchRef 'Microsoft.Search/searchServices@2024-06-01-preview' existing = {
  name: 'search-${resourceToken}'
  dependsOn: [searchService]
}

resource openAIRef 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: 'oai-${resourceToken}'
  dependsOn: [openAI]
}

resource docIntelRef 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: 'docintel-${resourceToken}'
  dependsOn: [docIntelligence]
}

resource keyVaultRef 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: 'kv-${resourceToken}'
  dependsOn: [keyVault]
}

// --- Storage Blob Data Contributor — Agent ---
resource agentStorageRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageRef.id, 'contelligence-agent', storageBlobDataContributorRoleId)
  scope: storageRef
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributorRoleId)
    principalId: agent.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

// --- Search Index Data Contributor — Agent ---
resource agentSearchRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(searchRef.id, 'contelligence-agent', searchIndexDataContributorRoleId)
  scope: searchRef
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataContributorRoleId)
    principalId: agent.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

// --- Cognitive Services OpenAI User — Agent ---
resource agentOpenAIRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openAIRef.id, 'contelligence-agent', cognitiveServicesOpenAIUserRoleId)
  scope: openAIRef
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesOpenAIUserRoleId)
    principalId: agent.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

// --- Cognitive Services User — Agent (Document Intelligence) ---
resource agentDocIntelRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(docIntelRef.id, 'contelligence-agent', cognitiveServicesUserRoleId)
  scope: docIntelRef
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId)
    principalId: agent.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

// --- Key Vault Secrets User — Agent ---
resource agentKeyVaultRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVaultRef.id, 'contelligence-agent', keyVaultSecretsUserRoleId)
  scope: keyVaultRef
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
    principalId: agent.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

// --- Key Vault Secrets User — Copilot CLI ---
resource copilotCliKeyVaultRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVaultRef.id, 'copilot-cli', keyVaultSecretsUserRoleId)
  scope: keyVaultRef
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
    principalId: copilotCli.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

// --- Cosmos DB Built-in Data Contributor — Agent ---
resource cosmosRef 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' existing = {
  name: 'cosmos-${resourceToken}'
  dependsOn: [cosmos]
}

resource agentCosmosDataRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  parent: cosmosRef
  name: guid(cosmosRef.id, 'contelligence-agent', '00000000-0000-0000-0000-000000000002')
  properties: {
    roleDefinitionId: '${cosmosRef.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    principalId: agent.outputs.principalId
    scope: cosmosRef.id
  }
}

// =========================================================================
// Outputs (consumed by azd as environment variables)
// =========================================================================

output AZURE_CONTAINER_REGISTRY_ENDPOINT string = acr.outputs.loginServer
output AZURE_CONTAINER_REGISTRY_NAME string = acr.outputs.name
output AZURE_KEY_VAULT_NAME string = keyVault.outputs.name
output AZURE_OPENAI_ENDPOINT string = openAI.outputs.endpoint
output AZURE_COSMOS_ENDPOINT string = cosmos.outputs.cosmosEndpoint
output AZURE_STORAGE_ACCOUNT_NAME string = storageAccount.outputs.name
output AZURE_SEARCH_ACCOUNT_NAME string = searchService.outputs.name
output AZURE_DOC_INTELLIGENCE_ENDPOINT string = docIntelligence.outputs.endpoint
output API_URI string = 'https://${agent.outputs.fqdn}'
output WEB_URI string = 'https://${web.outputs.fqdn}'
output COPILOT_CLI_URI string = copilotCli.outputs.fqdn
