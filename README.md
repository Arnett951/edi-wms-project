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

The chatbot translates requests into SQL queries and returns transaction status information.

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

Current Features
✓ EDI 940 ingestion
✓ Azure Data Factory orchestration
✓ Azure SQL processing
✓ Data Lake parquet storage
✓ React operational dashboard
✓ FastAPI backend
✓ Role-based security
✓ Audit logging

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
□ OpenAI-powered operations assistant
□ Natural language transaction lookup
□ Root cause analysis recommendations

