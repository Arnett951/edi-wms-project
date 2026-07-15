import React, { useEffect, useMemo, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { useMsal, useIsAuthenticated } from "@azure/msal-react";
import { buildStatusChart, normalizeSummary, statusClass } from "./dashboardUtils";
import { authFetch } from "./apiClient.js";
import { loginRequest } from "./authConfig.js";
import ChatPanel from "./ChatPanel";
import CapacityDashboard from "./CapacityDashboard.jsx";
import AdminChangeRequests from "./AdminChangeRequests.jsx";
import ReportsDashboard from "./ReportsDashboard.jsx";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const mockSummary = {
  filesReceived: 6,
  filesParsed: 5,
  filesFailed: 1,
  wmsReady: 2,
  wmsSent: 1,
  wmsSuccess: 2,
  wmsFailed: 1,
  wmsPickedUp: 4,
};

const mockRecentFiles = [
  { rawId: 7, fileName: "sample_940_2.edi", processStatus: "PARSED", loadDateTime: "2026-04-28 18:45:50", errorMessage: null },
  { rawId: 6, fileName: "sample_940.edi", processStatus: "PARSED", loadDateTime: "2026-04-28 18:42:13", errorMessage: null },
  { rawId: 5, fileName: "bad_940_missing_st.edi", processStatus: "PARSE_FAILED", loadDateTime: "2026-04-28 18:38:19", errorMessage: "No ST*940 transaction sets were parsed from this file." },
];

const mockWmsOrders = [
  { wmsOrderHeaderStagingId: 101, warehouseOrderNumber: "ORDER1001", integrationStatus: "SUCCESS", attemptCount: 1, errorMessage: null },
  { wmsOrderHeaderStagingId: 102, warehouseOrderNumber: "ORDER1002", integrationStatus: "READY", attemptCount: 0, errorMessage: null },
  { wmsOrderHeaderStagingId: 103, warehouseOrderNumber: "ORDER1003", integrationStatus: "FAILED", attemptCount: 2, errorMessage: "Mock WMS rejected order: invalid SKU." },
];

function Icon({ type, className = "" }) {
  const props = { className, width: 24, height: 24, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true };
  if (type === "refresh") return <svg {...props}><path d="M21 12a9 9 0 0 1-15.5 6.3" /><path d="M3 12A9 9 0 0 1 18.5 5.7" /><path d="M18 2v4h-4" /><path d="M6 22v-4h4" /></svg>;
  if (type === "alert") return <svg {...props}><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4" /><path d="M12 17h.01" /></svg>;
  if (type === "check") return <svg {...props}><path d="M22 11.1V12a10 10 0 1 1-5.9-9.1" /><path d="m9 11 3 3L22 4" /></svg>;
  if (type === "database") return <svg {...props}><ellipse cx="12" cy="5" rx="9" ry="3" /><path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5" /><path d="M3 12c0 1.7 4 3 9 3s9-1.3 9-3" /></svg>;
  if (type === "truck") return <svg {...props}><path d="M10 17h4V5H2v12h3" /><path d="M14 17h1" /><path d="M15 7h4l3 4v6h-3" /><circle cx="7" cy="17" r="2" /><circle cx="17" cy="17" r="2" /></svg>;
  if (type === "play") return (
    <svg {...props}>
      <path d="M5 3l14 9-14 9V3z" />
    </svg>
  );
  if (type === "clock") return (
    <svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 3" />
    </svg>
  );
  return <svg {...props}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6" /><path d="M16 13H8" /><path d="M16 17H8" /><path d="M10 9H8" /></svg>;
}

function formatAge(seconds = 0) {
  if (!seconds) return "0 sec";
  if (seconds < 60) return `${seconds} sec`;
  return `${(seconds / 60).toFixed(1)} min`;
}

function queueClass(seconds = 0) {
  if (seconds < 60) return "queue-green";
  if (seconds <= 300) return "queue-yellow";
  return "queue-red";
}

async function fetchJson(url) {
  const response = await authFetch(url);
  if (!response.ok) throw new Error(`${url} returned HTTP ${response.status}`);
  return response.json();
}

function StatusBadge({ status }) {
  return <span className={`status-badge ${statusClass(status)}`}>{status || "UNKNOWN"}</span>;
}

export default function App() {
  const { instance, accounts } = useMsal();
  const isAuthenticated = useIsAuthenticated();
  const [summary, setSummary] = useState(null);
  const [recentFiles, setRecentFiles] = useState([]);
  const [wmsOrders, setWmsOrders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [usingMockData, setUsingMockData] = useState(false);
  const [error, setError] = useState(null);
  const [simulateMessage, setSimulateMessage] = useState(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("operations");
  const [permissions, setPermissions] = useState([]);
  const canDownloadFiles = permissions.includes("files.download");

  async function loadPermissions() {
    try {
      const data = await fetchJson(`${API_BASE}/api/me/permissions`);
      setPermissions(Array.isArray(data.permissions) ? data.permissions : []);
    } catch (err) {
      // Non-fatal - admin-gated UI just stays hidden if this fails.
    }
  }

  async function toggleDemoAdmin() {
    const endpoint = canDownloadFiles ? "/api/demo/revoke-admin" : "/api/demo/grant-admin";
    try {
      const res = await authFetch(`${API_BASE}${endpoint}`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Failed to update admin status.");
      setPermissions(Array.isArray(data.permissions) ? data.permissions : []);
    } catch (err) {
      setError(err.message || "Failed to update admin status.");
    }
  }

  async function downloadFile(rawId) {
    try {
      const res = await authFetch(`${API_BASE}/api/files/${rawId}/download-url`);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Failed to get download link.");
      window.open(data.downloadUrl, "_blank", "noopener,noreferrer");
    } catch (err) {
      setError(err.message || "Failed to download file.");
    }
  }

  async function loadDashboard() {
    setLoading(true);
    setError(null);
    try {
      const [summaryData, filesData, wmsData] = await Promise.all([
        fetchJson(`${API_BASE}/api/dashboard/summary`),
        fetchJson(`${API_BASE}/api/dashboard/recent-files`),
        fetchJson(`${API_BASE}/api/dashboard/wms-orders`),
      ]);
      setSummary(normalizeSummary(summaryData));
      setRecentFiles(Array.isArray(filesData) ? filesData : []);
      setWmsOrders(Array.isArray(wmsData) ? wmsData : []);
      setUsingMockData(false);
    } catch (err) {
      setSummary(mockSummary);
      setRecentFiles(mockRecentFiles);
      setWmsOrders(mockWmsOrders);
      setUsingMockData(true);
setError(
  `API service is asleep (Azure free-tier serverless cold start) — this can take 3–5 minutes on first load. ${err.message ? `(${err.message}) ` : ""}Showing mock data so the UI can still be tested.`
);    } finally {
      setLoading(false);
    }
  }
  async function triggerEdiFile() {
    setLoading(true);
    setError(null);

    try {
      const res = await authFetch(`${API_BASE}/api/actions/trigger-edi`, {
        method: "POST",
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok || data.success === false) {
        throw new Error(data.error || "EDI trigger failed");
      }

      await loadDashboard();
    } catch (err) {
      setError(err.message || "Failed to trigger EDI file.");
    } finally {
      setLoading(false);
    }
  }
  async function runEdiBatch() {
  setLoading(true);
  setError(null);

  try {
    const res = await authFetch(`${API_BASE}/api/adf/run`, {
      method: "POST",
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok || data.success === false) {
      throw new Error(data.error || "ADF batch run failed");
    }

    await loadDashboard();
  } catch (err) {
    setError(err.message || "Failed to start EDI batch.");
  } finally {
    setLoading(false);
  }
}
  async function simulateWmsPickup() {
    setLoading(true);
    setError(null);
    setSimulateMessage(null);

    try {
      const res = await authFetch(`${API_BASE}/api/wms/simulate-pickup`, {
        method: "POST",
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok || data.success === false) {
        throw new Error(data.error || "WMS pickup simulation failed");
      }

      setSimulateMessage(data.message || `Simulated WMS pickup for ${data.pickedUp ?? 0} order(s).`);
      await loadDashboard();
    } catch (err) {
      setError(err.message || "Failed to simulate WMS pickup.");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    if (isAuthenticated) {
      loadDashboard();
      loadPermissions();
    } else {
      setSummary(mockSummary);
      setRecentFiles(mockRecentFiles);
      setWmsOrders(mockWmsOrders);
      setUsingMockData(true);
      setPermissions([]);
    }
  }, [isAuthenticated]);

  function signIn() {
    instance.loginRedirect(loginRequest).catch(console.error);
  }

  function signOut() {
    instance.logoutRedirect();
  }

  const safeSummary = normalizeSummary(summary);
  const statusChart = useMemo(() => buildStatusChart(safeSummary), [summary]);

  const cards = [
    {
      title: "Files Waiting",
      value: safeSummary.filesWaiting ?? 0,
      age: safeSummary.oldestFileAgeSeconds ?? 0,
      icon: "clock",
      status: safeSummary.queueStatus ?? "GREEN"
    },
    {
      title: "Files Received",
      value: safeSummary.filesReceived,
      icon: "file"
    },
    {
      title: "Files Parsed",
      value: safeSummary.filesParsed,
      icon: "check"
    },
    {
      title: "Parse Errors",
      value: safeSummary.filesFailed,
      icon: "alert"
    },
    {
      title: "WMS Picked Up",
      value: safeSummary.wmsPickedUp,
      icon: "truck"
    }
  ];

  return <div className="page"><main className="shell">
    <header className="header">
      <div>
        <h1>EDI Dashboard</h1>
        <p>Warehouse Integration Demo</p>
        <a
          className="demo-link-btn"
          href="/architecture-demo.html"
          target="_blank"
          rel="noopener noreferrer"
        >
          <Icon type="play" />
          Watch the architecture demo
        </a>
      </div>

<div className="auth-badge">
  {isAuthenticated ? (
    <>
      <div className="user-info">
        <span>👤 {accounts[0]?.username}</span>
        <span className="auth-status">Authenticated</span>
      </div>
      <button onClick={toggleDemoAdmin} title="Demo-only role toggle - not a real Entra role">
        {canDownloadFiles ? "Revoke Admin (Demo)" : "Make me an Admin (Demo)"}
      </button>
      <button onClick={signOut}>Sign out</button>
    </>
  ) : (
    <>
      <button onClick={signIn}>Sign in with Microsoft for live data</button>
      <a className="demo-cta" href="https://www.chrisarnett.me" target="_blank" rel="noopener noreferrer">
        Or contact www.chrisarnett.me for a full guided demo
      </a>
    </>
  )}
</div>

{activeTab === "operations" && isAuthenticated && (
        <div className="header-actions">
          <button onClick={triggerEdiFile} disabled={loading}>
            <Icon type="play" />
            Create Test Files
          </button>

          <button onClick={runEdiBatch} disabled={loading}>
            <Icon type="database" />
            Run EDI Batch
          </button>

          <button onClick={loadDashboard} disabled={loading}>
            <Icon type="refresh" className={loading ? "spin" : ""} />
            Refresh
          </button>
        </div>
      )}
    </header>

    <div className="tabs">
      <button
        className={activeTab === "operations" ? "tab-active" : ""}
        onClick={() => setActiveTab("operations")}
      >
        EDI Monitor Dashboard
      </button>
      <button
        className={activeTab === "capacity" ? "tab-active" : ""}
        onClick={() => setActiveTab("capacity")}
      >
        Capacity Planning(Machine Learning)
      </button>
      {isAuthenticated && (
        <button
          className={activeTab === "reports" ? "tab-active" : ""}
          onClick={() => setActiveTab("reports")}
        >
          Reports
        </button>
      )}
      {canDownloadFiles && (
        <button
          className={activeTab === "admin" ? "tab-active" : ""}
          onClick={() => setActiveTab("admin")}
        >
          Admin
        </button>
      )}
    </div>

    {activeTab === "operations" && (
      <>
        {error && <section className="alert"><Icon type="alert" /><div><strong>API connection issue</strong><p>{error}</p></div></section>}
        {usingMockData && (
          <section className="mock">
            {isAuthenticated
              ? `Mock mode is active. Start the FastAPI service at ${API_BASE} to show live SQL data.`
              : "You're viewing demo data, feel free to browse both EDI Dashboard and Capacity Planning, or Sign in with Microsoft to see live pipeline data and run real actions."}
          </section>
        )}
        {simulateMessage && (
          <section className="mock">
            {simulateMessage}
          </section>
        )}
        <section className="cards">
          {cards.map((card) => (
            <article
              className={`card ${
                card.title === "Files Waiting" ? queueClass(card.age) : ""
              }`}
              key={card.title}
            >
              <div>
                <span>{card.title}</span>
                <b>{card.value}</b>

                {card.title === "Files Waiting" && (
                  <small>Oldest Age: {formatAge(card.age)}</small>
                )}
              </div>

              <Icon type={card.icon} />
            </article>
          ))}

          <article className="card action-card" onClick={() => (isAuthenticated ? setChatOpen(true) : signIn())}>
            <div>
              <span>Support</span>
              <b>Ask PO / ISA</b>
            </div>
          </article>

          <article className="card action-card" onClick={isAuthenticated ? simulateWmsPickup : signIn}>
            <div>
              <span>Simulation</span>
              <b>WMS Pickup</b>
            </div>
            <Icon type="truck" />
          </article>
        </section>

        <section className="panel">
          <h2><Icon type="database" />Pipeline Status Counts</h2>
          <div className="chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={statusChart}>
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="count" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        {chatOpen && (
          <ChatPanel onClose={() => setChatOpen(false)} canDownloadFiles={canDownloadFiles} />
        )}

        <section className="grid">
          <div className="panel">
            <h2>Recent EDI Files</h2>
            <table>
              <thead>
                <tr>
                  <th>ISA</th>
                  <th>Sender</th>
                  <th>File</th>
                  <th>Status</th>
                  <th>Loaded</th>
                  <th>Error</th>
                  {canDownloadFiles && <th>File</th>}
                </tr>
              </thead>
              <tbody>
                {recentFiles.length === 0 ? (
                  <tr><td colSpan={canDownloadFiles ? "7" : "6"}>No recent files found.</td></tr>
                ) : (
                  recentFiles.map(f => (
                    <tr key={f.rawId ?? f.fileName}>
                      <td>{f.isaControlNumber || "—"}</td>
                      <td>{f.isaSender || "—"}</td>

                      <td className="file-name-cell" title={f.fileName}>
                        {f.fileName}
                      </td>

                      <td><StatusBadge status={f.processStatus} /></td>
                      <td>{f.loadDateTime || "—"}</td>
                      <td className="error-text">{f.errorMessage || "—"}</td>
                      {canDownloadFiles && (
                        <td>
                          {f.rawId != null && (
                            <button type="button" onClick={() => downloadFile(f.rawId)}>
                              Download
                            </button>
                          )}
                        </td>
                      )}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="panel">
            <h2>WMS Staging Queue</h2>
            <table>
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Status</th>
                  <th>Attempts</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {wmsOrders.length === 0 ? (
                  <tr><td colSpan="4">No WMS staging orders found.</td></tr>
                ) : (
                  wmsOrders.map(o => (
                    <tr key={o.wmsOrderHeaderStagingId ?? o.warehouseOrderNumber}>
                      <td>{o.warehouseOrderNumber}</td>
                      <td><StatusBadge status={o.integrationStatus} /></td>
                      <td>{o.attemptCount ?? 0}</td>
                      <td className="error-text">{o.errorMessage || "—"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      </>
    )}

    {activeTab === "capacity" && <CapacityDashboard />}

    {activeTab === "reports" && isAuthenticated && <ReportsDashboard />}

    {activeTab === "admin" && canDownloadFiles && <AdminChangeRequests />}
  </main></div >;
}
