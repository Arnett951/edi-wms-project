import React, { useEffect, useRef, useState } from "react";
import { Chart } from "chart.js/auto";

// Linear regression trained on 30 days of pick/pack activity
// (packer-hours available & order complexity -> orders shipped, CV R^2 0.91).
const MODEL = {
  intercept: 157.3509363146291,
  coefPackerHours: 5.670364553091294,
  coefComplexity: -65.34606343082069,
  residualStd: 12.897217829187284,
};

const HISTORY = [
  { date: "2026-06-13", ordersShipped: 228, forecastedOrders: 218 },
  { date: "2026-06-14", ordersShipped: 211, forecastedOrders: 230 },
  { date: "2026-06-15", ordersShipped: 210, forecastedOrders: 192 },
  { date: "2026-06-16", ordersShipped: 274, forecastedOrders: 258 },
  { date: "2026-06-17", ordersShipped: 279, forecastedOrders: 290 },
  { date: "2026-06-18", ordersShipped: 299, forecastedOrders: 338 },
  { date: "2026-06-19", ordersShipped: 243, forecastedOrders: 234 },
  { date: "2026-06-20", ordersShipped: 190, forecastedOrders: 167 },
  { date: "2026-06-21", ordersShipped: 198, forecastedOrders: 210 },
  { date: "2026-06-22", ordersShipped: 269, forecastedOrders: 294 },
  { date: "2026-06-23", ordersShipped: 236, forecastedOrders: 259 },
  { date: "2026-06-24", ordersShipped: 230, forecastedOrders: 199 },
  { date: "2026-06-25", ordersShipped: 285, forecastedOrders: 254 },
  { date: "2026-06-26", ordersShipped: 225, forecastedOrders: 238 },
  { date: "2026-06-27", ordersShipped: 203, forecastedOrders: 204 },
  { date: "2026-06-28", ordersShipped: 200, forecastedOrders: 196 },
  { date: "2026-06-29", ordersShipped: 281, forecastedOrders: 264 },
  { date: "2026-06-30", ordersShipped: 367, forecastedOrders: 400 },
  { date: "2026-07-01", ordersShipped: 273, forecastedOrders: 283 },
  { date: "2026-07-02", ordersShipped: 244, forecastedOrders: 217 },
  { date: "2026-07-03", ordersShipped: 276, forecastedOrders: 270 },
  { date: "2026-07-04", ordersShipped: 164, forecastedOrders: 182 },
  { date: "2026-07-05", ordersShipped: 187, forecastedOrders: 206 },
  { date: "2026-07-06", ordersShipped: 254, forecastedOrders: 267 },
  { date: "2026-07-07", ordersShipped: 293, forecastedOrders: 331 },
  { date: "2026-07-08", ordersShipped: 277, forecastedOrders: 296 },
  { date: "2026-07-09", ordersShipped: 351, forecastedOrders: 389 },
  { date: "2026-07-10", ordersShipped: 276, forecastedOrders: 263 },
  { date: "2026-07-11", ordersShipped: 185, forecastedOrders: 199 },
  { date: "2026-07-12", ordersShipped: 208, forecastedOrders: 239 },
];

const AXIS_MAX = 450;
const Z_SCORE_80 = 1.28;

function pct(value) {
  return Math.max(0, Math.min(100, (value / AXIS_MAX) * 100));
}

function stepValues(min, max, step) {
  const decimals = (String(step).split(".")[1] || "").length;
  const factor = 10 ** decimals;
  const count = Math.round((max - min) / step);
  const values = [];
  for (let i = 0; i <= count; i++) {
    values.push(Math.round((min + i * step) * factor) / factor);
  }
  return values;
}

// Custom tick overlay: native <datalist> ticks don't render once a range
// input has -webkit-appearance: none (needed for the styled thumb), so we
// draw the step positions ourselves, positioned to line up with the thumb.
function TickMarks({ min, max, step, majorStep }) {
  return (
    <div className="cap-slider-ticks" aria-hidden="true">
      {stepValues(min, max, step).map((v) => {
        const isMajor = majorStep && Math.abs(Math.round(v / majorStep) * majorStep - v) < step / 2;
        return (
          <span
            key={v}
            className={isMajor ? "cap-tick-major" : undefined}
            style={{ left: `${((v - min) / (max - min)) * 100}%` }}
          ></span>
        );
      })}
    </div>
  );
}

