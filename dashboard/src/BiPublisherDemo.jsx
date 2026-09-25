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

const GAP_STEPS = [
  {
    step: "Model the data",
    detail: "Designed a synthetic tire-distribution WMS schema in Db2 LUW (Docker) and wrote the lot-level aging dataset in DBeaver.",
  },
  {
    step: "Build the report",
    detail: "Exported the dataset as XML and built the RTF layout in Template Builder for Word: SKU grouping, totals, aging.",
  },
  {
    step: "Make it run live",
    detail: "Rendered with the BI Publisher engine on a Linux server, with a facility parameter like a data model LOV.",
  },
  {
    step: "Rehearse legacy data",
    detail: "Rebuilt the dataset against an IBM i-style copy of the data and proved both versions match.",
  },
];

const FINDINGS = [
  {
    title: "SKU totals didn't match their rows",
    symptom: "A SKU header showed $9,272 of value, but its only printed lot was $6,308.",
    cause: "The engine's compile log flagged an unmatched loop tag: the detail row had lost its <?for-each:current-group()?>, so each group printed only its first lot.",
    fix: "Restored the inner loop. Now every total reconciles to the rows under it.",
  },
  {
    title: "Date math returned zero",
    symptom: "xdoxslt:minimum on received dates gave 0 instead of the oldest date.",
    cause: "The XML carries dates as text; the template's aggregate functions are numeric.",
    fix: "Moved the logic to SQL: MIN(RECEIVED_DATE) OVER (PARTITION BY facility, SKU). Compute in the dataset, format in the template.",
  },
  {
    title: "Group headers stranded at page breaks",
    symptom: "A SKU header landed at the bottom of a page with its lots on the next.",
    cause: "\"Keep with next\" was on every row, so every group chained to the next and none of the keeps could be honored.",
    fix: "Traced it in the compiled XSL-FO: keep-with-next on the group header rows only fixes it.",
  },
  {
    title: "Text hidden under a graphic",
    symptom: "The report date rendered in the PDF but was invisible.",
    cause: "Floating images are drawn in anchor order (Word's \"Send to Back\" is ignored), and PNG transparency is flattened.",
    fix: "Layout-driven fix: trimmed the image so it doesn't overlap text.",
  },
];

const FEATURES = [
  "Inventory grouped by SKU with a per-SKU value total",
  "Warehouse age from received date, plus oldest-receipt age per SKU",
  "DOT code and manufacturing date carried from lot attributes",
  "Product age (since manufacture) alongside warehouse age",
  "On-hand, allocated and available quantity by location",
  "Inventory value by line and by SKU group",
];

// Used until the report registry loads (or if the home lab is offline).
const FALLBACK_REPORTS = [
  {
    id: "inventory-aging",
    title: "Warehouse Inventory Aging",
    description: "Aged inventory by SKU and location with lot/DOT data, availability and value.",
    sources: [{ id: "wms", label: "Modern schema (WMS.*)", note: "" }],
  },
];

