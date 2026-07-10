import { PublicClientApplication } from "@azure/msal-browser";

const clientId = import.meta.env.VITE_AZURE_AD_CLIENT_ID;
const tenantId = import.meta.env.VITE_AZURE_AD_TENANT_ID;
const apiScope = import.meta.env.VITE_AZURE_AD_API_SCOPE;

export const msalConfig = {
  auth: {
    clientId,
    authority: `https://login.microsoftonline.com/${tenantId}`,
    redirectUri: window.location.origin,
  },
  cache: {
    cacheLocation: "sessionStorage",
    storeAuthStateInCookie: false,
  },
};

// The one scope the API accepts - see api://<client-id>/access_as_user
// exposed on the Azure AD App Registration.
export const loginRequest = {
  scopes: [apiScope],
};

export const msalInstance = new PublicClientApplication(msalConfig);
