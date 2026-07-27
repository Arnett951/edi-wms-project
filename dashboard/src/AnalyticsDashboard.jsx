import React from "react";

// TODO: replace with the real Tableau view URL once published.
const TABLEAU_TRENDING_ERRORS_URL = "https://public.tableau.com/app/profile/REPLACE_ME/viz/REPLACE_ME";

export default function AnalyticsDashboard() {
  return (
    <section className="panel">
      <h2>Analytics</h2>
      <p>
        Trending EDI 940 parse and WMS integration errors by customer over the
        last 30 days, tracked in Tableau.
      </p>
      <a
        className="demo-link-btn"
        href={TABLEAU_TRENDING_ERRORS_URL}
        target="_blank"
        rel="noopener noreferrer"
      >
        Open Tableau: Trending Errors by Customer (30 days)
      </a>
    </section>
  );
}
