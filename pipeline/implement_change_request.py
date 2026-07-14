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
swept together. See ../docs/ai-delivery-pipeline.md for the design this
implements.

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


def find_cr_file(repo_path: Path, config: dict, cr_number: int) -> Path:
    output_dir = repo_path / config.get("output_dir", "change-requests")
    request_file = output_dir / f"CR-{cr_number:03d}" / "request.md"
    if not request_file.exists():
        raise FileNotFoundError(f"{request_file} not found")
    return request_file


def parse_title(text: str) -> str:
    match = re.search(r"^#\s*CR-\d+:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else "change-request"


def parse_estimated_cost(text: str) -> float:
    match = re.search(r"-\s*\*\*Estimated cost:\*\*\s*\$([\d.]+)", text)
    return float(match.group(1)) if match else MIN_BUDGET_USD


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:50] or "change"


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
        cwd=repo_path, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git worktree add failed:\n{result.stderr}")
    return worktree_path


def check_mergeability(worktree_path: Path) -> str:
    """Dry-run merge check against origin/main, done entirely inside the
    disposable worktree (never touches the caller's own working directory --
    it's fine to leave this worktree mid-merge-attempt since we abort right
    after). Returns "Clean" or "Conflicts detected -- manual resolution needed"."""
    subprocess.run(["git", "fetch", "origin", "main"], cwd=worktree_path, capture_output=True, text=True)
    merge_check = subprocess.run(
        ["git", "merge", "--no-commit", "--no-ff", "origin/main"],
        cwd=worktree_path, capture_output=True, text=True,
    )
    subprocess.run(["git", "merge", "--abort"], cwd=worktree_path, capture_output=True, text=True)
    return "Clean" if merge_check.returncode == 0 else "Conflicts detected -- manual resolution needed"


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
    config = cr_lib.load_config(repo_path / "api" / ".change-pipeline.yml")
    cr_file = find_cr_file(repo_path, config, args.cr_number)
    cr_text = cr_file.read_text(encoding="utf-8")

    status = cr_lib.get_status(cr_text)
    if not status.startswith("Approved"):
        print(
            f"CR-{args.cr_number:03d} is not approved (status: '{status}'). "
            "Gate 1 must approve it in the Admin tab before implementation runs.",
            file=sys.stderr,
        )
        sys.exit(1)

    title = parse_title(cr_text)
    branch_name = f"cr-{args.cr_number:03d}-{slugify(title)}"
    prompt = build_prompt(args.cr_number, branch_name, cr_text)
    estimated_cost = parse_estimated_cost(cr_text)
    max_budget = max(MIN_BUDGET_USD, estimated_cost * MAX_BUDGET_MARGIN_MULTIPLIER)

    if args.dry_run:
        print(f"--- Branch: {branch_name} ---")
        print(f"--- Max budget: ${max_budget:.2f} ---")
        print(f"--- Allowed tools: {ALLOWED_TOOLS} ---")
        print(prompt)
        return

    worktree_path = create_worktree(repo_path, branch_name)
    print(f"Created isolated worktree at {worktree_path} on branch {branch_name}")

    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--permission-mode", args.permission_mode,
        "--allowedTools", ALLOWED_TOOLS,
        "--max-budget-usd", str(max_budget),
        "--add-dir", str(worktree_path),
    ]
    result = subprocess.run(cmd, cwd=worktree_path, capture_output=True, text=True)

    # Non-zero exit doesn't mean nothing happened -- e.g. hitting
    # --max-budget-usd right after the task finishes still exits non-zero.
    # Always surface stdout too, not just stderr, so that detail isn't lost.
    try:
        output = json.loads(result.stdout)
        final_message = output.get("result", result.stdout)
        cost = output.get("total_cost_usd")
        subtype = output.get("subtype")
    except json.JSONDecodeError:
        final_message = result.stdout
        cost = None
        subtype = None

    if result.returncode != 0:
        print(f"Claude Code exited with an error (subtype: {subtype}):", file=sys.stderr)
        print(f"stdout: {final_message}", file=sys.stderr)
        print(f"stderr: {result.stderr}", file=sys.stderr)
        if cost is not None:
            print(f"Cost so far: ${cost:.4f} (budget was ${max_budget:.2f})", file=sys.stderr)
        print(
            f"\nCheck `git log`/`git status` in {worktree_path} -- work may have already been "
            "committed/pushed before the failure. A non-zero exit here does not mean nothing happened.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(final_message)
    if cost is not None:
        print(f"\nActual cost: ${cost:.4f} (budget was ${max_budget:.2f})")

    merge_readiness = check_mergeability(worktree_path)
    print(f"\nMerge readiness: {merge_readiness}")

    # Record the branch + summary on the CR itself and advance it to Gate 2,
    # so the Admin tab's Approve & Merge action knows what to merge and a
    # reviewer has the agent's own account of what it did -- plus whether it's
    # a clean one-click merge or will need manual conflict resolution -- before approving.
    updated_text = cr_text
    updated_text = cr_lib.set_field(updated_text, "Branch", branch_name)
    updated_text = cr_lib.set_field(updated_text, "Merge readiness", merge_readiness)
    updated_text = cr_lib.append_or_replace_section(
        updated_text, "Implementation summary", final_message.strip() or "(no summary returned)"
    )
    updated_text = cr_lib.update_status(updated_text, "Implemented -- awaiting Gate 2 (merge approval)")
    cr_file.write_text(updated_text, encoding="utf-8")

    # Best-effort compare URL so opening the PR is a single human click.
    remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=worktree_path, capture_output=True, text=True)
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
