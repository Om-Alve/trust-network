---
id: "09"
title: Command parser
status: todo
priority: P0
owner: agent
depends_on: ["05"]
plan_refs: ["§3 Rule 4 (fixed forms)", "§3 Commands any agent can send", "§3 Owner-only commands", "§11 LLMs format commands badly"]
target: Nov 6 morning
---

# 09 · Command parser

## Goal
`trustnet/gate/commands.py` turns message text into typed commands, enforces the fixed forms at the boundary, and is forgiving about how LLMs write dates, while being strict about everything else.

## Tasks
- [ ] Typed command objects for every command in PLAN.md §3:
  - cross-boundary: `free`, `ask`, `ask-owner`, `propose`, `counter`, `gift-ideas`, `claim`, `ask-around`;
  - owner-only: `dm`, `ask-around` (outbound), `yes`, `no`, `answer`, `trust`, `view-as`, `ledger`;
  - gate-to-gate (needed by phase 14, not named in the plan): `join-dm <room> "<goal>"`, and consent/status relays (`consent P1 yes|no via-agent|direct`). Document them in *Log* and later in `SKILL.md`.
- [ ] Parsing rules:
  - strip the leading `@<gate-name>`, tolerate extra whitespace, smart quotes, trailing punctuation, code fences;
  - dates via `dateparser` with `Asia/Kolkata`, `PREFER_DATES_FROM: future`; ranges `A..B`, `A to B`, `Nov 14-16`;
  - proposal (Rule 4): ID `P\d+`, ISO-ish start, duration (`2h`, `90m`), title ≤ 60 chars, place ≤ 60 chars from `[A-Za-z0-9 ,.'&-]`;
  - free-text questions (`ask-owner`, `ask-around`, `dm` goal): ≤ 140 chars, stored as data and only ever rendered quoted;
  - `budget<=3000`, `budget 3000`, `₹3,000` all parse.
- [ ] Errors return a `ParseError` with a **correct example** of the command, which the gate posts back.
- [ ] Unknown or malformed commands → `Unknown(raw)` so the gate can reply with the command list and (phase 21) send an overreach note.
- [ ] `tests/test_commands.py`: every example line from PLAN.md §3 parses; sloppy variants (lowercase, missing quotes around one-word titles, `Sat 9pm`) parse; over-length title/place/question, bad place characters, and unknown commands are rejected with an example.

## Done when
- [ ] `make check` passes.
- [ ] Every literal command line in PLAN.md §3 and §4 is a test case and parses to the expected object.
- [ ] No code path returns an un-validated string from a cross-boundary command (questions are wrapped in a `Quoted` type).

## Commit
`phase 09: gate command parser with fixed-form validation`

## Log
<!-- evidence, deviations, notes -->
