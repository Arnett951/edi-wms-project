// Azure Container Apps deployment for the EDI WMS FastAPI backend (api/).
// Scaffold only -- not wired into any GitHub Actions workflow yet, and does
// not replace the existing App Service deployment (deploy-api-appservice.yml).
// Deploy manually to try it out:
//
//   az group create -n edi-wms-containers-rg -l eastus
//   az deployment group create \
//     -g edi-wms-containers-rg \
//     -f infra/main.bicep \
//     -p sqlServer=<your-sql-server> sqlDatabase=<your-db> sqlUser=<user> \
//        sqlPassword=<password> apiKey=<key> anthropicApiKey=<key> \
//        storageConnectionString=<conn-string> allowedOrigins=<https://...>
//
// Then push an image to the created ACR and point the container app at it:
//
//   az acr build -r <acrName> -t edi-wms-api:latest ./api
//   az containerapp update -n edi-wms-api -g edi-wms-containers-rg \
//     --image <acrName>.azurecr.io/edi-wms-api:latest

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Base name used to derive resource names')
param namePrefix string = 'ediwms'

@description('SQL Server hostname (e.g. myserver.database.windows.net)')
param sqlServer string

@description('SQL Database name')
param sqlDatabase string

@description('SQL login username')
param sqlUser string

@secure()
@description('SQL login password')
param sqlPassword string

@secure()
@description('Shared API key required on write endpoints (x-api-key header)')
param apiKey string

@secure()
@description('Anthropic API key for the AI chat fallback (optional -- leave blank to disable)')
param anthropicApiKey string = ''

@secure()
@description('Azure Storage connection string for the inbound blob container')
param storageConnectionString string

@description('Blob container name for inbound EDI files')
param blobContainerName string = 'edi940-inbound'

@description('Comma-separated list of allowed CORS origins for the dashboard')
param allowedOrigins string

@description('Placeholder container image used on first deploy, before a real image has been pushed to the ACR created here')
param placeholderImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

var acrName = toLower('${namePrefix}acr${uniqueString(resourceGroup().id)}')
var logAnalyticsName = '${namePrefix}-logs'
var envName = '${namePrefix}-env'
var containerAppName = '${namePrefix}-api'

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource containerAppEnv 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: envName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: containerAppName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: 'system'
        }
      ]
      secrets: [
        { name: 'sql-password', value: sqlPassword }
        { name: 'api-key', value: apiKey }
        { name: 'anthropic-api-key', value: anthropicApiKey }
        { name: 'storage-connection-string', value: storageConnectionString }
      ]
    }
    template: {
      containers: [
        {
          name: 'edi-wms-api'
          image: placeholderImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'SQL_SERVER', value: sqlServer }
            { name: 'SQL_DATABASE', value: sqlDatabase }
            { name: 'SQL_USER', value: sqlUser }
            { name: 'SQL_PASSWORD', secretRef: 'sql-password' }
            { name: 'API_KEY', secretRef: 'api-key' }
            { name: 'ANTHROPIC_API_KEY', secretRef: 'anthropic-api-key' }
            { name: 'AZURE_STORAGE_CONNECTION_STRING', secretRef: 'storage-connection-string' }
            { name: 'BLOB_CONTAINER_NAME', value: blobContainerName }
            { name: 'ALLOWED_ORIGINS', value: allowedOrigins }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 3
        rules: [
          {
            name: 'http-scale'
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
}

// Lets the container app's managed identity pull from the ACR without
// storing registry credentials as a secret -- same "managed identity + RBAC"
// pattern already used for triggering ADF in api/main.py.
resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, containerApp.id, 'AcrPull')
  scope: acr
  properties: {
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

output containerAppUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output acrLoginServer string = acr.properties.loginServer
