"""
Screen capture + OCR tools.

These let the agent "see" the desktop: take a screenshot and optionally
run OCR over it (or a region of it) to read on-screen text.
"""

from __future__ import annotations

import base64
import io

import pyautogui
import pytesseract
from PIL import Image

from app.config import settings

if settings.tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_path


def take_screenshot(region: tuple[int, int, int, int] | None = None) -> Image.Image:
    """region = (left, top, width, height), or None for the full screen."""
    return pyautogui.screenshot(region=region)


def screenshot_base64(region: tuple[int, int, int, int] | None = None) -> str:
    image = take_screenshot(region=region)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def read_text_on_screen(region: tuple[int, int, int, int] | None = None) -> str:
    """OCR the screen (or a region of it) and return the extracted text."""
    image = take_screenshot(region=region)
    return pytesseract.image_to_string(image)


def find_text_location(target_text: str) -> list[dict]:
    """
    Return bounding boxes for every OCR word match on screen that
    contains `target_text` (case-insensitive substring match).
    """
    image = take_screenshot()
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

    matches = []
    needle = target_text.lower()
    for i, word in enumerate(data["text"]):
        if needle in word.lower().strip() and word.strip():
            matches.append(
                {
                    "text": word,
                    "x": data["left"][i],
                    "y": data["top"][i],
                    "width": data["width"][i],
                    "height": data["height"][i],
                }
            )
    return matches
