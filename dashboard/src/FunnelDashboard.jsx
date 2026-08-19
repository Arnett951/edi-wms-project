import React, { useEffect, useMemo, useState } from "react";
import { authFetch } from "./apiClient.js";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const STALE_THRESHOLD_MINUTES = 60;

// Happy-path stages shown as the funnel shape, in pipeline order.
// Parse Failed / WMS Failed are terminal drop-offs, so they're called out
// separately rather than bent into a monotonic funnel.
const FUNNEL_GATE_ORDER = [
  "Files Received",
  "Parsed Successfully",
  "WMS Awaiting Pickup",
  "WMS Sent",
  "WMS Success",
];

const NEUTRAL_FILL = "#2f6fd6";
const GREEN_FILL = "#22c55e";
const RED_FILL = "#ef4444";

// File Reconciliation buckets, in the order every file moves through them.
// "Reported to Customer" is a manual override (see the mass-select report
// tool below) that reconciles a file green without it ever having succeeded
// end to end - so every file still lands in exactly one bucket, and the
// five counts always sum to the total files received. See
// sql/views/dbo.vw_FileReconciliation.sql for the rollup rule ("worst
// status wins", overridden by a customer-reported timestamp).
const FILE_STATUS_ORDER = ["Delivered", "Reported to Customer", "In Progress", "Needs Attention", "Parse Failed"];
const FILE_STATUS_FILL = {
  Delivered: GREEN_FILL,
  "Reported to Customer": "#0ea5e9",
  "In Progress": NEUTRAL_FILL,
  "Needs Attention": RED_FILL,
  "Parse Failed": "#b91c1c",
};
const ACTIONABLE_STATUSES = new Set(["Needs Attention", "Parse Failed"]);

const mockFunnelGates = [
  { GateName: "Files Received", GateOrder: 1, IsMonitoredGate: 0, ItemCount: 14, OldestItemDateTime: "2026-07-24 17:51:15", OldestItemAgeMinutes: 4269, GateStatusColor: "GREEN" },
  { GateName: "Parsed Successfully", GateOrder: 2, IsMonitoredGate: 1, ItemCount: 0, OldestItemDateTime: null, OldestItemAgeMinutes: null, GateStatusColor: "GREEN" },
  { GateName: "Parse Failed", GateOrder: 3, IsMonitoredGate: 0, ItemCount: 9, OldestItemDateTime: "2026-07-24 17:51:15", OldestItemAgeMinutes: 4269, GateStatusColor: "GREEN" },
  { GateName: "WMS Awaiting Pickup", GateOrder: 4, IsMonitoredGate: 1, ItemCount: 2, OldestItemDateTime: "2026-07-27 16:10:48", OldestItemAgeMinutes: 50, GateStatusColor: "GREEN" },
  { GateName: "WMS Sent", GateOrder: 5, IsMonitoredGate: 0, ItemCount: 0, OldestItemDateTime: null, OldestItemAgeMinutes: null, GateStatusColor: "GREEN" },
  { GateName: "WMS Success", GateOrder: 6, IsMonitoredGate: 0, ItemCount: 3, OldestItemDateTime: "2026-07-24 17:52:11", OldestItemAgeMinutes: 4268, GateStatusColor: "GREEN" },
  { GateName: "WMS Failed", GateOrder: 7, IsMonitoredGate: 0, ItemCount: 0, OldestItemDateTime: null, OldestItemAgeMinutes: null, GateStatusColor: "GREEN" },
];

