"""
Phase 1 of the human-governed autonomous delivery pipeline: intake, requirements
generation, impact analysis (blast-radius Tier check), and cost estimation --
ending in a Change Request row in dbo.ChangeRequests for Gate 1 review.

Shares its core logic (config, system prompt, cost math, DB access) with the
live API endpoint via api/change_request_lib.py, so the CLI and the deployed
dashboard's chat-based intake never drift apart. This script is local-only
and never deployed, so importing across into api/ is fine here -- the
reverse (api/ importing from pipeline/) would NOT be, since only api/**
ships to production.

See ../docs/ai-delivery-pipeline.md for the design this implements.

Usage:
    python generate_change_request.py "Add a chart showing daily EDI file volume"
    python generate_change_request.py                       # prompts interactively
    python generate_change_request.py "..." --dry-run        # no API/DB calls, no cost
    python generate_change_request.py "..." --repo /path/to/other/project
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
import change_request_lib as cr_lib  # noqa: E402

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

        cr_data = cr_lib.extract_json_block(reply)
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
    parser.add_argument("--dry-run", action="store_true", help="Skip real API/DB calls; print only.")
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    config = cr_lib.load_config(repo_path / "api" / ".change-pipeline.yml")

    initial_request = args.request or input("Describe the request: ").strip()
    if not initial_request:
        print("No request provided.", file=sys.stderr)
        sys.exit(1)

    load_dotenv(repo_path / "api" / ".env")

    if args.dry_run:
        cr_data, transcript = dry_run_stub(initial_request)
        dollars, ratio_pct = cr_lib.compute_cost(cr_data.get("estimated_tokens", 0), config)
        print(f"--- Dry run -- nothing written to the database ---")
        print(f"Title: {cr_data['title']}")
        print(f"Tier {cr_data['tier']} -- estimated {cr_data['estimated_tokens']:,} tokens "
              f"(~${dollars:.2f}, {ratio_pct:.1f}% of ${config['cost']['reference_monthly_budget_usd']}/mo)")
        return

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
    system_prompt = cr_lib.build_system_prompt(config)
    cr_data, transcript = run_intake(client, system_prompt, initial_request)

    dollars, ratio_pct = cr_lib.compute_cost(cr_data.get("estimated_tokens", 0), config)

    with cr_lib.get_conn() as conn:
        cr_number = cr_lib.next_cr_number(conn)
        created = cr_lib.create_cr(conn, cr_number, initial_request, transcript, cr_data, dollars, ratio_pct, config)

    print(f"\nCreated CR-{cr_number:03d}: {created['title']}")
    print(
        f"Tier {created['tier']} -- estimated {created['estimatedTokens']:,} tokens "
        f"(~${created['estimatedCost']:.2f}, {created['costRatioPct']:.1f}% of ${config['cost']['reference_monthly_budget_usd']}/mo)"
    )


if __name__ == "__main__":
    main()
