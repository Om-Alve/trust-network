---
id: "08"
title: Ledger and view-as
status: done
priority: P0
owner: agent
depends_on: ["07"]
plan_refs: ["§3 Rule 6", "§3 owner commands `view-as`, `ledger`", "§4 Scene 2 step 6", "§4 Overreach and view-as"]
target: Nov 6 morning
---

# 08 · Ledger and view-as

## Goal
`trustnet/gate/ledger.py` records every disclosure, and `view-as` shows the owner exactly what a given person's side can learn. Both reuse `policy.py`, never their own rules.

## Tasks
- [x] Ledger entries appended to `<data dir>/ledger.jsonl`: `ts`, `field`, `value`, `to` (person), `room`, `kind` (`answer` | `brief` | `proposal` | `gift` | `ask-around`), optional `sealed_until`.
- [x] `record_brief(brief_facts, to, room)` writes one entry per fact in the brief (Rule 6: a brief discloses every fact in it).
- [x] `owner_view(now)`: unsealed entries in full; sealed entries collapsed to a count plus the earliest open date, e.g. "1 sealed entry, opens Nov 21". Sealed entries become visible after `sealed_until`.
- [x] `format_ledger(...)` → compact text for `#om-home` (grouped by person, newest first, at most ~20 lines).
- [x] `view_as(profile, trust, person)` → field-by-field table: each fact with ✅ value / ❌ "not shared at this level", calendar detail (busy blocks only vs with titles), the person's level, and a line for "not on your list → nothing" if applicable. Claimed gift items are not shown to the owner (hook for phase 19; for now, an empty claims set).
- [x] Tests: sealed entry hidden then revealed by time; brief logging; `view_as(om, rahul)` vs `view_as(om, priya)` differ exactly by the close-level facts and nothing else.

