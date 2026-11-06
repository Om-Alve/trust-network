---
id: "27"
title: Scenario hardening — many end-to-end scenarios, refined by Codex and DeepSeek
status: in-progress
priority: P1
owner: agent
depends_on: ["26"]
plan_refs: ["§3 Rules and commands", "§8 Security"]
target: Nov 6 evening
---

# 27 · Scenario hardening

## Goal
Exercise the whole system end to end in many scenarios (happy paths, refusals, races,
hostile peers, odd input), fix what breaks, and leave each scenario as a repeatable test.
Added 2026-11-06 at Om's request: "have Codex and OpenCode Go DeepSeek work on everything in
the codebase … refine it as much as possible."

Two areas, worked in parallel on separate branches, then merged:
- **A (Codex, gpt-6.1-sol):** planning rooms and consent: `dm`/`join-dm`, share cards, the
  handshake, `propose`/`answer`/`consent`, `ask-owner`, speak-first, room limits and archive,
  `RoomPool`, `PROTOCOL.md` §7a/§7b.
- **B (OpenCode, DeepSeek v4.1 flash):** facts and trust levels (`ask`, `free`, `view-as`,
  overreach notes, ledger), gifts and claims, ask-around, the `tn` CLI and `tn mcp` tools,
  `tn wake`, `PROTOCOL.md` §7c–§7e.

## Tasks
- [ ] A: scenarios written down (failure modes first), run in-process on `FakeSwitch` with the
  real gate code, bugs fixed, `PROTOCOL.md` kept true.
- [ ] B: the same for its area.
- [ ] Merged; live re-check of Scene 1 on the real Switch.

## Done when
- [ ] `make check` passes on the merged branch.
- [ ] Every scenario in both lists has a test or a written reason it can't have one.
- [ ] Scene 1 still passes live after the merge.

## Commit
`phase 27: <item>`

## Log
### A

Scenario inventory and failure modes, before implementation:
- Three example people, private share cards, hello both ways, both votes and
  confirmation: cross-room routing or disclosure to the wrong friend.
- Decline P1 then P2: declined room incorrectly closes to further proposals.
- Two rooms with the same friend and with different friends, both using P1:
  person-global IDs silently collide, or a yes applies to the wrong room.
- Duplicate/late answer and consent: repeated documents or changed votes.
- Wrong fingerprint, room, sender, and consent after limit archive: forged
  votes or a closed plan confirming. Final confirmation relays must still land.
- Proposal before friend speaks, friend agent proposing/answering to our gate,
  own agent answering in direct mode: unilateral or unauthorized consent.
- Ask-owner answered twice: duplicate disclosure or rebinding a question.
- Missing hello, old major, restart/re-hello: incompatible peer accepted or
  stale state blocks a compatible peer.
- Restart mid-plan: lost votes, questions, limits or archive guards.
- Bad time, past start, huge duration, quotes and Unicode title: crash,
  unusable plan or fingerprint changed on forwarding.
- Message/time limits: dispatch after closure or restart resets limits.
- RoomPool beyond MAX_ANCHORS and failed stream: connection exhaustion,
  newest rooms starved, duplicate events or failed recovery.


Implementation evidence:
- Added eight grouped FakeSwitch flows in `tests/planning_flows.py`, driven by
  `tests/test_planning_scenarios.py`. The same flows power the artifact runner.
- Failing-before run: 4 failed, 4 passed. ID collisions and unauthorized proposals
  had no refusal message; huge duration raised `OverflowError: Python int too
  large to convert to C int`; restart lost the room watch with `KeyError`.
- Follow-up failure: Rahul's vote was recorded from home after limit archive.
- Fixed silent ID collisions and unauthorized planning commands; handshake
  failures, invalid relays, repeated votes and completed references explain refusal.
- Fixed huge-duration overflow at parsing; past proposals are refused using the
  gate's injectable clock. Unicode card fingerprints survive forwarding.
- Saved room watches atomically with private permissions; restart restores turn
  counts, deadlines and closure. Home answers cannot vote into closed rooms.
- Existing real flows already covered missing/incompatible hello and basic room
  limits. New flows compose these with restart, re-hello and late consent.
- RoomPool cap and failed-stream recovery already worked; no production change.

Deviations and limits:
- No live checks, processes, pushes or area B work. Phase remains in progress for
  area B, merge and the separately owned live check.
- IDs remain person-global as designed. Gates cannot atomically reserve an ID
  across peers; a receiving-side collision may leave a proposal only on the
  opening side. Refusals and share cards now explain choosing a fresh ID on both.
- Persistence covers completed event dispatch across restart. Crash recovery
  between a state write and transport side effects remains outside this phase.

### B
