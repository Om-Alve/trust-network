---
id: "07"
title: Policy engine
status: done
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
- [x] `visible_facts(profile, level) -> dict` — the §3 table: `acquaintance` facts at every level, `friend` at friend+close, `close` at close only, `private` never. `self` view sees everything.
- [x] `calendar_view(blocks, level)` — busy blocks at every level; titles only at friend and close.
- [x] `room_level(owner, participants, trust) -> Level | None` (Rule 1):
  - `participants` = humans and agents with their **owner IDs as reported by Switch** (callers pass `list_participants` / `get_agent_detail` results, never message text);
  - skip the owner and the owner's own agents;
  - result = lowest level the owner gives any remaining person;
  - anyone not on the list → `None` (gate stays silent);
  - only the owner and own agents → `self`.
- [x] `authorize(command, sender, owner, consent_mode, personal_agents) -> Allowed(mode="direct" | "via-agent") | Denied(reason)` (Rule 2):
  - `yes`/`no`, `answer`: owner's Switch user (direct), or the owner's registered personal agent when `consent.default` is `via-agent`;
  - `trust`, `view-as`, `ledger`: owner's Switch user only;
  - `dm`, `ask-around` (owner commands): owner or owner's own agents;
  - cross-boundary commands (`free`, `ask`, `ask-owner`, `propose`, `counter`, `gift-ideas`, `claim`, `ask-around` inbound): allowed for anyone the room level permits; the handlers apply the level.
- [x] `can_set_level(old, new, actor) -> bool` (Rule 3): agents only tighten (move toward `private`); owner edits by hand can loosen.
- [x] `tests/test_policy.py`:
  - one test per cell of the §3 table (parametrized);
  - room level: mixed room (Rahul close + Priya friend → friend), stranger present → `None`, owner's agents ignored, home room → `self`;
  - consent forgery: a message whose **text** claims to be from Om but whose sender is Rahul's agent is denied; Hermes `yes` accepted as `via-agent` for Rahul but denied for Om (`direct` mode);
  - tighten-only: agent `friend → close` allowed, `close → friend` denied.

## Done when
- [x] `make check` passes; `tests/test_policy.py` covers every row of the §3 table and Rules 1–3.
- [x] `policy.py` imports nothing from Switch, network or file I/O (checked by a test or by eye, noted in *Log*).

## Commit
`phase 07: trust policy engine with full rule tests`

## Log

### What was built

`trustnet/gate/policy.py` — pure, no I/O, no Switch import, no message text in any signature.

- **§3 table.** `visible_facts(profile, level) -> dict[str, Any]` returns fact values (deep copies) visible at a room level; `fact_is_visible(fact_level, level) -> bool` is the single-cell primitive phase 08's `view_as` needs to print ❌ rows. `self` sees every fact; `private` is rejected as a room level (`PolicyError`). `calendar_view(blocks, level) -> list[Block]` keeps every busy block at every level and strips titles at `acquaintance`; friend/close/self keep titles.
- **Rule 1.** `room_level(owner, participants, trust) -> Level | None`. Participants are `Identity` objects (`Identity.user(id)` / `Identity.agent(id, owner_id)`) built by the caller from `list_participants` + `get_agent_detail`. The owner and every agent whose `owner_id` is the owner are skipped; the result is the lowest level given to anyone left. An agent with no owner, anyone not on the trust list, or an id the trust list cannot hold (e.g. an mxid) returns `None`, so the gate stays silent. Only owner + own agents → `Level.SELF`; an empty participant list also → `SELF` (home room).
- **Rule 2.** `authorize(command, sender, owner, consent_mode, personal_agents=(), direction=Direction.OUTBOUND) -> Allowed | Denied`. It takes a PLAN.md command name, never raw text; a structural test asserts the signature has no text/body/message parameter, and the forgery test feeds a "from Om" text alongside Rahul's agent identity and gets a denial.
  - `yes`/`no`/`answer`: owner's user → `Allowed("direct")`; a registered personal agent (`personal_agents`) owned by the owner and `consent_mode == "via-agent"` → `Allowed("via-agent")`; owner's agent in `direct` mode → `Denied(CONSENT_MODE)`.
  - `trust`/`view-as`/`ledger`: owner's Switch user only (`Denied(NOT_OWNER)` for anyone else, including the owner's own agent).
  - `dm`/outbound `ask-around`: owner's user → direct, any owner-owned agent → via-agent.
  - `free`/`ask`/`ask-owner`/`propose`/`counter`/`gift-ideas`/`claim`/inbound `ask-around`: `Allowed("cross-boundary")` for any sender; the handler applies the room level. Owner commands sent `Direction.INBOUND` are denied (`OWNER_COMMAND`), so a cross-boundary `yes` can never become consent.
  - Unknown names → `Denied(UNKNOWN_COMMAND)`; malformed types → `PolicyError`.
