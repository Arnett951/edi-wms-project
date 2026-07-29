# infra/

Bicep scaffold for running the FastAPI backend (`api/`) on **Azure Container
Apps** instead of Azure App Service.

This is a parallel, opt-in path. It does not touch or replace the existing
App Service deployment (`.github/workflows/deploy-api-appservice.yml`) --
that keeps working exactly as it does today. Nothing here is wired into CI
yet.

## What it creates

- Azure Container Registry (Basic SKU, admin user disabled)
- Log Analytics workspace
- Container Apps managed environment
- The container app itself (`edi-wms-api`), system-assigned managed identity,
  scale-to-zero (0-3 replicas on HTTP concurrency)

The container app's managed identity is granted `AcrPull` on the registry --
same "managed identity + Azure RBAC" pattern already used for triggering ADF
in `api/main.py`, rather than storing registry credentials as a secret.

## Deploy

```bash
az group create -n edi-wms-containers-rg -l eastus

az deployment group create \
  -g edi-wms-containers-rg \
  -f infra/main.bicep \
  -p sqlServer=<your-sql-server>.database.windows.net \
     sqlDatabase=<your-db> \
     sqlUser=<user> \
     sqlPassword=<password> \
     apiKey=<key> \
     anthropicApiKey=<key> \
     storageConnectionString=<conn-string> \
     allowedOrigins=https://<your-static-web-app>.azurestaticapps.net
```

The container app deploys first with a Microsoft placeholder image (it needs
*something* running before the ACR has a real image in it). Build and push
the real image, then point the app at it:

```bash
az acr build -r <acrName from deployment output> -t edi-wms-api:latest ./api
az containerapp update -n edi-wms-api -g edi-wms-containers-rg \
  --image <acrName>.azurecr.io/edi-wms-api:latest
```

## Not done yet (future work, not part of this scaffold)

- No GitHub Actions workflow builds/pushes the image automatically
- `SQL_PASSWORD` / storage connection string are still plain secrets, not
  migrated to managed identity (same known gap as the App Service version,
  see root `README.md`)
- No VNet integration / private endpoints
