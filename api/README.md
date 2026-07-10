# EDI WMS Dashboard API

## Local run

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## Required environment variables

```text
SQL_SERVER=your-server.database.windows.net
SQL_DATABASE=your-database
SQL_USER=your-user
SQL_PASSWORD=your-password
ALLOWED_ORIGINS=http://localhost:5173,https://your-static-web-app.azurestaticapps.net
ANTHROPIC_API_KEY=your-anthropic-api-key   # optional: enables the AI chat fallback
AZURE_AD_TENANT_ID=your-azure-ad-tenant-id
AZURE_AD_CLIENT_ID=your-app-registration-client-id
```

## Auth

Every route except `/health` requires a valid Azure AD access token, sent by the
React dashboard as `Authorization: Bearer <token>` after the user signs in via
MSAL.js. The backend validates the token's signature (against Azure AD's public
JWKS), audience, and issuer - it never sees a password or a shared secret. If
`AZURE_AD_TENANT_ID` / `AZURE_AD_CLIENT_ID` aren't set, protected routes return
`500` rather than silently allowing access.

## Azure App Service startup command

```bash
gunicorn -w 2 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 main:app
```
