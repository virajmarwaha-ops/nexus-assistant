# NEXUS — Your Talking Computer Assistant (Windows 11)

*Written for someone who has never built something like this before. Every new word is explained
the first time it shows up. Nothing here assumes you already know what any of it means.*

---

## 1. What we are building

A program that sits on your Windows PC. You say **"Hey Jarvis"** out loud. It wakes up, listens,
does what you asked, and answers you **out loud**.

Like this:

> **You:** "Hey Jarvis... send a WhatsApp to Rahul saying I'll be late"
>
> **NEXUS:** *(opens WhatsApp, finds Rahul, types the message)*
> *(shows you a box on screen: "Send **I'll be late** to **Rahul**?" with an Approve button)*
>
> **You:** *(click Approve)*
>
> **NEXUS:** *(sends it)* "Sent it to Rahul."

That confirmation box is on purpose. More on why in section 6.

---

## 2. Words you will see in this plan

You don't need to memorise these. Come back here whenever one confuses you.

| Word | What it actually means |
|---|---|
| **Backend** | The "brain" part. It has no screen. It does the thinking and the working. Ours is written in **Python**. |
| **Frontend** | The "face" part. The thing you look at and click. Ours is written in **TypeScript/React**. |
| **They talk to each other** | The face sends messages to the brain, the brain sends answers back. |
| **WebSocket** | A permanent open phone line between the face and the brain. Normal web requests are like sending one letter and waiting for one reply. A WebSocket stays open so both sides can talk whenever they want — which we need, because audio is constantly flowing. |
| **API key** | A password that lets our program use someone else's AI. You sign up on a website, they give you a long secret string, you paste it into a file. Treat it like a bank password. |
| **LLM** | "Large Language Model" — the actual AI that understands your sentence and decides what to do. ChatGPT is an LLM. We'll use one from a company called **Groq** or **OpenRouter**. |
| **STT** | "Speech To Text" — turns your voice into written words. |
| **TTS** | "Text To Speech" — turns written words into a voice. |
| **Tool** | A single thing NEXUS knows how to do, like "open an app" or "send a WhatsApp". The AI picks which tool to use. Think of them as buttons the AI is allowed to press. |
| **Wake word** | The magic phrase that wakes it up. Ours is "Hey Jarvis". |
| **Electron** | The technology that turns a website into a real desktop app with its own window. Discord, Slack, and VS Code are all built this way. |
| **Terminal / PowerShell** | The black window where you type commands instead of clicking. On Windows it's called PowerShell. You'll use it a lot. |

---

## 3. What's in your folder right now, and why it doesn't work

Right now the folder has some starter code someone generated. **None of it runs.** Not "it has a
bug" — it genuinely cannot start. Here's the honest list:

1. **There is no voice code at all.** There's a shopping list of voice ingredients
   (`openai-whisper`, `edge-tts`), but zero lines of actual listening or speaking code. The
   headline feature is 0% built.
2. **There is nothing that can open an app.** No "open WhatsApp". No WhatsApp code anywhere. The
   main thing you asked for doesn't exist yet.
3. **Nothing is installed.** No libraries downloaded for either half. Typing "start" today does nothing.
4. **The brain's thinking loop is written wrong.** When the AI uses a tool, the answer has to be
   handed back in a very specific format. Our code hands it back as plain chat text
   (`agent.py` line 110). The AI gets confused and can't finish the job.
5. **It sends the AI an instruction the AI will reject.** In `llm_providers.py` line 55, the
   "system prompt" (the AI's standing orders) is put in the wrong slot. The AI service rejects it.
6. **The face is a bare grey box.** `App.tsx` is 99 lines of unstyled text boxes. Not the look you want.
7. **The website part uses a dead tool.** It uses `react-scripts`, which stopped being maintained
   and fights with modern Node. We swap it for **Vite**, which is the current standard and much faster.
8. **There's no save history.** `git` (the tool that saves versions of your work so you can undo
   mistakes) was accidentally set up on your entire home folder instead of this project, and has
   saved exactly 0 files. We fix that first.

