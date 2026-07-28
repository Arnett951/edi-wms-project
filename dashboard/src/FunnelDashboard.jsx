import React, { useEffect, useState } from "react";
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
// Every inbound file lands in exactly one bucket, so the four counts always
// sum to the total files received - see sql/views/dbo.vw_FileReconciliation.sql
// for the rollup rule ("worst status wins" across a file's orders).
const FILE_STATUS_ORDER = ["Delivered", "In Progress", "Needs Attention", "Parse Failed"];
const FILE_STATUS_FILL = {
  Delivered: GREEN_FILL,
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
  { RawId: 14, FileName: "sample_940_2.edi", LoadDateTime: "2026-07-24 17:51:15", ProcessStatus: "STAGED", OrderCount: 1, SuccessCount: 1, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Delivered", AttentionReason: null },
  { RawId: 13, FileName: "sample_940.edi", LoadDateTime: "2026-07-24 17:48:02", ProcessStatus: "STAGED", OrderCount: 1, SuccessCount: 1, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Delivered", AttentionReason: null },
  { RawId: 12, FileName: "sample_940_3.edi", LoadDateTime: "2026-07-24 17:44:37", ProcessStatus: "STAGED", OrderCount: 1, SuccessCount: 1, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Delivered", AttentionReason: null },
  { RawId: 11, FileName: "order_940_2216.edi", LoadDateTime: "2026-07-27 16:10:48", ProcessStatus: "STAGED", OrderCount: 1, SuccessCount: 0, FailedOrderCount: 0, InFlightCount: 1, FileStatus: "In Progress", AttentionReason: null },
  { RawId: 10, FileName: "order_940_2217.edi", LoadDateTime: "2026-07-27 15:20:11", ProcessStatus: "STAGED", OrderCount: 1, SuccessCount: 0, FailedOrderCount: 1, InFlightCount: 0, FileStatus: "Needs Attention", AttentionReason: "1 of 1 order(s) rejected by WMS: Invalid SKU on line 2" },
  { RawId: 9, FileName: "bad_940_missing_st.edi", LoadDateTime: "2026-07-24 17:51:15", ProcessStatus: "PARSE_FAILED", OrderCount: 0, SuccessCount: 0, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Parse Failed", AttentionReason: "No ST*940 transaction sets were parsed from this file." },
  { RawId: 8, FileName: "bad_940_bad_isa.edi", LoadDateTime: "2026-07-24 17:49:03", ProcessStatus: "PARSE_FAILED", OrderCount: 0, SuccessCount: 0, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Parse Failed", AttentionReason: "ISA segment failed control-number validation." },
  { RawId: 7, FileName: "bad_940_truncated.edi", LoadDateTime: "2026-07-24 17:46:51", ProcessStatus: "PARSE_FAILED", OrderCount: 0, SuccessCount: 0, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Parse Failed", AttentionReason: "File ended before an SE segment was found." },
  { RawId: 6, FileName: "bad_940_dup_isa.edi", LoadDateTime: "2026-07-24 17:45:20", ProcessStatus: "PARSE_FAILED", OrderCount: 0, SuccessCount: 0, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Parse Failed", AttentionReason: "Duplicate ISA control number." },
  { RawId: 5, FileName: "bad_940_bad_gs.edi", LoadDateTime: "2026-07-24 17:43:12", ProcessStatus: "PARSE_FAILED", OrderCount: 0, SuccessCount: 0, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Parse Failed", AttentionReason: "GS segment count did not match trailer." },
  { RawId: 4, FileName: "bad_940_empty.edi", LoadDateTime: "2026-07-24 17:41:55", ProcessStatus: "PARSE_FAILED", OrderCount: 0, SuccessCount: 0, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Parse Failed", AttentionReason: "File was empty." },
  { RawId: 3, FileName: "bad_940_bad_st.edi", LoadDateTime: "2026-07-24 17:40:08", ProcessStatus: "PARSE_FAILED", OrderCount: 0, SuccessCount: 0, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Parse Failed", AttentionReason: "ST segment count did not match SE trailer." },
  { RawId: 2, FileName: "bad_940_bad_encoding.edi", LoadDateTime: "2026-07-24 17:38:44", ProcessStatus: "PARSE_FAILED", OrderCount: 0, SuccessCount: 0, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Parse Failed", AttentionReason: "File was not valid ASCII/EDI text." },
  { RawId: 1, FileName: "bad_940_missing_gs.edi", LoadDateTime: "2026-07-24 17:36:19", ProcessStatus: "PARSE_FAILED", OrderCount: 0, SuccessCount: 0, FailedOrderCount: 0, InFlightCount: 0, FileStatus: "Parse Failed", AttentionReason: "No GS segment was found in this file." },
];

function formatAge(minutes) {
  if (minutes == null) return "—";
  if (minutes < 60) return `${minutes} min`;
  return `${(minutes / 60).toFixed(1)} hr`;
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

  useEffect(() => {
    async function load() {
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
    load();
  }, []);

  useEffect(() => {
    async function load() {
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
    load();
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
  const actionableFiles = fileRows
    .filter((r) => ACTIONABLE_STATUSES.has(r.FileStatus))
    .slice(0, 20);

  return (
    <>
      <section className="panel">
        <h2>File Reconciliation</h2>
        <p className="admin-lede">
          Every inbound file, accounted for from receipt through WMS delivery. A file
          lands in exactly one bucket below, so the four counts always add up to
          Files In — "Needs Attention" and "Parse Failed" are the ones that need
          action.
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
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Loaded</th>
                <th>Status</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {actionableFiles.map((r) => (
                <tr key={r.RawId}>
                  <td>{r.FileName}</td>
                  <td>{r.LoadDateTime}</td>
                  <td>
                    <span className="status-badge bad">{r.FileStatus}</span>
                  </td>
                  <td>{r.AttentionReason || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
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
    </>
  );
}
