---
id: "25"
title: P2 stretch goals
status: todo
priority: P2
owner: agent
depends_on: ["18"]
plan_refs: ["§9 Cut lines (P2)", "§6 'Stronger on the VM'"]
target: only if time is left before Nov 7 afternoon, or after submission
---

# 25 · P2 stretch goals

Each item is its own commit (`phase 25: <item>`) and can be marked done on its own. The phase is `done` when every item is either done or explicitly dropped in *Log*. Never start these before phases 01–24's P0 items are done.

## Items
- [ ] **`--separate-users` on the VM** — `install-service --separate-users` so each envoy runs as its own Linux user: can't read home directories or gate files, can't reach the cloud metadata address. *Done when:* from inside `rahul-envoy-om`'s user, reading `/home/*/` and `curl 169.254.169.254` both fail; noted in README safety section.
- [ ] **Envoy template** — create envoys with `run_template` (managed agents since 0.31) instead of `create_agent`. *Done when:* phase 13 tests pass using the template path.
- [ ] **Counter-proposals** — `counter P1 P2 …` handling end to end (parser already exists from phase 09). *Done when:* a counter replaces the pending proposal on both sides and needs two fresh yeses; tests cover it.
- [ ] **Priya's own main agent (OpenCode)** — Priya joins through `tn mcp` from OpenCode. *Done when:* Priya answers Scene 3's question from OpenCode.
- [ ] **OpenClaw and Grok Bot recipes** — `docs/recipes/*.md` with the MCP config for each. *Done when:* each recipe was tried, or is marked untested.
- [ ] **Mattermost instructions** — README section for the bundled Mattermost fallback. *Done when:* `#om-home` equivalent works on Mattermost following the instructions.

## Log
<!-- evidence, deviations, notes -->
