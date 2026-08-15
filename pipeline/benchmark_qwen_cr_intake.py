"""
Repeatable benchmark: how well does the local Qwen model (skynet, vLLM
OpenAI-compatible endpoint) do at CR-Workflow intake across a spread of
request types, compared against the tier each request SHOULD get per
api/.change-pipeline.yml?

Builds on test_qwen_cr_intake.py's single-request harness (same system
prompt, same multi-round auto-answered clarification loop) but runs a fixed
suite of TEST_CASES and scores each one, so results are comparable run over
run -- e.g. before/after raising skynet's --max-model-len off its current
2048-token ceiling.

Does NOT write to the database and does NOT call Claude.

Usage:
    python benchmark_qwen_cr_intake.py
    python benchmark_qwen_cr_intake.py --context-length 8192
    python benchmark_qwen_cr_intake.py --base-url http://100.123.161.53:8000/v1 --model Qwen/Qwen2.5-3B-Instruct
"""

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
import change_request_lib as cr_lib  # noqa: E402
from test_qwen_cr_intake import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    run_intake,
    validate_schema,
)

RESULTS_CSV = Path(__file__).resolve().parent / "qwen_cr_intake_benchmark_results.csv"

# Experimental augmentation appended to the real production system prompt
# (api/change_request_lib.build_system_prompt) for the "fewshot" prompt
# variant -- NOT a change to that shared function itself, since it's used by
# the live Claude-backed pipeline too. This is scoped to this benchmark only.
#
# Encodes the two gaps the baseline run exposed: (1) tier is decided by a
# holistic judgment call over an example list, which a 3B model handled
# unreliably for Tier B; (2) the deterministic C backstop only catches exact
# force_keywords phrases, so a model that reasons in different words (e.g.
# "remove" instead of "drop") never gets flagged even at the model layer.
# The checklist forces the decision into ordered binary questions instead,
# and the worked examples use DIFFERENT concrete requests than TEST_CASES
# below so this remains a genuine generalization test, not memorization of
# the eval set itself.
FEWSHOT_BLOCK = """

Before you settle on a tier, walk through this checklist IN ORDER and stop at
the first question you answer "yes" to -- do not skip ahead based on overall
vibe:

1. Does this touch authentication, authorization, secrets, credentials, or
   production data-mutation logic? -> Tier C.
2. Does this delete, drop, rename, or otherwise remove any existing table or
   column -- regardless of whether the request uses the word "drop" ("remove",
   "get rid of", "no longer needed", "clean up" all count too)? -> Tier C.
3. Does this ADD a new table, column, ADF pipeline step, or scheduled job,
   with nothing existing removed or renamed? -> Tier B at minimum, even if it
   sounds simple.
4. Otherwise (new read-only views/queries/charts/GET endpoints on data that
   already exists, or copy/label/UI-only changes) -> Tier A.

Worked examples (do not just pattern-match these verbatim -- apply the same
checklist reasoning to the actual request):

- "Add a bar chart of weekly order counts by status" -> checklist: not
  auth/secrets, nothing removed, nothing new added to schema, purely reads
  existing data. Tier A.
- "Add a tracking_number column to the Shipments table" -> checklist: not
  auth/secrets, nothing removed, but a new column IS being added. Tier B, even
  though it looks like "just one column."
- "Remove the unused LegacyFlag column from Shipments, nothing reads it
  anymore" -> checklist: this removes an existing column. Tier C, even though
  the word "drop" never appears -- "remove" and "unused ... anymore" both mean
  the same schema-drop risk.
- "Let users reset their own password from the login screen" -> checklist:
  touches authentication directly. Tier C.
"""

# expected_tier is what api/.change-pipeline.yml's own tier rules say this
# request should land on -- NOT what we expect Qwen to say. Comparing the
# two is the point of this benchmark.
TEST_CASES = [
    {
        "name": "new-chart",
        "request": "Add a chart showing daily EDI file volume to the dashboard",
        "expected_tier": "A",
        "note": "Tier A example verbatim from .change-pipeline.yml",
    },
    {
        "name": "new-get-endpoint",
        "request": "Add a new read-only API endpoint that lists EDI files that failed to parse in the last 7 days",
        "expected_tier": "A",
        "note": "Tier A example verbatim from .change-pipeline.yml",
    },
    {
        "name": "additive-schema-change",
        "request": "Add a carrier_name column to the Orders table so we can track which carrier shipped each order",
        "expected_tier": "B",
        "note": "Tier B example verbatim (additive schema change) -- no keyword backstop exists for B, so a model that under-calls this to A silently skips Gate 1 extra review",
    },
    {
        "name": "auth-feature",
        "request": "Add password reset functionality so users can reset their dashboard login",
        "expected_tier": "C",
        "note": "Should hit the deterministic force_keywords backstop ('password') even if the model self-reports something lower",
    },
    {
        "name": "schema-drop",
        "request": "Remove the legacy StatusCode column from the Orders table, it's not used anymore",
        "expected_tier": "C",
        "note": "Should hit the 'drop column' force_keywords backstop",
    },
    {
        "name": "trivial-copy-edit",
        "request": "Change the label on the EDI Files tab from 'Files' to 'EDI Files'",
        "expected_tier": "A",
        "note": "Sounds trivial -- per edi_wms_cr_estimation_gap this class of request ran Claude's own estimates 8-9.5x over actual, so this checks whether Qwen's token estimate is even in a sane ballpark, not just whether tier is right",
    },
]

