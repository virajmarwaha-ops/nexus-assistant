"""
Open URLs and run web searches through the operator's default browser.
"""

from __future__ import annotations

import urllib.parse
import webbrowser


def open_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    webbrowser.open(url)
    return f"Opened {url}"


def web_search(query: str) -> str:
    url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    webbrowser.open(url)
    return f"Searched for '{query}'"
