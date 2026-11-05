---
id: "15"
title: Ask-your-person and consent → Scene 1 via CLI
status: todo
priority: P0
owner: agent
depends_on: ["14", "10"]
plan_refs: ["§4 Scene 1 steps 6–10", "§3 Rules 2, 4", "§0 Consent", "§9 Nov 6 afternoon milestone"]
target: Nov 6 afternoon
---

# 15 · Ask-your-person and consent → Scene 1 via CLI

## Goal
Envoys can ask their own person a question, propose a plan, and nothing is committed until both people say yes. **Scene 1 runs end to end, with Rahul driven from the terminal** (`tn --as rahul`), before Hermes is involved.

## Tasks
- [ ] `ask-owner Qn "…"` (from the gate's own envoy, in a DM room only): relay to the home room as a quoted question with "reply `@om-gate answer Qn …`"; track open questions per room.
- [ ] `answer Qn "…"` (authorized per Rule 2, `direct` or `via-agent`): post the answer into the DM room for the envoy; ledger entry.
- [ ] `propose Pn …` (validated fixed form): store as pending per room; post the card in the home room ("P1: Sun 21:00, 2h, Bowling + dinner @ Smaaash, Indiranagar · reply `yes P1` / `no P1`").
- [ ] `yes Pn` / `no Pn` → gate sends `@<friend-gate> consent Pn yes direct|via-agent` in the DM room; when both sides have said yes, both gates post the confirmation in their home rooms: "✅ P1: Sun 21:00, Bowling + dinner @ Smaaash · Om ✅ · Rahul ✅ via Hermes". A `no` from either side posts "❌ P1 declined" and lets envoys continue.
- [ ] After confirmation: write the plan as a room document (`plan` record) if available, archive the DM room, ledger entries on both sides.
- [ ] Personal-agent core `trustnet/tn/personal.py` (shared by the CLI now and `tn mcp` in phase 17): connects as `<person>-hermes`, `inbox()` returns unread messages from the person's home room (questions, proposals, notices) with a persistent cursor in the data dir, `answer(id, text)`.
- [ ] CLI: `tn --as rahul inbox`, `tn --as rahul answer Q1 "yes"`, `tn --as rahul answer P1 yes`, `tn --as om dm rahul "…"` (convenience).
- [ ] Main agents add the event: `tn --as om cal add …` (Om's Codex agent is told this by `SKILL.md`).
- [ ] Offline tests: forged consent (text says "Om says yes") denied; proposal never confirmed with one yes; `via-agent` label shown only when it was via the agent; questions over 140 chars rejected.

## Done when
- [ ] `make check` passes.
- [ ] **Scene 1 live without Hermes:** Om's request in `#om-home` → envoys plan → Rahul's envoy asks Q1 about budget → `tn --as rahul inbox` shows it → `tn --as rahul answer Q1 "yes"` → P1 proposed → Om types `@om-gate yes P1` → `tn --as rahul answer P1 yes` → both home rooms show the ✅ line → both calendars contain P1 → DM room archived → both ledgers list what was shared. Step-by-step evidence in *Log*.

## Commit
`phase 15: ask-owner, proposals and two-sided consent (scene 1 via CLI)`

## Log
<!-- evidence, deviations, notes -->
