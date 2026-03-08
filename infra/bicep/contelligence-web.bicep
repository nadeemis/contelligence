// ============================================================================
// Contelligence Web — Azure Container App (AVM)
// ============================================================================
// Wraps AVM br/public:avm/res/app/container-app:0.20.0.
// Serves the React SPA via nginx and reverse-proxies /api/ calls to the
// agent Container App within the same Container Apps Environment.
// ============================================================================

@description('Name of the Container App.')
param containerAppName string = 'contelligence-web'

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

@description('Backend API URL for nginx reverse proxy (internal Container App URL).')
param backendUrl string = 'http://contelligence-agent'

// =========================================================================
// Container App (AVM)
// =========================================================================

module webApp 'br/public:avm/res/app/container-app:0.20.0' = {
  name: '${containerAppName}-deploy'
  params: {
    name: containerAppName
    location: location
    tags: union(tags, { 'azd-service-name': 'web' })
    environmentResourceId: containerAppEnvId
    managedIdentities: {
      systemAssigned: true
    }
    ingressExternal: true
    ingressTargetPort: 80
    ingressTransport: 'auto'
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
        name: 'web'
        image: containerImage
        resources: {
          cpu: '0.5'
          memory: '1Gi'
        }
        env: [
          { name: 'BACKEND_URL', value: backendUrl }
        ]
      }
    ]
    scaleSettings: {
      minReplicas: 1
      maxReplicas: 5
      rules: [
        {
          name: 'http-scaling'
          http: {
            metadata: {
              concurrentRequests: '50'
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
output fqdn string = webApp.outputs.fqdn

@description('Container App name.')
output containerAppName string = webApp.outputs.name

@description('Container App managed identity principal ID.')
output principalId string = webApp.outputs.systemAssignedMIPrincipalId
