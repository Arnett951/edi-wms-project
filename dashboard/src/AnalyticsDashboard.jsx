import React from "react";
import "@tableau/embedding-api";

export default function AnalyticsDashboard() {
  return (
    <section className="analytics-panel">

      <p>
        Tableau dashboard showing EDI pipeline health, operational alerts, and customer error trends.
      </p>

      <tableau-viz
        src="https://public.tableau.com/views/Book1_17852780799060/EDIOpsDashboard?:showVizHome=no"
        toolbar="bottom"
        hide-tabs
        style={{
          width: "100%",
          height: "1500px",
          display: "block"
        }}
      />
    </section>
  );
}