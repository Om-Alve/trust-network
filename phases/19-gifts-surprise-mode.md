---
id: "19"
title: Gift rooms and surprise mode → Scene 2
status: todo
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
> triggers it through his own Codex agent (`rahul-agent`, via `tn --as rahul gift-ideas …` in
> `rahul-home`), not through Hermes (Hermes is Om's agent now).

## Tasks
- [ ] Asker side (`gift_ideas` from `tn mcp`/CLI): the asker's gate creates `gift-<asker>-<for>-<slug>` as agent-only **and** private (`read_visibility`), members = asker's gate + recipient's gate only; sends `@<for>-gate gift-ideas <occasion> <date> budget<=N`.
- [ ] `trustnet/gate/surprise.py` on the recipient side, in `gift-*` rooms:
  - answer from stored facts only, at the room level (wishlist with prices and `taken` flags at close; interests at friend; sizes at close); filter by budget, but list over-budget items as "(over budget)";
  - **never** ask the owner and **never** relay anything to the home room;
  - ledger entries with `sealed_until = occasion date + 1 day`.
- [ ] `claim "<item>"`: store in `<data dir>/claims.json` with claimer and `reveal_after`; reply "claimed". Claims are visible to other askers as `taken`, and hidden from the owner's own views (`tn fact get wishlist`, `view-as`, gate replies in the home room) until `reveal_after`.
- [ ] `owner_view` in the ledger shows "1 sealed entry, opens Nov 21".
- [ ] Archive the gift room after the claim (or after 10 minutes).
- [ ] `tests/test_surprise.py`: no message to the home room during the whole flow (assert on FakeSwitch); claim hidden from owner but shown to Priya's ask as taken; seal opens on the right date; Om (or Om's agent) can't read the gift room (FakeSwitch visibility).

## Done when
- [ ] `make check` passes.
- [ ] **Scene 2 live:** Rahul tells his Codex agent (`rahul-agent`, in `rahul-home`) for ideas under ₹3k → gets Catan Seafarers (≈₹2,500), Hario V60 (≈₹2,000), Kindle (over budget), interests, size M → claims Catan → Om's home surface (Hermes/`#om-home`) shows nothing → `@om-gate ledger` shows "1 sealed entry, opens Nov 21" → Om's wishlist still shows Catan. Optional: Priya's ask shows "Catan Seafarers: taken". Evidence in *Log*.
- [ ] Check 10's second half holds live: Om can't open the gift room in Console (or the courtesy-seal fallback is noted).

## Commit
`phase 19: gift rooms, sealed ledger entries and hidden claims`

## Log
<!-- evidence, deviations, notes -->

### No-envoy decision and main-agent swap, 2026-11-05

No mechanics changed — gift rooms were always gate-to-gate, never routed through an envoy.
Updated the demo narrative only: Rahul now triggers `gift_ideas`/`claim` through his own Codex
agent (`rahul-agent`) instead of Hermes, since Hermes is Om's agent after the swap.