**Plain version:** we're keeping the good ideas and roughly 20% of the code, and writing the rest.

---

## 4. How the whole thing works, as a story

Follow one sentence from your mouth to WhatsApp:

```
  1. Your microphone is always quietly listening.
        |
  2. A tiny local detector waits for the sound "Hey Jarvis".
     (This runs on YOUR PC. Nothing is sent anywhere until it hears the wake word.)
        |
  3. Heard it! The orb on screen lights up. Now it records what you say next.
        |
  4. You stop talking. It notices the silence and stops recording.
        |
  5. The recording goes to a speech service, which sends back text:
     "send a WhatsApp to Rahul saying I'll be late"
        |
  6. That text goes to the AI, along with a list of tools it's allowed to use.
        |
  7. The AI replies: "use the tool `whatsapp_send`, recipient=Rahul, message=I'll be late"
        |
  8. This is an OUTWARD action, so we STOP and ask you first. A card appears on screen.
        |
  9. You click Approve.
        |
 10. NEXUS opens WhatsApp, finds Rahul, pastes the message, presses Enter.
        |
 11. It takes a screenshot to check it actually worked.
        |
 12. The AI writes "Sent it to Rahul", which is turned into a voice and played to you.
```

Steps 2 and 10 are the tricky ones. Sections 5 and 6 explain them.

---

## 5. How NEXUS opens apps and sends WhatsApp on Windows

This is the part people assume is impossible. It isn't. Here's the trick.

### Opening any app

Windows can list every app in your Start Menu with one command:

```powershell
Get-StartApps
```

That gives back every app's **Name** and its **AppID** (Windows' internal name for it). We ask for
that list once, remember it, and when you say "open Obsidian" we find the closest matching name and
launch it. Fuzzy matching means "open whats app", "open whatsapp", and "open WhatsApp" all work.

### Sending a WhatsApp — the good trick

WhatsApp doesn't let programs control it directly. But it does register something called a **URI
scheme** — a special link, like `https://` but for WhatsApp. If Windows opens this link:

```
whatsapp://send?phone=919876543210&text=Hello%20from%20NEXUS
```

...WhatsApp opens, jumps to that person's chat, **and the message is already typed in the box.**
All that's left is pressing **Enter**.

