from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from pathlib import Path
from typing import Optional
import calendar
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import jwt
from jwt import PyJWKClient
import pyodbc
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from datetime import datetime, timezone, timedelta
import requests
from azure.identity import DefaultAzureCredential
from azure.mgmt.datafactory import DataFactoryManagementClient
from anthropic import Anthropic
from typing import List
import change_request_lib as cr_lib
from services.google_sheets import (
    clear_sheet_values,
    update_sheet_values,
)
from services.sql_export import query_to_sheet_values

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


# ---------------------------------------------------------------------------
# RBAC: Groups -> Roles -> Permissions, stored in dbo.Groups/Roles/Permissions/
# RolePermissions/GroupRoles/UserGroups/UserRoles (see api/sql/001_rbac_schema.sql).
# A user's effective permissions are the union of permissions granted by
# roles assigned directly to them and roles inherited through group
# membership. Every protected endpoint declares the one permission it needs
# via require_permission("some.permission") rather than checking role names
# inline, so adding a new protected action never touches this auth code.
# ---------------------------------------------------------------------------

def get_user_oid(payload: dict) -> str:
    oid = payload.get("oid") or payload.get("sub")
    if not oid:
        raise HTTPException(status_code=401, detail="Token missing user identifier")
    return oid


def get_user_permissions(user_oid: str) -> list[str]:
    result = rows_params(
        """
        SELECT DISTINCT p.PermissionName
        FROM dbo.Permissions p
        JOIN dbo.RolePermissions rp ON rp.PermissionId = p.PermissionId
        WHERE rp.RoleId IN (
            SELECT RoleId FROM dbo.UserRoles WHERE UserOid = ?
            UNION
            SELECT gr.RoleId FROM dbo.UserGroups ug
            JOIN dbo.GroupRoles gr ON gr.GroupId = ug.GroupId
            WHERE ug.UserOid = ?
        )
        """,
        (user_oid, user_oid),
    )
    return [row["PermissionName"] for row in result]


def require_permission(permission_name: str):
    def _check(payload: dict = Depends(require_auth)) -> dict:
        user_oid = get_user_oid(payload)
        if permission_name not in get_user_permissions(user_oid):
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission_name}")
        return payload
    return _check


def require_any_permission(*permission_names: str):
    """Allow the caller through if they hold ANY of the given permissions --
    e.g. SuperUser (files.download) and Admin (cr.admin) can both view/triage
    the CR queue, while endpoints that only Admin should reach still use
    require_permission("cr.admin") directly."""
    def _check(payload: dict = Depends(require_auth)) -> dict:
        user_oid = get_user_oid(payload)
        user_perms = get_user_permissions(user_oid)
        if not any(p in user_perms for p in permission_names):
            raise HTTPException(status_code=403, detail=f"Missing permission: one of {list(permission_names)}")
        return payload
    return _check


@app.get("/api/me/permissions")
def my_permissions(payload: dict = Depends(require_auth)):
    return {"permissions": get_user_permissions(get_user_oid(payload))}


# Demo-only self-service role grant so the portfolio site's "Make me a
# SuperUser" button has something to call. SuperUser only grants
# files.download (the file-browsing demo) -- it deliberately does NOT grant
# cr.admin, since that role controls real code changes/merges/deploys and
# must never be self-service on a public site. A real Admin is added by
# inserting directly into dbo.UserRoles (see api/README or ask the site
# owner) - require_permission() itself doesn't know or care how a row got
# into UserRoles, so that grant path never touches this code.
@app.post("/api/demo/grant-admin")
def grant_demo_admin(payload: dict = Depends(require_auth)):
    user_oid = get_user_oid(payload)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            MERGE dbo.UserRoles AS target
            USING (
                SELECT ? AS UserOid, RoleId FROM dbo.Roles WHERE RoleName = 'SuperUser'
            ) AS src
            ON target.UserOid = src.UserOid AND target.RoleId = src.RoleId
            WHEN NOT MATCHED THEN
                INSERT (UserOid, RoleId) VALUES (src.UserOid, src.RoleId);
            """,
            (user_oid,),
        )
        conn.commit()
    return {"permissions": get_user_permissions(user_oid)}


@app.post("/api/demo/revoke-admin")
def revoke_demo_admin(payload: dict = Depends(require_auth)):
    user_oid = get_user_oid(payload)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            DELETE ur
            FROM dbo.UserRoles ur
            JOIN dbo.Roles r ON r.RoleId = ur.RoleId
            WHERE ur.UserOid = ? AND r.RoleName = 'SuperUser'
            """,
            (user_oid,),
        )
        conn.commit()
    return {"permissions": get_user_permissions(user_oid)}


# ---------------------------------------------------------------------------
# Change request review (pipeline Gate 1) - lists and approves/rejects the
# markdown Change Requests written by pipeline/generate_change_request.py.
# Reuses the existing files.download permission as the "admin" gate rather
# than adding a new RBAC permission + seed migration for this demo-scale
# feature - see docs/ai-delivery-pipeline.md for the pipeline this serves.
# ---------------------------------------------------------------------------

# CRs live in dbo.ChangeRequests (Azure SQL) -- see api/change_request_lib.py
# for the schema/columns. Both local dev and the deployed API read/write the
# same table, closing the local-vs-deployed split that markdown files under
# api/change-requests/ had (those got wiped on every zip-deploy redeploy too).

# Loaded once at import time -- .change-pipeline.yml rarely changes, and this
# avoids a file read on every intake message.
CR_PIPELINE_CONFIG = cr_lib.load_config(Path(__file__).resolve().parent / ".change-pipeline.yml")
CR_INTAKE_SYSTEM_PROMPT = cr_lib.build_system_prompt(CR_PIPELINE_CONFIG)


# ---------------------------------------------------------------------------
# CR intake verification tools: narrow, read-only lookups the intake model
# can call to check its own classification against reality (e.g. "does this
# request really touch an auth file?") instead of guessing from the request
# text alone. Same allowlist-dispatch pattern as AI_TOOL_DISPATCH further
# below -- the model can only ever invoke one of these four functions, never
# arbitrary SQL or a shell command. This is a quality aid for classification,
# not the security backstop -- that's the deterministic keyword floor in
# cr_lib.find_forced_tier_c_keyword(), which doesn't trust the model at all.
# ---------------------------------------------------------------------------

GREP_REPO_ALLOWED_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".sql", ".yml", ".yaml", ".json", ".md"}
GREP_REPO_EXCLUDED_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
GREP_REPO_MAX_MATCHES = 20
GREP_REPO_MAX_FILES_SCANNED = 3000


def grep_repo(query: str) -> dict:
    query = (query or "").strip()
    if not query:
        return {"matches": []}

    # REPO_ROOT is the full monorepo root for local dev (main.py sits inside
    # a real git checkout), but the deployed container image is built with
    # `./api` as its Docker context (see api/Dockerfile's `COPY . .` into
    # WORKDIR /app) -- only the api/ folder ever lands in the image, so
    # REPO_ROOT (main.py's parent.parent) resolves to the container's
    # filesystem root there, and rglob'ing it walks the entire OS image.
    # Same "no .git = not a real checkout" signal require_git_repo() already
    # uses; fall back to just this file's own directory, the one thing
    # guaranteed to exist and be scoped correctly in every environment.
    search_root = REPO_ROOT if (REPO_ROOT / ".git").exists() else Path(__file__).resolve().parent

    pattern = re.compile(re.escape(query), re.IGNORECASE)
    matches = []
    scanned = 0
    for path in search_root.rglob("*"):
        if len(matches) >= GREP_REPO_MAX_MATCHES or scanned >= GREP_REPO_MAX_FILES_SCANNED:
            break
        if path.is_dir() or path.suffix not in GREP_REPO_ALLOWED_EXTENSIONS:
            continue
        if GREP_REPO_EXCLUDED_DIRS & set(path.parts):
            continue
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                matches.append({
                    "file": str(path.relative_to(search_root)),
                    "line": line_number,
                    "snippet": line.strip()[:200],
                })
                if len(matches) >= GREP_REPO_MAX_MATCHES:
                    break
    return {"matches": matches}


def read_rbac_schema() -> dict:
    return {
        "roles": rows("SELECT RoleId, RoleName FROM dbo.Roles"),
        "permissions": rows("SELECT PermissionId, PermissionName FROM dbo.Permissions"),
        "rolePermissions": rows("""
            SELECT r.RoleName, p.PermissionName
            FROM dbo.RolePermissions rp
            JOIN dbo.Roles r ON r.RoleId = rp.RoleId
            JOIN dbo.Permissions p ON p.PermissionId = rp.PermissionId
        """),
    }


def list_schema_columns(table_name: str) -> dict:
    columns = rows_params(
        """
        SELECT COLUMN_NAME AS columnName, DATA_TYPE AS dataType, IS_NULLABLE AS isNullable
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = ?
        ORDER BY ORDINAL_POSITION
        """,
        (table_name,),
    )
    return {"tableExists": bool(columns), "columns": columns}


