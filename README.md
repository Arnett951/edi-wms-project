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
GET /api/dashboard/summary
GET /api/dashboard/recent-files
GET /api/dashboard/wms-orders
```
