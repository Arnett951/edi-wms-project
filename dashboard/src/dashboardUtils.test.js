import { describe, expect, it } from "vitest";
import {
  buildStatusChart,
  normalizeSummary,
  recentFilesToCsv,
  statusClass,
} from "./dashboardUtils";

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

  it("builds CSV with a header row reflecting the shown columns", () => {
    const csv = recentFilesToCsv([
      {
        rawId: 1,
        isaControlNumber: "111",
        isaSender: "ACME",
        fileName: "a.edi",
        processStatus: "PARSED",
        loadDateTime: "2026-01-01 00:00:00",
        errorMessage: null,
      },
    ]);
    const [header, firstRow] = csv.split("\r\n");
    expect(header).toBe(
      "ISA Control Number,ISA Sender,File Name,Process Status,Load DateTime,Error Message"
    );
    expect(firstRow).toBe("111,ACME,a.edi,PARSED,2026-01-01 00:00:00,");
  });

  it("escapes values containing commas, quotes, and newlines", () => {
    const csv = recentFilesToCsv([
      {
        isaControlNumber: "1",
        isaSender: "A, B",
        fileName: 'weird"name.edi',
        processStatus: "PARSE_FAILED",
        loadDateTime: "2026-01-01 00:00:00",
        errorMessage: "line1\nline2",
      },
    ]);
    const rows = csv.split("\r\n");
    expect(rows[1]).toBe('1,"A, B","weird""name.edi",PARSE_FAILED,2026-01-01 00:00:00,"line1\nline2"');
  });

  it("returns just the header row when there are no files", () => {
    const csv = recentFilesToCsv([]);
    expect(csv.split("\r\n")).toHaveLength(1);
    expect(recentFilesToCsv(null)).toBe(csv);
  });
});
