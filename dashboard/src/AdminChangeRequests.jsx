import React, { useEffect, useState } from "react";
import { useIsAuthenticated } from "@azure/msal-react";
import { authFetch } from "./apiClient.js";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const PENDING_STATUS = "Pending Gate 1 review";
const PENDING_BUILD_PREFIX = "Pending Build Approval";
const APPROVED_PREFIX = "Approved";
const IMPLEMENTED_PREFIX = "Implemented";
const MERGED_PREFIX = "Merged";
const CLOSED_PREFIXES = [MERGED_PREFIX, "Rejected", "Auto-denied", "Rolled back"];

const mockChangeRequests = [
  {
    crNumber: 101,
    title: "Add carrier SCAC validation on inbound 940",
    tier: "B",
    tierLabel: "Moderate",
    status: PENDING_STATUS,
    estimatedTokens: 42000,
    estimatedCost: 3.15,
    costRatioPct: 18,
    tokensSoFar: null,
    actualCostUsd: null,
    date: "2026-07-24",
    originalRequest: "Reject 940s with an unrecognized SCAC code instead of silently staging them.",
    requirements: ["Validate SCAC against the carrier reference table on ingest", "Route unrecognized SCACs to a new PARSE_FAILED reason"],
    touchPoints: ["EDI parser", "dbo.RawFiles"],
    outOfScope: ["Backfilling historical files"],
  },
  {
    crNumber: 100,
    title: "Surface WMS retry count on Recent Files table",
    tier: "A",
    tierLabel: "Low risk",
    status: `${PENDING_BUILD_PREFIX}`,
    estimatedTokens: 15000,
    estimatedCost: 1.1,
    costRatioPct: 6,
    tokensSoFar: null,
    actualCostUsd: null,
    date: "2026-07-22",
    originalRequest: "Show attemptCount next to WMS orders so stuck retries are visible without querying SQL directly.",
    requirements: ["Add a Retries column to the WMS orders table"],
    touchPoints: ["dashboard/src/App.jsx"],
    outOfScope: ["Changing retry behavior itself"],
  },
  {
    crNumber: 99,
    title: "Auto-close stale Gate 1 reviews after 7 days",
    tier: "B",
    tierLabel: "Moderate",
    status: "Approved — implementing",
    estimatedTokens: 20000,
    estimatedCost: 1.5,
    costRatioPct: 41,
    tokensSoFar: 8300,
    actualCostUsd: 0.62,
    date: "2026-07-20",
    originalRequest: "CRs sitting in Gate 1 review past 7 days should auto-reject with an explanatory note.",
    requirements: ["Nightly job flags and rejects stale pending CRs"],
    touchPoints: ["api/main.py"],
    outOfScope: ["Notifying requesters by email"],
  },
  {
    crNumber: 98,
    title: "Add cost-ratio column to CR table",
    tier: "A",
    tierLabel: "Low risk",
    status: "Implemented — ready to merge",
    mergeReadiness: "Clean merge available",
    estimatedTokens: 13000,
    estimatedCost: 0.98,
    costRatioPct: 96,
    tokensSoFar: 12400,
    actualCostUsd: 0.94,
    date: "2026-07-18",
    branch: "cr-98-cost-ratio-column",
    originalRequest: "Show actual-vs-estimated cost ratio per CR so reviewers can spot runaway builds early.",
    requirements: ["Add CostRatioPct column to the CR table and detail modal"],
    touchPoints: ["dashboard/src/AdminChangeRequests.jsx"],
    outOfScope: ["Historical backfill of past CRs"],
    implementationSummary: "Added a CostRatioPct column sourced from the existing estimate/actual fields; no schema changes needed.",
  },
  {
    crNumber: 97,
    title: "Fix duplicate ISA control number false-positive",
    tier: "A",
    tierLabel: "Low risk",
    status: "Merged",
    mergeReadiness: "Clean merge available",
    mergeCommit: "a1b2c3d4e5",
    estimatedTokens: 9500,
    estimatedCost: 0.75,
    costRatioPct: 96,
    tokensSoFar: 9100,
    actualCostUsd: 0.71,
    date: "2026-07-12",
    branch: "cr-97-fix-isa-dup",
    originalRequest: "The duplicate-ISA check was flagging same-day resubmits from the same trading partner as duplicates.",
    requirements: ["Scope the duplicate check to control number + partner + calendar day"],
    touchPoints: ["EDI parser"],
    outOfScope: [],
    implementationSummary: "Narrowed the duplicate-ISA check to (ControlNumber, PartnerId, Date) instead of ControlNumber alone.",
  },
  {
    crNumber: 96,
    title: "Add Slack alert on WMS integration failure",
    tier: "C",
    tierLabel: "High risk",
    status: "Auto-denied — Tier C requests require manual scoping",
    estimatedTokens: 60000,
    estimatedCost: 4.5,
    costRatioPct: 0,
    tokensSoFar: null,
    actualCostUsd: null,
    date: "2026-07-10",
    originalRequest: "Post a Slack message whenever a WMS order integration fails.",
    requirements: [],
    touchPoints: ["New external integration"],
    outOfScope: [],
  },
];

