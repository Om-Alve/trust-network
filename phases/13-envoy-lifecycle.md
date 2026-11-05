---
id: "13"
title: Envoy lifecycle (managed agents)
status: todo
priority: P0
owner: agent
depends_on: ["04", "11", "12"]
plan_refs: ["§0 Envoys", "§5 gate/envoy.py", "§6 envoy row", "§8 checks 4–6", "§11 Envoys chat forever"]
target: Nov 6 afternoon
---

# 13 · Envoy lifecycle (managed agents)

> Skip this phase (set `status: skipped`) if phase 04 chose the fallback runner; do 13b instead.

## Goal
`trustnet/gate/envoy.py` gets a person's envoy for a friend ready for one conversation: create it once as a Switch-managed agent on the owner's own machine, re-brief it each time, invite it, and end the conversation when it runs too long.

## Tasks
- [ ] `ensure_envoy(owner, friend)`: look up `<owner>-envoy-<friend>`; if missing, `create_agent` with provider and machine from `trust.yaml`, an empty working folder, file and shell tools off, `auto_mode` and `auto_approve` off.
- [ ] `brief_envoy(envoy, brief_text)`: `update_agent_detail` with the brief from phase 12 (and the ledger entry it implies).
- [ ] Addressing: the envoy answers only its own gate and the friend's envoy (set via `update_agent_detail` or the fallback from check 5, recorded in `docs/day0.md`).
- [ ] `start_conversation(room, envoy)`: `invite_agent_to_room`; each DM room is a fresh session (verified in check 5).
- [ ] `ConversationWatch`: counts envoy turns per room and a wall-clock timer; at 12 turns or 10 minutes, the gate posts a short summary to its home room and calls `archive_room`.
- [ ] Offline tests with `FakeSwitch`: create-once (second call reuses), re-brief changes instructions, tools-off flags in the `create_agent` payload, turn limit and timer both archive.

## Done when
- [ ] `make check` passes.
- [ ] Live: `om-gate` creates `om-envoy-rahul` (OpenCode, `opencode-go/deepseek-v4.1-flash`, laptop; model from `trust.yaml` `envoy.model`) and `rahul-gate` creates `rahul-envoy-om` (Codex, VM, or laptop per check 2/3), each replies in a test room, and a re-brief visibly changes the next reply.
- [ ] Live: a test room is archived automatically after the 12th envoy turn.
- [ ] The `create_agent` payload actually sent is pasted in *Log* (shows tools off, auto-mode off).

## Commit
`phase 13: managed envoy create/brief/invite and conversation limits`

## Log
<!-- evidence, deviations, notes -->
