---
id: "09"
title: Command parser
status: done
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
- [x] Typed command objects for every command in PLAN.md §3:
  - cross-boundary: `free`, `ask`, `ask-owner`, `propose`, `counter`, `gift-ideas`, `claim`, `ask-around`;
  - owner-only: `dm`, `ask-around` (outbound), `yes`, `no`, `answer`, `trust`, `view-as`, `ledger`;
  - gate-to-gate (needed by phase 14, not named in the plan): `join-dm <room> "<goal>"`, and consent/status relays (`consent P1 yes|no via-agent|direct`). Document them in *Log* and later in `SKILL.md`.
- [x] Parsing rules:
  - strip the leading `@<gate-name>`, tolerate extra whitespace, smart quotes, trailing punctuation, code fences;
  - dates via `dateparser` with `Asia/Kolkata`, `PREFER_DATES_FROM: future`; ranges `A..B`, `A to B`, `Nov 14-16`;
  - proposal (Rule 4): ID `P\d+`, ISO-ish start, duration (`2h`, `90m`), title ≤ 60 chars, place ≤ 60 chars from `[A-Za-z0-9 ,.'&-]`;
  - free-text questions (`ask-owner`, `ask-around`, `dm` goal): ≤ 140 chars, stored as data and only ever rendered quoted;
  - `budget<=3000`, `budget 3000`, `₹3,000` all parse.
- [x] Errors return a `ParseError` with a **correct example** of the command, which the gate posts back.
- [x] Unknown or malformed commands → `Unknown(raw)` so the gate can reply with the command list and (phase 21) send an overreach note.
- [x] `tests/test_commands.py`: every example line from PLAN.md §3 parses; sloppy variants (lowercase, missing quotes around one-word titles, `Sat 9pm`) parse; over-length title/place/question, bad place characters, and unknown commands are rejected with an example.

## Done when
- [x] `make check` passes.
- [x] Every literal command line in PLAN.md §3 and §4 is a test case and parses to the expected object.
- [x] No code path returns an un-validated string from a cross-boundary command (questions are wrapped in a `Quoted` type).

## Commit
`phase 09: command parser`

## Log

### Evidence: command parser tests and checks

```
$ uv run ruff format --check trustnet/gate/commands.py tests/test_commands.py
2 files already formatted
$ uv run ruff check trustnet/gate/commands.py tests/test_commands.py
All checks passed!
$ uv run pytest -q tests/test_commands.py
104 passed in 0.64s
$ uv run pytest -q
302 passed in 0.76s
```

Full `make check` at commit time:

```
$ make check
uv run ruff format --check . && uv run ruff check . && uv run pytest -q
61 files already formatted
All checks passed!
302 passed in 0.77s
```

(Earlier while phase 07 was still in progress, `make check` stopped on an unformatted
`trustnet/gate/policy.py`; that file was never touched by this phase and phase 07 landed
before this commit.)

### What is in `trustnet/gate/commands.py`

Public surface:

- `parse(text, *, now=None) -> Command`: strips a leading `@<gate-name>` (kept as
  `command.target`), extra whitespace, smart quotes, code fences and sentence punctuation;
  dispatches on a case-insensitive command word.
- `Command = Free | Ask | AskOwner | Propose | Counter | GiftIdeas | Claim | AskAround |
  Dm | Yes | No | Answer | Trust | ViewAs | Ledger | JoinDm | Consent | Unknown`.
- `Quoted`: the only shape for a free-text question/goal. Validated at construction
  (1–140 chars, one line, no double quote) and `str()` renders it with quotes, so a
  handler cannot accidentally interpolate the raw text.
