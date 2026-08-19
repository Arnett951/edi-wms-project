import React, { useEffect, useState } from "react";
import { authFetch } from "./apiClient.js";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const DEFAULT_ISA_SUGGESTION = "What happened with ISA 000012345?";
const FAILED_ORDERS_SUGGESTION = "Give me the failed orders";

const INTAKE_WELCOME = {
  role: "bot",
  text:
    "Describe a feature, report, or change you'd like. I'll ask a few clarifying questions, " +
    "then create a Change Request for an admin to review -- see docs/ai-delivery-pipeline.md for how this pipeline works.",
};

const INTAKE_SUGGESTIONS = [
  "Add a chart showing daily EDI file volume",
  "Add an export-to-CSV button for the WMS staging queue",
];

export default function ChatPanel({ onClose, canDownloadFiles = false }) {
  const [mode, setMode] = useState("support");
  const [messages, setMessages] = useState([
    {
      role: "bot",
      text:
        'Ask me about a PO/order number or an ISA control number, e.g. "Where is PO 12345?" ' +
        'You can also ask things like "give me the failed orders" in plain English — an AI fallback ' +
        "handles anything the quick lookups don't recognize.",
    },
  ]);
  const [intakeMessages, setIntakeMessages] = useState([INTAKE_WELCOME]);
  const [intakeHistory, setIntakeHistory] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [feedback, setFeedback] = useState({});
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

  async function sendSupport(text) {
    setMessages((m) => [...m, { role: "user", text }]);
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
          id: crypto.randomUUID(),
          role: "bot",
          text: data.reply || "No answer returned.",
          source: data.source,
          downloads: data.downloads,
          question: text,
          feedbackEligible: true,
        },
      ]);
    } catch (err) {
      setMessages((m) => [...m, { role: "bot", text: `Couldn't reach the chat API: ${err.message}` }]);
    } finally {
      setSending(false);
    }
  }

  async function sendIntake(text) {
    setIntakeMessages((m) => [...m, { role: "user", text }]);
    setSending(true);
    try {
      const response = await authFetch(`${API_BASE}/api/change-requests/intake`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history: intakeHistory }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `Intake API returned HTTP ${response.status}`);

      if (data.type === "question") {
        setIntakeMessages((m) => [
          ...m,
          { id: crypto.randomUUID(), role: "bot", text: data.text, source: "ai", question: text, feedbackEligible: true },
        ]);
        setIntakeHistory((h) => [...h, { role: "user", content: text }, { role: "assistant", content: data.text }]);
      } else if (data.type === "complete") {
        const crCode = `CR-${String(data.crNumber).padStart(3, "0")}`;
        setIntakeMessages((m) => [
          ...m,
          {
            role: "bot",
            source: "ai",
            text:
              `${crCode} created: "${data.title}" -- Tier ${data.tier}, ~$${data.estimatedCost} ` +
              `(${data.costRatioPct}% of budget). An admin reviews it next in the Admin tab.`,
          },
        ]);
        setIntakeHistory([]);
      } else {
        setIntakeMessages((m) => [...m, { role: "bot", text: "Unexpected response from intake API." }]);
      }
    } catch (err) {
      setIntakeMessages((m) => [...m, { role: "bot", text: `Couldn't reach the intake API: ${err.message}` }]);
    } finally {
      setSending(false);
    }
  }

  function selectFeedbackRating(messageId, rating) {
    setFeedback((f) => ({
      ...f,
      [messageId]: { ...(f[messageId] || {}), rating, submitted: false, error: null },
    }));
  }

  function setFeedbackComment(messageId, comment) {
    setFeedback((f) => ({ ...f, [messageId]: { ...(f[messageId] || {}), comment } }));
  }

  async function submitFeedback(message, channel) {
    const entry = feedback[message.id];
    if (!entry?.rating || entry.submitted || entry.pending) return;

    setFeedback((f) => ({ ...f, [message.id]: { ...f[message.id], pending: true, error: null } }));
    try {
      const response = await authFetch(`${API_BASE}/api/chat/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: message.question,
          reply: message.text,
          source: message.source,
          channel,
          rating: entry.rating,
          comment: entry.comment?.trim() || null,
        }),
      });
      if (!response.ok) throw new Error(`Feedback API returned HTTP ${response.status}`);
      setFeedback((f) => ({ ...f, [message.id]: { ...f[message.id], pending: false, submitted: true } }));
    } catch (err) {
      setFeedback((f) => ({ ...f, [message.id]: { ...f[message.id], pending: false, error: err.message } }));
    }
  }

  async function send(question) {
    const text = (question ?? input).trim();
    if (!text || sending) return;
    setInput("");
    if (mode === "intake") {
      await sendIntake(text);
    } else {
      await sendSupport(text);
    }
  }

  const activeMessages = mode === "intake" ? intakeMessages : messages;
  const activeSuggestions = mode === "intake" ? INTAKE_SUGGESTIONS : allSuggestions;

  return (
    <section className="chat-side-panel">
      <div className="chat-header">
        <h2>{mode === "intake" ? "Request a change" : "Ask about a PO or ISA #"}</h2>
        <button className="chat-close" type="button" onClick={onClose}>
          ×
        </button>
      </div>
      <div className="chat-mode-toggle">
        <button
          className={mode === "support" ? "chat-mode-active" : ""}
          onClick={() => setMode("support")}
          disabled={sending}
        >
          Support
        </button>
        <button
          className={mode === "intake" ? "chat-mode-active" : ""}
          onClick={() => setMode("intake")}
          disabled={sending}
        >
          Request a change
        </button>
      </div>
      <div className="chat-log">
        {activeMessages.map((m, i) => {
          const fb = feedback[m.id];
          return (
            <div key={m.id ?? i} className={`chat-bubble ${m.role}`}>
              {(m.source === "ai" || m.source === "local_ai") && (
                <span className="ai-badge">{m.source === "local_ai" ? "AI-L" : "AI"}</span>
              )}
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
              {m.feedbackEligible && (
                <div className="chat-feedback">
                  {fb?.submitted ? (
                    <span className="chat-feedback-thanks">Thanks for the feedback!</span>
                  ) : (
                    <>
                      <div className="chat-feedback-buttons">
                        <button
                          type="button"
                          className={`chat-feedback-btn${fb?.rating === 1 ? " active" : ""}`}
                          aria-label="Helpful"
                          aria-pressed={fb?.rating === 1}
                          onClick={() => selectFeedbackRating(m.id, 1)}
                        >
                          👍
                        </button>
                        <button
                          type="button"
                          className={`chat-feedback-btn${fb?.rating === -1 ? " active" : ""}`}
                          aria-label="Not helpful"
                          aria-pressed={fb?.rating === -1}
                          onClick={() => selectFeedbackRating(m.id, -1)}
                        >
                          👎
                        </button>
                      </div>
                      {fb?.rating && (
                        <div className="chat-feedback-comment">
                          <textarea
                            placeholder="Optional: tell us why (helps improve future replies)"
                            value={fb.comment || ""}
                            maxLength={1000}
                            onChange={(e) => setFeedbackComment(m.id, e.target.value)}
                          />
                          <button
                            type="button"
                            disabled={fb.pending}
                            onClick={() => submitFeedback(m, mode === "intake" ? "intake" : "support")}
                          >
                            {fb.pending ? "Submitting..." : "Submit feedback"}
                          </button>
                          {fb.error && <span className="chat-feedback-error">{fb.error}</span>}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="chat-suggestions">
        {activeSuggestions.map((s) => (
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
          placeholder={mode === "intake" ? "e.g. Add a chart showing..." : "e.g. Where is PO 12345?"}
          disabled={sending}
        />
        <button type="submit" disabled={sending || !input.trim()}>Send</button>
      </form>
    </section>
  );
}
