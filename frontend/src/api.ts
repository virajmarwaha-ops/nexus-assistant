const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const WS_BASE = import.meta.env.VITE_WS_BASE || "ws://localhost:8000";

export const WS_URL = `${WS_BASE}/ws`;

export interface ChatResponse {
  type: "reply" | "confirm";
  reply?: string;
  confirmation_id?: string;
  tool_name?: string;
  summary?: string;
  arguments?: Record<string, unknown>;
}

async function postJson(path: string, body: unknown): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail || `Request failed: ${res.status}`);
  }

  return res.json();
}

export function sendMessage(message: string): Promise<ChatResponse> {
  return postJson("/chat", { message });
}

export function confirmAction(confirmationId: string, approved: boolean): Promise<ChatResponse> {
  return postJson("/chat/confirm", { confirmation_id: confirmationId, approved });
}
