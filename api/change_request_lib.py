"""
Shared logic for the change-request intake pipeline, used by both the local
CLI (pipeline/generate_change_request.py, implement_change_request.py,
gate2_dispatch.py) and the live API endpoints (api/main.py) so none of them
drift apart.

CRs live in dbo.ChangeRequests (Azure SQL), not markdown files -- files on a
zip-deployed Azure App Service get wiped on every redeploy, and a shared SQL
table also means local dev and the deployed API read/write the exact same
data instead of two separate disks. Every function that touches storage
takes a `conn` (a pyodbc connection) rather than opening its own; callers own
the connection lifecycle via get_conn() below.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pyodbc
import yaml

# Shared status literals -- both api/main.py (Gate 1/Build endpoints) and
# pipeline/implement_change_request.py (resets a failed build back to Pending
# Build Approval) need these to match exactly, so they live here once rather
# than as separately-typed string literals that could drift apart.
PENDING_STATUS = "Pending Gate 1 review"
PENDING_BUILD_STATUS = "Pending Build Approval"

DEFAULT_CONFIG = {
    "project_name": "Unnamed project",
    "stack_summary": "Unknown stack -- describe your project in .change-pipeline.yml",
    "tiers": {
        "A": {"label": "In scope", "examples": []},
        "B": {"label": "Semi-automated", "examples": []},
        "C": {"label": "Excluded -- handle manually", "examples": []},
    },
    "cost": {
        "reference_monthly_budget_usd": 20,
        "blended_rate_per_million_tokens_usd": 6.0,
    },
}


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        return DEFAULT_CONFIG
    with open(config_path, "r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    merged = {**DEFAULT_CONFIG, **loaded}
    merged["cost"] = {**DEFAULT_CONFIG["cost"], **loaded.get("cost", {})}
    merged["tiers"] = loaded.get("tiers", DEFAULT_CONFIG["tiers"])
    return merged


def build_system_prompt(config: dict) -> str:
    tier_lines = []
    for key, tier in config["tiers"].items():
        examples = "; ".join(tier.get("examples", [])) or "(no examples configured)"
        tier_lines.append(f"  {key} ({tier.get('label', '')}): {examples}")
    tier_block = "\n".join(tier_lines)

    return f"""You are the intake stage of a change-management pipeline for this project:

Project: {config['project_name']}
Stack: {config['stack_summary']}

A person will describe a feature, report, dashboard change, or integration they
want. Your job has two parts:

1. Ask clarifying questions ONE AT A TIME if the request is ambiguous or is
   missing details you'd need to scope it (what data, which page/screen, what
   fields, any constraints). Prefix each such question with exactly "QUESTION:"
   on its own line, nothing else in the message. Ask at most a few questions --
   don't interrogate for details that don't change the scope.