# Real closed CRs pulled from dbo.ChangeRequests (via cr_lib.list_crs(conn,
# "closed")), NOT written by hand for this benchmark and NOT structurally
# close to any FEWSHOT_BLOCK worked example (no chart/GET-endpoint/schema-
# add/auth analog among them) -- a genuine held-out generalization check
# rather than a category the fewshot prompt was explicitly primed for.
# expected_tier is each CR's actual stored `tier` column, i.e. the real
# Claude-driven pipeline's post-backstop effective tier for that exact
# request text, not a hand-guess.
HELD_OUT_CASES = [
    {
        "name": "closed-cr021-export-csv-button",
        "request": "Add an export-to-CSV button for the WMS staging queue",
        "expected_tier": "A",
        "note": "CR-021, real closed CR -- new UI action/button, not a chart or GET endpoint",
    },
    {
        "name": "closed-cr014-split-tabs",
        "request": "on CR-WOrkflow page the list of CR's is getting long, need to create a 2nd tab on that page the "
                    "initial tab will show CR's in progress status and the 2nd tab will only show Closed / Merged CR's only",
        "expected_tier": "A",
        "note": "CR-014, real closed CR -- multi-step UI/logic feature (new tab + status-based filtering), noisier "
                "phrasing (typos, run-on) than any synthetic case, and more complex than trivial-copy-edit while "
                "still correctly Tier A (no schema/auth touched)",
    },
    {
        "name": "closed-cr013-widen-column",
        "request": "on the CR Work Flow tab the Status column needs to be a little longer and allow for word wrapping",
        "expected_tier": "A",
        "note": "CR-013, real closed CR -- pure CSS/layout tweak, a category (styling) none of the fewshot examples cover",
    },
    {
        "name": "closed-cr010-multi-dim-chart",
        "request": "add a stacked bar chart on how many files recieved and  errored per client over last 48 hours.  "
                    "add chart to the reports tab",
        "expected_tier": "A",
        "note": "CR-010, real closed CR -- chart request but multi-dimensional (per-client, received vs errored, "
                "48hr window) and typo'd, unlike the clean single-metric fewshot chart example",
    },
]

CASE_SETS = {"synthetic": TEST_CASES, "held_out_closed": HELD_OUT_CASES}


def run_case(base_url, model, system_prompt, config, case, out_budget, timeout, prompt_variant):
    print(f"\n{'=' * 90}\n[{case['name']}] {case['request']}\n{'=' * 90}")

    t0 = time.perf_counter()
    try:
        cr_data, messages, total_elapsed, failure_mode = run_intake(
            base_url, model, system_prompt, case["request"], out_budget, timeout
        )
    except Exception as exc:
        return {
            "prompt_variant": prompt_variant, "name": case["name"], "request": case["request"],
            "expected_tier": case["expected_tier"],
            "outcome": "error", "detail": str(exc), "actual_tier": "", "tier_match": False,
            "schema_valid": False, "rounds": 0, "latency_sec": round(time.perf_counter() - t0, 2),
            "estimated_tokens": "", "forced_escalation": "",
        }

    rounds = sum(1 for m in messages if m["role"] == "assistant")

    if failure_mode:
        print(f"OUTCOME: {failure_mode}")
        return {
            "prompt_variant": prompt_variant, "name": case["name"], "request": case["request"],
            "expected_tier": case["expected_tier"],
            "outcome": failure_mode, "detail": "", "actual_tier": "", "tier_match": False,
            "schema_valid": False, "rounds": rounds, "latency_sec": round(total_elapsed, 2),
            "estimated_tokens": "", "forced_escalation": "",
        }

    problems = validate_schema(cr_data)
    schema_valid = not problems

    forced_keyword = None
    actual_tier = cr_data.get("tier", "")
    if schema_valid:
        forced_keyword = cr_lib.find_forced_tier_c_keyword(
            " ".join([
                cr_data.get("title", ""), cr_data.get("risk_notes", ""),
                " ".join(cr_data.get("requirements", [])), " ".join(cr_data.get("touch_points", [])),
                case["request"],
            ]),
            config,
        )
        effective_tier = "C" if (forced_keyword and actual_tier != "C") else actual_tier
    else:
        effective_tier = ""

    tier_match = effective_tier == case["expected_tier"]

    print(f"Model self-reported tier: {actual_tier!r}" + (f" -> force-escalated to C ({forced_keyword})" if forced_keyword and actual_tier != "C" else ""))
    print(f"Effective tier: {effective_tier!r} vs expected {case['expected_tier']!r} -> {'MATCH' if tier_match else 'MISMATCH'}")
    print(f"Schema valid: {schema_valid}" + (f" -- problems: {problems}" if problems else ""))
    if schema_valid:
        print(f"estimated_tokens: {cr_data.get('estimated_tokens')}")

    return {
        "prompt_variant": prompt_variant, "name": case["name"], "request": case["request"],
        "expected_tier": case["expected_tier"],
        "outcome": "ok" if schema_valid else "invalid_schema",
        "detail": "; ".join(problems),
        "actual_tier": actual_tier, "tier_match": tier_match, "schema_valid": schema_valid,
        "rounds": rounds, "latency_sec": round(total_elapsed, 2),
        "estimated_tokens": cr_data.get("estimated_tokens", "") if schema_valid else "",
        "forced_escalation": forced_keyword or "",
    }


