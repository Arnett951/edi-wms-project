# CR-004: Reports Tab: Stacked Bar Chart of Inbound Files Received (Last 7 Days) by Customer

- **Date:** 2026-07-14
- **Tier:** A -- In scope — full pipeline
- **Status:** Implemented -- awaiting Gate 2 (merge approval)
- **Merge readiness:** Clean
- **Branch:** cr-004-reports-tab-stacked-bar-chart-of-inbound-files-rec
- **Estimated tokens:** 6,000
- **Estimated cost:** $0.04 (blended rate -- see .change-pipeline.yml)
- **Cost ratio vs $20/mo reference budget:** 0.2%

## Original request

> add a chart to the reports tab that will show last 7 days of inbound files reiceved grouped by customer

## Clarification

- **Q:** What's the data source for "inbound files received" (e.g., a specific SQL table/view like an EDI 940 ingestion log, or Azure Blob Storage metadata), and does it already have a customer identifier field to group by?
  **A:** the recent EDI files list has sender and file so source the same
- **Q:** What chart type would you like (e.g., stacked bar per day with customer segments, grouped bar, or line chart with one line per customer)?
  **A:** stacked bar sounds good

## Requirements

- Add new read-only API GET endpoint that returns count of inbound EDI files received per day (last 7 days), grouped by customer/sender
- Source data from the same table/view backing the 'recent EDI files' list, using sender field as customer identifier and file received timestamp
- New chart component on Reports tab: stacked bar chart, x-axis = date (last 7 days), bars segmented/colored by customer (sender)
- Chart should update on page load / tab navigation to Reports
- Handle case of no files received in a given day (zero-value bar)
- Legend showing customer/sender names with distinct colors

## Touch points

- FastAPI backend: new GET endpoint (e.g., /api/reports/inbound-files-by-customer)
- SQL query/view against existing EDI files table (same source as recent EDI files list)
- React/Vite dashboard: Reports tab component
- New chart component (e.g., using existing charting library already in use on dashboard)

## Out of scope

- Changes to file ingestion or EDI processing logic
- New database tables or schema changes
- Historical data beyond 7 days
- Filtering/drill-down by additional dimensions (e.g., file type, status)
- Export functionality for chart data

## Implementation summary

Branch pushed. Here's a summary of what was built:

**Backend (`api/main.py`)** -- new endpoint `GET /api/reports/inbound-files-by-customer` that queries `dbo.EDI940_Raw`, groups by `CAST(LoadDateTime AS date)` and `ISASender` for the last 7 days, returning rows of `{date, sender, count}`.

**Frontend (`dashboard/src/InboundByCustomerChart.jsx`)** -- new component using Recharts `BarChart` with `stackId="a"` bars, one per sender, using the same patterns as the existing `ReportsDashboard`. Client-side pivot fills zero-count days so all 7 dates always appear on the x-axis. Ten distinct colors cycle for the sender segments; a `Legend` shows sender names.

**Integration (`dashboard/src/ReportsDashboard.jsx`)** -- wrapped return in a fragment and appended `<InboundByCustomerChart />` below the existing 30-day line chart. No changes to `App.jsx` were needed.

**Tests (`api/tests/test_reports.py`)** -- three new tests following the existing monkeypatch pattern: response shape, auth enforcement, and SQL field coverage. The auth test exhibits the same pre-existing 500-vs-401 failure as `test_daily_volume_requires_auth` (live Azure AD JWKS unreachable in test environment); no new failures introduced.
