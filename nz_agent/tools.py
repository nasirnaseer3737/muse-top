"""Tool registry for NZ Agent.

A tool is a named Python function with a short description. The agent
asks the LLM to emit ``CALL <name> <json-args>`` lines; the registry
executes them and returns the result as text. New tools register with
one decorator — see the built-ins at the bottom.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable


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


def build_default_registry(memory) -> ToolRegistry:
    """Registry with the Day-1 built-in tools."""
    registry = ToolRegistry()

    @registry.tool("get_current_time", "Returns the current date and time.")
    def _get_current_time() -> str:
        return datetime.now().strftime("%A, %d %B %Y, %H:%M %Z")

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
