import React from "react";
import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ChatPanel from "./ChatPanel";

// authFetch normally attaches a real Azure AD bearer token via MSAL; in
// tests it just forwards to the already-mocked global.fetch below.
vi.mock("./apiClient.js", () => ({
  authFetch: (url, options) => global.fetch(url, options),
}));

function jsonResponse(body, ok = true) {
  return Promise.resolve({ ok, status: ok ? 200 : 500, json: () => Promise.resolve(body) });
}

describe("ChatPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("replaces the default ISA suggestion with the latest failed ISA from the API", async () => {
    global.fetch = vi.fn(() => jsonResponse({ isaControlNumber: "000098765" }));

    render(<ChatPanel onClose={() => {}} />);

    expect(await screen.findByText("What happened with ISA 000098765?")).toBeInTheDocument();
  });

  it("keeps the default ISA suggestion when the sample-isa fetch fails", async () => {
    global.fetch = vi.fn(() => Promise.reject(new Error("network down")));

    render(<ChatPanel onClose={() => {}} />);

    expect(await screen.findByText("What happened with ISA 000012345?")).toBeInTheDocument();
  });

  it("keeps the default ISA suggestion when there is no recent failure", async () => {
    global.fetch = vi.fn(() => jsonResponse({ isaControlNumber: null }));

    render(<ChatPanel onClose={() => {}} />);
    await screen.findByText("Where is PO ORDER1001?");

    expect(screen.getByText("What happened with ISA 000012345?")).toBeInTheDocument();
  });

  it("sends a question and shows the bot reply", async () => {
    const user = userEvent.setup();
    global.fetch = vi.fn((url) =>
      url.includes("sample-isa")
        ? jsonResponse({ isaControlNumber: null })
        : jsonResponse({ reply: "PO ORDER1001 is ready." })
    );

    render(<ChatPanel onClose={() => {}} />);

    await user.type(screen.getByPlaceholderText(/where is po/i), "Where is PO ORDER1001?");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("PO ORDER1001 is ready.")).toBeInTheDocument();
  });

  it("clicking a suggestion sends it as the question", async () => {
    const user = userEvent.setup();
    global.fetch = vi.fn((url) =>
      url.includes("sample-isa")
        ? jsonResponse({ isaControlNumber: null })
        : jsonResponse({ reply: "Order located." })
    );

    render(<ChatPanel onClose={() => {}} />);

    await user.click(await screen.findByText("Where is PO ORDER1001?"));

    expect(await screen.findByText("Order located.")).toBeInTheDocument();
  });

  it("shows a connection error when the chat API is unreachable", async () => {
    const user = userEvent.setup();
    global.fetch = vi.fn((url) =>
      url.includes("sample-isa")
        ? jsonResponse({ isaControlNumber: null })
        : Promise.reject(new Error("Failed to fetch"))
    );

    render(<ChatPanel onClose={() => {}} />);

    await user.type(screen.getByPlaceholderText(/where is po/i), "Where is PO 1?");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText(/Couldn't reach the chat API/)).toBeInTheDocument();
  });

  it("calls onClose when the close button is clicked", async () => {
    const user = userEvent.setup();
    global.fetch = vi.fn(() => jsonResponse({ isaControlNumber: null }));
    const onClose = vi.fn();

    render(<ChatPanel onClose={onClose} />);
    await user.click(screen.getByRole("button", { name: "×" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
