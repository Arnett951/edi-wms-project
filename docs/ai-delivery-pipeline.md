# Human-Governed Autonomous Delivery Pipeline

Three versions of the same idea, in increasing order of ambition:

1. **Minimal 2-gate pipeline** (below) — the manual process already happening in
   this chat, formalized on paper with zero new tooling. Cheapest to demonstrate.
2. **v0 rough draft** (further down) — adds a scope limiter, a written paper
   trail per change, and 4–5 gates. Still leans entirely on Claude Code as the
   executor, no custom infra.
3. **Long-form enterprise vision** — the full change-management platform (chat
   intake service, DB-backed change requests, automated security/regression
   pipelines, staged promotion with rollback) discussed as the ultimate goal.
   Estimated separately at ~45–72 sessions / 3.9M–6.5M tokens; not drafted here.

## Minimal 2-gate pipeline — what's already running, formalized

No new tooling, no CI, no staging environment. Just two named checkpoints around
a single Claude Code session — the same shape this conversation has already
followed for every change so far.

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
system — it's a personal-project pipeline that leans entirely on the Claude Agent
SDK / Claude Code as the executor, with a human gate before every irreversible step.

## Design principle

Don't build a custom orchestrator, sandbox, or agent harness. Claude Code / the
Claude Agent SDK already *is* the execution engine — "assign to a coding agent" is
just running a scoped session with the approved spec as its prompt. The only new
things to build are: (1) a scope limiter so risky requests never get automated,
and (2) a paper trail (Change Request docs in-repo) that ties each gate together.

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

1. **Intake & Clarification** — a Claude Code session with a system prompt scoped
   to this repo; output is a markdown Change Request committed to
   `change-requests/CR-###/request.md` (title, tier, systems touched,
   requirements, explicitly out-of-scope notes). The CR folder *is* the change
   log — no separate database.
2. **Gate 1 (Scope Approval)** — you read `request.md`, edit or approve inline,
   or it gets rejected if Tier C.
3. **Spec Generation** — same session, on approval, writes `spec.md`,
   `acceptance-criteria.md`, `test-cases.md`, `rollback.md` into the CR folder.
4. **Gate 2 (Spec Approval)** — read those four files before any code changes.
   Cheapest gate to reverse a misunderstanding.
5. **Implementation** — a Claude Code session (or a subagent) implements exactly
   what's in `spec.md`, on a branch named `cr-###-<slug>`, commits reference
   `CR-###`.
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
with its own sandboxing and guardrails — disappears entirely, since Claude Code
sessions (run by you, on demand, per stage) *are* the orchestrator. What's left
to actually build is small: the Tier classifier prompt, the CR folder template,
and wiring the existing GitHub Actions workflow to a staging slot plus a
promotion step. That's realistically **8–14 sessions / roughly 700k–1.2M
tokens** for a working v0 — not the 45–72 sessions estimated for the full
enterprise version.

## Open questions for v1+ (explicitly deferred)

- Who counts as "business owner" vs "technical approver" on a single-maintainer
  project — probably collapse Gates 3 and 4 reviewers into "you," revisit if
  this ever has other stakeholders.
- Whether Gate 4 and the production promotion should be separate clicks or the
  same one (drafted above as separate, but could merge for v0).
- Notifications: v0 assumes you're watching the repo directly (PR notifications
  from GitHub are enough); no dedicated Slack/Teams integration yet.
