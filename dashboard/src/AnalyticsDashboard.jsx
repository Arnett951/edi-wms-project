import React from "react";
import "@tableau/embedding-api";

export default function AnalyticsDashboard() {
  return (
    <section className="panel">
      <h2>EDI Operations Dashboard</h2>

      <p>
        Interactive Tableau dashboard showing EDI pipeline health,
        operational alerts, and customer error trends.
      </p>

      <tableau-viz
        src="https://public.tableau.com/views/Book1_17852780799060/EDIOpsDashboard?:showVizHome=no"
        toolbar="bottom"
        hide-tabs
        device="desktop"
        style={{ width: "100%", height: "900px" }}
      />

    </section>
  );
}
