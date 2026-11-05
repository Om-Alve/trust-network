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
A main agent can ask its own person a question, propose a plan, and nothing is committed until both people say yes. **Scene 1 runs end to end, with both Om and Rahul driven from the terminal** (`tn --as om`, `tn --as rahul`), before either Hermes exists.

> Repurposed, 2026-11-05 (no-envoy decision, then both people on Hermes via Discord): `ask-owner`
> is still here as a generic mechanism, but in the new design a main agent that needs something
> from its own person usually just asks it directly on its own channel — each person's own
> Hermes, on Discord — rather than relaying through the gate; the gate relay matters most when
> the agent has no other path to its person. `propose`/`yes`/`no` are unchanged: proposals and
> consent always go through the gates.

## Tasks
- [ ] `ask-owner Qn "…"` (from the gate's own main agent, in a DM room or elsewhere it's a member): relay to the home room/inbox as a quoted question with "reply `@<gate> answer Qn …`"; track open questions per room. Kept as a generic fallback; Scene 1's budget question in the new design is answered directly by Rahul to his own Hermes on Discord, without going through this relay.
- [ ] `answer Qn "…"` (authorized per Rule 2, `direct` or `via-agent`): post the answer into the DM room for the main agent; ledger entry.
- [ ] `propose Pn …` (validated fixed form): store as pending per room; post the card in the home room ("P1: Sun 21:00, 2h, Bowling + dinner @ Smaaash, Indiranagar · reply `yes P1` / `no P1`").
- [ ] `yes Pn` / `no Pn` → gate sends `@<friend-gate> consent Pn yes direct|via-agent` in the DM room; when both sides have said yes, both gates post the confirmation in their home rooms: "✅ P1: Sun 21:00, Bowling + dinner @ Smaaash · Om ✅ via Hermes · Rahul ✅". A `no` from either side posts "❌ P1 declined" and lets the agents continue.
- [ ] After confirmation: write the plan as a room document (`plan` record) if available, archive the DM room, ledger entries on both sides.
- [ ] Personal-agent core `trustnet/tn/personal.py` (shared by the CLI now and `tn mcp` in phase 17, generic over which person it runs `--as`): connects as `<person>-hermes`, `inbox()` returns unread messages from the person's home room (questions, proposals, notices) with a persistent cursor in the data dir, `answer(id, text)`.
- [ ] CLI: `tn --as om inbox`, `tn --as om answer Q1 "yes"`, `tn --as om answer P1 yes`, `tn --as rahul dm om "…"` (convenience). Also needs a way to post plain-language text directly into a DM room (standing in for a main agent before phase 14's real agents exist) — see phase 14's Log for this gap.
- [ ] Main agents add the event: `tn --as rahul cal add …` / `tn --as om cal add …` as the terminal stand-ins for now; once Hermes exists on either side (phase 17), it calls the `tn mcp` `cal_add` tool instead, since Hermes has no shell. Both sides use the same `cal_add` tool, symmetrically, since neither side's real main agent is shell-capable.
- [ ] Offline tests: forged consent (text says "Om says yes") denied; proposal never confirmed with one yes; `via-agent` label shown only when it was via the agent; questions over 140 chars rejected.

## Done when
- [ ] `make check` passes.
- [ ] **Scene 1 live without Hermes or `rahul-agent`:** Om's request (via `tn --as om dm rahul "…"`) → main-agent stand-ins plan in the DM room → when Rahul's side needs Om's budget confirmation, `tn --as rahul` answers directly in the room (standing in for `rahul-agent` asking Rahul in `rahul-home`) → an agent proposes P1 through both gates → `tn --as om answer P1 yes` (standing in for Om telling Hermes "yes") → `tn --as rahul answer P1 yes` (standing in for Rahul saying yes directly) → both home rooms show the ✅ line → both calendars contain P1 → DM room archived → both ledgers list what was shared. Step-by-step evidence in *Log*.

## Commit
`phase 15: ask-owner, proposals and two-sided consent (scene 1 via CLI)`

## Log
<!-- evidence, deviations, notes -->

### No-envoy decision and main-agent swap, 2026-11-05

Reworded for the no-envoy design (main agents ask their own person directly where they can;
`ask-owner` stays as a generic relay) and the main-agent swap (Om ↔ Hermes, Rahul ↔
`rahul-agent`). No task here was actually built yet (`status: todo`), so this is a planning-only
change; the CLI task gained a note that it will also need a way to post plain text into a DM
room once phase 14 needs a stand-in for a main agent.

### Both on Hermes, on Discord — 2026-11-05

Superseded the main-agent swap above: Rahul's main agent is now his own Hermes, on Discord, not
a managed Codex `rahul-agent`. Reworded the `ask-owner` note and the "main agents add the event"
task so both sides end up symmetric — both eventually call `tn mcp`'s `cal_add` tool, since
neither main agent has a shell. Still `status: todo`; planning-only change.
