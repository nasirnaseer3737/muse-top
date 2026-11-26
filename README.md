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

Day 3 (2026-11-22): `read_file` / `write_file` tools — read and write
text files sandboxed to the agent workspace (`~/.muse-top/workspace`,
tune with `MUSE_TOP_WORKSPACE`); absolute paths, `..` escapes and
symlinks pointing outside are refused, 64 KB read cap.

Day 4 (2026-11-23): conversation history — the last 10 turns are saved
to `~/.muse-top/history.json` (tune with `MUSE_TOP_MAX_HISTORY`) and
loaded on start, so the agent remembers the conversation across
restarts; `/history` shows the recent conversation.

Day 5 (2026-11-24): email drafts — `draft_email` builds an email draft
(to/subject/body, optional cc/bcc), validates every address, and saves
it as JSON in `~/.muse-top/drafts/` (tune with `MUSE_TOP_DRAFTS_DIR`);
`list_drafts` lists saved drafts, newest first, and `/drafts` shows
them in the chat. Drafts are never sent — there is no SMTP code at
all; sending needs a human. Also fixed: `Config.from_env()` used to
point data/workspace/drafts at the current directory when the env vars
were unset (`Path("")` is truthy); now they correctly fall back to
`~/.muse-top`.

Day 6 (2026-11-25): scheduler — `schedule` schedules a task (a message
for the agent) for later (`tomorrow 14:00`, `in 30 minutes`,
`2026-11-26 14:00`); tasks live in `~/.muse-top/schedule.json` (tune
with `MUSE_TOP_SCHEDULE_PATH`); `list_tasks` lists pending tasks
(soonest first), `cancel_task` cancels one by id, and `/tasks` shows
them in the chat. `python -m muse_top run --once` runs every task whose
time has come, feeds each to the agent as a chat message, and marks it
done so it never runs twice.

Day 7 (2026-11-26): lead scoring — `score_leads` scores a leads CSV in
the workspace 0–100 with grades A–D (email quality, phone, website,
company size, industry fit, source, budget, TCPA consent), reusing the
NZ AI Lead Scorer rule logic; leads without consent are scored but
flagged DO-NOT-CONTACT and excluded from the ranked outreach list.
Each top lead gets a one-line outreach angle, clearly labelled mock
(not model output). At most 500 rows are scored per call (tune with
`MUSE_TOP_LEAD_MAX_ROWS`); the CSV is read through the same workspace
sandbox as `read_file`.

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
- **History** (`muse_top/history.py`): the last 10 turns saved as JSON in
  `~/.muse-top/history.json` (tune with `MUSE_TOP_MAX_HISTORY`), loaded
  on start and included in every prompt; corrupt files start empty.
- **Tools** (`muse_top/tools.py`): a registry. Each tool has a name,
  description and a Python function. New tools are one `@registry.tool(...)`
  away — see the built-ins (`get_current_time`, `remember_fact`, `recall_fact`).
- **Web fetch** (`muse_top/web.py`): `web_fetch` downloads a page and
  returns its title + readable text — http(s) only, 15s timeout, 512 KB
  cap (tune with `MUSE_TOP_WEB_TIMEOUT` / `MUSE_TOP_WEB_MAX_BYTES`).
- **File tools** (`muse_top/files.py`): `read_file` / `write_file` work
  only inside the workspace folder (`~/.muse-top/workspace`, tune with
  `MUSE_TOP_WORKSPACE`); absolute paths, `..` escapes and symlinks
  pointing outside are refused, reads cap at 64 KB
  (`MUSE_TOP_FILE_MAX_BYTES`).
- **Email drafts** (`muse_top/email_draft.py`): `draft_email` builds a
  draft (to/subject/body, optional cc/bcc), validates every address,
  and saves it as JSON in `~/.muse-top/drafts/` (tune with
  `MUSE_TOP_DRAFTS_DIR`); `list_drafts` lists them newest first.
  Drafts are never sent — there is no SMTP code anywhere; sending
  needs a human's approval.
- **Scheduler** (`muse_top/schedule.py`): `schedule` schedules a task
  (a message for the agent) for later — `tomorrow 14:00`,
  `in 30 minutes`, `2026-11-26 14:00` — stored in
  `~/.muse-top/schedule.json` (tune with `MUSE_TOP_SCHEDULE_PATH`);
  `list_tasks` lists pending tasks soonest first, `cancel_task`
  cancels one by id. `python -m muse_top run --once` executes every
  due task (each runs as a chat message) and marks it done so it never
  runs twice; a corrupt schedule file starts empty.
- **Lead scoring** (`muse_top/leads.py`): `score_leads` scores a leads
  CSV in the workspace 0–100 with grades A–D — email quality, phone,
  website, company size, industry fit, source, budget, TCPA consent —
  reusing the NZ AI Lead Scorer rule logic; leads without consent are
  scored but flagged DO-NOT-CONTACT and excluded from the ranked list.
  Each top lead gets a one-line outreach angle, clearly labelled mock.
  At most 500 rows per call (tune with `MUSE_TOP_LEAD_MAX_ROWS`); the
  CSV is read through the same workspace sandbox as `read_file`.
- **Config** (`muse_top/config.py`): everything from environment variables.
  Never put an API key in code.

## Commands (inside the chat)

| Command   | What it does              |
|-----------|---------------------------|
| `/help`   | show commands             |
| `/tools`  | list registered tools     |
| `/memory` | list remembered facts     |
| `/history`| show recent conversation  |
| `/drafts` | list saved email drafts   |
| `/tasks`  | list scheduled tasks      |
| `/exit`   | quit                      |

## Tests

```bash
python -m unittest discover -s tests -v
```

## Roadmap

See [ROADMAP.md](ROADMAP.md) — one item per day, in order.
