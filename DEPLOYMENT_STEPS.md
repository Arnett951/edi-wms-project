# Azure Deployment Steps

## 1. Push this repo to GitHub

```bash
git init
git add .
git commit -m "Initial EDI WMS dashboard project"
git branch -M main
git remote add origin https://github.com/YOUR-USER/edi-wms-project.git
git push -u origin main
```

## 2. Azure App Service for FastAPI

Create a Linux Web App with Python 3.11 or 3.12.

Set App Service configuration values:

```text
SQL_SERVER=your-server.database.windows.net
SQL_DATABASE=free-sql-db-5402162
SQL_USER=azureadmin
SQL_PASSWORD=your-password
ALLOWED_ORIGINS=https://your-static-web-app.azurestaticapps.net,http://localhost:5173
```

Startup command:

```bash
gunicorn -w 2 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 main:app
```

Test:

```text
https://your-api-app.azurewebsites.net/health
https://your-api-app.azurewebsites.net/api/dashboard/summary
```

## 3. GitHub secrets for API deploy

In GitHub repo settings, add:

```text
AZURE_API_APP_NAME=your-api-app-name
AZURE_API_PUBLISH_PROFILE=<downloaded publish profile XML from App Service>
```

## 4. Azure Static Web App for React

Create Static Web App connected to this GitHub repo.

Build settings:

```text
App location: dashboard
API location: blank
Output location: dist
```

Set GitHub secret:

```text
VITE_API_BASE=https://your-api-app.azurewebsites.net
```

Static Web Apps will also create a deployment token secret automatically. If using the included workflow manually, add:

```text
AZURE_STATIC_WEB_APPS_API_TOKEN=<deployment token>
```

## 5. CORS

After Static Web App is created, copy its URL and add it to the API App Service setting:

```text
ALLOWED_ORIGINS=https://your-static-web-app.azurestaticapps.net,http://localhost:5173
```

Restart App Service.
