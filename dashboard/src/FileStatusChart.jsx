import React, { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { authFetch } from "./apiClient.js";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export default function FileStatusChart() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await authFetch(`${API_BASE}/api/reports/file-status-summary`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        setData(Array.isArray(json) ? json : []);
      } catch (err) {
        setError(err.message || "Failed to load file status data.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const displayData = data.map((row) => ({
    sender: row.sender || "(unknown)",
    received: row.received || 0,
    errored: row.errored || 0,
  }));

  return (
    <section className="panel">
      <h2>Files Received vs Errored per Client — Last 48 Hours</h2>

      {loading && <p>Loading…</p>}

      {error && (
        <p style={{ color: "var(--danger, #ef4444)" }}>Error: {error}</p>
      )}

      {!loading && !error && displayData.length === 0 && (
        <p>No files received in the last 48 hours.</p>
      )}

      {!loading && !error && displayData.length > 0 && (
        <div className="chart">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={displayData}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="sender" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Bar dataKey="received" name="Received" stackId="files" fill="#22c55e" />
              <Bar dataKey="errored" name="Errored" stackId="files" fill="#ef4444" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
