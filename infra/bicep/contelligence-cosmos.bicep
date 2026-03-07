// ============================================================================
// Contelligence Cosmos DB — Account, Database & Containers (AVM)
// ============================================================================
// Wraps AVM br/public:avm/res/document-db/database-account:0.19.0
// Provisions the Cosmos DB NoSQL account, the `contelligence-agent` database,
// and all containers:
//   - sessions          (pk: /id)
//   - conversation       (pk: /session_id)
//   - outputs            (pk: /session_id)
//   - extraction-cache   (pk: /pk, TTL-enabled)
//   - scheduler-locks    (pk: /id)
//   - agents             (pk: /id)
// ============================================================================

@description('Name of the Cosmos DB account.')
param cosmosAccountName string = 'contelligence-cosmos'

@description('Azure region for the Cosmos DB account.')
param location string = resourceGroup().location

@description('Database name.')
param databaseName string = 'contelligence-agent'

@description('Max autoscale throughput (RU/s) for each container.')
param maxThroughput int = 4000

@description('Tags to apply to the Cosmos DB account.')
param tags object = {}

// =========================================================================
// Cosmos DB Account (AVM)
// =========================================================================

module cosmosAccount 'br/public:avm/res/document-db/database-account:0.19.0' = {
  name: '${cosmosAccountName}-deploy'
  params: {
    name: cosmosAccountName
    location: location
    tags: tags
    defaultConsistencyLevel: 'Session'
    enableAutomaticFailover: false
    sqlDatabases: [
      {
        name: databaseName
        containers: [
          {
            name: 'sessions'
            paths: ['/id']
            kind: 'Hash'
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
            autoscaleSettingsMaxThroughput: maxThroughput
          }
          {
            name: 'conversation'
            paths: ['/session_id']
            kind: 'Hash'
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
            autoscaleSettingsMaxThroughput: maxThroughput
          }
          {
            name: 'outputs'
            paths: ['/session_id']
            kind: 'Hash'
            autoscaleSettingsMaxThroughput: maxThroughput
          }
          {
            name: 'extraction-cache'
            paths: ['/pk']
            kind: 'Hash'
            defaultTtl: 604800
            autoscaleSettingsMaxThroughput: maxThroughput
          }
          {
            name: 'scheduler-locks'
            paths: ['/id']
            kind: 'Hash'
            autoscaleSettingsMaxThroughput: maxThroughput
          }
          {
            name: 'agents'
            paths: ['/id']
            kind: 'Hash'
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
            autoscaleSettingsMaxThroughput: maxThroughput
          }
        ]
      }
    ]
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------
@description('Cosmos DB account document endpoint.')
output cosmosEndpoint string = cosmosAccount.outputs.endpoint

@description('Cosmos DB account name.')
output cosmosAccountName string = cosmosAccount.outputs.name