export default function CapacityDashboard() {
  const [headcount, setHeadcount] = useState(5);
  const [shiftHours, setShiftHours] = useState(9);
  const [receiving, setReceiving] = useState(0);
  const [complexity, setComplexity] = useState(2.3);
  const [forecast, setForecast] = useState(280);

  const canvasRef = useRef(null);
  const chartRef = useRef(null);

  const packerHours = Math.max(0, headcount * shiftHours - receiving);
  const predicted =
    MODEL.intercept + MODEL.coefPackerHours * packerHours + MODEL.coefComplexity * complexity;
  const low = predicted - Z_SCORE_80 * MODEL.residualStd;
  const high = predicted + Z_SCORE_80 * MODEL.residualStd;
  const gap = predicted - forecast;

  let status = "ON TRACK";
  let statusClass = "cap-status-on";
  if (low >= forecast) {
    status = "ON TRACK";
    statusClass = "cap-status-on";
  } else if (high < forecast) {
    status = "AT RISK";
    statusClass = "cap-status-risk";
  } else {
    status = "TIGHT — WATCH CLOSELY";
    statusClass = "cap-status-tight";
  }

  // Build the chart once on mount.
  useEffect(() => {
    const labels = HISTORY.map((d) => d.date.slice(5));
    const shipped = HISTORY.map((d) => d.ordersShipped);
    const forecasted = HISTORY.map((d) => d.forecastedOrders);

    chartRef.current = new Chart(canvasRef.current.getContext("2d"), {
      type: "line",
      data: {
        labels: [...labels, "Today"],
        datasets: [
          {
            label: "Orders shipped",
            data: shipped,
            borderColor: "#3fa66b",
            backgroundColor: "rgba(63,166,107,0.08)",
            tension: 0.25,
            pointRadius: 2,
            borderWidth: 2,
          },
          {
            label: "Forecasted",
            data: [...forecasted, Math.round(forecast)],
            borderColor: "#7e8896",
            borderDash: [4, 3],
            pointRadius: 0,
            borderWidth: 1.5,
          },
          {
            label: "Today's projection",
            data: new Array(HISTORY.length).fill(null).concat([Math.round(predicted)]),
            pointRadius: new Array(HISTORY.length).fill(0).concat([6]),
            borderColor: "#f5a623",
            backgroundColor: "#f5a623",
            showLine: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: {
            labels: { color: "#7e8896", font: { family: "IBM Plex Mono", size: 11 }, boxWidth: 12 },
          },
        },
        scales: {
          x: { ticks: { color: "#4d5561", font: { size: 10 } }, grid: { color: "#232935" } },
          y: { ticks: { color: "#4d5561", font: { size: 10 } }, grid: { color: "#232935" } },
        },
      },
    });

    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep the "today" points in sync as sliders change, without rebuilding the chart.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const baseForecast = HISTORY.map((d) => d.forecastedOrders);
    chart.data.datasets[1].data = [...baseForecast, Math.round(forecast)];
    chart.data.datasets[2].data = new Array(HISTORY.length).fill(null).concat([Math.round(predicted)]);
    chart.update("none");
  }, [predicted, forecast]);

  return (
    <div className="capacity-widget">
      <div className="cap-eyebrow">Fulfillment Ops · Live Estimator</div>
      <h1 className="cap-title">Will today's crew ship today's orders?</h1>
      <p className="cap-subtitle">
        Linear regression trained on 30 days of pick/pack activity (packer-hours available &amp;
        order complexity → orders shipped, cross-validated R² 0.91). Adjust today's inputs below to
        see the live projection.
      </p>

      <div className="cap-panel cap-hero">
        <div>
          <div className={`cap-status-badge ${statusClass}`}>
            <span className="cap-dot"></span>
            <span>{status}</span>
          </div>
          <div className="cap-readout-row">
            <div
              className="cap-readout-main"
              style={{
                color:
                  statusClass === "cap-status-on"
                    ? "var(--cap-green)"
                    : statusClass === "cap-status-risk"
                    ? "var(--cap-red)"
                    : "var(--cap-amber)",
              }}
            >
              {Math.round(predicted)}
            </div>
            <div className="cap-readout-unit">orders capacity</div>
          </div>
          <div className="cap-readout-caption">vs. {Math.round(forecast)} forecasted today</div>
          <div className="cap-readout-range">
            80% range: {Math.round(low)}–{Math.round(high)} orders &nbsp;·&nbsp; gap:{" "}
            {gap >= 0 ? "+" : ""}
            {Math.round(gap)} orders
          </div>

          <div className="cap-scale">
            <div className="cap-scale-track">
              <div
                className="cap-scale-band"
                style={{ left: `${pct(low)}%`, width: `${Math.max(0.5, pct(high) - pct(low))}%` }}
              ></div>
              <div
                className="cap-scale-marker"
                data-label="Forecast"
                style={{ left: `${pct(forecast)}%` }}
              ></div>
            </div>
            <div className="cap-scale-ticks">
              {[0, 100, 200, 300, 400].map((tick) => (
                <span key={tick}>{tick}</span>
              ))}
            </div>
          </div>
        </div>

        <div>
          <div className="cap-panel-label">
            <span>Today's Inputs</span>
          </div>
          <div className="cap-controls-grid" style={{ gridTemplateColumns: "1fr" }}>
            <div className="cap-control">
              <label htmlFor="cap-headcount">
                Packers on shift <span className="cap-value">{headcount}</span>
              </label>
              <div className="cap-slider-wrap">
                <input
                  id="cap-headcount"
                  type="range"
                  min="2"
                  max="8"
                  step="1"
                  value={headcount}
                  onChange={(e) => setHeadcount(Number(e.target.value))}
                />
                <TickMarks min={2} max={8} step={1} majorStep={1} />
              </div>
            </div>
            <div className="cap-control">
              <label htmlFor="cap-shift-hours">
                Shift length (hrs) <span className="cap-value">{shiftHours}</span>
              </label>
              <div className="cap-slider-wrap">
                <input
                  id="cap-shift-hours"
                  type="range"
                  min="6"
                  max="11"
                  step="0.5"
                  value={shiftHours}
                  onChange={(e) => setShiftHours(Number(e.target.value))}
                />
                <TickMarks min={6} max={11} step={0.5} majorStep={1} />
              </div>
            </div>
            <div className="cap-control">
              <label htmlFor="cap-receiving">
                Receiving hours pulled <span className="cap-value">{receiving}</span>
              </label>
              <div className="cap-slider-wrap">
                <input
                  id="cap-receiving"
                  type="range"
                  min="0"
                  max="8"
                  step="0.5"
                  value={receiving}
                  onChange={(e) => setReceiving(Number(e.target.value))}
                />
                <TickMarks min={0} max={8} step={0.5} majorStep={2} />
              </div>
            </div>
            <div className="cap-control">
              <label htmlFor="cap-complexity">
                Order complexity (avg lines/order){" "}
                <span className="cap-value">{complexity.toFixed(1)}</span>
              </label>
              <div className="cap-slider-wrap">
                <input
                  id="cap-complexity"
                  type="range"
                  min="1.3"
                  max="4.0"
                  step="0.1"
                  value={complexity}
                  onChange={(e) => setComplexity(Number(e.target.value))}
                />
                <TickMarks min={1.3} max={4.0} step={0.1} majorStep={0.5} />
              </div>
            </div>
            <div className="cap-control">
              <label htmlFor="cap-forecast">
                Forecasted orders today <span className="cap-value">{Math.round(forecast)}</span>
              </label>
              <div className="cap-slider-wrap">
                <input
                  id="cap-forecast"
                  type="range"
                  min="100"
                  max="450"
                  step="5"
                  value={forecast}
                  onChange={(e) => setForecast(Number(e.target.value))}
                />
                <TickMarks min={100} max={450} step={5} majorStep={50} />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="cap-panel">
        <div className="cap-panel-label">
          <span>Last 30 Days — Orders Shipped vs. Forecast</span>
          <span>Today's projection highlighted</span>
        </div>
        <div className="cap-chart-wrap">
          <canvas ref={canvasRef}></canvas>
        </div>
      </div>

      <div className="cap-panel">
        <div className="cap-panel-label">
          <span>Model Spec Plate</span>
          <span>Linear Regression · 5-fold CV</span>
        </div>
        <div className="cap-spec-grid">
          <div className="cap-spec-item">
            <div className="cap-k">CV R²</div>
            <div className="cap-v">0.911</div>
          </div>
          <div className="cap-spec-item">
            <div className="cap-k">CV MAE</div>
            <div className="cap-v">10.3 orders</div>
          </div>
          <div className="cap-spec-item">
            <div className="cap-k">Residual SD</div>
            <div className="cap-v">12.9 orders</div>
          </div>
          <div className="cap-spec-item">
            <div className="cap-k">Training window</div>
            <div className="cap-v">30 days</div>
          </div>
        </div>
        <div className="cap-formula">
          orders_shipped&nbsp; = <span className="cap-hl">157.4</span>
          &nbsp;+&nbsp;<span className="cap-hl">5.67</span> × packer_hours_available
          &nbsp;−&nbsp;<span className="cap-hl">65.3</span> × order_complexity
          <br />
          Random Forest was tested as a comparison (CV R² 0.81) — linear regression won on both
          accuracy and interpretability, so it drives this estimator.
        </div>
      </div>
    </div>
  );
}
