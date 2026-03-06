// ============================================================================
// Contelligence Cosmos DB — Account, Database & Containers
// ============================================================================
// Provisions the Cosmos DB NoSQL account, the `contelligence-agent` database,
// and three containers used by Phase 2 Persistent Sessions:
//
//   - sessions      (pk: /id)          — one document per session
//   - conversation  (pk: /session_id)  — conversation turns
//   - outputs       (pk: /session_id)  — output artifacts
//
// Usage:
//   az deployment group create \
//     --resource-group <rg> \
//     --template-file contelligence-cosmos.bicep \
//     --parameters cosmosAccountName=<name>
// ============================================================================

@description('Name of the Cosmos DB account.')
param cosmosAccountName string = 'contelligence-cosmos'

@description('Azure region for the Cosmos DB account.')
param location string = resourceGroup().location

@description('Database name.')
param databaseName string = 'contelligence-agent'

@description('Max autoscale throughput (RU/s) for each container.')
param maxThroughput int = 4000

// ---------------------------------------------------------------------------
// Cosmos DB Account — NoSQL (SQL API), Session consistency
// ---------------------------------------------------------------------------
resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: cosmosAccountName
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    enableFreeTier: false
    enableAutomaticFailover: false
  }
}

// ---------------------------------------------------------------------------
// Database
// ---------------------------------------------------------------------------
resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmosAccount
  name: databaseName
  properties: {
    resource: {
      id: databaseName
    }
  }
}

// ---------------------------------------------------------------------------
// Container: sessions (pk: /id)
// ---------------------------------------------------------------------------
resource sessionsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'sessions'
  properties: {
    resource: {
      id: 'sessions'
      partitionKey: {
        paths: ['/id']
        kind: 'Hash'
      }
      indexingPolicy: {
        automatic: true
        indexingMode: 'consistent'
        includedPaths: [
          { path: '/*' }
        ]
        excludedPaths: [
          { path: '/"_etag"/?' }
        ]
        compositeIndexes: [
          [
            { path: '/status', order: 'ascending' }
            { path: '/created_at', order: 'descending' }
          ]
        ]
      }
    }
    options: {
      autoscaleSettings: {
        maxThroughput: maxThroughput
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Container: conversation (pk: /session_id)
// ---------------------------------------------------------------------------
resource conversationContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'conversation'
  properties: {
    resource: {
      id: 'conversation'
      partitionKey: {
        paths: ['/session_id']
        kind: 'Hash'
      }
      indexingPolicy: {
        automatic: true
        indexingMode: 'consistent'
        includedPaths: [
          { path: '/*' }
        ]
        excludedPaths: [
          { path: '/"_etag"/?' }
        ]
        compositeIndexes: [
          [
            { path: '/session_id', order: 'ascending' }
            { path: '/sequence', order: 'ascending' }
          ]
        ]
      }
    }
    options: {
      autoscaleSettings: {
        maxThroughput: maxThroughput
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Container: outputs (pk: /session_id)
// ---------------------------------------------------------------------------
resource outputsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'outputs'
  properties: {
    resource: {
      id: 'outputs'
      partitionKey: {
        paths: ['/session_id']
        kind: 'Hash'
      }
    }
    options: {
      autoscaleSettings: {
        maxThroughput: maxThroughput
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Phase 4 — Container: extraction-cache (pk: /pk, TTL-enabled)
// ---------------------------------------------------------------------------
resource cacheContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'extraction-cache'
  properties: {
    resource: {
      id: 'extraction-cache'
      partitionKey: {
        paths: ['/pk']
        kind: 'Hash'
      }
      defaultTtl: 604800 // 7 days — individual docs may override
    }
    options: {
      autoscaleSettings: {
        maxThroughput: maxThroughput
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Phase 4 — Container: scheduler-locks (pk: /id)
// ---------------------------------------------------------------------------
resource locksContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'scheduler-locks'
  properties: {
    resource: {
      id: 'scheduler-locks'
      partitionKey: {
        paths: ['/id']
        kind: 'Hash'
      }
    }
    options: {
      autoscaleSettings: {
        maxThroughput: maxThroughput
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Custom Agent Management — Container: agents (pk: /id)
// ---------------------------------------------------------------------------
resource agentsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'agents'
  properties: {
    resource: {
      id: 'agents'
      partitionKey: {
        paths: ['/id']
        kind: 'Hash'
      }
      indexingPolicy: {
        automatic: true
        indexingMode: 'consistent'
        includedPaths: [
          { path: '/status/?' }
          { path: '/source/?' }
          { path: '/tags/[]/?' }
          { path: '/created_at/?' }
          { path: '/display_name/?' }
        ]
        excludedPaths: [
          { path: '/prompt/*' }
          { path: '/"_etag"/?' }
        ]
        compositeIndexes: [
          [
            { path: '/status', order: 'ascending' }
            { path: '/created_at', order: 'descending' }
          ]
          [
            { path: '/source', order: 'ascending' }
            { path: '/display_name', order: 'ascending' }
          ]
        ]
      }
    }
    options: {
      autoscaleSettings: {
        maxThroughput: maxThroughput
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Outputs (Bicep outputs)
// ---------------------------------------------------------------------------
@description('Cosmos DB account document endpoint.')
output cosmosEndpoint string = cosmosAccount.properties.documentEndpoint

@description('Cosmos DB account name.')
output cosmosAccountName string = cosmosAccount.name

@description('Database name.')
output cosmosDatabaseName string = database.name
