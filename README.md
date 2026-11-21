# Muse Top

A modular AI agent system, built piece by piece — one small step every day.
Think of it as a personal assistant agent: it talks to an LLM (Google Gemini),
remembers facts, and calls tools to get things done.

> Built by Nasir Naseer. Python 3.10+ standard library only — no pip installs.

## Status

Day 1 (2026-11-21): skeleton — CLI, config, agent loop, tool registry,
JSON memory, Gemini client with labelled mock fallback. See [ROADMAP.md](ROADMAP.md)
for what comes next, one piece at a time.

Day 2 (2026-11-21): `web_fetch` tool — fetch a URL, return its title +
readable text (stdlib urllib, 15s timeout, 512 KB cap, http(s) only).

## Quick start

```bash
# 1. Get a free Gemini API key: https://aistudio.google.com/apikey
export NZ_GEMINI_API_KEY="your-key-here"

# 2. Run the agent
python -m muse_top
```

Without a key the agent still runs in clearly labelled **mock mode** — it
answers from local rules and tools, and every mock reply says so.

## How it works

```
you ──▶ CLI (muse_top/cli.py) ──▶ Agent (muse_top/agent.py)
                                          │  builds a prompt from memory + tools
                                          ▼
                                   LLM (muse_top/llm.py) ── Gemini API
                                          │  may answer: CALL tool_name {"arg": ...}
                                          ▼
                                   Tool registry (muse_top/tools.py)
                                          │  executes the tool, result goes back
                                          ▼
                                   final answer to you
```

- **Memory** (`muse_top/memory.py`): facts saved as JSON in `~/.muse-top/memory.json`.
  The agent can remember things (`remember_fact`) and recall them later.
- **Tools** (`muse_top/tools.py`): a registry. Each tool has a name,
  description and a Python function. New tools are one `@registry.tool(...)`
  away — see the built-ins (`get_current_time`, `remember_fact`, `recall_fact`).
- **Web fetch** (`muse_top/web.py`): `web_fetch` downloads a page and
  returns its title + readable text — http(s) only, 15s timeout, 512 KB
  cap (tune with `MUSE_TOP_WEB_TIMEOUT` / `MUSE_TOP_WEB_MAX_BYTES`).
- **Config** (`muse_top/config.py`): everything from environment variables.
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
