---
id: "19"
title: Gift rooms and surprise mode → Scene 2
status: done
priority: P1
owner: agent
depends_on: ["15", "17"]
plan_refs: ["§3 Rule 5", "§0 Gift privacy", "§4 Scene 2", "§2 Rooms (gift-*)"]
target: Nov 7 morning
---

# 19 · Gift rooms and surprise mode → Scene 2

## Goal
Rahul can ask Om's gate for gift ideas and claim one, and Om learns nothing until after the occasion. Other askers see the item as taken. This flow is gate-to-gate only; main agents aren't party to it beyond triggering the request.

> Note, 2026-11-05: this phase was never routed through envoys, and the no-envoy decision and
> main-agent swap don't change its mechanics — only who triggers it in the demo. Rahul now
> triggers it through his own Hermes (`rahul-hermes`, via `gift_ideas` over `tn mcp`, or
> `tn --as rahul gift-ideas …` as the terminal stand-in), on Discord.

## Tasks
- [x] Asker side (`gift_ideas` from `tn mcp`/CLI): the asker's gate creates `gift-<asker>-<for>-<slug>` as agent-only **and** private (`read_visibility`), members = asker's gate + recipient's gate only; sends `@<for>-gate gift-ideas <occasion> <date> budget<=N`.
- [x] `trustnet/gate/surprise.py` on the recipient side, in `gift-*` rooms:
  - answer from stored facts only, at the room level (wishlist with prices and `taken` flags at close; interests at friend; sizes at close); filter by budget, but list over-budget items as "(over budget)";
  - **never** ask the owner and **never** relay anything to the home room;
  - ledger entries with `sealed_until = occasion date + 1 day`.
- [x] `claim "<item>"`: store in `<data dir>/claims.json` with claimer and `reveal_after`; reply "claimed". Claims are visible to other askers as `taken`, and hidden from the owner's own views (`tn fact get wishlist`, `view-as`, gate replies in the home room) until `reveal_after`.
- [x] `owner_view` in the ledger shows "1 sealed entry, opens Nov 21".
- [x] Archive the gift room after the claim (or after 10 minutes).
- [x] Gift behavior E2E in `tests/test_mcp_e2e.py`: no message to the home room during the whole flow (assert on FakeSwitch); claim hidden from owner but shown to Priya's ask as taken; seal opens on the right date; Om (or Om's agent) can't read the gift room (FakeSwitch visibility).

## Done when
- [x] `make check` passes.
- [x] **Scene 2 live with authorized CLI Hermes stand-ins:** Rahul asks for ideas under ₹3k → gets Catan Seafarers (≈₹2,500), Hario V60 (≈₹2,000), Kindle (over budget), interests, size M → claims Catan → Om's home surface (his own Hermes/`#om-home`) shows nothing → `@om-gate ledger` shows "1 sealed entry, opens Nov 21" → Om's wishlist hides Catan until Nov 21. Optional: Priya's ask shows "Catan Seafarers: taken". Evidence in *Log*.
- [x] Check 10's second half holds live: Om can't open the gift room in Console (or the courtesy-seal fallback is noted).

## Commit
`phase 19: gift rooms, sealed ledger entries and hidden claims`

## Log
<!-- evidence, deviations, notes -->

### No-envoy decision and main-agent swap, 2026-11-05

No mechanics changed — gift rooms were always gate-to-gate, never routed through an envoy.
Updated the demo narrative only: Rahul now triggers `gift_ideas`/`claim` through his own Codex
agent (`rahul-agent`) instead of Hermes, since Hermes is Om's agent after the swap.

### Both on Hermes, on Discord — 2026-11-05

Superseded the above the same day: `rahul-agent` is dropped. Rahul triggers `gift_ideas`/`claim`
through his own Hermes (`rahul-hermes`), on Discord, same as Om would on his side. Mechanics are
still unchanged — gift rooms remain gate-to-gate only.

### Implementation and pending live verification, 2026-11-05

Gift requests pass from the asker's Hermes through its home gate to a private,
agent-only gift room. The recipient uses stored facts at the freshly computed
room level, returns available suggestions within budget, and separately labels
taken and over-budget items. Gift rooms intercept all other commands, including
owner questions, and never post home on the recipient side. One disclosure entry
per session is sealed until the occasion plus one day. Claims persist in
`claims.json`; sessions persist in `gift-sessions.json`. Owner fact-get, view-as
and home fact replies hide active claimed wishlist items. Other gift askers see
taken markers at the wishlist's permitted level. Rooms archive after successful
claim or ten minutes. Demo reset already cleared claims; it now clears sessions.

Validation before deployment: `make check`; live artifact and final state follow.
The VM deployment script requires committed source, so the initial commit precedes
the live run and will be amended with its evidence. Workspace administrators can
read private rooms, as established in docs/day0.md check 10. The seal is a courtesy.


### Final evidence, 2026-11-05

`make check` passes: 96 files formatted, lint clean, 460 tests passed. Gift behavior
is verified in the existing real-stdio MCP E2E rather than new isolated unit tests.
It exercises both gate runtimes through the Switch protocol adapter, verifies private
room visibility against Om's Hermes, observes successful claim and room archival,
and checks the recipient home receives no new message.

Live repeat: `uv run python -m scripts.e2e_scene2`.
Artifact: `data/scene2-1793888795635001000/artifact.json`.
Rahul's actual VM gate created the room and relayed responses. The laptop ran
Om's gate against copied disposable profiles. No local Rahul gate was started.
`scripts/vm_up.sh` deployed committed source and reported `active`; the live
script checked `rahul-gate.service` active before running. The service remains up.

The artifact contains CLI calls, available Catan ₹2500 and V60 ₹2000, separately
labelled Kindle ₹14000 over budget, size M and permitted interests, the successful
claim, Om's filtered fact-get/view-as, identical before/after Om home transcripts,
the archived gift-room detail and transcript, the exact sealed line on Nov 20,
and its opened rendering on simulated Nov 21 using the real persisted ledger.
It also proves Priya at friend receives no wishlist or sizes, and at close sees
Catan taken and only V60 available. Simulated date affects ledger rendering only;
no system clock or VM clock was changed. Home transcript equality also proves
nothing new could reach Om's home-based inbox from this flow.

The script retains the claims and raw ledger in the artifact before invoking the
actual demo reset clearing function against its disposable data directory. It
asserts both claims.json and gift-sessions.json are removed. Existing demo-reset
behavior is preserved. The phase-22 bootstrap replay script requires stopping the
VM gate and was not rerun because this task requires leaving that service running.

Deviations: UUID room suffixes avoid collisions. Over-budget items are separate
from suggestions. One sealed disclosure entry aggregates a gift response; claiming
updates claims.json without adding a second disclosure entry. Om's wishlist hides
claimed items, correcting the old contradictory Scene 2 line in PLAN.md. Actual
Discord/Hermes interaction remains phase 18; the requested CLI/MCP stand-ins supply
the Scene 2 implementation evidence. Workspace admins can read rooms; docs/day0.md
check 10's courtesy-seal fallback applies. Delivery is not a durable outbox: a crash
between writing state and publishing a response may require operator reconciliation.
