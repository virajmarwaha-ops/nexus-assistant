"""
Mouse and keyboard control tools.

Wraps pyautogui with small safety rails (a fail-safe corner and
bounds checking) since these calls act on the operator's real desktop.
"""

from __future__ import annotations

import pyautogui

# Moving the mouse to a screen corner aborts execution — keep this on.
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


def _clamp_to_screen(x: int, y: int) -> tuple[int, int]:
    width, height = pyautogui.size()
    return max(0, min(x, width - 1)), max(0, min(y, height - 1))


def move_mouse(x: int, y: int, duration: float = 0.2) -> None:
    x, y = _clamp_to_screen(x, y)
    pyautogui.moveTo(x, y, duration=duration)


def click(x: int | None = None, y: int | None = None, button: str = "left") -> None:
    if x is not None and y is not None:
        x, y = _clamp_to_screen(x, y)
        pyautogui.click(x=x, y=y, button=button)
    else:
        pyautogui.click(button=button)


def double_click(x: int, y: int) -> None:
    x, y = _clamp_to_screen(x, y)
    pyautogui.doubleClick(x=x, y=y)


def type_text(text: str, interval: float = 0.02) -> None:
    pyautogui.typewrite(text, interval=interval)


def press_key(key: str) -> None:
    """Press a single key, e.g. 'enter', 'esc', 'tab'."""
    pyautogui.press(key)


def hotkey(*keys: str) -> None:
    """Press a key combination, e.g. hotkey('ctrl', 'c')."""
    pyautogui.hotkey(*keys)


def scroll(amount: int) -> None:
    """Positive scrolls up, negative scrolls down."""
    pyautogui.scroll(amount)
