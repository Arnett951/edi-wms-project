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
