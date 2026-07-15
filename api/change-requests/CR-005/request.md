# CR-005: Customer-Level Field Mapping Configuration Layer (940 Staging -> WMS)

- **Date:** 2026-07-15
- **Tier:** B -- Semi-automated — extra reviewer attention at Gate 1
- **Status:** Pending Gate 1 review
- **Estimated tokens:** 14,000
- **Estimated cost:** $0.08 (blended rate -- see .change-pipeline.yml)
- **Cost ratio vs $20/mo reference budget:** 0.4%

## Original request

> on the 940 sql move to the final WMS tables I want to create a configuration layer by customer to allow the columns from the header detail staging table to be mapped to the WMS schema tabbles. Config can be a simple XML file format and maybe a UI for a user to save the data from Table A to Table B

## Clarification

- **Q:** When you say "create a configuration layer" -- is the scope just the mapping *configuration* (defining/storing which staging columns map to which WMS columns, viewable/editable via UI), or does it also include building the actual execution logic that reads the config and moves/writes the data from the staging table into the final WMS tables?
  **A:** lets do just the build the configuration part. no touching the live Stored procedures that actually push data to the table yet
- **Q:** Should the mapping configuration be persisted as a new SQL table (storing the XML/config per customer) or as XML files in Blob Storage, and is a new table/column considered fine for this build?
  **A:** table storage is fine for this build
- **Q:** For the UI piece, should this be a brand-new dashboard page (e.g. "Field Mapping" under a customer's settings) supporting full CRUD (create/edit/delete/view mappings), or just a read-only view of the current mapping config for now?
  **A:** add a new table "Admin Configs"
- **Q:** Should a single customer's config support mapping to multiple WMS target tables (e.g., separate header/detail mappings), or is this one mapping set (source column -> target column) per customer for now?
  **A:** per customer for now future will choose table or JSON sements

## Risk notes

Requires an additive new SQL table ('Admin Configs') to store per-customer mapping configuration (staging column -> WMS column, stored as XML). No existing tables/columns are modified, no drops/renames, and no production data-mutation logic (execution/apply logic is explicitly out of scope). Flagged Tier B solely due to the new schema object and new write-capable CRUD API endpoints.

## Requirements

- New SQL table 'Admin Configs' to store per-customer field mapping configuration
- Config format: XML document per customer representing staging-column-to-WMS-column mappings
- One mapping set per customer (single target, no multi-table/JSON segment selection yet -- future enhancement)
- New API endpoints: GET (list/view), POST (create), PUT (update), DELETE (remove) mapping configs per customer
- New dashboard UI page for CRUD management of a customer's field mapping (create/edit/delete/view)
- UI should allow selecting staging header/detail columns and mapping them to WMS schema target column names
- No changes to existing stored procedures or the live 940-to-WMS data push logic
- Validation: prevent duplicate/conflicting column mappings within a single customer config (basic form-level validation only)

## Touch points

- Azure SQL Database: new table 'Admin Configs'
- FastAPI: new router/module for mapping config CRUD endpoints
- React/Vite dashboard: new 'Field Mapping' admin page/component
- 940 staging header/detail tables (read-only, for column name reference)
- WMS schema tables (read-only, for target column name reference)

## Out of scope

- Execution logic that applies the mapping to move/transform data from staging to WMS tables
- Modifications to existing stored procedures pushing data to WMS
- Support for multiple target tables or JSON segment mapping per customer (future phase)
- Auth/permission changes for who can edit configs
- Any Azure Data Factory pipeline changes