Why this matters: the clumsy way is to have a robot blindly click around the screen, which breaks
the moment a window moves. This way, WhatsApp itself does the hard part and we only press one key.
*(I confirmed WhatsApp registers this `whatsapp://` scheme — it's how "click to chat" links work.)*

If you give a **name** instead of a phone number, we open WhatsApp, press `Ctrl+F` to search, type
the name, press Enter to open the top chat, then fill the message box.

### Two details that decide whether this actually works

- **We never "type" the message letter by letter.** Fake keystrokes mangle emoji, accents, and
  anything not plain English. Instead we **copy the message to your clipboard and press Ctrl+V**.
  This is the difference between "works when I test with *hi*" and "works with real messages".
- **We check, we don't assume.** After sending, NEXUS screenshots the window and includes it in the
  result — so a failed send shows up as failed, instead of NEXUS cheerfully lying that it worked.

### Good news about Windows

On a Mac, this whole category of feature needs the user to hunt through Security settings granting
"Accessibility" permission, and it fails silently and confusingly if they don't.
**Windows has no such wall.** This is genuinely easier on your PC. You may see a one-time Microsoft
Defender "unknown app" warning, and that's it.

---

## 6. The safety part (please don't skip this)

The AI can misunderstand you. If you say "message Rahul" and you have three Rahuls, it might guess
the wrong one. Once a WhatsApp is sent, **it cannot be unsent** — the person sees it.

So every tool gets a label:

| Label | Meaning | Examples |
|---|---|---|
| **safe** | Just do it | open an app, check the volume, take a screenshot, search the web, read a file |
| **confirm** | Stop and ask first | **send a WhatsApp**, send an email, delete a file, run a raw system command |

For a **confirm** tool, NEXUS freezes, shows you a card with the *exact* person and the *exact*
words, and waits. If you don't answer within a time limit it **cancels by itself** rather than
sending. Nothing goes out without you clicking Approve.

Your first test will be sending a message **to your own number**, so a mistake costs nothing.

---

## 7. What you'll need to sign up for

You need at least one AI account. All have free tiers to start.

| What | Why | Roughly costs |
|---|---|---|
| **Groq** (console.groq.com) | The thinking brain. Chosen because it is *extremely* fast, which matters when you're waiting for a spoken reply. | Free tier is generous |
| **OpenRouter** (openrouter.ai) | Alternative brain — one key gets you Google Gemini and many others. Good backup. | Pay as you go, cents |
| **OpenAI** (platform.openai.com) | Ears (Whisper) and voice (TTS). | Fractions of a cent per sentence |

**Money-saving option:** Groq also does speech-to-text (`whisper-large-v3-turbo`) very cheaply, and
Windows has a built-in voice. So a **Groq key alone** can run the whole thing. I'll build it so it
automatically uses whichever keys you have, and falls back to the built-in Windows voice so NEXUS
never goes silent. **Start with just Groq**, add OpenAI later only if you want a nicer voice.

You paste keys into a file called `.env`. That file is set to never be uploaded anywhere.

---

## 8. The build, in phases

Each phase ends with something you can actually see working. We don't move on until it does.

### Phase 0 — Tidy up (30 min)
- Fix the nested `nexus-assistant/nexus-assistant/` folder-inside-a-folder confusion.
- Set up **git** properly *inside this project* so every step is saved and undoable.
  *(Your home folder was accidentally made into a git repo. I'll leave that alone — separate mess, not ours.)*
- Delete `setup_nexus.py`. It was a one-time generator; we're replacing what it made.
- Save this plan into the project as `PLAN.md` so it lives next to the code.

### Phase 1 — Make it start ← *this is your "at least make it run together"*
**Goal: you type ONE command and both halves start and connect.**
- Backend set up with **Python 3.12** on Windows (the version with the best support across every
  library we need — not the newest, the most reliable).
- Throw out the dead `react-scripts` setup, replace with **Vite + Electron**.
- One command at the top: `npm run dev` → brain starts, face opens, and **the orb turns green when
  they're connected**. That green dot is proof they're talking.
- Cut ~10 unused libraries the old shopping list included but nothing uses.
- No login screen. It only ever listens to your own PC, so a password box is pointless friction.

**You'll see:** a window opens with a glowing orb and a green "connected" dot.

### Phase 2 — Make it do things (typed, no voice yet)
Voice adds a lot of ways to fail. So first we make everything work by **typing**, then add voice on
top of a thing we know already works.
- Tools: `open_app`, `close_app`, `list_apps`, `whatsapp_send`, `system control` (volume, lock),
  `open_url`, `web_search`, `screenshot`, `read/write file`.
- The confirm-before-sending gate from section 6.
- Rewrite the AI's thinking loop properly, fixing bugs #4 and #5 from section 3.

**You'll see:** you type "open notepad" → Notepad opens. You type "whatsapp my own number saying
hi" → a confirm card appears → you approve → the message arrives on your phone. **This is the
moment the project becomes real.**

### Phase 3 — Give it ears and a voice
- **"Hey Jarvis"** detection using openWakeWord. *Nice surprise: "hey_jarvis" is one of its
  ready-made detectors, so we download it rather than train it.*
- The microphone is read by the **Electron app**, not by Python. This matters: installing
  microphone libraries in Python on Windows is famously painful (`PyAudio` breaks constantly).
  Doing it in the app window avoids that entire problem.
- It notices when you stop talking, and stops recording by itself.
- **Barge-in:** talk while it's talking and it shuts up and listens. Makes it feel alive.

**You'll see:** say "Hey Jarvis, what time is it" and hear a spoken answer.

### Phase 4 — Make it look like Jarvis
- A **floating orb** with no window border, always on top, that reacts: calm when idle, pulsing when
  listening, swirling when thinking, glowing when speaking.
- **`Ctrl+Shift+Space` from anywhere** summons it, even from inside another app.
- A panel showing what you said, what it's replying, and a live list of what it's doing right now
  ("Opening WhatsApp → Finding Rahul → Waiting for your OK").
- Icon in the system tray so it's always one click away.
- Click-through when idle, so the orb never blocks what you're working on.

### Phase 5 — Make it trustworthy
- **Automated tests** for the fiddly logic: phone number formatting, app-name matching, and
  *especially* the confirm gate (does Deny truly send nothing?). These tests **never actually send
  a message** — the sending part is faked during testing.
- A `SETUP.md` written this same plain way, so you can set it up again from zero.
- A first-run checklist screen that tells you exactly what's missing if something isn't working.

---

## 9. How we'll work together

Because I'm on your Mac and NEXUS runs on your Windows PC:

1. I write the code here.
2. You copy the folder to your Windows PC (or I set up git so you `git pull` it — cleaner, I'll show you).
3. You run a command I give you, exactly as written.
4. **If you see red text, copy all of it and paste it to me.** Error messages are not failure —
   they are the exact information I need. Don't summarise them, paste the whole thing.
5. I fix it, you re-run.

That loop is normal and expected. Nothing works first try, and that's fine.

---

## 10. How we'll know it's actually done

In order — each one has to pass before the next:

1. `npm run dev` → window opens, green connected dot.
2. Tests pass when you run `pytest`.
3. Type "open notepad" → Notepad opens.
4. Type a WhatsApp to **your own number** → confirm card → approve → message arrives on your phone.
5. Click **Deny** instead → nothing is sent, and NEXUS says it cancelled. *(Just as important as #4.)*
6. Say "Hey Jarvis" → orb wakes → ask the time → hear it answered out loud.
7. **The full thing:** *"Hey Jarvis, send a WhatsApp to Rahul saying I'm running late"* → confirm →
   approve → sent.

---

## 11. Things that might go wrong (so they don't scare you)

| What you might see | What it means | Fix |
|---|---|---|
| "python is not recognised" | Python isn't installed, or wasn't added to PATH | Reinstall Python 3.12 and **tick "Add to PATH"** on the first screen |
| Microphone does nothing | Windows blocked mic access for the app | Settings → Privacy → Microphone → allow desktop apps |
| Defender warns "unknown publisher" | Normal for any app you built yourself | Click "More info" → "Run anyway" |
| WhatsApp opens but doesn't send | Its window wasn't focused when we pressed Enter | Known timing issue; we add a wait-and-retry |
| Wake word won't trigger | Background noise, or you're too far from the mic | We can lower the sensitivity, or just use `Ctrl+Shift+Space` instead |
| It sends to the wrong person | The AI guessed wrong between similar names | This is exactly what the confirm card is for — read it before approving |

---

## 12. Honest expectations

- **Phases 0–2 will work reliably.** Opening apps and the WhatsApp URI trick are solid ground.
- **Phase 3 (voice) usually needs tuning.** Wake words trigger on the TV, or miss you when you
  mumble. Expect to adjust sensitivity a few times. That's tuning, not breakage.
- **The WhatsApp *name* search is the most fragile piece.** Phone numbers are near-bulletproof;
  searching by contact name depends on WhatsApp's layout and can break when they update the app.
  We use numbers where we can and treat names as a convenience.
- **I cannot test any of this from here.** Every Windows claim in this plan is based on how Windows
  and WhatsApp are documented to behave, and I'm confident in it — but *confident* is not the same
  as *verified*. Real proof comes when you run it on your PC. I'll say so plainly if something
  turns out different from what I expected here.

---

## 13. What I need from you to start

1. A **Groq API key** from console.groq.com (free, ~2 minutes). Enough to start on its own.
2. Your **country code** for phone numbers — I'm assuming **+91 (India)** unless you say otherwise.
3. **A phone number you own**, for safe testing. Your own WhatsApp number is ideal.

You don't need any of these for Phase 0 and Phase 1 — I can start right now, and you can go get the
key while I build.
