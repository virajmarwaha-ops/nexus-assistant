const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:8000";

let accessToken: string | null = null;

export async function login(passphrase: string): Promise<void> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ passphrase }),
  });

  if (!res.ok) {
    throw new Error("Login failed");
  }

  const data = await res.json();
  accessToken = data.access_token;
}

export async function sendMessage(message: string): Promise<string> {
  if (!accessToken) {
    throw new Error("Not authenticated — call login() first");
  }

  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ message }),
  });

  if (!res.ok) {
    throw new Error(`Chat request failed: ${res.status}`);
  }

  const data = await res.json();
  return data.reply as string;
}
