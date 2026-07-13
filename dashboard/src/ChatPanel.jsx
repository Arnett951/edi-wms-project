import React, { useEffect, useState } from "react";
import { authFetch } from "./apiClient.js";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const DEFAULT_ISA_SUGGESTION = "What happened with ISA 000012345?";
const FAILED_ORDERS_SUGGESTION = "Give me the failed orders";

export default function ChatPanel({ onClose, canDownloadFiles = false }) {
  const [messages, setMessages] = useState([
    {
      role: "bot",
      text:
        'Ask me about a PO/order number or an ISA control number, e.g. "Where is PO 12345?" ' +
        'You can also ask things like "give me the failed orders" in plain English — an AI fallback ' +
        "handles anything the quick lookups don't recognize.",
    },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [suggestions, setSuggestions] = useState([
    "Where is PO ORDER1001?",
    DEFAULT_ISA_SUGGESTION,
    FAILED_ORDERS_SUGGESTION,
  ]);

  useEffect(() => {
    let cancelled = false;
    authFetch(`${API_BASE}/api/chat/sample-isa`)
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (cancelled || !data?.isaControlNumber) return;
        setSuggestions((s) => [s[0], `What happened with ISA ${data.isaControlNumber}?`, s[2]]);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const allSuggestions = canDownloadFiles
    ? [...suggestions, `Download the file for ${suggestions[1].match(/ISA (\d+)/)?.[0] || "ISA 000012345"}`]
    : suggestions;

  async function send(question) {
    const text = (question ?? input).trim();
    if (!text || sending) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setSending(true);
    try {
      const response = await authFetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text }),
      });
      if (!response.ok) throw new Error(`Chat API returned HTTP ${response.status}`);
      const data = await response.json();
      setMessages((m) => [
        ...m,
        {
          role: "bot",
          text: data.reply || "No answer returned.",
          source: data.source,
          downloads: data.downloads,
        },
      ]);
    } catch (err) {
      setMessages((m) => [...m, { role: "bot", text: `Couldn't reach the chat API: ${err.message}` }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <section className="chat-side-panel">
      <div className="chat-header">
        <h2>Ask about a PO or ISA #</h2>
        <button className="chat-close" type="button" onClick={onClose}>
          ×
        </button>
      </div>
      <div className="chat-log">
        {messages.map((m, i) => (
          <div key={i} className={`chat-bubble ${m.role}`}>
            {m.source === "ai" && <span className="ai-badge">AI</span>}
            {m.text}
            {m.downloads?.length > 0 && (
              <div className="chat-downloads">
                {m.downloads.map((d) => (
                  <div key={d.downloadUrl}>
                    <a href={d.downloadUrl} target="_blank" rel="noopener noreferrer">
                      Download {d.fileName}
                    </a>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="chat-suggestions">
        {allSuggestions.map((s) => (
          <button key={s} type="button" onClick={() => send(s)} disabled={sending}>{s}</button>
        ))}
      </div>
      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g. Where is PO 12345?"
          disabled={sending}
        />
        <button type="submit" disabled={sending || !input.trim()}>Send</button>
      </form>
    </section>
  );
}
