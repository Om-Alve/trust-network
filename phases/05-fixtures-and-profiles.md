---
id: "05"
title: Fixtures and profile loading
status: todo
priority: P0
owner: agent
depends_on: ["01"]
plan_refs: ["§3 Levels, facts and preferences", "§2 Cast", "§4 Scenes (data each scene needs)"]
target: Nov 6 morning
---

# 05 · Fixtures and profile loading

## Goal
The demo cast's data on disk, and `trustnet/gate/facts.py` to load and save it with validation. Every later module works on these typed objects, never on raw YAML.

## Tasks
- [ ] `Level` (ordered): `acquaintance < friend < close < private`. A viewer level is one of the first three; `private` is a fact tag only. Also a `self` view used when the only others in a room are the owner's own agents (the home room).
- [ ] Data models (dataclasses): `Fact(value, level)`, `Profile(owner, facts, calendar_path)`, `TrustList(people: dict[str, Level], consent_default: "direct" | "via-agent", envoy_provider, envoy_machine)`.
- [ ] Loaders/savers for `trust.yaml` and `facts.yaml` with clear errors on unknown levels, unknown keys, or a missing calendar file. Saving keeps key order and comments where practical (round-trip via `yaml` is fine if comments are lost; note it).
- [ ] Fixtures for `examples/om/`, `examples/rahul/`, `examples/priya/`, exactly per PLAN.md §3, plus what the scenes need:
  - Om: facts as in §3. **Wishlist items carry a price** so the budget filter in Scene 2 works, e.g. `{item: Catan Seafarers, price: 2500}`, `{item: Hario V60, price: 2000}`, `{item: Kindle Paperwhite, price: 14000}`.
  - Rahul: close to Om; `consent.default: via-agent`; `envoy.provider: codex`; some facts at each level; **no** tent in `has` (Scene 3).
  - Priya: friend to Om; `has: [2-person tent]` at friend level (Scene 3); a `recommends` entry (dentist).
  - `envoy.machine` left as a placeholder string that `scripts/demo_up.py` (phase 22) fills in.
- [ ] Data dir resolution: `TN_DATA_DIR/<person>/` if set, else `examples/<person>/`, so the demo never mutates committed fixtures once `demo_up.py` copies them.
- [ ] Tests: load all three fixtures; reject a bad level; round-trip save/load.

## Decision to make (write the answer in *Log*)
PLAN.md uses `2026-11-08` for "Saturday", but **Nov 8, 2026 is a Sunday** (Nov 7 is Saturday). Pick one and make fixtures, `SKILL.md` examples and the video script agree. Suggested: keep `2026-11-08` and call it "Sunday evening" in the demo, since Nov 7 is submission day.

## Done when
- [ ] `make check` passes with the new tests.
- [ ] `uv run python -c "from trustnet.gate.facts import load_profile; print(load_profile('om'))"` prints Om's profile.
- [ ] Fixture calendars exist as placeholders (`calendar.ics` files that phase 06 fills with events).
- [ ] The date decision above is recorded.

## Commit
`phase 05: demo fixtures and profile/trust loaders`

## Log
<!-- evidence, deviations, notes -->
