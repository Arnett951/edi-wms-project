# Change request intake (pipeline phase 1)

Implements the "Intake & Clarification" + "Impact analysis / blast-radius
check" stages from [`../docs/ai-delivery-pipeline.md`](../docs/ai-delivery-pipeline.md).
Takes a plain-language request, asks clarifying questions if needed, and
writes a Change Request markdown file for Gate 1 (human) review.

## Local run

```bash
pip install -r requirements.txt
python generate_change_request.py "Add a chart showing daily EDI file volume"
```

Omit the request text to be prompted for it interactively. Add `--dry-run` to
verify the CR file gets written correctly without making any real API calls
(useful for testing, costs nothing).

## Required environment variables

```text
ANTHROPIC_API_KEY=your-anthropic-api-key
```

Read from the environment, or from `../api/.env` if set there instead. Not
required for `--dry-run`.

## Output

Writes `../change-requests/CR-###/request.md`, auto-numbered from whatever
CR folders already exist. Each file has the original request verbatim, any
clarification Q&A, the tier classification, requirements, touch points,
out-of-scope notes, and an estimated token count with a cost ratio against
the `reference_monthly_budget_usd` set in `../.change-pipeline.yml`.

That dollar figure is a **sizing proxy**, not a literal bill -- it's the
estimated tokens priced at a placeholder blended rate (`blended_rate_per_million_tokens_usd`
in the config), divided by the reference budget. Confirm the rate against
[anthropic.com/pricing](https://www.anthropic.com/pricing) before trusting it,
and note that actual usage may run through a Pro/Max subscription rather than
metered API billing, in which case this is purely a relative-size gauge.

## Pointing at a different repo

```bash
python generate_change_request.py "..." --repo /path/to/other/project
```

Reads `.change-pipeline.yml` from that repo's root if present (falls back to
generic defaults if not) and writes its `change-requests/` folder there too --
this script doesn't assume it's only ever run against this project.
