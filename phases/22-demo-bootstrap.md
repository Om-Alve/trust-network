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
  - reads keys from `.env`; registers `om-gate`, `rahul-gate`, `priya-gate`, `om-hermes` and `rahul-hermes` (both Hermes profiles, decided 2026-11-05 — no more managed `rahul-agent`);
  - copies `examples/*` into `TN_DATA_DIR` (never mutating fixtures);
  - sets each gate's addressing (check 9);
  - starts the gates (or prints the commands to start them in separate terminals);
  - prints the remaining manual clicks: enroll the VM if used (optional — no managed agent needs it now), run the home template for Om's optional `om-agent`. "Can manage agents" is no longer required just to run gates, now that gates don't create envoys, and no managed main agent exists on either side — it's only needed if Om's optional `om-agent` is placed.
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

### No-envoy decision and main-agent swap, 2026-11-05

Dropped the `envoy.machine` fill-in (no envoys to place at runtime). Swapped the registered
Hermes identity from `rahul-hermes` to `om-hermes`. Added `rahul-agent` (managed Codex) to the
remaining-manual-clicks list, since it now needs the same kind of managed-agent placement
`om-agent` used to need exclusively.

### Both on Hermes, on Discord — 2026-11-05

Superseded the above the same day: `rahul-agent` is dropped, so it's removed from the
remaining-manual-clicks list rather than added to it. `demo_up.py` now registers **both**
`om-hermes` and `rahul-hermes`. The VM enrollment click becomes fully optional (no managed agent
needs it); the only managed-agent click left is Om's optional `om-agent`.
