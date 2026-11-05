---
id: "10"
title: tn CLI (offline commands)
status: done
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
- [x] `trustnet/tn/cli.py` with argparse subcommands and a global `--as <person>` (selects the data dir from phase 05; defaults to `$TN_PERSON`):
  - `tn init <person>` — create a data dir with empty `trust.yaml`, `facts.yaml`, `calendar.ics`;
  - `tn trust <person> <level>` — owner edits their trust list;
  - `tn fact get [<key>…]` — the owner's own view (later hides claimed gift items, phase 19);
  - `tn fact set <key> --level <level> [--value …]` — **tighten-only** (Rule 3): loosening is refused with "edit facts.yaml by hand to loosen";
  - `tn cal add <start> <duration> "<title>" @ "<place>" [--id P1]` — via `calendar.add_event`;
  - `tn view-as <person>` — prints the phase 08 table.
- [x] Output is plain text by default and `--json` for agents.
- [x] Tests (call `main([...])` directly): each subcommand against a temp copy of the fixtures; tighten-only refusal; `cal add` idempotent.

## Done when
- [ ] `make check` passes. *(This phase's files are clean and the full pytest suite passes; `make check` currently stops in phase 12's `trustnet/gate/brief.py`, owned by another agent. See Log.)*
- [x] `uv run tn --as om view-as rahul` and `uv run tn --as om view-as priya` print different, correct tables.
- [x] `uv run tn --as om fact set drinks --level acquaintance` is refused; `--level close` succeeds (on a temp data dir, not the committed fixtures).

## Commit
`phase 10: tn CLI for trust, facts, calendar and view-as`

## Log

### What was built
`trustnet/tn/cli.py` (one module, ~600 lines including docstrings; the CLI surface is ~200 lines of logic) with `main(argv: list[str] | None = None) -> int`, so both the console script (`tn = "trustnet.tn.cli:main"`) and tests call the same entry point.

```
tn [-a|--as PERSON] [--json] <command>
  init [person] [--force]                 empty trust.yaml, facts.yaml, calendar.ics
  trust <person> <level>                  owner edits the trust list (acquaintance/friend/close)
  fact get [key ...]                      owner's own view, private facts included
  fact set <key> --level <level> [--value VALUE]   tighten-only (Rule 3)
  cal add <start> <duration> "<title>" @ "<place>" [--id P1]
  view-as <person> [--days N]             phase 08 table (calendar window, default 7 days)
```

- **Parser.** One `_build_parser()` builds every subcommand and stamps each leaf with `set_defaults(handler=…)`; `main` dispatches through `args.handler`. Phase 15 adds `inbox`/`answer`/`dm` by adding parsers and handlers beside these, no dispatch changes. `--as` and `--json` are accepted before **or** after the subcommand (the subparser copies use `SUPPRESS` defaults, so they never reset an earlier flag; `set_defaults` on the root would have mutated the shared parent action and broken `tn --as om …` — the comment in `_global_options` records this).
- **Exit codes.** `0` success, `1` refused/user error (`CliError`, `FactsError`, `CalendarError`, `ViewAsError`, `OSError`, printed as `tn: error: …` on stderr), `2` argparse usage error. `main` catches `SystemExit` from argparse, so `--help` returns 0 and `main(["nope"])` returns 2 instead of raising.
- **Tighten-only.** `fact set` calls `policy.can_set_level(old, new, Actor.AGENT)`, the phase 07 rule, rather than reimplementing the comparison. Refusal is `refusing to loosen drinks: friend → acquaintance; edit facts.yaml by hand to loosen`. Setting the same level (or changing only `--value`) is allowed. A new fact needs `--value`; a value starting with `[` or `{` is parsed as YAML so lists/mappings can be set, everything else stays a string.
- **Calendar.** `cal add` loads the profile to find `calendar.ics` and calls `calendar.add_event(..., uid=--id)`, so re-adding `--id P1` leaves the file byte-identical (`add_event` returns the stored block before writing). Starts are parsed with `dateparser` pinned to `Asia/Kolkata` + `PREFER_DATES_FROM: future` (`2026-11-08T21:00`, `Sun 9pm` both work); durations are parsed locally (`2h`, `90m`, `1h30m`, 1 minute–24 hours) because `commands.py` keeps its helpers private and its errors name `@gate propose` examples. Titles/places use the Rule 4 limits (60 chars, place charset) and places require the literal `@` token.
- **JSON.** One object per command, no envelope: `init` → `{person, data_dir, files, overwrote}`; `trust` → `{owner, person, level, previous}`; `fact get` → `{owner, facts: {key: {value, level}}}`; `fact set` → `{owner, fact, value, level, previous_level, created}`; `cal add` → `{owner, id, start, end, title, place, calendar}`; `view-as` → `{owner, person, level, facts: [{name, visible, value}], calendar, titles_visible, window, days}`. Values pass through `_jsonable` so YAML dates never break `json.dumps`.
- **Tests.** `tests/test_cli.py`: 36 tests, all calling `main([...])`, all writes against a `tmp_path` copy of `examples/` with `TN_DATA_DIR`; the committed fixtures are only read (there is a test that asserts their bytes are unchanged after `view-as`).

