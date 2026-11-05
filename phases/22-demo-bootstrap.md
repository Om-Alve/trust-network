---
id: "22"
title: Demo bootstrap and one-machine layout
status: done
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
- [x] `scripts/demo_up.py`:
  - reads keys from `.env`; registers `om-gate`, `rahul-gate`, `priya-gate`, `om-hermes` and `rahul-hermes` (both Hermes profiles, decided 2026-11-05 — no more managed `rahul-agent`);
  - copies `examples/*` into `TN_DATA_DIR` (never mutating fixtures);
  - sets each gate's addressing (check 9);
  - starts the gates (or prints the commands to start them in separate terminals);
  - prints remaining phase 18 setup for two Hermes Discord profiles; optional managed agents/controllers are left alone;
- [x] `scripts/demo_reset.py`: archives `dm-*` / `gift-*` rooms, clears ledgers, claims, inbox cursors and added calendar events in `TN_DATA_DIR`, so each scene can be re-recorded from scratch.
- [x] One-machine layout: run all three gates and both Hermes CLI stand-ins locally against `http://127.0.0.1:53330`, with local identity export and no controller.
- [x] `--dry-run` for both scripts (prints what it would do).

## Done when
- [x] `make check` passes.
- [x] From a fresh `TN_DATA_DIR`, `demo_up.py` → Scene 1 (CLI version) passes → `demo_reset.py` → Scene 1 passes again.
- [x] One-machine layout tested on the laptop using localhost while existing Tailscale Serve mappings remain running; result in *Log*.

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

### Phase 22 implementation and acceptance, 2026-11-05

- Bootstrap: `uv run python -m scripts.demo_up --one-machine --data-dir data/phase22-profiles`.
  Existing gate and Hermes credentials reused, missing profiles copied, addressing
  configured through owner Gateway API and local identity map exported.
- Repeatable acceptance: `PYTHONPATH=. uv run python tests/e2e_demo_bootstrap.py`.
  Fresh `TN_DATA_DIR` bootstrapped, all three gates local against port 53330,
  Scene 1 passed, reset cleared state and restored calendars, Scene 1 passed again.
  Artifacts: `data/phase22-1793888117728441000/scene1-take1.json` and
  `data/phase22-1793888117728441000/scene1-take2.json`.
  Log: `data/phase22-e2e.log`. Wrapper adapts the existing Scene 1 script's
  fixed output directory and dotenv loading to test the actual bootstrapped root.
  Committed fixture hashes and retained gate credentials stayed unchanged.
  An earlier wrapper run passed both scenes but included an unrelated untracked
  inbox cursor in its fixture hash check; the final run checks committed fixtures.
- Scene 3 after reset: `uv run python -m scripts.e2e_scene3` passed the offline
  three-gate human-answer flow. Artifact:
  `data/scene3-offline-1793888104678676000/artifact.json`.
- Both dry runs succeeded; bootstrap dry run created no profile directory.
- VM reset succeeded over SSH using the deployed `data/profiles/rahul` path.
  Log: `data/phase22-reset-vm.log`. The VM service was stopped for local testing
  and reset, then restarted. Final `systemctl --user is-active rahul-gate.service`
  returned `active`. No local gate processes remain.
- `make check`: ruff format and lint passed; **460 passed**, 3.10s.
  Evidence: `data/phase22-check.log`.

Deviations: the superseded second-controller requirement is replaced with three
local gates and two Hermes CLI stand-ins. Tailscale Serve was left running and
its mappings were never changed; localhost selected the one-machine transport.
No envoys or optional managed agents were modified. The publisher and gate
startup commands are printed rather than spawning persistent processes.
