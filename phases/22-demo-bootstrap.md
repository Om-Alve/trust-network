---
id: "22"
title: Demo bootstrap and one-machine layout
status: todo
priority: P0
owner: agent
depends_on: ["15"]
plan_refs: ["§5 scripts/demo_up.py", "§2 'Judges can run everything on one machine'", "§11 Judges must reproduce it"]
target: Nov 7 morning
---

# 22 · Demo bootstrap and one-machine layout

## Goal
One script brings the demo up from keys, another resets it between takes, and a judge can run everything on one machine without a VM or Tailscale.

## Tasks
- [ ] `scripts/demo_up.py`:
  - reads keys from `.env`; registers `om-gate`, `rahul-gate`, `priya-gate`, `rahul-hermes`;
  - copies `examples/*` into `TN_DATA_DIR` (never mutating fixtures) and fills `envoy.machine` from `list_machines`;
  - sets each gate's addressing (check 9);
  - starts the gates (or prints the commands to start them in separate terminals);
  - prints the remaining manual clicks: turn on "can manage agents" for each gate, enroll the VM or start the second controller, run the home template.
- [ ] `scripts/demo_reset.py`: archives `dm-*` / `gift-*` rooms, clears ledgers, claims, inbox cursors and added calendar events in `TN_DATA_DIR`, so each scene can be re-recorded from scratch.
- [ ] One-machine layout: document and script a second `switch-agent-controller` with its own `--data-dir` against `http://localhost:<switch-core port>` acting as Rahul's machine.
- [ ] `--dry-run` for both scripts (prints what it would do).

## Done when
- [ ] `make check` passes.
- [ ] From a fresh `TN_DATA_DIR`, `demo_up.py` → Scene 1 (CLI version) passes → `demo_reset.py` → Scene 1 passes again.
- [ ] One-machine layout tested on the laptop with Tailscale Serve off; result in *Log*.

## Commit
`phase 22: demo_up/demo_reset and one-machine layout`

## Log
<!-- evidence, deviations, notes -->
