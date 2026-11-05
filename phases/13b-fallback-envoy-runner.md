---
id: "13b"
title: Fallback envoy runner (only if checks 4–6 fail)
status: skipped
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
- [x] Runner: `--person`, `--friend`, `--provider opencode|codex`, `--key-env`. Registers as `<owner>-envoy-<friend>`.
- [x] Per addressed message: build a prompt from the current brief + room transcript; run the CLI in a fresh empty temp dir:
  - `opencode run -m opencode-go/deepseek-v4.1-flash` with Bash/Edit/Write denied in its permission config;
  - `codex exec` with sandbox read-only / no network approvals;
  - `opencode run`;
  and post its stdout (trimmed) to the room.
- [x] Brief handoff: the gate writes the brief to the runner's state dir (or sends it over a local socket); the runner never reads the person's data dir.
- [x] Fresh session per DM room: transcript scoped to the room only.
- [x] Same turn/timer limits as phase 13.
- [x] Offline tests: prompt assembly, tool-disable flags present in the command line, transcript scoping per room.

## Done when
- [x] `make check` passes.
- [x] Live: Om's runner (OpenCode) and Rahul's runner (Codex) talk to each other in an agent-only room for at least 4 turns.
- [x] *Log* lists which checks failed and why this path was taken.

## Commit
`phase 13b: fallback headless envoy runner`

## Log
<!-- evidence, deviations, notes -->

### Day-0 decision, 2026-11-05

Phase 04 selects this branch. Core 0.31.0 rejects OpenCode disallowedTools and the short live managed probe did not prove OpenCode replies or rebrief delivery. Keep OpenCode DeepSeek for Om and Codex for Rahul; enforce native tool restrictions and per-conversation isolation in the runner. See docs/day0.md for evidence.

### Implementation and live evidence, 2026-11-05

Implemented `trustnet/envoy_runner.py` and gate-side `ensure_envoy`, `brief_envoy`,
`start_conversation`, `ConversationWatch`. No runtime.py or relay.py edits.

