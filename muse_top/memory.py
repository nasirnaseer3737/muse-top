"""Persistent fact memory for Muse Top.

Facts are stored as a simple key -> value JSON file (default
``~/.muse-top/memory.json``). Writes are atomic: write to a temp file,
then replace, so a crash mid-write never corrupts the store.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path


class Memory:
    """A tiny persistent key/value fact store."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._facts: dict[str, str] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self._facts = {}
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        if isinstance(data, dict):
            self._facts = {str(k): str(v) for k, v in data.items()}
        else:
            self._facts = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._facts, indent=2, ensure_ascii=False)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.path.parent), prefix=".memory-", suffix=".tmp")
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

    def remember(self, key: str, value: str) -> None:
        self._facts[key.strip().lower()] = value.strip()
        self.save()

    def recall(self, key: str) -> str | None:
        return self._facts.get(key.strip().lower())

    def forget(self, key: str) -> bool:
        removed = self._facts.pop(key.strip().lower(), None) is not None
        if removed:
            self.save()
        return removed

    def all(self) -> dict[str, str]:
        return dict(self._facts)

    def search(self, query: str) -> dict[str, str]:
        q = query.strip().lower()
        if not q:
            return {}
        return {k: v for k, v in self._facts.items() if q in k or q in v.lower()}

    def render_for_prompt(self) -> str:
        """Facts formatted for inclusion in an LLM prompt."""
        if not self._facts:
            return "No facts remembered yet."
        return "\n".join(f"- {k}: {v}" for k, v in sorted(self._facts.items()))
