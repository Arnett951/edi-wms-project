"""
Shared logic for the change-request intake pipeline, used by both the local
CLI (pipeline/generate_change_request.py) and the live API endpoint
(api/main.py's /api/change-requests/intake) so the two never drift apart.

Lives inside api/ (not repo root, not pipeline/) so it deploys with the
backend -- .github/workflows/deploy-api-appservice.yml only packages api/**.
The CLI script imports this module across directories since it's local-only
and never deployed; the API imports it as a plain sibling module.
"""

import json
import re
from datetime import date
from pathlib import Path

import yaml

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


def load_config(config_path: Path) -> dict:
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
     (planning + implementation + testing) needed to build this end to end --
     ALWAYS a realistic non-zero estimate, even for Tier C. A Tier C request
     still needs this number for future roadmap sizing if it's ever picked up
     manually; "it won't be automated" is not a reason to write 0.

Tier rules for this project:
{tier_block}

If the request clearly belongs to Tier C, still produce the JSON (with tier
"C" and risk_notes explaining why) rather than refusing -- the pipeline itself
decides what happens with a Tier C request, not you. The impact analysis and
token estimate you already did to reach that conclusion should still be
reported, not discarded."""


def extract_json_block(text: str):
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


STATUS_PATTERN = re.compile(r"-\s*\*\*Status:\*\*\s*(.+)")


def get_status(text: str) -> str:
    match = STATUS_PATTERN.search(text)
    return match.group(1).strip() if match else ""


def update_status(text: str, new_status: str) -> str:
    updated, count = STATUS_PATTERN.subn(f"- **Status:** {new_status}", text, count=1)
    if count == 0:
        raise ValueError("Could not locate a Status line to update")
    return updated


def get_field(text: str, field_name: str):
    pattern = re.compile(rf"-\s*\*\*{re.escape(field_name)}:\*\*\s*(.+)")
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def set_field(text: str, field_name: str, value: str) -> str:
    """Update a top '- **Field:** value' metadata line if present, else insert
    it right after the Status line (metadata block always starts there)."""
    pattern = re.compile(rf"-\s*\*\*{re.escape(field_name)}:\*\*\s*.+")
    if pattern.search(text):
        return pattern.sub(f"- **{field_name}:** {value}", text, count=1)
    status_pattern = re.compile(r"(-\s*\*\*Status:\*\*\s*.+\n)")
    updated, count = status_pattern.subn(rf"\1- **{field_name}:** {value}\n", text, count=1)
    if count == 0:
        raise ValueError("Could not locate the Status line to insert the new field after")
    return updated


def append_or_replace_section(text: str, heading: str, content: str) -> str:
    pattern = re.compile(rf"## {re.escape(heading)}\s*\n(.*?)(?=\n## |\Z)", re.DOTALL)
    if pattern.search(text):
        return pattern.sub(f"## {heading}\n\n{content}\n", text, count=1)
    return text.rstrip() + f"\n\n## {heading}\n\n{content}\n"


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
