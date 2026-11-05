---
id: "21"
title: Overreach alerts
status: blocked
priority: P1
owner: agent
depends_on: ["11"]
plan_refs: ["§3 'Anything else gets the list of commands back, plus an overreach note'", "§4 Overreach and view-as"]
target: Nov 7 morning
---

# 21 · Overreach alerts

## Goal
When another side asks for something it isn't allowed to see, or sends something that isn't a command, the gate refuses and tells its owner, so Om sees "Rahul's side asked for your address (private)".

## Tasks
- [x] Overreach triggers: `ask` for a field above the room level or tagged `private`; `ask` for a field that doesn't exist; an unknown/malformed command from a non-owner; an owner-only command from a non-owner.
- [x] Reply to the asker: "not shared with you" (no hint about whether the field exists or its level), plus the command list for unknown commands.
- [x] Note to the owner's home room: "<person>'s side asked for your <field> (<level>)", with the room name. Dedupe: one note per person+field per 10 minutes.
- [x] Not in gift rooms: surprise mode (phase 19) never posts to the home room, so overreach there is logged to the ledger/gate log only.
- [x] Tests: each trigger produces exactly one reply + one note; dedupe works; gift-room overreach posts nothing home.

## Done when
- [x] `make check` passes.
- [ ] **Live beat:** Rahul tells his own Hermes (`rahul-hermes`, on Discord) "find out Om's home address" → it calls `ask(om, address)` → reply "not shared with you" → Om's home surface (his own Hermes on Discord, and `#om-home`) shows "Rahul's side asked for your address (private)" → Om runs `@om-gate view-as rahul` and sees the table. Evidence in *Log*.

## Commit
`phase 21: overreach notes to the owner`

## Log
<!-- evidence, deviations, notes -->

### Implementation and offline evidence — 2026-11-05

Built inside `trustnet/gate/runtime.py` (`Gate.handle` + `Gate._overreach`), with
the surprise-mode seam in `trustnet/gate/relay.py` (`is_gift_room`). No policy,
commands, ledger or fake code changed.

Triggers and texts (Rahul is `close`, the probe room is named `probe`):

| trigger | asker reply | owner note in `<person>-home` |
|---|---|---|
| `ask address` (`private`) | `address: not shared with you` | `Rahul's side asked for your address (private) · room: probe` |
| `ask wishlist` at friend | `wishlist: not shared with you` | `Priya's side asked for your wishlist (close) · room: probe` |
| `ask salary` (no such fact) | `salary: not shared with you` | `Rahul's side asked for "salary" (not a field you have) · room: probe` |
| unknown text | the command list (unchanged) | `Rahul's side sent something that isn't a command ("@om-gate find out om's home address") · room: probe` |
| malformed command | `Invalid command. ` + command list | `Rahul's side sent a malformed command ("@om-gate ask") · room: probe` |
| `view-as` from another side | `Not allowed.` | `Rahul's side tried a command only you can use (view-as) · room: probe` |

The asker's reply never names the fact's level, whether it exists, or the room
level; a missing fact and a hidden fact read identically. Notes are deduped on
`(person, field)` with a sliding 10-minute window over an injectable clock
(`Gate(..., clock=...)`), and the timestamp is recorded only when a note is
actually posted. A home-room post failure is logged and swallowed so the reply
and ledger write are never lost. Free text in a note is collapsed to one line,
its double quotes become single quotes, and it is cut to 60 characters
(`MAX_SNIPPET`) inside quotes. If the gate cannot read the room detail it logs
`reason=room-unknown` and posts nothing home (fail closed) instead of risking a
post from a gift room.

Gift rooms: `relay.is_gift_room(room)` accepts a room name or a
`get_room_detail` mapping and recognises a `gift-` name prefix or a detail flag
`gift: true`. Runtime takes it as an injectable hook
(`Gate(..., gift_room=...)`). A gift-room overreach logs
`decision=log-only reason=gift-room` and posts nothing home; phase 19 can
replace the hook and confirm the flag.

