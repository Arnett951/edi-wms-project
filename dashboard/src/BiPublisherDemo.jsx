import React, { useEffect, useRef, useState } from "react";

// Portfolio section for the Db2 + Oracle BI Publisher lab. The static sample
// PDF/preview live in public/bi-publisher/; the "Run it live" panel calls the
// API's public /api/public/bi-report/* routes, which proxy to the bip-report
// service on Skynet (no sign-in needed).
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const PDF_URL = "/bi-publisher/inventory-aging-report.pdf";
const PREVIEW_URL = "/bi-publisher/inventory-aging-preview.jpg";
const FALLBACK_FACILITIES = [
  { code: "ATLANTA", name: "Demo West Tire Distribution" },
  { code: "PERRIS", name: "Demo East Tire Distribution" },
];
// After this long, tell the visitor the API is probably cold-starting.
const SLOW_NOTICE_MS = 5000;

const WORKFLOW = [
  { step: "Db2 WMS Data", detail: "Synthetic tire-distribution schema in IBM Db2 LUW" },
  { step: "SQL Dataset", detail: "Joins inventory, lots, locations and allocations" },
  { step: "XML", detail: "Dataset exported as the report's XML data model" },
  { step: "RTF Template", detail: "BI Publisher Template Builder for Word; grouped by SKU" },
  { step: "PDF", detail: "Rendered by BI Publisher with group totals" },
];

const TECH = ["IBM Db2", "SQL", "Oracle BI Publisher", "XML Data Model", "RTF Templates", "WMS Reporting"];

const SCHEMA = [
  "WAREHOUSE",
  "LOCATION",
  "ITEM",
  "INVENTORY",
  "INVENTORY_TRANSACTION",
  "LOT_ATTRIBUTE",
  "OUTBOUND_ORDER / OUTBOUND_LINE",
];

const FEATURES = [
  "Inventory grouped by SKU with a per-SKU value total",
  "Warehouse age from received date, plus oldest-receipt age per SKU",
  "DOT code and manufacturing date carried from lot attributes",
  "Product age (since manufacture) alongside warehouse age",
  "On-hand, allocated and available quantity by location",
  "Inventory value by line and by SKU group",
];

function LiveReport() {
  const [facilities, setFacilities] = useState(FALLBACK_FACILITIES);
  const [facility, setFacility] = useState(FALLBACK_FACILITIES[0].code);
  const [status, setStatus] = useState("idle"); // idle | loading | done | error
  const [slow, setSlow] = useState(false);
  const [error, setError] = useState(null);
  const [pdf, setPdf] = useState(null); // { url, facility, at }
  const pdfUrlRef = useRef(null);

  useEffect(() => {
    // Also warms the scale-to-zero API before the visitor clicks Run.
    fetch(`${API_BASE}/api/public/bi-report/facilities`)
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then((list) => {
        if (Array.isArray(list) && list.length) setFacilities(list);
      })
      .catch(() => {});
    return () => pdfUrlRef.current && URL.revokeObjectURL(pdfUrlRef.current);
  }, []);

  async function runReport() {
    setStatus("loading");
    setSlow(false);
    setError(null);
    const slowTimer = setTimeout(() => setSlow(true), SLOW_NOTICE_MS);
    try {
      const res = await fetch(`${API_BASE}/api/public/bi-report/pdf?facility=${encodeURIComponent(facility)}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Report request failed (HTTP ${res.status}).`);
      }
      const blob = await res.blob();
      if (pdfUrlRef.current) URL.revokeObjectURL(pdfUrlRef.current);
      pdfUrlRef.current = URL.createObjectURL(blob);
      setPdf({ url: pdfUrlRef.current, facility, at: new Date() });
      setStatus("done");
    } catch (err) {
      setError(err.message && err.message !== "Failed to fetch" ? err.message : "Couldn't reach the live report server.");
      setStatus("error");
    } finally {
      clearTimeout(slowTimer);
    }
  }

  return (
    <div className="panel bip-live">
      <h2>Run it live</h2>
      <p>
        Pick a facility to query the Db2 lab database and render the same RTF template with the BI Publisher
        engine, on demand. Runs on a home-lab server (Docker on Linux) reached through the API over Tailscale.
      </p>
      <div className="bip-live-controls">
        <label>
          <span>Facility</span>
          <select value={facility} onChange={(e) => setFacility(e.target.value)} disabled={status === "loading"}>
            {facilities.map((f) => (
              <option key={f.code} value={f.code}>{f.code} - {f.name}</option>
            ))}
          </select>
        </label>
        <button type="button" onClick={runReport} disabled={status === "loading"}>
          {status === "loading" ? "Generating..." : "Run Live Report"}
        </button>
      </div>
      {status === "loading" && slow && (
        <p className="bip-live-note">
          Waking the API (it scales to zero when idle) - the first request can take a few minutes.
        </p>
      )}
      {status === "error" && (
        <p className="bip-live-error">
          {error} The home-lab server may be offline - the{" "}
          <a href={PDF_URL} target="_blank" rel="noopener noreferrer">static sample PDF</a> is always available.
        </p>
      )}
      {pdf && (
        <div className="bip-live-result">
          <div className="bip-live-meta">
            <span>
              Live render: <b>{pdf.facility}</b> at {pdf.at.toLocaleTimeString()}
            </span>
            <a href={pdf.url} target="_blank" rel="noopener noreferrer">Open PDF in new tab</a>
          </div>
          <iframe title={`Live inventory aging report for ${pdf.facility}`} src={pdf.url} />
        </div>
      )}
    </div>
  );
}

