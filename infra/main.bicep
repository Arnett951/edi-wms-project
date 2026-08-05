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

@description('Azure AD tenant ID -- validates the bearer tokens MSAL issues to the dashboard. Not a secret (also baked into the dashboard build as VITE_AZURE_AD_TENANT_ID).')
param azureAdTenantId string

@description('Azure AD app registration client ID for this API. Not a secret (also baked into the dashboard build as VITE_AZURE_AD_CLIENT_ID).')
param azureAdClientId string

@secure()
@description('Tailscale reusable+ephemeral auth key for the tailscale sidecar (tskey-auth-...). Leave blank to omit the sidecar entirely.')
param tailscaleAuthKey string = ''

@description('Hostname this container app registers as on the tailnet')
param tailscaleHostname string = 'edi-wms-containerapp'

@description('Base URL (OpenAI-compatible /v1) of the self-hosted local model, reached over the tailscale sidecar. Leave blank to skip the local-model chat tier entirely.')
param localModelBaseUrl string = ''

// The remaining params below mirror app settings the original App Service
// deployment picked up ad hoc over time -- this scaffold predates them, so
// they were missing on first cutover. Kept optional (empty default) so the
// features that read them (os.environ[...] in api/main.py) degrade to a
// clear error on use rather than blocking deploys of this template when a
// value isn't supplied.

@description('Azure subscription ID -- used for ADF pipeline triggers and the Cost Management dashboard card.')
param azureSubscriptionId string = ''

@description('Resource group and factory/pipeline names for the ADF "run pipeline" button.')
param adfResourceGroup string = ''
param adfFactoryName string = ''
param adfPipelineName string = ''

@secure()
@description('Fine-grained GitHub PAT (Actions: write) for the CR gate2/build workflow-dispatch fallback used when this deployment has no local git repo -- which Container Apps never does.')
param githubDispatchToken string = ''

@secure()
@description('Base64-encoded Google service account JSON for the Tableau-refresh Sheets export endpoints.')
param googleServiceAccountJsonBase64 string = ''

@description('Target Google Sheet ID for the Tableau-refresh export endpoints.')
param googleSpreadsheetId string = ''

@secure()
@description('Logic App HTTP trigger URL (includes a SAS signature) for /api/actions/trigger-edi.')
param logicAppTriggerUrl string = ''

var acrName = toLower('${namePrefix}acr${uniqueString(resourceGroup().id)}')
var logAnalyticsName = '${namePrefix}-logs'
var envName = '${namePrefix}-env'
var containerAppName = '${namePrefix}-api'

// Tailscale sidecar: shares this replica's network namespace with the main
// container, so the app reaches the tailnet (and the local vLLM model on it)
// over localhost:1055 (SOCKS5) without needing a TUN device, which Container
// Apps' sandbox doesn't expose. Omitted entirely when tailscaleAuthKey is
// blank -- see AZ App Service sidecar note below for why this lives here and
// not on the App Service deployment.
var tailscaleContainer = {
  name: 'tailscale'
  image: 'docker.io/tailscale/tailscale:latest'
  resources: {
    cpu: json('0.25')
    memory: '0.5Gi'
  }
  env: [
    { name: 'TS_AUTHKEY', secretRef: 'tailscale-authkey' }
    { name: 'TS_HOSTNAME', value: tailscaleHostname }
    // Backed by an Azure Files mount (see volumes below), not container-local
    // /tmp -- /tmp is wiped on every restart, which meant every redeploy
    // re-registered as a brand-new tailnet device (edi-wms-containerapp,
    // -1, -2, ...) instead of resuming the same one. Mounting persistent
    // state here lets it reuse its existing node key across restarts.
    { name: 'TS_STATE_DIR', value: '/tailscale-state' }
    { name: 'TS_SOCKS5_SERVER', value: ':1055' }
    { name: 'TS_USERSPACE', value: 'true' }
    // Container Apps is built on Kubernetes and injects KUBERNETES_SERVICE_HOST
    // into every container, which makes containerboot assume it's running as a
    // k8s pod and try (forever) to read a serviceaccount token ACA doesn't
    // mount -- it never gets past that to actually run `tailscale up`.
    // TS_KUBE_SECRET="" opts back out of the k8s state-store path so it uses
    // TS_STATE_DIR instead. See github.com/tailscale/tailscale/issues/18558.
    { name: 'TS_KUBE_SECRET', value: '' }
  ]
  volumeMounts: [
    {
      volumeName: 'tailscale-state'
      mountPath: '/tailscale-state'
    }
  ]
}

