// ── Azure Container Apps Environment + 4 Container Apps ──────────────────────

param location string
param baseName string
param acrName string
param imageTag string
param storageConnectionString string
param storageAccountName string
param openAiDeployment string

@secure()
param microsoftAppId string = ''
@secure()
param microsoftAppPassword string = ''
param microsoftAppTenantId string = ''

@secure()
param azureAiProjectEndpoint string = ''
@secure()
param bingProjectConnectionId string = ''
@secure()
param azureOpenAiDalleEndpoint string = ''
@secure()
param azureOpenAiDalleApiKey string = ''
@secure()
param bingSearchApiKey string = ''

// ── Log Analytics Workspace ───────────────────────────────────────────────────
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${baseName}-logs'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// ── ACA Environment ────────────────────────────────────────────────────────────
resource acaEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${baseName}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: listKeys(logAnalytics.id, logAnalytics.apiVersion).primarySharedKey
      }
    }
  }
}

// ── ACR reference ─────────────────────────────────────────────────────────────
resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: acrName
}

// ── Shared environment variables ──────────────────────────────────────────────
var commonEnv = [
  { name: 'AZURE_STORAGE_CONNECTION_STRING', value: storageConnectionString }
  { name: 'AZURE_STORAGE_ACCOUNT_NAME', value: storageAccountName }
  { name: 'BLOB_CONTAINER_TEMPLATES', value: 'templates' }
  { name: 'BLOB_CONTAINER_GENERATED', value: 'generated' }
  { name: 'BLOB_CONTAINER_IMAGES', value: 'images' }
  { name: 'BLOB_CONTAINER_UPLOADS', value: 'uploads' }
]

// ── PPTX MCP Server (external ingress) ───────────────────────────────────────
resource pptxMcpApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${baseName}-pptx-mcp'
  location: location
  properties: {
    environmentId: acaEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
      }
      registries: [{ server: acr.properties.loginServer, identity: 'system' }]
    }
    template: {
      containers: [
        {
          name: 'pptx-mcp-server'
          image: '${acr.properties.loginServer}/pptx-mcp-server:${imageTag}'
          env: commonEnv
          resources: { cpu: json('0.5'), memory: '1Gi' }
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 5 }
    }
  }
  identity: { type: 'SystemAssigned' }
}

// ── Image MCP Server (external ingress) ───────────────────────────────────────
resource imageMcpApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${baseName}-image-mcp'
  location: location
  properties: {
    environmentId: acaEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8001
        transport: 'http'
      }
      registries: [{ server: acr.properties.loginServer, identity: 'system' }]
    }
    template: {
      containers: [
        {
          name: 'image-mcp-server'
          image: '${acr.properties.loginServer}/image-mcp-server:${imageTag}'
          env: union(commonEnv, [
            { name: 'AZURE_OPENAI_DALLE_ENDPOINT', value: azureOpenAiDalleEndpoint }
            { name: 'AZURE_OPENAI_DALLE_API_KEY', value: azureOpenAiDalleApiKey }
            { name: 'AZURE_OPENAI_DALLE_DEPLOYMENT', value: 'dall-e-3' }
            { name: 'BING_SEARCH_API_KEY', value: bingSearchApiKey }
          ])
          resources: { cpu: json('0.5'), memory: '1Gi' }
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 5 }
    }
  }
  identity: { type: 'SystemAssigned' }
}

// ── Orchestrator (internal only) ──────────────────────────────────────────────
resource orchestratorApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${baseName}-orchestrator'
  location: location
  properties: {
    environmentId: acaEnv.id
    configuration: {
      ingress: {
        external: false
        targetPort: 8080
        transport: 'http'
      }
      registries: [{ server: acr.properties.loginServer, identity: 'system' }]
    }
    template: {
      containers: [
        {
          name: 'orchestrator'
          image: '${acr.properties.loginServer}/orchestrator:${imageTag}'
          env: union(commonEnv, [
            { name: 'AZURE_AI_PROJECT_ENDPOINT', value: azureAiProjectEndpoint }
            { name: 'AZURE_OPENAI_DEPLOYMENT', value: openAiDeployment }
            { name: 'BING_PROJECT_CONNECTION_ID', value: bingProjectConnectionId }
            { name: 'PPTX_MCP_SERVER_URL', value: 'https://${pptxMcpApp.properties.configuration.ingress.fqdn}/mcp' }
            { name: 'IMAGE_MCP_SERVER_URL', value: 'https://${imageMcpApp.properties.configuration.ingress.fqdn}/mcp' }
          ])
          resources: { cpu: json('1.0'), memory: '2Gi' }
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
  identity: { type: 'SystemAssigned' }
}

// ── Bot Service (external ingress) ────────────────────────────────────────────
resource botApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${baseName}-bot'
  location: location
  properties: {
    environmentId: acaEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 3978
        transport: 'http'
      }
      registries: [{ server: acr.properties.loginServer, identity: 'system' }]
    }
    template: {
      containers: [
        {
          name: 'bot'
          image: '${acr.properties.loginServer}/bot:${imageTag}'
          env: union(commonEnv, [
            { name: 'MICROSOFT_APP_ID', value: microsoftAppId }
            { name: 'MICROSOFT_APP_PASSWORD', value: microsoftAppPassword }
            { name: 'MICROSOFT_APP_TENANT_ID', value: microsoftAppTenantId }
            { name: 'ORCHESTRATOR_URL', value: 'https://${orchestratorApp.properties.configuration.ingress.fqdn}' }
          ])
          resources: { cpu: json('0.5'), memory: '1Gi' }
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
  identity: { type: 'SystemAssigned' }
}

// ── Outputs ────────────────────────────────────────────────────────────────────
output botUrl string = 'https://${botApp.properties.configuration.ingress.fqdn}'
output pptxMcpUrl string = 'https://${pptxMcpApp.properties.configuration.ingress.fqdn}/mcp'
output imageMcpUrl string = 'https://${imageMcpApp.properties.configuration.ingress.fqdn}/mcp'
output orchestratorInternalUrl string = 'https://${orchestratorApp.properties.configuration.ingress.fqdn}'
output acaEnvironmentId string = acaEnv.id
