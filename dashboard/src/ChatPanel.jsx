import React, { useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const SUGGESTIONS = ["Where is PO ORDER1001?", "What happened with ISA 000012345?"];

export default function ChatPanel({ onClose }) {
  const [messages, setMessages] = useState([
    { role: "bot", text: 'Ask me about a PO/order number or an ISA control number, e.g. "Where is PO 12345?"' },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  async function send(question) {
    const text = (question ?? input).trim();
    if (!text || sending) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setSending(true);
    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text }),
      });
      if (!response.ok) throw new Error(`Chat API returned HTTP ${response.status}`);
      const data = await response.json();
      setMessages((m) => [...m, { role: "bot", text: data.reply || "No answer returned." }]);
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
          <div key={i} className={`chat-bubble ${m.role}`}>{m.text}</div>
        ))}
      </div>
      <div className="chat-suggestions">
        {SUGGESTIONS.map((s) => (
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
