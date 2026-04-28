import { describe, expect, it } from "vitest";
import { buildStatusChart, normalizeSummary, statusClass } from "./dashboardUtils";

describe("dashboard utilities", () => {
  it("normalizes missing and string count values", () => {
    const result = normalizeSummary({ filesReceived: "3", filesParsed: null, wmsPickedUp: 2 });
    expect(result.filesReceived).toBe(3);
    expect(result.filesParsed).toBe(0);
    expect(result.wmsPickedUp).toBe(2);
  });

  it("always builds seven status chart bars", () => {
    const chart = buildStatusChart({ filesReceived: 1, filesParsed: 1, wmsReady: 1 });
    expect(chart).toHaveLength(7);
    expect(chart[0]).toEqual({ name: "Received", count: 1 });
  });

  it("maps error statuses to bad styling", () => {
    expect(statusClass("FAILED")).toBe("bad");
    expect(statusClass("PARSE_FAILED")).toBe("bad");
  });
});
