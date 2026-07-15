import React, { useEffect, useState } from "react";
import { authFetch } from "./apiClient.js";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const PENDING_STATUS = "Pending Gate 1 review";
const PENDING_BUILD_PREFIX = "Pending Build Approval";
const APPROVED_PREFIX = "Approved";
const IMPLEMENTED_PREFIX = "Implemented";
const MERGED_PREFIX = "Merged";

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
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
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
    try {
      const res = await authFetch(`${API_BASE}/api/change-requests?status_group=${tab}`);
      const data = await res.json().catch(() => []);
      if (!res.ok) throw new Error(data.detail || "Failed to load change requests.");
      const fresh = Array.isArray(data) ? data : [];
      setRequests(fresh);
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
  }, [crTab]);

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
    if (approvedCrNumbers.length === 0 && pendingDispatchCount === 0) return undefined;
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
  }, [approvedCrNumbers.join(","), pendingDispatchCount]);

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
          Requests generated by the intake pipeline (<code>pipeline/generate_change_request.py</code>),
          waiting on human approval before implementation starts. Tier C requests are auto-denied by the
          pipeline itself and never reach this queue for approval -- they're listed here for visibility only.
          Gate 1 approval (SuperUser or Admin) only marks a CR ready -- it does not start any build. Only
          Admin can actually start the build (with an optional budget override) once a CR reaches Pending
          Build Approval. Implemented CRs show a merge-readiness badge -- a red "needs attention" flag means
          the branch has conflicts and won't be a clean one-click merge.
        </p>
        {error && <section className="alert"><div><strong>Error</strong><p>{error}</p></div></section>}
        {info && <section className="mock"><p>{info}</p></section>}
        <button onClick={loadRequests} disabled={loading}>
          {loading ? "Loading..." : "Refresh"}
        </button>
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
        <table>
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
              <th>Actions</th>
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
                  <td>
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