## Done when
- [x] `make check` passes.
- [x] `view_as` output for Om→Rahul and Om→Priya matches `policy.visible_facts` for the same level (asserted in a test, so the two can't disagree).
- [x] Ledger file is append-only (no code path rewrites it), noted in *Log*.

## Commit
`phase 08: disclosure ledger, sealed entries, view-as`

## Log

### What was built

**`trustnet/gate/ledger.py` — the append-only disclosure ledger.**

- `ledger_path(person)` is `resolve_data_dir(person)/ledger.jsonl`, i.e. `TN_DATA_DIR/<person>/` when set, otherwise `examples/<person>/`. Tests always point `TN_DATA_DIR` at `tmp_path`, so nothing writes into `examples/`.
- One `Entry` per line: `ts`, `field`, `value`, `to`, `room`, `kind`, and `sealed_until` only when sealed. `ts` is an aware Asia/Kolkata ISO timestamp (naive input is read as India time); `sealed_until` is stored as an ISO date and the entry opens on that day.
- `record(...)` is the single write path. `record_brief(brief_facts, to, room, ...)` writes one `brief` entry per fact in mapping order, all with one shared timestamp (Rule 6). `read(person)` returns entries oldest first; a missing file is an empty ledger, a malformed line raises `LedgerError` and leaves the bytes alone.
- `owner_view(now, person=...)` returns `visible` (opened entries, newest first) and `sealed` (still-sealed entries), plus `sealed_count`, `sealed_opens` and `sealed_line` → `"1 sealed entry, opens Nov 21"`.
- `format_ledger(now, person=..., max_lines=20)` groups by person (newest group first, newest entry first inside a group), keeps the output under the line cap with `… N more entries`, and always leaves the sealed line last. A ledger holding only sealed entries prints just the sealed line, which is Scene 2's home-channel output.

**`trustnet/gate/view_as.py` — the owner's view of one person's side.**

- `view_as(profile, trust, person, now=None, days=7, claims=())` builds one row for **every** fact the owner has: ✅ with the value from `policy.visible_facts`, or ❌ `"not shared at this level"`. Every ✅ is the policy's answer; no level rule is repeated here.
- The calendar is `calendar.busy` for the window, filtered through `policy.calendar_view`. `titles_visible` is decided by asking the policy with a one-block probe, not by checking the level again.
- Someone not on the list (or an id the list cannot hold, like an mxid) gets no rows and no calendar, and the result renders `view-as dev — not on your list → nothing`.
- `Claim(item, reveal_after)` is the phase 19 hook: a claimed wishlist item is dropped from the owner's view until its reveal day. The default claims set is empty. Phase 19 can pass its own records because only `.item` and `.reveal_after` are read.
- `ViewAsResult` exposes `.person`, `.level`, `.rows` (`FactRow.name/.visible/.value`), `.calendar`, `.titles_visible`, `.window`, `.days`, `.visible_values` and `.render()`/`str()`.

**Tests:** `tests/test_ledger.py` (34) and `tests/test_view_as.py` (24) = 58.

### Append-only

`_append()` is the module's only write: it opens the file with `path.open("a", encoding="utf-8")` and writes one JSON line. No code path uses `"w"`, truncates, renames or deletes the ledger. Three tests pin this down:

- `test_record_never_rewrites_earlier_lines` — after a second record the file still starts with the exact previous bytes;
- `test_no_code_path_rewrites_the_ledger` — one `.open(` in the module and it is append mode; no `write_text`, `truncate`, `os.replace` or `shutil`;
- `test_read_raises_on_a_malformed_line_and_keeps_the_file` — a bad line is reported and the bytes are unchanged.

### Public API for phases 10, 12, 19

```python
from trustnet.gate import ledger, view_as

ledger.ledger_path(person) -> Path
ledger.record(field, value, to, room, kind, *, person,
              sealed_until=None, now=None) -> Entry
ledger.record_brief(brief_facts, to, room, *, person,
                    sealed_until=None, now=None) -> list[Entry]
ledger.read(person) -> list[Entry]                 # oldest first
ledger.owner_view(now=None, *, person) -> OwnerView
ledger.format_ledger(now=None, *, person, max_lines=20) -> str
# OwnerView: .visible, .sealed, .sealed_count, .sealed_opens, .sealed_line
# Entry: .ts, .field, .value, .to, .room, .kind, .sealed_until, .is_sealed(now)
# Kind: "answer" | "brief" | "proposal" | "gift" | "ask-around"; LedgerError

view_as.view_as(profile, trust, person, *, now=None, days=7, claims=()) -> ViewAsResult
# ViewAsResult: .person, .level, .rows, .calendar, .titles_visible,
#               .window, .days, .visible_values, .render(), str()
# FactRow: .name, .visible, .value
# CalendarRow: .start, .end, .title
view_as.Claim(item, reveal_after)   # phase 19 claims hook
view_as.ViewAsError
```

Phase 12 calls `ledger.record_brief(disclosed_facts, friend, room, person=profile.owner)` after writing a brief. Phase 19 records a gift with `ledger.record(..., kind="gift", sealed_until=occasion + 1 day, person=profile.owner)` and passes its hidden claims to `view_as(...)`.

### Evidence: make check

```
$ make check
uv run ruff format --check . && uv run ruff check . && uv run pytest -q
65 files already formatted
All checks passed!
360 passed in 0.86s
```

### Evidence: phase tests

```
$ uv run pytest -q tests/test_ledger.py tests/test_view_as.py
58 passed in 0.07s
```

The required assertion is in `test_rahul_gets_exactly_the_close_level_facts` and `test_priya_gets_exactly_the_friend_level_facts` (both compare `.visible_values` to `policy.visible_facts`), and `test_the_two_views_differ_exactly_by_the_close_level_facts` asserts the difference is exactly `{neighbourhood, sizes, wishlist}` — the facts tagged `close` in `examples/om/facts.yaml`.

### Evidence: `view_as` Om→Rahul (close)

```
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
```

### Evidence: `view_as` Om→Priya (friend)

```
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

### Evidence: a person not on the list

```
view-as dev — not on your list → nothing
```

### Evidence: sample `format_ledger` (after a brief, a proposal, an ask-around and a sealed gift)

```
Shared: 5 entries · 2 people
priya
  Nov 6 09:30  conn-om-priya  ask-around  tent to borrow, Nov 14-16
rahul
  Nov 5 18:12  dm-om-rahul-sat  proposal    P1: id: P1, start: 2026-11-08T21:00, duration: 2h, title: Bowling + dinner, place: Smaaas…
  Nov 5 18:05  dm-om-rahul-sat  brief       diet: vegetarian
  Nov 5 18:05  dm-om-rahul-sat  brief       interests: bowling, board games, sci-fi
  Nov 5 18:05  dm-om-rahul-sat  brief       has: projector, camping stove
1 sealed entry, opens Nov 21
```

With only a sealed gift in the ledger, `format_ledger` returns exactly:

```
1 sealed entry, opens Nov 21
```

### Deviations

- `view-as` lives in its own module, `trustnet/gate/view_as.py` (explicitly allowed by the brief), so `ledger.py` stays file-only. `Claim` lives in `view_as.py`; phase 19 imports it or passes any record with `.item` and `.reveal_after`.
- Every ledger function takes the ledger's owner as a required keyword, `person=`, and resolves the path through `resolve_data_dir`. There is no hidden default owner, so a caller cannot log to the wrong person's ledger by omission. Tests set `TN_DATA_DIR` to `tmp_path`.
- `sealed_until` is a date, not a datetime: entries open on that calendar day, matching "opens Nov 21" and phase 19's `occasion + 1 day`. `date`, `datetime` and ISO strings are accepted and normalized.
- `format_ledger` prints at most 20 lines by default (`max_lines`, minimum 3). It drops the oldest entries and prints `… N more entries`; the sealed summary is always last. A sealed-only ledger prints just the sealed line, because that is what `#om-home` should show in Scene 2.
- `kind` is a `StrEnum` (`Kind`) and is accepted case-insensitively; unknown kinds raise `LedgerError`.
- Ask-around ledger lines print the question value without the field name (e.g. `ask-around  tent to borrow, Nov 14-16`); other kinds print `field: value`.
- `view_as`'s calendar window defaults to 7 days from `now` (`days=` overrides). It shows busy blocks even with no events ("nothing busy"). Title visibility is answered by `policy.calendar_view` on a probe block, so a future policy change cannot make `view-as` disagree with `ask`.
- With a non-empty claims set, `view_as(...).visible_values` intentionally differs from `policy.visible_facts` for the wishlist (that is the surprise). The equivalence assertions use the default empty claims set.
- Only `trustnet/gate/ledger.py` (was a one-line stub), new `trustnet/gate/view_as.py`, new `tests/test_ledger.py`, new `tests/test_view_as.py` and this phase file changed.
