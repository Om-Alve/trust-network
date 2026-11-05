---
id: "11"
title: "Gate runtime: free / ask live"
status: blocked
priority: P0
owner: agent + human
depends_on: ["03", "04", "07", "08", "09"]
plan_refs: ["§0 gate", "§2 Rooms (#om-home)", "§3 Rules 1, 2, 6", "§5 templates/home.template.yaml, SKILL.md", "§8 check 12", "§9 Nov 6 morning milestone"]
target: Nov 6 morning
---

# 11 · Gate runtime: `free` / `ask` live

## Goal
A running gate process per person (`python -m trustnet.gate`) that listens on Switch, works out each room's level from server-side membership, and answers `free`, `ask`, `view-as`, `ledger` and `trust`. Om's Discord home channel exists from a template.

## Tasks
- [x] `trustnet/gate/__main__.py`: `--person om` (data dir from phase 05), key from `--key-env OM_GATE_KEY`, server from `SWITCH_URL`. Logs to stderr; one line per command handled (command, room, level, decision).
- [x] Event loop: for each `addressed` message → identify sender via Switch (never message text) → `room_level` from `list_participants` + `get_agent_detail` (cached per room, refreshed on membership-change events and every N minutes) → `authorize` → handler → reply → ledger entry.
- [x] Silence rule: if `room_level` is `None`, the gate posts nothing at all (a log line only).
- [x] Handlers: `free` (calendar view at level), `ask` (values or "not shared at this level"), owner-only `view-as`, `ledger`, `trust`. Unknown commands → command list (overreach note comes in phase 21).
- [x] `trustnet/gate/relay.py`: `post_home(person, text)`, which finds the person's home room (`#om-home` for Om; `rahul-home` / `priya-home` agent-only rooms for others, created on first use).
- [x] `templates/home.template.yaml`: private Discord channel `om-home`; a managed Codex agent `om-agent` (`provider: codex`, no model override, laptop `Om’s MacBook Pro`, `allow_existing`, addressing `owner`); `om-gate`; `SKILL.md` as a room doc.
- [x] Stub `skills/trust-network/SKILL.md` with the command list and examples (replaced by the dictated version in phase 18).
- [x] Offline tests with `FakeSwitch`: gate answers Rahul-level in a room with `rahul-gate`, friend-level with `priya-gate`, stays silent with a stranger, refuses `trust` from Om's agent, answers `self` level in the home room.
- [ ] **[human]** Run the template; confirm `#om-home` is a private Discord channel with Om, `om-agent`, `om-gate` (finishes check 12 in `docs/day0.md`).

## Done when
- [x] `make check` passes, including the FakeSwitch gate tests above.
- [ ] Live: in `#om-home`, Om asks `@om-agent ask my gate what I'm doing Sunday`, the agent sends `@om-gate free 2026-11-08..2026-11-09`, and the gate replies with Om's own calendar. Evidence (screenshot or copied text) in *Log*.
- [x] Live: in a probe room with `om-gate` + `rahul-gate`, `@om-gate ask diet wishlist address` returns diet + wishlist (Rahul is close) and "not shared" for address; with `priya-gate`, wishlist is "not shared". Ledger shows exactly the disclosed fields.
- [ ] Check 12 recorded as passed (or Mattermost fallback recorded).

## Commit
`phase 11: gate runtime with free/ask, home template, SKILL stub`

## Log
<!-- evidence, deviations, notes -->

### Implementation and evidence — 2026-11-05

Offline runtime, relay, template and skill are implemented. `Gate.handle` is the
single sequential dispatcher. It connects before room operations, reloads facts
and trust per command, refreshes membership and agent ownership per request,
and logs command name / room / level / authorization without message contents.
Unknown identities and unknown room members fail closed. Owner-only commands
also require a self-level room to avoid displaying owner views to other people.
`consent` remains its own parsed command and is denied by phase 07; it never
enters an owner `yes` handler. No existing module APIs changed.

Identity deviation: core 0.31.0's agent API exposes neither the transport-client
mapping nor Gateway member clients in list_participants. `gate_identity_export.py`
reads users, clients, agents and client_rooms in a read-only DB transaction,
using Console's installed Python/asyncpg and existing DB owner credentials.
Only the three explicit demo account emails map to person names. The platform
admin client is excluded from room audiences and is never trusted as a sender.
Other unresolved clients make the room silent. Runtime refreshes this export
before each addressed command, supplements list_participants with Gateway
membership, and checks get_agent_detail ownership. This local adapter requires
Console's core 0.31.0 installation; remote gates need a server-side authenticated
identity adapter later. External Discord identity claims must be integrated and
verified when Discord is connected; they currently fail closed.

Run with environment variables loaded from `.env` (never echo them):
`uv run python -m trustnet.gate --person om --key-env OM_GATE_KEY`.
Retained credentials are reused from gitignored `data/day0-state.json`.
Priya's new gate is retained there too, with addressing open and
can_manage_agents enabled through her owner Gateway API (both HTTP 200).
Identity aliases are stored in gitignored `data/gate-identities.json`.

