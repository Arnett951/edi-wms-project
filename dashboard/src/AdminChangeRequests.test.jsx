import React from "react";
import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import AdminChangeRequests from "./AdminChangeRequests.jsx";

// authFetch normally attaches a real Azure AD bearer token via MSAL; in tests
// it just forwards to the already-mocked global.fetch below.
vi.mock("./apiClient.js", () => ({
  authFetch: (url, options) => global.fetch(url, options),
}));

const changeRequestsPayload = [
  {
    crNumber: 13,
    title: "Widen Status column",
    tier: "A",
    status: "Pending Build Approval",
  },
];

function jsonResponse(body, ok = true) {
  return Promise.resolve({ ok, status: ok ? 200 : 500, json: () => Promise.resolve(body) });
}

describe("AdminChangeRequests", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("tags the Status column header and cell so it can widen and word-wrap", async () => {
    global.fetch = vi.fn((url) => {
      if (url.includes("/api/change-requests")) return jsonResponse(changeRequestsPayload);
      return jsonResponse({});
    });

    render(<AdminChangeRequests canManageCr={false} />);

    // The status badge text renders inside the Status cell once the CR loads.
    const badge = await screen.findByText("Pending Build Approval");
    const statusCell = badge.closest("td");
    expect(statusCell).toHaveClass("cr-status-cell");

    const statusHeader = screen.getByRole("columnheader", { name: "Status" });
    expect(statusHeader).toHaveClass("cr-status-cell");
  });
});
