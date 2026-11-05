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
An MCP server (stdio, FastMCP) that lets any personal agent (Hermes first) take part, using nine purpose-built tools and nothing else. It wraps the phase 15 personal-agent core, so it behaves exactly like `tn --as <person> …`.

## Tasks
- [ ] `uv run tn mcp --as rahul` starts a FastMCP stdio server acting in Switch as `rahul-hermes` (key from `RAHUL_HERMES_KEY`).
- [ ] Tools (typed parameters, short docstrings the LLM will read):
  - `inbox()`; `answer(id, text)`;
  - `dm(friend, goal)`; `ask(friend, fields)`; `gift_ideas(friend, occasion, date, budget)`; `claim(friend, item)`; `ask_around(question)`;
  - `cal_add(start, duration, title, place, id)`; `fact_set(key, level)` (**tighten-only**).
  `gift_ideas`, `claim` and `ask_around` can return "not available yet" until phases 19–20 land.
- [ ] No other tools: no file access, no raw `post_message`.
- [ ] Tests: start the server in-process with an MCP client, list tools (exactly nine), call `inbox` and `answer` against `FakeSwitch`, `fact_set` loosening refused.

## Done when
- [ ] `make check` passes.
- [ ] An MCP client (test or `npx @modelcontextprotocol/inspector uv run tn mcp --as rahul`) lists exactly the nine tools.
- [ ] Scene 1's Rahul steps (`inbox`, `answer Q1`, `answer P1 yes`) succeed through MCP tool calls against the live server, with the confirmation showing "via Hermes".

## Commit
`phase 17: tn mcp server for personal agents`

## Log
<!-- evidence, deviations, notes -->