- **Rule 3.** `can_set_level(old, new, actor) -> bool` with `Actor.OWNER` (always true) and `Actor.AGENT` (`new.rank >= old.rank`, i.e. only toward `private`). `Level.SELF` and non-fact tags raise `PolicyError`.
- **Constants for phases 09/11.** `OWNER_DIRECT_COMMANDS`, `OWNER_ONLY_COMMANDS`, `OWNER_AGENT_COMMANDS`, `CROSS_BOUNDARY_COMMANDS`, `OWNER_COMMANDS`, `KNOWN_COMMANDS`. `ask-around` is the only name in two sets; a test pins that, so phase 11 must pass `Direction.INBOUND` for the gate-to-gate form.

### Public API for phases 08, 11, 12

```python
Identity.user(id) -> Identity
Identity.agent(id, owner_id=None) -> Identity      # .person -> str | None
room_level(owner, participants, trust) -> Level | None
authorize(command, sender, owner, consent_mode,
          personal_agents=(), direction=Direction.OUTBOUND) -> Allowed | Denied
visible_facts(profile, level) -> dict[str, Any]
fact_is_visible(fact_level, level) -> bool
calendar_view(blocks, level) -> list[Block]
can_set_level(old, new, actor) -> bool
# Allowed.mode in {"direct", "via-agent", "cross-boundary"}; Allowed.allowed, Denied.code, .reason, .allowed
# SenderKind, Direction, Actor, DenialCode, PolicyError
```

### Evidence: make check

```
$ make check
uv run ruff format --check . && uv run ruff check . && uv run pytest -q
61 files already formatted
All checks passed!
302 passed in 0.75s
```

### Evidence: policy tests

```
$ uv run pytest -q tests/test_policy.py
127 passed in 0.05s
```

127 tests: 16 §3 table cells, 4 whole-level fact sets, Om fixture at four levels, copy isolation, calendar titles at every level, 14 room-level cases (mixed room, stranger, owner's agents skipped, home room, Rahul's agent as Rahul, ownerless agent, unmappable id, case-insensitive), 9 consent cases on the real Rahul/Om fixtures (Hermes via-agent for Rahul; denied for Om; direct-mode denial), forgery, owner-only × direction, `dm`/`ask-around` direction, cross-boundary, unknown names, Rule 3 (9 agent cells + 4 owner cells + errors), identity validation, and the purity test.

### Evidence: purity

The module's complete import set is asserted by `test_policy_imports_nothing_impure` (AST walk of `policy.py`):

```
['__future__', 'collections.abc', 'copy', 'dataclasses', 'enum',
 'trustnet.gate.calendar', 'trustnet.gate.facts', 'typing']
```

No `trustnet.switch_client`, no `os`/`pathlib`/`socket`/`httpx`/`websockets`/`yaml`, no file or network access.

### Deviations

- `Allowed.mode` has a third value, `"cross-boundary"`, beyond the phase file's `"direct" | "via-agent"`. Cross-boundary commands carry no owner consent to attribute, and the handler applies the room level; `Allowed`/`Denied` are also truthy/falsy (`if not decision`) so a caller cannot forget `.allowed`.
- `Denied` is `Denied(code: DenialCode, reason: str)`. The stable `DenialCode` values (`unknown-command`, `not-owner`, `not-owner-agent`, `consent-mode`, `owner-command`) keep tests and phase 21's overreach notes off prose.
- `authorize` takes `direction: Direction` (default `OUTBOUND`) only to disambiguate `ask-around`; the same flag also makes the gate reject inbound `yes`/`trust`/`dm`, which Rule 2 requires anyway.
- Senders are `Identity(kind, id, owner_id)` with `kind` a `SenderKind`. For a user the person is the id; for an agent it is `owner_id`. The caller maps Switch ids to the trust list's person names (`get_agent_detail` gives `owner_id`; check 8 notes in `docs/day0.md`).
- `room_level` skips *any* agent owned by the owner, not only `personal_agents` (Rule 1 says "the owner's own agents"). `personal_agents` is used only for consent in `authorize`. A personal agent is not required for `dm`/`ask-around`, matching "the owner or the owner's own agents".
- Unknown command names are `Denied(UNKNOWN_COMMAND)` rather than raising, so a parser miss cannot crash the gate; wrong Python types still raise `PolicyError`.
- `visible_facts` returns deep copies, so a brief builder that sorts a wishlist cannot mutate the loaded `Profile`.
- Phase 09's extra gate-to-gate commands (`join-dm`, `consent P1 yes|no …`) are **not** in the §3 sets and are therefore denied by `authorize` today. Phase 14 must add them deliberately, and a `consent` relay must never be routed through the owner `yes` path. Flagged here so it is not silently assumed.
- No changes outside `trustnet/gate/policy.py`, `tests/test_policy.py` and this phase file.
