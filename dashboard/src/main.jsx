import React from 'react';
import { createRoot } from 'react-dom/client';
import { MsalProvider } from '@azure/msal-react';
import { EventType } from '@azure/msal-browser';
import App from './App.jsx';
import './styles.css';
import { msalInstance } from './authConfig.js';

async function bootstrap() {
  await msalInstance.initialize();

  // Explicitly process the auth code Azure AD appended to the URL after a
  // loginRedirect. Resolves to null if there's no redirect response pending
  // (e.g. a normal page load), so this is always safe to call.
  const redirectResult = await msalInstance.handleRedirectPromise();
  const account = redirectResult?.account ?? msalInstance.getAllAccounts()[0];
  if (account) {
    msalInstance.setActiveAccount(account);
  }

  msalInstance.addEventCallback((event) => {
    if (event.eventType === EventType.LOGIN_SUCCESS && event.payload?.account) {
      msalInstance.setActiveAccount(event.payload.account);
    }
  });

  createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <MsalProvider instance={msalInstance}>
        <App />
      </MsalProvider>
    </React.StrictMode>
  );
}

bootstrap().catch((err) => {
  // If bootstrap itself fails, render something instead of leaving a
  // permanently blank page with a silently swallowed error.
  console.error('App failed to start:', err);
  document.getElementById('root').innerHTML =
    '<p style="padding:24px;font-family:sans-serif;">Something went wrong loading the app. Check the browser console for details.</p>';
});
