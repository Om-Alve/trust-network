---
id: "12"
title: Envoy brief
status: blocked
priority: P0
owner: agent + human
depends_on: ["07", "08"]
plan_refs: ["§3 Rule 7", "§3 Rule 6", "§5 envoy-brief.md.j2", "§12 Code with Wispr"]
target: Nov 6 afternoon
---

# 12 · Envoy brief

## Goal
The envoy's instructions are built from the same policy code that answers `ask`, so an envoy never knows more than the other side could ask the gate for (Rule 7).

**Repurposed (2026-11-05, no-envoy decision):** there is no envoy to brief anymore. This phase's code (`brief.py`, `envoy-brief.md.j2`) is kept and repurposed as the **share card** each gate hands its own main agent privately at the start of a DM — built from the same policy code that answers `ask`, so the card tells the agent what the friend's trust level allows. Unlike the old envoy brief, the card is guidance, not a hard limiter: the main agent (`om-hermes`/Hermes, `rahul-agent`/Codex) already knows its own person's whole life and isn't restricted to the card's contents. See PLAN.md §3 Rule 7 and §6. The worked examples below still read "envoy"; treat every occurrence as "the owner's own main agent" and every rendered brief as the share card text handed to that agent.

## Tasks
- [ ] **[human]** Om dictates the prose of `templates/envoy-brief.md.j2` with Wispr (Code with Wispr requirement). The agent supplies the variable slots and edits only for structure.
- [x] Template contents: the goal (quoted), the person's name and the friend's name, facts at the room level, busy blocks (and titles if allowed) for the relevant date range, and the rules: "only state what's here; if you need something else, send `@<gate> ask-owner Qn "…"`; you can't commit to anything; propose with `@<gate> propose …` and `@<friend-gate> propose …`; keep messages short; stop after agreement". Include exact command examples.
- [x] `trustnet/gate/brief.py`: `build_brief(profile, trust, friend, room, goal, date_range) -> (text, disclosed_facts)` using `policy.visible_facts` and `policy.calendar_view`.
- [x] Every brief written calls `ledger.record_brief` (phase 08).
- [x] `tests/test_brief.py`:
  - brief for a friend-level room contains no close or private facts (search for each value string);
  - **equivalence**: the set of facts in the brief equals the set `ask` would return at that level;
  - the goal and other free text appear only in quoted form;
  - snapshot test of the rendered Om→Rahul brief (stored in `tests/data/`).

## Done when
- [x] `make check` passes, including the equivalence test.
- [ ] The template text was dictated by Om (noted in *Log* for the Wispr submission).
- [x] Rendered Om→Rahul and Om→Priya briefs are pasted in *Log* for a human read-through.

## Commit
`phase 12: level-filtered envoy brief and template`

## Log

### What was built

**`templates/envoy-brief.md.j2`** — the envoy's whole prompt, laid out from slots only:

- the owner's and friend's display names, and both gate names (`om-gate`, `rahul-gate`);
- the goal, always rendered by `commands.Quoted` (so the only free text is quoted);
- the facts the policy allows, one bullet per fact;
- the busy blocks for the inclusive date range, with a title only when `policy.calendar_view` kept it;
- the six rules, with exact phase 09 commands: one `ask-owner`, two `propose` (own gate and friend's gate) and two `counter` (own gate and friend's gate).

The prose blocks carry `{# DRAFT: Om dictates final prose (Wispr) #}` (six markers). Jinja comments do not render, so they never reach the envoy. The slots and section order are stable: Om's dictation replaces the sentences, not the structure.

**`trustnet/gate/brief.py`**

