# EDI 940 to WMS Dashboard Project

Portfolio project showing an EDI 940 pipeline with Azure SQL-backed dashboard visibility.

## Structure

```text
api/        FastAPI backend for dashboard APIs
dashboard/  React/Vite dashboard frontend
.github/    Example GitHub Actions workflows
```

## Local quick start

Terminal 1:

```bash
cd api
pip install -r requirements.txt
uvicorn main:app --reload
```

Terminal 2:

```bash
cd dashboard
npm install
npm run dev
```

## Dashboard APIs

```text
GET  /api/dashboard/summary
GET  /api/dashboard/recent-files
GET  /api/dashboard/wms-orders
POST /api/chat            body: { "question": "Where is PO 12345?" }
```

## Chatbot (phase 1)

Rule-based, no LLM: regex intent parsing on `POST /api/chat` recognizes
"PO/order <number>" and "ISA <number>" questions.

- PO/order lookups query `wms.OrderHeader_Staging.WarehouseOrderNumber` directly.
- ISA lookups scan `dbo.EDI940_Raw.RawContent` (pre-filtered with `LIKE`, then
  parsed segment-by-segment) since ISA control numbers aren't stored in a
  dedicated column yet.

Anything else returns a fallback message describing what it can answer.
