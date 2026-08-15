"""
Ad-hoc test: can the local Qwen model (skynet, vLLM OpenAI-compatible
endpoint) stand in for Claude at the CR-Workflow intake stage?

Reuses the real system prompt from api/change_request_lib.build_system_prompt
so this is testing the actual production prompt, not a simplified stand-in.
Runs the same multi-round clarification loop as pipeline/generate_change_request.py's
run_intake(), except answers to Qwen's "QUESTION:" turns are auto-supplied (a
canned "use a reasonable default" answer) instead of read from stdin, so this
can run unattended. Stops and reports PASS/FAIL once Qwen returns a
```json block or MAX_ROUNDS is hit.

This does NOT write to the database and does NOT call Claude -- it's a
standalone comparison harness, separate from generate_change_request.py.

skynet's Qwen2.5-3B is served with a 2048-token TOTAL context window (see
--max-tokens below), which is small enough that the accumulating multi-round
transcript can itself blow the budget -- that's tracked and reported as a
first-class failure mode, not just a crash.

Usage:
    python test_qwen_cr_intake.py
    python test_qwen_cr_intake.py "Add a chart showing daily EDI file volume"
    python test_qwen_cr_intake.py --base-url http://100.123.161.53:8000/v1 --model Qwen/Qwen2.5-3B-Instruct
"""

import argparse
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
import change_request_lib as cr_lib  # noqa: E402

DEFAULT_BASE_URL = "http://100.123.161.53:8000/v1"
DEFAULT_MODEL = "Qwen/Qwen2.5-3B-Instruct"
DEFAULT_REQUEST = "Add a chart showing daily EDI file volume to the dashboard"
DEFAULT_CONTEXT_LENGTH = 2048
MAX_ROUNDS = 4
CANNED_ANSWER = "Use a reasonable default; there are no additional constraints."

REQUIRED_KEYS = {
    "title": str,
    "tier": str,
    "risk_notes": str,
    "requirements": list,
    "touch_points": list,
    "out_of_scope": list,
    "estimated_tokens": int,
}


def call_qwen(base_url: str, model: str, system_prompt: str, messages: list, timeout: tuple, max_tokens: int):
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system_prompt}] + messages,
    }
    start = time.perf_counter()
    resp = requests.post(f"{base_url.rstrip('/')}/chat/completions", json=payload, timeout=timeout)
    elapsed = time.perf_counter() - start
    if resp.status_code == 400 and "maximum context length" in resp.text:
        return None, elapsed, resp.json()["error"]["message"]
    resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"] or ""
    return text, elapsed, None


def validate_schema(cr_data: dict):
    problems = []
    for key, expected_type in REQUIRED_KEYS.items():
        if key not in cr_data:
            problems.append(f"missing key: {key}")
            continue
        if not isinstance(cr_data[key], expected_type):
            problems.append(f"{key}: expected {expected_type.__name__}, got {type(cr_data[key]).__name__}")

    if "tier" in cr_data and cr_data["tier"] not in ("A", "B", "C"):
        problems.append(f"tier: expected one of A/B/C, got {cr_data['tier']!r}")

    if "estimated_tokens" in cr_data and isinstance(cr_data["estimated_tokens"], int):
        if cr_data["estimated_tokens"] <= 0:
            problems.append("estimated_tokens: expected a realistic non-zero estimate, got <= 0")

    return problems


