import React, { useEffect, useState } from "react";
import {
  FunnelChart,
  Funnel,
  Cell,
  LabelList,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
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

const mockFunnelGates = [
  { GateName: "Files Received", GateOrder: 1, IsMonitoredGate: 0, ItemCount: 42, OldestItemDateTime: "2026-07-27 10:05:00", OldestItemAgeMinutes: 375, GateStatusColor: "GREEN" },
  { GateName: "Parsed Successfully", GateOrder: 2, IsMonitoredGate: 1, ItemCount: 38, OldestItemDateTime: "2026-07-27 14:10:00", OldestItemAgeMinutes: 75, GateStatusColor: "RED" },
  { GateName: "Parse Failed", GateOrder: 3, IsMonitoredGate: 0, ItemCount: 4, OldestItemDateTime: "2026-07-27 09:00:00", OldestItemAgeMinutes: 435, GateStatusColor: "GREEN" },
  { GateName: "WMS Awaiting Pickup", GateOrder: 4, IsMonitoredGate: 1, ItemCount: 12, OldestItemDateTime: "2026-07-27 15:00:00", OldestItemAgeMinutes: 25, GateStatusColor: "GREEN" },
  { GateName: "WMS Sent", GateOrder: 5, IsMonitoredGate: 0, ItemCount: 15, OldestItemDateTime: "2026-07-27 13:40:00", OldestItemAgeMinutes: 105, GateStatusColor: "GREEN" },
  { GateName: "WMS Success", GateOrder: 6, IsMonitoredGate: 0, ItemCount: 11, OldestItemDateTime: "2026-07-27 12:00:00", OldestItemAgeMinutes: 225, GateStatusColor: "GREEN" },
  { GateName: "WMS Failed", GateOrder: 7, IsMonitoredGate: 0, ItemCount: 1, OldestItemDateTime: "2026-07-27 11:00:00", OldestItemAgeMinutes: 285, GateStatusColor: "GREEN" },
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

  const failedGates = gates.filter((g) => /Failed/i.test(g.GateName));
  const monitoredGates = gates.filter((g) => g.IsMonitoredGate);

  return (
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

      <div className="chart" style={{ height: 320 }}>
        <ResponsiveContainer width="100%" height="100%">
          <FunnelChart>
            <Tooltip />
            <Funnel dataKey="value" data={funnelData} isAnimationActive={false}>
              <LabelList dataKey="name" position="right" fill="#1f2937" stroke="none" />
              {funnelData.map((entry) => (
                <Cell key={entry.name} fill={entry.fill} />
              ))}
            </Funnel>
          </FunnelChart>
        </ResponsiveContainer>
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
  );
}
