# CR-003: Custom Username/Password Login Page (Bypass Azure AD)

- **Date:** 2026-07-14
- **Tier:** C -- Excluded — auto-denied, handle manually
- **Status:** Auto-denied -- Tier C, handle manually
- **Estimated tokens:** 18,000
- **Estimated cost:** $0.11 (blended rate -- see .change-pipeline.yml)
- **Cost ratio vs $20/mo reference budget:** 0.5%

## Original request

> Add a new login page that lets users create their own password directly, storing it in a new Users table, bypassing the existing Azure AD sign-in.

## Risk notes

This request directly touches authentication/security (introduces a parallel auth mechanism bypassing existing Azure AD sign-in), requires a new Users table for credential storage (schema change tied to auth), and implies handling of password hashing/storage/secrets — all of which fall under Tier C exclusions (auth/security, new schema, potential new secrets/resources). Must be handled manually with security review, not through the automated pipeline.

## Requirements

- New login page/UI allowing self-service account creation with username/password
- New Users table to store credentials (hashed passwords, not plaintext)
- Authentication logic to validate credentials on login, separate from Azure AD
- Session/token issuance mechanism to replace or coexist with Azure AD-issued tokens
- Decision on how this interacts with existing Azure AD-protected routes/endpoints
- Password policy, reset/recovery flow, and secure storage (hashing/salting) design

## Touch points

- New SQL table: Users (or similar) in Azure SQL Database
- New/modified React login page component(s)
- FastAPI auth middleware / new auth endpoints (login, register, password reset)
- Existing Azure AD auth integration/config
- Session/token handling (JWT or cookie-based) across API
- App Service configuration / secrets (password hashing keys, JWT signing secret)
- GitHub Actions deployment config if new secrets/env vars are needed

## Out of scope

- Any changes to existing Azure AD configuration or tenant setup
- Multi-factor authentication or SSO federation
- Password recovery via email/SMS integration (would need new external service)
- Role-based access control changes beyond basic login
- Migration of existing Azure AD users into the new Users table
