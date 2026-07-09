from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os
import re
import pyodbc
from fastapi import Header, HTTPException, Depends
import os

app = FastAPI(title="EDI WMS Dashboard API")

API_KEY = os.getenv("API_KEY")

def require_api_key(x_api_key: str = Header(None)):
    if not API_KEY:
        raise HTTPException(
            status_code=500,
            detail="API key not configured"
        )

    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized"
        )

    return True

@app.get("/health")
def health():
    return {"status": "ok"}
    
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

import requests


@app.post("/api/actions/trigger-edi")
def trigger_edi(_: bool = Depends(require_api_key)):
    url = os.getenv("LOGIC_APP_TRIGGER_URL")
    if not url:
        return {"success": False, "error": "LOGIC_APP_TRIGGER_URL not configured"}

    response = requests.post(url, json={})
    return {
        "success": response.ok,
        "status_code": response.status_code,
        "response": response.text[:500]
    }

@app.get("/")
def root():
    return {"status": "EDI WMS API running"}

@app.get("/health")
def health():
    return {"status": "ok"}
import pyodbc

@app.post("/api/wms/simulate-pickup")
def simulate_pickup(_: bool = Depends(require_api_key)):
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute("""
            UPDATE wms.OrderHeader_Staging
            SET
                IntegrationStatus = 'SUCCESS',
                AttemptCount = ISNULL(AttemptCount, 0) + 1,
                ErrorMessage = NULL
            WHERE IntegrationStatus = 'READY'
        """)

        updated = cur.rowcount
        conn.commit()

    return {
        "success": True,
        "pickedUp": updated,
        "message": f"Simulated WMS pickup for {updated} staged order(s)."
    }
    
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://brave-beach-07b122d1e.7.azurestaticapps.net",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/api/debug/logic-url")
def debug_logic():
    return {"url_set": bool(os.getenv("LOGIC_APP_TRIGGER_URL"))}

@app.get("/api/test-env")
def test_env():
    return {
        "api_key_loaded": bool(os.getenv("API_KEY"))
    }

def escape_odbc(value):
    value = (value or "").strip()
    return "{" + value.replace("}", "}}") + "}"

def get_conn():
    server = (os.getenv("SQL_SERVER") or "").strip()
    database = (os.getenv("SQL_DATABASE") or "").strip()
    user = (os.getenv("SQL_USER") or "").strip()
    password_raw = os.getenv("SQL_PASSWORD")

    missing = [
        name for name, value in {
            "SQL_SERVER": server,
            "SQL_DATABASE": database,
            "SQL_USER": user,
            "SQL_PASSWORD": password_raw,
        }.items()
        if not value
    ]

    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    password = escape_odbc(password_raw)

    return pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER=tcp:{server},1433;"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password};"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
        "Connection Timeout=30;"
    )