The V2 OpenCode docs and schema (https://opencode.ai/v2/docs/permissions and
https://opencode.ai/config.json) specify `permissions`, `shell`, `subagent`, and
wildcard actions. V1 `permission` / `bash` is obsolete in 2.1.4. The per-run config
sets `permissions=[{"action":"*","resource":"*","effect":"deny"}]` and
`policies=[{"action":"tool.use","resource":"*","effect":"deny"}]`.
This covers read, glob, grep, directory listing, edit/write/patch, shell,
webfetch/websearch, subagents, skills, MCP and execute. Snapshots, updates and
sharing are disabled. `auth export opencode-go` is captured without printing;
only that integration is imported into the temporary home with `auth import
--standalone`. The model CLI uses a private server, never the user's shared server.

Commands, with ROOT a fresh resolved temporary directory and BIN the resolved CLI:

```
/usr/bin/sandbox-exec -f ROOT/sandbox.sb ~/.opencode/bin/opencode run --standalone -m opencode-go/deepseek-v4.1-flash --format json
/usr/bin/sandbox-exec -f ROOT/sandbox.sb BIN -a never exec --sandbox read-only --ignore-user-config --ignore-rules --skip-git-repo-check --ephemeral -c features.shell_tool=false -c features.apply_patch=false -c web_search="disabled" --json -
```

Prompts go through stdin. Environment is allowlisted, with fresh HOME, CODEX_HOME
and XDG paths. Only Codex auth.json is copied. No owner's environment, instructions,
MCP configuration or project files are copied. Each cwd is a fresh empty work dir.
Seatbelt blocks file content reads under /Users, /Volumes and /private, allowing
only the temporary root, exact provider executable, /private/etc and /private/var/db.
File metadata reads are allowed for path resolution. Both native CLI launches
returned hello under these restrictions. Linux fails closed until a separate OS
user/container is supplied in phase 16.

Residual security risk: this is practical CLI confinement, not a VM. System files
outside the denied roots and file metadata remain readable. Provider authentication
is accessible inside the disposable home; inference network access is required and
allowed for the CLI process. Native tool denial and Codex sandbox enforcement must
remain trustworthy. A compromised CLI could use its inference network access or
write outside the temp directory because the outer profile constrains reads, not
all writes. The runner itself never opens the person's data directory. A dedicated
OS user/container is needed for a stronger boundary. See the SECURITY comment.

Live command: `uv run python -m scripts.envoy_live_probe`. Both providers ran on
the laptop, including Rahul's Codex, per PLAN §2 one-machine fallback. Four CLI
turns were manually orchestrated through the runner's generate function and posted
by the corresponding registered envoy into agent-only room
`2e95fef6-7a8f-4e76-ad9f-545041b91744`; this probe does not prove automatic WebSocket
peer dispatch. Server read_context saved to gitignored data/envoy-probe-context.json.
Turn 1 Om proposed vegetarian lunch Sunday noon, subject to approval; turn 2 Rahul
agreed tentatively and asked both owners; turns 3 and 4 reaffirmed the tentative
plan and requested approval. Probe room archived in finally. Registrations retained
for phase 14; credentials are mode 0600 in
`data/envoys/om-envoy-rahul/credentials.json` and
`data/envoys/rahul-envoy-om/credentials.json`, both gitignored.

Phase 14 must call ensure_envoy(owner, friend, url=..., key=owner registration key,
state_dir=per-envoy state path), gate brief.write_brief(...), then
brief_envoy(envoy, brief.text, state_dir=..., room=room UUID,
allowed_senders=[verified own-gate and peer transport IDs], peer=peer envoy name).
Use the phase 11 trusted identity export, never names guessed from message text.
Call start_conversation(room, envoy_name, client=gate_client), run Runner with the
retained envoy client and provider, and run ConversationWatch.run() in a task.
Feed only verified envoy messages to watch.turn(text), counting both sides.
Cancel/stop runners or remove their room handoff files when the watch closes:
archive does not prohibit writes. Runner also refuses expired briefs and caps its
local room history at 12 entries. Gate must own room operations sequentially to
avoid its connected-room context being changed concurrently by other dispatch.
No gate runtime hook is installed in this phase. Rebrief each new room; old room
transcripts are never included. The brief is the whole application instruction.

Verification: own paths Ruff format and lint pass; six envoy tests pass. Full
`make check` was run and stopped at Ruff formatting in the other agent's
`tests/test_overreach.py` (1 would reformat, 79 formatted). Independent full pytest
run: 449 passed, 2 failed, both phase 21 in-progress assertions:
`test_gate_disclosures[om-self]` and
`test_free_text_in_the_note_is_quoted_and_length_limited`. Per the user's explicit
exception, commit proceeds with these unrelated failures documented.

Deviations: V2 permission schema replaces the V1 suggestion. Live probe orchestrates
four CLI turns explicitly; phase 14 still needs end-to-end automatic peer dispatch.
Rahul runs locally until phase 16. Checks 4/6 selected this path because the managed
controller cannot recognize OpenCode 2.x startup and core rejects tool restrictions;
check 5 did not establish managed rebrief/session guarantees. See docs/day0.md.

Final verification rerun after phase 21 edits settled: `make check` passed:
`80 files already formatted`, `All checks passed!`, `452 passed in 1.28s`.
The earlier concurrent failures above were transient. Own paths also pass separately.

### No-envoy decision, 2026-11-05

Built, unused after the no-envoy decision (2026-11-05). PLAN.md now has main agents
(`om-hermes`/Hermes and `rahul-agent`, a managed Codex agent) talk directly in DM rooms;
nothing calls `trustnet/envoy_runner.py` or `trustnet/gate/envoy.py` anymore. The code,
tests and live evidence above are left in the repo and unmodified — do not delete them.
