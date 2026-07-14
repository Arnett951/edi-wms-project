import React, { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { authFetch } from "./apiClient.js";
import InboundByCustomerChart from "./InboundByCustomerChart.jsx";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export default function ReportsDashboard() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await authFetch(`${API_BASE}/api/reports/daily-volume`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        setData(Array.isArray(json) ? json : []);
      } catch (err) {
        setError(err.message || "Failed to load daily volume data.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const displayData = data.map((row) => ({
    date: row.date.slice(5),
    count: row.count,
  }));

  return (
    <>
      <section className="panel">
        <h2>Daily EDI 940 Volume — Last 30 Days</h2>

        {loading && <p>Loading…</p>}

        {error && (
          <p style={{ color: "var(--danger, #ef4444)" }}>Error: {error}</p>
        )}

        {!loading && !error && (
          <div className="chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={displayData}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11 }}
                  interval={4}
                />
                <YAxis allowDecimals={false} />
                <Tooltip
                  formatter={(value) => [value, "Files received"]}
                  labelFormatter={(label) => `Date: ${label}`}
                />
                <Line
                  type="monotone"
                  dataKey="count"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      <InboundByCustomerChart />
    </>
  );
}