def check_endpoint_exists(path: str) -> dict:
    normalized = path if path.startswith("/") else f"/{path}"
    existing_paths = {route.path for route in app.routes if hasattr(route, "path")}
    return {"exists": normalized in existing_paths}


CR_INTAKE_TOOLS = [
    {
        "name": "grep_repo",
        "description": (
            "Case-insensitive text search across this repo's source files (.py, .ts, .tsx, "
            ".sql, .yml, .json, .md). Use this to verify whether a request actually touches "
            "auth/security code, a specific table, or an existing feature, instead of "
            "guessing. Returns up to 20 matching file:line snippets."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text to search for, e.g. a function name, table name, or keyword."}
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_rbac_schema",
        "description": (
            "Return this project's actual roles, permissions, and role-permission mappings, "
            "so you can check a claim like 'touches auth' against the real permission model."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_schema_columns",
        "description": (
            "Look up the real columns of a database table by name, to verify a claimed schema "
            "touch-point (e.g. 'adds a column to X') against what the table actually has today."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"table_name": {"type": "string", "description": "Table name without schema prefix, e.g. 'EDI940_Raw'."}},
            "required": ["table_name"],
        },
    },
    {
        "name": "check_endpoint_exists",
        "description": "Check whether an API route path already exists, to verify a claim like 'new GET endpoint' is genuinely new.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Route path, e.g. '/api/reports/daily-volume'."}},
            "required": ["path"],
        },
    },
]

CR_INTAKE_TOOL_DISPATCH = {
    "grep_repo": lambda tool_input: grep_repo(tool_input["query"]),
    "read_rbac_schema": lambda tool_input: read_rbac_schema(),
    "list_schema_columns": lambda tool_input: list_schema_columns(tool_input["table_name"]),
    "check_endpoint_exists": lambda tool_input: check_endpoint_exists(tool_input["path"]),
}

# Hard cap on tool round trips per intake message -- bounds latency/cost and
# guarantees the loop below terminates rather than trusting the model to stop
# calling tools on its own.
CR_INTAKE_MAX_TOOL_ITERATIONS = 4


class IntakeHistoryTurn(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class IntakeRequest(BaseModel):
    message: str
    history: List[IntakeHistoryTurn] = []


@app.post("/api/change-requests/intake")
def change_request_intake(
    request: IntakeRequest,
    http_request: Request,
    payload: dict = Depends(require_auth),
):
    # Open to any signed-in user, not admin-gated -- submitting a request is
    # the "Business user" role in the pipeline design; only approving it
    # (Gate 1) is admin-gated. Shares the AI chat fallback's rate limit since
    # both are the same kind of cost-incurring, publicly-reachable AI path.
    if not _anthropic_client:
        raise HTTPException(status_code=503, detail="AI intake is not configured on this deployment.")
    if is_ai_rate_limited(get_client_ip(http_request)):
        raise HTTPException(status_code=429, detail="Too many AI requests this hour. Try again later.")

    messages = [{"role": turn.role, "content": turn.content} for turn in request.history]
    messages.append({"role": "user", "content": request.message})

    # Tool round trips (grep_repo, read_rbac_schema, ...) happen on a working
    # copy, not `messages` itself -- they're local to this request and never
    # echoed back into request.history by the frontend, so `messages` stays
    # exactly request.history + the new user turn for the transcript-pairing
    # logic below, which assumes strict user/assistant alternation.
    loop_messages = list(messages)
    reply = None
    try:
        for _ in range(CR_INTAKE_MAX_TOOL_ITERATIONS):
            response = _anthropic_client.messages.create(
                model="claude-sonnet-5",
                max_tokens=1500,
                system=CR_INTAKE_SYSTEM_PROMPT,
                tools=CR_INTAKE_TOOLS,
                messages=loop_messages,
            )
            # Claude can emit more than one tool_use block in a single turn
            # (parallel tool calls) -- the API requires every tool_use id to
            # have a matching tool_result in the very next message, so all of
            # them must be resolved and answered together, not just the first.
            tool_use_blocks = [block for block in response.content if block.type == "tool_use"]
            if not tool_use_blocks:
                reply = "".join(block.text for block in response.content if block.type == "text")
                break

            loop_messages.append({"role": "assistant", "content": response.content})
            tool_result_blocks = []
            for tool_use in tool_use_blocks:
                tool_fn = CR_INTAKE_TOOL_DISPATCH.get(tool_use.name)
                if not tool_fn:
                    tool_result = {"error": f"Unknown tool '{tool_use.name}'"}
                else:
                    try:
                        tool_result = tool_fn(tool_use.input)
                    except Exception as tool_exc:
                        # A tool failing (e.g. DB unreachable) shouldn't kill the
                        # whole intake conversation -- feed the model an error
                        # result so it can proceed without that piece of info,
                        # rather than surfacing an opaque 502 to the user.
                        print(f"[change-request-intake] tool '{tool_use.name}' failed: {tool_exc}")
                        tool_result = {"error": f"Tool '{tool_use.name}' failed: {tool_exc}"}
                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": json.dumps(tool_result),
                })
            loop_messages.append({"role": "user", "content": tool_result_blocks})
        else:
            # Hit the iteration cap while the model was still calling tools --
            # force a final answer with tools stripped so the request always
            # terminates instead of leaving the user stuck mid-loop.
            response = _anthropic_client.messages.create(
                model="claude-sonnet-5",
                max_tokens=1500,
                system=CR_INTAKE_SYSTEM_PROMPT,
                messages=loop_messages,
            )
            reply = "".join(block.text for block in response.content if block.type == "text")
    except Exception as exc:
        print(f"[change-request-intake] error: {exc}")
        raise HTTPException(status_code=502, detail="AI intake call failed. Try again.")

    cr_data = cr_lib.extract_json_block(reply)

    if cr_data is None:
        question = reply.strip()
        if question.startswith("QUESTION:"):
            question = question[len("QUESTION:"):].strip()
        return {"type": "question", "text": question}

    # Original request = the first user turn in the conversation, not this
    # final message (which is just the answer to the last clarifying question).
    original_request = request.history[0].content if request.history else request.message

    # messages alternates user(0), assistant(1), user(2), assistant(3), ... --
    # index 0 is the original request, so (question, answer) pairs start at
    # the first assistant turn (index 1) and step by 2.
    transcript = []
    for i in range(1, len(messages) - 1, 2):
        question = messages[i]["content"].strip()
        if question.startswith("QUESTION:"):
            question = question[len("QUESTION:"):].strip()
        transcript.append((question, messages[i + 1]["content"]))

    dollars, ratio_pct = cr_lib.compute_cost(cr_data.get("estimated_tokens", 0), CR_PIPELINE_CONFIG)
    with cr_lib.get_conn() as conn:
        cr_number = cr_lib.next_cr_number(conn)
        created = cr_lib.create_cr(conn, cr_number, original_request, transcript, cr_data, dollars, ratio_pct, CR_PIPELINE_CONFIG)

    return {
        "type": "complete",
        "crNumber": cr_number,
        "title": created["title"],
        "tier": created["tier"],
        "estimatedTokens": created["estimatedTokens"],
        "estimatedCost": created["estimatedCost"],
        "costRatioPct": created["costRatioPct"],
    }


@app.get("/api/change-requests")
def list_change_requests(
    status_group: Optional[str] = None,
    _: dict = Depends(require_any_permission("cr.admin", "files.download")),
):
    # status_group filters the list for the CR-Workflow tabs: "active" (every
    # CR that isn't Closed/Merged), "closed" (only Closed/Merged), or all when
    # omitted. Unknown values fall through to the unfiltered list.
    with cr_lib.get_conn() as conn:
        return cr_lib.list_crs(conn, status_group)


@app.get("/api/change-requests/{cr_number}")
def get_change_request(cr_number: int, _: dict = Depends(require_any_permission("cr.admin", "files.download"))):
    with cr_lib.get_conn() as conn:
        cr = cr_lib.get_cr(conn, cr_number)
    if not cr:
        raise HTTPException(status_code=404, detail=f"CR-{cr_number:03d} not found")
    return cr


@app.get("/api/change-requests/{cr_number}/progress")
def get_change_request_progress(cr_number: int, _: dict = Depends(require_any_permission("cr.admin", "files.download"))):
    # Updated incrementally by pipeline/implement_change_request.py as it
    # streams Claude Code's output -- session id, running token count, and a
    # human-readable last-action line, independent of whatever process (CLI
    # or API) launched the run, and readable from anywhere with DB access
    # (unlike the old sidecar progress.json, which was local-repo-only).
    with cr_lib.get_conn() as conn:
        return cr_lib.get_progress(conn, cr_number)


PIPELINE_SCRIPT = Path(__file__).resolve().parent.parent / "pipeline" / "implement_change_request.py"


