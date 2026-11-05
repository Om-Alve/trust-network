---
id: "20"
title: Ask around → Scene 3
status: todo
priority: P1
owner: agent
depends_on: ["15"]
plan_refs: ["§4 Scene 3", "§3 commands `ask-around`"]
target: Nov 7 morning
---

# 20 · Ask around → Scene 3

## Goal
Om asks all his friends at once ("anyone have a tent for Nov 14–16?"). Each friend's gate answers from facts if it can, otherwise asks its person, and Om gets one summary.

## Tasks
- [ ] Owner command `ask-around "<question>"` (≤140 chars): post `@<friend>-gate ask-around Ak "<question>"` into every connection room the owner has (creating conn rooms for listed friends if missing). Gate-to-gate only; no envoys involved.
- [ ] Receiving gate:
  - match the question against `has` and `recommends` facts **visible at the room level** (simple keyword/singular-plural match; no LLM);
  - a match → answer at once ("Priya: 2-person tent");
  - no match → relay to its person as a quoted question (home room / `inbox`); the person's `answer Ak "…"` goes back to the asker's gate;
  - ledger entry for whatever is disclosed.
- [ ] Asker gate collects answers for up to N minutes and posts one summary in the home room as they arrive: "Priya can lend a 2-person tent. Rahul can't."
- [ ] Same flow covers recommendations ("a good dentist nearby?" → `recommends.dentist`).
- [ ] Offline tests: Priya answers from facts without asking; Rahul's side asks its person; a close-level `has` fact is not used in a friend-level conn room.

## Done when
- [ ] `make check` passes.
- [ ] **Scene 3 live:** Om's tent request in `#om-home` → Priya's gate answers instantly → Rahul is asked on Telegram (or `tn --as rahul inbox`) and says "no, sorry" → `#om-home` shows the combined summary. Evidence in *Log*.

## Commit
`phase 20: ask-around across connection rooms (scene 3)`

## Log
<!-- evidence, deviations, notes -->
