import React, { useEffect, useRef, useState } from "react";
import { sendMessage, WS_URL } from "./api";

interface Message {
  role: "user" | "assistant";
  text: string;
}

function useBackendConnection(): boolean {
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout>;

    function connect() {
      const socket = new WebSocket(WS_URL);
      socketRef.current = socket;

      socket.onopen = () => !cancelled && setConnected(true);
      socket.onclose = () => {
        if (cancelled) return;
        setConnected(false);
        retryTimer = setTimeout(connect, 2000);
      };
      socket.onerror = () => socket.close();
    }

    connect();
    return () => {
      cancelled = true;
      clearTimeout(retryTimer);
      socketRef.current?.close();
    };
  }, []);

  return connected;
}

export default function App(): JSX.Element {
  const connected = useBackendConnection();

  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || busy) return;

    const userMessage: Message = { role: "user", text: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setBusy(true);

    try {
      const reply = await sendMessage(userMessage.text);
      setMessages((prev) => [...prev, { role: "assistant", text: reply }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: `Error: ${(err as Error).message}` },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 640, margin: "40px auto", fontFamily: "sans-serif" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
        <div
          style={{
            width: 72,
            height: 72,
            borderRadius: "50%",
            background: connected
              ? "radial-gradient(circle at 35% 30%, #7CFFCB, #12B886)"
              : "radial-gradient(circle at 35% 30%, #999, #444)",
            boxShadow: connected ? "0 0 24px 4px rgba(18,184,134,0.6)" : "none",
            transition: "all 0.3s ease",
          }}
        />
        <div>
          <h2 style={{ margin: 0 }}>NEXUS</h2>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "#666" }}>
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: connected ? "#12B886" : "#c92a2a",
                display: "inline-block",
              }}
            />
            {connected ? "Connected" : "Connecting..."}
          </div>
        </div>
      </div>

      <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12, minHeight: 320 }}>
        {messages.map((m, i) => (
          <div key={i} style={{ margin: "8px 0" }}>
            <strong>{m.role === "user" ? "You" : "NEXUS"}:</strong> {m.text}
          </div>
        ))}
      </div>

      <form onSubmit={handleSend} style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask NEXUS to do something..."
          style={{ flex: 1, padding: 8 }}
          disabled={busy}
        />
        <button type="submit" disabled={busy}>
          {busy ? "..." : "Send"}
        </button>
      </form>
    </div>
  );
}
