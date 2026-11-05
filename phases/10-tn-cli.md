---
id: "10"
title: tn CLI (offline commands)
status: todo
priority: P0
owner: agent
depends_on: ["06", "07", "08"]
plan_refs: ["§5 `tn` CLI", "§3 Rule 3", "§4 Scene 1 step 10"]
target: Nov 6 morning
---

# 10 · `tn` CLI (offline commands)

## Goal
The local commands a person (or their main agent) runs on their own data. These need no Switch connection. Switch-connected commands (`inbox`, `answer`, `dm`, …) are added in phase 15 and reuse this CLI's structure.

## Tasks
- [ ] `trustnet/tn/cli.py` with argparse subcommands and a global `--as <person>` (selects the data dir from phase 05; defaults to `$TN_PERSON`):
  - `tn init <person>` — create a data dir with empty `trust.yaml`, `facts.yaml`, `calendar.ics`;
  - `tn trust <person> <level>` — owner edits their trust list;
  - `tn fact get [<key>…]` — the owner's own view (later hides claimed gift items, phase 19);
  - `tn fact set <key> --level <level> [--value …]` — **tighten-only** (Rule 3): loosening is refused with "edit facts.yaml by hand to loosen";
  - `tn cal add <start> <duration> "<title>" @ "<place>" [--id P1]` — via `calendar.add_event`;
  - `tn view-as <person>` — prints the phase 08 table.
- [ ] Output is plain text by default and `--json` for agents.
- [ ] Tests (call `main([...])` directly): each subcommand against a temp copy of the fixtures; tighten-only refusal; `cal add` idempotent.

## Done when
- [ ] `make check` passes.
- [ ] `uv run tn --as om view-as rahul` and `uv run tn --as om view-as priya` print different, correct tables.
- [ ] `uv run tn --as om fact set drinks --level acquaintance` is refused; `--level close` succeeds (on a temp data dir, not the committed fixtures).

## Commit
`phase 10: tn CLI for trust, facts, calendar and view-as`

## Log
<!-- evidence, deviations, notes -->