function LiveReport() {
  const [reports, setReports] = useState(FALLBACK_REPORTS);
  const [reportId, setReportId] = useState(FALLBACK_REPORTS[0].id);
  const [facilities, setFacilities] = useState(FALLBACK_FACILITIES);
  const [facility, setFacility] = useState(FALLBACK_FACILITIES[0].code);
  const [source, setSource] = useState("wms");
  const [status, setStatus] = useState("idle"); // idle | loading | done | error
  const [slow, setSlow] = useState(false);
  const [error, setError] = useState(null);
  const [pdf, setPdf] = useState(null); // { url, reportTitle, facility, sourceLabel, at }
  const pdfUrlRef = useRef(null);

  const report = reports.find((r) => r.id === reportId) || reports[0];
  const sources = report.sources.length ? report.sources : [{ id: "wms", label: "Default", note: "" }];
  const currentSource = sources.find((src) => src.id === source) || sources[0];

  useEffect(() => {
    // Also warms the scale-to-zero API before the visitor clicks Run.
    fetch(`${API_BASE}/api/public/bi-report/facilities`)
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then((list) => {
        if (Array.isArray(list) && list.length) setFacilities(list);
      })
      .catch(() => {});
    // The report registry: every folder of report.json + SQL + RTF on the report server.
    fetch(`${API_BASE}/api/public/bi-report/reports`)
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then((list) => {
        if (Array.isArray(list) && list.length) setReports(list);
      })
      .catch(() => {});
    return () => pdfUrlRef.current && URL.revokeObjectURL(pdfUrlRef.current);
  }, []);

  function chooseReport(id) {
    setReportId(id);
    const next = reports.find((r) => r.id === id);
    setSource(next && next.sources.length ? next.sources[0].id : "wms");
  }

  async function runReport() {
    setStatus("loading");
    setSlow(false);
    setError(null);
    const slowTimer = setTimeout(() => setSlow(true), SLOW_NOTICE_MS);
    try {
      const params = new URLSearchParams({ report: report.id, facility, source: currentSource.id });
      const res = await fetch(`${API_BASE}/api/public/bi-report/pdf?${params}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Report request failed (HTTP ${res.status}).`);
      }
      const blob = await res.blob();
      if (pdfUrlRef.current) URL.revokeObjectURL(pdfUrlRef.current);
      pdfUrlRef.current = URL.createObjectURL(blob);
      setPdf({
        url: pdfUrlRef.current,
        reportTitle: report.title,
        facility,
        sourceLabel: sources.length > 1 ? currentSource.label : null,
        at: new Date(),
      });
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
        Pick a report and a facility to query the Db2 lab database and render the report's RTF template with the
        BI Publisher engine, on demand. Runs on a home-lab server (Docker on Linux) reached through the API over
        Tailscale. Each report is a folder of report.json + SQL + RTF on that server, so a new report shows up
        here as soon as its folder is copied in.
      </p>
      <div className="bip-live-controls">
        <label>
          <span>Report</span>
          <select value={report.id} onChange={(e) => chooseReport(e.target.value)} disabled={status === "loading"}>
            {reports.map((r) => (
              <option key={r.id} value={r.id}>{r.title}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Facility</span>
          <select value={facility} onChange={(e) => setFacility(e.target.value)} disabled={status === "loading"}>
            {facilities.map((f) => (
              <option key={f.code} value={f.code}>{f.code} - {f.name}</option>
            ))}
          </select>
        </label>
        {sources.length > 1 && (
          <label>
            <span>Data source</span>
            <select value={currentSource.id} onChange={(e) => setSource(e.target.value)} disabled={status === "loading"}>
              {sources.map((src) => (
                <option key={src.id} value={src.id}>{src.label}</option>
              ))}
            </select>
          </label>
        )}
        <button type="button" onClick={runReport} disabled={status === "loading"}>
          {status === "loading" ? "Generating..." : "Run Live Report"}
        </button>
      </div>
      <p className="bip-live-source">
        {report.description}
        {sources.length > 1 && currentSource.note ? ` ${currentSource.note}` : ""}
      </p>
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
              Live render: <b>{pdf.reportTitle}</b> for <b>{pdf.facility}</b>
              {pdf.sourceLabel ? <> from <b>{pdf.sourceLabel}</b></> : null} at {pdf.at.toLocaleTimeString()}
            </span>
            <a href={pdf.url} target="_blank" rel="noopener noreferrer">Open PDF in new tab</a>
          </div>
          <iframe title={`Live ${pdf.reportTitle} for ${pdf.facility}`} src={pdf.url} />
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

      <div className="panel bip-story">
        <h2>Closing the gap: Db2 + BI Publisher in under a week</h2>
        <p className="bip-story-intro">
          My production background is SQL Server, Informix, Crystal Reports, Manhattan WMOS and EDI. Db2 and
          Oracle BI Publisher were new to me, so I built this lab to learn the stack hands-on, including the
          parts that don't work the way a Crystal or SQL Server habit expects.
        </p>

        <ol className="bip-flow bip-story-steps">
          {GAP_STEPS.map((g) => (
            <li key={g.step}>
              <b>{g.step}</b>
              <span>{g.detail}</span>
            </li>
          ))}
        </ol>

        <h3>What the engine taught me</h3>
        <div className="bip-findings">
          {FINDINGS.map((f) => (
            <article key={f.title} className="bip-finding">
              <h4>{f.title}</h4>
              <dl>
                <dt>Symptom</dt>
                <dd>{f.symptom}</dd>
                <dt>Cause</dt>
                <dd>{f.cause}</dd>
                <dt>Fix</dt>
                <dd>{f.fix}</dd>
              </dl>
            </article>
          ))}
        </div>

        <h3>Rehearsing legacy IBM i data</h3>
        <p>
          Production WMS data on IBM i rarely looks like a clean relational schema, so I made a copy in legacy
          conventions: 10-character file names, blank-padded CHAR, numeric YYYYMMDD / CYYMMDD dates and HHMMSS
          times, one-letter status codes, and natural keys. I rewrote the dataset against it, converting dates
          safely (0 becomes NULL) and filtering on the raw numeric column so indexes still apply. Then I
          proved the rewrite: <b>EXCEPT ALL in both directions returns 0 rows, 44 = 44 rows, and $330,816 on
          both sides</b>. The "Legacy IBM i-style" data source above renders the same report from it.
        </p>

        <h3>What this lab doesn't cover</h3>
        <p>
          It uses Db2 LUW and the BI Publisher core engine, not Db2 for i and the Enterprise server. The
          template skills carry over directly. On the job I'd still need to learn the server side (data
          models, LOVs, scheduling, bursting and delivery) and the local IBM i conventions: system vs SQL
          naming, library lists and the actual WMi files. My plan on any new system: start from the reports
          Ops runs most, learn their joins, and reconcile old vs new whenever I change one.
        </p>
      </div>

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