def launch_implementation(cr_number: int, repo_root: Path, max_budget_usd: Optional[float] = None):
    # Fire-and-forget: implement_change_request.py writes its own progress
    # (session id, token count, last action) to dbo.ChangeRequests as it
    # streams, so there's no need for an in-memory job registry here -- the
    # row itself is the durable status, readable by /progress regardless of
    # what launched the run or whether this API process restarts. Raw stdout
    # goes to a temp file purely for post-mortem debugging, not read back.
    import tempfile
    log_path = Path(tempfile.gettempdir()) / f"cr-{cr_number:03d}-implement.log"
    log_file = open(log_path, "w", encoding="utf-8")
    cmd = [sys.executable, str(PIPELINE_SCRIPT), str(cr_number), "--repo", str(repo_root)]
    if max_budget_usd is not None:
        cmd += ["--max-budget-usd", str(max_budget_usd)]
    subprocess.Popen(cmd, cwd=repo_root, stdout=log_file, stderr=subprocess.STDOUT)


# Gate 1 (review) is now split from Build kickoff so SuperUser -- a
# self-service, publicly-reachable role -- can triage requests without being
# able to trigger a real Claude Code run. Approve only moves a CR to Pending
# Build Approval; only Admin (cr.admin) can start the actual build from
# there, via start_build_change_request below. Status literals live in
# cr_lib -- implement_change_request.py resets a failed build back to
# PENDING_BUILD_STATUS too, so both need the exact same string.
PENDING_STATUS = cr_lib.PENDING_STATUS
PENDING_BUILD_STATUS = cr_lib.PENDING_BUILD_STATUS


@app.post("/api/change-requests/{cr_number}/approve")
def approve_change_request(cr_number: int, payload: dict = Depends(require_any_permission("cr.admin", "files.download"))):
    approver = payload.get("name") or payload.get("preferred_username") or get_user_oid(payload)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with cr_lib.get_conn() as conn:
        cr = cr_lib.get_cr(conn, cr_number)
        if not cr:
            raise HTTPException(status_code=404, detail=f"CR-{cr_number:03d} not found")
        if cr["status"] != PENDING_STATUS:
            raise HTTPException(status_code=400, detail=f"CR-{cr_number:03d} is not awaiting Gate 1 review (status: '{cr['status']}').")
        cr_lib.update_status(conn, cr_number, f"{PENDING_BUILD_STATUS} -- Gate 1 approved by {approver} on {timestamp}")
        return cr_lib.get_cr(conn, cr_number)


@app.post("/api/change-requests/{cr_number}/reject")
def reject_change_request(cr_number: int, payload: dict = Depends(require_any_permission("cr.admin", "files.download"))):
    approver = payload.get("name") or payload.get("preferred_username") or get_user_oid(payload)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with cr_lib.get_conn() as conn:
        cr = cr_lib.get_cr(conn, cr_number)
        if not cr:
            raise HTTPException(status_code=404, detail=f"CR-{cr_number:03d} not found")
        at_build_stage = cr["status"].startswith(PENDING_BUILD_STATUS)
        if not at_build_stage and cr["status"] != PENDING_STATUS:
            raise HTTPException(status_code=400, detail=f"CR-{cr_number:03d} is not awaiting a decision (status: '{cr['status']}').")
        if at_build_stage and "cr.admin" not in get_user_permissions(get_user_oid(payload)):
            raise HTTPException(status_code=403, detail="Only Admin can reject at the Pending Build Approval stage.")
        label = "Rejected (Pre-Build)" if at_build_stage else "Rejected (Gate 1)"
        cr_lib.update_status(conn, cr_number, f"{label} by {approver} on {timestamp}")
        return cr_lib.get_cr(conn, cr_number)


class StartBuildRequest(BaseModel):
    maxBudgetUsd: Optional[float] = None


@app.post("/api/change-requests/{cr_number}/start-build")
def start_build_change_request(cr_number: int, body: StartBuildRequest, payload: dict = Depends(require_permission("cr.admin"))):
    approver = payload.get("name") or payload.get("preferred_username") or get_user_oid(payload)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with cr_lib.get_conn() as conn:
        cr = cr_lib.get_cr(conn, cr_number)
        if not cr:
            raise HTTPException(status_code=404, detail=f"CR-{cr_number:03d} not found")
        if not cr["status"].startswith(PENDING_BUILD_STATUS):
            raise HTTPException(status_code=400, detail=f"CR-{cr_number:03d} is not awaiting build approval (status: '{cr['status']}').")
        # Same "Approved (Gate 1) by ..." format the pipeline script and the
        # dashboard's progress polling already recognize -- reusing it here
        # means neither has to learn a second "build started" status.
        cr_lib.update_status(conn, cr_number, f"Approved (Gate 1) by {approver} on {timestamp}")
        result = cr_lib.get_cr(conn, cr_number)

    repo_root = Path(__file__).resolve().parent.parent
    if (repo_root / ".git").exists():
        launch_implementation(cr_number, repo_root, max_budget_usd=body.maxBudgetUsd)
        return result

    dispatch_build_workflow(cr_number, approver, body.maxBudgetUsd)
    return {
        "type": "dispatched",
        "message": f"Build for CR-{cr_number:03d} triggered via GitHub Actions -- check the repo's Actions tab for progress.",
    }


# ---------------------------------------------------------------------------
# Gate 2: merge / rollback. Runs real git commands against whatever repo this
# API process lives in. Only meaningful for a local dev API with a real git
# checkout and push credentials -- a zip-deployed Azure App Service has
# neither, so require_git_repo() fails those cleanly rather than pretend to
# work. Refuses to touch `main` if the working tree is dirty, since this repo
# is also where interactive edits happen (see the worktree fix in
# pipeline/implement_change_request.py for the same class of problem).
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent


def require_git_repo() -> Path:
    if not (REPO_ROOT / ".git").exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "No git repository here (this looks like a zip-deployed API with no .git). "
                "Merge/rollback only work against a local dev API with the real repo checked out."
            ),
        )
    return REPO_ROOT


def require_clean_working_tree(repo_root: Path):
    result = subprocess.run(["git", "status", "--porcelain"], cwd=repo_root, capture_output=True, text=True, encoding="utf-8")
    if result.stdout.strip():
        raise HTTPException(
            status_code=409,
            detail="Working tree has uncommitted changes -- commit or stash them before merging/rolling back.",
        )


def run_git(args: list, cwd: Path):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"`git {' '.join(args)}` failed:\n{result.stderr}")
    return result.stdout.strip()


# Fallback for deployments with no local git repo (e.g. a zip-deployed Azure
# App Service): trigger the actual merge/revert via a GitHub Actions
# workflow_dispatch instead. The git operations then run on GitHub's own
# runner using the Actions-provided token -- this App Service never holds
# push credentials itself. Requires GITHUB_DISPATCH_TOKEN (a fine-grained PAT
# scoped to this repo with Actions: write) set as an app setting.
GITHUB_REPO = os.getenv("GITHUB_REPO", "Arnett951/edi-wms-project")
GITHUB_DISPATCH_TOKEN = os.getenv("GITHUB_DISPATCH_TOKEN")


def dispatch_github_workflow_file(workflow_file: str, inputs: dict):
    if not GITHUB_DISPATCH_TOKEN:
        raise HTTPException(
            status_code=503,
            detail=(
                "No local git repo here, and GITHUB_DISPATCH_TOKEN isn't configured on this "
                "deployment -- can't trigger this action remotely. Set that app setting to enable it."
            ),
        )
    resp = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{workflow_file}/dispatches",
        headers={
            "Authorization": f"Bearer {GITHUB_DISPATCH_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        json={"ref": "main", "inputs": inputs},
        timeout=10,
    )
    if resp.status_code != 204:
        raise HTTPException(status_code=502, detail=f"GitHub workflow dispatch failed ({resp.status_code}): {resp.text}")


def dispatch_github_workflow(action: str, cr_number: int, approver: str):
    dispatch_github_workflow_file(
        "cr-gate2-dispatch.yml",
        {"action": action, "cr_number": str(cr_number), "approver": approver},
    )


def dispatch_build_workflow(cr_number: int, approver: str, max_budget_usd: Optional[float]):
    inputs = {"cr_number": str(cr_number), "approver": approver}
    if max_budget_usd is not None:
        inputs["max_budget_usd"] = str(max_budget_usd)
    dispatch_github_workflow_file("cr-build-dispatch.yml", inputs)


