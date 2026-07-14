# CR-001: Daily EDI 940 Volume Report (API + Reports Tab Chart)

- **Date:** 2026-07-14
- **Tier:** A -- In scope — full pipeline
- **Status:** Approved (Gate 1) by chris arnett on 2026-07-14 17:00 UTC (local test copy)
- **Estimated tokens:** 6,000
- **Estimated cost:** $0.04 (blended rate -- see .change-pipeline.yml)
- **Cost ratio vs $20/mo reference budget:** 0.2%

## Original request

> Add a read-only GET /api/reports/daily-volume endpoint that returns the count of EDI 940 files received per day for the last 30 days, grouped by date, sourced from the existing dbo.EDI940_Raw table's LoadDateTime column. Display it as a line chart on a new 'Reports' tab in the existing React dashboard, visible to all authenticated users.

## Clarification

- **Q:** Should the chart include days within the last 30 days that had zero EDI 940 files (showing a 0 count), or should only dates with at least one file appear?
  **A:** No further constraints beyond what was already described.

## Requirements

- New read-only GET /api/reports/daily-volume endpoint returning count of EDI 940 files per day for the last 30 days
- Data sourced from existing dbo.EDI940_Raw table, grouped by date derived from LoadDateTime
- Response includes date and count fields for each of the last 30 calendar days
- Dates with no files present in source data should still appear in the response with a count of 0
- New 'Reports' tab added to existing React dashboard navigation
- Reports tab displays a line chart of daily volume using data from the new endpoint
- Reports tab and endpoint accessible only to authenticated users, consistent with existing auth mechanism (no changes to auth logic itself)
- No new database objects (uses existing table directly or via a simple query/view)

## Touch points

- FastAPI backend: new route file/module for /api/reports/daily-volume
- dbo.EDI940_Raw table (read-only query)
- React dashboard: new Reports tab/page component
- React dashboard: navigation/routing config to add Reports tab
- Charting library integration (e.g., existing chart component/library if already in use)
- API client/service layer in React app for calling new endpoint

## Out of scope

- Any changes to authentication or authorization logic
- New database tables, columns, or schema changes
- Historical data beyond 30 days
- Export/download functionality for the report
- Filtering or drill-down by trading partner, file status, or other dimensions
- New Azure resources or infrastructure changes
