"""Configuration for Muse Top — everything comes from environment variables.

No API key is ever stored in code. Set NZ_GEMINI_API_KEY in your shell
(or a .env file you load yourself) to use the real Gemini API.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    """Runtime configuration, read from the environment."""

    api_key: str = ""
    model: str = "gemini-2.0-flash"
    data_dir: Path = field(default_factory=lambda: Path.home() / ".muse-top")
    llm_timeout_seconds: int = 30
    max_history_turns: int = 10
    web_timeout_seconds: int = 15
    web_max_bytes: int = 512_000
    workspace_dir: Path = field(
        default_factory=lambda: Path.home() / ".muse-top" / "workspace"
    )
    file_max_bytes: int = 64_000

    @classmethod
    def from_env(cls) -> "Config":
        data_dir = Path(os.environ.get("MUSE_TOP_DATA_DIR", "")) or (Path.home() / ".muse-top")
        return cls(
            api_key=os.environ.get("NZ_GEMINI_API_KEY", "").strip(),
            model=os.environ.get("NZ_GEMINI_MODEL", "gemini-2.0-flash").strip() or "gemini-2.0-flash",
            data_dir=data_dir,
            llm_timeout_seconds=int(os.environ.get("MUSE_TOP_LLM_TIMEOUT", "30")),
            max_history_turns=int(os.environ.get("MUSE_TOP_MAX_HISTORY", "10")),
            web_timeout_seconds=int(os.environ.get("MUSE_TOP_WEB_TIMEOUT", "15")),
            web_max_bytes=int(os.environ.get("MUSE_TOP_WEB_MAX_BYTES", "512000")),
            workspace_dir=Path(os.environ.get("MUSE_TOP_WORKSPACE", ""))
            or (Path.home() / ".muse-top" / "workspace"),
            file_max_bytes=int(os.environ.get("MUSE_TOP_FILE_MAX_BYTES", "64000")),
        )

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)

    @property
    def memory_path(self) -> Path:
        return self.data_dir / "memory.json"

    @property
    def history_path(self) -> Path:
        return self.data_dir / "history.json"
