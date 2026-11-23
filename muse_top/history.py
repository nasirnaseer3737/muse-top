"""Persistent conversation history for Muse Top.

The last ``max_turns`` turns (user + assistant message pairs) are kept
in a JSON file (default ``~/.muse-top/history.json``) so the agent
remembers the conversation across restarts. The agent loads the history
on start and includes it in every prompt.

The file format is a list of ``{"role": "User"|"Assistant", "text": ...}``
objects, oldest first. Writes are atomic (temp file + replace) and a
corrupt or oddly-shaped file starts empty instead of crashing.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

ROLES = ("User", "Assistant")


class History:
    """A capped, persistent list of conversation turns."""

    def __init__(self, path: Path, max_turns: int = 10) -> None:
        self.path = Path(path)
        self.max_turns = max(1, int(max_turns))
        self._entries: list[tuple[str, str]] = []
        self.load()

    @property
    def max_entries(self) -> int:
        """Maximum stored messages (two per turn)."""
        return self.max_turns * 2

    def load(self) -> None:
        if not self.path.exists():
            self._entries = []
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = None
        entries: list[tuple[str, str]] = []
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                role = item.get("role")
                text = item.get("text")
                if role in ROLES and isinstance(text, str):
                    entries.append((role, text))
        self._entries = entries[-self.max_entries :]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            [{"role": role, "text": text} for role, text in self._entries],
            indent=2,
            ensure_ascii=False,
        )
        fd, tmp_name = tempfile.mkstemp(dir=str(self.path.parent), prefix=".history-", suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            Path(tmp_name).replace(self.path)
        except OSError:
            try:
                Path(tmp_name).unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def append(self, role: str, text: str) -> None:
        """Add one message and persist, dropping the oldest beyond the cap."""
        if role not in ROLES:
            raise ValueError(f"role must be one of {ROLES}, got {role!r}")
        self._entries.append((role, text))
        self._entries = self._entries[-self.max_entries :]
        self.save()

    def turns(self) -> list[tuple[str, str]]:
        """All stored messages, oldest first."""
        return list(self._entries)

    def clear(self) -> None:
        self._entries = []
        self.save()

    def render(self) -> str:
        """Messages formatted for inclusion in an LLM prompt."""
        if not self._entries:
            return ""
        return "\n".join(f"{role}: {text}" for role, text in self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __getitem__(self, index):
        return self._entries[index]
