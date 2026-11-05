---
id: "04"
title: Day-0 protocol checks 4–10
status: todo
priority: P0
owner: agent + human
depends_on: ["02", "03"]
plan_refs: ["§8 checks 4–10", "§0 Envoys", "§11 Risks"]
target: Nov 5 night
---

# 04 · Day-0 protocol checks 4–10

## Goal
Prove (or disprove) the managed-agent design before building on it. Each result picks a branch: managed envoys (phase 13) or the fallback runner (phase 13b); agent-only rooms or workspace-readable rooms; addressing set by gates or by hand.

## Tasks
- [ ] `scripts/day0_probe.py` with one subcommand per check, using `SwitchClient`. Each prints PASS/FAIL and the raw response, so results are reproducible.
- [ ] **[human]** Turn on "can manage agents" for `om-gate` and `rahul-gate` in Gateway.
- [ ] Check 4: `rahul-gate` calls `create_agent(machine=<VM>, provider="codex", instructions=…)`; the envoy answers in an agent-only room; `update_agent_detail` changes its instructions and the next reply reflects the change. Same for `om-gate` + Claude Code on the laptop.
- [ ] Check 5: `rahul-envoy-om` can address `om-envoy-rahul` once addressing names it; `get_agent_detail` from `rahul-gate` on `om-envoy-rahul` does **not** expose its instructions; a new DM room starts a fresh session (envoy doesn't remember the previous room).
- [ ] Check 6: Claude Code envoy with file and shell tools disallowed still replies; Codex with `auto_mode` off doesn't act without asking.
- [ ] Check 7: `create_room(internal_only=True)` from `om-gate` including `rahul-gate`, or create then `invite_agent_to_room`.
- [ ] Check 8 (second half): `list_participants` and `get_agent_detail` give each agent's owner.
- [ ] Check 9: a gate's addressing set to `anyone` via `update_agent_detail`.
- [ ] Check 10: **[human]** Om can open an agent-only DM room in Console, but can't open a private gift room created by `rahul-gate`.
- [ ] Record every result in `docs/day0.md` and update the `FakeSwitch` from phase 03 if the real server behaves differently (the fake must match reality).

## Done when
- [ ] Checks 4–10 each have a result, evidence and *Decision taken* in `docs/day0.md`.
- [ ] The envoy branch is decided: if checks 4–6 pass, set phase 13b `status: skipped`; if any fails, set phase 13 `status: skipped` (or narrow its scope) and keep 13b `todo`. Write the reason in both files' *Log*.
- [ ] Room strategy decided (check 7): agent-only rooms, or workspace-readable rooms + `connect_to_room` with gifts on the courtesy seal only. Recorded in `docs/day0.md` and in phase 14's *Log*.
- [ ] Any `# UNVERIFIED` markers left from phase 03 are resolved.
- [ ] Probe agents and rooms created during checks are archived/deleted, so the demo workspace starts clean.

## Commit
`phase 04: day-0 protocol probes and recorded decisions`

## Log
<!-- evidence, deviations, notes -->
