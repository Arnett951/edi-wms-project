"""
Phase 1 of the human-governed autonomous delivery pipeline: intake, requirements
generation, impact analysis (blast-radius Tier check), and cost estimation --
ending in a Change Request markdown file for Gate 1 review.

See ../docs/ai-delivery-pipeline.md for the design this implements.

Usage:
    python generate_change_request.py "Add a chart showing daily EDI file volume"
    python generate_change_request.py                       # prompts interactively
    python generate_change_request.py "..." --dry-run        # no API calls, no cost
    python generate_change_request.py "..." --repo /path/to/other/project
"""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import yaml
from dotenv import load_dotenv

DEFAULT_CONFIG = {
    "project_name": "Unnamed project",
    "stack_summary": "Unknown stack -- describe your project in .change-pipeline.yml",
    "output_dir": "change-requests",
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

MAX_CLARIFICATION_ROUNDS = 6
MODEL = "claude-sonnet-5"


def load_config(repo_path: Path) -> dict:
    config_path = repo_path / ".change-pipeline.yml"
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
     (planning + implementation + testing) needed to build this end to end

Tier rules for this project:
{tier_block}

If the request clearly belongs to Tier C, still produce the JSON (with tier
"C" and risk_notes explaining why) rather than refusing -- the pipeline itself
decides what happens with a Tier C request, not you."""


def call_claude(client, system_prompt: str, messages: list) -> str:
    response = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=system_prompt,
        messages=messages,
    )
    return "".join(block.text for block in response.content if block.type == "text")


def extract_json_block(text: str):
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def run_intake(client, system_prompt: str, initial_request: str):
    messages = [{"role": "user", "content": initial_request}]
    transcript = []

    for _ in range(MAX_CLARIFICATION_ROUNDS):
        reply = call_claude(client, system_prompt, messages)
        messages.append({"role": "assistant", "content": reply})

        cr_data = extract_json_block(reply)
        if cr_data is not None:
            return cr_data, transcript

        question = reply.strip()
        if question.startswith("QUESTION:"):
            question = question[len("QUESTION:"):].strip()
        print(f"\n{question}")
        answer = input("> ").strip()
        transcript.append((question, answer))
        messages.append({"role": "user", "content": answer})

    raise RuntimeError(
        f"No final answer after {MAX_CLARIFICATION_ROUNDS} clarification rounds -- "
        "narrow the request and try again."
    )


def dry_run_stub(initial_request: str):
    cr_data = {
        "title": "Dry-run stub -- no real API call made",
        "tier": "A",
        "risk_notes": "",
        "requirements": [f"(stub) implement: {initial_request}"],
        "touch_points": ["(stub) unknown -- run without --dry-run for a real answer"],
        "out_of_scope": [],
        "estimated_tokens": 100000,
    }
    return cr_data, []


def compute_cost(estimated_tokens: int, config: dict):
    rate = config["cost"]["blended_rate_per_million_tokens_usd"]
    budget = config["cost"]["reference_monthly_budget_usd"]
    dollars = (estimated_tokens / 1_000_000) * rate
    ratio_pct = (dollars / budget) * 100
    return dollars, ratio_pct


def next_cr_number(output_dir: Path) -> int:
    if not output_dir.exists():
        return 1
    existing = [p.name for p in output_dir.iterdir() if p.is_dir() and p.name.startswith("CR-")]
    numbers = []
    for name in existing:
        match = re.match(r"CR-(\d+)", name)
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1


def render_markdown(cr_number, original_request, transcript, cr_data, dollars, ratio_pct, config):
    tier = cr_data.get("tier", "?")
    tier_label = config["tiers"].get(tier, {}).get("label", "")
    status = "Auto-denied -- Tier C, handle manually" if tier == "C" else "Pending Gate 1 review"

    lines = [
        f"# CR-{cr_number:03d}: {cr_data.get('title', '(untitled)')}",
        "",
        f"- **Date:** {date.today().isoformat()}",
        f"- **Tier:** {tier} -- {tier_label}",
        f"- **Status:** {status}",
        f"- **Estimated tokens:** {cr_data.get('estimated_tokens', 0):,}",
        f"- **Estimated cost:** ${dollars:.2f} (blended rate -- see .change-pipeline.yml)",
        f"- **Cost ratio vs ${config['cost']['reference_monthly_budget_usd']}/mo reference budget:** {ratio_pct:.1f}%",
        "",
        "## Original request",
        "",
        f"> {original_request}",
        "",
    ]

    if transcript:
        lines.append("## Clarification")
        lines.append("")
        for question, answer in transcript:
            lines.append(f"- **Q:** {question}")
            lines.append(f"  **A:** {answer}")
        lines.append("")

    if cr_data.get("risk_notes"):
        lines.append("## Risk notes")
        lines.append("")
        lines.append(cr_data["risk_notes"])
        lines.append("")

    lines.append("## Requirements")
    lines.append("")
    for item in cr_data.get("requirements", []):
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Touch points")
    lines.append("")
    for item in cr_data.get("touch_points", []):
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Out of scope")
    lines.append("")
    for item in cr_data.get("out_of_scope", []):
        lines.append(f"- {item}")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate a Change Request from a plain-language request.")
    parser.add_argument("request", nargs="?", help="The request text. Prompted interactively if omitted.")
    parser.add_argument("--repo", default=".", help="Path to the target repo (default: current directory).")
    parser.add_argument("--dry-run", action="store_true", help="Skip real API calls; verify file output only.")
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    config = load_config(repo_path)

    initial_request = args.request or input("Describe the request: ").strip()
    if not initial_request:
        print("No request provided.", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        cr_data, transcript = dry_run_stub(initial_request)
    else:
        load_dotenv(repo_path / "api" / ".env")
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print(
                "ANTHROPIC_API_KEY not set (checked env and api/.env). "
                "Set it, or use --dry-run to test without a real API call.",
                file=sys.stderr,
            )
            sys.exit(1)
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        system_prompt = build_system_prompt(config)
        cr_data, transcript = run_intake(client, system_prompt, initial_request)

    dollars, ratio_pct = compute_cost(cr_data.get("estimated_tokens", 0), config)

    output_dir = repo_path / config["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    cr_number = next_cr_number(output_dir)
    cr_folder = output_dir / f"CR-{cr_number:03d}"
    cr_folder.mkdir(parents=True, exist_ok=True)

    markdown = render_markdown(cr_number, initial_request, transcript, cr_data, dollars, ratio_pct, config)
    request_path = cr_folder / "request.md"
    request_path.write_text(markdown, encoding="utf-8")

    print(f"\nWrote {request_path}")
    print(
        f"Tier {cr_data.get('tier', '?')} -- estimated {cr_data.get('estimated_tokens', 0):,} tokens "
        f"(~${dollars:.2f}, {ratio_pct:.1f}% of ${config['cost']['reference_monthly_budget_usd']}/mo)"
    )


if __name__ == "__main__":
    main()
