# Muse Top — Roadmap

One item per day, in order. Small, focused, working. Mark each done with its date.

## Milestone 1 — Core (done: skeleton)
- [x] 2026-11-21 — Day 1: skeleton — CLI, config, agent loop, tool registry, JSON memory, Gemini client with labelled mock fallback, tests.
- [x] 2026-11-21 — Day 2: `web_fetch` tool — fetch a URL, return title + text (stdlib urllib, timeout + size cap).
- [x] 2026-11-22 — Day 3: `read_file` / `write_file` tools — sandboxed to a workspace folder.
- [x] 2026-11-23 — Day 4: conversation history in memory — last N turns saved, loaded on start.
- [x] 2026-11-24 — Day 5: `draft_email` draft tool — builds an email draft (to/subject/body, cc/bcc), validates addresses, saves JSON to `~/.muse-top/drafts/`; never sends (no SMTP code at all) — sending needs a human. Also `list_drafts` tool + `/drafts` CLI command. Bonus fix: `Config.from_env()` `Path("")`-is-truthy bug — unset env vars silently pointed data/workspace/drafts at the current directory instead of `~/.muse-top`.
- [x] 2026-11-25 — Day 6: scheduler — `schedule` tool + a `muse-top run --once` mode that executes due tasks.
- [x] 2026-11-26 — Day 7: lead tools — `score_leads` tool scores a leads CSV in the workspace 0-100 (grades A-D, TCPA consent flag; no-consent leads are DO-NOT-CONTACT and excluded from the ranked list), reusing the NZ AI Lead Scorer rule logic, with a labelled mock outreach angle per top lead.

## Milestone 2 — Real assistant jobs
- [x] 2026-11-27 — Day 8: SEO tools — `audit_seo` tool audits a URL's on-page SEO (title, meta, H1, headings, alt, canonical, OG/Twitter, JSON-LD, content, links, readability, keyword) into a 0-100 score + grade A-F with rule-based fixes, reusing the NZ AI SEO Auditor logic.
- [ ] Outreach tools: draft a personalised outreach email from a prospect row.
- [ ] Social tools: draft a LinkedIn/X/Facebook post from a topic.
- [ ] Daily briefing: one command that summarises memory + due tasks + today's schedule.

## Milestone 3 — Hardening
- [ ] Approval gate: tools marked "needs approval" ask before running.
- [ ] Logging: every tool call logged to `~/.muse-top/calls.log`.
- [ ] Config file support (`~/.muse-top/config.json`) alongside env vars.
- [ ] Packaging: `pip install -e .` via pyproject.toml.