function isClosedStatus(status) {
  return CLOSED_PREFIXES.some((prefix) => status.startsWith(prefix));
}

function mockRequestsForTab(tab) {
  return mockChangeRequests.filter((cr) => (tab === "closed" ? isClosedStatus(cr.status) : !isClosedStatus(cr.status)));
}

function statusBadgeClass(status) {
  if (status === PENDING_STATUS) return "neutral";
  if (status.startsWith(MERGED_PREFIX)) return "good";
  if (status.startsWith(PENDING_BUILD_PREFIX)) return status.includes("previous attempt failed") ? "bad" : "ready";
  if (status.startsWith("Approved") || status.startsWith(IMPLEMENTED_PREFIX)) return "ready";
  if (status.startsWith("Rejected") || status.startsWith("Auto-denied") || status.startsWith("Rolled back")) return "bad";
  return "neutral";
}

function tierBadgeClass(tier) {
  if (tier === "A") return "good";
  if (tier === "B") return "ready";
  return "bad";
}

function crCode(crNumber) {
  return `CR-${String(crNumber).padStart(3, "0")}`;
}

function needsAttention(cr) {
  return cr.status.startsWith(IMPLEMENTED_PREFIX) && !!cr.mergeReadiness?.startsWith("Conflicts");
}

export default function AdminChangeRequests({ canManageCr }) {
  const isAuthenticated = useIsAuthenticated();
  const [requests, setRequests] = useState(mockRequestsForTab("active"));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [usingMockData, setUsingMockData] = useState(!isAuthenticated);
  const [actioningCr, setActioningCr] = useState(null);
  const [selectedCr, setSelectedCr] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);
  const [info, setInfo] = useState(null);
  const [progressByCr, setProgressByCr] = useState({});
  const [maxBudgetByCr, setMaxBudgetByCr] = useState({});
  // CR-Workflow tabs: "active" shows every CR that isn't Closed/Merged
  // (default), "closed" shows only Closed/Merged CRs.
  const [crTab, setCrTab] = useState("active");
  const [pendingDispatch, setPendingDispatch] = useState({});

  async function openDetail(crNumber) {
    if (usingMockData) {
      setSelectedCr(mockChangeRequests.find((cr) => cr.crNumber === crNumber) || { crNumber });
      return;
    }
    setSelectedCr({ crNumber });
    setDetailLoading(true);
    setDetailError(null);
    try {
      const res = await authFetch(`${API_BASE}/api/change-requests/${crNumber}`);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Failed to load ${crCode(crNumber)}.`);
      setSelectedCr(data);
    } catch (err) {
      setDetailError(err.message || `Failed to load ${crCode(crNumber)}.`);
    } finally {
      setDetailLoading(false);
    }
  }

  function closeDetail() {
    setSelectedCr(null);
    setDetailError(null);
  }

  async function loadRequests(tab = crTab) {
    setLoading(true);
    setError(null);
    if (!isAuthenticated) {
      setRequests(mockRequestsForTab(tab));
      setUsingMockData(true);
      setLoading(false);
      return;
    }
    try {
      const res = await authFetch(`${API_BASE}/api/change-requests?status_group=${tab}`);
      const data = await res.json().catch(() => []);
      if (!res.ok) throw new Error(data.detail || "Failed to load change requests.");
      const fresh = Array.isArray(data) ? data : [];
      setRequests(fresh);
      setUsingMockData(false);
      // Clear a "dispatched" marker once the remote merge/rollback has
      // actually landed (status changed), not just because a poll ran --
      // without this the row would flip back to its clickable state well
      // before the GitHub Actions run behind it is actually done.
      setPendingDispatch((prev) => {
        if (Object.keys(prev).length === 0) return prev;
        const next = { ...prev };
        for (const cr of fresh) {
          const action = next[cr.crNumber];
          if (!action) continue;
          if (action === "merge" && cr.status.startsWith(MERGED_PREFIX)) delete next[cr.crNumber];
          if (action === "rollback" && !cr.status.startsWith(MERGED_PREFIX)) delete next[cr.crNumber];
        }
        return next;
      });
    } catch (err) {
      setRequests(mockRequestsForTab(tab));
      setUsingMockData(true);
      setError(err.message || "Failed to load change requests.");
    } finally {
      setLoading(false);
    }
  }

  async function decide(crNumber, decision) {
    setActioningCr(crNumber);
    setError(null);
    setInfo(null);
    try {
      const res = await authFetch(`${API_BASE}/api/change-requests/${crNumber}/${decision}`, {
        method: "POST",
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Failed to ${decision} CR-${crNumber}.`);
      if (data.type === "dispatched") {
        // No local repo on this deployment -- the actual merge/rollback runs
        // async via GitHub Actions, so there's no fresh CR row to show yet.
        // Mark it pending so the row shows "dispatched" instead of the
        // action button springing back as if nothing happened, and so
        // polling keeps running until loadRequests() sees the real change.
        setInfo(data.message);
        if (decision === "merge" || decision === "rollback") {
          setPendingDispatch((prev) => ({ ...prev, [crNumber]: decision }));
        }
      } else {
        setRequests((prev) => prev.map((cr) => (cr.crNumber === crNumber ? data : cr)));
      }
    } catch (err) {
      setError(err.message || `Failed to ${decision} CR-${crNumber}.`);
    } finally {
      setActioningCr(null);
    }
  }

  async function startBuild(crNumber) {
    setActioningCr(crNumber);
    setError(null);
    setInfo(null);
    try {
      const raw = maxBudgetByCr[crNumber];
      const maxBudgetUsd = raw ? Number(raw) : null;
      const res = await authFetch(`${API_BASE}/api/change-requests/${crNumber}/start-build`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ maxBudgetUsd }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Failed to start build for CR-${crNumber}.`);
      if (data.type === "dispatched") {
        setInfo(data.message);
        loadRequests();
      } else {
        setRequests((prev) => prev.map((cr) => (cr.crNumber === crNumber ? data : cr)));
      }
    } catch (err) {
      setError(err.message || `Failed to start build for CR-${crNumber}.`);
    } finally {
      setActioningCr(null);
    }
  }

  // Fetch on mount and whenever the tab switches -- the server returns only
  // the CRs for the selected tab, so no full page reload is needed.
  useEffect(() => {
    loadRequests(crTab);
  }, [crTab, isAuthenticated]);

  // Simple polling: while any CR is Approved (implementation auto-starts on
  // approval server-side), refresh its live progress -- session id, running
  // token count, last action -- and re-check the CR list so a finished run
  // (status flips to "Implemented...") drops out of this view on its own.
  // Also keeps running while a merge/rollback is dispatched-but-unconfirmed
  // (pendingDispatch), since that transition only ever happens on GitHub's
  // runner, never locally -- without this, the row would never update on
  // its own once nothing is actively "Approved"/building.
  const approvedCrNumbers = requests.filter((cr) => cr.status.startsWith(APPROVED_PREFIX)).map((cr) => cr.crNumber);
  const pendingDispatchCount = Object.keys(pendingDispatch).length;
  useEffect(() => {
    if (usingMockData || (approvedCrNumbers.length === 0 && pendingDispatchCount === 0)) return undefined;
    const interval = setInterval(async () => {
      for (const crNumber of approvedCrNumbers) {
        try {
          const res = await authFetch(`${API_BASE}/api/change-requests/${crNumber}/progress`);
          const data = await res.json().catch(() => null);
          if (data) setProgressByCr((prev) => ({ ...prev, [crNumber]: data }));
        } catch {
          // Transient poll error -- next tick will retry.
        }
      }
      loadRequests();
    }, 4000);
    return () => clearInterval(interval);
  }, [approvedCrNumbers.join(","), pendingDispatchCount, usingMockData]);

  const attentionCount = requests.filter(needsAttention).length;

  return (
    <>
      <section className="panel">
        <h2>
          Change Request Review (Gate 1)
          {attentionCount > 0 && (
            <span className="status-badge bad" style={{ marginLeft: 10 }}>
              {attentionCount} need{attentionCount === 1 ? "s" : ""} attention
            </span>
          )}
        </h2>
        <p className="admin-lede">
          CRs move through Gate 1 review (SuperUser or Admin), Admin-only build approval, and Gate 2 merge
          before landing on <code>main</code> -- see the{" "}
          <a href="https://www.edi.chrisarnett.me/ai-pipeline-diagram.html" target="_blank" rel="noopener noreferrer">
            full pipeline diagram
          </a>. Tier C requests are auto-denied and shown for visibility only. A red "needs attention" flag
          means a branch has merge conflicts.
        </p>
        {error && <section className="alert"><div><strong>Error</strong><p>{error}</p></div></section>}
        {info && <section className="mock"><p>{info}</p></section>}
        {usingMockData && !loading && (
          <p className="admin-lede">Showing mock data — sign in for live change requests and to manage the pipeline.</p>
        )}
        <button onClick={loadRequests} disabled={loading}>
          {loading ? "Loading..." : "Refresh"}
        </button>{" "}
        <a href="https://www.edi.chrisarnett.me/shipped-feature-gap-analysis.html" target="_blank" rel="noopener noreferrer">
          Shipped Feature GAP Analysis
        </a>
      </section>

      <div className="tabs">
        <button
          className={crTab === "active" ? "tab-active" : ""}
          onClick={() => setCrTab("active")}
        >
          In Progress
        </button>
        <button
          className={crTab === "closed" ? "tab-active" : ""}
          onClick={() => setCrTab("closed")}
        >
          Closed / Merged
        </button>
      </div>

      <section className="panel">
        <table className="cr-table">
          <thead>
            <tr>
              <th>CR</th>
              <th>Title</th>
              <th>Tier</th>
              <th>Est. tokens</th>
              <th>Est. cost</th>
              <th>Cost ratio</th>
              <th>Actual tokens</th>
              <th>Actual cost</th>
              <th className="cr-status-cell">Status</th>
              <th className="cr-actions-cell">Actions</th>
            </tr>
          </thead>
          <tbody>
            {requests.length === 0 ? (
              <tr><td colSpan="10">{crTab === "closed" ? "No closed or merged change requests yet." : "No change requests in progress."}</td></tr>
            ) : (
              requests.map((cr) => (
                <tr key={cr.crNumber}>
                  <td>
                    <button className="link-btn" onClick={() => openDetail(cr.crNumber)}>
                      {crCode(cr.crNumber)}
                    </button>
                  </td>
                  <td className="file-name-cell" title={cr.originalRequest}>{cr.title}</td>
                  <td>
                    <span className={`status-badge ${tierBadgeClass(cr.tier)}`}>{cr.tier}</span>
                  </td>
                  <td>{cr.estimatedTokens ?? "—"}</td>
                  <td>{cr.estimatedCost ? `$${cr.estimatedCost}` : "—"}</td>
                  <td>{cr.costRatioPct ? `${cr.costRatioPct}%` : "—"}</td>
                  <td>{cr.tokensSoFar ?? "—"}</td>
                  <td>{cr.actualCostUsd != null ? `$${cr.actualCostUsd}` : "—"}</td>
                  <td className="cr-status-cell">
                    <span className={`status-badge ${statusBadgeClass(cr.status)}`}>{cr.status}</span>{" "}
                    {cr.status.startsWith(IMPLEMENTED_PREFIX) && cr.mergeReadiness && (
                      <span className={`status-badge ${cr.mergeReadiness.startsWith("Conflicts") ? "bad" : "good"}`}>
                        {cr.mergeReadiness.startsWith("Conflicts") ? "Needs attention" : "Clean merge"}
                      </span>
                    )}
                  </td>
                  <td className="cr-actions-cell">
                    {usingMockData ? (
                      <span className="status-badge neutral">Sign in to manage</span>
                    ) : (
                      <>
                        {cr.status === PENDING_STATUS && (
                          <>
                            <button
                              onClick={() => decide(cr.crNumber, "approve")}
                              disabled={actioningCr === cr.crNumber}
                            >
                              Approve
                            </button>{" "}
                            <button
                              onClick={() => decide(cr.crNumber, "reject")}
                              disabled={actioningCr === cr.crNumber}
                            >
                              Reject
                            </button>
                          </>
                        )}
                        {cr.status.startsWith(PENDING_BUILD_PREFIX) && (
                          canManageCr ? (
                            <div className="cr-progress">
                              <input
                                type="number"
                                min="0"
                                step="0.5"
                                placeholder="Max $ (optional)"
                                value={maxBudgetByCr[cr.crNumber] ?? ""}
                                onChange={(e) => setMaxBudgetByCr((prev) => ({ ...prev, [cr.crNumber]: e.target.value }))}
                                style={{ width: 110 }}
                              />{" "}
                              <button
                                onClick={() => startBuild(cr.crNumber)}
                                disabled={actioningCr === cr.crNumber}
                              >
                                Start Build
                              </button>{" "}
                              <button
                                onClick={() => decide(cr.crNumber, "reject")}
                                disabled={actioningCr === cr.crNumber}
                              >
                                Reject
                              </button>
                            </div>
                          ) : (
                            <span className="status-badge neutral">Awaiting Admin build approval</span>
                          )
                        )}
                        {cr.status.startsWith(APPROVED_PREFIX) && (
                          <div className="cr-progress">
                            <span className="status-badge neutral">
                              {progressByCr[cr.crNumber]?.status === "failed" ? "Implementation failed" : "Implementing..."}
                            </span>
                            {progressByCr[cr.crNumber]?.sessionId && (
                              <div className="cr-progress-detail">
                                Session {progressByCr[cr.crNumber].sessionId.slice(0, 8)} &middot;{" "}
                                {progressByCr[cr.crNumber].tokensSoFar ?? 0} tokens
                              </div>
                            )}
                            {progressByCr[cr.crNumber]?.lastAction && (
                              <div className="cr-progress-detail">{progressByCr[cr.crNumber].lastAction.slice(0, 140)}</div>
                            )}
                          </div>
                        )}
                        {cr.status.startsWith(IMPLEMENTED_PREFIX) && (
                          pendingDispatch[cr.crNumber] === "merge" ? (
                            <span className="status-badge neutral">Merge dispatched -- check Actions tab</span>
                          ) : (
                            <button
                              onClick={() => {
                                if (window.confirm(`Merge ${crCode(cr.crNumber)}'s branch into main and push?`)) {
                                  decide(cr.crNumber, "merge");
                                }
                              }}
                              disabled={actioningCr === cr.crNumber}
                            >
                              Approve &amp; Merge
                            </button>
                          )
                        )}
                        {cr.status.startsWith(MERGED_PREFIX) && (
                          pendingDispatch[cr.crNumber] === "rollback" ? (
                            <span className="status-badge neutral">Rollback dispatched -- check Actions tab</span>
                          ) : (
                            <button
                              onClick={() => {
                                if (window.confirm(`Revert ${crCode(cr.crNumber)}'s merge commit and push?`)) {
                                  decide(cr.crNumber, "rollback");
                                }
                              }}
                              disabled={actioningCr === cr.crNumber}
                            >
                              Rollback
                            </button>
                          )
                        )}
                      </>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      {selectedCr && (
        <div className="cr-modal-overlay" onClick={closeDetail}>
          <div className="cr-modal" onClick={(e) => e.stopPropagation()}>
            <div className="cr-modal-header">
              <h2>{crCode(selectedCr.crNumber)}{selectedCr.title ? `: ${selectedCr.title}` : ""}</h2>
              <button className="cr-modal-close" onClick={closeDetail} aria-label="Close">×</button>
            </div>

            {detailLoading && <p>Loading...</p>}
            {detailError && (
              <section className="alert"><div><strong>Error</strong><p>{detailError}</p></div></section>
            )}

            {!detailLoading && !detailError && selectedCr.status && (
              <div className="cr-modal-body">
                <div className="cr-modal-meta">
                  <span className={`status-badge ${tierBadgeClass(selectedCr.tier)}`}>
                    Tier {selectedCr.tier} -- {selectedCr.tierLabel}
                  </span>
                  <span className={`status-badge ${statusBadgeClass(selectedCr.status)}`}>
                    {selectedCr.status}
                  </span>
                  <span className="cr-modal-meta-item">{selectedCr.date}</span>
                  <span className="cr-modal-meta-item">{selectedCr.estimatedTokens} tokens</span>
                  <span className="cr-modal-meta-item">${selectedCr.estimatedCost}</span>
                  <span className="cr-modal-meta-item">{selectedCr.costRatioPct}% of budget</span>
                </div>

                {(selectedCr.branch || selectedCr.mergeCommit || selectedCr.rollbackCommit) && (
                  <div className="cr-modal-meta">
                    {selectedCr.branch && <span className="cr-modal-meta-item">Branch: {selectedCr.branch}</span>}
                    {selectedCr.mergeReadiness && (
                      <span className={`status-badge ${selectedCr.mergeReadiness.startsWith("Conflicts") ? "bad" : "good"}`}>
                        {selectedCr.mergeReadiness}
                      </span>
                    )}
                    {selectedCr.mergeCommit && (
                      <span className="cr-modal-meta-item">Merge commit: {selectedCr.mergeCommit.slice(0, 10)}</span>
                    )}
                    {selectedCr.rollbackCommit && (
                      <span className="cr-modal-meta-item">Rollback commit: {selectedCr.rollbackCommit.slice(0, 10)}</span>
                    )}
                  </div>
                )}

                <h3>Original request</h3>
                <blockquote className="cr-modal-quote">{selectedCr.originalRequest}</blockquote>

                {selectedCr.clarification?.length > 0 && (
                  <>
                    <h3>Clarification</h3>
                    <dl className="cr-modal-qa">
                      {selectedCr.clarification.map((qa, i) => (
                        <React.Fragment key={i}>
                          <dt>{qa.question}</dt>
                          <dd>{qa.answer}</dd>
                        </React.Fragment>
                      ))}
                    </dl>
                  </>
                )}

                {selectedCr.riskNotes && (
                  <>
                    <h3>Risk notes</h3>
                    <p className="cr-modal-risk">{selectedCr.riskNotes}</p>
                  </>
                )}

                <h3>Requirements</h3>
                <ul>{selectedCr.requirements?.map((item, i) => <li key={i}>{item}</li>)}</ul>

                <h3>Touch points</h3>
                <ul>{selectedCr.touchPoints?.map((item, i) => <li key={i}>{item}</li>)}</ul>

                <h3>Out of scope</h3>
                <ul>{selectedCr.outOfScope?.map((item, i) => <li key={i}>{item}</li>)}</ul>

                {selectedCr.implementationSummary && (
                  <>
                    <h3>Implementation summary</h3>
                    <p className="cr-modal-quote">{selectedCr.implementationSummary}</p>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
