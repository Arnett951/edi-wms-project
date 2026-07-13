EDI 940 to WMS Integration Platform

End-to-end Azure integration project demonstrating EDI order ingestion, warehouse management system (WMS) integration, operational visibility, chatbot-based order lookup, and data lake reporting.

The solution simulates a common logistics workflow where trading partners transmit EDI 940 Warehouse Shipping Orders that must be validated, transformed, loaded into a WMS, and exposed through operational dashboards and support tools.

Business Scenario

A third-party logistics provider receives EDI 940 orders from customers and must:

Receive and validate inbound EDI transactions
Parse EDI data into relational warehouse tables
Load orders into a WMS staging environment
Track processing status and failures
Archive raw transactions for audit purposes
Expose operational visibility through dashboards
Allow support teams to quickly search orders and transaction history

This project demonstrates a cloud-native implementation of that workflow using Microsoft Azure services.

Solution Architecture
EDI 940 File
      │
      ▼
Azure Data Lake Storage Gen2
      │
      ▼
Azure Data Factory
      │
      ├── Load Raw EDI
      ├── Parse EDI 940
      ├── Load WMS Staging
      ├── Archive Files
      └── Export Analytics Data
      │
      ▼
Azure SQL Database
      │
      ├── Raw EDI Tables
      ├── Parsed EDI Tables
      ├── WMS Staging Tables
      └── Processing Logs
      │
      ▼
FastAPI Backend
      │
      ▼
React Dashboard + Chatbot
Technologies Used
Azure
Azure Managed Identity for service-to-service communication
Azure Data Factory
Azure Data Lake Storage Gen2
Azure SQL Database
Azure Static Web Apps
Azure App Service
Event Grid

Backend
Python
FastAPI
SQL Server / T-SQL

Frontend
React
Vite
JavaScript

Data Integration
ANSI X12 EDI 940
Warehouse Shipping Orders
Staging Architecture
Data Lake Reporting

Key Features
EDI 940 Processing
Inbound EDI file ingestion
Raw transaction retention
Segment-level parsing
Header/detail extraction
Control number validation
WMS Integration
Order header staging
Order detail staging
Integration status tracking
Error logging and monitoring
Operational Dashboard
Files received
Files processed
Processing failures
WMS integration status
Recent transaction activity
Support Chatbot

Users can search operational data using natural language:

Where is PO 12345?
Show order 100234
Lookup ISA 000123456
Give me the failed orders

Regex intent parsing handles the PO/ISA lookup patterns directly against SQL. Anything that doesn't match falls back to Claude (Anthropic), which picks from a fixed set of backend query tools rather than generating SQL itself - so free-form phrasing ("what's failing right now?") is handled without hardcoding a new regex for every way to ask. The AI fallback is optional: without an `ANTHROPIC_API_KEY` configured, the bot still works using the regex path alone.

Capacity Planning

A second dashboard tab, separate from live EDI/WMS operations. A linear regression model (trained offline on 30 days of pick/pack activity, cross-validated R² 0.91) estimates how many orders today's crew can ship, from adjustable inputs:

Packers on shift
Shift length
Receiving hours pulled (reduces packer availability)
Order complexity (avg lines/order)
Today's forecasted order volume

The estimator shows a live projection with an 80% confidence range, a status badge (ON TRACK / TIGHT / AT RISK) comparing that range to the forecast, and a 30-day trend chart (Chart.js) of shipped vs. forecasted orders with today's projection highlighted. This is a self-contained, client-side "what-if" tool - it doesn't call the API, so it works the same whether the FastAPI backend has live data or not.

Data Model
Raw EDI Layer
EDI940_Raw

Stores original inbound EDI transactions.

Parsed EDI Layer
EDI940_Header
EDI940_Detail
EDI940_Address
EDI940_Control

Stores structured EDI business data.

WMS Staging Layer
OrderHeader_Staging
OrderDetail_Staging

