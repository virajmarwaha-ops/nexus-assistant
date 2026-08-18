import React, { useEffect, useRef, useState } from "react";
import { ChatResponse, ChecklistItem, confirmAction, getChecklist, sendMessage, speak, WS_URL } from "./api";
import ChecklistScreen from "./ChecklistScreen";
import HudOrb, { VoiceState } from "./HudOrb";
import "./hud.css";
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

export default function App(): JSX.Element {
  const [connected, setConnected] = useState(false);
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [micError, setMicError] = useState<string | null>(null);

  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<PendingConfirmation | null>(null);

  const [clock, setClock] = useState(() => new Date());

  const [checklist, setChecklist] = useState<ChecklistItem[] | null>(null);
  const [checklistChecking, setChecklistChecking] = useState(true);
  const [checklistDismissed, setChecklistDismissed] = useState(false);

  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const voiceClientRef = useRef<VoiceClient | null>(null);

  const runChecklist = React.useCallback(() => {
    setChecklistChecking(true);
    getChecklist()
      .then(setChecklist)
      .catch(() => setChecklist(null)) // backend unreachable — nothing useful to show yet, let the connection indicator handle it
      .finally(() => setChecklistChecking(false));
  }, []);

  useEffect(() => {
    runChecklist();
  }, [runChecklist]);

  useEffect(() => {
    const id = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    window.nexus?.reportVoiceState?.(voiceState);
  }, [voiceState]);

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
            break;
          case "confirm_resolved":
            // The pending confirmation was just answered by voice — drop the
            // on-screen card so a stale Approve/Deny click can't double-resolve it.
            setPending((prev) => (prev?.confirmationId === payload.confirmation_id ? null : prev));
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

  const statusText = !connected
    ? "Connecting..."
    : { idle: "Standing by — say “Hey Jarvis”", listening: "Listening", thinking: "Processing", speaking: "Speaking" }[
        voiceState
      ];

  if (checklist && !checklist.every((item) => item.ok) && !checklistDismissed) {
    return (
      <ChecklistScreen
        items={checklist}
        checking={checklistChecking}
        onRecheck={runChecklist}
        onContinueAnyway={() => setChecklistDismissed(true)}
      />
    );
  }

  return (
    <div className="hud-root">
      <div className="hud-corner-frame" />

      <div
        className="hud-drag-region"
        style={{ display: "flex", justifyContent: "space-between", padding: "24px 32px 0", flexShrink: 0 }}
      >
        <div className="hud-panel" style={{ width: 230 }}>
          <div className="hud-panel-title">Date / Time</div>
          <div className="hud-clock">{clock.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</div>
          <div className="hud-date">
            {clock.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" }).toUpperCase()}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8 }}>
          <div className="hud-label" style={{ letterSpacing: 4, fontSize: 13, color: "var(--hud-cyan)" }}>
            NEXUS
          </div>
          <div className="hud-panel" style={{ width: 230, textAlign: "right" }}>
            <div className="hud-panel-title">Status</div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, justifyContent: "flex-end" }}>
              <span
                className={connected ? "hud-pulse" : undefined}
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: connected ? "var(--hud-idle)" : "var(--hud-red)",
                  boxShadow: connected ? "0 0 6px var(--hud-idle)" : "none",
                  display: "inline-block",
                }}
              />
              {statusText}
            </div>
            {micError && <div className="hud-mic-error" style={{ marginTop: 6 }}>Mic: {micError}</div>}
          </div>
        </div>
      </div>

      <div style={{ display: "flex", justifyContent: "center", flexShrink: 0, margin: "4px 0" }}>
        <HudOrb connected={connected} voiceState={voiceState} />
      </div>

      <div
        style={{
          flex: 1,
          minHeight: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 28,
          padding: "0 32px 28px",
        }}
      >
        <div className="hud-deco-ring" aria-hidden="true" />

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            width: 640,
            maxWidth: "100%",
            height: "100%",
            gap: 12,
          }}
        >
          <div className="hud-panel" style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
            <div className="hud-panel-title">Transcript</div>
            <div className="hud-messages">
              {messages.map((m, i) => (
                <div key={i}>
                  <span className="hud-message-role">{m.role === "user" ? "YOU" : "NEXUS"}:</span>
                  {m.text}
                </div>
              ))}
            </div>
          </div>

          {pending && (
            <div className="hud-panel hud-confirm-panel">
              <div className="hud-panel-title">Confirm — {pending.toolName}</div>
              <div style={{ marginBottom: 10 }}>{pending.summary}</div>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="hud-button" onClick={() => handleConfirm(true)}>
                  Approve
                </button>
                <button className="hud-button hud-button-danger" onClick={() => handleConfirm(false)}>
                  Deny
                </button>
              </div>
            </div>
          )}

          <form onSubmit={handleSend} className="hud-input-row">
            <input
              className="hud-input"
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask NEXUS to do something..."
              disabled={busy || !!pending}
            />
            <button className="hud-button" type="submit" disabled={busy || !!pending}>
              {busy ? "..." : "Send"}
            </button>
          </form>
        </div>

        <div className="hud-deco-ring hud-deco-ring-reverse" aria-hidden="true" />
      </div>
    </div>
  );
}