def run_intake(base_url: str, model: str, system_prompt: str, initial_request: str, out_budget: int, timeout: tuple):
    messages = [{"role": "user", "content": initial_request}]
    total_elapsed = 0.0

    for round_num in range(1, MAX_ROUNDS + 1):
        print(f"--- Round {round_num} ---")

        # The server reports context overflow in terms of "at least N input
        # tokens" (a lower bound -- it stops counting once input + max_tokens
        # exceeds the ceiling, so the true prompt length is unknown). Back off
        # the output budget and retry rather than trying to compute the exact
        # token count ourselves.
        budget = out_budget
        text = ctx_error = None
        while budget >= 256:
            text, elapsed, ctx_error = call_qwen(base_url, model, system_prompt, messages, timeout, budget)
            total_elapsed += elapsed
            if not ctx_error:
                break
            print(f"[context overflow at max_tokens={budget}, backing off to {budget // 2}]")
            budget //= 2

        if ctx_error:
            print(f"CONTEXT LIMIT HIT: {ctx_error}")
            return None, messages, total_elapsed, "context_limit"

        print(f"Latency: {elapsed:.2f}s")
        print(text)
        print()

        messages.append({"role": "assistant", "content": text})

        cr_data = cr_lib.extract_json_block(text)
        if cr_data is not None:
            return cr_data, messages, total_elapsed, None

        question = text.strip()
        if question.upper().startswith("QUESTION:"):
            question = question[len("QUESTION:"):].strip()
        print(f"[auto-answering with canned response: {CANNED_ANSWER!r}]\n")
        messages.append({"role": "user", "content": CANNED_ANSWER})

    return None, messages, total_elapsed, "max_rounds"


def main():
    parser = argparse.ArgumentParser(description="Test whether local Qwen can complete CR intake end to end.")
    parser.add_argument("request", nargs="?", default=DEFAULT_REQUEST, help="The change request text.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="vLLM OpenAI-compatible base URL.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name as registered with vLLM.")
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent), help="Path to the target repo.")
    parser.add_argument("--context-length", type=int, default=DEFAULT_CONTEXT_LENGTH,
                         help="Server's total context window, used to size each round's output budget.")
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    config = cr_lib.load_config(repo_path / "api" / ".change-pipeline.yml")
    system_prompt = cr_lib.build_system_prompt(config)

    # Leave headroom under the server's context ceiling for the (growing)
    # conversation history plus the system prompt; err on the small side
    # rather than re-deriving vLLM's own tokenizer count.
    out_budget = max(256, args.context_length - 900)

    print(f"Qwen base URL:   {args.base_url}")
    print(f"Qwen model:      {args.model}")
    print(f"Context length:  {args.context_length} (output budget per round: {out_budget})")
    print(f"Request:         {args.request}\n")

    try:
        cr_data, messages, total_elapsed, failure_mode = run_intake(
            args.base_url, args.model, system_prompt, args.request, out_budget, timeout=(5, 60)
        )
    except Exception as exc:
        print(f"FAIL: request to Qwen failed: {exc}")
        sys.exit(1)

    print(f"Total latency across {len(messages) // 2 + (1 if failure_mode else 0)} round(s): {total_elapsed:.2f}s\n")

    if failure_mode == "context_limit":
        print("RESULT: FAIL -- hit the server's context-length ceiling before intake could finish. "
              "skynet's Qwen2.5-3B deployment (2048-token context) may be too small to run the "
              "multi-round CR intake prompt as currently written.")
        sys.exit(1)

    if failure_mode == "max_rounds":
        print(f"RESULT: FAIL -- no final JSON after {MAX_ROUNDS} rounds (kept asking questions).")
        sys.exit(1)

    problems = validate_schema(cr_data)

    print("--- Parsed CR ---")
    print(json.dumps(cr_data, indent=2))
    print()

    if problems:
        print("RESULT: FAIL -- schema problems:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)

    forced_keyword = cr_lib.find_forced_tier_c_keyword(
        " ".join([
            cr_data.get("title", ""),
            cr_data.get("risk_notes", ""),
            " ".join(cr_data.get("requirements", [])),
            " ".join(cr_data.get("touch_points", [])),
            args.request,
        ]),
        config,
    )

    print("RESULT: PASS -- Qwen produced a schema-valid CR.")
    print(f"  Tier: {cr_data['tier']}" + (f" (would force-escalate to C: matched '{forced_keyword}')" if forced_keyword and cr_data['tier'] != 'C' else ""))
    dollars, ratio_pct = cr_lib.compute_cost(cr_data["estimated_tokens"], config)
    print(f"  Estimated tokens: {cr_data['estimated_tokens']:,} (~${dollars:.2f}, {ratio_pct:.1f}% of ${config['cost']['reference_monthly_budget_usd']}/mo)")


if __name__ == "__main__":
    main()
