# Change request intake (pipeline phase 1)

Implements the "Intake & Clarification" + "Impact analysis / blast-radius
check" stages from [`../docs/ai-delivery-pipeline.md`](../docs/ai-delivery-pipeline.md).
Takes a plain-language request, asks clarifying questions if needed, and
creates a Change Request row in `dbo.ChangeRequests` for Gate 1 (human) review.

## Local run

```bash
pip install -r requirements.txt
python generate_change_request.py "Add a chart showing daily EDI file volume"
```

Omit the request text to be prompted for it interactively. Add `--dry-run` to
verify the flow without making any real API/DB calls (useful for testing,
costs nothing).

## Required environment variables

```text
ANTHROPIC_API_KEY=your-anthropic-api-key
SQL_SERVER=your-server.database.windows.net
SQL_DATABASE=your-database
SQL_USER=your-user
SQL_PASSWORD=your-password
```

Read from the environment, or from `../api/.env` if set there instead. Not
required for `--dry-run`.

## Output

Creates a row in `dbo.ChangeRequests` (see `../sql/tables/dbo.ChangeRequests.sql`),
auto-numbered from the highest existing `CRNumber`. Each row has the original
request verbatim, any clarification Q&A, the tier classification,
requirements, touch points, out-of-scope notes, and an estimated token count
with a cost ratio against the `reference_monthly_budget_usd` set in
`../api/.change-pipeline.yml`.

CRs used to live as markdown files under `api/change-requests/` -- that
storage was replaced with a shared SQL table because files on a zip-deployed
Azure App Service get wiped on every redeploy, and a shared table also means
local dev and the deployed API read/write the exact same data instead of two
separate disks.

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

Reads `.change-pipeline.yml` from that repo's `api/` folder if present (falls
back to generic defaults if not). Still writes to whatever database the
`SQL_*` environment variables point at, so pointing this at another repo's
code doesn't automatically point it at another database -- set those env
vars accordingly if the other project uses a separate one.
