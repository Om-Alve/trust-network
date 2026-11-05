---
id: "06"
title: Calendar
status: done
priority: P0
owner: agent
depends_on: ["05"]
plan_refs: ["§0 Calendars", "§3 table (busy blocks, event titles)", "§4 Scene 1 steps 5 and 10"]
target: Nov 6 morning
---

# 06 · Calendar

## Goal
`trustnet/gate/calendar.py` reads each person's `.ics` fixture into busy blocks (with titles), and appends accepted plans to it (`tn cal add`).

## Tasks
- [x] `busy(path, start, end) -> list[Block(start, end, title)]` using `icalendar` + `recurring-ical-events`; expands recurring events; clips to the range; merges overlaps; time zone `Asia/Kolkata` for floating times.
- [x] `add_event(path, start, duration, title, place, uid)`: appends a VEVENT; idempotent on `uid` (re-adding P1 doesn't duplicate it).
- [x] Fill the fixture calendars so the scenes play out:
  - Rahul: cricket on the outing day until 20:30, so the envoys land on 21:00.
  - Om: busy earlier that evening (free after 19:00).
  - Both: a couple of weekly recurring events to show expansion, and something during Nov 14–16 for nobody (tent weekend is free).
  - Om's birthday is **not** a calendar event Rahul can see unless it's a fact; keep it out of the calendar.
- [x] Tests: range clipping, recurrence expansion, overlap merge, add-then-read-back, idempotent add.

## Done when
- [x] `make check` passes.
- [x] `busy("examples/rahul/calendar.ics", <outing day 18:00>, <24:00>)` returns a block ending 20:30 titled "Cricket" (or similar).
- [x] Writing P1 into a temp copy of Om's calendar and reading it back returns the event once, even after a second `add_event`.

## Commit
`phase 06: calendar reader and writer`

## Log

### What was built
- `trustnet/gate/calendar.py`:
  - `Block(start, end, title)` — frozen, comparable, half-open (`[start, end)`); naive times are read as `Asia/Kolkata` and aware times are converted to it, so every block is comparable.
  - `busy(path, start, end)` — loads the `.ics` with `icalendar`, expands recurrences with `recurring-ical-events`, clips each occurrence to the requested range, merges, and returns blocks sorted by start. The range and every block are `Asia/Kolkata` aware.
  - `add_event(path, start, duration, title, place="", uid=None)` — appends a `VEVENT` with `UID`, `DTSTAMP`, `DTSTART`, `DTEND`, `SUMMARY` and (when given) `LOCATION`, then rewrites the file with `icalendar`. Returns the written `Block`. A missing or empty file becomes a new `VCALENDAR`; a blank `uid` gets a generated one.
  - `CalendarError(ValueError)` for a missing/malformed file, an empty range, a non-positive duration or a block that ends before it starts.
- Fixtures (`examples/{om,rahul,priya}/calendar.ics`, all `TZID=Asia/Kolkata`):
  - **Om:** single `Family video call` Sun Nov 8 17:00–19:00 (busy earlier that evening, free from 19:00); weekly `Badminton` Tue 20:00–21:30; weekly `Spanish class` Thu 19:00–20:00.
  - **Rahul:** single `Cricket` Sun Nov 8 15:00–20:30 (so the envoys land on 21:00); weekly `Gym` Wed 07:00–08:00; weekly `Badminton` Fri 19:00–20:30.
  - **Priya:** one weekly `Yoga` (Wed 07:00–08:00), kept light as asked.
  - No VEVENT falls in Nov 14–16 (Sat–Mon) for Om or Rahul, so the tent weekend is free. Om's birthday is not in any calendar.
  - Recurring events are Tue/Thu (Om) and Wed/Fri (Rahul) precisely so they miss Nov 14–16.
- Tests in `tests/test_calendar.py` (22 tests): clipping, two-week recurrence expansion, overlap+touching merge with title joining, same-title merge, skipping all-day/transparent/cancelled events, floating times, error cases, add-then-read-back (including `LOCATION` and `DTEND`), minutes-as-duration plus generated UID, creating a missing file, the two Done-when checks, Om free after 19:00, and the free tent weekend for both. Writes always go to `tmp_path` copies; committed fixtures are never mutated.

### Decisions
- **Merged title.** A merged block joins the distinct titles of its events in time order with `" + "` (`"Breakfast + Bowling + Dinner"`); a run that shares one title keeps it (`"Gym"`). This keeps a merged block honest about everything it covers instead of naming the whole stretch after its first event.
- **Touching merges too.** Back-to-back blocks (`end == next.start`) are merged, because the person is busy across the whole stretch. Overlap alone would leave an artificial gap that a proposal could be aimed at.
- **Skipped events.** All-day (`VALUE=DATE`) events, `TRANSP:TRANSPARENT` and `STATUS:CANCELLED` events are not busy: they have no time of day to propose around, or the person is explicitly free/gone.
- **No `VTIMEZONE` blocks** in the fixtures. `TZID=Asia/Kolkata` resolves through Python's `zoneinfo`, and the files stay readable; verified by the tests.
- **Idempotency returns the stored event.** Re-adding an existing `uid` does not touch the file and returns the block already stored, not the requested one, so a caller never reports a write that did not happen.

### Evidence: make check
```
$ make check
uv run ruff format --check . && uv run ruff check . && uv run pytest -q
59 files already formatted
All checks passed!
......................................................................   [100%]
70 passed in 0.14s
```

### Evidence: Done-when 1 — Rahul's cricket ends 20:30
```
$ uv run python -c 'from datetime import datetime; from zoneinfo import ZoneInfo; from trustnet.gate.calendar import busy; IST=ZoneInfo("Asia/Kolkata"); print(busy("examples/rahul/calendar.ics", datetime(2026,11,8,18,tzinfo=IST), datetime(2026,11,9,tzinfo=IST)))'
[Block(start=datetime.datetime(2026, 11, 8, 18, 0, tzinfo=zoneinfo.ZoneInfo(key='Asia/Kolkata')), end=datetime.datetime(2026, 11, 8, 20, 30, tzinfo=zoneinfo.ZoneInfo(key='Asia/Kolkata')), title='Cricket')]
```

### Evidence: Done-when 2 — P1 added twice to a temp copy, read back once
```
add #1 = Block(start=2026-11-08 21:00+05:30, end=2026-11-08 23:00+05:30, title='Bowling + dinner')
add #2 = Block(start=2026-11-08 21:00+05:30, end=2026-11-08 23:00+05:30, title='Bowling + dinner')
busy after two adds = [Block(start=2026-11-08 21:00+05:30, end=2026-11-08 23:00+05:30, title='Bowling + dinner')]
P1 UID count = 1
```
Also asserted in `test_p1_added_twice_to_om_copy_appears_once`: the file bytes are unchanged by the second add, and `busy` returns exactly one block. `uv run pytest -q tests/test_calendar.py` → `22 passed`.

### Evidence: recurrence expansion and free tent weekend
```
om 2026-11-09..16: [('Tue 10 20:00', '21:30', 'Badminton'), ('Thu 12 19:00', '20:00', 'Spanish class')]
om 2026-11-16..23: [('Tue 17 20:00', '21:30', 'Badminton'), ('Thu 19 19:00', '20:00', 'Spanish class')]
om 2026-11-14..17: []
rahul 2026-11-09..16: [('Wed 11 07:00', '08:00', 'Gym'), ('Fri 13 19:00', '20:30', 'Badminton')]
rahul 2026-11-16..23: [('Wed 18 07:00', '08:00', 'Gym'), ('Fri 20 19:00', '20:30', 'Badminton')]
rahul 2026-11-14..17: []
```

### Deviations
- `add_event`'s `place` and `uid` are keyword-defaulted (`""`, generated), so `tn cal add` can write an event without a location and retries without a UID still work; every task-listed argument is still accepted positionally.
- A numeric `duration` means **minutes** (`90` = 1.5 h); a `timedelta` is used as given.
- Commit message changed from the phase file's earlier `phase 06: ics calendar reader and writer` to `phase 06: calendar reader and writer` on the task owner's instruction.
