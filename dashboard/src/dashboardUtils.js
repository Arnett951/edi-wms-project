export function normalizeSummary(data) {
  return {
    filesReceived: Number(data?.filesReceived ?? 0),
    filesParsed: Number(data?.filesParsed ?? 0),
    filesFailed: Number(data?.filesFailed ?? 0),
    wmsReady: Number(data?.wmsReady ?? 0),
    wmsSent: Number(data?.wmsSent ?? 0),
    wmsSuccess: Number(data?.wmsSuccess ?? 0),
    wmsFailed: Number(data?.wmsFailed ?? 0),
    wmsPickedUp: Number(data?.wmsPickedUp ?? 0),
    filesWaiting: Number(data?.filesWaiting ?? 0),
    oldestFileAgeSeconds: Number(data?.oldestFileAgeSeconds ?? 0),
    queueStatus: data?.queueStatus ?? "GREEN"
  };
}

export function buildStatusChart(summary) {
  const safe = normalizeSummary(summary);
  return [
    { name: "Received", count: safe.filesReceived },
    { name: "Parsed", count: safe.filesParsed },
    { name: "Parse Failed", count: safe.filesFailed },
    { name: "WMS Ready", count: safe.wmsReady },
    { name: "WMS Sent", count: safe.wmsSent },
    { name: "WMS Success", count: safe.wmsSuccess },
    { name: "WMS Failed", count: safe.wmsFailed },
  ];
}

// Columns exported to CSV — mirrors the Recent EDI Files list on the main
// dashboard (see App.jsx). Order matches the on-screen table.
export const RECENT_FILES_CSV_COLUMNS = [
  { key: "isaControlNumber", label: "ISA Control Number" },
  { key: "isaSender", label: "ISA Sender" },
  { key: "fileName", label: "File Name" },
  { key: "processStatus", label: "Process Status" },
  { key: "loadDateTime", label: "Load DateTime" },
  { key: "errorMessage", label: "Error Message" },
];

function csvEscape(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  // Quote fields containing delimiters, quotes, or newlines per RFC 4180.
  if (/[",\r\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

export function recentFilesToCsv(rows, columns = RECENT_FILES_CSV_COLUMNS) {
  const safeRows = Array.isArray(rows) ? rows : [];
  const lines = [columns.map(col => csvEscape(col.label)).join(",")];
  for (const row of safeRows) {
    lines.push(columns.map(col => csvEscape(row?.[col.key])).join(","));
  }
  return lines.join("\r\n");
}

export function statusClass(status) {
  switch (status) {
    case "PARSED":
    case "SUCCESS": return "good";
    case "READY": return "ready";
    case "SENT": return "sent";
    case "PARSE_FAILED":
    case "FAILED": return "bad";
    default: return "neutral";
  }
}
