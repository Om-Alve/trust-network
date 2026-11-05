---
id: "13b"
title: Fallback envoy runner (only if checks 4–6 fail)
status: todo        # set to skipped by phase 04 if the managed-agent path works
priority: P0 if needed
owner: agent
depends_on: ["04", "11", "12"]
plan_refs: ["§0 Custom envoy runner", "§5 envoy_runner.py (fallback)", "§8 checks 3–6", "§11 Risks"]
target: Nov 6 afternoon
---

# 13b · Fallback envoy runner

> Only do this phase if phase 04 found that managed envoys (`create_agent`, re-briefing, or envoys addressing each other) don't work. Otherwise phase 04 sets `status: skipped`.

## Goal
`trustnet/envoy_runner.py`: our own small process that plays the envoy role. It registers in Switch under its person's key and runs that person's agent CLI headless, in an empty folder with tools off, once per incoming message. It exposes the **same interface** as phase 13 (`ensure_envoy`, `brief_envoy`, `start_conversation`, `ConversationWatch`), so phase 14 doesn't care which one is used.

## Tasks
- [ ] Runner: `--person`, `--friend`, `--provider claude|codex|opencode`, `--key-env`. Registers as `<owner>-envoy-<friend>`.
- [ ] Per addressed message: build a prompt from the current brief + room transcript; run the CLI in a fresh empty temp dir:
  - `claude -p --disallowedTools "Bash,Edit,Write,Read,…"`;
  - `codex exec` with sandbox read-only / no network approvals;
  - `opencode run`;
  and post its stdout (trimmed) to the room.
- [ ] Brief handoff: the gate writes the brief to the runner's state dir (or sends it over a local socket); the runner never reads the person's data dir.
- [ ] Fresh session per DM room: transcript scoped to the room only.
- [ ] Same turn/timer limits as phase 13.
- [ ] Offline tests: prompt assembly, tool-disable flags present in the command line, transcript scoping per room.

## Done when
- [ ] `make check` passes.
- [ ] Live: Om's runner (Claude) and Rahul's runner (Codex) talk to each other in an agent-only room for at least 4 turns.
- [ ] *Log* lists which checks failed and why this path was taken.

## Commit
`phase 13b: fallback headless envoy runner`

## Log
<!-- evidence, deviations, notes -->
