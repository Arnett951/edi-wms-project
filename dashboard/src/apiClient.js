import { InteractionRequiredAuthError } from "@azure/msal-browser";
import { msalInstance, loginRequest } from "./authConfig.js";

export async function getAccessToken() {
  const account = msalInstance.getActiveAccount() || msalInstance.getAllAccounts()[0];
  if (!account) {
    throw new Error("Not signed in");
  }

  try {
    const result = await msalInstance.acquireTokenSilent({ ...loginRequest, account });
    return result.accessToken;
  } catch (err) {
    if (err instanceof InteractionRequiredAuthError) {
      // Silent refresh needs interaction (e.g. expired session) - redirect
      // to sign in again. The caller's request won't complete this time
      // around; it'll succeed after the user is redirected back.
      await msalInstance.acquireTokenRedirect(loginRequest);
      return null;
    }
    throw err;
  }
}

// Drop-in replacement for fetch() that attaches the signed-in user's Azure AD
// access token as a Bearer header, so the FastAPI backend can validate it.
export async function authFetch(url, options = {}) {
  const token = await getAccessToken();
  return fetch(url, {
    ...options,
    headers: {
      ...(options.headers || {}),
      Authorization: `Bearer ${token}`,
    },
  });
}
