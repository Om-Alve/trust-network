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
- [x] A: scenarios written down (failure modes first), run in-process on `FakeSwitch` with the
  real gate code, bugs fixed, `PROTOCOL.md` kept true.
- [x] B: the same for its area.
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

Final validation and artifact:
- A further failing-before authority assertion showed that a friend's `answer`
  only got `Not allowed.`. Planning policy refusals now include the actual reason.
- Updated the existing brief snapshot for the deliberate ID guidance change.
- Both direct and via-agent votes are exercised, including both local yeses
  queued before either peer relay and the final relay after confirmation archive.
- `make check`: ruff format and lint passed; **482 passed**.
- `uv run python scripts/e2e_planning_scenarios.py` writes each scenario's
  input/output room transcript, steps, final coordination and failure traceback.
  Run from the repository root. The injected anchor ConnectionError is expected.
- Artifact: `data/scenarios-planning-20261106T104712880463Z/`.
  Summary quoted from `summary.txt`:

```text
PASS three_people
PASS collisions_and_decline
PASS consent_replays_and_restart
PASS authority_and_questions
PASS malformed_plans
PASS limits_and_restart
PASS handshake_restart
PASS pool_capacity_and_failure
8 PASS / 0 FAIL
```

### B

Scenarios and the ways each can fail (written before the tests; "why" is the
failure mode, not the happy path):

**Facts and trust levels**
- Every field at each level: a friend asks the owner's whole fact set at
  `acquaintance`, `friend`, `close` and `private`/unknown. Fails if a
  higher-level value leaks, if a hidden fact and a fact that does not exist
  read differently (existence hint), or if the ledger records a hidden field.
- DM room holding friends at different levels: the room is `close` for one and
  `friend` for the other. Fails if the gate answers at the sender's level or at
  the highest level instead of the lowest.
- `free` at `acquaintance`: busy times are shown, titles must be blanked.
  Fails if an event title reaches an acquaintance, or if titles vanish at
  `friend`/`close`.
- A person not on the trust list: `ask`/`free` must be silent and write nothing
  to the ledger. Fails if a stranger gets values, a refusal, or a home note
  about the fact.
- Overreach notes: at most one per person and field per 10 minutes. Fails if
  the cooldown is global, per room, not per field, or a note names the level in
  the room reply.
- `fact set` loosening: refused by the CLI and by the MCP tool. Fails if an
  agent can move `friend` back to `acquaintance` (or a `private` fact down).
- `view-as` equals what `ask` returns: the same person, room level and facts.
  Fails if the preview and the answer use different policy paths.

**Gifts and claims**
- Gift ideas within budget, over budget and for an item already claimed. Fails
  if an over-budget item is suggested, a taken item is offered again, or the
  `taken`/`over_budget` lists are swapped or missing.
- The recipient is never notified and nothing appears in their home room.
  Fails if the recipient's gate posts a home message, an overreach note, or a
  share card for gift traffic.
- The recipient's ledger entry stays sealed until the day after the occasion.
  Fails if the value is visible on the occasion day, or stays sealed after it.
- Two askers for the same item: the second claim must be refused. Fails if both
  claims succeed, or the second claimer sees the item as free.
- `ask` in a gift room: refused, overreach logged, nothing posted home. Fails
  if a fact value is disclosed, or the owner is told and the surprise spoiled.
- The room is archived on a claim and after the 10-minute timeout. Fails if a
  claimed room stays open, or an idle room accepts a claim forever.
- Malformed gift traffic (a bare `ask`, a bare `claim`, bad JSON from a peer)
  is ignored, not raised out of dispatch. Fails if it takes the gate's event
  loop down or posts a general-home note.

**Ask-around**
- Fan-out to every listed friend in a `conn-<pair>` room, with a local `A<n>`
  question to the friend's own home. Fails if a friend is skipped, or the
  fan-out needs a room that already exists.
- A reply from a non-friend, or forged in the wrong room, is ignored. Fails if
  the answer map changes or the owner gets a summary.
- One reply per friend (the latest answer, so the friend's own words can replace
  the automatic profile reply). Fails if answers accumulate per message.
- Replies after the 5-minute expiry are ignored. Fails if a late answer lands.
- The friend's own-words path rechecks membership and trust at answer time, and
  the asker sees the new answer. Fails if the answer is posted to the wrong
  room, lost, or sent to a room that now holds a stranger.
- No stranger disclosure: an inbound `ask-around` in a room with a stranger, or
  from a non-gate agent, gets nothing. Fails if the profile lists are sent.
- A long `has`/`recommends` value (over 140 characters) still produces a reply.
  Fails if the reply is silently dropped because it cannot be quoted.

**`tn` CLI, MCP and wake**
- Every MCP tool with bad input: unknown friend, bad date, empty string, huge
  text, unicode, wrong type. Fails if the call is a traceback, hangs on a
  Switch round trip for input the owner's own data can reject, or reports
  success for a command the gate will ignore.
- `answer` text round-trips exactly (backslashes must not be JSON-escaped a
  second time on the way to the gate).
- MCP `fact_set` refuses loosening; `cal_add` validates form; both reuse the
  CLI handlers so the terminal and agent paths cannot drift.
