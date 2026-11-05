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

> Note, 2026-11-05: ask-around was always gate-to-gate, never routed through an envoy or a main
> agent. After the main-agent swap, Om triggers this through Hermes (`ask_around` over `tn mcp`)
> instead of typing directly in Discord, and Rahul's gate relays its "I don't know" case to
> `rahul-home` (his Codex agent / Rahul directly) instead of to Hermes, since Hermes is Om's
> agent now.

## Tasks
- [ ] Owner command `ask-around "<question>"` (≤140 chars): post `@<friend>-gate ask-around Ak "<question>"` into every connection room the owner has (creating conn rooms for listed friends if missing). Gate-to-gate only; main agents aren't involved.
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
- [ ] **Scene 3 live:** Om's tent request, via Hermes on Telegram (or directly in `#om-home`) → Priya's gate answers instantly → Rahul is asked directly in `rahul-home` (or `tn --as rahul inbox`) and says "no, sorry" → Hermes tells Om the combined summary (or it shows in `#om-home`). Evidence in *Log*.

## Commit
`phase 20: ask-around across connection rooms (scene 3)`

## Log
<!-- evidence, deviations, notes -->

### No-envoy decision and main-agent swap, 2026-11-05

No mechanics changed — ask-around was always gate-to-gate. Updated the demo narrative: Om now
asks through Hermes, and Rahul now answers directly in `rahul-home` rather than via Hermes on
Telegram, following the Nov 5 main-agent swap.
