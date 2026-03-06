// =============================================================================
// rbac.bicep — RBAC Role Assignments for Contelligence Container App
// =============================================================================
// Assigns all required roles to the Container App's system-assigned managed
// identity following the principle of least privilege.

@description('Principal ID of the Container App system-assigned managed identity')
param principalId string

@description('Resource ID of the Azure Storage account')
param storageAccountId string

@description('Resource ID of the Azure AI Search service')
param searchServiceId string

@description('Resource ID of the Azure Cosmos DB account')
param cosmosAccountId string

@description('Resource ID of the Azure Document Intelligence resource')
param docIntelligenceId string

@description('Resource ID of the Azure OpenAI resource')
param openAIResourceId string

@description('Resource ID of the Azure Key Vault')
param keyVaultId string

// ---------------------------------------------------------------------------
// Well-known Role Definition IDs
// ---------------------------------------------------------------------------

var storageBlobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var searchIndexDataContributorRoleId = '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
var cognitiveServicesUserRoleId = 'a97b65f3-24c7-4388-baec-2e87135dc908'
var cognitiveServicesOpenAIUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
var keyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

// ---------------------------------------------------------------------------
// Storage Blob Data Contributor
// ---------------------------------------------------------------------------

resource storageBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, principalId, storageBlobDataContributorRoleId)
  scope: resourceId('Microsoft.Storage/storageAccounts', last(split(storageAccountId, '/')))
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributorRoleId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------------------------------------------------------------------------
// Search Index Data Contributor
// ---------------------------------------------------------------------------

resource searchIndexRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(searchServiceId, principalId, searchIndexDataContributorRoleId)
  scope: resourceId('Microsoft.Search/searchServices', last(split(searchServiceId, '/')))
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataContributorRoleId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------------------------------------------------------------------------
// Cognitive Services User (Document Intelligence)
// ---------------------------------------------------------------------------

resource docIntelligenceRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(docIntelligenceId, principalId, cognitiveServicesUserRoleId)
  scope: resourceId('Microsoft.CognitiveServices/accounts', last(split(docIntelligenceId, '/')))
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------------------------------------------------------------------------
// Cognitive Services OpenAI User
// ---------------------------------------------------------------------------

resource openAIRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openAIResourceId, principalId, cognitiveServicesOpenAIUserRoleId)
  scope: resourceId('Microsoft.CognitiveServices/accounts', last(split(openAIResourceId, '/')))
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesOpenAIUserRoleId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------------------------------------------------------------------------
// Key Vault Secrets User
// ---------------------------------------------------------------------------

resource keyVaultRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVaultId, principalId, keyVaultSecretsUserRoleId)
  scope: resourceId('Microsoft.KeyVault/vaults', last(split(keyVaultId, '/')))
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}
