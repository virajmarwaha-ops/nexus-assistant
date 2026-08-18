# Setting up NEXUS from zero

*Written the same plain way as [PLAN.md](PLAN.md) — every step spelled out, nothing assumed. If you
ever wiped this folder and started over, this is the document that gets you back to a working NEXUS.*

---

## 1. What you need installed first

| What | Why | Where to get it |
|---|---|---|
| **Python 3.12** | Runs the backend (the "brain"). | python.org — **tick "Add python.exe to PATH"** on the install screen |
| **Node.js 18 or newer** | Runs the frontend (the "face") and the Electron app window. | nodejs.org, the LTS version |
| **Tesseract OCR** | NEXUS screenshots the screen after sending a WhatsApp to check it actually worked — this is the tool that reads text out of that screenshot. | github.com/UB-Mannheim/tesseract → run the Windows installer |
| **A Groq API key** | The AI "brain" itself, and also the ears (speech-to-text). Free tier is enough to start. | console.groq.com → API Keys (about 2 minutes) |

You don't need an OpenAI or Anthropic key — Groq alone runs the whole thing, and NEXUS falls back to
Windows' own built-in voice if text-to-speech ever fails.

---

## 2. Get the code

```bash
git clone https://github.com/virajmarwaha-ops/nexus-assistant.git
cd nexus-assistant
```

(If you already have the folder, just `git pull` instead.)

---

## 3. Set up the backend (the brain)

```bash
python -m venv venv
venv\Scripts\activate
pip install -r backend/requirements.txt
```

The first line makes a private Python install just for this project, so it can't clash with
anything else on your PC. The second line switches your terminal into it — you'll see `(venv)`
appear at the start of the prompt. The third installs everything NEXUS's backend needs.

---

## 4. Set up the frontend (the face)

```bash
cd frontend
npm install
cd ..
```

This downloads the window/orb UI's own dependencies (React, Electron, etc.) — a one-time step.

---

## 5. Add your API key

Copy the example environment file and fill in your real key:

```bash
copy .env.example .env
```

Open `.env` in any text editor. At minimum, fill in:

```
GROQ_API_KEY=gsk_...your real key...
TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe
DEFAULT_COUNTRY_CODE=91
```

Adjust `TESSERACT_PATH` if you installed Tesseract somewhere else, and `DEFAULT_COUNTRY_CODE` to
your own country's dialing code (without the `+`) if you're not in India. `.env` is listed in
`.gitignore` — it's never uploaded anywhere, treat it like a password.

---

## 6. Run it

From the project root, one command starts everything — backend, frontend, and the Electron window:

```bash
npm run dev
```

A window should open with a glowing cyan orb and, after a second or two, a green "connected" dot.
That dot is the backend and the window actually talking to each other over the WebSocket.

---

## 7. Run the tests

```bash
cd backend
pytest
```

These check the fiddly logic — phone number formatting, app-name matching, and especially the
confirm gate (does clicking Deny truly send nothing). They run entirely offline against fake data;
no real message is ever sent while testing, and no API key or internet connection is needed.

---

## 8. How you'll know it's actually working

Go through these in order — each one should pass before you try the next:

1. `npm run dev` → the window opens with a green connected dot.
2. `pytest` (from `backend/`) → all tests pass.
3. Type "open notepad" into the text box → Notepad opens.
4. Type "whatsapp my own number saying hi" → a confirm card appears → click **Approve** → the
   message arrives on your phone.
5. Try that again but click **Deny** instead → nothing is sent, and NEXUS says it cancelled.
6. Say "Hey Jarvis" out loud → the orb wakes up and starts listening → ask it the time → it answers
   out loud.
7. The full thing: *"Hey Jarvis, send a WhatsApp to \<a contact\> saying I'm running late"* →
   confirm card appears **and NEXUS also says it out loud** → say "yes" or click Approve → sent.

---

## 9. If something goes wrong

| What you see | What it means | Fix |
|---|---|---|
| `python is not recognised` | Python wasn't added to PATH | Reinstall Python and tick "Add to PATH" |
| `Port 5173 is already in use` | A previous `npm run dev` is still running somewhere | Close that window/terminal first, or find and end the leftover `node`/`electron` process |
| Backend starts but every reply says "hit its rate limit" | Groq's free-tier daily token cap is used up | Wait — it resets daily — or use a different `GROQ_API_KEY` |
| `ANTHROPIC_API_KEY is not set` / `OPENAI_API_KEY is not set` | You're running with a provider that isn't Groq but haven't added that key | Either add the key to `.env`, or stick with the Groq default |
| Microphone does nothing | Windows blocked mic access for the app | Settings → Privacy → Microphone → allow desktop apps |
| Defender warns "unknown publisher" | Normal for any app you built yourself, not a real warning | Click "More info" → "Run anyway" |
| WhatsApp opens but doesn't send | Its window wasn't focused when Enter was pressed | Known timing issue — try again, it usually works the second time |
| Wake word won't trigger | Background noise, or you're too far from the mic | Use `Ctrl+Shift+Space` to summon NEXUS instead of the wake word |
| It sends to the wrong person | The AI guessed wrong between similar contact names | This is exactly what the confirm card is for — read it before approving |
| OCR/screenshot errors mentioning tesseract | `TESSERACT_PATH` in `.env` doesn't match where it's actually installed | Find `tesseract.exe` on your PC and update the path |

If none of these match what you're seeing, copy the full error text (not a summary) — that's the
exact information needed to track it down.