2. Once you have enough information, respond with ONLY a fenced ```json code
   block (no other text before or after it) containing exactly these keys:

   - "title": short string
   - "tier": one of "A", "B", "C" based on this project's tier rules below
   - "risk_notes": string explaining the tier choice if B or C, else ""
   - "requirements": array of short requirement strings
   - "touch_points": array of files/tables/systems this will likely touch
   - "out_of_scope": array of things explicitly NOT covered by this request
   - "estimated_tokens": integer, your best-effort estimate of total tokens
     (planning + implementation + testing) needed to build this end to end --
     ALWAYS a realistic non-zero estimate, even for Tier C. A Tier C request
     still needs this number for future roadmap sizing if it's ever picked up
     manually; "it won't be automated" is not a reason to write 0.

Tier rules for this project:
{tier_block}

If the request clearly belongs to Tier C, still produce the JSON (with tier
"C" and risk_notes explaining why) rather than refusing -- the pipeline itself
decides what happens with a Tier C request, not you. The impact analysis and
token estimate you already did to reach that conclusion should still be
reported, not discarded."""


def extract_json_block(text: str):
    import re
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def compute_cost(estimated_tokens: int, config: dict):
    rate = config["cost"]["blended_rate_per_million_tokens_usd"]
    budget = config["cost"]["reference_monthly_budget_usd"]
    dollars = (estimated_tokens / 1_000_000) * rate
    ratio_pct = (dollars / budget) * 100
    return dollars, ratio_pct


# ---------------------------------------------------------------------------
# Database access
# ---------------------------------------------------------------------------

def escape_odbc(value):
    value = (value or "").strip()
    return "{" + value.replace("}", "}}") + "}"


def get_conn():
    import os
    server = (os.getenv("SQL_SERVER") or "").strip()
    database = (os.getenv("SQL_DATABASE") or "").strip()
    user = (os.getenv("SQL_USER") or "").strip()
    password_raw = os.getenv("SQL_PASSWORD")

    missing = [
        name for name, value in {
            "SQL_SERVER": server, "SQL_DATABASE": database, "SQL_USER": user, "SQL_PASSWORD": password_raw,
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


CR_COLUMNS = [
    "CRNumber", "Title", "Tier", "TierLabel", "Status", "OriginalRequest", "ClarificationJson",
    "RiskNotes", "RequirementsJson", "TouchPointsJson", "OutOfScopeJson",
    "EstimatedTokens", "EstimatedCostUsd", "CostRatioPct",
    "Branch", "MergeReadiness", "MergeCommit", "RollbackCommit", "ImplementationSummary",
    "SessionId", "ProgressStatus", "TokensSoFar", "LastAction", "ActualCostUsd",
    "CreatedDateTime", "UpdatedDateTime",
]


def _to_cr_dict(row) -> dict:
    raw = dict(zip(CR_COLUMNS, row))
    return {
        "crNumber": raw["CRNumber"],
        "title": raw["Title"],
        "tier": raw["Tier"],
        "tierLabel": raw["TierLabel"],
        "status": raw["Status"],
        "originalRequest": raw["OriginalRequest"],
        "clarification": json.loads(raw["ClarificationJson"]) if raw["ClarificationJson"] else [],
        "riskNotes": raw["RiskNotes"] or "",
        "requirements": json.loads(raw["RequirementsJson"]) if raw["RequirementsJson"] else [],
        "touchPoints": json.loads(raw["TouchPointsJson"]) if raw["TouchPointsJson"] else [],
        "outOfScope": json.loads(raw["OutOfScopeJson"]) if raw["OutOfScopeJson"] else [],
        "estimatedTokens": raw["EstimatedTokens"],
        "estimatedCost": round(float(raw["EstimatedCostUsd"]), 2) if raw["EstimatedCostUsd"] is not None else None,
        "costRatioPct": round(float(raw["CostRatioPct"]), 1) if raw["CostRatioPct"] is not None else None,
        "branch": raw["Branch"],
        "mergeReadiness": raw["MergeReadiness"],
        "mergeCommit": raw["MergeCommit"],
        "rollbackCommit": raw["RollbackCommit"],
        "implementationSummary": raw["ImplementationSummary"],
        "sessionId": raw["SessionId"],
        "tokensSoFar": raw["TokensSoFar"],
        "lastAction": raw["LastAction"],
        "actualCostUsd": round(float(raw["ActualCostUsd"]), 4) if raw["ActualCostUsd"] is not None else None,
    }


def next_cr_number(conn) -> int:
    cur = conn.cursor()
    cur.execute("SELECT ISNULL(MAX(CRNumber), 0) + 1 FROM dbo.ChangeRequests")
    return cur.fetchone()[0]


def create_cr(conn, cr_number: int, original_request: str, transcript: list, cr_data: dict,
              dollars: float, ratio_pct: float, config: dict) -> dict:
    tier = cr_data.get("tier", "?")
    tier_label = config["tiers"].get(tier, {}).get("label", "")
    status = "Auto-denied -- Tier C, handle manually" if tier == "C" else PENDING_STATUS

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO dbo.ChangeRequests
            (CRNumber, Title, Tier, TierLabel, Status, OriginalRequest, ClarificationJson,
             RiskNotes, RequirementsJson, TouchPointsJson, OutOfScopeJson,
             EstimatedTokens, EstimatedCostUsd, CostRatioPct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        cr_number, cr_data.get("title", "(untitled)"), tier, tier_label, status, original_request,
        json.dumps([{"question": q, "answer": a} for q, a in transcript]),
        cr_data.get("risk_notes", ""),
        json.dumps(cr_data.get("requirements", [])),
        json.dumps(cr_data.get("touch_points", [])),
        json.dumps(cr_data.get("out_of_scope", [])),
        cr_data.get("estimated_tokens", 0), dollars, ratio_pct,
    )
    conn.commit()
    return get_cr(conn, cr_number)


def get_cr(conn, cr_number: int):
    cur = conn.cursor()
    cur.execute(f"SELECT {', '.join(CR_COLUMNS)} FROM dbo.ChangeRequests WHERE CRNumber = ?", cr_number)
    row = cur.fetchone()
    return _to_cr_dict(row) if row else None


def list_crs(conn) -> list:
    cur = conn.cursor()
    cur.execute(f"SELECT {', '.join(CR_COLUMNS)} FROM dbo.ChangeRequests ORDER BY CRNumber DESC")
    return [_to_cr_dict(row) for row in cur.fetchall()]


def get_status(conn, cr_number: int) -> str:
    cr = get_cr(conn, cr_number)
    return cr["status"] if cr else ""


def update_status(conn, cr_number: int, new_status: str):
    cur = conn.cursor()
    cur.execute(
        "UPDATE dbo.ChangeRequests SET Status = ?, UpdatedDateTime = sysutcdatetime() WHERE CRNumber = ?",
        new_status, cr_number,
    )
    conn.commit()


# Maps the API-friendly field names used elsewhere in the pipeline to actual
# column names, so callers don't need to know the SQL schema by heart.
FIELD_TO_COLUMN = {
    "branch": "Branch",
    "mergeReadiness": "MergeReadiness",
    "mergeCommit": "MergeCommit",
    "rollbackCommit": "RollbackCommit",
    "implementationSummary": "ImplementationSummary",
}


def set_fields(conn, cr_number: int, **fields):
    if not fields:
        return
    columns = [FIELD_TO_COLUMN.get(k, k) for k in fields]
    set_clause = ", ".join(f"{col} = ?" for col in columns)
    params = list(fields.values()) + [cr_number]
    cur = conn.cursor()
    cur.execute(
        f"UPDATE dbo.ChangeRequests SET {set_clause}, UpdatedDateTime = sysutcdatetime() WHERE CRNumber = ?",
        *params,
    )
    conn.commit()


def get_progress(conn, cr_number: int) -> dict:
    cur = conn.cursor()
    cur.execute(
        "SELECT SessionId, ProgressStatus, TokensSoFar, LastAction, ActualCostUsd, UpdatedDateTime "
        "FROM dbo.ChangeRequests WHERE CRNumber = ?",
        cr_number,
    )
    row = cur.fetchone()
    if not row:
        return {"status": "not_started"}
    session_id, status, tokens_so_far, last_action, cost, updated_at = row
    if status is None:
        return {"status": "not_started"}
    return {
        "status": status,
        "sessionId": session_id,
        "tokensSoFar": tokens_so_far,
        "lastAction": last_action,
        "costUsd": float(cost) if cost is not None else None,
        "updatedAt": updated_at.isoformat() if updated_at else None,
    }


def update_progress(conn, cr_number: int, **fields):
    """fields keys: status, sessionId, tokensSoFar, lastAction, costUsd (API names)."""
    column_map = {
        "status": "ProgressStatus", "sessionId": "SessionId", "tokensSoFar": "TokensSoFar",
        "lastAction": "LastAction", "costUsd": "ActualCostUsd",
    }
    set_fields(conn, cr_number, **{column_map[k]: v for k, v in fields.items() if k in column_map})


def cleanup_worktree(repo_root: Path, branch: str):
    """Remove the local worktree (and branch) for a CR that's done -- merged
    or rolled back, so implementation runs don't leave `<repo>-worktrees/`
    growing forever. Best-effort: a leftover worktree isn't worth failing a
    merge/rollback over."""
    worktrees_dir = repo_root.parent / f"{repo_root.name}-worktrees"
    wt_path = worktrees_dir / branch
    if not wt_path.exists():
        return
    subprocess.run(
        ["git", "worktree", "remove", str(wt_path), "--force"],
        cwd=repo_root, capture_output=True, text=True, encoding="utf-8",
    )
    if wt_path.exists():
        shutil.rmtree(wt_path, ignore_errors=True)
    subprocess.run(["git", "worktree", "prune"], cwd=repo_root, capture_output=True, text=True, encoding="utf-8")
    subprocess.run(["git", "branch", "-D", branch], cwd=repo_root, capture_output=True, text=True, encoding="utf-8")


def sweep_merged_worktrees(conn, repo_root: Path):
    """Clean up worktrees for every CR that's already Merged or Rolled back --
    covers merges dispatched remotely via GitHub Actions, where nothing local
    ran at merge time to clean up after itself."""
    worktrees_dir = repo_root.parent / f"{repo_root.name}-worktrees"
    if not worktrees_dir.exists():
        return
    for cr in list_crs(conn):
        branch = cr.get("branch")
        if not branch or not (cr["status"].startswith("Merged") or cr["status"].startswith("Rolled back")):
            continue
        cleanup_worktree(repo_root, branch)