### Evidence: `view-as` Om → Rahul (close) and Om → Priya (friend)

```
$ uv run tn --as om view-as rahul
view-as rahul — close
  ✅ diet           vegetarian
  ✅ city           Bangalore
  ✅ drinks         no alcohol
  ✅ interests      bowling, board games, sci-fi
  ✅ has            projector, camping stove
  ✅ recommends     dentist: Dr. Rao, 12th Main
  ✅ neighbourhood  Indiranagar
  ✅ sizes          tshirt: M
  ✅ wishlist       Catan Seafarers (≈₹2,500), Hario V60 (≈₹2,000), Kindle Paperwhite (≈₹14,000)
  ❌ address        not shared at this level

Calendar · next 7 days (Nov 5 – Nov 12) · with titles
  Thu Nov 5  19:00–20:00  Spanish class
  Sun Nov 8  17:00–19:00  Family video call
  Tue Nov 10  20:00–21:30  Badminton

$ uv run tn --as om view-as priya
view-as priya — friend
  ✅ diet           vegetarian
  ✅ city           Bangalore
  ✅ drinks         no alcohol
  ✅ interests      bowling, board games, sci-fi
  ✅ has            projector, camping stove
  ✅ recommends     dentist: Dr. Rao, 12th Main
  ❌ neighbourhood  not shared at this level
  ❌ sizes          not shared at this level
  ❌ wishlist       not shared at this level
  ❌ address        not shared at this level

Calendar · next 7 days (Nov 5 – Nov 12) · with titles
  Thu Nov 5  19:00–20:00  Spanish class
  Sun Nov 8  17:00–19:00  Family video call
  Tue Nov 10  20:00–21:30  Badminton
```

The two tables differ exactly by the facts tagged `close` (`neighbourhood`, `sizes`, `wishlist`), matching phase 08's evidence; both hide `address` (private).

### Evidence: tighten-only, on a temp copy of Om's fixture

```
$ TMP=$(mktemp -d) && cp -R examples/om "$TMP/om"
$ TN_DATA_DIR="$TMP" uv run tn --as om fact set drinks --level acquaintance
tn: error: refusing to loosen drinks: friend → acquaintance; edit facts.yaml by hand to loosen
$ echo $?
1
$ TN_DATA_DIR="$TMP" uv run tn --as om fact set drinks --level close
drinks: friend → close (no alcohol)
$ echo $?
0
$ TN_DATA_DIR="$TMP" uv run tn --as om fact get drinks
om — 1 fact
  drinks  close  no alcohol
```

The committed `examples/om/facts.yaml` was not touched; every write test uses `TN_DATA_DIR` pointing at a temp copy.

### Evidence: `cal add` idempotency (from the test suite)

```
$ uv run tn --as om cal add 2026-11-08T21:00 2h "Bowling + dinner" @ "Smaaash, Indiranagar" --id P1
P1  Sun Nov 8, 21:00–23:00  Bowling + dinner @ Smaaash, Indiranagar
$ uv run tn --as om cal add 2026-11-08T21:00 2h "Bowling + dinner" @ "Smaaash, Indiranagar" --id P1
P1  Sun Nov 8, 21:00–23:00  Bowling + dinner @ Smaaash, Indiranagar
$ grep -c 'UID:P1' calendar.ics
1
```

`test_cal_add_writes_the_event_and_is_idempotent` also asserts the second call leaves the calendar bytes identical and that `calendar.busy(20:00–23:00)` sees one 21:00–23:00 block titled `Bowling + dinner`.

### Evidence: checks

```
$ uv run ruff format --check trustnet/tn/cli.py tests/test_cli.py
2 files already formatted
$ uv run ruff check trustnet/tn/cli.py tests/test_cli.py
All checks passed!
$ uv run pytest -q tests/test_cli.py
36 passed in 0.77s
$ uv run pytest -q
400 passed in 0.94s
```

`make check` currently fails in the format step on `trustnet/gate/brief.py` (phase 12, another agent's in-progress file). Nothing in this phase's paths fails; re-run `make check` once phase 12 is formatted.

### Deviations
- `tn init`'s person is optional (`tn init` uses `--as` / `$TN_PERSON`), and `--force` overwrites an existing profile. The phase only names `tn init <person>`; both forms work.
- `view-as` takes `--days N` (default 7) to match `view_as(..., days=…)`; not required by the task.
- `cal add` parses dates/durations locally instead of importing `commands.py`'s underscore-prefixed helpers; the accepted forms and Rule 4 limits match the gate's parser.
- `--as` / `--json` work in both positions around the subcommand; this is what made the phase-15 reuse point explicit.
- No changes to `PLAN.md` were needed: the CLI, its size and its flags stay within PLAN §5.
