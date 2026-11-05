---
id: "08"
title: Ledger and view-as
status: todo
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
- [ ] Ledger entries appended to `<data dir>/ledger.jsonl`: `ts`, `field`, `value`, `to` (person), `room`, `kind` (`answer` | `brief` | `proposal` | `gift` | `ask-around`), optional `sealed_until`.
- [ ] `record_brief(brief_facts, to, room)` writes one entry per fact in the brief (Rule 6: a brief discloses every fact in it).
- [ ] `owner_view(now)`: unsealed entries in full; sealed entries collapsed to a count plus the earliest open date, e.g. "1 sealed entry, opens Nov 21". Sealed entries become visible after `sealed_until`.
- [ ] `format_ledger(...)` → compact text for `#om-home` (grouped by person, newest first, at most ~20 lines).
- [ ] `view_as(profile, trust, person)` → field-by-field table: each fact with ✅ value / ❌ "not shared at this level", calendar detail (busy blocks only vs with titles), the person's level, and a line for "not on your list → nothing" if applicable. Claimed gift items are not shown to the owner (hook for phase 19; for now, an empty claims set).
- [ ] Tests: sealed entry hidden then revealed by time; brief logging; `view_as(om, rahul)` vs `view_as(om, priya)` differ exactly by the close-level facts and nothing else.

## Done when
- [ ] `make check` passes.
- [ ] `view_as` output for Om→Rahul and Om→Priya matches `policy.visible_facts` for the same level (asserted in a test, so the two can't disagree).
- [ ] Ledger file is append-only (no code path rewrites it), noted in *Log*.

## Commit
`phase 08: disclosure ledger, sealed entries, view-as`

## Log
<!-- evidence, deviations, notes -->
