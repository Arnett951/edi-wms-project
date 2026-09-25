import React from "react";

// Static portfolio section for the Db2 + Oracle BI Publisher lab. Assets live
// in public/bi-publisher/ and are served as-is (no API calls, no sign-in).
const PDF_URL = "/bi-publisher/inventory-aging-report.pdf";
const PREVIEW_URL = "/bi-publisher/inventory-aging-preview.jpg";

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
            View Report PDF
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