- `build_brief(profile, trust, friend, room, goal, date_range) -> (text, disclosed_facts)` — pure: asks `policy.visible_facts` for facts and `policy.calendar_view(busy(...), level)` for blocks, renders the template, returns the text and the exact fact mapping it stated. It contains no level rule of its own.
- `write_brief(profile, trust, friend, room, goal, date_range, *, now=None) -> Brief` — the recording entry point phase 13b/14 should call. It renders the same brief, calls `ledger.record_brief(facts, friend, room, person=profile.owner, now=now)` (one `brief` entry per fact), and adds one `calendar` entry with the policy-filtered blocks (the same field name phase 11's `free` handler uses). `Brief` carries `.text`, `.level`, `.disclosed_facts` and `.entries`.
- `date_range` is two inclusive India dates, the same convention as `free 2026-11-08..2026-11-09`; the window ends at 00:00 the day after the second date. A `datetime` is read as its India date.
- The friend's trust level is the room level, which is true for a one-to-one DM; the module docstring says the caller must still check `policy.room_level` from Switch membership first (Rule 1).

### Public API for phases 13b/14

```python
from trustnet.gate.brief import Brief, BriefError, build_brief, write_brief

build_brief(profile, trust, friend, room, goal, date_range) -> (text, disclosed_facts)
write_brief(profile, trust, friend, room, goal, date_range, *, now=None) -> Brief
# Brief: .text, .level, .disclosed_facts, .entries
```

Use `write_brief` when briefing an envoy; `build_brief` writes no ledger entry by design.

### Evidence: make check

```
$ make check
uv run ruff format --check . && uv run ruff check . && uv run pytest -q
73 files already formatted
All checks passed!
433 passed in 1.06s
```

### Evidence: phase 12 tests

```
$ uv run pytest -q tests/test_brief.py
31 passed in 0.14s
```

The 31 tests cover: fact rows equal `policy.visible_facts` for Om→Rahul (close), Om→Priya (friend) and every hand-built room level; no close/private leaf string in a friend brief; no value above the room level anywhere in the text at acquaintance, friend and close; private address never present; titles stripped at acquaintance and kept at friend; the goal appears exactly once and quoted; unquotable goals rejected; every command example parses with the real gate names; the snapshot; the two demo briefs differ exactly by `neighbourhood`, `sizes`, `wishlist`; `write_brief` logs one entry per fact plus `calendar`, all in `TN_DATA_DIR`; `build_brief` alone writes nothing.

### Rendered Om → Rahul (close)

````text
# You are Om's envoy to Rahul

You speak for Om in a private Switch room with Rahul's envoy. This brief is your only source about Om. You have no files, no shell and no memory of earlier rooms: if something is not written here, you do not know it.

## The goal

Om asked for: "something fun Sunday evening, not pricey"

## What you may say about Om

Only state these facts, in your own words. Do not add, guess or infer anything else. If Rahul's envoy asks for something that is not here, say it is not shared and use `ask-owner` (rule 2).

- **diet**: vegetarian
- **city**: Bangalore
- **drinks**: no alcohol
- **interests**: bowling, board games, sci-fi
- **has**: projector, camping stove
- **recommends**: dentist: Dr. Rao, 12th Main
- **neighbourhood**: Indiranagar
- **sizes**: tshirt: M
- **wishlist**: Catan Seafarers (≈₹2,500), Hario V60 (≈₹2,000), Kindle Paperwhite (≈₹14,000)

## When Om is busy (Sun Nov 8 to Mon Nov 9, Asia/Kolkata)

These are Om's busy blocks. Propose around them; do not ask Om to move one unless Rahul's side cannot make anything else work.

- Sun Nov 8, 17:00–19:00 — Family video call

## Rules

1. Only state what is in this brief. Never invent a fact, a preference, a time or a promise.
2. If you need something that is not here, ask Om through your gate:
   `@om-gate ask-owner Q1 "Is ₹1,500 per person okay?"`
   Use a fresh question number each time (Q1, Q2, ...). The gate posts the answer in this room as `answer Q1 "..."`. Treat the answer as one more fact for this conversation only.
3. You cannot commit to anything. Only Om can agree, and only through the gate.
4. To propose a plan, send it through both gates with the same proposal ID:
   `@om-gate propose P1 2026-11-08T21:00 2h "Dinner and a walk" @ "The Park, MG Road"`
   `@rahul-gate propose P1 2026-11-08T21:00 2h "Dinner and a walk" @ "The Park, MG Road"`
   If Rahul's side proposes and you cannot accept it, counter it through both gates:
   `@om-gate counter P1 P2 2026-11-09T19:00 2h "Dinner and a walk" @ "The Park, MG Road"`
   `@rahul-gate counter P1 P2 2026-11-09T19:00 2h "Dinner and a walk" @ "The Park, MG Road"`
5. Keep messages short: one or two sentences, and no list longer than three lines.
6. Stop after you agree, or when the gate says the conversation is over. Do not keep chatting.

Your gate is `@om-gate`. Rahul's gate is `@rahul-gate`. Write commands exactly in the forms above; the gates ignore anything else.
````

### Rendered Om → Priya (friend)

````text
# You are Om's envoy to Priya

You speak for Om in a private Switch room with Priya's envoy. This brief is your only source about Om. You have no files, no shell and no memory of earlier rooms: if something is not written here, you do not know it.

## The goal

Om asked for: "something fun Sunday evening, not pricey"

## What you may say about Om

Only state these facts, in your own words. Do not add, guess or infer anything else. If Priya's envoy asks for something that is not here, say it is not shared and use `ask-owner` (rule 2).

- **diet**: vegetarian
- **city**: Bangalore
- **drinks**: no alcohol
- **interests**: bowling, board games, sci-fi
- **has**: projector, camping stove
- **recommends**: dentist: Dr. Rao, 12th Main

## When Om is busy (Sun Nov 8 to Mon Nov 9, Asia/Kolkata)

These are Om's busy blocks. Propose around them; do not ask Om to move one unless Priya's side cannot make anything else work.

- Sun Nov 8, 17:00–19:00 — Family video call

## Rules

1. Only state what is in this brief. Never invent a fact, a preference, a time or a promise.
2. If you need something that is not here, ask Om through your gate:
   `@om-gate ask-owner Q1 "Is ₹1,500 per person okay?"`
   Use a fresh question number each time (Q1, Q2, ...). The gate posts the answer in this room as `answer Q1 "..."`. Treat the answer as one more fact for this conversation only.
3. You cannot commit to anything. Only Om can agree, and only through the gate.
4. To propose a plan, send it through both gates with the same proposal ID:
   `@om-gate propose P1 2026-11-08T21:00 2h "Dinner and a walk" @ "The Park, MG Road"`
   `@priya-gate propose P1 2026-11-08T21:00 2h "Dinner and a walk" @ "The Park, MG Road"`
   If Priya's side proposes and you cannot accept it, counter it through both gates:
   `@om-gate counter P1 P2 2026-11-09T19:00 2h "Dinner and a walk" @ "The Park, MG Road"`
   `@priya-gate counter P1 P2 2026-11-09T19:00 2h "Dinner and a walk" @ "The Park, MG Road"`
5. Keep messages short: one or two sentences, and no list longer than three lines.
6. Stop after you agree, or when the gate says the conversation is over. Do not keep chatting.

Your gate is `@om-gate`. Priya's gate is `@priya-gate`. Write commands exactly in the forms above; the gates ignore anything else.
````

### Snapshot

`tests/data/brief-om-rahul.md` is the exact rendered Om→Rahul text above (rendered with the demo goal and `2026-11-08..2026-11-09`). After Om dictates the prose, regenerate it:

```sh
uv run python -c '
from datetime import date
from pathlib import Path
from trustnet.gate.brief import build_brief
from trustnet.gate.commands import Quoted
from trustnet.gate.facts import EXAMPLES_DIR, load_profile_file, load_trust_file
p = load_profile_file(EXAMPLES_DIR / "om" / "facts.yaml")
t = load_trust_file(EXAMPLES_DIR / "om" / "trust.yaml")
text, _ = build_brief(p, t, "rahul", "dm-om-rahul-sat",
    Quoted("something fun Sunday evening, not pricey"),
    (date(2026, 11, 8), date(2026, 11, 9)))
Path("tests/data/brief-om-rahul.md").write_text(text, encoding="utf-8")
'
```

### Deviations

- **Neutral command examples.** The phase/PLAN samples use `"Bowling + dinner"` and `"Smaaash, Indiranagar"`. Those strings contain two of Om's facts above the friend level (`neighbourhood: Indiranagar`, and `bowling` case-insensitively from `interests`), so a friend- or acquaintance-level brief would leak a fact through an example. The examples now use `"Dinner and a walk"` at `"The Park, MG Road"`; phase 09 syntax is unchanged and every example is parsed by a test. A test now fails if any fact value above the room level appears anywhere in the brief, at acquaintance, friend and close.
- **`build_brief` is pure; `write_brief` records.** The phase names `build_brief`'s signature and separately requires every brief to be logged. Keeping rendering and recording apart lets tests and snapshots render without touching a ledger, while phase 13b/14 call `write_brief` as the one recording path.
- **One extra `calendar` ledger entry.** `record_brief` is fact-level, but the brief also discloses busy blocks. `write_brief` adds one `calendar` entry holding the policy-filtered blocks (titles included only where the level allows), matching the `calendar` field name phase 11's `free` handler uses. `disclosed_facts` remains facts-only, so the equivalence test is unaffected.
- `date_range` is two inclusive dates rather than datetimes, matching the `free` command; `build_brief` still uses `datetime` boundaries internally for `busy`.
- The brief uses `trust.level_for(friend)` as the room level. That is correct only for the one-to-one DM this phase serves; phase 14 must compute `policy.room_level` from Switch membership first, as Rule 1 requires.

### Blocked: one ask for Om

Om: dictate the prose blocks in `templates/envoy-brief.md.j2` with Wispr (the six `{# DRAFT: … #}` blocks), then regenerate the snapshot with the command above and commit. Everything else in phase 12 is done and tested.

### No-envoy decision, 2026-11-05

PLAN.md dropped envoys and swapped main agents (Om → Hermes, Rahul → a managed Codex
`rahul-agent`). This phase's output is repurposed, unchanged in code, as the **share card**
each gate privately hands its own main agent — see the reworded Goal above. No task or test
in this phase needed to change: `build_brief`/`write_brief` already produce exactly that text;
only who consumes it, and how, changes (phase 14 hands it to a main agent instead of an
`update_agent_detail` call on a per-conversation envoy).

### Both on Hermes, on Discord — 2026-11-05

The managed Codex `rahul-agent` above is dropped the same day: both Om's and Rahul's main
agent are now their own Hermes profile (`om-hermes`, `rahul-hermes`), on Discord. Nothing in
this phase changes again — the share card is handed to "the owner's own main agent" either way,
and that's now Hermes on both sides rather than Hermes on one side and a managed Codex agent on
the other. The rendered Om→Rahul/Om→Priya briefs in this Log are unaffected.
