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

> Repurposed, 2026-11-05 (no-envoy decision + main-agent swap): in the demo this server now runs
> as `tn mcp --as om`, acting as `om-hermes` — Hermes is **Om's** main agent now, not Rahul's.
> The server itself stays generic over `--as <person>`; only the demo wiring changes. It also
> gains two tools (`dm_read`, `dm_post`) because, with no envoy in between, the main agent using
> this server is the one carrying the plain-language DM-room conversation itself.

## Tasks
- [ ] `uv run tn mcp --as om` starts a FastMCP stdio server acting in Switch as `om-hermes` (key from `OM_HERMES_KEY`).
- [ ] Tools (typed parameters, short docstrings the LLM will read):
  - `inbox()`; `answer(id, text)`;
  - `dm(friend, goal)`; `dm_read(room)`; `dm_post(room, text)`; `ask(friend, fields)`; `gift_ideas(friend, occasion, date, budget)`; `claim(friend, item)`; `ask_around(question)`;
  - `cal_add(start, duration, title, place, id)`; `fact_set(key, level)` (**tighten-only**).
  `dm_read`/`dm_post` only read/post in DM rooms the caller is already a member of — no raw room access. `gift_ideas`, `claim` and `ask_around` can return "not available yet" until phases 19–20 land.
- [ ] No other tools: no file access, no raw `post_message` outside a DM room the caller already belongs to.
- [ ] Tests: start the server in-process with an MCP client, list tools (exactly eleven), call `inbox` and `answer` against `FakeSwitch`, `dm_read`/`dm_post` scoped to rooms the caller is a member of, `fact_set` loosening refused.

## Done when
- [ ] `make check` passes.
- [ ] An MCP client (test or `npx @modelcontextprotocol/inspector uv run tn mcp --as om`) lists exactly the eleven tools.
- [ ] Scene 1's Om steps (`inbox`, `dm`, `dm_read`/`dm_post` into the DM room, `answer P1 yes`) succeed through MCP tool calls against the live server, with the confirmation showing "via Hermes".

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
