# Resume Bullets / Interview Talking Points

## Project title
EDI 940 Warehouse Order Integration Pipeline with WMS Dashboard

## Resume bullets

- Built an end-to-end EDI X12 940 ingestion pipeline using Azure Data Factory, Azure SQL, FastAPI, and React to process warehouse order files from inbound storage through WMS staging.
- Designed SQL raw, parsed, and WMS staging tables to support full auditability from physical EDI file receipt through READY, SENT, SUCCESS, and FAILED integration statuses.
- Developed parser logic to split X12 940 files into ST/SE transaction loops, normalize header/detail/address/control segments, and prepare order data for downstream WMS consumption.
- Created FastAPI dashboard endpoints exposing file receipt counts, parser errors, WMS queue status, retry attempts, and recent order activity from Azure SQL.
- Built a React/Vite operational dashboard showing EDI files received, parsed transactions, error visibility, and WMS pickup lifecycle metrics.
- Implemented portfolio-ready deployment architecture using Azure App Service for APIs and Azure Static Web Apps for the React dashboard.
- Added an AI fallback to the chatbot using Claude's tool-calling API: free-form questions the regex parser doesn't recognize (e.g. "give me the failed orders") are routed to Claude, which selects from a fixed set of backend query tools rather than generating SQL directly, keeping the LLM sandboxed while extending the bot beyond hardcoded intents.
- Replaced a broken shared-secret API key with real Azure AD authentication: registered an Azure AD app exposing an OAuth2 scope, wired MSAL.js into the React SPA for sign-in and token acquisition, and added FastAPI middleware that validates each request's JWT (signature, audience, issuer) against Azure AD's public JWKS - no shared secret between frontend and backend, and every route except the health check requires a verified token.

## Interview explanation

“I built a full-stack EDI 940 to WMS integration lab that mirrors common warehouse integration patterns. The flow starts with ADF loading inbound EDI files into SQL as raw audit records, then a parser splits each file into ST/SE transaction sets and loads normalized order header/detail records. From there, the orders move into WMS staging tables with READY, SENT, SUCCESS, and FAILED statuses. I added FastAPI endpoints and a React dashboard so operations can see files received, parser failures, and WMS pickup status.”

## Skills demonstrated

- EDI X12 940 concepts
- Azure Data Factory pipeline design
- Azure SQL staging and stored procedures
- WMS integration lifecycle tracking
- FastAPI backend API development
- React/Vite dashboard development
- Azure App Service and Static Web Apps deployment
- Integration logging, retry visibility, and operational dashboards
- LLM tool-calling integration (Anthropic Claude API) with sandboxed backend tools
- OAuth2/OIDC authentication with Azure AD, MSAL.js, and JWT validation via JWKS