- `ParseError` (`message`, `example`, `raw`): every known-command failure carries a
  correct example from `EXAMPLES` (also exported for the gate's help text).
- `Unknown(raw, target)`: any unrecognised verb or empty text, with the original text.
- `now=` pins relative dates (`Sat 9pm`, `Sunday`, `tomorrow`) for deterministic tests;
  without it the parser uses the current `Asia/Kolkata` time. Tests pin
  `2026-11-05 09:00 IST`, and 2026-11-08 is a Sunday.

`Propose`, `Counter`, `Dm`, `Trust`, `Claim`, etc. also validate in `__post_init__`, so a
caller that builds one by hand cannot bypass the fixed form.

### Gate-to-gate command syntax (for `SKILL.md`)

```
join-dm <room> "<goal>"
    @rahul-gate join-dm dm-om-rahul-sun "something fun Sunday evening, not pricey"
consent P<n> yes|no via-agent|direct
    @rahul-gate consent P1 yes via-agent
    @om-gate consent P1 no direct
```

- `join-dm`: sent by the inviting gate in `conn-<a>-<b>` after it created the DM room;
  the receiving gate accepts it only from the friend's gate and only in the matching
  connection room (enforced in phase 14). `room` is a lowercase Switch room name; `goal`
  is `Quoted` (≤140 chars).
- `consent`: one side's recorded answer to a proposal after its owner (`direct`) or the
  owner's registered personal agent (`via-agent`) said `yes`/`no`. The receiving gate
  uses `via` for the "✅ … via Hermes" label and never derives consent from text.
- Both are typed by `parse()` like every other command and are not in PLAN.md §3.

### Deviations from PLAN.md

- **Ranges are inclusive at both ends.** `free 2026-11-08..2026-11-09` parses to
  `Free(start=2026-11-08, end=2026-11-09)`, and `Nov 14-16` / `Nov 14 to 16` /
  `14-16 Nov` / `2026-11-14..16` all cover the 14th, 15th and 16th. A single date is a
  one-day range. The plan does not say whether `..` is half-open; inclusive matches the
  prose "tent for Nov 14-16" and the Sunday 2026-11-08 outing.
- **`counter` ID order** is `counter <proposal being replaced> <new proposal>`, read from
  the plan's `counter P1 P2 …` example: `Counter.of == "P1"`, `Counter.proposal_id == "P2"`.
- **`answer` accepts both reference kinds**: `answer Q3 "…"` answers a question, and
  `answer P1 yes` is the CLI/agent form phase 15 uses for a proposal. The parser types
  both as `Answer(reference, text: Quoted)`; the handler decides what `yes`/`no` means.
- **`claim`'s item is a bounded `str`, not `Quoted`**: it is an item label, not a
  question or goal. It is capped at 80 characters, one plain line, and no double quotes.
- **`ask-around` is one class for both directions**: the parser cannot know whether a
  message arrived from a friend's gate or was typed by the owner, so phase 07's policy
  layer decides inbound vs owner-only outbound authorization.
- **A `?` in unquoted free text is kept.** `ask-owner q3 Is this okay?` keeps the
  question mark; sentence punctuation (`. , ; : !`) is stripped, and a `?` after a
  closing quote (`"tent"?`) is stripped.
- **Extra caps not in the plan**: durations must be 1 minute–24 hours, and parsed dates
  must be within one year before to two years after `now` (dateparser can read a
  malformed `Nov 14-16` as year 2116; the range splitter handles the real range first,
  the sanity check catches anything else).
- **§4's two `propose` lines are truncated** (`@om-gate propose P1 …` /
  `@rahul-gate propose P1 …`), so they cannot be parsed literally; the full §3 propose
  line is the test case for the same command.
- **Commit message** is the one requested for this task (`phase 09: command parser`)
  rather than the phase file's earlier suggestion.

### Tests

`tests/test_commands.py` (104 tests):

- every literal command line in PLAN.md §3 and §4, compared to the expected dataclass;
- sloppy variants: case, extra whitespace, code fences, smart quotes, trailing
  punctuation, missing `@gate`, unquoted one-word title/place, `Sat 9pm`/`Sun 9pm`,
  `90m`/`1h30m`, all three budget spellings, all range spellings, lowercase IDs,
  unquoted questions/answers/claims, and the gate-to-gate forms;
- every `EXAMPLES` entry re-parses to its command;
- `now=` determinism (`Sat 9pm` is Nov 7 with a Nov 5 clock, Nov 14 with a Nov 10 clock);
- the outing day is Sunday 2026-11-08;
- questions/goals/answers are `Quoted`, and `Quoted` validates on its own;
- exact-limit title/place/question accepted, over-limit and bad place characters
  rejected;
- 30+ bad forms rejected with a `ParseError` whose `example` re-parses; unknown text
  becomes `Unknown(raw)`, including an empty message and a fenced non-command.
