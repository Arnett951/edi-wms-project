import React from "react";

// Power BI version of the Inventory Aging report, shown on the Operational
// Reporting tab. Data path: Db2 (Skynet) -> powerbi/copy_db2_to_azuresql.py ->
// Azure SQL wmslab.vw_InventoryAging -> Power BI (import) -> Publish to web.
// Paste the "Publish to web" iframe src here; until then a placeholder shows.
const POWERBI_EMBED_URL =
  "https://app.powerbi.com/view?r=eyJrIjoiOWZjY2VjOTEtN2JlNS00YTIxLWJkNmYtODQ2OGQyODRkZmQ5IiwidCI6ImMxZDk2ZGJhLTcyOTAtNDk2ZC04YTlmLTNmNzQ1YjI0OTJkNCJ9";

const PBI_FLOW = [
  { step: "Db2 WMS", detail: "Same TIREWMS lab tables the BI Publisher report reads" },
  { step: "Copy to Azure SQL", detail: "Python job reloads schema wmslab in one transaction" },
  { step: "SQL View", detail: "T-SQL port of the BIP dataset: same columns, same 7-day rule" },
  { step: "Power BI Model", detail: "Power Query import + DAX aging buckets and measures" },
  { step: "Publish to web", detail: "Embedded below, no sign-in needed" },
];

const PBI_TECH = ["Power BI", "Power Query (M)", "DAX", "Azure SQL", "T-SQL", "Python"];

export default function PowerBiReport() {
  return (
    <div className="panel">
      <span className="bip-eyebrow">Same data, second tool</span>
      <h2>Inventory Aging in Power BI</h2>
      <p>
        The same aging dataset, rebuilt as an interactive Power BI report. BI Publisher gives the pixel-exact
        PDF a client gets in their inbox; Power BI gives Ops a drillable view by facility, age bucket and DOT
        age. Rather than run a gateway into the home lab, the Db2 tables are copied to Azure SQL, which Power
        BI reaches directly.
      </p>
      <div className="bip-badges">
        {PBI_TECH.map((t) => <span key={t} className="bip-badge">{t}</span>)}
      </div>

      <ol className="bip-flow">
        {PBI_FLOW.map((w) => (
          <li key={w.step}>
            <b>{w.step}</b>
            <span>{w.detail}</span>
          </li>
        ))}
      </ol>

      {POWERBI_EMBED_URL ? (
        <div className="pbi-frame">
          <iframe
            title="Inventory Aging report (Power BI)"
            src={POWERBI_EMBED_URL}
            allowFullScreen
            loading="lazy"
          />
        </div>
      ) : (
        <div className="pbi-pending">
          The embedded Power BI report is being published. Until then, the live BI Publisher report above
          renders from the same data.
        </div>
      )}

      <p className="bip-note">
        Reconciled before publishing: Db2 and the Azure SQL view both return <b>48 lots, 3,192 units and
        $362,888</b> (ATLANTA 24 lots / $178,876, PERRIS 24 lots / $184,012). Power BI data is a snapshot as
        of the last copy and refresh; the BI Publisher report above queries Db2 live.
      </p>
    </div>
  );
}
