from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
import json
import os
import re
import time
import jwt
from jwt import PyJWKClient
import pyodbc
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
from datetime import datetime, timezone
import requests
from azure.identity import DefaultAzureCredential
from azure.mgmt.datafactory import DataFactoryManagementClient
from anthropic import Anthropic

# Explicit path (relative to this file, not the process's working directory) -
# load_dotenv()'s default search depends on cwd, which is unreliable across
# different ways of launching this app (uvicorn --app-dir, gunicorn, etc.).
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

app = FastAPI(title="EDI WMS Dashboard API")

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,https://brave-beach-07b122d1e.7.azurestaticapps.net"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Auth: validate Azure AD-issued JWTs (v2.0 access tokens) sent as
# `Authorization: Bearer <token>` by the React app after an MSAL login.
# The backend never sees a password or a shared secret - it just verifies
# the token's signature (against Azure AD's public JWKS), audience, and
# issuer. Applied to every route below except /health, which Azure's own
# monitoring probes need to reach unauthenticated.
# ---------------------------------------------------------------------------

AZURE_AD_TENANT_ID = os.getenv("AZURE_AD_TENANT_ID")
AZURE_AD_CLIENT_ID = os.getenv("AZURE_AD_CLIENT_ID")

_jwks_client = (
    PyJWKClient(f"https://login.microsoftonline.com/{AZURE_AD_TENANT_ID}/discovery/v2.0/keys")
    if AZURE_AD_TENANT_ID
    else None
)

_bearer_scheme = HTTPBearer(auto_error=False)


def require_auth(credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme)):
    if not AZURE_AD_TENANT_ID or not AZURE_AD_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Azure AD auth is not configured")

    if not credentials:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(credentials.credentials)
        payload = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["RS256"],
            audience=AZURE_AD_CLIENT_ID,
            issuer=f"https://login.microsoftonline.com/{AZURE_AD_TENANT_ID}/v2.0",
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return payload


# To check Health of the API
@app.get("/health")
def health():
    return {"status": "ok"}


# To trigger the Logic App for EDI processing
@app.post("/api/actions/trigger-edi")
def trigger_edi(_: dict = Depends(require_auth)):
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
def root(_: dict = Depends(require_auth)):
    return {"status": "EDI WMS API running"}

# To simulate WMS pickup for testing purposes on DB
@app.post("/api/wms/simulate-pickup")
def simulate_pickup(_: dict = Depends(require_auth)):
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
    

@app.get("/api/debug/logic-url")
def debug_logic(_: dict = Depends(require_auth)):
    return {"url_set": bool(os.getenv("LOGIC_APP_TRIGGER_URL"))}

