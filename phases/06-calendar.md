---
id: "06"
title: Calendar
status: todo
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
- [ ] `busy(path, start, end) -> list[Block(start, end, title)]` using `icalendar` + `recurring-ical-events`; expands recurring events; clips to the range; merges overlaps; time zone `Asia/Kolkata` for floating times.
- [ ] `add_event(path, start, duration, title, place, uid)`: appends a VEVENT; idempotent on `uid` (re-adding P1 doesn't duplicate it).
- [ ] Fill the fixture calendars so the scenes play out:
  - Rahul: cricket on the outing day until 20:30, so the envoys land on 21:00.
  - Om: busy earlier that evening (free after 19:00).
  - Both: a couple of weekly recurring events to show expansion, and something during Nov 14–16 for nobody (tent weekend is free).
  - Om's birthday is **not** a calendar event Rahul can see unless it's a fact; keep it out of the calendar.
- [ ] Tests: range clipping, recurrence expansion, overlap merge, add-then-read-back, idempotent add.

## Done when
- [ ] `make check` passes.
- [ ] `busy("examples/rahul/calendar.ics", <outing day 18:00>, <24:00>)` returns a block ending 20:30 titled "Cricket" (or similar).
- [ ] Writing P1 into a temp copy of Om's calendar and reading it back returns the event once, even after a second `add_event`.

## Commit
`phase 06: ics calendar reader and writer`

## Log
<!-- evidence, deviations, notes -->
