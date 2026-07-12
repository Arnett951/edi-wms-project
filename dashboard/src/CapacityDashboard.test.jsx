import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import CapacityDashboard from "./CapacityDashboard";

// jsdom doesn't implement canvas 2D contexts, so Chart.js can't actually
// render in tests - mock it out and assert against the component's own
// computed readout instead, which is what we actually want to test.
vi.mock("chart.js/auto", () => ({
  // `new Chart(...)` requires a real constructor - an arrow function can't
  // be invoked with `new`. A plain function that returns an object works:
  // `new` semantics use that returned object as the instance.
  Chart: vi.fn(function FakeChart() {
    return {
      data: { datasets: [{}, { data: [] }, { data: [] }] },
      update: vi.fn(),
      destroy: vi.fn(),
    };
  }),
}));

describe("CapacityDashboard", () => {
  it("renders the default projection for the initial slider values", () => {
    render(<CapacityDashboard />);

    // headcount=5, shiftHours=9, receiving=0 -> packerHours=45, complexity=2.3
    // predicted = 157.3509363146291 + 5.670364553091294*45 - 65.34606343082069*2.3 = 262.22 -> 262
    // 80% range is [246, 279]; since high (279) < forecast (280), the default
    // scenario is deliberately understaffed - status is AT RISK, not ON TRACK.
    expect(screen.getByText("262")).toBeInTheDocument();
    expect(screen.getByText(/vs\. 280 forecasted today/)).toBeInTheDocument();
    expect(screen.getByText("AT RISK")).toBeInTheDocument();
  });

  it("recomputes the projection when a slider changes", () => {
    render(<CapacityDashboard />);

    fireEvent.change(screen.getByLabelText(/Packers on shift/i), { target: { value: "8" } });

    // headcount=8, shiftHours=9, receiving=0 -> packerHours=72, complexity=2.3
    // predicted = 157.3509363146291 + 5.670364553091294*72 - 65.34606343082069*2.3 = 415.32 -> 415
    expect(screen.getByText("415")).toBeInTheDocument();
  });

  it("switches to ON TRACK when the forecast drops below the low end of the range", () => {
    render(<CapacityDashboard />);

    // Default scenario starts AT RISK (see previous test); lowering the
    // forecast well below the 80% range's low bound (246) should flip it.
    fireEvent.change(screen.getByLabelText(/Forecasted orders today/i), { target: { value: "200" } });

    expect(screen.getByText("ON TRACK")).toBeInTheDocument();
  });
});
