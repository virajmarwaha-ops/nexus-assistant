"""
The current date/time on the operator's PC — a natural first question to
ask a voice assistant, so it needs an actual answer rather than a decline.
"""

from __future__ import annotations

from datetime import datetime


def get_current_time() -> str:
    return datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
