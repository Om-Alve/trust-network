---
id: "14"
title: DM rooms and envoy conversations
status: todo
priority: P0
owner: agent
depends_on: ["13"]   # or 13b, whichever phase 04 chose
plan_refs: ["§2 Rooms (conn-*, dm-*)", "§4 Scene 1 steps 1–5", "§8 check 7"]
target: Nov 6 afternoon
---

# 14 · DM rooms and envoy conversations

## Goal
Om says `@om-gate dm rahul "…"`; both gates set up a DM room, brief and invite their own envoys at each other's level, and the envoys plan in plain language.

## Tasks
- [ ] Connection rooms: `conn-<a>-<b>` (sorted names), agent-only, members = the two gates. Created on first contact by whichever gate needs it; looked up by name afterwards.
- [ ] Owner command `dm <friend> "<goal>"` (from Om or Om's own agent):
  - check the friend is on the trust list;
  - create `dm-<a>-<b>-<slug>` agent-only (slug from the goal's day/keyword, e.g. `sun`; add `-2` if taken);
  - brief + invite own envoy (phase 13/13b);
  - post `@<friend>-gate join-dm <room> "<goal>"` in the connection room;
  - post "Planning with Rahul in <room>" to the home room.
- [ ] Gate-to-gate `join-dm`: accept only in the matching connection room and only from the friend's gate (owner checked via Switch); join the room (invite or `connect_to_room`, per check 7); brief + invite own envoy at **its own** trust level for the requester; relay "Om's agent is planning <goal> with you" to its home room (for Hermes `inbox`).
- [ ] Both gates sit in the DM room to answer `free`/`ask` and watch turns (phase 13 `ConversationWatch`).
- [ ] Offline test with `FakeSwitch`: full setup flow creates exactly one conn room and one DM room with four members (two gates, two envoys); a `join-dm` from a non-friend agent is ignored; Rahul's envoy's brief is at Rahul's level for Om (close), not Om's level for Rahul.

## Done when
- [ ] `make check` passes.
- [ ] Live (both gates may run on the laptop for now): Om's request in `#om-home` produces `dm-om-rahul-<slug>`; the two envoys exchange at least 4 messages using only briefed facts, visible in Switch Console. Transcript excerpt in *Log*.
- [ ] Room strategy matches the decision from check 7 (noted in *Log*).

## Commit
`phase 14: connection rooms, dm setup and envoy conversations`

## Log
<!-- evidence, deviations, notes -->
