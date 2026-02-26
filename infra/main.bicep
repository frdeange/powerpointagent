// ============================================================
// PowerPoint Agent — Main Bicep deployment
// Deploys: Storage, AI Foundry, ACR, ACA Environment + 4 apps
// ============================================================

targetScope = 'resourceGroup'

@description('Location for all resources')
param location string = 'eastus2'

@description('Base name prefix for all resources')
param baseName string = 'pptxagent'

@description('Azure OpenAI deployment name')
param openAiDeployment string = 'gpt-4o'

@description('Container image tag')
param imageTag string = 'latest'

@description('ACR name')
param acrName string = '${baseName}acr'

// ── Modules ──────────────────────────────────────────────────────────────────

module storage 'modules/storage.bicep' = {
  name: 'storage-deployment'
  params: {
    location: location
    baseName: baseName
  }
}

module acaEnv 'modules/container-apps.bicep' = {
  name: 'aca-deployment'
  params: {
    location: location
    baseName: baseName
    acrName: acrName
    imageTag: imageTag
    storageConnectionString: storage.outputs.connectionString
    storageAccountName: storage.outputs.accountName
    openAiDeployment: openAiDeployment
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────

output botUrl string = acaEnv.outputs.botUrl
output pptxMcpUrl string = acaEnv.outputs.pptxMcpUrl
output imageMcpUrl string = acaEnv.outputs.imageMcpUrl
output storageAccountName string = storage.outputs.accountName
