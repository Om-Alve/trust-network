---
id: "14"
title: DM rooms between main agents
status: todo
priority: P0
owner: agent
depends_on: ["11", "12"]   # was 13/13b (envoy lifecycle), dropped with the no-envoy decision
plan_refs: ["§2 Rooms (conn-*, dm-*, rahul-home)", "§4 Scene 1 steps 1–10", "§8 check 7"]
target: Nov 6 afternoon
---

# 14 · DM rooms between main agents

> Repurposed, 2026-11-05: no envoys. Om tells Hermes (`om-hermes`, via `tn mcp`); Rahul talks to
> his own managed Codex agent (`rahul-agent`, on `rahul-vm`). Both are long-lived main agents,
> not per-conversation envoys — this phase invites the *existing* agent into a DM room and hands
> it a private share card (phase 12's brief, repurposed), rather than creating/briefing a fresh
> one each time.

## Goal
Om tells Hermes "…"; `om-gate` sets up a DM room, invites `om-hermes` and asks `rahul-gate` to
join through the connection room; `rahul-gate` invites `rahul-agent` and hands it its own share
card. The two main agents plan directly in plain language.

## Tasks
- [ ] Connection rooms: `conn-<a>-<b>` (sorted names), agent-only, members = the two gates. Created on first contact by whichever gate needs it; looked up by name afterwards.
- [ ] Owner command `dm <friend> "<goal>"` (from Om, or from Hermes on his behalf via `tn mcp`'s `dm` tool):
  - check the friend is on the trust list;
  - create `dm-<a>-<b>-<slug>` agent-only (slug from the goal's day/keyword, e.g. `sun`; add `-2` if taken);
  - invite the owner's own main agent (`om-hermes`) to the room;
  - privately hand it a share card (phase 12's `write_brief`, posted to the owner's home room or delivered over `tn mcp` — not into the shared DM room);
  - post `@<friend>-gate join-dm <room> "<goal>"` in the connection room;
  - post "Planning with Rahul in <room>" to the home room/Hermes inbox.
- [ ] Gate-to-gate `join-dm`: accept only in the matching connection room and only from the friend's gate (owner checked via Switch); join the room (invite or `connect_to_room`, per check 7); invite the owner's own main agent (`rahul-agent`) at **its own** trust level for the requester; hand it its own share card privately; relay "Om's agent is planning <goal> with you" to `rahul-home`.
- [ ] Both gates sit in the DM room to answer `free`/`ask` and watch turns (a turn/time-limited `ConversationWatch`, same limits as the old phase 13 design — 12 turns or 10 minutes, then a summary and `archive_room`).
- [ ] **New code surface needed here, not in phase 17/18:** unlike the dropped envoy lifecycle, there is no "create once, brief, invite" call for a long-lived main agent — just `invite_agent_to_room` for `om-hermes`/`rahul-agent` plus the private share-card handoff. `rahul-agent` itself must already exist as a managed Codex agent on `rahul-vm`, which this repo has no template for yet (phase 16 builds it, analogous to `templates/home.template.yaml`). Until phase 17/18 give Hermes `dm_read`/`dm_post` (phase 17) and `rahul-agent` is live, test and demo this phase with `tn --as om` / `tn --as rahul` CLI stand-ins that can read and post into a DM room directly.
- [ ] Offline test with `FakeSwitch`: full setup flow creates exactly one conn room and one DM room with four members (two gates, two main agents); a `join-dm` from a non-friend agent is ignored; `rahul-agent`'s share card is at Rahul's level for Om (close), independent of what Om's side can see.

## Done when
- [ ] `make check` passes.
- [ ] Live (both gates may run on the laptop for now): Om's request to Hermes produces `dm-om-rahul-<slug>`; `om-hermes` and `rahul-agent` (or their CLI stand-ins) exchange at least 4 messages in plain language, visible in Switch Console. Transcript excerpt in *Log*.
- [ ] Room strategy matches the decision from check 7 (noted in *Log*).

## Commit
`phase 14: connection rooms, dm setup and direct main-agent conversations`

## Log
<!-- evidence, deviations, notes -->

### Day-0 decision, 2026-11-05

Phase 04 room strategy: internal_only=True rooms with explicit cross-owner invitations work. Internal rooms remain visible in Console. Om/admin can also read Rahul private gifts, so gifts use courtesy seals. Phase 13b supplies the envoys. Do not depend on archive to reject writes. See docs/day0.md for evidence.

### No-envoy decision and main-agent swap, 2026-11-05

PLAN.md dropped envoys (main agents now talk directly in the DM room) and swapped main
agents: Om's is Hermes (`om-hermes`, via `tn mcp`), Rahul's is a managed Codex agent
(`rahul-agent`) on `rahul-vm`. `depends_on` changed from phase 13/13b to 11 (gate runtime) and
12 (share card, repurposed from the envoy brief) — the old envoy-lifecycle dependency no
longer applies. Two things this phase needs that don't exist yet, flagged for whoever
implements it: (1) `tn mcp` needs `dm_read`/`dm_post` tools (phase 17) before Hermes can carry
the plain-language side of the conversation; (2) there is no managed-agent template for
`rahul-agent`/`rahul-home` yet (phase 16) — `om-agent`'s `templates/home.template.yaml` is the
closest precedent but targets a Discord channel, not an agent-only Switch room. Until both
exist, build and demo this phase against `tn --as om`/`tn --as rahul` CLI stand-ins.
