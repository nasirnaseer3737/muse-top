# NZ Agent

A modular AI agent system, built piece by piece — one small step every day.
Think of it as a personal assistant agent: it talks to an LLM (Google Gemini),
remembers facts, and calls tools to get things done.

> Built by Nasir Naseer. Python 3.10+ standard library only — no pip installs.

## Status

Day 1 (2026-11-21): skeleton — CLI, config, agent loop, tool registry,
JSON memory, Gemini client with labelled mock fallback. See [ROADMAP.md](ROADMAP.md)
for what comes next, one piece at a time.

## Quick start

```bash
# 1. Get a free Gemini API key: https://aistudio.google.com/apikey
export NZ_GEMINI_API_KEY="your-key-here"

# 2. Run the agent
python -m nz_agent
```

Without a key the agent still runs in clearly labelled **mock mode** — it
answers from local rules and tools, and every mock reply says so.

## How it works

```
you ──▶ CLI (nz_agent/cli.py) ──▶ Agent (nz_agent/agent.py)
                                          │  builds a prompt from memory + tools
                                          ▼
                                   LLM (nz_agent/llm.py) ── Gemini API
                                          │  may answer: CALL tool_name {"arg": ...}
                                          ▼
                                   Tool registry (nz_agent/tools.py)
                                          │  executes the tool, result goes back
                                          ▼
                                   final answer to you
```

- **Memory** (`nz_agent/memory.py`): facts saved as JSON in `~/.nz-agent/memory.json`.
  The agent can remember things (`remember_fact`) and recall them later.
- **Tools** (`nz_agent/tools.py`): a registry. Each tool has a name,
  description and a Python function. New tools are one `@registry.tool(...)`
  away — see the built-ins (`get_current_time`, `remember_fact`, `recall_fact`).
- **Config** (`nz_agent/config.py`): everything from environment variables.
  Never put an API key in code.

## Commands (inside the chat)

| Command   | What it does              |
|-----------|---------------------------|
| `/help`   | show commands             |
| `/tools`  | list registered tools     |
| `/memory` | list remembered facts     |
| `/exit`   | quit                      |

## Tests

```bash
python -m unittest discover -s tests -v
```

## Roadmap

See [ROADMAP.md](ROADMAP.md) — one item per day, in order.