#To check whether Azure AD auth env vars are loaded, for debugging deployment config
@app.get("/api/test-env")
def test_env(_: dict = Depends(require_auth)):
    return {
        "azure_ad_configured": bool(AZURE_AD_TENANT_ID and AZURE_AD_CLIENT_ID)
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
#helper to get latest failed ISA control number for chat suggestions
def get_latest_failed_isa():
    result = rows("""
        SELECT TOP 1
            ISA_ControlNumber AS isaControlNumber
        FROM dbo.EDI940_Raw
        WHERE ProcessStatus LIKE '%FAIL%'
        ORDER BY RawId DESC
    """)

    if result:
        return result[0].get("isaControlNumber")

    return None
#helper to get Blob metrics
def get_blob_queue_metrics():
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")

    blob_service = BlobServiceClient.from_connection_string(conn_str)

    container = blob_service.get_container_client("edi940-inbound")

    blobs = list(container.list_blobs())

    if not blobs:
        return {
            "filesWaiting": 0,
            "oldestFileAgeSeconds": 0
        }

    oldest_blob = min(blobs, key=lambda b: b.last_modified)

    age_seconds = int(
        (
            datetime.now(timezone.utc)
            - oldest_blob.last_modified
        ).total_seconds()
    )

    return {
        "filesWaiting": len(blobs),
        "oldestFileAgeSeconds": age_seconds
    }
#To display the summary of the dashboard including files received, parsed, failed and WMS status
@app.get("/api/dashboard/summary")
def dashboard_summary(_: dict = Depends(require_auth)):
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

    try:
        blob_metrics = get_blob_queue_metrics()
    except Exception as e:
        blob_metrics = {
            "filesWaiting": 0,
            "oldestFileAgeSeconds": 0,
            "blobStatusError": str(e)
        }
    return {
        **raw,
        **wms,
        **blob_metrics
    }

#To display the recent files received in the dashboard
@app.get("/api/dashboard/recent-files")
def recent_files(_: dict = Depends(require_auth)):
    return rows("""
        SELECT TOP 20
            RawId AS rawId,
            ISA_ControlNumber AS isaControlNumber,
            ISASender AS isaSender,
            FileName AS fileName,
            ProcessStatus AS processStatus,
            CONVERT(varchar(19), LoadDateTime, 120) AS loadDateTime,
            ErrorMessage AS errorMessage
        FROM dbo.EDI940_Raw
        ORDER BY RawId DESC
    """)

#To check the status of the blob storage including files waiting and oldest file age in seconds
@app.get("/api/dashboard/blob-status")
def blob_status(_: dict = Depends(require_auth)):
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    container_name = os.getenv("BLOB_CONTAINER_NAME", "edi940-inbound")

    if not conn_str:
        raise HTTPException(status_code=500, detail="AZURE_STORAGE_CONNECTION_STRING is not set")

    blob_service = BlobServiceClient.from_connection_string(conn_str)
    container = blob_service.get_container_client(container_name)

    blobs = list(container.list_blobs())

    now = datetime.now(timezone.utc)
    files_waiting = len(blobs)

    oldest_age_seconds = 0
    if blobs:
        oldest_blob = min(blobs, key=lambda b: b.creation_time or b.last_modified)
        blob_time = oldest_blob.creation_time or oldest_blob.last_modified
        oldest_age_seconds = int((now - blob_time).total_seconds())

    return {
        "filesWaiting": files_waiting,
        "oldestAgeSeconds": oldest_age_seconds
    }

#To display the recent WMS orders in the dashboard including their status and error messages if any
@app.get("/api/dashboard/wms-orders")
def wms_orders(_: dict = Depends(require_auth)):
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

#top allow remote start of ADF Pipeline for testing purposes
@app.post("/api/adf/run")
def run_adf_pipeline(_: dict = Depends(require_auth)):
    try:
        credential = DefaultAzureCredential()
        client = DataFactoryManagementClient(
            credential,
            os.environ["AZURE_SUBSCRIPTION_ID"],
        )

        run_response = client.pipelines.create_run(
            resource_group_name=os.environ["ADF_RESOURCE_GROUP"],
            factory_name=os.environ["ADF_FACTORY_NAME"],
            pipeline_name=os.environ["ADF_PIPELINE_NAME"],
        )

        return {
            "success": True,
            "message": "ADF pipeline started.",
            "runId": run_response.run_id,
        }
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to start the ADF pipeline.",
        )

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


def handle_failed_orders() -> dict:
    failed_rows = rows("""
        SELECT TOP 20
            FileName AS fileName,
            ProcessStatus AS processStatus,
            ErrorMessage AS errorMessage
        FROM dbo.EDI940_Raw
        WHERE ProcessStatus = 'PARSE_FAILED'
        ORDER BY RawId DESC
    """)

    if not failed_rows:
        return {"intent": "failed_orders", "reply": "No failed files in the EDI intake right now.", "matches": []}

    lines = [
        f"- {r['fileName']}: {r.get('errorMessage') or 'no error message recorded'}"
        for r in failed_rows
    ]
    reply = f"There are {len(failed_rows)} failed file(s):\n" + "\n".join(lines)
    return {"intent": "failed_orders", "reply": reply, "matches": failed_rows}


def build_unknown_reply() -> str:
    latest_failed = get_latest_failed_isa()
    example_isa = latest_failed or "000012345"
    return f'Try asking "Why did ISA {example_isa} fail?" or "Where is PO 12345?"'


# ---------------------------------------------------------------------------
# Phase 2 chat: AI fallback. When the regex patterns above don't match, hand
# the question to Claude with a fixed set of tools (the same lookup functions
# used by the regex path, plus list_failed_orders). Claude only ever picks a
# tool and supplies its arguments - it never sees or writes SQL - so the
# backend stays in full control of what gets queried.
# ---------------------------------------------------------------------------

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
_anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

AI_SYSTEM_PROMPT = (
    "You are an assistant for a warehouse EDI operations dashboard. Use the available tools "
    "to answer questions about a specific PO/order's status, a specific ISA file's status, or "
    "the current list of EDI files that failed to parse. Only call a tool when the question is "
    "clearly about one of those topics,  If you call a tool, use the exact input schema specified "
    "for that tool and do not make up any other fields. Otherwise, reply directly and briefly "
    "explaining you can only help with PO lookups, ISA lookups, and failed file lists, at this time."
)

