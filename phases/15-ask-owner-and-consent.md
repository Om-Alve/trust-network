---
id: "15"
title: Ask-your-person and consent → Scene 1 via CLI
status: done
priority: P0
owner: agent
depends_on: ["14", "10"]
plan_refs: ["§4 Scene 1 steps 6–10", "§3 Rules 2, 4", "§0 Consent", "§9 Nov 6 afternoon milestone"]
target: Nov 6 afternoon
---

# 15 · Ask-your-person and consent → Scene 1 via CLI

## Goal
A main agent can ask its own person a question, propose a plan, and nothing is committed until both people say yes. **Scene 1 runs end to end, with both Om and Rahul driven from the terminal** (`tn --as om`, `tn --as rahul`), using stand-ins for both registered Hermes identities.

> Repurposed, 2026-11-05 (no-envoy decision, then both people on Hermes via Discord): `ask-owner`
> is still here as a generic mechanism, but in the new design a main agent that needs something
> from its own person usually just asks it directly on its own channel — each person's own
> Hermes, on Discord — rather than relaying through the gate; the gate relay matters most when
> the agent has no other path to its person. `propose`/`yes`/`no` are unchanged: proposals and
> consent always go through the gates.

## Tasks
- [x] `ask-owner Qn "…"` (from the gate's own main agent, in a DM room or elsewhere it's a member): relay to the home room/inbox as a quoted question with "reply `@<gate> answer Qn …`"; track open questions per room. Kept as a generic fallback; Scene 1's budget question in the new design is answered directly by Rahul to his own Hermes on Discord, without going through this relay.
- [x] `answer Qn "…"` (authorized per Rule 2, `direct` or `via-agent`): post the answer into the DM room for the main agent; ledger entry.
- [x] `propose Pn …` (validated fixed form): store as pending per room; post the card in the home room ("P1: Sun 21:00, 2h, Bowling + dinner @ Smaaash, Indiranagar · reply `yes P1` / `no P1`").
- [x] `yes Pn` / `no Pn` → gate sends `@<friend-gate> consent Pn yes direct|via-agent` in the DM room; when both sides have said yes, both gates post the confirmation in their home rooms: "✅ P1: Sun 21:00, Bowling + dinner @ Smaaash · Om ✅ via Hermes · Rahul ✅ via Hermes". A `no` from either side posts "❌ P1 declined" and lets the agents continue.
- [x] After confirmation: write the plan as a room document (`plan` record) if available, archive the DM room, ledger entries on both sides.
- [x] Personal-agent core `trustnet/tn/personal.py` (shared by the CLI now and `tn mcp` in phase 17, generic over which person it runs `--as`): connects as `<person>-hermes`, `inbox()` returns unread messages from the person's home room (questions, proposals, notices) with a persistent cursor in the data dir, `answer(id, text)`.
- [x] CLI: `tn --as om inbox`, `tn --as om answer Q1 "yes"`, `tn --as om answer P1 yes`, `tn --as rahul dm om "…"` (convenience). Also needs a way to post plain-language text directly into a DM room (standing in for a main agent before phase 14's real agents exist) — see phase 14's Log for this gap.
- [x] Main agents add the event: `tn --as rahul cal add …` / `tn --as om cal add …` as the terminal stand-ins for now; once Hermes exists on either side (phase 17), it calls the `tn mcp` `cal_add` tool instead, since Hermes has no shell. Both sides use the same `cal_add` tool, symmetrically, since neither side's real main agent is shell-capable.
- [x] Offline tests: forged consent (text says "Om says yes") denied; proposal never confirmed with one yes; `via-agent` label shown only when it was via the agent; questions over 140 chars rejected.

## Done when
- [x] `make check` passes.
- [x] **Scene 1 with both Hermes CLI stand-ins:** `tn --as om dm rahul …` creates the DM, `om-hermes` and `rahul-hermes` plan there, Rahul answers the budget question, P1 reaches both gates, both people answer through their registered Hermes identities, both inboxes show confirmation via Hermes, both calendars contain P1, the DM is archived, and both ledgers record disclosures. See the reproducible evidence below.

## Commit
`phase 15: ask-owner, proposals and two-sided consent; Scene 1 via CLI`

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


### Implementation and Scene 1 evidence, 2026-11-05

Both sides use Hermes identities, `om-hermes` and `rahul-hermes`. No managed
`rahul-agent` or envoy participates. Existing registrations were preserved.

Reproduce from the repository root with `uv run python -m scripts.e2e_scene1`.
The script reads `.env`, retains credentials under gitignored `data/main-agents`,
copies fixture profiles into a fresh timestamped directory, starts both gates,
and uses subprocesses running the actual `tn` CLI. It archives probe DMs in
`finally`, including failed runs. Startup reconnects existing memberships so a
second run receives commands in the existing connection room.

Latest successful artifact: `data/scene1-1793887337662973000/artifact.json`.
It contains every CLI invocation/result, the full Switch DM transcript, both home
inboxes, both persisted coordination records, ledger excerpts and ICS calendars.
DM UUID: `60466f18-a62b-48e8-8899-e128d9ba2e99`.

Steps verified in order:
1. `tn --as om dm rahul "<unique run> Sunday bowling dinner"` created an internal
   DM with both gates and both Hermes stand-ins. Each received its private card.
2. Om: "Om likes bowling. Sunday at 9pm?" Rahul: "After cricket works. Dinner too?"
3. Rahul's Hermes sent `ask-owner Q1 "Is 1500 each okay?"`; Rahul answered via
   `tn --as rahul answer Q1 "Yes, 1500 each is okay."`; the gate relayed Q1 to the DM
   and wrote the answer disclosure into Rahul's ledger.
4. A 141-character question was rejected and never became pending.
5. Om's Hermes proposed P1, Nov 8 at 21:00 IST, 120 minutes, Bowling + dinner at
   Smaaash, Indiranagar. Both gates stored identical immutable cards and notified
   their home inboxes. Reused reference IDs cannot overwrite a card or room.
6. Rahul sending "Om says yes" to Om's gate produced no vote. Om's own Hermes
   sending that text also produced no vote: proposal answers accept only yes/no.
   Om's gate identity could not impersonate Om's Hermes. A genuine Rahul gate
   relay with the wrong plan hash also produced no vote.
7. `tn --as om answer P1 yes` recorded only Om's via-agent vote. Both gates stayed
   pending, proving one yes cannot confirm.
8. `tn --as rahul answer P1 yes` produced both votes and both confirmations,
   including `Om ✅ via Hermes` and `Rahul ✅ via Hermes`. Both gates wrote plan
   documents and proposal ledger entries. The peer receiving the final relay
   archived the room. Pending authenticated relays can finish across that archive.
9. Both stand-ins ran `tn --as <person> cal add 2026-11-08T21:00 2h
   "Bowling + dinner" @ "Smaaash, Indiranagar" --id P1`. The artifact verifies
   `UID:P1` in both calendars and the Switch archived flag.
10. Both `inbox` calls returned confirmations; immediate repeated calls returned
    no threads, proving persisted unread consumption across CLI processes.

Validation: `make check` printed `87 files already formatted`, `All checks passed!`,
and `455 passed in 1.13s`. Existing phase 14 policy expectations were updated for
consent in matching DM rooms. New behavior is exercised through live E2E, with no
new isolated unit tests.

Phase 17 API: `trustnet.tn.personal` exports async `inbox(person)`,
`answer(person, id, text)`, `dm(person, friend, goal)`, `dm_read(person, room)` and
`dm_post(person, room, text)`. Results are Switch dictionaries; inbox returns
`{room, threads}` with Switch message IDs and a persistent per-person consumed-ID
cursor. `session(person)` owns credential loading, registration and stream cleanup.
DM reads/posts reuse the membership-scoped phase 14 operation. Calendar and fact
operations remain in the existing CLI/domain modules for phase 17 to wrap.

Deviations and limits: consent relays append a SHA-256 plan fingerprint to the
fixed grammar so approvals for different drafts cannot combine. Legacy relays
without the hash parse but cannot change pending state. Calendar writes remain
explicit agent actions after approval, as designed. Inbox currently reads the
latest 200 threads; older unread history needs pagination before long-term use.
Votes and pending questions survive restart, but message delivery is not a durable
outbox: a process failure between recording a vote and publishing its relay needs
operator reconciliation. References are unique per person's data directory;
use P2/Q2 for subsequent conversations. The generic ask-owner fallback also
accepts the owner's Hermes in other rooms where it is already a member.