`uv run python -m scripts.gate_live_probe` passed against core 0.31.0:

- Rahul: `diet: vegetarian`; wishlist contained Catan Seafarers, Hario V60 and
  Kindle Paperwhite; `address: not shared at this level`. Ledger fields exactly
  `diet`, `wishlist`.
- Priya: `diet: vegetarian`; wishlist and address `not shared at this level`.
  Ledger fields exactly `diet`.
- Om, posting as his actual user through Gateway `/chats/.../messages` with a
  structured agent mention: `free 2026-11-08..2026-11-09` returned
  `2026-11-08T17:00:00+05:30 .. 2026-11-08T19:00:00+05:30 Family video call`.
  Ledger field exactly `calendar`. The agent-only room with Om explicitly added
  stood in for Discord; no managed agent was involved.
- All three disposable rooms deleted: HTTP 200 each. Fixture data was copied
  into a temporary directory; probe ledger never modified committed fixtures.

Template validation: installed `template_v2.compile_v2` followed by
`RoomTemplateDocument.model_validate(yaml.safe_load(compiled.document))` passed
with explicit sample machine/directory/Discord bridge inputs. No template was
run against the unconfigured Discord connection.

Verification: six FakeSwitch tests pass (Rahul, Priya, stranger, self, forged /
unaddressed / consent silence and unknown help, owner calendar/views/trust).
Initial full pytest: 426 passed, three failures confined to phase 12's active
brief tests. Initial `make check` stopped at phase 12 brief.py formatting.
See final validation below for the check immediately before commit.

### Blockers and exact human steps

Status remains blocked. Check 12a is pending: Om must create/configure the
Discord bot, enable Message Content and Server Members intents, invite it to
his guild, add the Discord connection to Switch, and link his Discord account
(see docs/setup-laptop.md step 7). Then run `templates/home.template.yaml` as
Om, select that Discord bridge and his laptop machine/directory, bind existing
om-agent if appropriate, and confirm private om-home membership includes Om,
om-agent and om-gate. Verify external identity claims through the server mapping
before accepting Discord commands. Finally ask om-agent to send the free command
and record the Discord reply/check 12b evidence.

Superseded by Om's Codex decision below. The original managed OpenCode blocker was: Console 0.40.1's controller waits
for `opencode server listening`; OpenCode 2.1.4 prints `server listening`.
No shell config, PATH, global package or Console files were changed. Om later
selected managed Codex for the main agent; see the subsequent evidence below.

Final validation immediately before commit: `make check` → `73 files already
formatted`, `All checks passed!`, `433 passed in 1.04s`; `git diff --check`
clean. Concurrent phase 12 changes had settled by this run.

### Om's main-agent decision and managed live check — 2026-11-05

Om selected managed Codex for `om-agent`, with no model override, on
`Om’s MacBook Pro`. The OpenCode startup blocker no longer applies to the main
agent. Om's envoy remains OpenCode with OpenCode Go DeepSeek V4.1 Flash through
the trust-network runner in phase 13b. `examples/om/trust.yaml` is unchanged.
The template now fixes `provider: codex`, omits `model`, and defaults to Om's
laptop machine. Installed v2 compilation and room schema validation passed,
including assertions that the compiled agent is Codex and has no model field.

`uv run python -m scripts.gate_codex_probe` passed one short real managed-agent
exchange in an internal Switch room standing in for Discord:

1. Om's actual Gateway user posted `@om-agent ask my gate what I'm doing Sunday`.
2. The managed Codex agent posted `@om-gate free 2026-11-08..2026-11-09`.
3. The gate replied `2026-11-08T17:00:00+05:30 .. 2026-11-08T19:00:00+05:30 Family video call`.
4. The temporary ledger contained exactly the `calendar` field. No calendar or
   committed example data was changed.

Retained `om-agent` ID: `30919e05-a808-4eda-b86e-7afb2b382ab3`.
The management API confirmed provider `codex`, model `null`, machine
`Om’s MacBook Pro`, process `running`. Its working directory is the gitignored
`data/om-agent` directory. Addressing is owner-only. After the probe, general
main-agent instructions replaced the date-specific probe brief (HTTP 200).
The probe room was deleted (HTTP 200); the agent remains for the demo.

Current blocker: Discord setup/check 12a and the actual private Discord home
run/check 12b remain pending, including verifying the linked external sender's
identity. The managed Codex home exchange itself has now passed with the
explicitly authorized agent-only room substitution. No OpenCode or Console
installation changes were needed.

Decision-update validation: `make check` passed with `76 files already formatted`,
`All checks passed!`, and `433 passed in 1.37s`. `git diff --check` passed.
Existing APIs and Om's envoy trust configuration were not changed.
