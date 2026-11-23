# Muse Top — Roadmap

One item per day, in order. Small, focused, working. Mark each done with its date.

## Milestone 1 — Core (done: skeleton)
- [x] 2026-11-21 — Day 1: skeleton — CLI, config, agent loop, tool registry, JSON memory, Gemini client with labelled mock fallback, tests.
- [x] 2026-11-21 — Day 2: `web_fetch` tool — fetch a URL, return title + text (stdlib urllib, timeout + size cap).
- [x] 2026-11-22 — Day 3: `read_file` / `write_file` tools — sandboxed to a workspace folder.
- [x] 2026-11-23 — Day 4: conversation history in memory — last N turns saved, loaded on start.
- [ ] Day 5: `send_email` draft tool — builds a draft email (no sending without approval).
- [ ] Day 6: scheduler — `schedule` tool + a `muse-top run --once` mode that executes due tasks.

## Milestone 2 — Real assistant jobs
- [ ] Lead tools: score a lead CSV (reuse the NZ AI Lead Scorer logic as a tool).
- [ ] SEO tools: audit a URL's on-page SEO (reuse the NZ AI SEO Auditor logic).
- [ ] Outreach tools: draft a personalised outreach email from a prospect row.
- [ ] Social tools: draft a LinkedIn/X/Facebook post from a topic.
- [ ] Daily briefing: one command that summarises memory + due tasks + today's schedule.

## Milestone 3 — Hardening
- [ ] Approval gate: tools marked "needs approval" ask before running.
- [ ] Logging: every tool call logged to `~/.muse-top/calls.log`.
- [ ] Config file support (`~/.muse-top/config.json`) alongside env vars.
- [ ] Packaging: `pip install -e .` via pyproject.toml.
