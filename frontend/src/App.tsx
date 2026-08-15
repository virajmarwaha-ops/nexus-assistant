import React, { useEffect, useRef, useState } from "react";
import { ChatResponse, confirmAction, sendMessage, speak, WS_URL } from "./api";
import { playAudioElement, speakWithBrowserVoice, VoiceClient } from "./voice";

interface Message {
  role: "user" | "assistant";
  text: string;
}

interface PendingConfirmation {
  confirmationId: string;
  toolName: string;
  summary: string;
  source: "text" | "voice";
}

type VoiceState = "idle" | "listening" | "thinking" | "speaking";

const ORB_COLORS: Record<VoiceState, string> = {
  idle: "radial-gradient(circle at 35% 30%, #7CFFCB, #12B886)",
  listening: "radial-gradient(circle at 35% 30%, #7CD4FF, #1C7ED6)",
  thinking: "radial-gradient(circle at 35% 30%, #D9B8FF, #7048E8)",
  speaking: "radial-gradient(circle at 35% 30%, #FFD68A, #F08C00)",
};

export default function App(): JSX.Element {
  const [connected, setConnected] = useState(false);
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [micError, setMicError] = useState<string | null>(null);

  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<PendingConfirmation | null>(null);

  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const voiceClientRef = useRef<VoiceClient | null>(null);

  async function playReply(text: string, audioBase64: string | null): Promise<void> {
    currentAudioRef.current?.pause();
    currentAudioRef.current = null;

    if (audioBase64) {
      const audio = new Audio(`data:audio/mpeg;base64,${audioBase64}`);
      currentAudioRef.current = audio;
      try {
        await playAudioElement(audio);
      } catch {
        await speakWithBrowserVoice(text);
      } finally {
        currentAudioRef.current = null;
      }
    } else {
      await speakWithBrowserVoice(text);
    }
  }

  useEffect(() => {
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout>;
    let socket: WebSocket;

    function connect() {
      socket = new WebSocket(WS_URL);
      const voiceClient = new VoiceClient(socket);
      voiceClientRef.current = voiceClient;

      socket.onopen = () => {
        if (cancelled) return;
        setConnected(true);
        voiceClient.startMic().catch((err: Error) => setMicError(err.message));
      };

      socket.onclose = () => {
        voiceClient.stopMic();
        if (cancelled) return;
        setConnected(false);
        setVoiceState("idle");
        retryTimer = setTimeout(connect, 2000);
      };

      socket.onerror = () => socket.close();

      socket.onmessage = (event) => {
        let payload: { type: string; [key: string]: unknown };
        try {
          payload = JSON.parse(event.data);
        } catch {
          return;
        }

        switch (payload.type) {
          case "wake":
            currentAudioRef.current?.pause();
            setVoiceState("listening");
            break;
          case "thinking":
            setVoiceState("thinking");
            break;
          case "transcript":
            setMessages((prev) => [...prev, { role: "user", text: payload.text as string }]);
            break;
          case "reply": {
            const text = (payload.text as string) || "";
            const audioBase64 = payload.audio_base64 as string | null;
            setMessages((prev) => [...prev, { role: "assistant", text }]);
            setVoiceState("speaking");
            playReply(text, audioBase64).finally(() => {
              setVoiceState("idle");
              voiceClientRef.current?.notifyPlaybackDone();
            });
            break;
          }
          case "confirm":
            setPending({
              confirmationId: payload.confirmation_id as string,
              toolName: payload.tool_name as string,
              summary: payload.summary as string,
              source: "voice",
            });
            setVoiceState("idle");
            break;
          case "error":
            setMessages((prev) => [...prev, { role: "assistant", text: `Error: ${payload.message}` }]);
            setVoiceState("idle");
            break;
          default:
            break;
        }
      };
    }

    connect();
    return () => {
      cancelled = true;
      clearTimeout(retryTimer);
      voiceClientRef.current?.stopMic();
      socket?.close();
    };
  }, []);

  function applyTextResponse(res: ChatResponse) {
    if (res.type === "confirm") {
      setPending({
        confirmationId: res.confirmation_id as string,
        toolName: res.tool_name as string,
        summary: res.summary as string,
        source: "text",
      });
    } else {
      setMessages((prev) => [...prev, { role: "assistant", text: res.reply || "" }]);
    }
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || busy || pending) return;

    const userMessage: Message = { role: "user", text: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setBusy(true);

    try {
      applyTextResponse(await sendMessage(userMessage.text));
    } catch (err) {
      setMessages((prev) => [...prev, { role: "assistant", text: `Error: ${(err as Error).message}` }]);
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirm(approved: boolean) {
    if (!pending) return;
    const { confirmationId, source } = pending;
    setPending(null);
    setBusy(true);

    try {
      const res = await confirmAction(confirmationId, approved);
      applyTextResponse(res);
      if (source === "voice" && res.type === "reply" && res.reply) {
        setVoiceState("speaking");
        try {
          const { audio_base64 } = await speak(res.reply);
          await playReply(res.reply, audio_base64);
        } finally {
          setVoiceState("idle");
        }
      }
    } catch (err) {
      setMessages((prev) => [...prev, { role: "assistant", text: `Error: ${(err as Error).message}` }]);
    } finally {
      setBusy(false);
    }
  }

  const orbBackground = connected ? ORB_COLORS[voiceState] : "radial-gradient(circle at 35% 30%, #999, #444)";
  const statusText = !connected
    ? "Connecting..."
    : { idle: "Connected — say “Hey Jarvis”", listening: "Listening...", thinking: "Thinking...", speaking: "Speaking..." }[
        voiceState
      ];

  return (
    <div style={{ maxWidth: 640, margin: "40px auto", fontFamily: "sans-serif" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
        <div
          style={{
            width: 72,
            height: 72,
            borderRadius: "50%",
            background: orbBackground,
            boxShadow: connected ? "0 0 24px 4px rgba(0,0,0,0.15)" : "none",
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
            {statusText}
          </div>
          {micError && <div style={{ fontSize: 12, color: "#c92a2a" }}>Mic: {micError}</div>}
        </div>
      </div>

      <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12, minHeight: 320 }}>
        {messages.map((m, i) => (
          <div key={i} style={{ margin: "8px 0" }}>
            <strong>{m.role === "user" ? "You" : "NEXUS"}:</strong> {m.text}
          </div>
        ))}
      </div>

      {pending && (
        <div
          style={{
            border: "2px solid #f08c00",
            borderRadius: 8,
            padding: 12,
            margin: "12px 0",
            background: "#fff9db",
          }}
        >
          <div style={{ marginBottom: 8 }}>
            <strong>Confirm ({pending.toolName}):</strong> {pending.summary}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={() => handleConfirm(true)}
              style={{ padding: "6px 16px", background: "#12B886", color: "#fff", border: "none", borderRadius: 4 }}
            >
              Approve
            </button>
            <button
              onClick={() => handleConfirm(false)}
              style={{ padding: "6px 16px", background: "#c92a2a", color: "#fff", border: "none", borderRadius: 4 }}
            >
              Deny
            </button>
          </div>
        </div>
      )}

      <form onSubmit={handleSend} style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask NEXUS to do something..."
          style={{ flex: 1, padding: 8 }}
          disabled={busy || !!pending}
        />
        <button type="submit" disabled={busy || !!pending}>
          {busy ? "..." : "Send"}
        </button>
      </form>
    </div>
  );
}
