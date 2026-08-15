"""
Basic OS-level controls: volume and locking the workstation. Volume uses
the same virtual media keys a physical keyboard would send, so it works
regardless of which app has focus.
"""

from __future__ import annotations

import ctypes

import pyautogui


def volume_up(steps: int = 2) -> str:
    for _ in range(steps):
        pyautogui.press("volumeup")
    return "Volume increased"


def volume_down(steps: int = 2) -> str:
    for _ in range(steps):
        pyautogui.press("volumedown")
    return "Volume decreased"


def mute(unmute: bool = False) -> str:
    pyautogui.press("volumemute")
    return "Unmuted" if unmute else "Muted"


def lock_screen() -> str:
    ctypes.windll.user32.LockWorkStation()
    return "Locked the screen"
