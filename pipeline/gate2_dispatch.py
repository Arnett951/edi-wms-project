"""
Runs inside GitHub Actions (.github/workflows/cr-gate2-dispatch.yml), triggered
by a workflow_dispatch call from the deployed API when it has no local git
repo of its own (a zip-deployed Azure App Service). The actual merge/revert
git operations happen here, on GitHub's runner using the Actions-provided
token -- the App Service itself never holds push credentials.

CR data (status, branch, merge commit) lives in dbo.ChangeRequests, so this
runner needs SQL_SERVER/SQL_DATABASE/SQL_USER/SQL_PASSWORD as GitHub Secrets,
and Azure SQL's firewall needs to allow GitHub-hosted runners (their IPs are
dynamic -- "Allow Azure services" does NOT cover this; a broader firewall
rule or a self-hosted runner is needed).

Mirrors api/main.py's merge_change_request/rollback_change_request exactly,
as a standalone script rather than an HTTP endpoint. Only the CODE change
gets committed/pushed here -- the CR's own status lives in SQL now, not a
git-tracked file, so there's no second "record status" commit needed.

Usage (inside the workflow):
    python pipeline/gate2_dispatch.py merge 4 --approver "chris arnett"
    python pipeline/gate2_dispatch.py rollback 4 --approver "chris arnett"
"""

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
import change_request_lib as cr_lib  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_git(args, cwd=REPO_ROOT):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        print(f"git {' '.join(args)} failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def do_merge(conn, cr_number: int, approver: str, timestamp: str):
    cr = cr_lib.get_cr(conn, cr_number)
    if not cr:
        print(f"CR-{cr_number:03d} not found.", file=sys.stderr)
        sys.exit(1)
    if not cr["status"].startswith("Implemented"):
        print(f"CR-{cr_number:03d} is not ready to merge (status: '{cr['status']}').", file=sys.stderr)
        sys.exit(1)
    branch = cr["branch"]
    if not branch:
        print(f"CR-{cr_number:03d} has no recorded Branch.", file=sys.stderr)
        sys.exit(1)

    run_git(["fetch", "origin"])
    run_git(["checkout", "main"])
    run_git(["pull", "origin", "main"])

    merge_result = subprocess.run(
        ["git", "merge", f"origin/{branch}", "--no-ff", "-m", f"Merge CR-{cr_number:03d}: {cr['title']}"],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8",
    )
    if merge_result.returncode != 0:
        subprocess.run(["git", "merge", "--abort"], cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8")
        print(f"Merge conflict merging origin/{branch} into main:\n{merge_result.stderr}", file=sys.stderr)
        sys.exit(1)

    run_git(["push", "origin", "main"])
    merge_commit = run_git(["rev-parse", "HEAD"])

    cr_lib.set_fields(conn, cr_number, mergeCommit=merge_commit)
    cr_lib.update_status(conn, cr_number, f"Merged (Gate 2) by {approver} on {timestamp} [via GitHub Actions]")
    print(f"CR-{cr_number:03d} merged: {merge_commit}")


def do_rollback(conn, cr_number: int, approver: str, timestamp: str):
    cr = cr_lib.get_cr(conn, cr_number)
    if not cr:
        print(f"CR-{cr_number:03d} not found.", file=sys.stderr)
        sys.exit(1)
    if not cr["status"].startswith("Merged"):
        print(f"CR-{cr_number:03d} has not been merged -- nothing to roll back.", file=sys.stderr)
        sys.exit(1)
    merge_commit = cr["mergeCommit"]
    if not merge_commit:
        print(f"CR-{cr_number:03d} has no recorded merge commit.", file=sys.stderr)
        sys.exit(1)

    run_git(["fetch", "origin"])
    run_git(["checkout", "main"])
    run_git(["pull", "origin", "main"])

    revert_result = subprocess.run(
        ["git", "revert", merge_commit, "-m", "1", "--no-edit"],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8",
    )
    if revert_result.returncode != 0:
        subprocess.run(["git", "revert", "--abort"], cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8")
        print(f"Revert conflict on {merge_commit}:\n{revert_result.stderr}", file=sys.stderr)
        sys.exit(1)

    run_git(["push", "origin", "main"])
    revert_commit = run_git(["rev-parse", "HEAD"])

    cr_lib.set_fields(conn, cr_number, rollbackCommit=revert_commit)
    cr_lib.update_status(conn, cr_number, f"Rolled back (Gate 2) by {approver} on {timestamp} [via GitHub Actions]")
    print(f"CR-{cr_number:03d} rolled back: {revert_commit}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["merge", "rollback"])
    parser.add_argument("cr_number", type=int)
    parser.add_argument("--approver", default="GitHub Actions")
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / "api" / ".env")
    conn = cr_lib.get_conn()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if args.action == "merge":
        do_merge(conn, args.cr_number, args.approver, timestamp)
    else:
        do_rollback(conn, args.cr_number, args.approver, timestamp)
    conn.close()


if __name__ == "__main__":
    main()
