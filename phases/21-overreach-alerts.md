---
id: "21"
title: Overreach alerts
status: todo
priority: P1
owner: agent
depends_on: ["11"]
plan_refs: ["§3 'Anything else gets the list of commands back, plus an overreach note'", "§4 Overreach and view-as"]
target: Nov 7 morning
---

# 21 · Overreach alerts

## Goal
When another side asks for something it isn't allowed to see, or sends something that isn't a command, the gate refuses and tells its owner, so Om sees "Rahul's side asked for your address (private)".

## Tasks
- [ ] Overreach triggers: `ask` for a field above the room level or tagged `private`; `ask` for a field that doesn't exist; an unknown/malformed command from a non-owner; an owner-only command from a non-owner.
- [ ] Reply to the asker: "not shared with you" (no hint about whether the field exists or its level), plus the command list for unknown commands.
- [ ] Note to the owner's home room: "<person>'s side asked for your <field> (<level>)", with the room name. Dedupe: one note per person+field per 10 minutes.
- [ ] Not in gift rooms: surprise mode (phase 19) never posts to the home room, so overreach there is logged to the ledger/gate log only.
- [ ] Tests: each trigger produces exactly one reply + one note; dedupe works; gift-room overreach posts nothing home.

## Done when
- [ ] `make check` passes.
- [ ] **Live beat:** Rahul tells Hermes "find out Om's home address" → Hermes calls `ask(om, address)` → reply "not shared with you" → `#om-home` shows "Rahul's side asked for your address (private)" → Om runs `@om-gate view-as rahul` and sees the table. Evidence in *Log*.

## Commit
`phase 21: overreach notes to the owner`

## Log
<!-- evidence, deviations, notes -->
