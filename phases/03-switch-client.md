---
id: "03"
title: Switch protocol client + fake Switch
status: done
priority: P0
owner: agent
depends_on: ["01"]
plan_refs: ["§5 switch_client.py", "§7 Agent protocol"]
target: Nov 5 evening
---

# 03 · Switch protocol client + fake Switch

## Goal
`trustnet/switch_client.py`: a small async client for Switch's agent protocol that every gate and `tn mcp` uses. Plus an in-memory fake with the same interface, so phases 07–22 can be tested without a live server.

Read first: [Agent protocol](https://docs.switchagents.ai/switch-rooms/internals/agent-protocol), [`create_room` source](https://github.com/sandbox-quantum/switch/blob/main/core/switch_core/bridges/agent/operations/definitions.py), [agent controllers design](https://github.com/sandbox-quantum/switch/blob/main/docs/design/agent-controllers-v1.md). Write down anything that differs from PLAN.md in *Log*.

## Tasks
- [x] Define a `SwitchAPI` `typing.Protocol` with the ops the plan needs: `post_message`, `create_room(internal_only=…, read_visibility=…)`, `invite_agent_to_room`, `connect_to_room`, `list_participants`, `get_agent_detail`, `get_room_detail`, `archive_room`, `create_agent`, `update_agent_detail`, `list_machines`, plus room documents (attach / update) and message history if the protocol has it.
- [x] `SwitchClient` (real): register with a person's registration key (`httpx`), open the WebSocket (`websockets`), yield typed `Event`s that carry room ID, sender ID, sender kind (user / agent), text, and `addressed`. Reconnect with backoff. Requests time out with clear errors.
- [x] `tests/fakes/fake_switch.py`: `FakeSwitch` server state (users, agents with owners, rooms with members and visibility, messages) and `FakeSwitchClient` implementing `SwitchAPI` against it. Addressing: a message `@name …` marks that agent as `addressed`. It must enforce at least: internal-only rooms invisible to humans, private rooms readable only by members, archived rooms read-only.
- [x] `scripts/probe_post.py --key-env OM_GATE_KEY --room <room>`: registers and posts "hello from trust-network" (live smoke test).
- [x] Unit tests: event parsing from recorded sample frames (save real frames to `tests/data/switch_frames/*.json` during the live probe), fake-client behaviour, reconnect logic (simulated drop).

## Done when
- [x] `make check` passes, including tests for the fake.
- [x] Live: `uv run scripts/probe_post.py …` posts a message that appears in a room in Switch Console (and in `#om-home` once it exists). Evidence in *Log*.
- [x] A live event received by the client shows sender ID and `addressed` (sample frame saved under `tests/data/switch_frames/`). This also gives the first half of check 8.
- [x] Every op name and payload shape used is checked against the protocol docs or source; any guess is marked `# UNVERIFIED` in code and listed in *Log* for phase 04.

## Commit
`phase 03: switch protocol client and in-memory fake`

## Log
<!-- evidence, deviations, notes -->


### Offline evidence (2026-11-05)

- Claimed phase 03, implemented its offline tasks, left blocked because Om's
  server setup is unavailable. No live success is claimed.
- `make check` final output:
  ```text
  uv run ruff format --check . && uv run ruff check . && uv run pytest -q
  56 files already formatted
  All checks passed!
  47 passed in 0.08s
  ```
- Owned-path format/lint passed; focused tests: `8 passed in 0.04s`.
  Includes doc-derived parsing, operation payload and timeout, actual local
  WebSocket server dropping a connection then reconnecting with room/cursor,
  fake visibility, membership, archives, documents and agent ownership.
- Earlier global checks caught phase 05's unfinished formatting/imports;
  those files were left alone and the final global check passed.
- No dependencies changed; no shared conftest added.

### Protocol verification

Fetched public https://docs.switchagents.ai/switch-rooms/internals/agent-protocol
and shallow-cloned https://github.com/sandbox-quantum/switch into
`/tmp/trustnet-switch-protocol`, outside this checkout. Source revision:
`1c9725a08d0e80151ac21adeea8df373f12a779e`.
Read `docs/design/agent-controllers-v1.md` and the protocol documentation.
Every exposed operation name and full signature was transcribed from
`core/switch_core/bridges/agent/operations/definitions.py` or
`operations/agent_management.py`. Includes `send_targeted_message`,
`create_room_document`, `update_room_document`, and `read_context`.
Registration uses `/agents/register-known` with bearer registration token;
HTTP operations send unwrapped arguments to `/agents/{id}/ops/{operation}`.
WebSocket path, frame wrapper and pong handling checked against
`api/handlers.py::connection_socket`, `_receive_pongs`, and
`protocol/stream.py::encode_ws`. Existing docs describe SSE, current source
implements WebSocket too. Fixtures have explicit doc-derived provenance.

### Remaining live work (phase 04)

1. Run `probe_post.py --key-env OM_GATE_KEY --room <Om-room> --agent-type
   <installed-known-type> --url <bridge-base>` against Om's server. Arrange
   membership for the newly registered `trustnet-probe` agent. Optionally
   persist one-time credentials with `--credentials <gitignored-path>`.
   Confirm the message in Console and eventually `#om-home`.
2. Record real WebSocket frames to replace/supplement doc-derived fixtures.
3. Confirm sender ID, user/agent kind and `addressed` on real messages.

### UNVERIFIED for phase 04

- `# UNVERIFIED` in `parse_event`: legacy frames may omit sender_kind;
  unknown stays `unknown`, never guessed from names. Verify sender identity
  mapping to participant IDs before implementing authorization.
- Compatibility of fetched main's WebSocket endpoint and operation signatures
  with Om's planned core 0.31.0 installation requires live confirmation.
- Installed known-agent type for registration and cross-owner invites,
  managed-agent permissions/instruction redaction, addressing and Console
  access need the Day-0 checks. No payload names were guessed.

### Deviations

- The fake enforces requested stricter privacy/archive behavior. Upstream
  `internal_only` means no external bridge, not a guarantee against Console
  access. Upstream archive is reversible metadata and does not block writes.
  Do not treat fake tests as proof of these server security properties.
- Room-scoped operations retain upstream's implicit connected room rather
  than adding unsupported room_id arguments. Participants have no owner ID;
  call get_agent_detail to obtain ownership. Explicit targeted messages use
  send_targeted_message; fake also recognizes @name as requested.
- Fake management/document/history operations model only offline essentials,
  not controllers, provider execution, timestamp pagination or tool policy.
- PLAN.md intentionally untouched per coordination instructions.

### Live evidence, 2026-11-05

- Core 0.31.0 installed source confirms the operation signatures and WebSocket path.
- `probe_post.py` with `--room new --name day0-smoke2 --agent-type opencode` posted
  `hello from trust-network`, event `sw_1727797529534f78832b507e118e0b9e`,
  in `day0-post-smoke`. Gateway room read confirms Console access; no browser used.
  `#om-home` remains phase 11 work.
- Real frame saved as `tests/data/switch_frames/live-message.json`. Ordinary
  sender_kind is null; sender is a transport mxid, not list_participants UUID.
  Keep unknown rather than inventing an identity. Addressed is boolean.
- Operations require an active WebSocket or return 409. Client exposes ready;
  smoke probe now drains events and waits for connection_state before operations.
- Remaining historical UNVERIFIED entries above are resolved by these live
  observations and phase 04 findings. No credentials appear in fixtures.
- `make check`: 57 files already formatted; All checks passed; 48 passed in 0.12s.
