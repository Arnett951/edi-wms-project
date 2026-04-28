from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import pyodbc

app = FastAPI(title="EDI WMS Dashboard API")

allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in allowed_origins if origin.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_conn():
    server = os.getenv("SQL_SERVER")
    database = os.getenv("SQL_DATABASE")
    user = os.getenv("SQL_USER")
    password = os.getenv("SQL_PASSWORD")

    missing = [
        name for name, value in {
            "SQL_SERVER": server,
            "SQL_DATABASE": database,
            "SQL_USER": user,
            "SQL_PASSWORD": password,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    return pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password};"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )


def rows(sql: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql)
        columns = [column[0] for column in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/dashboard/summary")
def summary():
    raw = rows("""
        SELECT
            COUNT(*) AS filesReceived,
            SUM(CASE WHEN ProcessStatus = 'PARSED' THEN 1 ELSE 0 END) AS filesParsed,
            SUM(CASE WHEN ProcessStatus = 'PARSE_FAILED' THEN 1 ELSE 0 END) AS filesFailed
        FROM dbo.EDI940_Raw
    """)[0]

    wms = rows("""
        SELECT
            SUM(CASE WHEN IntegrationStatus = 'READY' THEN 1 ELSE 0 END) AS wmsReady,
            SUM(CASE WHEN IntegrationStatus = 'SENT' THEN 1 ELSE 0 END) AS wmsSent,
            SUM(CASE WHEN IntegrationStatus = 'SUCCESS' THEN 1 ELSE 0 END) AS wmsSuccess,
            SUM(CASE WHEN IntegrationStatus = 'FAILED' THEN 1 ELSE 0 END) AS wmsFailed,
            SUM(CASE WHEN IntegrationStatus IN ('SENT','SUCCESS','FAILED') THEN 1 ELSE 0 END) AS wmsPickedUp
        FROM wms.OrderHeader_Staging
    """)[0]

    return {**raw, **wms}


@app.get("/api/dashboard/recent-files")
def recent_files():
    return rows("""
        SELECT TOP 20
            RawId AS rawId,
            FileName AS fileName,
            ProcessStatus AS processStatus,
            CONVERT(varchar(19), LoadDateTime, 120) AS loadDateTime,
            ErrorMessage AS errorMessage
        FROM dbo.EDI940_Raw
        ORDER BY RawId DESC
    """)


@app.get("/api/dashboard/wms-orders")
def wms_orders():
    return rows("""
        SELECT TOP 20
            WMSOrderHeaderStagingId AS wmsOrderHeaderStagingId,
            WarehouseOrderNumber AS warehouseOrderNumber,
            IntegrationStatus AS integrationStatus,
            AttemptCount AS attemptCount,
            ErrorMessage AS errorMessage
        FROM wms.OrderHeader_Staging
        ORDER BY WMSOrderHeaderStagingId DESC
    """)
