"""
Open, close, and list installed Windows applications.

Windows can list every Start Menu entry with `Get-StartApps`, giving back
each app's display Name and its AppID. We fuzzy-match the name the user
said against that list, then launch via `shell:appsFolder\\<AppID>` — the
same mechanism Windows itself uses, so it works uniformly for both
traditional desktop apps and packaged (Store) apps.
"""

from __future__ import annotations

import difflib
import json
import subprocess

_APPS_CACHE: list[dict] | None = None


def _run_powershell(command: str) -> str:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "PowerShell command failed")
    return result.stdout


def _load_apps(force: bool = False) -> list[dict]:
    global _APPS_CACHE
    if _APPS_CACHE is not None and not force:
        return _APPS_CACHE

    output = _run_powershell("Get-StartApps | ConvertTo-Json -Compress")
    data = json.loads(output) if output.strip() else []
    if isinstance(data, dict):
        data = [data]
    _APPS_CACHE = [{"name": a["Name"], "app_id": a["AppID"]} for a in data]
    return _APPS_CACHE


def list_apps(refresh: bool = False) -> list[str]:
    return sorted(a["name"] for a in _load_apps(force=refresh))


def _fuzzy_match(query: str, candidates: list[str]) -> str:
    # Substring match takes priority over difflib's whole-string ratio: for a
    # short query like "edge", get_close_matches actually prefers "Notepad"
    # over "Microsoft Edge" (ratio is computed against full string length, so
    # a short query scores better against a short-but-unrelated candidate
    # than against a long candidate that literally contains it). A plain
    # substring hit is a much stronger signal than that ratio for this case.
    lowered = query.lower()
    substr = [c for c in candidates if lowered in c.lower()]
    if substr:
        return substr[0]
    matches = difflib.get_close_matches(query, candidates, n=1, cutoff=0.3)
    if not matches:
        raise LookupError(f"No match for '{query}'")
    return matches[0]


def _best_app_match(query: str) -> dict:
    apps = _load_apps()
    names = [a["name"] for a in apps]
    try:
        match_name = _fuzzy_match(query, names)
    except LookupError:
        raise LookupError(f"No installed app matches '{query}'") from None
    return next(a for a in apps if a["name"] == match_name)


def open_app(name: str) -> str:
    app = _best_app_match(name)
    subprocess.Popen(["explorer.exe", f"shell:appsFolder\\{app['app_id']}"])
    return f"Opened {app['name']}"


def _running_process_names() -> list[str]:
    output = _run_powershell("Get-Process | Select-Object -ExpandProperty ProcessName")
    return [line.strip() for line in output.splitlines() if line.strip()]


def close_app(name: str) -> str:
    processes = _running_process_names()
    try:
        process_name = _fuzzy_match(name, processes)
    except LookupError:
        raise LookupError(f"No running process matches '{name}'") from None
    result = subprocess.run(
        ["taskkill", "/IM", f"{process_name}.exe", "/F"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Could not close {process_name}")
    return f"Closed {process_name}"