def main():
    parser = argparse.ArgumentParser(description="Score Qwen on a fixed suite of CR intake requests.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--context-length", type=int, default=2048,
                         help="Server's total context window right now -- pass the new value after you raise "
                              "skynet's --max-model-len so the output budget and CSV run-metadata reflect it.")
    parser.add_argument("--prompt-variant", choices=["baseline", "fewshot"], default="baseline",
                         help="'baseline' = the real production system prompt as-is. 'fewshot' = baseline plus "
                              "an appended blast-radius checklist and worked examples (see FEWSHOT_BLOCK), "
                              "testing whether that closes the Tier B / schema-drop gaps baseline showed.")
    parser.add_argument("--case-set", choices=list(CASE_SETS), default="synthetic",
                         help="'synthetic' = the hand-written TEST_CASES (some structurally close to fewshot "
                              "examples). 'held_out_closed' = real closed CRs pulled from dbo.ChangeRequests, "
                              "none matching a fewshot example's category, for a genuine generalization check.")
    args = parser.parse_args()

    cases = CASE_SETS[args.case_set]
    repo_path = Path(args.repo).resolve()
    config = cr_lib.load_config(repo_path / "api" / ".change-pipeline.yml")
    system_prompt = cr_lib.build_system_prompt(config)
    if args.prompt_variant == "fewshot":
        system_prompt += FEWSHOT_BLOCK
    out_budget = max(256, args.context_length - 900)

    print(f"Qwen base URL:  {args.base_url}")
    print(f"Qwen model:     {args.model}")
    print(f"Context length: {args.context_length} (output budget per round: {out_budget})")
    print(f"Prompt variant: {args.prompt_variant}")
    print(f"Case set:       {args.case_set}")
    print(f"Cases:          {len(cases)}")

    run_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results = [
        run_case(args.base_url, args.model, system_prompt, config, case, out_budget, timeout=(5, 60), prompt_variant=args.prompt_variant)
        for case in cases
    ]
    for r in results:
        r["case_set"] = args.case_set

    print(f"\n{'=' * 90}\nSUMMARY\n{'=' * 90}")
    header = f"{'name':<24}{'outcome':<16}{'expected':<10}{'actual':<10}{'match':<7}{'rounds':<8}{'sec':<7}{'est_tok':<8}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(f"{r['name']:<24}{r['outcome']:<16}{r['expected_tier']:<10}{r['actual_tier']:<10}"
              f"{str(r['tier_match']):<7}{r['rounds']:<8}{r['latency_sec']:<7}{str(r['estimated_tokens']):<8}")

    n = len(results)
    tier_matches = sum(1 for r in results if r["tier_match"])
    schema_valid_count = sum(1 for r in results if r["schema_valid"])
    avg_latency = sum(r["latency_sec"] for r in results) / n
    print(f"\nTier match: {tier_matches}/{n}  |  Schema valid: {schema_valid_count}/{n}  |  Avg latency: {avg_latency:.2f}s")

    # Append (not overwrite) so results accumulate across runs -- e.g. one
    # row-set at context_length=2048, another after raising --max-model-len,
    # directly comparable in one file.
    file_exists = RESULTS_CSV.exists()
    fieldnames = ["run_date", "context_length", "model", "prompt_variant", "case_set", "name", "request",
                  "expected_tier", "actual_tier", "tier_match", "forced_escalation", "outcome", "schema_valid",
                  "detail", "rounds", "latency_sec", "estimated_tokens"]
    with open(RESULTS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for r in results:
            writer.writerow({"run_date": run_date, "context_length": args.context_length, "model": args.model, **r})

    print(f"\nAppended {n} rows to {RESULTS_CSV}")


if __name__ == "__main__":
    main()
