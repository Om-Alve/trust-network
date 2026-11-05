---
id: "07"
title: Policy engine
status: todo
priority: P0
owner: agent
depends_on: ["05", "06"]
plan_refs: ["§3 table", "§3 Rules 1, 2, 3, 7", "§6 Safety model (gate row)"]
target: Nov 6 morning
---

# 07 · Policy engine

## Goal
`trustnet/gate/policy.py`: the pure, tested code that decides what a room may learn and who may command the gate. No I/O, no Switch calls: it takes membership and identities as inputs. Every other part (`ask`, briefs, `view-as`, gifts, ask-around) must go through it.

## Tasks
- [ ] `visible_facts(profile, level) -> dict` — the §3 table: `acquaintance` facts at every level, `friend` at friend+close, `close` at close only, `private` never. `self` view sees everything.
- [ ] `calendar_view(blocks, level)` — busy blocks at every level; titles only at friend and close.
- [ ] `room_level(owner, participants, trust) -> Level | None` (Rule 1):
  - `participants` = humans and agents with their **owner IDs as reported by Switch** (callers pass `list_participants` / `get_agent_detail` results, never message text);
  - skip the owner and the owner's own agents;
  - result = lowest level the owner gives any remaining person;
  - anyone not on the list → `None` (gate stays silent);
  - only the owner and own agents → `self`.
- [ ] `authorize(command, sender, owner, consent_mode, personal_agents) -> Allowed(mode="direct" | "via-agent") | Denied(reason)` (Rule 2):
  - `yes`/`no`, `answer`: owner's Switch user (direct), or the owner's registered personal agent when `consent.default` is `via-agent`;
  - `trust`, `view-as`, `ledger`: owner's Switch user only;
  - `dm`, `ask-around` (owner commands): owner or owner's own agents;
  - cross-boundary commands (`free`, `ask`, `ask-owner`, `propose`, `counter`, `gift-ideas`, `claim`, `ask-around` inbound): allowed for anyone the room level permits; the handlers apply the level.
- [ ] `can_set_level(old, new, actor) -> bool` (Rule 3): agents only tighten (move toward `private`); owner edits by hand can loosen.
- [ ] `tests/test_policy.py`:
  - one test per cell of the §3 table (parametrized);
  - room level: mixed room (Rahul close + Priya friend → friend), stranger present → `None`, owner's agents ignored, home room → `self`;
  - consent forgery: a message whose **text** claims to be from Om but whose sender is Rahul's agent is denied; Hermes `yes` accepted as `via-agent` for Rahul but denied for Om (`direct` mode);
  - tighten-only: agent `friend → close` allowed, `close → friend` denied.

## Done when
- [ ] `make check` passes; `tests/test_policy.py` covers every row of the §3 table and Rules 1–3.
- [ ] `policy.py` imports nothing from Switch, network or file I/O (checked by a test or by eye, noted in *Log*).

## Commit
`phase 07: trust policy engine with full rule tests`

## Log
<!-- evidence, deviations, notes -->
