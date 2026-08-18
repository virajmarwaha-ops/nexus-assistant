"""
First-run checklist: quick, synchronous checks for the setup steps most
likely to be missing (see SETUP.md's troubleshooting table) — surfacing
exactly what's wrong up front beats a cryptic error three steps into
actually trying to use NEXUS.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from app.config import settings


def _tesseract_found() -> bool:
    if settings.tesseract_path and Path(settings.tesseract_path).is_file():
        return True
    return shutil.which("tesseract") is not None


def run_checklist() -> list[dict]:
    return [
        {
            "id": "groq_api_key",
            "label": "Groq API key",
            "ok": bool(settings.groq_api_key),
            "hint": "Add GROQ_API_KEY to your .env file — see SETUP.md section 5.",
        },
        {
            "id": "tesseract",
            "label": "Tesseract OCR",
            "ok": _tesseract_found(),
            "hint": (
                "Install Tesseract OCR and set TESSERACT_PATH in .env to where it "
                "was installed — see SETUP.md section 1."
            ),
        },
    ]
