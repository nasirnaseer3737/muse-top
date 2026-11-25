"""Command-line chat for Muse Top: ``python -m muse_top``."""
from __future__ import annotations

import sys

from .agent import Agent
from .config import Config

HELP = """Commands:
  /help     show this help
  /tools    list registered tools
  /memory   list remembered facts
  /history  show the recent conversation
  /drafts   list saved email drafts
  /tasks    list scheduled tasks
  /exit     quit
Just type a message to chat with the agent.
"""


def main(argv: list[str] | None = None) -> int:
    config = Config.from_env()
    agent = Agent(config=config)
    if argv and argv[0] == "run":
        if argv[1:] == ["--once"]:
            print(agent.run_due_tasks())
            return 0
        print("Usage: python -m muse_top run --once")
        print("(A looping scheduler mode is not implemented yet.)")
        return 2
    mode = "Gemini API" if config.has_api_key else "MOCK MODE (no NZ_GEMINI_API_KEY set)"
    print(f"Muse Top v0.1.0 — running in {mode}. Type /help for commands, /exit to quit.")
    if argv:
        reply = agent.chat(" ".join(argv))
        print(reply)
        return 0
    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return 0
        if not user_input:
            continue
        if user_input == "/exit":
            print("Goodbye.")
            return 0
        if user_input == "/help":
            print(HELP)
            continue
        if user_input == "/tools":
            print(agent.registry.describe())
            continue
        if user_input == "/memory":
            print(agent.memory.render_for_prompt())
            continue
        if user_input == "/history":
            print(agent.history.render() or "No conversation yet.")
            continue
        if user_input == "/drafts":
            print(agent.registry.call("list_drafts"))
            continue
        if user_input == "/tasks":
            print(agent.registry.call("list_tasks"))
            continue
        print(agent.chat(user_input))
    return 0


if __name__ == "__main__":
    sys.exit(main())
