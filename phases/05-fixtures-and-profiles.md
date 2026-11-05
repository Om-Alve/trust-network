---
id: "05"
title: Fixtures and profile loading
status: done
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
- [x] `Level` (ordered): `acquaintance < friend < close < private`. A viewer level is one of the first three; `private` is a fact tag only. Also a `self` view used when the only others in a room are the owner's own agents (the home room).
- [x] Data models (dataclasses): `Fact(value, level)`, `Profile(owner, facts, calendar_path)`, `TrustList(people: dict[str, Level], consent_default: "direct" | "via-agent", envoy_provider, envoy_machine)`.
- [x] Loaders/savers for `trust.yaml` and `facts.yaml` with clear errors on unknown levels, unknown keys, or a missing calendar file. Saving keeps key order and comments where practical (round-trip via `yaml` is fine if comments are lost; note it).
- [x] Fixtures for `examples/om/`, `examples/rahul/`, `examples/priya/`, exactly per PLAN.md §3, plus what the scenes need:
  - Om: facts as in §3. **Wishlist items carry a price** so the budget filter in Scene 2 works, e.g. `{item: Catan Seafarers, price: 2500}`, `{item: Hario V60, price: 2000}`, `{item: Kindle Paperwhite, price: 14000}`.
  - Rahul: close to Om; `consent.default: via-agent`; `envoy.provider: codex`; some facts at each level; **no** tent in `has` (Scene 3).
  - Priya: friend to Om; `has: [2-person tent]` at friend level (Scene 3); a `recommends` entry (dentist).
  - `envoy.machine` left as a placeholder string that `scripts/demo_up.py` (phase 22) fills in.
- [x] Data dir resolution: `TN_DATA_DIR/<person>/` if set, else `examples/<person>/`, so the demo never mutates committed fixtures once `demo_up.py` copies them.
- [x] Tests: load all three fixtures; reject a bad level; round-trip save/load.

## Decision to make (write the answer in *Log*)
PLAN.md uses `2026-11-08` for "Saturday", but **Nov 8, 2026 is a Sunday** (Nov 7 is Saturday). Pick one and make fixtures, `SKILL.md` examples and the video script agree. Suggested: keep `2026-11-08` and call it "Sunday evening" in the demo, since Nov 7 is submission day.

## Done when
- [x] `make check` passes with the new tests.
- [x] `uv run python -c "from trustnet.gate.facts import load_profile; print(load_profile('om'))"` prints Om's profile.
- [x] Fixture calendars exist as placeholders (`calendar.ics` files that phase 06 fills with events).
- [x] The date decision above is recorded.

## Commit
`phase 05: demo fixtures and profile/trust loaders`

## Log

### What was built
- `trustnet/gate/facts.py`:
  - `Level` (a `StrEnum`) with `ACQUAINTANCE < FRIEND < CLOSE < PRIVATE < SELF`, `rank`, `is_viewer` and `is_fact_tag`. `SELF` is the last rank so `policy.visible_facts(profile, level)` (phase 07) can pass it and see every fact; it is rejected in YAML, as are `private`/`self` in a trust list.
  - `Fact(value, level)`, `Profile(owner, facts, calendar_path)` (calendar path resolved to an absolute path), `TrustList(people, consent_default, envoy_provider, envoy_machine)` with `level_for(person)`.
  - `resolve_data_dir(person)`: `TN_DATA_DIR/<person>/` when set, else `examples/<person>/` under `REPO_ROOT = Path(__file__).parents[2]`, so it does not depend on the CWD. `..`/path-separator names are rejected.
  - `load_trust(person)`, `load_trust_file(path)`, `save_trust(trust, path)`, `load_profile(person)`, `load_profile_file(path)`, `save_profile(profile, path)`; all YAML errors raise `FactsError(ValueError)` with the file, key and value in the message.
  - Validation: unknown top-level keys (`trust.yaml`: `people`/`consent`/`envoy`; `facts.yaml`: `calendar`/`facts`), unknown per-fact keys (only `value`/`level`), unknown or disallowed levels, bad `consent.default`, non-string `envoy` values, missing `calendar` file.
  - Saving: key order is preserved (`sort_keys=False`); **YAML comments are lost** on save (the loaders/savers work on `yaml.safe_load`/`safe_dump`, not a comment-preserving round-trip). Fixtures are hand-written with comments and are not rewritten by the demo because `demo_up.py` copies them into `TN_DATA_DIR`.