@app.post("/api/change-requests/{cr_number}/merge")
def merge_change_request(cr_number: int, payload: dict = Depends(require_permission("cr.admin"))):
    approver = payload.get("name") or payload.get("preferred_username") or get_user_oid(payload)
    if not (REPO_ROOT / ".git").exists():
        dispatch_github_workflow("merge", cr_number, approver)
        return {
            "type": "dispatched",
            "message": f"Merge for CR-{cr_number:03d} triggered via GitHub Actions -- check the repo's Actions tab for progress.",
        }

    repo_root = require_git_repo()
    require_clean_working_tree(repo_root)

    with cr_lib.get_conn() as conn:
        cr = cr_lib.get_cr(conn, cr_number)
        if not cr:
            raise HTTPException(status_code=404, detail=f"CR-{cr_number:03d} not found")
        if not cr["status"].startswith("Implemented"):
            raise HTTPException(status_code=400, detail=f"CR-{cr_number:03d} is not ready to merge (status: '{cr['status']}').")
        branch = cr["branch"]
        if not branch:
            raise HTTPException(status_code=400, detail=f"CR-{cr_number:03d} has no recorded Branch to merge.")
        title = cr["title"]

        run_git(["fetch", "origin"], repo_root)
        run_git(["checkout", "main"], repo_root)
        run_git(["pull", "origin", "main"], repo_root)

        merge_result = subprocess.run(
            ["git", "merge", f"origin/{branch}", "--no-ff", "-m", f"Merge CR-{cr_number:03d}: {title}"],
            cwd=repo_root, capture_output=True, text=True, encoding="utf-8",
        )
        if merge_result.returncode != 0:
            subprocess.run(["git", "merge", "--abort"], cwd=repo_root, capture_output=True, text=True, encoding="utf-8")
            raise HTTPException(
                status_code=409,
                detail=f"Merge conflict merging origin/{branch} into main -- resolve manually. Details:\n{merge_result.stderr}",
            )

        run_git(["push", "origin", "main"], repo_root)
        merge_commit = run_git(["rev-parse", "HEAD"], repo_root)

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        cr_lib.set_fields(conn, cr_number, mergeCommit=merge_commit)
        cr_lib.update_status(conn, cr_number, f"Merged (Gate 2) by {approver} on {timestamp}")
        cr_lib.cleanup_worktree(repo_root, branch)
        return cr_lib.get_cr(conn, cr_number)


@app.post("/api/change-requests/{cr_number}/rollback")
def rollback_change_request(cr_number: int, payload: dict = Depends(require_permission("cr.admin"))):
    approver = payload.get("name") or payload.get("preferred_username") or get_user_oid(payload)
    if not (REPO_ROOT / ".git").exists():
        dispatch_github_workflow("rollback", cr_number, approver)
        return {
            "type": "dispatched",
            "message": f"Rollback for CR-{cr_number:03d} triggered via GitHub Actions -- check the repo's Actions tab for progress.",
        }

    repo_root = require_git_repo()
    require_clean_working_tree(repo_root)

    with cr_lib.get_conn() as conn:
        cr = cr_lib.get_cr(conn, cr_number)
        if not cr:
            raise HTTPException(status_code=404, detail=f"CR-{cr_number:03d} not found")
        if not cr["status"].startswith("Merged"):
            raise HTTPException(status_code=400, detail=f"CR-{cr_number:03d} has not been merged -- nothing to roll back.")
        merge_commit = cr["mergeCommit"]
        if not merge_commit:
            raise HTTPException(status_code=400, detail=f"CR-{cr_number:03d} has no recorded merge commit.")

        run_git(["fetch", "origin"], repo_root)
        run_git(["checkout", "main"], repo_root)
        run_git(["pull", "origin", "main"], repo_root)

        revert_result = subprocess.run(
            ["git", "revert", merge_commit, "-m", "1", "--no-edit"],
            cwd=repo_root, capture_output=True, text=True, encoding="utf-8",
        )
        if revert_result.returncode != 0:
            subprocess.run(["git", "revert", "--abort"], cwd=repo_root, capture_output=True, text=True, encoding="utf-8")
            raise HTTPException(
                status_code=409,
                detail=f"Revert conflict on {merge_commit} -- resolve manually. Details:\n{revert_result.stderr}",
            )

        run_git(["push", "origin", "main"], repo_root)
        revert_commit = run_git(["rev-parse", "HEAD"], repo_root)

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        cr_lib.set_fields(conn, cr_number, rollbackCommit=revert_commit)
        cr_lib.update_status(conn, cr_number, f"Rolled back (Gate 2) by {approver} on {timestamp}")
        if cr["branch"]:
            cr_lib.cleanup_worktree(repo_root, cr["branch"])
        return cr_lib.get_cr(conn, cr_number)


# To check Health of the API
@app.get("/health")
def health():
    return {"status": "ok"}

OPERATIONAL_ALERTS_QUERY = """
SELECT *
FROM dbo.vw_OperationalAlerts
ORDER BY 1;
"""
CUSTOMER_ERRORS_QUERY = """
SELECT *
FROM dbo.vw_CustomerErrors
WHERE ErrorDate >= DATEADD(DAY,-30,GETDATE())
ORDER BY ErrorDate DESC;
"""
@app.post("/api/tableau/load-customer-errors")
def load_customer_errors():

    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID")

    values = query_to_sheet_values(CUSTOMER_ERRORS_QUERY)

    clear_sheet_values(
        spreadsheet_id=spreadsheet_id,
        sheet_range="ORDERS_CUST_ERROR!A:ZZ"
    )

    result = update_sheet_values(
        spreadsheet_id=spreadsheet_id,
        sheet_range="ORDERS_CUST_ERROR!A1",
        values=values
    )

    return {
        "status": "success",
        "rows": len(values)-1,
        "updatedCells": result.get("updatedCells")
    }

@app.post("/api/tableau/load-operational-alerts")
def load_operational_alerts():
    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID")

    if not spreadsheet_id:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_SPREADSHEET_ID is not configured",
        )

    try:
        values = query_to_sheet_values(
            OPERATIONAL_ALERTS_QUERY
        )

        clear_sheet_values(
            spreadsheet_id=spreadsheet_id,
            sheet_range="OperationalAlerts!A:ZZ",
        )

        result = update_sheet_values(
            spreadsheet_id=spreadsheet_id,
            sheet_range="OperationalAlerts!A1",
            values=values,
        )

        return {
            "status": "success",
            "sheet": "OperationalAlerts",
            "data_rows": max(len(values) - 1, 0),
            "columns": len(values[0]) if values else 0,
            "updated_cells": result.get(
                "updatedCells",
                0,
            ),
            "completed_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Operational Alerts export failed: {exc}",
        ) from exc

@app.post("/api/tableau/test-google-sheet")
def test_google_sheet(_: dict = Depends(require_auth)):
    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID")

    if not spreadsheet_id:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_SPREADSHEET_ID is not configured",
        )

    values = [
        ["Status", "UpdatedAt"],
        [
            "FastAPI connected successfully",
            datetime.now(timezone.utc).isoformat(),
        ],
    ]

    try:
        result = update_sheet_values(
            spreadsheet_id=spreadsheet_id,
            sheet_range="OperationalAlerts!A1",
            values=values,
        )
    except Exception as exc:
        print(f"[google-sheets-test] error: {exc}")
        raise HTTPException(
            status_code=502,
            detail="Unable to update Google Sheet",
        )

    return {
        "status": "success",
        "updatedRange": result.get("updatedRange"),
        "updatedCells": result.get("updatedCells"),
    }

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

SQL_RESUME_RETRY_ATTEMPTS = 4
SQL_RESUME_RETRY_DELAY_SECONDS = 5

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

    connection_string = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER=tcp:{server},1433;"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password};"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
        "Connection Timeout=30;"
    )

    # This DB is on Azure SQL's serverless tier, which auto-pauses after
    # inactivity -- the first connection after a gap gets error 40613
    # ("not currently available... retry the connection later") while it
    # resumes, not a real outage. Retry with a short delay instead of
    # surfacing that as a 500/502 to every caller.
    for attempt in range(SQL_RESUME_RETRY_ATTEMPTS):
        try:
            return pyodbc.connect(connection_string)
        except pyodbc.Error as exc:
            if "40613" not in str(exc) or attempt == SQL_RESUME_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(SQL_RESUME_RETRY_DELAY_SECONDS)

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

# ---------------------------------------------------------------------------
# File retrieval: resolve a filename to a short-lived SAS download URL. A
# file lives in edi940-inbound while still queued, and gets moved to
# edi940-archive once ADF has processed it - rather than guessing which from
# ProcessStatus, just check archive first (the common case for anything
# already in EDI940_Raw) and fall back to inbound.
# ---------------------------------------------------------------------------

def _parse_storage_account_key(conn_str: str) -> tuple[str, str]:
    parts = dict(segment.split("=", 1) for segment in conn_str.split(";") if "=" in segment)
    return parts["AccountName"], parts["AccountKey"]


