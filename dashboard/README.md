# EDI WMS Dashboard

## Local run

```bash
npm install
npm run dev
```

Create `.env` from `.env.example` and set:

```text
VITE_API_BASE=http://localhost:8000
VITE_AZURE_AD_CLIENT_ID=your-app-registration-client-id
VITE_AZURE_AD_TENANT_ID=your-azure-ad-tenant-id
VITE_AZURE_AD_API_SCOPE=api://your-app-registration-client-id/access_as_user
```

## Auth

The dashboard signs users in via MSAL.js against an Azure AD App Registration
(a single registration exposes both the SPA client and the `access_as_user`
API scope). After login, every API call attaches the resulting access token
as a `Bearer` header - see `src/authConfig.js` and `src/apiClient.js`. The
backend validates that token independently (see `api/README.md`); there's no
shared secret between frontend and backend.

## Tests

```bash
npm test
```

## Build

```bash
npm run build
```
