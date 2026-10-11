import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import "./App.css";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [threadId, setThreadId] = useState(localStorage.getItem("thread_id"));
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send() {
    const text = input.trim();
    if (!text || loading) return;

    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, thread_id: threadId }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Request failed");

      const data = await res.json();
      setThreadId(data.thread_id);
      localStorage.setItem("thread_id", data.thread_id);
      setMessages((m) => [
        ...m,
        { role: "assistant", text: data.answer, flights: data.flight_results },
      ]);
    } catch (err) {
      setMessages((m) => [...m, { role: "assistant", text: `Error: ${err.message}`, error: true }]);
    } finally {
      setLoading(false);
    }
  }

  function newTrip() {
    localStorage.removeItem("thread_id");
    setThreadId(null);
    setMessages([]);
  }

  return (
    <div className="app">
      <header>
        <h1>✈️ AI Travel Planner</h1>
        <button onClick={newTrip}>New trip</button>
      </header>

      <main>
        {messages.length === 0 && (
          <p className="hint">
            Try: “Plan a 5 day budget trip from Hyderabad to Dubai, leaving 20 Nov 2026 and returning 25 Nov 2026”
          </p>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role} ${m.error ? "error" : ""}`}>
            {m.role === "assistant" ? <ReactMarkdown>{m.text}</ReactMarkdown> : m.text}
            {m.flights && (
              <details>
                <summary>Raw flight data</summary>
                <pre>{m.flights}</pre>
              </details>
            )}
          </div>
        ))}

        {loading && <div className="msg assistant">Planning your trip… this can take up to a minute.</div>}
        <div ref={bottomRef} />
      </main>

      <footer>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Where do you want to go? Include origin, destination and dates."
          disabled={loading}
        />
        <button onClick={send} disabled={loading || !input.trim()}>
          Send
        </button>
      </footer>
    </div>
  );
}