"""
Phase 2 of the human-governed autonomous delivery pipeline: implementation.
Takes an *already Gate-1-approved* Change Request and hands it to Claude Code
(headless, via `claude -p`) to implement on a new branch, commit, and push --
stopping just short of opening the PR, which is a single manual click via the
compare URL this prints (Gate 3 / code review still happens on a real PR,
not inside this script).

Runs in an isolated `git worktree`, not the caller's own working directory --
otherwise a background run and whatever you're interactively editing at the
same time end up on the same checked-out branch, and unrelated commits get
swept together. CR data and live progress (session id, running token count,
last action) live in dbo.ChangeRequests, not files -- see
api/change_request_lib.py. See ../docs/ai-delivery-pipeline.md for the
design this implements.

Usage:
    python implement_change_request.py 1
    python implement_change_request.py 1 --dry-run     # build the prompt, don't invoke Claude
    python implement_change_request.py 1 --repo /path/to/other/project
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
import change_request_lib as cr_lib  # noqa: E402

# Claude Code's own spend is capped at this multiple of the CR's own
# estimated cost -- a real budget backstop, not just a display number.
MAX_BUDGET_MARGIN_MULTIPLIER = 3
MIN_BUDGET_USD = 1.0

# Scoped on purpose: no WebFetch/WebSearch (nothing to exfiltrate data with),
# and Bash is restricted to the specific command families implementation
# actually needs -- not a bare "Bash" allow.
ALLOWED_TOOLS = (
    "Read Write Edit Glob Grep "
    "Bash(git *) Bash(python *) Bash(pip *) Bash(npm *) Bash(pytest*) Bash(node *)"
)


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:50] or "change"


def format_cr_for_prompt(cr: dict) -> str:
    lines = [f"# CR-{cr['crNumber']:03d}: {cr['title']}", ""]
    lines.append(f"Tier: {cr['tier']} -- {cr['tierLabel']}")
    lines.append("")
    lines.append("## Original request")
    lines.append(f"> {cr['originalRequest']}")
    lines.append("")
    if cr["clarification"]:
        lines.append("## Clarification")
        for qa in cr["clarification"]:
            lines.append(f"- Q: {qa['question']}")
            lines.append(f"  A: {qa['answer']}")
        lines.append("")
    if cr["riskNotes"]:
        lines.append("## Risk notes")
        lines.append(cr["riskNotes"])
        lines.append("")
    lines.append("## Requirements")
    lines.extend(f"- {item}" for item in cr["requirements"])
    lines.append("")
    lines.append("## Touch points")
    lines.extend(f"- {item}" for item in cr["touchPoints"])
    lines.append("")
    lines.append("## Out of scope")
    lines.extend(f"- {item}" for item in cr["outOfScope"])
    return "\n".join(lines)


def create_worktree(repo_path: Path, branch_name: str) -> Path:
    # Sibling directory, not nested inside repo_path -- keeps it fully outside
    # the main checkout's tracked tree, no .gitignore juggling required.
    worktree_root = repo_path.parent / f"{repo_path.name}-worktrees"
    worktree_path = worktree_root / branch_name
    if worktree_path.exists():
        raise FileExistsError(
            f"{worktree_path} already exists -- remove it first with "
            f"`git worktree remove {worktree_path}` (run from {repo_path}) if it's stale."
        )
    worktree_root.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "worktree", "add", str(worktree_path), "-b", branch_name],
        cwd=repo_path, capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git worktree add failed:\n{result.stderr}")
    return worktree_path


def check_mergeability(worktree_path: Path) -> str:
    """Dry-run merge check against origin/main, done entirely inside the
    disposable worktree (never touches the caller's own working directory --
    it's fine to leave this worktree mid-merge-attempt since we abort right
    after). Returns "Clean" or "Conflicts detected -- manual resolution needed"."""
    subprocess.run(["git", "fetch", "origin", "main"], cwd=worktree_path, capture_output=True, text=True, encoding="utf-8")
    merge_check = subprocess.run(
        ["git", "merge", "--no-commit", "--no-ff", "origin/main"],
        cwd=worktree_path, capture_output=True, text=True, encoding="utf-8",
    )
    subprocess.run(["git", "merge", "--abort"], cwd=worktree_path, capture_output=True, text=True, encoding="utf-8")
    return "Clean" if merge_check.returncode == 0 else "Conflicts detected -- manual resolution needed"


def run_claude_streaming(cmd: list, cwd: Path, conn, cr_number: int):
    """Runs Claude Code with --output-format stream-json, updating
    dbo.ChangeRequests after every event so the API/UI can poll live status
    (session id, running token count, last action) instead of only seeing a
    result once the whole run finishes. Returns (final_message, cost, subtype,
    returncode, stderr, session_id, tokens_so_far)."""
    process = subprocess.Popen(
        cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", bufsize=1,
    )

    session_id = None
    tokens_so_far = 0
    final_message = None
    cost = None
    subtype = None

    for line in process.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        session_id = event.get("session_id", session_id)
        event_type = event.get("type")

        if event_type == "assistant":
            usage = event.get("message", {}).get("usage", {})
            tokens_so_far += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            cr_lib.update_progress(conn, cr_number, status="running", sessionId=session_id, tokensSoFar=tokens_so_far)
        elif event_type == "system" and event.get("subtype") == "post_turn_summary":
            cr_lib.update_progress(
                conn, cr_number, status="running", sessionId=session_id, tokensSoFar=tokens_so_far,
                lastAction=event.get("status_detail") or "",
            )
        elif event_type == "result":
            final_message = event.get("result")
            cost = event.get("total_cost_usd")
            subtype = event.get("subtype")

    process.wait()
    stderr_output = process.stderr.read()
    return final_message, cost, subtype, process.returncode, stderr_output, session_id, tokens_so_far


def build_prompt(cr_number: int, branch_name: str, cr_text: str) -> str:
    return f"""You are the implementation stage of a change-management pipeline. A human