export default function BiPublisherDemo() {
  return (
    <section className="bip">
      <div className="panel bip-hero">
        <div className="bip-hero-text">
          <span className="bip-eyebrow">Operational Reporting Demo</span>
          <h2>Warehouse Inventory Aging Report</h2>
          <p className="bip-sub">Aged inventory by SKU and location, built with Db2 and Oracle BI Publisher</p>
          <span className="bip-synthetic">Synthetic WMS data · portfolio demonstration</span>
          <p>
            A synthetic warehouse reporting environment built with Db2 and Oracle BI Publisher. The Inventory
            Aging report identifies aging stock by SKU and location while exposing lot/DOT manufacturing data,
            availability, allocations and inventory value. Built as a hands-on demonstration of operational WMS
            reporting, SQL datasets, XML data models and RTF/PDF report generation.
          </p>
          <div className="bip-badges">
            {TECH.map((t) => <span key={t} className="bip-badge">{t}</span>)}
          </div>
          <a className="bip-btn" href={PDF_URL} target="_blank" rel="noopener noreferrer">
            View Sample PDF
          </a>
        </div>
        <a className="bip-preview" href={PDF_URL} target="_blank" rel="noopener noreferrer" title="Open the full PDF">
          <img
            src={PREVIEW_URL}
            alt="First page of the Warehouse Inventory Aging Report PDF, showing Hello World Tire branding and per-SKU aging groups"
            loading="lazy"
          />
        </a>
      </div>

      <LiveReport />

      <div className="panel">
        <h2>The business problem</h2>
        <p className="bip-problem">
          “Identify inventory that has been sitting too long, where it is located, and how much inventory/value
          is tied up.”
        </p>
        <ul className="bip-list">
          {FEATURES.map((f) => <li key={f}>{f}</li>)}
        </ul>
      </div>

      <div className="panel">
        <h2>Report workflow</h2>
        <ol className="bip-flow">
          {WORKFLOW.map((w) => (
            <li key={w.step}>
              <b>{w.step}</b>
              <span>{w.detail}</span>
            </li>
          ))}
        </ol>
      </div>

      <div className="panel">
        <h2>Demo schema (Db2 LUW)</h2>
        <div className="bip-badges">
          {SCHEMA.map((t) => <code key={t} className="bip-table">{t}</code>)}
        </div>
        <p className="bip-note">
          All data is synthetic, and “Hello World Tire” is original demo branding. The schema is a simplified
          model I designed myself, not the schema of any real retailer, 3PL or commercial WMS. I built this lab to get
          hands-on experience with Db2 and BI Publisher; my production background is SQL Server, Informix,
          Manhattan WMOS, EDI and warehouse systems.
        </p>
      </div>
    </section>
  );
}
