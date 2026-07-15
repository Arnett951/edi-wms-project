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

const COLORS = [
  "#6366f1", "#f59e0b", "#10b981", "#ef4444", "#3b82f6",
  "#8b5cf6", "#f97316", "#14b8a6", "#ec4899", "#84cc16",
];

function getLast7Dates() {
  const dates = [];
  const today = new Date();
  for (let i = 6; i >= 0; i--) {
    const d = new Date(today);
    d.setUTCDate(d.getUTCDate() - i);
    dates.push(d.toISOString().slice(0, 10));
  }
  return dates;
}

export default function InboundByCustomerChart() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await authFetch(
          `${API_BASE}/api/reports/inbound-files-by-customer`
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        setData(Array.isArray(json) ? json : []);
      } catch (err) {
        setError(err.message || "Failed to load inbound files data.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const senders = [...new Set(data.map((r) => r.sender))].sort();
  const dates = getLast7Dates();
  const chartData = dates.map((date) => {
    const row = { date: date.slice(5) };
    senders.forEach((sender) => {
      const found = data.find((r) => r.date === date && r.sender === sender);
      row[sender] = found ? found.count : 0;
    });
    return row;
  });

  return (
    <section className="panel">
      <h2>Inbound Files by Customer — Last 7 Days</h2>

      {loading && <p>Loading…</p>}

      {error && (
        <p style={{ color: "var(--danger, #ef4444)" }}>Error: {error}</p>
      )}

      {!loading && !error && (
        <div className="chart">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Legend />
              {senders.map((sender, i) => (
                <Bar
                  key={sender}
                  dataKey={sender}
                  stackId="a"
                  fill={COLORS[i % COLORS.length]}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {!loading && !error && senders.length === 0 && (
        <p style={{ color: "var(--muted, #6b7280)" }}>
          No inbound files received in the last 7 days.
        </p>
      )}
    </section>
  );
}