Represents data prepared for warehouse execution systems.

API Endpoints
GET  /api/dashboard/summary
GET  /api/dashboard/recent-files
GET  /api/dashboard/wms-orders
POST /api/chat

Example:

{
  "question": "Where is PO 12345?"
}
## Performance / Orchestration Note

Direct SQL execution completed in milliseconds, but end-to-end ADF runs showed higher latency due to orchestration and activity startup overhead. This demo uses low-cost, serverless-style Azure components, so latency was not optimized.

Potential production options:
- Scheduled micro-batching to reduce per-file pipeline overhead
- Azure Functions for event-driven file processing
- Managed VNet Integration Runtime TTL if ADF warm-start behavior is required
- Fewer ADF activities per file

The goal of this project was to demonstrate integration architecture, visibility, and operational support patterns while maintaining low Azure operating costs.

## Security Architecture Note

This project intentionally demonstrates several different Azure identity and access patterns rather than applying one pattern uniformly everywhere. That's a deliberate choice for a portfolio/lab project - the goal is breadth of technique, not internal consistency the way a production system would prioritize it.

- **Entra ID roles (human/admin access)** - Owner at the subscription scope, plus separate, narrower Contributor-tier roles scoped to individual resources (storage accounts, Key Vault). Two layers of admin access control, not one flat grant.
- **Managed identity + Azure RBAC (service-to-service)** - the App Service's system-assigned managed identity holds a "Data Factory Contributor" role scoped to the ADF resource, so triggering pipeline runs (`/api/adf/run`) never touches a credential - `DefaultAzureCredential()` resolves the identity, Azure RBAC decides what it's allowed to do.
- **JWT / OAuth2 (end-user access)** - the web app's own users authenticate via MSAL.js against an Azure AD App Registration; the FastAPI backend validates each request's token (signature via JWKS, audience, issuer) rather than trusting a shared secret. See `api/README.md` and `dashboard/README.md` for details.

**Not yet migrated to the RBAC pattern:** Blob Storage access (`AZURE_STORAGE_CONNECTION_STRING`, an account key) and SQL access (`SQL_USER`/`SQL_PASSWORD`, SQL authentication) still use shared credentials rather than the managed-identity + role-assignment approach used for ADF. This is a known, intentional gap, not an oversight - the identical technique already proven with ADF (managed identity → Azure RBAC role → `DefaultAzureCredential()`) generalizes directly to both: grant the managed identity `Storage Blob Data Reader` for Storage, or an Azure AD SQL login mapped to `db_datareader`/`db_datawriter` for SQL (the SQL server already has Azure AD auth enabled). Left as shared credentials here to spend project time on demonstrating more distinct patterns rather than repeating the same one three times.

Current Features
✓ EDI 940 ingestion
✓ Azure Data Factory orchestration
✓ Azure SQL processing
✓ Data Lake parquet storage
✓ React operational dashboard
✓ FastAPI backend
✓ Azure AD (MSAL.js) sign-in with JWT-validated API access - every backend route except /health requires a token
✓ Audit logging
✓ AI-powered chatbot fallback (Claude tool-calling) for natural language transaction lookup
✓ Capacity Planning tab - linear regression staffing/throughput estimator with a live Chart.js trend view

Testing

Backend (api/) — pytest, with the SQL/Azure calls mocked out so no live database or Azure credentials are needed:

    cd api
    .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
    .venv\Scripts\python.exe -m pytest

Frontend (dashboard/) — vitest + React Testing Library:

    cd dashboard
    npm install
    npm test

Future Enhancements

High Priority
□ User-initiated reprocessing
□ Real-time operational alerts
□ Power BI analytics reporting
□ Multi-transaction EDI support (850/856/945)

Medium Priority
□ Customer-specific mapping configuration
□ Automated exception workflows
□ CI/CD environment promotion (Dev/Test/Prod)

Stretch Goals
□ Root cause analysis recommendations

