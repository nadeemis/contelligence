// ============================================================================
// Copilot CLI — Azure Container App (AVM)
// ============================================================================
// Wraps AVM br/public:avm/res/app/container-app:0.20.0.
// Runs the GitHub Copilot CLI in headless mode as an internal service
// within the Container Apps Environment. Accessed by the agent at port 4321.
// ============================================================================

@description('Name of the Container App.')
param containerAppName string = 'copilot-cli'

@description('Azure region for the Container App.')
param location string = resourceGroup().location

@description('Name of the Azure Container Registry.')
param acrName string

@description('ACR login server (e.g. crxxx.azurecr.io).')
param acrLoginServer string

@description('ACR admin password for registry authentication.')
@secure()
param acrPassword string

@description('Container App Environment resource ID.')
param containerAppEnvId string

@description('Tags to apply to the Container App.')
param tags object = {}

@description('Container image (placeholder for initial provisioning).')
param containerImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('GitHub Copilot token (stored in Key Vault, referenced as secret).')
@secure()
param copilotGitHubToken string

// =========================================================================
// Container App (AVM)
// =========================================================================

module copilotCli 'br/public:avm/res/app/container-app:0.20.0' = {
  name: '${containerAppName}-deploy'
  params: {
    name: containerAppName
    location: location
    tags: union(tags, { 'azd-service-name': 'copilot-cli' })
    environmentResourceId: containerAppEnvId
    managedIdentities: {
      systemAssigned: true
    }
    // Internal-only: not exposed externally, only reachable within the CAE
    ingressExternal: false
    ingressTargetPort: 4321
    ingressTransport: 'auto'
    secrets: [
      {
        name: 'registry-password'
        value: acrPassword
      }
      {
        name: 'copilot-github-token'
        value: copilotGitHubToken
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
        name: 'copilot-cli'
        image: containerImage
        resources: {
          cpu: '1'
          memory: '2Gi'
        }
        env: [
          {
            name: 'COPILOT_GITHUB_TOKEN'
            secretRef: 'copilot-github-token'
          }
        ]
        probes: [
          {
            type: 'Startup'
            exec: {
              command: ['copilot', '--version']
            }
            initialDelaySeconds: 15
            periodSeconds: 30
            timeoutSeconds: 10
            failureThreshold: 5
          }
        ]
      }
    ]
    scaleSettings: {
      minReplicas: 1
      maxReplicas: 1
    }
  }
}

// =========================================================================
// Outputs
// =========================================================================

@description('Container App FQDN (internal).')
output fqdn string = copilotCli.outputs.fqdn

@description('Container App name.')
output containerAppName string = copilotCli.outputs.name

@description('Container App managed identity principal ID.')
output principalId string = copilotCli.outputs.systemAssignedMIPrincipalId