- Fixtures: `examples/{om,rahul,priya}/{trust.yaml,facts.yaml,calendar.ics}`; the `.gitkeep` files were removed. Om's wishlist carries prices (Catan 2500, Hario V60 2000, Kindle 14000). Rahul is close to Om, `via-agent`, provider `codex`, facts at every level, no tent. Priya is friend to Om with a `2-person tent` and a dentist recommendation at friend level. All three `envoy.machine` values are placeholders (`"<laptop machine name in Switch>"`, `"<VM machine name in Switch>"`).
- Tests in `tests/test_facts.py` (24 tests): all three fixtures load; Om/Rahul/Priya specifics; level ordering and viewer/fact-tag flags; bad levels (unknown, `private`/`self` in a trust list, `self` as a fact level); unknown keys (trust top level, fact entry, facts top level); missing calendar file; empty trust file; trust and profile round-trips (key order kept, `calendar: ./calendar.ics` written back); CWD independence; `TN_DATA_DIR` override; invalid person names.

### Date decision
Keep **`2026-11-08`** and call it **Sunday** (verified: Nov 8, 2026 is a Sunday; Nov 7 is the Saturday/submission day). PLAN.md §3/§4 now says "Sunday evening"/"Sunday" in the outing command and Scene 1 (4 words changed, nothing else). `SKILL.md` examples and the video script must use Sunday when written in later phases.

### Evidence: load_profile
```
$ uv run python -c "from trustnet.gate.facts import load_profile; print(load_profile('om'))"
Profile(owner='om', facts={'diet': Fact(value='vegetarian', level=<Level.ACQUAINTANCE: 'acquaintance'>), 'city': Fact(value='Bangalore', level=<Level.ACQUAINTANCE: 'acquaintance'>), 'drinks': Fact(value='no alcohol', level=<Level.FRIEND: 'friend'>), 'interests': Fact(value=['bowling', 'board games', 'sci-fi'], level=<Level.FRIEND: 'friend'>), 'has': Fact(value=['projector', 'camping stove'], level=<Level.FRIEND: 'friend'>), 'recommends': Fact(value={'dentist': 'Dr. Rao, 12th Main'}, level=<Level.FRIEND: 'friend'>), 'neighbourhood': Fact(value='Indiranagar', level=<Level.CLOSE: 'close'>), 'sizes': Fact(value={'tshirt': 'M'}, level=<Level.CLOSE: 'close'>), 'wishlist': Fact(value=[{'item': 'Catan Seafarers', 'price': 2500}, {'item': 'Hario V60', 'price': 2000}, {'item': 'Kindle Paperwhite', 'price': 14000}], level=<Level.CLOSE: 'close'>), 'address': Fact(value='42, 12th Main, Indiranagar, Bangalore 560038', level=<Level.PRIVATE: 'private'>)}, calendar_path=PosixPath('/Users/om/switch-hackathon/trust-network/examples/om/calendar.ics'))
```

### Evidence: make check
```
$ make check
uv run ruff format --check . && uv run ruff check . && uv run pytest -q
56 files already formatted
All checks passed!
...............................................                          [100%]
47 passed in 0.08s
```

### Deviations
- `Level` has a fifth member, `SELF`, ordered after `PRIVATE`. The task asks for "`acquaintance < friend < close < private` plus a `self` view"; making it a member of the same ordered enum is what lets phase 07's `visible_facts(profile, level)` / `room_level(...) -> Level | None` pass `self` without a second type. The loaders reject `self` and `private` wherever a room level is expected.
- Fixture wishlist order is Catan, Hario, Kindle (price filter output order in Scene 2); PLAN §3 lists Catan, Kindle, Hario. Same three items and prices.
- Fixture addresses are invented placeholder strings (PLAN §3 shows `"…"`); `private` means they are never disclosed in the demo.
- Calendar files are minimal valid VCALENDARs with no VEVENTs (phase 06 fills them).
