import React from "react";
import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";

const summaryPayload = {
  filesReceived: 10,
  filesParsed: 8,
  filesFailed: 2,
  wmsReady: 1,
  wmsSent: 1,
  wmsSuccess: 3,
  wmsFailed: 1,
  wmsPickedUp: 5,
  filesWaiting: 2,
  oldestFileAgeSeconds: 30,
  queueStatus: "GREEN",
};

const recentFilesPayload = [
  {
    rawId: 1,
    fileName: "a.edi",
    isaControlNumber: "111",
    isaSender: "ACME",
    processStatus: "PARSED",
    loadDateTime: "2026-01-01 00:00:00",
    errorMessage: null,
  },
];

const wmsOrdersPayload = [
  {
    wmsOrderHeaderStagingId: 1,
    warehouseOrderNumber: "ORDER1",
    integrationStatus: "READY",
    attemptCount: 0,
    errorMessage: null,
  },
];

function jsonResponse(body, ok = true) {
  return Promise.resolve({ ok, status: ok ? 200 : 500, json: () => Promise.resolve(body) });
}

function mockDashboardFetch({ failDashboard = false } = {}) {
  global.fetch = vi.fn((url) => {
    if (url.includes("/.auth/me")) return jsonResponse({});
    if (url.includes("/api/dashboard/summary")) return failDashboard ? jsonResponse({}, false) : jsonResponse(summaryPayload);
    if (url.includes("/api/dashboard/recent-files")) return failDashboard ? jsonResponse({}, false) : jsonResponse(recentFilesPayload);
    if (url.includes("/api/dashboard/wms-orders")) return failDashboard ? jsonResponse({}, false) : jsonResponse(wmsOrdersPayload);
    if (url.includes("/api/wms/simulate-pickup")) {
      return jsonResponse({ success: true, pickedUp: 2, message: "Simulated WMS pickup for 2 order(s)." });
    }
    if (url.includes("/api/chat/sample-isa")) return jsonResponse({ isaControlNumber: null });
    return jsonResponse({});
  });
}

describe("App", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders live dashboard data on successful load", async () => {
    mockDashboardFetch();
    render(<App />);

    expect(await screen.findByText("a.edi")).toBeInTheDocument();
    expect(screen.getByText("ORDER1")).toBeInTheDocument();
    expect(screen.queryByText(/Mock mode is active/)).not.toBeInTheDocument();
  });

  it("falls back to mock data and shows a banner when the dashboard API is unreachable", async () => {
    mockDashboardFetch({ failDashboard: true });
    render(<App />);

    expect(await screen.findByText(/Mock mode is active/)).toBeInTheDocument();
    expect(screen.getByText(/Showing mock data/)).toBeInTheDocument();
    expect(screen.getByText("sample_940.edi")).toBeInTheDocument();
  });

  it("opens and closes the chat panel from the support card", async () => {
    mockDashboardFetch();
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("a.edi");

    await user.click(screen.getByText("Ask PO / ISA"));
    expect(await screen.findByText("Ask about a PO or ISA #")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "×" }));
    expect(screen.queryByText("Ask about a PO or ISA #")).not.toBeInTheDocument();
  });

  it("simulates a WMS pickup and shows the confirmation message", async () => {
    mockDashboardFetch();
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("a.edi");

    await user.click(screen.getByText("WMS Pickup"));

    expect(await screen.findByText("Simulated WMS pickup for 2 order(s).")).toBeInTheDocument();
  });
});
