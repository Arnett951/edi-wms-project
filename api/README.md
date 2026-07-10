# EDI WMS Dashboard API

## Local run

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## Required environment variables

```text
SQL_SERVER=your-server.database.windows.net
SQL_DATABASE=your-database
SQL_USER=your-user
SQL_PASSWORD=your-password
ALLOWED_ORIGINS=http://localhost:5173,https://your-static-web-app.azurestaticapps.net
ANTHROPIC_API_KEY=your-anthropic-api-key   # optional: enables the AI chat fallback
```

## Azure App Service startup command

```bash
gunicorn -w 2 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 main:app
```