already approved the Change Request below at Gate 1 -- your job is to build
exactly what it describes, nothing more.

{cr_text}

You are already on branch "{branch_name}", checked out in its own isolated
git worktree -- no need to create or switch branches yourself.

Instructions:
1. Implement exactly the requirements listed above. Do not touch anything
   listed under "Out of scope". Follow the existing code style and patterns
   already used in this repo -- look at neighboring files before writing new
   ones.
2. If tests already exist for the affected area, run them. Add tests for new
   behavior where the existing codebase has a pattern for doing so.
3. Commit your changes with a message that starts with "CR-{cr_number:03d}:".
4. Push the branch to origin.
5. Do NOT open a pull request yourself and do NOT merge anything -- stop
   after pushing. A human reviews and opens the PR next (Gate 3 in the
   pipeline design).
6. If the request turns out to be ambiguous or infeasible as written, stop,
   explain why in your final message, and do not push a half-finished branch.
"""


def main():
    parser = argparse.ArgumentParser(description="Implement an approved Change Request via headless Claude Code.")
    parser.add_argument("cr_number", type=int, help="The CR number to implement (must already be Approved).")
    parser.add_argument("--repo", default=".", help="Path to the target repo (default: current directory).")
    parser.add_argument("--dry-run", action="store_true", help="Build and print the prompt without invoking Claude.")
    parser.add_argument(
        "--permission-mode",
        default="bypassPermissions",
        help=(
            "Claude Code permission mode (default: bypassPermissions). Headless -p runs have no "
            "terminal to answer approval prompts, so anything not covered by ALLOWED_TOOLS above "
            "must be allowed up front rather than left to interactive approval."
        ),
    )
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    load_dotenv(repo_path / "api" / ".env")

    conn = cr_lib.get_conn()
    cr = cr_lib.get_cr(conn, args.cr_number)
    if not cr:
        print(f"CR-{args.cr_number:03d} not found.", file=sys.stderr)
        sys.exit(1)

    if not cr["status"].startswith("Approved"):
        print(
            f"CR-{args.cr_number:03d} is not approved (status: '{cr['status']}'). "
            "Gate 1 must approve it in the Admin tab before implementation runs.",
            file=sys.stderr,
        )
        sys.exit(1)

    branch_name = f"cr-{args.cr_number:03d}-{slugify(cr['title'])}"
    cr_text = format_cr_for_prompt(cr)
    prompt = build_prompt(args.cr_number, branch_name, cr_text)
    estimated_cost = cr["estimatedCost"] or MIN_BUDGET_USD
    max_budget = max(MIN_BUDGET_USD, estimated_cost * MAX_BUDGET_MARGIN_MULTIPLIER)

    if args.dry_run:
        print(f"--- Branch: {branch_name} ---")
        print(f"--- Max budget: ${max_budget:.2f} ---")
        print(f"--- Allowed tools: {ALLOWED_TOOLS} ---")
        print(prompt)
        return

    worktree_path = create_worktree(repo_path, branch_name)
    print(f"Created isolated worktree at {worktree_path} on branch {branch_name}")

    cr_lib.update_progress(conn, args.cr_number, status="running", lastAction="Starting...", tokensSoFar=0)

    cmd = [
        "claude", "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--permission-mode", args.permission_mode,
        "--allowedTools", ALLOWED_TOOLS,
        "--max-budget-usd", str(max_budget),
        "--add-dir", str(worktree_path),
    ]
    # Explicit UTF-8: Windows' default subprocess text-mode encoding (the
    # system ANSI codepage) mangles Claude Code's em-dashes and other
    # multi-byte UTF-8 output into mojibake otherwise.
    final_message, cost, subtype, returncode, stderr_output, session_id, tokens_so_far = run_claude_streaming(
        cmd, worktree_path, conn, args.cr_number
    )

    # Non-zero exit doesn't mean nothing happened -- e.g. hitting
    # --max-budget-usd right after the task finishes still exits non-zero.
    if returncode != 0:
        cr_lib.update_progress(conn, args.cr_number, status="failed", sessionId=session_id, tokensSoFar=tokens_so_far)
        print(f"Claude Code exited with an error (subtype: {subtype}):", file=sys.stderr)
        print(f"stdout result: {final_message}", file=sys.stderr)
        print(f"stderr: {stderr_output}", file=sys.stderr)
        if cost is not None:
            print(f"Cost so far: ${cost:.4f} (budget was ${max_budget:.2f})", file=sys.stderr)
        print(
            f"\nCheck `git log`/`git status` in {worktree_path} -- work may have already been "
            "committed/pushed before the failure. A non-zero exit here does not mean nothing happened.",
            file=sys.stderr,
        )
        sys.exit(1)

    cr_lib.update_progress(
        conn, args.cr_number, status="succeeded", sessionId=session_id, tokensSoFar=tokens_so_far, costUsd=cost
    )
    print(final_message)
    if cost is not None:
        print(f"\nActual cost: ${cost:.4f} (budget was ${max_budget:.2f})")

    merge_readiness = check_mergeability(worktree_path)
    print(f"\nMerge readiness: {merge_readiness}")

    # Record the branch + summary on the CR itself and advance it to Gate 2,
    # so the Admin tab's Approve & Merge action knows what to merge and a
    # reviewer has the agent's own account of what it did -- plus whether it's
    # a clean one-click merge or will need manual conflict resolution -- before approving.
    cr_lib.set_fields(
        conn, args.cr_number,
        branch=branch_name, mergeReadiness=merge_readiness,
        implementationSummary=(final_message or "").strip() or "(no summary returned)",
    )
    cr_lib.update_status(conn, args.cr_number, "Implemented -- awaiting Gate 2 (merge approval)")
    conn.close()

    # Best-effort compare URL so opening the PR is a single human click.
    remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=worktree_path, capture_output=True, text=True, encoding="utf-8")
    match = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", remote.stdout.strip())
    if match:
        owner, repo_name = match.groups()
        print(f"\nOpen a PR: https://github.com/{owner}/{repo_name}/compare/main...{branch_name}?expand=1")

    print(
        f"\nWork happened in an isolated worktree at {worktree_path}, separate from your "
        f"own working directory -- nothing there was touched. Once the branch is merged (or "
        f"abandoned), remove the worktree with: git worktree remove {worktree_path}"
    )


if __name__ == "__main__":
    main()
