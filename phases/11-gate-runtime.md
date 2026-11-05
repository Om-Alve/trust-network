---
id: "11"
title: "Gate runtime: free / ask live"
status: todo
priority: P0
owner: agent + human
depends_on: ["03", "04", "07", "08", "09"]
plan_refs: ["§0 gate", "§2 Rooms (#om-home)", "§3 Rules 1, 2, 6", "§5 templates/home.template.yaml, SKILL.md", "§8 check 12", "§9 Nov 6 morning milestone"]
target: Nov 6 morning
---

# 11 · Gate runtime: `free` / `ask` live

## Goal
A running gate process per person (`python -m trustnet.gate`) that listens on Switch, works out each room's level from server-side membership, and answers `free`, `ask`, `view-as`, `ledger` and `trust`. Om's Discord home channel exists from a template.

## Tasks
- [ ] `trustnet/gate/__main__.py`: `--person om` (data dir from phase 05), key from `--key-env OM_GATE_KEY`, server from `SWITCH_URL`. Logs to stderr; one line per command handled (command, room, level, decision).
- [ ] Event loop: for each `addressed` message → identify sender via Switch (never message text) → `room_level` from `list_participants` + `get_agent_detail` (cached per room, refreshed on membership-change events and every N minutes) → `authorize` → handler → reply → ledger entry.
- [ ] Silence rule: if `room_level` is `None`, the gate posts nothing at all (a log line only).
- [ ] Handlers: `free` (calendar view at level), `ask` (values or "not shared at this level"), owner-only `view-as`, `ledger`, `trust`. Unknown commands → command list (overreach note comes in phase 21).
- [ ] `trustnet/gate/relay.py`: `post_home(person, text)`, which finds the person's home room (`#om-home` for Om; `rahul-home` / `priya-home` agent-only rooms for others, created on first use).
- [ ] `templates/home.template.yaml`: private Discord channel `om-home`; an OpenCode agent `om-agent` (`provider: "{provider}"` = `opencode`, `model: "opencode-go/deepseek-v4.1-flash"`, `allow_existing`, addressing `owner`); `om-gate`; `SKILL.md` as a room doc.
- [ ] Stub `skills/trust-network/SKILL.md` with the command list and examples (replaced by the dictated version in phase 18).
- [ ] Offline tests with `FakeSwitch`: gate answers Rahul-level in a room with `rahul-gate`, friend-level with `priya-gate`, stays silent with a stranger, refuses `trust` from Om's agent, answers `self` level in the home room.
- [ ] **[human]** Run the template; confirm `#om-home` is a private Discord channel with Om, `om-agent`, `om-gate` (finishes check 12 in `docs/day0.md`).

## Done when
- [ ] `make check` passes, including the FakeSwitch gate tests above.
- [ ] Live: in `#om-home`, Om asks `@om-agent ask my gate what I'm doing Sunday`, the agent sends `@om-gate free 2026-11-08..2026-11-09`, and the gate replies with Om's own calendar. Evidence (screenshot or copied text) in *Log*.
- [ ] Live: in a probe room with `om-gate` + `rahul-gate`, `@om-gate ask diet wishlist address` returns diet + wishlist (Rahul is close) and "not shared" for address; with `priya-gate`, wishlist is "not shared". Ledger shows exactly the disclosed fields.
- [ ] Check 12 recorded as passed (or Mattermost fallback recorded).

## Commit
`phase 11: gate runtime with free/ask, home template, SKILL stub`

## Log
<!-- evidence, deviations, notes -->
