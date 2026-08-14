"""
File system tools, sandboxed to settings.allowed_file_root.

Every path the agent touches is resolved and checked against the allowed
root before any read/write/list/delete happens, to stop path-traversal
(e.g. "../../etc/passwd") from escaping the sandbox.
"""

from __future__ import annotations

from pathlib import Path

from app.config import settings


class FileAccessError(PermissionError):
    pass


def _resolve_within_root(relative_path: str) -> Path:
    root = Path(settings.allowed_file_root).resolve()
    candidate = (root / relative_path).resolve()

    if root not in candidate.parents and candidate != root:
        raise FileAccessError(
            f"Path '{relative_path}' resolves outside the allowed root '{root}'"
        )
    return candidate


def list_dir(relative_path: str = ".") -> list[str]:
    target = _resolve_within_root(relative_path)
    if not target.is_dir():
        raise NotADirectoryError(f"{target} is not a directory")
    return sorted(p.name for p in target.iterdir())


def read_file(relative_path: str, max_bytes: int = 1_000_000) -> str:
    target = _resolve_within_root(relative_path)
    if not target.is_file():
        raise FileNotFoundError(f"{target} does not exist")
    data = target.read_bytes()[:max_bytes]
    return data.decode("utf-8", errors="replace")


def write_file(relative_path: str, content: str, overwrite: bool = True) -> str:
    target = _resolve_within_root(relative_path)
    if target.exists() and not overwrite:
        raise FileExistsError(f"{target} already exists and overwrite=False")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return str(target)


def delete_file(relative_path: str) -> None:
    target = _resolve_within_root(relative_path)
    if not target.is_file():
        raise FileNotFoundError(f"{target} does not exist")
    target.unlink()