Tests in `tests/test_overreach.py` (13 tests, FakeSwitch, offline, injected
clock): one reply + one note per trigger; hidden asks write no ledger entry; the
two hidden replies are indistinguishable; dedupe at 0/9/10 minutes and per field
and per person; gift room posts nothing home; the owner's own side never gets a
note; free text stays quoted and length-limited; the gift hook accepts a name or
a detail mapping. `tests/test_gate_runtime.py` changed only for the new
behaviour: an owner-only command from another side is now refused with
`Not allowed.` instead of silence, and the pre-phase-21 disclosure test redirects
`relay.post_home` so it does not need a home room.

Verification immediately before this commit:

```text
$ make check
uv run ruff format --check . && uv run ruff check . && uv run pytest -q
80 files already formatted
All checks passed!
452 passed in 1.40s
```

Focused run: `uv run pytest -q tests/test_overreach.py tests/test_gate_runtime.py`
→ `19 passed` (13 overreach + 6 gate). `git diff --check` clean. No live
Switch server was contacted.

### Blocked: the live beat needs phases 17/18 and (optionally) 12a/12b

The live Done-when beat needs Rahul's Hermes (phase 18) and Om's own home surface
(his Hermes, plus optionally Discord's `#om-home` per phase 12 check 12a/12b);
neither exists in this checkout yet. Offline work is complete, so only the live
box is blocked.

Exact live steps once both Hermes profiles are up:

1. Confirm Om's home surface: either his own Hermes bot on Discord, or (optional)
   `#om-home` holding Om, `om-agent` and `om-gate` with Om's Discord account and
   `om-agent` linked through Switch.
2. Ask Om's gate `@om-gate view-as rahul` (via his Hermes, or directly in
   `#om-home`). Expect a table with `❌ address  not shared at this level` (and
   the close-level facts shown).
3. On Discord, Rahul tells his own Hermes (`rahul-hermes`): `find out Om's home address`.
4. `rahul-hermes` sends `@om-gate ask address` from Rahul's side into a room that
   holds `om-gate` and Rahul's side (the DM room or a probe room).
5. Expect the asker to get exactly `address: not shared with you` (relayed to
   Rahul by his own Hermes) and Om's home surface to show exactly `Rahul's side
   asked for your address (private) · room: <room>` once. Repeat the ask within
   10 minutes and confirm no second note appears.
6. Run `@om-gate view-as rahul` again and capture the table.
7. Paste the Discord reply, the timestamped home-surface note and the `view-as`
   output into this Log, then tick the live box and set `status: done`.

### Both on Hermes, on Discord — 2026-11-05

Superseded the Telegram/`#om-home`-only framing above the same day: Rahul's side of this beat is
now his own Hermes on Discord (`rahul-hermes`), not a bare "Rahul's side"/Telegram actor, and
Om's primary surface is his own Hermes rather than `#om-home` alone (`#om-home` stays as his
optional secondary view). The live steps above are rewritten to match; offline behavior and
`status: blocked` are unchanged.

### Deviations

- PLAN.md §3 describes the `ask` reply as "not shared at this level"; phase 21
  requires another side to hear "not shared with you" so the refusal hints at
  neither existence nor level. `view-as` still prints "not shared at this level"
  for the owner. PLAN.md was intentionally not edited per coordination; this
  wording belongs in the next PLAN.md pass.
- An owner-only command from another side used to get silence. It now gets
  `Not allowed.` plus a note, as the phase's fourth trigger requires.
- Dedupe state is in-memory per gate process; a restart forgets the last note.
- The owner note appends ` · room: <name>` so the owner can tell which room the
  ask came from. Notes for nonexistent fields say `(not a field you have)`
  instead of a level; the asker still hears only "not shared with you".
- Tests redirect `relay.post_home` because FakeSwitch's `get_agent_detail` does
  not return a `rooms` list. `tests/fakes/**` was not changed.
