"""
Phase 2 of the human-governed autonomous delivery pipeline: implementation.
Takes an *already Gate-1-approved* Change Request and hands it to Claude Code
(headless, via `claude -p`) to implement on a new branch, commit, and push --
stopping just short of opening the PR, which is a single manual click via the
compare URL this prints (Gate 3 / code review still happens on a real PR,
not inside this script).

See ../docs/ai-delivery-pipeline.md for the design this implements.

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

import yaml

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


def load_config(repo_path: Path) -> dict:
    config_path = repo_path / ".change-pipeline.yml"
    if not config_path.exists():
        return {"output_dir": "change-requests"}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def find_cr_file(repo_path: Path, config: dict, cr_number: int) -> Path:
    output_dir = repo_path / config.get("output_dir", "change-requests")
    request_file = output_dir / f"CR-{cr_number:03d}" / "request.md"
    if not request_file.exists():
        raise FileNotFoundError(f"{request_file} not found")
    return request_file


def parse_status(text: str) -> str:
    match = re.search(r"-\s*\*\*Status:\*\*\s*(.+)", text)
    return match.group(1).strip() if match else ""


def parse_title(text: str) -> str:
    match = re.search(r"^#\s*CR-\d+:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else "change-request"


def parse_estimated_cost(text: str) -> float:
    match = re.search(r"-\s*\*\*Estimated cost:\*\*\s*\$([\d.]+)", text)
    return float(match.group(1)) if match else MIN_BUDGET_USD


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:50] or "change"


def build_prompt(cr_number: int, branch_name: str, cr_text: str) -> str:
    return f"""You are the implementation stage of a change-management pipeline. A human
already approved the Change Request below at Gate 1 -- your job is to build
exactly what it describes, nothing more.

{cr_text}

Instructions:
1. Create and switch to a new git branch named "{branch_name}" (from the
   current default branch).
2. Implement exactly the requirements listed above. Do not touch anything
   listed under "Out of scope". Follow the existing code style and patterns
   already used in this repo -- look at neighboring files before writing new
   ones.
3. If tests already exist for the affected area, run them. Add tests for new
   behavior where the existing codebase has a pattern for doing so.
4. Commit your changes with a message that starts with "CR-{cr_number:03d}:".
5. Push the branch to origin.
6. Do NOT open a pull request yourself and do NOT merge anything -- stop
   after pushing. A human reviews and opens the PR next (Gate 3 in the
   pipeline design).
7. If the request turns out to be ambiguous or infeasible as written, stop,
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
    config = load_config(repo_path)
    cr_file = find_cr_file(repo_path, config, args.cr_number)
    cr_text = cr_file.read_text(encoding="utf-8")

    status = parse_status(cr_text)
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

    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--permission-mode", args.permission_mode,
        "--allowedTools", ALLOWED_TOOLS,
        "--max-budget-usd", str(max_budget),
        "--add-dir", str(repo_path),
    ]
    result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Claude Code exited with an error:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    try:
        output = json.loads(result.stdout)
        final_message = output.get("result", result.stdout)
        cost = output.get("total_cost_usd")
    except json.JSONDecodeError:
        final_message = result.stdout
        cost = None

    print(final_message)
    if cost is not None:
        print(f"\nActual cost: ${cost:.4f} (budget was ${max_budget:.2f})")

    # Best-effort compare URL so opening the PR is a single human click.
    remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=repo_path, capture_output=True, text=True)
    match = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", remote.stdout.strip())
    if match:
        owner, repo_name = match.groups()
        print(f"\nOpen a PR: https://github.com/{owner}/{repo_name}/compare/main...{branch_name}?expand=1")


if __name__ == "__main__":
    main()