def find_blob(file_name: str) -> Optional[tuple[str, str]]:
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not conn_str:
        return None

    blob_service = BlobServiceClient.from_connection_string(conn_str)
    archive_container = os.getenv("BLOB_ARCHIVE_CONTAINER_NAME", "edi940-archive")
    inbound_container = os.getenv("BLOB_CONTAINER_NAME", "edi940-inbound")

    for container_name in (archive_container, inbound_container):
        container = blob_service.get_container_client(container_name)

        if container.get_blob_client(file_name).exists():
            return container_name, file_name

        # EDI940_Raw.FileName doesn't always match the blob's actual name on
        # disk (e.g. the pipeline has been seen writing a ".txt" suffix onto
        # the recorded name) - fall back to a prefix match within the container.
        for blob in container.list_blobs(name_starts_with=file_name):
            return container_name, blob.name

    return None


def generate_file_download_url(file_name: str, container_name: str) -> tuple[str, datetime]:
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not conn_str:
        raise HTTPException(status_code=500, detail="AZURE_STORAGE_CONNECTION_STRING is not set")

    account_name, account_key = _parse_storage_account_key(conn_str)
    expiry = datetime.now(timezone.utc) + timedelta(minutes=10)
    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container_name,
        blob_name=file_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=expiry,
    )
    url = f"https://{account_name}.blob.core.windows.net/{container_name}/{file_name}?{sas_token}"
    return url, expiry


def resolve_file_download(file_name: str) -> dict:
    found = find_blob(file_name)
    if not found:
        raise HTTPException(
            status_code=404,
            detail=f"{file_name} was not found in blob storage (it may have been purged).",
        )
    container_name, blob_name = found
    url, expiry = generate_file_download_url(blob_name, container_name)
    return {"fileName": blob_name, "downloadUrl": url, "expiresAt": expiry.isoformat()}


@app.get("/api/files/{raw_id}/download-url")
def get_file_download_url(raw_id: int, _: dict = Depends(require_permission("files.download"))):
    result = rows_params(
        "SELECT FileName AS fileName FROM dbo.EDI940_Raw WHERE RawId = ?",
        (raw_id,),
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"No file found for RawId {raw_id}.")
    return resolve_file_download(result[0]["fileName"])

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

# ---------------------------------------------------------------------------
# Reports: read-only analytics endpoints. All require authentication but no
# special RBAC permission beyond being a signed-in user.
# ---------------------------------------------------------------------------

@app.get("/api/reports/daily-volume")
def daily_edi_volume(_: dict = Depends(require_auth)):
    """Return count of EDI 940 files received per day for the last 30 calendar
    days (UTC), including days with zero files."""
    return rows("""
        WITH DateSeries AS (
            SELECT CAST(DATEADD(day, -n.n, CAST(GETUTCDATE() AS date)) AS date) AS [date]
            FROM (VALUES (0),(1),(2),(3),(4),(5),(6),(7),(8),(9),
                         (10),(11),(12),(13),(14),(15),(16),(17),(18),(19),
                         (20),(21),(22),(23),(24),(25),(26),(27),(28),(29)) AS n(n)
        )
        SELECT
            FORMAT(ds.[date], 'yyyy-MM-dd') AS [date],
            COUNT(r.RawId) AS [count]
        FROM DateSeries ds
        LEFT JOIN dbo.EDI940_Raw r
            ON CAST(r.LoadDateTime AS date) = ds.[date]
        GROUP BY ds.[date]
        ORDER BY ds.[date]
    """)


@app.get("/api/reports/file-status-summary")
def file_status_summary(_: dict = Depends(require_auth)):
    """Return counts of received vs errored EDI 940 files per client (sender)
    over a rolling 48-hour window ending now (UTC). A file is 'errored' when
    its ProcessStatus matches '%fail%' (case-insensitive, the default SQL
    Server collation); every other row counts as 'received'. Grouped by
    ISASender, used directly as the client label with no name lookup."""
    return rows("""
        SELECT
            ISASender AS sender,
            SUM(CASE WHEN ProcessStatus LIKE '%fail%' THEN 0 ELSE 1 END) AS received,
            SUM(CASE WHEN ProcessStatus LIKE '%fail%' THEN 1 ELSE 0 END) AS errored
        FROM dbo.EDI940_Raw
        WHERE LoadDateTime >= DATEADD(hour, -48, GETUTCDATE())
        GROUP BY ISASender
        ORDER BY ISASender
    """)


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

#To power the Funnel Dashboard: one row per pipeline gate, with item counts,
#oldest-item age, and a RED/GREEN health color for the monitored gates
#(see sql/views/dbo.vw_PiplineFunnel.sql for the staleness rule).
@app.get("/api/dashboard/funnel")
def dashboard_funnel(_: dict = Depends(require_auth)):
    return rows("""
        SELECT
            GateName,
            GateOrder,
            IsMonitoredGate,
            ItemCount,
            CONVERT(varchar(19), OldestItemDateTime, 120) AS OldestItemDateTime,
            OldestItemAgeMinutes,
            GateStatusColor
        FROM dbo.vw_PiplineFunnel
        ORDER BY GateOrder
    """)

#To power the File Reconciliation panel: one row per inbound file with a
#rolled-up FileStatus (Reported to Customer / Delivered / In Progress / Needs
#Attention / Parse Failed) so every file received can be accounted for, and
#an AttentionReason for the ones that need action (see
#sql/views/dbo.vw_FileReconciliation.sql for the rollup rule).
@app.get("/api/dashboard/file-reconciliation")
def dashboard_file_reconciliation(_: dict = Depends(require_auth)):
    return rows("""
        SELECT TOP 500
            RawId,
            FileName,
            ISASender,
            ISA_ControlNumber,
            LoadDateTime,
            ProcessStatus,
            OrderCount,
            SuccessCount,
            FailedOrderCount,
            InFlightCount,
            FileStatus,
            AttentionReason,
            CustomerReportedDateTime,
            CustomerReportedBy
        FROM dbo.vw_FileReconciliation
        ORDER BY RawId DESC
    """)

#Line/PO-level detail for the customer exception report: one row per failed
#WMS order line for "Needs Attention" files, or one row per file for
#"Parse Failed" files (which never made it far enough to have orders/lines).
#Powers the "Generate Customer Report" action on the Funnel Dashboard.
@app.get("/api/dashboard/file-reconciliation/report-detail")
def file_reconciliation_report_detail(raw_ids: str, _: dict = Depends(require_auth)):
    try:
        ids = [int(x) for x in raw_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="raw_ids must be a comma-separated list of integers")
    if not ids:
        raise HTTPException(status_code=400, detail="raw_ids is required")

    placeholders = ",".join("?" for _ in ids)
    return rows_params(f"""
        SELECT
            r.RawId AS rawId,
            r.FileName AS fileName,
            r.ISASender AS isaSender,
            r.ISA_ControlNumber AS isaControlNumber,
            COALESCE(ohs.WarehouseOrderNumber, '—') AS po,
            CASE WHEN ods.LineNumber IS NOT NULL
                 THEN CONCAT('Line ', ods.LineNumber, ' — ', ods.SKU)
                 ELSE '—' END AS lineItem,
            COALESCE(ohs.ErrorMessage, vw.AttentionReason, 'No details available') AS errorMessage
        FROM dbo.EDI940_Raw r
        JOIN dbo.vw_FileReconciliation vw ON vw.RawId = r.RawId
        LEFT JOIN dbo.EDI940_Header h ON h.RawId = r.RawId
        LEFT JOIN wms.OrderHeader_Staging ohs ON ohs.SourceHeaderId = h.HeaderId AND ohs.IntegrationStatus = 'FAILED'
        LEFT JOIN wms.OrderDetail_Staging ods ON ods.WMSOrderHeaderStagingId = ohs.WMSOrderHeaderStagingId
        WHERE r.RawId IN ({placeholders})
        ORDER BY r.RawId, ohs.WarehouseOrderNumber, ods.LineNumber
    """, tuple(ids))


class MarkFilesReportedRequest(BaseModel):
    rawIds: List[int]


