---
id: "17"
title: tn mcp server
status: todo
priority: P0
owner: agent
depends_on: ["15"]
plan_refs: ["§5 `tn mcp`", "§6 Hermes row", "§3 Rule 3"]
target: Nov 6 night
---

# 17 · `tn mcp` server

## Goal
An MCP server (stdio, FastMCP) that lets any personal agent (Hermes first) take part, using eleven purpose-built tools and nothing else. It wraps the phase 15 personal-agent core, so it behaves exactly like `tn --as <person> …`.

> Repurposed, 2026-11-05 (no-envoy decision, then both people on Hermes via Discord): in the demo
> this server now runs **twice**, once per person — `tn mcp --as om` acting as `om-hermes`, and
> `tn mcp --as rahul` acting as `rahul-hermes` — since both main agents are now Hermes, not just
> Om's. The server itself stays generic over `--as <person>`; only the demo wiring changes. It
> also gains two tools (`dm_read`, `dm_post`) because, with no envoy in between, the main agent
> using this server is the one carrying the plain-language DM-room conversation itself.

## Tasks
- [ ] `uv run tn mcp --as om` starts a FastMCP stdio server acting in Switch as `om-hermes` (key from `OM_HERMES_KEY`); `uv run tn mcp --as rahul` starts the same server acting as `rahul-hermes` (key from `RAHUL_HERMES_KEY`).
- [ ] Tools (typed parameters, short docstrings the LLM will read):
  - `inbox()`; `answer(id, text)`;
  - `dm(friend, goal)`; `dm_read(room)`; `dm_post(room, text)`; `ask(friend, fields)`; `gift_ideas(friend, occasion, date, budget)`; `claim(friend, item)`; `ask_around(question)`;
  - `cal_add(start, duration, title, place, id)`; `fact_set(key, level)` (**tighten-only**).
  `dm_read`/`dm_post` only read/post in DM rooms the caller is already a member of — no raw room access. `gift_ideas`, `claim` and `ask_around` can return "not available yet" until phases 19–20 land.
- [ ] No other tools: no file access, no raw `post_message` outside a DM room the caller already belongs to.
- [ ] Tests: start the server in-process with an MCP client, list tools (exactly eleven), call `inbox` and `answer` against `FakeSwitch`, `dm_read`/`dm_post` scoped to rooms the caller is a member of, `fact_set` loosening refused.

## Done when
- [ ] `make check` passes.
- [ ] An MCP client (test or `npx @modelcontextprotocol/inspector uv run tn mcp --as om`) lists exactly the eleven tools; the same holds with `--as rahul`.
- [ ] Scene 1's Om steps (`inbox`, `dm`, `dm_read`/`dm_post` into the DM room, `answer P1 yes`) succeed through MCP tool calls against the live server, with the confirmation showing "via Hermes"; the same steps succeed symmetrically for Rahul against `tn mcp --as rahul`, with his confirmation also showing "via Hermes".

## Commit
`phase 17: tn mcp server for personal agents`

## Log
<!-- evidence, deviations, notes -->

### No-envoy decision and main-agent swap, 2026-11-05

Added `dm_read`/`dm_post` (now eleven tools, was nine): with no envoy, the main agent behind
this server carries the DM-room conversation itself, so it needs a bounded way to read and post
in a room it already belongs to. Swapped the demo identity from `rahul-hermes` to `om-hermes`
(Hermes is now Om's main agent, per PLAN.md's Nov 5 main-agent swap); the server code itself was
never person-specific (`--as <person>`), so this is a demo-wiring change, not a design change to
the module.

### Both on Hermes, on Discord — 2026-11-05

Superseded the swap above the same day: the managed-Codex `rahul-agent` plan is dropped, and
Rahul also gets his own Hermes, on Discord. The demo now runs this server **twice**, once per
person (`--as om` as `om-hermes`, `--as rahul` as `rahul-hermes`). No code or test changes: the
server was already generic over `--as <person>`, and `dm_read`/`dm_post` already serve whichever
main agent is in the room — this identity was never hardcoded.