AI_TOOLS = [
    {
        "name": "lookup_po",
        "description": "Look up the WMS integration status of a specific PO/warehouse order number.",
        "input_schema": {
            "type": "object",
            "properties": {"po_number": {"type": "string", "description": "The PO or warehouse order number"}},
            "required": ["po_number"],
        },
    },
    {
        "name": "lookup_isa",
        "description": "Look up the parse status of a specific EDI file by its ISA control number.",
        "input_schema": {
            "type": "object",
            "properties": {"isa_number": {"type": "string", "description": "The ISA control number"}},
            "required": ["isa_number"],
        },
    },
    {
        "name": "list_failed_orders",
        "description": "List EDI files that failed to parse (ProcessStatus = PARSE_FAILED), most recent first.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

AI_TOOL_DISPATCH = {
    "lookup_po": lambda tool_input: handle_po_lookup(tool_input["po_number"]),
    "lookup_isa": lambda tool_input: handle_isa_lookup(tool_input["isa_number"]),
    "list_failed_orders": lambda tool_input: handle_failed_orders(),
}

# In-memory, per-process rate limit on the AI fallback path only - the regex
# fast path is free and unlimited. This resets per Azure App Service worker
# process (gunicorn runs 2), so the effective ceiling is roughly 2x the
# configured value. That's an acceptable tradeoff for a portfolio-scale app;
# a shared store (e.g. Redis) would be needed for an exact global limit.
AI_RATE_LIMIT_WINDOW_SECONDS = 60 * 60
AI_RATE_LIMIT_MAX_REQUESTS = 20
_ai_rate_limit_state: dict[str, tuple[float, int]] = {}


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def is_ai_rate_limited(client_ip: str) -> bool:
    now = time.time()
    window_start, count = _ai_rate_limit_state.get(client_ip, (now, 0))
    if now - window_start > AI_RATE_LIMIT_WINDOW_SECONDS:
        window_start, count = now, 0
    count += 1
    _ai_rate_limit_state[client_ip] = (window_start, count)
    return count > AI_RATE_LIMIT_MAX_REQUESTS


def handle_ai_fallback(question: str) -> Optional[dict]:
    if not _anthropic_client:
        return None

    try:
        messages = [{"role": "user", "content": question}]
        response = _anthropic_client.messages.create(
            model="claude-sonnet-5",
            max_tokens=400,
            system=AI_SYSTEM_PROMPT,
            tools=AI_TOOLS,
            messages=messages,
        )

        tool_use = next((block for block in response.content if block.type == "tool_use"), None)
        if not tool_use:
            text = "".join(block.text for block in response.content if block.type == "text")
            return {
                "intent": "ai_unhandled",
                "reply": text or build_unknown_reply(),
                "matches": [],
                "source": "ai",
            }

        tool_fn = AI_TOOL_DISPATCH.get(tool_use.name)
        if not tool_fn:
            return {"intent": "ai_unhandled", "reply": build_unknown_reply(), "matches": [], "source": "ai"}

        tool_result = tool_fn(tool_use.input)

        messages.append({"role": "assistant", "content": response.content})
        messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": json.dumps(tool_result),
            }],
        })

        final = _anthropic_client.messages.create(
            model="claude-sonnet-5",
            max_tokens=300,
            system=AI_SYSTEM_PROMPT,
            tools=AI_TOOLS,
            messages=messages,
        )
        final_text = "".join(block.text for block in final.content if block.type == "text")

        return {
            "intent": f"ai_{tool_use.name}",
            "reply": final_text or tool_result.get("reply", ""),
            "matches": tool_result.get("matches", []),
            "source": "ai",
        }
    except Exception as exc:
        # Don't leak exception details (e.g. a billing/quota error) to the chat UI -
        # degrade to the same message the regex path gives when it can't help.
        print(f"[chat] AI fallback error: {exc}")
        return {"intent": "ai_error", "reply": build_unknown_reply(), "matches": [], "source": "regex"}


@app.get("/api/chat/sample-isa")
def sample_isa(_: dict = Depends(require_auth)):
    return {"isaControlNumber": get_latest_failed_isa()}


@app.post("/api/chat")
def chat(request: ChatRequest, http_request: Request, _: dict = Depends(require_auth)):
    question = request.question or ""

    isa_match = ISA_PATTERN.search(question)
    if isa_match:
        return {**handle_isa_lookup(isa_match.group(1).strip()), "source": "regex"}

    po_match = PO_PATTERN.search(question)
    if po_match:
        return {**handle_po_lookup(po_match.group(1).strip()), "source": "regex"}

    if _anthropic_client and is_ai_rate_limited(get_client_ip(http_request)):
        return {"intent": "ai_rate_limited", "reply": build_unknown_reply(), "matches": [], "source": "regex"}

    ai_result = handle_ai_fallback(question)
    if ai_result:
        return ai_result

    return {"intent": "unknown", "reply": build_unknown_reply(), "matches": [], "source": "regex"}
