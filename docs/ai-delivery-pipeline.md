# Human-Governed Autonomous Delivery Pipeline

Three versions of the same idea, in increasing order of ambition:

1. **Minimal 2-gate pipeline** (below) — the manual process already happening in
   this chat, formalized on paper with zero new tooling. This one really is an
   interactive Claude Code session, typed by a person, every time. Cheapest to
   demonstrate.
2. **v0 rough draft** (further down) — adds a scope limiter, a written paper
   trail per change, and 4–5 gates. Every AI stage is a **Claude Agent SDK
   call, invoked programmatically from a script or CI job — not an interactive
   chat session.** No custom orchestrator, sandbox, or agent harness beyond
   that SDK call itself.
3. **Long-form enterprise vision** — the full change-management platform (chat
   intake service, DB-backed change requests, automated security/regression
   pipelines, staged promotion with rollback) discussed as the ultimate goal.
   Estimated separately at ~45–72 sessions / 3.9M–6.5M tokens; not drafted here.

## Minimal 2-gate pipeline — what's already running, formalized

No new tooling, no CI, no staging environment. Just two named checkpoints around
a single interactive Claude Code session — you typing in chat, same as this
conversation — not an API integration. That distinction matters: this version
is a person opening Claude Code by hand every time; the v0 draft below is the
version where that gets replaced by code.

```
[AI] Intake & Planning
     - clarify the request
     - draft a short plan (what will change, where, why)
        │
   ── GATE 1: Plan Approval ──  (before any code is written)
        │
[AI] Implementation
     - write the code
     - write/run validation (unit tests, or a manual verification pass —
       e.g. loading it in a browser preview and checking for errors)
        │
   ── GATE 2: Validation Confirmation ──  (after tests/checks are shown passing)
        │
[HUMAN] Push  (git push — the one always-explicit "go live" action)
```

**Worked example, from this session:** the cartoon-demo finale-stage request
followed this exact shape — clarifying question asked and answered (Intake →
implicit Gate 1), the new stage implemented, then verified live in the browser
preview with console/log checks before being reported done (Gate 2). The only
step not yet taken is the push, which stays a separate, explicit ask every time.

This is deliberately *not* automated further than that: Gate 1 and Gate 2 are
just "the point where I stop and you read what I did before I continue,"
formalized so it can be pointed to and explained, not new infrastructure.

---

# v0 rough draft (5-gate, semi-automated)

Scoped-down version of the "chat request → production" concept illustrated in the
architecture demo's finale stage. This is **not** an enterprise change-management
system — it's a personal-project pipeline that leans entirely on the **Claude
Agent SDK, called from code**, with a human gate before every irreversible step.

## Design principle

Don't build a custom orchestrator, sandbox, or agent harness. The Claude Agent
SDK already *is* the execution engine — "assign to a coding agent" means a
script or CI step calls the SDK programmatically (system prompt scoped to this
repo, tools limited to file edit + git + `gh` CLI) and it runs unattended until
it finishes or hits a gate. No person opens a terminal to type the prompt — that
manual version is the separate "minimal 2-gate pipeline" above. The only new
things to build here are: (1) the SDK invocation harness itself (auth, tool
scoping, a CLI/script wrapper, capturing output back into the CR record),
(2) a scope limiter so risky requests never get automated, and (3) a paper
trail (Change Request docs in-repo) that ties each gate together.

## Scope limiter — which requests are even eligible

| Tier | Examples | Automation |
|---|---|---|
| **A — in scope** | New SQL view/query, new dashboard chart on existing tables, new read-only API `GET` endpoint | Full pipeline below |
| **B — semi-automated** | Additive schema change (new table/column, no drops/renames), new ADF pipeline step, new scheduled job | Full pipeline + extra reviewer attention at Gate 2 |
| **C — excluded, do manually** | Anything touching auth/security, schema drops/renames, new Azure resources or secrets, prod data-mutation logic | Pipeline refuses at Intake, tells you to do it by hand |

Classification is a simple pattern match at intake (what tables/files/resources
would this touch), not a bulletproof risk model. That's the whole point of
limiting scope — no need to get this perfectly right.

## Stages and gates

```
[AI] Intake & Clarification
        │
   ── GATE 1: Scope Approval ──  (you approve/edit/reject the Change Request; Tier C auto-stops)
        │
[AI] Spec Generation (tech spec, acceptance criteria, test cases, rollback plan)
        │
   ── GATE 2: Spec Approval ──  (cheapest place to catch misunderstood scope, before any code)
        │
[AI] Implementation (feature branch, SQL/API/dashboard/docs, commits reference CR#)
        │
[AI] Automated Checks (lint, existing test suite, basic data-validation script)
        │
[AI] PR Packaging (opens PR, links CR + spec — never merges itself)
        │
   ── GATE 3: Code Review ──  (normal PR review, nothing bypasses this)
        │
[AI] Deploy to Staging (existing GitHub Actions workflow, dev/staging slot)
        │
   ── GATE 4: UAT Sign-off ──  (you click-test the staged feature; sign-off = comment on the CR)
        │
[AI] Promote to Production (merge staging → main; same artifact that passed staging)
        │
[existing] Monitoring (reuse whatever's already wired up — no new build)
        │
[you or AI] Rollback (revert the merge commit, redeploy via the same workflow)
```

