// =============================================================================
// keyvault.bicep — Azure Key Vault for Contelligence secrets (AVM)
// =============================================================================
// Wraps AVM br/public:avm/res/key-vault/vault:0.13.3

@description('Name of the Key Vault')
param keyVaultName string

@description('Azure region for the Key Vault')
param location string = resourceGroup().location

@description('Enable RBAC authorization (recommended over access policies)')
param enableRbacAuthorization bool = true

@description('Tags to apply to the Key Vault')
param tags object = {}

// ---------------------------------------------------------------------------
// Key Vault (AVM)
// ---------------------------------------------------------------------------

module keyVault 'br/public:avm/res/key-vault/vault:0.13.3' = {
  name: '${keyVaultName}-deploy'
  params: {
    name: keyVaultName
    location: location
    tags: tags
    sku: 'standard'
    enableRbacAuthorization: enableRbacAuthorization
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: true
  }
}

// ---------------------------------------------------------------------------
// Output
// ---------------------------------------------------------------------------

output keyVaultId string = keyVault.outputs.resourceId
output keyVaultUri string = keyVault.outputs.uri
output keyVaultName string = keyVault.outputs.name
