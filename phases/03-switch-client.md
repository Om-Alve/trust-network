---
id: "03"
title: Switch protocol client + fake Switch
status: todo
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
- [ ] Define a `SwitchAPI` `typing.Protocol` with the ops the plan needs: `post_message`, `create_room(internal_only=…, read_visibility=…)`, `invite_agent_to_room`, `connect_to_room`, `list_participants`, `get_agent_detail`, `get_room_detail`, `archive_room`, `create_agent`, `update_agent_detail`, `list_machines`, plus room documents (attach / update) and message history if the protocol has it.
- [ ] `SwitchClient` (real): register with a person's registration key (`httpx`), open the WebSocket (`websockets`), yield typed `Event`s that carry room ID, sender ID, sender kind (user / agent), text, and `addressed`. Reconnect with backoff. Requests time out with clear errors.
- [ ] `tests/fakes/fake_switch.py`: `FakeSwitch` server state (users, agents with owners, rooms with members and visibility, messages) and `FakeSwitchClient` implementing `SwitchAPI` against it. Addressing: a message `@name …` marks that agent as `addressed`. It must enforce at least: internal-only rooms invisible to humans, private rooms readable only by members, archived rooms read-only.
- [ ] `scripts/probe_post.py --key-env OM_GATE_KEY --room <room>`: registers and posts "hello from trust-network" (live smoke test).
- [ ] Unit tests: event parsing from recorded sample frames (save real frames to `tests/data/switch_frames/*.json` during the live probe), fake-client behaviour, reconnect logic (simulated drop).

## Done when
- [ ] `make check` passes, including tests for the fake.
- [ ] Live: `uv run scripts/probe_post.py …` posts a message that appears in a room in Switch Console (and in `#om-home` once it exists). Evidence in *Log*.
- [ ] A live event received by the client shows sender ID and `addressed` (sample frame saved under `tests/data/switch_frames/`). This also gives the first half of check 8.
- [ ] Every op name and payload shape used is checked against the protocol docs or source; any guess is marked `# UNVERIFIED` in code and listed in *Log* for phase 04.

## Commit
`phase 03: switch protocol client and in-memory fake`

## Log
<!-- evidence, deviations, notes -->