- `tn wake`: a failed or timed-out turn is carried into the next prompt; a
  second runner for the same person is refused; `[SILENT]` prints nothing; the
  OpenCode JSON stream parser takes the last assistant message and ignores
  non-object lines.
- `watch`: a new peer message wakes once, the agent's own message does not, and
  the cursor is persisted (`watch` is what `tn wake` polls).

**Tests added (all offline, real gates over `FakeSwitch` unless noted)**
- `tests/test_scenario_facts.py`: level filtering and its ledger, hidden vs
  unknown fields, the lowest level in a mixed DM room, `free` titles by level,
  a stranger's silence, and `view-as` matching the answer.
- `tests/test_scenario_gifts.py`: two askers, taken/over-budget, the recipient's
  home untouched, the seal on the occasion day and the day after, claim and
  timeout archives, `ask` refused in a gift room, malformed gift traffic.
- `tests/test_scenario_around.py`: fan-out, one answer per friend, the friend's
  own words replacing the profile reply, forged/wrong-room/late/stranger
  replies, and a long profile list still producing a reply.
- `tests/test_wake.py`: a failed turn and a timed-out turn carried into the next
  prompt, the per-person lock, `[SILENT]`, `opencode_reply`, the `watch` cursor,
  and `answer` fidelity.
- `tests/test_mcp_bad_input.py`: every MCP tool with bad input over real stdio
  (unknown friend, bad dates, empty strings, huge text, wrong type), plus a
  unicode title and a tightening edit that must still succeed.
- `tests/scenario_harness.py`: the shared world (gates, agents, homes, clock,
  `FakeSwitch`); `tests/fakes/fake_switch.py` now records the `timestamp`,
  `sender_name` and `kind` a real Switch message carries, so `watch` runs.
- Existing tests already covered the overreach cooldown
  (`tests/test_overreach.py`) and the CLI/MCP loosen refusal (`tests/test_cli.py`,
  `tests/test_mcp_e2e.py`); no duplicate regression test was added.

**Bugs found and fixed**
- A malformed command in a gift room (`@om-gate ask`, `@om-gate claim`, a bad
  gift envelope) raised `ParseError` out of `surprise.handle`. It is now
  ignored: no reply, no owner note, and the event loop stays up. Peer
  `gift-result` JSON is parsed defensively too.
- `dm`, `ask`, `gift_ideas` and `claim` posted a command for a friend who is not
  on the trust list; the gate ignored it, so the tool either reported success or
  waited 15–30 s for a room that would never open. The personal layer now
  refuses with `no friend named <name>`.
- `personal.answer` JSON-escaped the answer text after already parsing it as
  `Quoted`, doubling every backslash on the way to the gate. It now posts the
  `Quoted` rendering, and refuses a `P<n>` answer that is not yes or no instead
  of letting the gate ignore it.
- Ask-around profile replies were dropped when `has`/`recommends` exceeded the
  140-character command limit. They are now rendered with the shared value
  formatter and cut with `…`; `ask` uses the same formatter as `view-as`, so a
  list no longer reads as a Python literal.
- `opencode_reply` raised `AttributeError` on a non-object JSON line (or a
  non-object `part`) from `opencode run --format json`; such lines are skipped.
- `personal.watch` assumed every message had `timestamp`; it now defaults to 0
  (and the fake records Switch-style fields), matching `consent._friend_spoke`.

**Deviations / found but left alone**
- `view-as` and the owner's own `ask` drop a claimed wishlist item, while a
  friend's `ask` returns the wishlist unchanged. That is deliberate surprise
  hygiene, not a policy split; `PROTOCOL.md` §7d now says so.
- `write_brief` (share cards) does not filter claimed wishlist items. The card is
  guidance in the owner's own home and never shows the claim status, and the
  file is used by area A's `dm.setup`; left alone to keep the parallel branches
  from colliding.
- The gate still silently ignores a raw `dm` for an unknown friend (the spec's
  behaviour); only the CLI/MCP layer refuses it early.
- The wake presets pass `SWITCH_URL`/`TN_DATA_DIR`/`TN_STATE_DIR` to the MCP
  server but not the person's registration key; the phase 26 runs had saved
  state, so this was not exercised and is left for a live run (no live systems
  here).

**Artifact** (`scripts/e2e_facts_scenarios.py`, run as
`uv run python -m scripts.e2e_facts_scenarios`; transcripts and summary under
`data/scenarios-facts-<nanoseconds>/`):

```
scenarios-facts 2026-11-06T16:32:17
PASS facts-levels (0.02s)
PASS facts-mixed-room (0.00s)
PASS facts-free-and-stranger (0.07s)
PASS overreach-dedupe (0.01s)
PASS fact-set-refusals (0.01s)
PASS gifts-and-claims (0.77s)
PASS ask-around (0.05s)
PASS ask-around-long-list (0.03s)
PASS mcp-bad-input (0.93s)
PASS tn-wake (0.04s)
10/10 passed
artifacts: data/scenarios-facts-1793962935521588000
```

`make check`: ruff format and lint clean, 501 tests passed.

