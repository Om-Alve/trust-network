---
id: "04"
title: Day-0 protocol checks 4–10
status: done
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
- [x] `scripts/day0_probe.py` with one subcommand per check, using `SwitchClient`. Each prints PASS/FAIL and the raw response, so results are reproducible.
- [x] **[human]** Turn on "can manage agents" for `om-gate` and `rahul-gate` in Gateway.
- [x] Check 4: `rahul-gate` calls `create_agent(machine=<VM>, provider="codex", instructions=…)`; the envoy answers in an agent-only room; `update_agent_detail` changes its instructions and the next reply reflects the change. Same for `om-gate` + OpenCode (`model="opencode-go/deepseek-v4.1-flash"`) on the laptop.
- [x] Check 5: `rahul-envoy-om` can address `om-envoy-rahul` once addressing names it; `get_agent_detail` from `rahul-gate` on `om-envoy-rahul` does **not** expose its instructions; a new DM room starts a fresh session (envoy doesn't remember the previous room).
- [x] Check 6: OpenCode envoy (`opencode-go/deepseek-v4.1-flash`) with file and shell tools (Bash, Edit, Write) disallowed still replies; Codex with `auto_mode` off doesn't act without asking.
- [x] Check 7: `create_room(internal_only=True)` from `om-gate` including `rahul-gate`, or create then `invite_agent_to_room`.
- [x] Check 8 (second half): `list_participants` and `get_agent_detail` give each agent's owner.
- [x] Check 9: a gate's addressing set to `anyone` via `update_agent_detail`.
- [x] Check 10: **[human]** Om can open an agent-only DM room in Console, but can't open a private gift room created by `rahul-gate`.
- [x] Record every result in `docs/day0.md` and update the `FakeSwitch` from phase 03 if the real server behaves differently (the fake must match reality).

## Done when
- [x] Checks 4–10 each have a result, evidence and *Decision taken* in `docs/day0.md`.
- [x] The envoy branch is decided: if checks 4–6 pass, set phase 13b `status: skipped`; if any fails, set phase 13 `status: skipped` (or narrow its scope) and keep 13b `todo`. Write the reason in both files' *Log*.
- [x] Room strategy decided (check 7): agent-only rooms, or workspace-readable rooms + `connect_to_room` with gifts on the courtesy seal only. Recorded in `docs/day0.md` and in phase 14's *Log*.
- [x] Any `# UNVERIFIED` markers left from phase 03 are resolved.
- [x] Probe agents and rooms created during checks are archived/deleted, so the demo workspace starts clean.

## Commit
`phase 04: day-0 protocol probes and recorded decisions`

## Log
<!-- evidence, deviations, notes -->

### Live run, 2026-11-05

Checks were attempted against native core 0.31.0; failures are design findings,
not uncompleted human steps. Detailed Result / Date / Evidence / Decision taken
are in docs/day0.md and redacted raw responses in docs/day0-evidence/.

- 4 fail: managed creation works, OpenCode reply and instruction refresh not proved.
- 5 partial: cross-owner instructions hidden and peer message delivered; fresh
  session isolation not proved within the short probe.
- 6 fail: unsupported OpenCode disallowedTools rejected with explicit 400.
- 7 pass: cross-owner internal invitation works.
- 8 partial: ownership works, events have null kind and transport mxids.
- 9 self-update fails with 403; owner Gateway policy null succeeds for both gates.
- 10 fails gift privacy: Om/admin reads both rooms with HTTP 200.

Decision: 13 skipped, 13b todo. Internal rooms with explicit invitations; gifts
use courtesy seal. PLAN sections 8 and 11 and phase 14 Log updated.

Cleanup: all day0 agents and rooms deleted via Gateway, HTTP 200. Reuse om-gate
and rahul-gate in phase 11, already permitted to manage agents and openly
addressable. Their credentials are mode 0600 in gitignored data/day0-state.json;
registration keys remain in .env. No clicks or other Om actions remain.

Fake now models creator membership, Console visibility of internal rooms, admin
read bypass, and archive as metadata. It still simplifies addressing and provider
execution; live frames remain the authority for transport identity.

Deviations: bounded probes deliberately do not claim unobserved fresh-session
or Codex approval guarantees. Choose fallback on the observed tool-setting failure.
`make check`: 59 files already formatted; All checks passed; 71 tests passed.
