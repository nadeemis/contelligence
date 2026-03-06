// ============================================================================
// Contelligence Storage — Blob Lifecycle Management Policy
// ============================================================================
// Adds a lifecycle management policy to the existing storage account that
// tiers the `agent-outputs` blob container to optimise costs:
//
//   - Hot  → Cool    after 90 days
//   - Cool → Archive after 365 days
//   - Delete          after 730 days (Phase 4)
//
// Usage:
//   az deployment group create \
//     --resource-group <rg> \
//     --template-file contelligence-storage.bicep \
//     --parameters storageAccountName=<name>
// ============================================================================

@description('Name of the existing storage account.')
param storageAccountName string

@description('Azure region (must match the existing storage account).')
param location string = resourceGroup().location

// Reference the existing storage account
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

// ---------------------------------------------------------------------------
// Lifecycle Management Policy
// ---------------------------------------------------------------------------
resource lifecyclePolicy 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    policy: {
      rules: [
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
                tierToCool: {
                  daysAfterModificationGreaterThan: 90
                }
                tierToArchive: {
                  daysAfterModificationGreaterThan: 365
                }
                delete: {
                  daysAfterModificationGreaterThan: 730
                }
              }
            }
          }
        }
      ]
    }
  }
}