const mockFileReconciliation = [
  { RawId: 14, FileName: "sample_940_2.edi", ISASender: "LOW", ISA_ControlNumber: "000000141", LoadDateTime: "2026-07-24 17:51:15", ProcessStatus: "STAGED", OrderCount: 1, SuccessCount: 1, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Delivered", AttentionReason: null, CustomerReportedDateTime: null, CustomerReportedBy: null },
  { RawId: 13, FileName: "sample_940.edi", ISASender: "TGT", ISA_ControlNumber: "000000140", LoadDateTime: "2026-07-24 17:48:02", ProcessStatus: "STAGED", OrderCount: 1, SuccessCount: 1, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Delivered", AttentionReason: null, CustomerReportedDateTime: null, CustomerReportedBy: null },
  { RawId: 12, FileName: "sample_940_3.edi", ISASender: "LOW", ISA_ControlNumber: "000000139", LoadDateTime: "2026-07-24 17:44:37", ProcessStatus: "STAGED", OrderCount: 1, SuccessCount: 1, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Delivered", AttentionReason: null, CustomerReportedDateTime: null, CustomerReportedBy: null },
  { RawId: 11, FileName: "order_940_2216.edi", ISASender: "HD", ISA_ControlNumber: "000000138", LoadDateTime: "2026-07-27 16:10:48", ProcessStatus: "STAGED", OrderCount: 1, SuccessCount: 0, FailedOrderCount: 0, InFlightCount: 1, FileStatus: "In Progress", AttentionReason: null, CustomerReportedDateTime: null, CustomerReportedBy: null },
  { RawId: 10, FileName: "order_940_2217.edi", ISASender: "LOW", ISA_ControlNumber: "000000137", LoadDateTime: "2026-07-27 15:20:11", ProcessStatus: "STAGED", OrderCount: 1, SuccessCount: 0, FailedOrderCount: 1, InFlightCount: 0, FileStatus: "Needs Attention", AttentionReason: "1 of 1 order(s) rejected by WMS: Invalid SKU on line 2", CustomerReportedDateTime: null, CustomerReportedBy: null },
  { RawId: 9, FileName: "bad_940_missing_st.edi", ISASender: "LOW", ISA_ControlNumber: null, LoadDateTime: "2026-07-24 17:51:15", ProcessStatus: "PARSE_FAILED", OrderCount: 0, SuccessCount: 0, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Parse Failed", AttentionReason: "No ST*940 transaction sets were parsed from this file.", CustomerReportedDateTime: null, CustomerReportedBy: null },
  { RawId: 8, FileName: "bad_940_bad_isa.edi", ISASender: "TGT", ISA_ControlNumber: null, LoadDateTime: "2026-07-24 17:49:03", ProcessStatus: "PARSE_FAILED", OrderCount: 0, SuccessCount: 0, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Parse Failed", AttentionReason: "ISA segment failed control-number validation.", CustomerReportedDateTime: null, CustomerReportedBy: null },
  { RawId: 7, FileName: "bad_940_truncated.edi", ISASender: "LOW", ISA_ControlNumber: null, LoadDateTime: "2026-07-24 17:46:51", ProcessStatus: "PARSE_FAILED", OrderCount: 0, SuccessCount: 0, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Parse Failed", AttentionReason: "File ended before an SE segment was found.", CustomerReportedDateTime: null, CustomerReportedBy: null },
  { RawId: 6, FileName: "bad_940_dup_isa.edi", ISASender: "HD", ISA_ControlNumber: null, LoadDateTime: "2026-07-24 17:45:20", ProcessStatus: "PARSE_FAILED", OrderCount: 0, SuccessCount: 0, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Parse Failed", AttentionReason: "Duplicate ISA control number.", CustomerReportedDateTime: null, CustomerReportedBy: null },
  { RawId: 5, FileName: "bad_940_bad_gs.edi", ISASender: "LOW", ISA_ControlNumber: null, LoadDateTime: "2026-07-24 17:43:12", ProcessStatus: "PARSE_FAILED", OrderCount: 0, SuccessCount: 0, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Parse Failed", AttentionReason: "GS segment count did not match trailer.", CustomerReportedDateTime: null, CustomerReportedBy: null },
  { RawId: 4, FileName: "bad_940_empty.edi", ISASender: "LOW", ISA_ControlNumber: null, LoadDateTime: "2026-07-24 17:41:55", ProcessStatus: "PARSE_FAILED", OrderCount: 0, SuccessCount: 0, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Parse Failed", AttentionReason: "File was empty.", CustomerReportedDateTime: null, CustomerReportedBy: null },
  { RawId: 3, FileName: "bad_940_bad_st.edi", ISASender: "TGT", ISA_ControlNumber: null, LoadDateTime: "2026-07-24 17:40:08", ProcessStatus: "PARSE_FAILED", OrderCount: 0, SuccessCount: 0, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Parse Failed", AttentionReason: "ST segment count did not match SE trailer.", CustomerReportedDateTime: null, CustomerReportedBy: null },
  { RawId: 2, FileName: "bad_940_bad_encoding.edi", ISASender: "LOW", ISA_ControlNumber: null, LoadDateTime: "2026-07-24 17:38:44", ProcessStatus: "PARSE_FAILED", OrderCount: 0, SuccessCount: 0, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Parse Failed", AttentionReason: "File was not valid ASCII/EDI text.", CustomerReportedDateTime: null, CustomerReportedBy: null },
  { RawId: 1, FileName: "bad_940_missing_gs.edi", ISASender: "LOW", ISA_ControlNumber: null, LoadDateTime: "2026-07-24 17:36:19", ProcessStatus: "PARSE_FAILED", OrderCount: 0, SuccessCount: 0, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Parse Failed", AttentionReason: "No GS segment was found in this file.", CustomerReportedDateTime: null, CustomerReportedBy: null },
];

function formatAge(minutes) {
  if (minutes == null) return "—";
  if (minutes < 60) return `${minutes} min`;
  return `${(minutes / 60).toFixed(1)} hr`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Builds a small self-contained HTML exception report for one customer:
// ISA control #, file, PO, line, and error per row. Meant to be downloaded
// and attached to (or pasted into) the email the mass-select tool drafts.
function buildCustomerReportHtml(customerLabel, detailRows) {
  const generated = new Date().toISOString().slice(0, 16).replace("T", " ") + " UTC";
  const bodyRows = detailRows
    .map(
      (d) => `
        <tr>
          <td>${escapeHtml(d.isaControlNumber || "—")}</td>
          <td>${escapeHtml(d.fileName)}</td>
          <td>${escapeHtml(d.po)}</td>
          <td>${escapeHtml(d.lineItem)}</td>
          <td>${escapeHtml(d.errorMessage)}</td>
        </tr>`
    )
    .join("");

  return `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>EDI Exceptions — ${escapeHtml(customerLabel)}</title>
<style>
  body { font-family: Arial, Helvetica, sans-serif; color: #0f172a; padding: 24px; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  p.meta { color: #64748b; font-size: 13px; margin: 0 0 20px; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { border: 1px solid #e2e8f0; padding: 8px 10px; text-align: left; vertical-align: top; }
  th { background: #f1f5f9; color: #475569; }
</style>
</head>
<body>
  <h1>EDI Exception Report — ${escapeHtml(customerLabel)}</h1>
  <p class="meta">Generated ${escapeHtml(generated)} · ${detailRows.length} line(s)</p>
  <table>
    <thead>
      <tr><th>ISA Control #</th><th>File</th><th>PO</th><th>Line</th><th>Error</th></tr>
    </thead>
    <tbody>${bodyRows}</tbody>
  </table>
</body>
</html>`;
}

function buildMailtoLink(to, customerLabel, detailRows) {
  const subject = `EDI Exceptions — ${customerLabel} — ${new Date().toISOString().slice(0, 10)}`;
  const lines = detailRows.map(
    (d) => `ISA ${d.isaControlNumber || "—"} | ${d.fileName} | PO ${d.po} | ${d.lineItem} | ${d.errorMessage}`
  );
  const body = [`The following ${detailRows.length} exception(s) need review:`, "", ...lines].join("\n");
  return `mailto:${encodeURIComponent(to)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

export default function FunnelDashboard() {
  const [gates, setGates] = useState(mockFunnelGates);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [usingMockData, setUsingMockData] = useState(true);

  const [fileRows, setFileRows] = useState(mockFileReconciliation);
  const [fileLoading, setFileLoading] = useState(true);
  const [fileError, setFileError] = useState(null);
  const [usingMockFileData, setUsingMockFileData] = useState(true);

  const [customerFilter, setCustomerFilter] = useState("");
  const [selectedIds, setSelectedIds] = useState(new Set());

  const [reportOpen, setReportOpen] = useState(false);
  const [reportDetail, setReportDetail] = useState([]);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState(null);
  const [reportHtml, setReportHtml] = useState("");
  const [mailTo, setMailTo] = useState("");
  const [marking, setMarking] = useState(false);
  const [markMessage, setMarkMessage] = useState(null);

  async function loadFunnel() {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/api/dashboard/funnel`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      if (Array.isArray(json) && json.length > 0) {
        setGates(json);
        setUsingMockData(false);
      } else {
        setGates(mockFunnelGates);
        setUsingMockData(true);
      }
    } catch (err) {
      setGates(mockFunnelGates);
      setUsingMockData(true);
      setError(err.message || "Failed to load funnel data.");
    } finally {
      setLoading(false);
    }
  }

  async function loadFileReconciliation() {
    setFileLoading(true);
    setFileError(null);
    try {
      const res = await authFetch(`${API_BASE}/api/dashboard/file-reconciliation`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      if (Array.isArray(json) && json.length > 0) {
        setFileRows(json);
        setUsingMockFileData(false);
      } else {
        setFileRows(mockFileReconciliation);
        setUsingMockFileData(true);
      }
    } catch (err) {
      setFileRows(mockFileReconciliation);
      setUsingMockFileData(true);
      setFileError(err.message || "Failed to load file reconciliation data.");
    } finally {
      setFileLoading(false);
    }
  }

  useEffect(() => {
    loadFunnel();
    loadFileReconciliation();
  }, []);

  const byName = Object.fromEntries(gates.map((g) => [g.GateName, g]));

  const funnelData = FUNNEL_GATE_ORDER.map((name) => byName[name])
    .filter(Boolean)
    .map((g) => ({
      name: g.GateName,
      value: g.ItemCount,
      fill: g.IsMonitoredGate
        ? g.GateStatusColor === "RED"
          ? RED_FILL
          : GREEN_FILL
        : NEUTRAL_FILL,
    }));

  const maxValue = Math.max(1, ...funnelData.map((d) => d.value));

  const failedGates = gates.filter((g) => /Failed/i.test(g.GateName));
  const monitoredGates = gates.filter((g) => g.IsMonitoredGate);

  const filesInTotal = fileRows.length;
  const fileBuckets = FILE_STATUS_ORDER.map((status) => ({
    status,
    count: fileRows.filter((r) => r.FileStatus === status).length,
    fill: FILE_STATUS_FILL[status],
  }));
  const maxFileBucket = Math.max(1, ...fileBuckets.map((b) => b.count));

  const actionableFiles = fileRows.filter((r) => ACTIONABLE_STATUSES.has(r.FileStatus));
  const customers = useMemo(
    () => Array.from(new Set(actionableFiles.map((r) => r.ISASender).filter(Boolean))).sort(),
    [actionableFiles]
  );
  const visibleFiles = (customerFilter ? actionableFiles.filter((r) => r.ISASender === customerFilter) : actionableFiles).slice(0, 20);

  // Selection is scoped to a single customer at a time so a generated report
  // never mixes two customers' exceptions in one email/file.
  const selectedRows = fileRows.filter((r) => selectedIds.has(r.RawId));
  const selectedCustomer = selectedRows[0]?.ISASender || null;
  const allVisibleSelected = visibleFiles.length > 0 && visibleFiles.every((r) => selectedIds.has(r.RawId));

  function toggleRow(row) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(row.RawId)) {
        next.delete(row.RawId);
      } else {
        next.add(row.RawId);
      }
      return next;
    });
  }

  function toggleSelectAllVisible() {
    setSelectedIds((prev) => {
      if (allVisibleSelected) {
        const next = new Set(prev);
        visibleFiles.forEach((r) => next.delete(r.RawId));
        return next;
      }
      // Starting a fresh selection from the visible (already customer-
      // filtered, if a filter is set) rows keeps it single-customer.
      return new Set(visibleFiles.map((r) => r.RawId));
    });
  }

  function clearSelection() {
    setSelectedIds(new Set());
  }

  async function openReportModal() {
    setReportOpen(true);
    setReportLoading(true);
    setReportError(null);
    setMarkMessage(null);
    setMailTo("");
    try {
      const idsParam = Array.from(selectedIds).join(",");
      const res = await authFetch(
        `${API_BASE}/api/dashboard/file-reconciliation/report-detail?raw_ids=${idsParam}`
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const detail = await res.json();
      setReportDetail(detail);
      setReportHtml(buildCustomerReportHtml(selectedCustomer || "Customer", detail));
    } catch (err) {
      setReportError(err.message || "Failed to build report.");
    } finally {
      setReportLoading(false);
    }
  }

  function closeReportModal() {
    setReportOpen(false);
    setReportDetail([]);
    setReportHtml("");
    setReportError(null);
    setMarkMessage(null);
  }

  function downloadReport() {
    const blob = new Blob([reportHtml], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `edi-exceptions-${(selectedCustomer || "customer").toLowerCase()}-${new Date()
      .toISOString()
      .slice(0, 10)}.html`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async function markSelectedReported() {
    setMarking(true);
    setMarkMessage(null);
    try {
      const res = await authFetch(`${API_BASE}/api/dashboard/file-reconciliation/mark-reported`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rawIds: Array.from(selectedIds) }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setMarkMessage(`Marked ${selectedIds.size} file(s) as Reported to Customer.`);
      clearSelection();
      await loadFileReconciliation();
    } catch (err) {
      setMarkMessage(`Failed to mark files as reported: ${err.message || err}`);
    } finally {
      setMarking(false);
    }
  }

  return (
    <>
      <section className="panel">
        <h2>File Reconciliation</h2>
        <p className="admin-lede">
          Every inbound file, accounted for from receipt through WMS delivery. A file
          lands in exactly one bucket below, so the five counts always add up to
          Files In — "Needs Attention" and "Parse Failed" are the ones that still need
          action; "Reported to Customer" is handled.
        </p>

        {fileLoading && <p>Loading…</p>}
        {fileError && <p style={{ color: "var(--danger, #ef4444)" }}>Error: {fileError}</p>}
        {usingMockFileData && !fileLoading && (
          <p className="admin-lede">Showing mock data — sign in for live pipeline counts.</p>
        )}

        <p className="admin-lede" style={{ margin: "0 0 14px", fontWeight: 700, color: "#1f2937" }}>
          Files In: {filesInTotal}
        </p>

        <div className="funnel-bars">
          {fileBuckets.map((bucket) => {
            const widthPct = bucket.count > 0 ? Math.max(3, (bucket.count / maxFileBucket) * 100) : 0;
            return (
              <div className="funnel-bar-row" key={bucket.status}>
                <span className="funnel-bar-label">{bucket.status}</span>
                <div className="funnel-bar-track">
                  <div
                    className="funnel-bar-fill"
                    style={{ width: `${widthPct}%`, background: bucket.fill }}
                  />
                </div>
                <span className="funnel-bar-count">{bucket.count}</span>
              </div>
            );
          })}
        </div>

        {actionableFiles.length > 0 && (
          <>
            <div className="recon-toolbar">
              <div className="recon-toolbar-filter">
                <label htmlFor="recon-customer-filter">Customer</label>
                <select
                  id="recon-customer-filter"
                  value={customerFilter}
                  onChange={(e) => {
                    setCustomerFilter(e.target.value);
                    clearSelection();
                  }}
                >
                  <option value="">All customers</option>
                  {customers.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>

              {selectedIds.size > 0 && (
                <div className="recon-toolbar-selection">
                  <span>
                    {selectedIds.size} file(s) selected{selectedCustomer ? ` — ${selectedCustomer}` : ""}
                  </span>
                  <button className="link-btn" onClick={clearSelection} type="button">
                    Clear
                  </button>
                  <button onClick={openReportModal} type="button">
                    Generate Customer Report
                  </button>
                </div>
              )}
            </div>

            <table>
              <thead>
                <tr>
                  <th>
                    <input
                      type="checkbox"
                      checked={allVisibleSelected}
                      onChange={toggleSelectAllVisible}
                      aria-label="Select all visible files"
                    />
                  </th>
                  <th>Customer</th>
                  <th>File</th>
                  <th>Loaded</th>
                  <th>Status</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {visibleFiles.map((r) => {
                  const isSelected = selectedIds.has(r.RawId);
                  const isDisabled = selectedCustomer && r.ISASender !== selectedCustomer && !isSelected;
                  return (
                    <tr key={r.RawId} className={isSelected ? "recon-row-selected" : ""}>
                      <td>
                        <input
                          type="checkbox"
                          checked={isSelected}
                          disabled={isDisabled}
                          onChange={() => toggleRow(r)}
                          title={isDisabled ? "Clear the current selection to pick a different customer" : undefined}
                        />
                      </td>
                      <td>{r.ISASender || "—"}</td>
                      <td>{r.FileName}</td>
                      <td>{r.LoadDateTime}</td>
                      <td>
                        <span className="status-badge bad">{r.FileStatus}</span>
                      </td>
                      <td>{r.AttentionReason || "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </>
        )}
      </section>

      <section className="panel">
        <h2>Funnel Dashboard</h2>
        <p className="admin-lede">
          Live pipeline funnel from file receipt through WMS pickup. "Parsed Successfully"
          and "WMS Awaiting Pickup" turn red once the oldest item in that gate has been
          waiting more than {STALE_THRESHOLD_MINUTES} minutes.
        </p>

        {loading && <p>Loading…</p>}
        {error && <p style={{ color: "var(--danger, #ef4444)" }}>Error: {error}</p>}
        {usingMockData && !loading && (
          <p className="admin-lede">Showing mock data — sign in for live pipeline counts.</p>
        )}

        <div className="funnel-bars">
          {funnelData.map((stage) => {
            const widthPct = stage.value > 0 ? Math.max(3, (stage.value / maxValue) * 100) : 0;
            return (
              <div className="funnel-bar-row" key={stage.name}>
                <span className="funnel-bar-label">{stage.name}</span>
                <div className="funnel-bar-track">
                  <div
                    className="funnel-bar-fill"
                    style={{ width: `${widthPct}%`, background: stage.fill }}
                  />
                </div>
                <span className="funnel-bar-count">{stage.value}</span>
              </div>
            );
          })}
        </div>

        <div className="grid">
          <div className="panel">
            <h2>Gate Health</h2>
            <table>
              <thead>
                <tr>
                  <th>Gate</th>
                  <th>Count</th>
                  <th>Oldest Item Age</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {monitoredGates.map((g) => (
                  <tr key={g.GateName}>
                    <td>{g.GateName}</td>
                    <td>{g.ItemCount}</td>
                    <td>{formatAge(g.OldestItemAgeMinutes)}</td>
                    <td>
                      <span className={`status-badge ${g.GateStatusColor === "RED" ? "bad" : "good"}`}>
                        {g.GateStatusColor === "RED" ? "STALE" : "OK"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {failedGates.length > 0 && (
            <div className="panel">
              <h2>Drop-offs</h2>
              <table>
                <thead>
                  <tr>
                    <th>Gate</th>
                    <th>Count</th>
                  </tr>
                </thead>
                <tbody>
                  {failedGates.map((g) => (
                    <tr key={g.GateName}>
                      <td>{g.GateName}</td>
                      <td>{g.ItemCount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {reportOpen && (
        <div className="cr-modal-overlay" onClick={closeReportModal}>
          <div className="cr-modal" onClick={(e) => e.stopPropagation()}>
            <div className="cr-modal-header">
              <h2>Customer Exception Report — {selectedCustomer || "—"}</h2>
              <button className="cr-modal-close" onClick={closeReportModal} aria-label="Close">
                ×
              </button>
            </div>

            <div className="cr-modal-body">
              {reportLoading && <p>Building report…</p>}
              {reportError && <p style={{ color: "var(--danger, #ef4444)" }}>Error: {reportError}</p>}

              {!reportLoading && !reportError && (
                <>
                  <p className="admin-lede">
                    {reportDetail.length} line(s) across {selectedIds.size} file(s). Review below, then
                    download the report, open a mail draft, or mark these files as reported.
                  </p>

                  <div className="report-table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>ISA</th>
                          <th>File</th>
                          <th>PO</th>
                          <th>Line</th>
                          <th>Error</th>
                        </tr>
                      </thead>
                      <tbody>
                        {reportDetail.map((d, i) => (
                          <tr key={`${d.rawId}-${i}`}>
                            <td>{d.isaControlNumber || "—"}</td>
                            <td>{d.fileName}</td>
                            <td>{d.po}</td>
                            <td>{d.lineItem}</td>
                            <td>{d.errorMessage}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <h3>Send to customer</h3>
                  <div className="recon-mailto-row">
                    <input
                      type="email"
                      placeholder="customer-contact@example.com (optional)"
                      value={mailTo}
                      onChange={(e) => setMailTo(e.target.value)}
                    />
                    <a
                      className="link-btn"
                      href={buildMailtoLink(mailTo, selectedCustomer || "Customer", reportDetail)}
                    >
                      Open Email Draft
                    </a>
                  </div>

                  <div className="recon-modal-actions">
                    <button type="button" onClick={downloadReport}>
                      Download HTML Report
                    </button>
                    <button type="button" onClick={markSelectedReported} disabled={marking}>
                      {marking ? "Marking…" : "Mark as Reported to Customer"}
                    </button>
                  </div>

                  {markMessage && <p className="admin-lede">{markMessage}</p>}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
