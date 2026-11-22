"""Sandboxed file tools for Muse Top — stdlib only.

``read_file`` / ``write_file`` operate only inside the agent's workspace
folder (default ``~/.muse-top/workspace``). Absolute paths and ``..``
escapes are refused, and symlinks that point outside the workspace are
refused too, so the agent can never read or write outside its sandbox.
Anything a tool cannot do comes back as an error string, so the agent
loop never crashes on a bad path.
"""
from __future__ import annotations

from pathlib import Path

DEFAULT_FILE_MAX_BYTES = 64_000  # 64 KB of file text is plenty for the agent


def resolve_workspace_path(workspace: Path, path: str) -> Path | None:
    """Resolve ``path`` inside ``workspace``.

    Returns the resolved absolute path, or ``None`` when the path would
    escape the workspace (absolute path, ``..`` traversal, or a symlink
    pointing outside).
    """
    raw = (path or "").strip()
    if not raw:
        return None
    candidate = Path(raw)
    if candidate.is_absolute():
        return None
    resolved = (workspace / candidate).resolve()
    workspace_resolved = workspace.resolve()
    if not resolved.is_relative_to(workspace_resolved):
        return None
    return resolved


def read_file(
    workspace: Path, path: str, max_bytes: int = DEFAULT_FILE_MAX_BYTES
) -> str:
    """Return the text of a workspace file, or an error string."""
    resolved = resolve_workspace_path(workspace, path)
    if resolved is None:
        return f"Error: '{path}' is outside the workspace."
    if not resolved.exists():
        return f"Error: file not found: '{path}'."
    if resolved.is_dir():
        return f"Error: '{path}' is a directory, not a file."
    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        return f"Error reading '{path}': {exc}."
    truncated = len(raw) > max_bytes
    text = raw[:max_bytes].decode("utf-8", errors="replace")
    lines = [f"File: {path}"]
    lines.append(text if text else "(file is empty)")
    if truncated:
        lines.append(f"(Note: file cut off after {max_bytes} bytes.)")
    return "\n".join(lines)


def write_file(workspace: Path, path: str, content: str) -> str:
    """Write ``content`` to a workspace file, creating parent folders.

    Returns a confirmation, or an error string when the path escapes
    the workspace.
    """
    resolved = resolve_workspace_path(workspace, path)
    if resolved is None:
        return f"Error: '{path}' is outside the workspace."
    if resolved.is_dir():
        return f"Error: '{path}' is a directory, not a file."
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        data = (content or "").encode("utf-8")
        resolved.write_bytes(data)
    except OSError as exc:
        return f"Error writing '{path}': {exc}."
    return f"Wrote {len(data)} bytes to '{path}'."
