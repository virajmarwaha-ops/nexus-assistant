"""
Send a WhatsApp message via the `whatsapp://send` URI scheme, which opens
WhatsApp Desktop with the recipient's chat already open. We paste (never
type) the message itself so emoji/accents survive, then press Enter, then
OCR the screen to check the message actually appears rather than assuming
it worked.
"""

from __future__ import annotations

import re
import time
import webbrowser

import pyautogui
import pygetwindow as gw
import pyperclip

from app.config import settings
from app.tools.screen import read_text_on_screen


def _normalize_phone(phone: str) -> str:
    digits = re.sub(r"[^\d]", "", phone)
    if len(digits) == 10:
        digits = settings.default_country_code + digits
    if not re.match(r"^\d{10,15}$", digits):
        raise ValueError(f"'{phone}' doesn't look like a valid phone number")
    return digits


def _focus_whatsapp(timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        windows = [w for w in gw.getAllWindows() if "whatsapp" in w.title.lower()]
        if windows:
            try:
                windows[0].activate()
            except Exception:
                pass
            return
        time.sleep(0.3)


def whatsapp_send(message: str, phone: str | None = None, name: str | None = None) -> dict:
    """Send `message` to a WhatsApp contact identified by `phone` or `name`."""
    if not phone and not name:
        raise ValueError("Provide either 'phone' or 'name'")

    pyperclip.copy(message)

    if phone:
        target = _normalize_phone(phone)
        webbrowser.open(f"whatsapp://send?phone={target}")
        _focus_whatsapp()
        time.sleep(1.5)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.3)
        pyautogui.press("enter")
    else:
        webbrowser.open("whatsapp://")
        _focus_whatsapp()
        time.sleep(1.5)
        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.3)
        pyautogui.typewrite(name, interval=0.02)
        time.sleep(0.5)
        pyautogui.press("enter")
        time.sleep(0.5)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.3)
        pyautogui.press("enter")

    time.sleep(0.8)
    screen_text = read_text_on_screen()
    verified = message.strip().lower() in screen_text.lower()
    return {
        "sent_to": phone or name,
        "message": message,
        "verified": verified,
        "note": (
            "Message text found on screen after sending."
            if verified
            else "Could not confirm the message appeared on screen — check manually."
        ),
    }
