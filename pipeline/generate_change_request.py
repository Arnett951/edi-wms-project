"""
Phase 1 of the human-governed autonomous delivery pipeline: intake, requirements
generation, impact analysis (blast-radius Tier check), and cost estimation --
ending in a Change Request markdown file for Gate 1 review.

Shares its core logic (config, system prompt, cost math, CR rendering) with
the live API endpoint via api/change_request_lib.py, so the CLI and the
deployed dashboard's chat-based intake never drift apart. This script is
local-only and never deployed, so importing across into api/ is fine here --
the reverse (api/ importing from pipeline/) would NOT be, since only api/**
ships to production.

See ../docs/ai-delivery-pipeline.md for the design this implements.

Usage:
    python generate_change_request.py "Add a chart showing daily EDI file volume"
    python generate_change_request.py                       # prompts interactively
    python generate_change_request.py "..." --dry-run        # no API calls, no cost
    python generate_change_request.py "..." --repo /path/to/other/project
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
from change_request_lib import (  # noqa: E402
    build_system_prompt,
    compute_cost,
    extract_json_block,
    load_config,
    next_cr_number,
    render_markdown,
)

MAX_CLARIFICATION_ROUNDS = 6
MODEL = "claude-sonnet-5"


def call_claude(client, system_prompt: str, messages: list) -> str:
    response = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=system_prompt,
        messages=messages,
    )
    return "".join(block.text for block in response.content if block.type == "text")


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


def main():
    parser = argparse.ArgumentParser(description="Generate a Change Request from a plain-language request.")
    parser.add_argument("request", nargs="?", help="The request text. Prompted interactively if omitted.")
    parser.add_argument("--repo", default=".", help="Path to the target repo (default: current directory).")
    parser.add_argument("--dry-run", action="store_true", help="Skip real API calls; verify file output only.")
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    config = load_config(repo_path / "api" / ".change-pipeline.yml")

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