var mainContainer = {
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
    { name: 'AZURE_AD_TENANT_ID', value: azureAdTenantId }
    { name: 'AZURE_AD_CLIENT_ID', value: azureAdClientId }
    { name: 'LOCAL_MODEL_BASE_URL', value: localModelBaseUrl }
    { name: 'LOCAL_MODEL_SOCKS5_PROXY', value: empty(tailscaleAuthKey) ? '' : 'socks5h://localhost:1055' }
    { name: 'AZURE_SUBSCRIPTION_ID', value: azureSubscriptionId }
    { name: 'ADF_RESOURCE_GROUP', value: adfResourceGroup }
    { name: 'ADF_FACTORY_NAME', value: adfFactoryName }
    { name: 'ADF_PIPELINE_NAME', value: adfPipelineName }
    { name: 'GITHUB_DISPATCH_TOKEN', secretRef: 'github-dispatch-token' }
    { name: 'GOOGLE_SERVICE_ACCOUNT_JSON_BASE64', secretRef: 'google-service-account-json' }
    { name: 'GOOGLE_SPREADSHEET_ID', value: googleSpreadsheetId }
    { name: 'LOGIC_APP_TRIGGER_URL', secretRef: 'logic-app-trigger-url' }
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

var containers = empty(tailscaleAuthKey) ? [mainContainer] : [mainContainer, tailscaleContainer]

// Small dedicated file share the tailscale sidecar's state lives on (see
// TS_STATE_DIR above) -- separate from the app's own blob storage account
// (storageConnectionString) since this is infra this template owns and
// tears down on its own lifecycle, not the app's data.
var tailscaleStateStorageAccountName = toLower('${namePrefix}tsst${uniqueString(resourceGroup().id)}')
var tailscaleStateShareName = 'tailscale-state'

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

resource tailscaleStateStorageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = if (!empty(tailscaleAuthKey)) {
  name: tailscaleStateStorageAccountName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

resource tailscaleStateFileService 'Microsoft.Storage/storageAccounts/fileServices@2023-01-01' = if (!empty(tailscaleAuthKey)) {
  parent: tailscaleStateStorageAccount
  name: 'default'
}

resource tailscaleStateFileShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-01-01' = if (!empty(tailscaleAuthKey)) {
  parent: tailscaleStateFileService
  name: tailscaleStateShareName
  properties: {
    shareQuota: 1
  }
}

// Registers the file share as an environment-level storage that any
// container app in this environment can mount by name (see `volumes` below).
resource tailscaleStateEnvStorage 'Microsoft.App/managedEnvironments/storages@2023-05-01' = if (!empty(tailscaleAuthKey)) {
  parent: containerAppEnv
  name: 'tailscale-state'
  properties: {
    azureFile: {
      accountName: tailscaleStateStorageAccountName
      accountKey: !empty(tailscaleAuthKey) ? tailscaleStateStorageAccount.listKeys().keys[0].value : ''
      shareName: tailscaleStateShareName
      accessMode: 'ReadWrite'
    }
  }
}

var volumes = empty(tailscaleAuthKey) ? [] : [
  {
    name: 'tailscale-state'
    storageType: 'AzureFile'
    storageName: tailscaleStateEnvStorage.name
  }
]

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
      // Safe to declare now: acrPullRoleAssignment (below) granted the
      // managed identity AcrPull on a prior deploy of this template. Do NOT
      // add this on a from-scratch deploy before that role assignment
      // exists -- Container Apps validates every declared registry
      // credential on every revision (even ones the current image doesn't
      // use), and 401s here stall the revision until "Operation expired",
      // since the role assignment itself can't be created until this
      // resource (and its identity) already exists.
      registries: [
        {
          server: acr.properties.loginServer
          identity: 'system'
        }
      ]
      secrets: concat([
        { name: 'sql-password', value: sqlPassword }
        { name: 'api-key', value: apiKey }
        { name: 'anthropic-api-key', value: anthropicApiKey }
        { name: 'storage-connection-string', value: storageConnectionString }
        { name: 'github-dispatch-token', value: githubDispatchToken }
        { name: 'google-service-account-json', value: googleServiceAccountJsonBase64 }
        { name: 'logic-app-trigger-url', value: logicAppTriggerUrl }
      ], empty(tailscaleAuthKey) ? [] : [
        { name: 'tailscale-authkey', value: tailscaleAuthKey }
      ])
    }
    template: {
      containers: containers
      volumes: volumes
      // Capped at 1: the tailscale sidecar's state (and node identity) now
      // lives on a shared Azure Files mount, not per-replica local storage --
      // two concurrent replicas would fight over the same tailscaled state
      // and corrupt it. minReplicas stays 0 (scale-to-zero is fine, nothing
      // touches the mount while no replica is running).
      scale: {
        minReplicas: 0
        maxReplicas: empty(tailscaleAuthKey) ? 3 : 1
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

// Mirrors the role the old App Service's identity held -- required for
// /api/dashboard/cloud-cost's DefaultAzureCredential-based call to Azure
// Cost Management. Subscription-scoped (Cost Management is subscription-
// level), which needs its own module since this template deploys at
// resource-group scope -- see modules/cost-management-reader.bicep.
module costManagementReaderAssignment 'modules/cost-management-reader.bicep' = {
  name: 'costManagementReaderAssignment'
  scope: subscription()
  params: {
    principalId: containerApp.identity.principalId
  }
}

output containerAppUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output acrLoginServer string = acr.properties.loginServer
