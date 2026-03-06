// =============================================================================
// keyvault.bicep — Azure Key Vault for Contelligence secrets
// =============================================================================

@description('Name of the Key Vault')
param keyVaultName string

@description('Azure region for the Key Vault')
param location string = resourceGroup().location

@description('Principal ID to grant Key Vault Secrets User role')
param secretsUserPrincipalId string = ''

@description('Enable RBAC authorization (recommended over access policies)')
param enableRbacAuthorization bool = true

@description('Tags to apply to the Key Vault')
param tags object = {}

// ---------------------------------------------------------------------------
// Key Vault resource
// ---------------------------------------------------------------------------

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: enableRbacAuthorization
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: true
  }
}

// ---------------------------------------------------------------------------
// Secret placeholder — GitHub PAT
// ---------------------------------------------------------------------------
// The actual PAT value is set via CLI:
//   az keyvault secret set --vault-name <name> --name "github-copilot-token" --value <pat>
//
// This is documented here for reference. Secrets with sensitive values should
// never be embedded in Bicep templates.

// ---------------------------------------------------------------------------
// Output
// ---------------------------------------------------------------------------

output keyVaultId string = keyVault.id
output keyVaultUri string = keyVault.properties.vaultUri
output keyVaultName string = keyVault.name