#Flips selected files to "Reported to Customer" once their exceptions have
#been handed off (see the Funnel Dashboard's mass-select report tool). Only
#sets a timestamp/author on EDI940_Raw -- never touches ProcessStatus, which
#the parsing/staging pipeline owns.
@app.post("/api/dashboard/file-reconciliation/mark-reported")
def mark_files_reported(body: MarkFilesReportedRequest, payload: dict = Depends(require_auth)):
    if not body.rawIds:
        raise HTTPException(status_code=400, detail="rawIds is required")

    reported_by = payload.get("name") or payload.get("preferred_username") or get_user_oid(payload)
    placeholders = ",".join("?" for _ in body.rawIds)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            UPDATE dbo.EDI940_Raw
            SET CustomerReportedDateTime = SYSUTCDATETIME(),
                CustomerReportedBy = ?
            WHERE RawId IN ({placeholders})
            """,
            (reported_by, *body.rawIds),
        )
        conn.commit()
    return {"success": True, "rawIds": body.rawIds, "reportedBy": reported_by}

#Live Azure Cost Management MTD spend for the "Cloud Cost" dashboard card.
#Requires the DefaultAzureCredential identity to hold Cost Management Reader
#on the subscription - see AZURE_SUBSCRIPTION_ID used elsewhere for ADF.
@app.get("/api/dashboard/cloud-cost")
def cloud_cost(_: dict = Depends(require_auth)):
    budget = float(os.getenv("CLOUD_BUDGET_MTD", "17.00"))
    try:
        credential = DefaultAzureCredential()
        token = credential.get_token("https://management.azure.com/.default").token
        subscription_id = os.environ["AZURE_SUBSCRIPTION_ID"]

        response = requests.post(
            f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.CostManagement/query",
            params={"api-version": "2023-11-01"},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "type": "ActualCost",
                "timeframe": "MonthToDate",
                "dataset": {
                    "granularity": "None",
                    "aggregation": {"totalCost": {"name": "PreTaxCost", "function": "Sum"}},
                },
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        columns = [c["name"] for c in payload["properties"]["columns"]]
        row = payload["properties"]["rows"][0]
        spend_mtd = float(row[columns.index("PreTaxCost")])
        currency = row[columns.index("Currency")]
    except Exception:
        raise HTTPException(status_code=502, detail="Unable to fetch Azure cost data.")

    now = datetime.now(timezone.utc)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    projected_month_end = (spend_mtd / now.day) * days_in_month if now.day else spend_mtd

    return {
        "spendMtd": round(spend_mtd, 2),
        "budget": budget,
        "projectedMonthEnd": round(projected_month_end, 2),
        "percentUsed": round((spend_mtd / budget) * 100) if budget else 0,
        "currency": currency,
    }

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
    except Exception as exc:
        print(f"[adf-run] error: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Unable to start the ADF pipeline.",
        )

# ---------------------------------------------------------------------------
# Phase 1 chat: rule-based lookups for "where is PO X" / "what happened with
# ISA X" style questions. ISA control numbers aren't parsed into a column
# yet, so they're pulled out of EDI940_Raw.RawContent on the fly.
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str
    history: Optional[List[ChatMessage]] = None


# Support-mode follow-ups (e.g. answering "yes" to "Want a download link?")
# need the last few turns of conversation, the same way the CR-intake mode
# already threads its own history through -- capped at 5 so a long-running
# chat session doesn't balloon every AI-tier prompt.
CHAT_HISTORY_MAX_MESSAGES = 5


def sanitize_chat_history(history: Optional[List[ChatMessage]]) -> list[dict]:
    if not history:
        return []
    cleaned = [
        {"role": m.role, "content": m.content}
        for m in history
        if m.role in ("user", "assistant") and (m.content or "").strip()
    ]
    return cleaned[-CHAT_HISTORY_MAX_MESSAGES:]


CHAT_FEEDBACK_COMMENT_MAX_LENGTH = 1000
CHAT_FEEDBACK_CHANNELS = {"support", "intake"}


class ChatFeedbackRequest(BaseModel):
    question: str
    reply: str
    source: Optional[str] = None
    channel: Optional[str] = "support"
    rating: int
    comment: Optional[str] = None

PO_PATTERN = re.compile(
    r"\b(?:po|p\.o\.|purchase\s+order|order|warehouse\s+order)\b[\s#:\-]*([a-z0-9\-]+)",
    re.IGNORECASE
)

ISA_PATTERN = re.compile(
    r"\b(?:isa|isa\s+number|control\s+number|interchange|interchange\s+control\s+number)\b[\s#:\-]*([0-9]{1,9})",
    re.IGNORECASE
)

# Only catches the explicit "customer <name>" phrasing (matching the style of
# PO_PATTERN/ISA_PATTERN above) -- used to scope the bulk failed-file-download
# regex path below to one customer instead of silently ignoring the qualifier
# and returning the top N failures across all customers.
CUSTOMER_PATTERN = re.compile(
    r"\bcustomer\b[\s#:\-]*([a-z0-9\-]+)",
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# File-request detection: a self-contained fast path, checked before (and
# independent of) the ISA/PO status-lookup regexes below. It only fires on
# explicit "give/send/download me the file" phrasing, so plain status
# questions like "What happened with ISA 123?" are untouched and keep
# flowing through ISA_PATTERN/PO_PATTERN exactly as before.
# ---------------------------------------------------------------------------

FILE_REQUEST_INTENT_PATTERN = re.compile(
    r"\b(download|retrieve|copy of|send me|give me|can i get|get me)\b",
    re.IGNORECASE
)

FILENAME_PATTERN = re.compile(r"\b([\w\-]+\.edi)\b", re.IGNORECASE)

ERROR_FILES_PATTERN = re.compile(
    r"\b(error|errors|failed|failure|failures)\b.{0,20}\bfiles?\b|\bfiles?\b.{0,20}\b(error|errors|failed|failure|failures)\b",
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


def explain_error(error_message: Optional[str]) -> Optional[str]:
    # dbo.ErrorKnowledgeBase maps a substring of a raw EDI940_Raw.ErrorMessage
    # (SQL Server's ERROR_MESSAGE(), set by ParseEDI940RawByFile's CATCH
    # block) to a plain-English explanation and remediation step, so the
    # chat can go beyond repeating the bare SQL error text back at the user.
    if not error_message:
        return None
    match = rows_params(
        "SELECT TOP 1 Explanation, RemediationStep FROM dbo.ErrorKnowledgeBase WHERE ? LIKE '%' + ErrorPattern + '%'",
        (error_message,),
    )
    if not match:
        return None
    explanation = match[0]["Explanation"]
    remediation = match[0].get("RemediationStep")
    return f"{explanation} {remediation}" if remediation else explanation


def describe_file_status(file_row: dict) -> str:
    status = file_row.get("processStatus")
    loaded = file_row.get("loadDateTime") or "an unknown time"
    if status == "PARSED":
        return f"File {file_row['fileName']} (ISA {file_row.get('isaControlNumber')}) was received and parsed successfully at {loaded}."
    if status == "PARSE_FAILED":
        error = file_row.get("errorMessage") or "no error message was recorded"
        note = explain_error(file_row.get("errorMessage"))
        suffix = f" ({note})" if note else ""
        return f"File {file_row['fileName']} (ISA {file_row.get('isaControlNumber')}) was received at {loaded} but failed to parse: {error}{suffix}"
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


def resolve_customer_alias(term: str) -> str:
    # dbo.CustomerAliases maps free-text names ("Lowes", "Lowe's") to the
    # canonical ISASender code ("LOW"). SQL Server's default collation is
    # already case-insensitive, so this only needs to handle genuinely
    # different spellings, not case. Falls back to the term as-typed when
    # there's no alias row, so an already-correct code still works.
    match = rows_params(
        "SELECT TOP 1 CustomerCode FROM dbo.CustomerAliases WHERE Alias = ?",
        (term.strip(),),
    )
    return match[0]["CustomerCode"] if match else term


def handle_failed_orders(customer: Optional[str] = None) -> dict:
    if customer:
        customer = resolve_customer_alias(customer)

    # loadDateTime is included so date-scoped questions ("today", "yesterday")
    # can be answered by the model reasoning over these rows -- no separate
    # date param/query needed for that.
    base_query = """
        SELECT TOP 20
            FileName AS fileName,
            ISASender AS sender,
            ProcessStatus AS processStatus,
            ErrorMessage AS errorMessage,
            CONVERT(varchar(19), LoadDateTime, 120) AS loadDateTime
        FROM dbo.EDI940_Raw
        WHERE ProcessStatus = 'PARSE_FAILED'{customer_filter}
        ORDER BY RawId DESC
    """
    if customer:
        failed_rows = rows_params(
            base_query.format(customer_filter=" AND ISASender = ?"),
            (customer,),
        )
    else:
        failed_rows = rows(base_query.format(customer_filter=""))

    if not failed_rows:
        scope = f" for customer {customer}" if customer else ""
        return {"intent": "failed_orders", "reply": f"No failed files{scope} in the EDI intake right now.", "matches": []}

    def describe_failure(r: dict) -> str:
        error = r.get("errorMessage") or "no error message recorded"
        note = explain_error(r.get("errorMessage"))
        suffix = f" ({note})" if note else ""
        return f"- {r['fileName']} ({r['sender']}, {r['loadDateTime']}): {error}{suffix}"

    lines = [describe_failure(r) for r in failed_rows]
    reply = f"There are {len(failed_rows)} failed file(s):\n" + "\n".join(lines)
    return {"intent": "failed_orders", "reply": reply, "matches": failed_rows}


def build_unknown_reply() -> str:
    latest_failed = get_latest_failed_isa()
    example_isa = latest_failed or "000012345"
    return f'Try asking "Why did ISA {example_isa} fail?" or "Where is PO 12345?"'


# All file-download handlers return {"downloads": [{"fileName", "downloadUrl"}, ...]}
# (possibly empty) so the chat response shape is the same whether one file or
# several come back. Only ever reachable when the caller has the
# files.download permission - see detect_file_download_handler()/chat() below.

def handle_file_download_by_filename(file_name: str) -> dict:
    try:
        download = resolve_file_download(file_name)
    except HTTPException as exc:
        return {"intent": "file_download", "reply": exc.detail, "matches": [], "downloads": []}

    return {
        "intent": "file_download",
        "reply": f"Here's the download link for {download['fileName']} (expires in about 10 minutes).",
        "matches": [],
        "downloads": [{"fileName": download["fileName"], "downloadUrl": download["downloadUrl"]}],
    }


def handle_file_download_by_isa(isa_number: str) -> dict:
    isa_result = handle_isa_lookup(isa_number)
    if not isa_result.get("matches"):
        return {"intent": "file_download", "reply": isa_result["reply"], "matches": [], "downloads": []}
    return handle_file_download_by_filename(isa_result["matches"][0]["fileName"])


# Caps at 5 files so a busy failure queue doesn't generate dozens of SAS
# tokens (and a huge chat response) from one request.
MAX_BULK_FILE_DOWNLOADS = 5


def handle_failed_file_downloads(customer: Optional[str] = None) -> dict:
    if customer:
        customer = resolve_customer_alias(customer)
    failed = handle_failed_orders(customer)
    if not failed.get("matches"):
        return {"intent": "file_download", "reply": failed["reply"], "matches": [], "downloads": []}

    downloads = []
    for row in failed["matches"][:MAX_BULK_FILE_DOWNLOADS]:
        try:
            download = resolve_file_download(row["fileName"])
            downloads.append({"fileName": download["fileName"], "downloadUrl": download["downloadUrl"]})
        except HTTPException:
            continue

    if not downloads:
        return {
            "intent": "file_download",
            "reply": "Found failed files, but none of them are still available in blob storage.",
            "matches": [],
            "downloads": [],
        }

    return {
        "intent": "file_download",
        "reply": f"Here are download links for {len(downloads)} failed file(s):",
        "matches": [],
        "downloads": downloads,
    }


def detect_file_download_handler(question: str):
    if not FILE_REQUEST_INTENT_PATTERN.search(question):
        return None

    filename_match = FILENAME_PATTERN.search(question)
    if filename_match:
        return lambda: handle_file_download_by_filename(filename_match.group(1))

    if ERROR_FILES_PATTERN.search(question):
        customer_match = CUSTOMER_PATTERN.search(question)
        customer = customer_match.group(1).strip() if customer_match else None
        return lambda: handle_failed_file_downloads(customer)

    isa_match = ISA_PATTERN.search(question)
    if isa_match:
        return lambda: handle_file_download_by_isa(isa_match.group(1).strip())

    return None


# ---------------------------------------------------------------------------
# Phase 2 chat: AI fallback, three tiers. When the regex patterns above don't
# match: (1) try the self-hosted local model first (free -- an OpenAI-
# compatible vLLM server on the home tailnet, reached over the tailscale
# sidecar's SOCKS5 proxy in this deployment), (2) fall back to Claude if the
# local model is unset, offline, or errors. Both tiers get the same fixed set
# of tools (the same lookup functions used by the regex path, plus
# list_failed_orders) -- the model only ever picks a tool and supplies its
# arguments, it never sees or writes SQL, so the backend stays in full control
# of what gets queried.
# ---------------------------------------------------------------------------

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
_anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

AI_SYSTEM_PROMPT = (
    "You are an assistant for a warehouse EDI operations dashboard. Use the available tools "
    "to answer questions about a specific PO/order's status, a specific ISA file's status, or "
    "the current list of EDI files that failed to parse. Only call a tool when the question is "
    "clearly about one of those topics. If you call a tool, use the exact input schema specified "
    "for that tool and do not make up any other fields. Otherwise, reply directly and briefly "
    "explaining you can only help with the topics covered by your available tools."
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
        "description": (
            "List EDI files that failed to parse (ProcessStatus = PARSE_FAILED), most recent first. "
            "Each result includes the sender/customer code and load date, so date-scoped questions "
            "(e.g. 'today', 'yesterday') can be answered by filtering these results yourself -- there's "
            "no separate date parameter."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer": {
                    "type": "string",
                    "description": "ISA sender/customer code or common customer name to filter to (e.g. 'LOW' or 'Lowes' -- known aliases are resolved automatically). Omit to list failures across all customers.",
                }
            },
        },
    },
]

# CR-025: recent disliked chat responses are folded into the AI-tier system
# prompt so future replies can steer away from whatever the comment flagged.
# Only rows with a comment are useful here -- a bare thumbs-down with no
# comment gives the model nothing actionable to change.
CHAT_FEEDBACK_CONTEXT_LIMIT = 5


def get_recent_negative_feedback(limit: int = CHAT_FEEDBACK_CONTEXT_LIMIT) -> list[dict]:
    return rows_params(
        """
        SELECT TOP (?) QuestionText, ResponseText, Comment
        FROM dbo.ChatFeedback
        WHERE Rating = -1
        ORDER BY CreatedDateTime DESC
        """,
        (limit,),
    )


def build_feedback_context() -> str:
    try:
        negative = get_recent_negative_feedback()
    except Exception as exc:
        # Best-effort only -- a feedback-table hiccup shouldn't take down chat.
        print(f"[chat] failed to load recent feedback context: {exc}")
        return ""

    lines = [
        f'- A user disliked a past reply to "{row["QuestionText"]}" because: "{(row.get("Comment") or "").strip()}"'
        for row in negative
        if (row.get("Comment") or "").strip()
    ]
    if not lines:
        return ""

    return (
        "\n\nRecent user feedback on past responses -- take this into account and avoid "
        "repeating the same mistakes:\n" + "\n".join(lines)
    )


AI_TOOL_DISPATCH = {
    "lookup_po": lambda tool_input: handle_po_lookup(tool_input["po_number"]),
    "lookup_isa": lambda tool_input: handle_isa_lookup(tool_input["isa_number"]),
    "list_failed_orders": lambda tool_input: handle_failed_orders(tool_input.get("customer")),
}

# Added to a chat request's tools/dispatch only when the caller has the
# files.download permission - see chat(). Kept out of AI_TOOLS/AI_TOOL_DISPATCH
# so non-admin callers never even have this tool offered to Claude.
#
# Accepts either file_name or isa_number because the conversation history the
# model sees often only has one of the two -- e.g. handle_failed_orders()'s
# reply text lists file names but never surfaces an ISA control number, so a
# follow-up like "give me that file" (referring to an earlier failed-files
# list) has nothing to extract an isa_number from. Mirrors the two lookup
# paths detect_file_download_handler() already supports on the regex path.
FILE_DOWNLOAD_TOOL = {
    "name": "get_file_download_link",
    "description": (
        "Get a temporary download link for the original EDI file. Provide file_name if the exact "
        "file name is known (e.g. from an earlier list of files in this conversation), otherwise "
        "provide isa_number. Only call this if the user explicitly asks to download, retrieve, or "
        "get a copy of the file itself, not just its status."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "file_name": {"type": "string", "description": "The exact EDI file name, if known."},
            "isa_number": {"type": "string", "description": "The ISA control number, if the file name isn't known."},
        },
    },
}


def dispatch_file_download(tool_input: dict) -> dict:
    file_name = tool_input.get("file_name")
    if file_name:
        return handle_file_download_by_filename(file_name)

    isa_number = tool_input.get("isa_number")
    if isa_number:
        return handle_file_download_by_isa(isa_number)

    return {
        "intent": "file_download",
        "reply": "I need either the file name or the ISA control number to find that file.",
        "matches": [],
        "downloads": [],
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


def handle_ai_fallback(
    question: str, tools: list, dispatch: dict, feedback_context: str = "", history: Optional[list] = None
) -> Optional[dict]:
    if not _anthropic_client:
        return None

    system_prompt = AI_SYSTEM_PROMPT + feedback_context

    try:
        messages = [*(history or []), {"role": "user", "content": question}]
        response = _anthropic_client.messages.create(
            model="claude-sonnet-5",
            max_tokens=400,
            system=system_prompt,
            tools=tools,
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

        tool_fn = dispatch.get(tool_use.name)
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
            system=system_prompt,
            tools=tools,
            messages=messages,
        )
        final_text = "".join(block.text for block in final.content if block.type == "text")

        result = {
            "intent": f"ai_{tool_use.name}",
            "reply": final_text or tool_result.get("reply", ""),
            "matches": tool_result.get("matches", []),
            "source": "ai",
        }
        if "downloads" in tool_result:
            result["downloads"] = tool_result["downloads"]
        return result
    except Exception as exc:
        # Don't leak exception details (e.g. a billing/quota error) to the chat UI -
        # degrade to the same message the regex path gives when it can't help.
        print(f"[chat] AI fallback error: {exc}")
        return {"intent": "ai_error", "reply": build_unknown_reply(), "matches": [], "source": "regex"}


# LOCAL_MODEL_BASE_URL is intentionally unset by default (not the raw
# tailscale IP) so deployments without a tailscale sidecar -- or without
# LOCAL_MODEL_BASE_URL configured -- skip this tier outright instead of
# stalling on a request to a host they have no route to. LOCAL_MODEL_PROXY is
# only set in the deployment that has the tailscale sidecar (socks5h://
# localhost:1055); local dev, which already runs tailscale on the host
# machine, sets LOCAL_MODEL_BASE_URL to the tailnet IP directly with no proxy.
LOCAL_MODEL_BASE_URL = os.getenv("LOCAL_MODEL_BASE_URL")
LOCAL_MODEL_NAME = os.getenv("LOCAL_MODEL_NAME", "Qwen/Qwen2.5-3B-Instruct")
LOCAL_MODEL_PROXY = os.getenv("LOCAL_MODEL_SOCKS5_PROXY")
LOCAL_MODEL_TIMEOUT_SECONDS = (3, 7)  # (connect, read) -- fail fast to Claude rather than making the user wait on a slow local response; well under gunicorn's --timeout (90s)


def _openai_style_tools(tools: list) -> list:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        }
        for tool in tools
    ]


def _local_model_request(messages: list, tools: list, max_tokens: int):
    return requests.post(
        f"{LOCAL_MODEL_BASE_URL.rstrip('/')}/chat/completions",
        proxies={"http": LOCAL_MODEL_PROXY, "https": LOCAL_MODEL_PROXY} if LOCAL_MODEL_PROXY else None,
        timeout=LOCAL_MODEL_TIMEOUT_SECONDS,
        json={
            "model": LOCAL_MODEL_NAME,
            "messages": messages,
            "tools": _openai_style_tools(tools),
            "max_tokens": max_tokens,
        },
    )


def handle_local_model_fallback(
    question: str, tools: list, dispatch: dict, feedback_context: str = "", history: Optional[list] = None
) -> Optional[dict]:
    """Tries the self-hosted local model via its OpenAI-compatible /chat/completions
    endpoint. Returns None on any failure (unconfigured, offline, timeout, malformed
    response) so the caller falls through to the next tier (Claude) -- never raises."""
    if not LOCAL_MODEL_BASE_URL:
        return None

    try:
        messages = [
            {"role": "system", "content": AI_SYSTEM_PROMPT + feedback_context},
            *(history or []),
            {"role": "user", "content": question},
        ]
        response = _local_model_request(messages, tools, max_tokens=400)
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            content = message.get("content") or ""
            if "<tool_call>" in content:
                # The local model's chat template attempted a tool call but the
                # vLLM server didn't parse it into the structured tool_calls
                # field -- content is raw <tool_call>{...}</tool_call> markup
                # (sometimes several, plus hallucinated prose/fake links after
                # it). Never surface this to a user; fall through to Claude.
                print("[chat] local model leaked raw <tool_call> text instead of a structured tool call; falling back to Claude")
                return None
            return {
                "intent": "ai_unhandled",
                "reply": content or build_unknown_reply(),
                "matches": [],
                "source": "local_ai",
            }

        tool_call = tool_calls[0]
        call = tool_call["function"]
        tool_fn = dispatch.get(call["name"])
        if not tool_fn:
            return {"intent": "ai_unhandled", "reply": build_unknown_reply(), "matches": [], "source": "local_ai"}

        tool_result = tool_fn(json.loads(call["arguments"] or "{}"))
        result = {
            "intent": f"ai_{call['name']}",
            "reply": tool_result.get("reply", ""),
            "matches": tool_result.get("matches", []),
            "source": "local_ai",
        }
        if "downloads" in tool_result:
            result["downloads"] = tool_result["downloads"]

        # Second round trip: hand the tool result back to the model to phrase
        # a natural reply, matching how the Claude tier works (see
        # handle_ai_fallback). Best-effort only -- any failure here just
        # keeps the raw tool_result reply set above rather than falling all
        # the way back to Claude, so a slow/flaky local model still answers
        # quickly instead of doubling the worst-case wait for nothing.
        try:
            messages.append({"role": "assistant", "content": message.get("content"), "tool_calls": [tool_call]})
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": json.dumps(tool_result),
            })
            final = _local_model_request(messages, tools, max_tokens=300)
            final.raise_for_status()
            final_text = final.json()["choices"][0]["message"].get("content")
            if final_text:
                result["reply"] = final_text
        except Exception as exc:
            print(f"[chat] local model final-reply round trip failed (using raw tool reply): {exc}")

        return result
    except Exception as exc:
        # Local model unreachable/offline/misbehaving -- degrade silently to
        # the Claude tier rather than surfacing this to the chat UI.
        print(f"[chat] local model fallback error (falling back to Claude): {exc}")
        return None


@app.get("/api/chat/sample-isa")
def sample_isa(_: dict = Depends(require_auth)):
    return {"isaControlNumber": get_latest_failed_isa()}


@app.post("/api/chat")
def chat(request: ChatRequest, http_request: Request, payload: dict = Depends(require_auth)):
    question = request.question or ""

    # Checked first, entirely separate from the ISA/PO status-lookup regexes
    # below - it only fires on explicit file-request phrasing, so plain
    # status questions are unaffected and keep flowing through unchanged.
    file_download_handler = detect_file_download_handler(question)
    if file_download_handler:
        if "files.download" not in get_user_permissions(get_user_oid(payload)):
            return {
                "intent": "file_download_denied",
                "reply": "You don't have permission to download files yet. Try the demo admin toggle first.",
                "matches": [],
                "source": "regex",
            }
        return {**file_download_handler(), "source": "regex"}

    isa_match = ISA_PATTERN.search(question)
    if isa_match:
        return {**handle_isa_lookup(isa_match.group(1).strip()), "source": "regex"}

    po_match = PO_PATTERN.search(question)
    if po_match:
        return {**handle_po_lookup(po_match.group(1).strip()), "source": "regex"}

    tools = list(AI_TOOLS)
    dispatch = dict(AI_TOOL_DISPATCH)
    if "files.download" in get_user_permissions(get_user_oid(payload)):
        tools.append(FILE_DOWNLOAD_TOOL)
        dispatch["get_file_download_link"] = dispatch_file_download

    # CR-025: recent disliked-response comments, folded into both AI tiers'
    # system prompt below so future replies can steer away from them.
    feedback_context = build_feedback_context()

    # Last few turns of the conversation so far, so a short follow-up like
    # "yes" to "Want a download link?" has something to resolve against
    # instead of landing as a brand-new, context-free question.
    history = sanitize_chat_history(request.history)

    # Tier 2: local model. Unrate-limited (it's free, self-hosted) and tried
    # before Claude regardless of ANTHROPIC_API_KEY -- handle_local_model_fallback
    # itself is a no-op (returns None) when LOCAL_MODEL_BASE_URL isn't set.
    local_result = handle_local_model_fallback(question, tools, dispatch, feedback_context, history)
    if local_result:
        return local_result

    # Tier 3: Claude, only reached when the local model is unconfigured or
    # unreachable.
    if not _anthropic_client:
        return {"intent": "unknown", "reply": build_unknown_reply(), "matches": [], "source": "regex"}

    if is_ai_rate_limited(get_client_ip(http_request)):
        return {"intent": "ai_rate_limited", "reply": build_unknown_reply(), "matches": [], "source": "regex"}

    ai_result = handle_ai_fallback(question, tools, dispatch, feedback_context, history)
    if ai_result:
        return ai_result

    return {"intent": "unknown", "reply": build_unknown_reply(), "matches": [], "source": "regex"}


@app.post("/api/chat/feedback")
def submit_chat_feedback(request: ChatFeedbackRequest, payload: dict = Depends(require_auth)):
    if request.rating not in (1, -1):
        raise HTTPException(status_code=400, detail="rating must be 1 (helpful) or -1 (not helpful)")

    question = (request.question or "").strip()
    reply = (request.reply or "").strip()
    if not question or not reply:
        raise HTTPException(status_code=400, detail="question and reply are required")

    comment = (request.comment or "").strip() or None
    if comment and len(comment) > CHAT_FEEDBACK_COMMENT_MAX_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"comment must be {CHAT_FEEDBACK_COMMENT_MAX_LENGTH} characters or fewer",
        )

    channel = request.channel if request.channel in CHAT_FEEDBACK_CHANNELS else "support"
    source = request.source or "unknown"
    message_hash = hashlib.sha256(f"{question}\x1f{reply}".encode("utf-8")).hexdigest()
    user_oid = get_user_oid(payload)

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO dbo.ChatFeedback
                (UserOid, MessageHash, Channel, Source, QuestionText, ResponseText, Rating, Comment)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_oid, message_hash, channel, source, question, reply, request.rating, comment),
        )
        conn.commit()

    return {"status": "ok"}
