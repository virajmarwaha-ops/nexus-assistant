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

async function postJson<T>(path: string, body: unknown): Promise<T> {
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
  return postJson<ChatResponse>("/chat", { message });
}

export function confirmAction(confirmationId: string, approved: boolean): Promise<ChatResponse> {
  return postJson<ChatResponse>("/chat/confirm", { confirmation_id: confirmationId, approved });
}

export interface TTSResponse {
  audio_base64: string | null;
}

export function speak(text: string): Promise<TTSResponse> {
  return postJson<TTSResponse>("/tts", { text });
}

export interface ChecklistItem {
  id: string;
  label: string;
  ok: boolean;
  hint: string;
}

export async function getChecklist(): Promise<ChecklistItem[]> {
  const res = await fetch(`${API_BASE}/system/checklist`);
  if (!res.ok) throw new Error(`Checklist request failed: ${res.status}`);
  return res.json();
}
