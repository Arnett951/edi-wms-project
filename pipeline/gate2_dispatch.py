"""
Runs inside GitHub Actions (.github/workflows/cr-gate2-dispatch.yml), triggered
by a workflow_dispatch call from the deployed API when it has no local git
repo of its own (a zip-deployed Azure App Service). The actual merge/revert
git operations happen here, on GitHub's runner using the Actions-provided
token -- the App Service itself never holds push credentials.

Mirrors api/main.py's merge_change_request/rollback_change_request exactly,
as a standalone script rather than an HTTP endpoint.

Usage (inside the workflow):
    python pipeline/gate2_dispatch.py merge 4 --approver "chris arnett"
    python pipeline/gate2_dispatch.py rollback 4 --approver "chris arnett"
"""

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
import change_request_lib as cr_lib  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGE_REQUESTS_DIR = REPO_ROOT / "api" / "change-requests"


def run_git(args, cwd=REPO_ROOT):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        print(f"git {' '.join(args)} failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def get_title(text: str, cr_number: int) -> str:
    first_line = text.splitlines()[0]
    return first_line.split(":", 1)[1].strip() if ":" in first_line else f"CR-{cr_number:03d}"


def do_merge(cr_number: int, approver: str, timestamp: str):
    request_file = CHANGE_REQUESTS_DIR / f"CR-{cr_number:03d}" / "request.md"
    text = request_file.read_text(encoding="utf-8")

    status = cr_lib.get_status(text)
    if not status.startswith("Implemented"):
        print(f"CR-{cr_number:03d} is not ready to merge (status: '{status}').", file=sys.stderr)
        sys.exit(1)
    branch = cr_lib.get_field(text, "Branch")
    if not branch:
        print(f"CR-{cr_number:03d} has no recorded Branch.", file=sys.stderr)
        sys.exit(1)
    title = get_title(text, cr_number)

    run_git(["fetch", "origin"])
    run_git(["checkout", "main"])
    run_git(["pull", "origin", "main"])

    merge_result = subprocess.run(
        ["git", "merge", f"origin/{branch}", "--no-ff", "-m", f"Merge CR-{cr_number:03d}: {title}"],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8",
    )
    if merge_result.returncode != 0:
        subprocess.run(["git", "merge", "--abort"], cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8")
        print(f"Merge conflict merging origin/{branch} into main:\n{merge_result.stderr}", file=sys.stderr)
        sys.exit(1)

    merge_commit = run_git(["rev-parse", "HEAD"])
    updated_text = cr_lib.set_field(text, "Merge commit", merge_commit)
    updated_text = cr_lib.update_status(
        updated_text, f"Merged (Gate 2) by {approver} on {timestamp} [via GitHub Actions]"
    )
    request_file.write_text(updated_text, encoding="utf-8")

    run_git(["add", str(request_file)])
    run_git(["commit", "-m", f"CR-{cr_number:03d}: record Gate 2 merge status"])
    run_git(["push", "origin", "main"])
    print(f"CR-{cr_number:03d} merged: {merge_commit}")


def do_rollback(cr_number: int, approver: str, timestamp: str):
    request_file = CHANGE_REQUESTS_DIR / f"CR-{cr_number:03d}" / "request.md"
    text = request_file.read_text(encoding="utf-8")

    status = cr_lib.get_status(text)
    if not status.startswith("Merged"):
        print(f"CR-{cr_number:03d} has not been merged -- nothing to roll back.", file=sys.stderr)
        sys.exit(1)
    merge_commit = cr_lib.get_field(text, "Merge commit")
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

    revert_commit = run_git(["rev-parse", "HEAD"])
    updated_text = cr_lib.set_field(text, "Rollback commit", revert_commit)
    updated_text = cr_lib.update_status(
        updated_text, f"Rolled back (Gate 2) by {approver} on {timestamp} [via GitHub Actions]"
    )
    request_file.write_text(updated_text, encoding="utf-8")

    run_git(["add", str(request_file)])
    run_git(["commit", "-m", f"CR-{cr_number:03d}: record Gate 2 rollback status"])
    run_git(["push", "origin", "main"])
    print(f"CR-{cr_number:03d} rolled back: {revert_commit}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["merge", "rollback"])
    parser.add_argument("cr_number", type=int)
    parser.add_argument("--approver", default="GitHub Actions")
    args = parser.parse_args()

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if args.action == "merge":
        do_merge(args.cr_number, args.approver, timestamp)
    else:
        do_rollback(args.cr_number, args.approver, timestamp)


if __name__ == "__main__":
    main()
