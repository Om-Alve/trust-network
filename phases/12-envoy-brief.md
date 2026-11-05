---
id: "12"
title: Envoy brief
status: todo
priority: P0
owner: agent + human
depends_on: ["07", "08"]
plan_refs: ["§3 Rule 7", "§3 Rule 6", "§5 envoy-brief.md.j2", "§12 Code with Wispr"]
target: Nov 6 afternoon
---

# 12 · Envoy brief

## Goal
The envoy's instructions are built from the same policy code that answers `ask`, so an envoy never knows more than the other side could ask the gate for (Rule 7).

## Tasks
- [ ] **[human]** Om dictates the prose of `templates/envoy-brief.md.j2` with Wispr (Code with Wispr requirement). The agent supplies the variable slots and edits only for structure.
- [ ] Template contents: the goal (quoted), the person's name and the friend's name, facts at the room level, busy blocks (and titles if allowed) for the relevant date range, and the rules: "only state what's here; if you need something else, send `@<gate> ask-owner Qn \"…\"`; you can't commit to anything; propose with `@<gate> propose …` and `@<friend-gate> propose …`; keep messages short; stop after agreement". Include exact command examples.
- [ ] `trustnet/gate/brief.py`: `build_brief(profile, trust, friend, room, goal, date_range) -> (text, disclosed_facts)` using `policy.visible_facts` and `policy.calendar_view`.
- [ ] Every brief written calls `ledger.record_brief` (phase 08).
- [ ] `tests/test_brief.py`:
  - brief for a friend-level room contains no close or private facts (search for each value string);
  - **equivalence**: the set of facts in the brief equals the set `ask` would return at that level;
  - the goal and other free text appear only in quoted form;
  - snapshot test of the rendered Om→Rahul brief (stored in `tests/data/`).

## Done when
- [ ] `make check` passes, including the equivalence test.
- [ ] The template text was dictated by Om (noted in *Log* for the Wispr submission).
- [ ] Rendered Om→Rahul and Om→Priya briefs are pasted in *Log* for a human read-through.

## Commit
`phase 12: level-filtered envoy brief and template`

## Log
<!-- evidence, deviations, notes -->