## What each stage actually is (v0, no new infra)

1. **Intake & Clarification** — **implemented** in
   [`../pipeline/generate_change_request.py`](../pipeline/generate_change_request.py):
   a scripted Anthropic API call (not yet the full Agent SDK harness — see note
   below) with a system prompt built from `.change-pipeline.yml`; asks
   clarifying questions one at a time, then writes a markdown Change Request to
   `change-requests/CR-###/request.md` (title, tier, requirements, touch
   points, out-of-scope notes, estimated tokens, and a cost ratio against the
   configured reference budget). The CR folder *is* the change log — no
   separate database. Run with `--dry-run` to verify the file output with no
   API cost. Currently uses the plain Anthropic Python SDK directly rather
   than the Claude Agent SDK proper (no file-edit/git tools yet — this stage
   only reasons and writes one file) — that distinction matters more once
   Implementation (stage 5) needs real tool access.
2. **Gate 1 (Scope Approval)** — you read `request.md`, edit or approve inline,
   or it gets rejected if Tier C.
3. **Spec Generation** — same session, on approval, writes `spec.md`,
   `acceptance-criteria.md`, `test-cases.md`, `rollback.md` into the CR folder.
4. **Gate 2 (Spec Approval)** — read those four files before any code changes.
   Cheapest gate to reverse a misunderstanding.
5. **Implementation** — another Claude Agent SDK call (same harness, different
   prompt) implements exactly what's in `spec.md`, on a branch named
   `cr-###-<slug>`, commits reference `CR-###`.
6. **Automated Checks** — existing lint + test suite (pytest/vitest), plus a
   lightweight data-validation script (row-count/schema sanity check against a
   WMS test dataset). No custom security tooling for v0 — rely on GitHub's
   built-in secret scanning + Dependabot, which already exist for free.
7. **PR Packaging** — the agent opens the PR itself, description links back to
   the CR folder. It never merges its own PR.
8. **Gate 3 (Code Review)** — ordinary GitHub PR review.
9. **Deploy to Staging** — reuses the existing `deploy-static-web-app.yml`
   pattern against a staging branch/slot.
10. **Gate 4 (UAT Sign-off)** — you test the staged feature; sign-off is a
    comment/checkbox appended to the CR (`UAT: approved YYYY-MM-DD`).
11. **Promote to Production** — merge `staging` → `main`; since this is a
    static-site + serverless setup, there's no separate binary/artifact
    versioning to build — the merge commit *is* the version.
12. **Monitoring & Rollback** — no new build. If something's wrong, revert the
    merge commit and let the existing workflow redeploy `main`.

## What this cuts from the original estimate

The expensive piece from the full estimate — a custom coding-agent orchestrator
with its own sandboxing and guardrails — disappears entirely, since Claude
Agent SDK calls *are* the orchestrator. What's left to actually build:

| Component | Sessions | Tokens |
|---|---|---|
| Claude Agent SDK invocation harness (auth, tool scoping, CLI/script wrapper, output capture into the CR record) — shared by every AI stage | 2–3 | 200k–350k |
| Chat intake + requirements generation prompt | 1–2 | 100k–150k |
| Impact analysis + blast-radius (Tier) classifier prompt | 1 | 80k–120k |
| Gate 1 wiring (CR record, approval capture) | 1 | 80k–120k |
| Implementation-stage prompt (reuses the harness) | 1 | 60k–100k |
| Git branch + PR automation | 1–2 | 100k–150k |
| Automated checks (lint, test suite, data-validation script) | 2–3 | 150k–250k |
| Staging deploy (extend existing GitHub Actions workflow) | 1–2 | 100k–150k |
| Gate 2 / UAT capture | 1 | 80k–120k |
| Production promotion | 1 | 60k–100k |
| Monitoring & rollback (reuse existing) | 1 | 60k–100k |
| Integration + end-to-end dry run | 1–2 | 100k–150k |
| **Total** | **~14–20 sessions** | **~1.17M–1.8M tokens** |

That's up slightly from the earlier 8–14 / 700k–1.2M estimate — that number
didn't call out the SDK invocation harness as its own line item, and building
a real programmatic wrapper (not just writing prompts) is genuine engineering
work. Still nowhere near the 45–72 sessions estimated for the full enterprise
version.

## Open questions for v1+ (explicitly deferred)

- Who counts as "business owner" vs "technical approver" on a single-maintainer
  project — probably collapse Gates 3 and 4 reviewers into "you," revisit if
  this ever has other stakeholders.
- Whether Gate 4 and the production promotion should be separate clicks or the
  same one (drafted above as separate, but could merge for v0).
- Notifications: v0 assumes you're watching the repo directly (PR notifications
  from GitHub are enough); no dedicated Slack/Teams integration yet.