def rows(sql: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql)
        columns = [column[0] for column in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def rows_params(sql: str, params: tuple):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        columns = [column[0] for column in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/dashboard/summary")
def dashboard_summary():
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


# ---------------------------------------------------------------------------
# Phase 1 chat: rule-based lookups for "where is PO X" / "what happened with
# ISA X" style questions. ISA control numbers aren't parsed into a column
# yet, so they're pulled out of EDI940_Raw.RawContent on the fly.
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    question: str


PO_PATTERN = re.compile(
    r"\b(?:po|p\.o\.|purchase\s+order|order|warehouse\s+order)\b[\s#:\-]*([a-z0-9\-]+)",
    re.IGNORECASE
)

ISA_PATTERN = re.compile(
    r"\b(?:isa|isa\s+number|control\s+number|interchange|interchange\s+control\s+number)\b[\s#:\-]*([0-9]{1,9})",
    re.IGNORECASE
)

WMS_STATUS_TEXT = {
    "READY": "parsed and waiting to be sent to WMS",
    "SENT": "sent to WMS and awaiting confirmation",
    "SUCCESS": "successfully picked up by WMS",
}


def extract_isa_control_number(raw_content: Optional[str]) -> Optional[str]:
    if not raw_content:
        return None
    for segment in raw_content.replace("\n", "").replace("\r", "").split("~"):
        parts = segment.strip().split("*")
        if parts and parts[0].strip().upper() == "ISA" and len(parts) > 13:
            return parts[13].strip()
    return None


def describe_file_status(file_row: dict) -> str:
    status = file_row.get("processStatus")
    loaded = file_row.get("loadDateTime") or "an unknown time"
    if status == "PARSED":
        return f"File {file_row['fileName']} (ISA {file_row.get('isaControlNumber')}) was received and parsed successfully at {loaded}."
    if status == "PARSE_FAILED":
        error = file_row.get("errorMessage") or "no error message was recorded"
        return f"File {file_row['fileName']} (ISA {file_row.get('isaControlNumber')}) was received at {loaded} but failed to parse: {error}"
    return f"File {file_row['fileName']} (ISA {file_row.get('isaControlNumber')}) was received at {loaded}. Current status: {status or 'UNKNOWN'}."


def handle_isa_lookup(isa_number: str) -> dict:
    candidates = rows_params(
        """
        SELECT TOP 50
            RawId AS rawId,
            FileName AS fileName,
            ProcessStatus AS processStatus,
            CONVERT(varchar(19), LoadDateTime, 120) AS loadDateTime,
            ErrorMessage AS errorMessage,
            RawEDIText AS rawContent
        FROM dbo.EDI940_Raw
        WHERE RawEDIText LIKE ?
        ORDER BY RawId DESC
        """,
        (f"%{isa_number}%",),
    )

    target = isa_number.lstrip("0") or "0"
    match = None
    for row in candidates:
        control_number = extract_isa_control_number(row.get("rawContent"))
        if control_number and control_number.lstrip("0") == target:
            match = row
            match["isaControlNumber"] = control_number
            break

    if not match:
        return {
            "intent": "isa_lookup",
            "reply": f"I couldn't find any file with ISA control number {isa_number}.",
            "matches": [],
        }

    match.pop("rawContent", None)
    return {"intent": "isa_lookup", "reply": describe_file_status(match), "matches": [match]}


def handle_po_lookup(po_number: str) -> dict:
    wms_rows = rows_params(
        """
        SELECT TOP 5
            WMSOrderHeaderStagingId AS wmsOrderHeaderStagingId,
            WarehouseOrderNumber AS warehouseOrderNumber,
            IntegrationStatus AS integrationStatus,
            AttemptCount AS attemptCount,
            ErrorMessage AS errorMessage
        FROM wms.OrderHeader_Staging
        WHERE WarehouseOrderNumber = ?
        """,
        (po_number,),
    )

    if not wms_rows:
        return {
            "intent": "po_lookup",
            "reply": f"I couldn't find PO/order {po_number} in the WMS staging queue yet. It may not have been received or parsed.",
            "matches": [],
        }

    wms_row = wms_rows[0]
    status = wms_row["integrationStatus"]
    if status == "FAILED":
        status_text = f"picked up by WMS but failed: {wms_row.get('errorMessage') or 'no error message recorded'}"
    else:
        status_text = WMS_STATUS_TEXT.get(status, f"in status {status or 'UNKNOWN'}")

    reply = f"PO/order {wms_row['warehouseOrderNumber']} is {status_text} (attempts: {wms_row.get('attemptCount') or 0})."
    return {"intent": "po_lookup", "reply": reply, "matches": wms_rows}


@app.post("/api/chat")
def chat(request: ChatRequest):
    question = request.question or ""

    isa_match = ISA_PATTERN.search(question)
    if isa_match:
        return handle_isa_lookup(isa_match.group(1).strip())

    po_match = PO_PATTERN.search(question)
    if po_match:
        return handle_po_lookup(po_match.group(1).strip())

    return {
        "intent": "unknown",
        "reply": (
            "I can look up a PO/order number (e.g. \"where is PO 12345\") or an ISA "
            "control number (e.g. \"what happened with ISA 000012345\"). Try rephrasing your question."
        ),
        "matches": [],
    }
