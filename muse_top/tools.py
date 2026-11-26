"""Tool registry for Muse Top.

A tool is a named Python function with a short description. The agent
asks the LLM to emit ``CALL <name> <json-args>`` lines; the registry
executes them and returns the result as text. New tools register with
one decorator — see the built-ins at the bottom.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable


from .email_draft import create_draft, list_drafts
from .files import read_file, write_file
from .leads import score_leads_file
from .schedule import Scheduler
from .web import fetch_url


@dataclass
class Tool:
    name: str
    description: str
    func: Callable[..., str]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def tool(self, name: str, description: str):
        """Decorator to register a function as a tool."""

        def decorator(func: Callable[..., str]) -> Callable[..., str]:
            self._tools[name] = Tool(name=name, description=description, func=func)
            return func

        return decorator

    def register(self, name: str, description: str, func: Callable[..., str]) -> None:
        self._tools[name] = Tool(name=name, description=description, func=func)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def describe(self) -> str:
        """Tool list formatted for inclusion in an LLM prompt."""
        if not self._tools:
            return "No tools available."
        lines = []
        for name in self.names():
            tool = self._tools[name]
            lines.append(f"- {tool.name}: {tool.description}")
        return "\n".join(lines)

    def call(self, name: str, args: dict | None = None) -> str:
        """Execute a tool by name. Unknown tools and errors return text, never raise."""
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: no tool named '{name}'."
        try:
            result = tool.func(**(args or {}))
        except TypeError as exc:
            return f"Error calling '{name}': bad arguments ({exc})."
        except Exception as exc:  # noqa: BLE001 — tools must never crash the agent
            return f"Error calling '{name}': {exc}."
        return str(result)


def build_default_registry(memory, config=None) -> ToolRegistry:
    """Registry with the Day-1 built-in tools."""
    registry = ToolRegistry()

    @registry.tool("get_current_time", "Returns the current date and time.")
    def _get_current_time() -> str:
        return datetime.now().strftime("%A, %d %B %Y, %H:%M %Z")

    @registry.tool(
        "web_fetch",
        "Fetch a web page and return its title + readable text. Args: url.",
    )
    def _web_fetch(url: str) -> str:
        timeout = getattr(config, "web_timeout_seconds", 15) if config else 15
        max_bytes = getattr(config, "web_max_bytes", 512_000) if config else 512_000
        return fetch_url(url, timeout_seconds=timeout, max_bytes=max_bytes)

    @registry.tool("remember_fact", "Remember a fact. Args: key, value.")
    def _remember_fact(key: str, value: str) -> str:
        memory.remember(key, value)
        return f"Remembered: {key} = {value}"

    @registry.tool("recall_fact", "Recall a remembered fact. Args: key.")
    def _recall_fact(key: str) -> str:
        value = memory.recall(key)
        if value is None:
            return f"No fact remembered for '{key}'."
        return f"{key} = {value}"

    @registry.tool(
        "read_file",
        "Read a text file inside the agent workspace. Args: path (relative to the workspace).",
    )
    def _read_file(path: str) -> str:
        workspace = getattr(config, "workspace_dir", None) if config else None
        if workspace is None:
            workspace = Path.home() / ".muse-top" / "workspace"
        max_bytes = getattr(config, "file_max_bytes", 64_000) if config else 64_000
        return read_file(workspace, path, max_bytes=max_bytes)

    @registry.tool(
        "write_file",
        "Write text to a file inside the agent workspace (creates folders). Args: path (relative to the workspace), content.",
    )
    def _write_file(path: str, content: str) -> str:
        workspace = getattr(config, "workspace_dir", None) if config else None
        if workspace is None:
            workspace = Path.home() / ".muse-top" / "workspace"
        return write_file(workspace, path, content)

    @registry.tool(
        "draft_email",
        "Build an email draft and save it — never sends. Args: to, subject, body, cc (optional), bcc (optional).",
    )
    def _draft_email(
        to, subject: str, body: str = "", cc=None, bcc=None
    ) -> str:
        drafts_dir = getattr(config, "drafts_dir", None) if config else None
        if drafts_dir is None:
            drafts_dir = Path.home() / ".muse-top" / "drafts"
        return create_draft(drafts_dir, to, subject, body, cc=cc, bcc=bcc)

    @registry.tool("list_drafts", "List saved email drafts (newest first).")
    def _list_drafts() -> str:
        drafts_dir = getattr(config, "drafts_dir", None) if config else None
        if drafts_dir is None:
            drafts_dir = Path.home() / ".muse-top" / "drafts"
        return list_drafts(drafts_dir)

    @registry.tool(
        "schedule",
        "Schedule a task for the agent to run later. Args: task, when (e.g. 'tomorrow 14:00', 'in 30 minutes', '2026-11-26 14:00').",
    )
    def _schedule(task: str, when: str) -> str:
        schedule_path = getattr(config, "schedule_path", None) if config else None
        if schedule_path is None:
            schedule_path = Path.home() / ".muse-top" / "schedule.json"
        return Scheduler(schedule_path).add(task, when)

    @registry.tool("list_tasks", "List scheduled tasks (soonest first).")
    def _list_tasks() -> str:
        schedule_path = getattr(config, "schedule_path", None) if config else None
        if schedule_path is None:
            schedule_path = Path.home() / ".muse-top" / "schedule.json"
        return Scheduler(schedule_path).render_list()

    @registry.tool("cancel_task", "Cancel a scheduled task. Args: id.")
    def _cancel_task(id: str) -> str:
        schedule_path = getattr(config, "schedule_path", None) if config else None
        if schedule_path is None:
            schedule_path = Path.home() / ".muse-top" / "schedule.json"
        return Scheduler(schedule_path).cancel(id)

    @registry.tool(
        "score_leads",
        "Score a leads CSV in the workspace 0-100 (grades A-D, TCPA consent flag; no-consent leads are DO-NOT-CONTACT). Args: path (relative to the workspace), top (optional, default 5).",
    )
    def _score_leads(path: str, top: int = 5) -> str:
        workspace = getattr(config, "workspace_dir", None) if config else None
        if workspace is None:
            workspace = Path.home() / ".muse-top" / "workspace"
        max_bytes = getattr(config, "file_max_bytes", 64_000) if config else 64_000
        max_rows = getattr(config, "lead_max_rows", 500) if config else 500
        return score_leads_file(
            workspace, path, top=top, max_bytes=max_bytes, max_rows=max_rows
        )

    return registry


def parse_tool_call(line: str) -> tuple[str, dict] | None:
    """Parse a ``CALL <name> <json-args>`` line. Returns (name, args) or None."""
    line = line.strip()
    if not line.startswith("CALL "):
        return None
    rest = line[5:].strip()
    if not rest:
        return None
    name, _, arg_text = rest.partition(" ")
    arg_text = arg_text.strip()
    if not arg_text:
        return name, {}
    try:
        args = json.loads(arg_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(args, dict):
        return None
    return name, args
