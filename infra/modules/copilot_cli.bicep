// ---------------------------------------------------------------------------
// GitHub Copilot CLI — headless server container for Copilot SDK connectivity
// ---------------------------------------------------------------------------
// Runs the Copilot CLI in headless mode as a separate Container App.
// The agent connects to it over TCP using the CLI_URL env var on port 4321.
// Session state is persisted via Azure File Share volume mount.
// ---------------------------------------------------------------------------

@description('Name of the Container App Environment')
param containerAppEnvironmentId string

@description('Azure region for the resource')
param location string = resourceGroup().location

@description('Copilot CLI container image (build from copilot-cli/Dockerfile and push to your ACR)')
param copilotCliImage string

@description('Copilot CLI listen port')
param cliPort int = 4321

@description('CPU allocation')
param cpu string = '0.5'

@description('Memory allocation')
param memory string = '1Gi'

@description('Name of the Azure Storage Account for session-state volume')
param storageAccountName string

@description('Name of the Azure File Share for session-state persistence')
param fileShareName string = 'copilot-session-state'

@description('Storage account access key')
@secure()
param storageAccountKey string

// ---------------------------------------------------------------------------

resource copilotCli 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'copilot-cli'
  location: location
  properties: {
    managedEnvironmentId: containerAppEnvironmentId
    configuration: {
      ingress: {
        external: false
        targetPort: cliPort
        transport: 'tcp'
      }
      secrets: [
        {
          name: 'copilot-github-token'
          value: '' // Populated via Key Vault reference or deployment parameter override
        }
        {
          name: 'storage-account-key'
          value: storageAccountKey
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'copilot-cli'
          image: copilotCliImage
          command: []
          args: [
            '--headless'
            '--port'
            string(cliPort)
          ]
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: [
            {
              name: 'COPILOT_GITHUB_TOKEN'
              secretRef: 'copilot-github-token'
            }
          ]
          volumeMounts: [
            {
              volumeName: 'session-state'
              mountPath: '/root/.copilot/session-state'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              tcpSocket: {
                port: cliPort
              }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              tcpSocket: {
                port: cliPort
              }
              initialDelaySeconds: 5
              periodSeconds: 10
            }
          ]
        }
      ]
      volumes: [
        {
          name: 'session-state'
          storageType: 'AzureFile'
          storageName: 'copilot-session-state-storage'
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Storage link on the Container App Environment
// ---------------------------------------------------------------------------

resource sessionStateStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  name: '${split(containerAppEnvironmentId, '/')[8]}/copilot-session-state-storage'
  properties: {
    azureFile: {
      accountName: storageAccountName
      accountKey: storageAccountKey
      shareName: fileShareName
      accessMode: 'ReadWrite'
    }
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

@description('Internal FQDN of the Copilot CLI server')
output cliFqdn string = copilotCli.properties.configuration.ingress.fqdn

@description('CLI URL for SDK connection (host:port)')
output cliUrl string = '${copilotCli.properties.configuration.ingress.fqdn}:${cliPort}'
