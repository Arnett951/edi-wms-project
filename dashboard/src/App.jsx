import React, { useEffect, useMemo, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { buildStatusChart, normalizeSummary, statusClass } from "./dashboardUtils";

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
  if (type === "refresh") return <svg {...props}><path d="M21 12a9 9 0 0 1-15.5 6.3"/><path d="M3 12A9 9 0 0 1 18.5 5.7"/><path d="M18 2v4h-4"/><path d="M6 22v-4h4"/></svg>;
  if (type === "alert") return <svg {...props}><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>;
  if (type === "check") return <svg {...props}><path d="M22 11.1V12a10 10 0 1 1-5.9-9.1"/><path d="m9 11 3 3L22 4"/></svg>;
  if (type === "database") return <svg {...props}><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5"/><path d="M3 12c0 1.7 4 3 9 3s9-1.3 9-3"/></svg>;
  if (type === "truck") return <svg {...props}><path d="M10 17h4V5H2v12h3"/><path d="M14 17h1"/><path d="M15 7h4l3 4v6h-3"/><circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/></svg>;
  return <svg {...props}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/></svg>;
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url} returned HTTP ${response.status}`);
  return response.json();
}

function StatusBadge({ status }) {
  return <span className={`status-badge ${statusClass(status)}`}>{status || "UNKNOWN"}</span>;
}

export default function App() {
  const [summary, setSummary] = useState(null);
  const [recentFiles, setRecentFiles] = useState([]);
  const [wmsOrders, setWmsOrders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [usingMockData, setUsingMockData] = useState(false);
  const [error, setError] = useState(null);

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
      setError(`${err.message || "Failed to load dashboard."} Showing mock data so the UI can still be tested.`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadDashboard(); }, []);

  const safeSummary = normalizeSummary(summary);
  const statusChart = useMemo(() => buildStatusChart(safeSummary), [summary]);
  const cards = [
    ["Files Received", safeSummary.filesReceived, "file"],
    ["Files Parsed", safeSummary.filesParsed, "check"],
    ["Parse Errors", safeSummary.filesFailed, "alert"],
    ["WMS Picked Up", safeSummary.wmsPickedUp, "truck"],
  ];

  return <div className="page"><main className="shell">
    <header className="header">
  <div>
    <h1>EDI 940 → WMS Dashboard</h1>
    <p>Inbound files, parser status, staging queue, and WMS lifecycle visibility.</p>
  </div>

  <div className="header-actions">
    <button onClick={triggerEdiFile} disabled={loading}>
      <Icon type="play" />
      Trigger EDI
    </button>

    <button onClick={loadDashboard} disabled={loading}>
      <Icon type="refresh" className={loading ? "spin" : ""} />
      Refresh
    </button>
  </div>
</header>
    {error && <section className="alert"><Icon type="alert"/><div><strong>API connection issue</strong><p>{error}</p></div></section>}
    {usingMockData && <section className="mock">Mock mode is active. Start the FastAPI service at {API_BASE} to show live SQL data.</section>}
    <section className="cards">{cards.map(([label, value, icon]) => <article className="card" key={label}><div><span>{label}</span><b>{value}</b></div><Icon type={icon}/></article>)}</section>
    <section className="panel"><h2><Icon type="database"/>Pipeline Status Counts</h2><div className="chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={statusChart}><XAxis dataKey="name" tick={{fontSize: 12}}/><YAxis allowDecimals={false}/><Tooltip/><Bar dataKey="count" radius={[8,8,0,0]}/></BarChart></ResponsiveContainer></div></section>
    <section className="grid"><div className="panel"><h2>Recent EDI Files</h2><table><thead><tr><th>File</th><th>Status</th><th>Loaded</th><th>Error</th></tr></thead><tbody>{recentFiles.length === 0 ? <tr><td colSpan="4">No recent files found.</td></tr> : recentFiles.map(f => <tr key={f.rawId ?? f.fileName}><td>{f.fileName}</td><td><StatusBadge status={f.processStatus}/></td><td>{f.loadDateTime || "—"}</td><td className="error-text">{f.errorMessage || "—"}</td></tr>)}</tbody></table></div>
    <div className="panel"><h2>WMS Staging Queue</h2><table><thead><tr><th>Order</th><th>Status</th><th>Attempts</th><th>Error</th></tr></thead><tbody>{wmsOrders.length === 0 ? <tr><td colSpan="4">No WMS staging orders found.</td></tr> : wmsOrders.map(o => <tr key={o.wmsOrderHeaderStagingId ?? o.warehouseOrderNumber}><td>{o.warehouseOrderNumber}</td><td><StatusBadge status={o.integrationStatus}/></td><td>{o.attemptCount ?? 0}</td><td className="error-text">{o.errorMessage || "—"}</td></tr>)}</tbody></table></div></section>
  </main></div>;
}
