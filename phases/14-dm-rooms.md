---
id: "14"
title: DM rooms between main agents
status: done
priority: P0
owner: agent
depends_on: ["11", "12"]   # was 13/13b (envoy lifecycle), dropped with the no-envoy decision
plan_refs: ["§2 Rooms (conn-*, dm-*, rahul-home)", "§4 Scene 1 steps 1–10", "§8 check 7"]
target: Nov 6 afternoon
---

# 14 · DM rooms between main agents

> Repurposed, 2026-11-05: no envoys. Om tells Hermes (`om-hermes`, via `tn mcp`); Rahul talks to
> his own managed Codex agent (`rahul-agent`, on `rahul-vm`). Both are long-lived main agents,
> not per-conversation envoys — this phase invites the *existing* agent into a DM room and hands
> it a private share card (phase 12's brief, repurposed), rather than creating/briefing a fresh
> one each time.

## Goal
Om tells Hermes "…"; `om-gate` sets up a DM room, invites `om-hermes` and asks `rahul-gate` to
join through the connection room; `rahul-gate` invites `rahul-agent` and hands it its own share
card. The two main agents plan directly in plain language.

## Tasks
- [x] Connection rooms: `conn-<a>-<b>` (sorted names), agent-only, members = the two gates. Created on first contact by whichever gate needs it; looked up by name afterwards.
- [x] Owner command `dm <friend> "<goal>"` (from Om, or from Hermes on his behalf via `tn mcp`'s `dm` tool):
  - check the friend is on the trust list;
  - create `dm-<a>-<b>-<slug>` agent-only (slug from the goal's day/keyword, e.g. `sun`; add `-2` if taken);
  - invite the owner's own main agent (`om-hermes`) to the room;
  - privately hand it a share card (phase 12's `write_brief`, posted to the owner's home room or delivered over `tn mcp` — not into the shared DM room);
  - post `@<friend>-gate join-dm <room> "<goal>"` in the connection room;
  - post "Planning with Rahul in <room>" to the home room/Hermes inbox.
- [x] Gate-to-gate `join-dm`: accept only in the matching connection room and only from the friend's gate (owner checked via Switch); join the room (invite or `connect_to_room`, per check 7); invite the owner's own main agent (`rahul-agent`) at **its own** trust level for the requester; hand it its own share card privately; relay "Om's agent is planning <goal> with you" to `rahul-home`.
- [x] Both gates sit in the DM room to answer `free`/`ask` and watch turns (a turn/time-limited `ConversationWatch`, same limits as the old phase 13 design — 12 turns or 10 minutes, then a summary and `archive_room`).
- [x] **New code surface needed here, not in phase 17/18:** unlike the dropped envoy lifecycle, there is no "create once, brief, invite" call for a long-lived main agent — just `invite_agent_to_room` for `om-hermes`/`rahul-agent` plus the private share-card handoff. `rahul-agent` itself must already exist as a managed Codex agent on `rahul-vm`, which this repo has no template for yet (phase 16 builds it, analogous to `templates/home.template.yaml`). Until phase 17/18 give Hermes `dm_read`/`dm_post` (phase 17) and `rahul-agent` is live, test and demo this phase with `tn --as om` / `tn --as rahul` CLI stand-ins that can read and post into a DM room directly.
- [x] Offline test with `FakeSwitch`: full setup flow creates exactly one conn room and one DM room with four members (two gates, two main agents); a `join-dm` from a non-friend agent is ignored; `rahul-agent`'s share card is at Rahul's level for Om (close), independent of what Om's side can see.

## Done when
- [x] `make check` passes.
- [x] Live (both gates may run on the laptop for now): Om's request to Hermes produces `dm-om-rahul-<slug>`; `om-hermes` and `rahul-agent` (or their CLI stand-ins) exchange at least 4 messages in plain language, visible in Switch Console. Transcript excerpt in *Log*.
- [x] Room strategy matches the decision from check 7 (noted in *Log*).

## Commit
`phase 14: connection rooms, dm setup and direct main-agent conversations`

## Log
<!-- evidence, deviations, notes -->

### Day-0 decision, 2026-11-05

Phase 04 room strategy: internal_only=True rooms with explicit cross-owner invitations work. Internal rooms remain visible in Console. Om/admin can also read Rahul private gifts, so gifts use courtesy seals. Phase 13b supplies the envoys. Do not depend on archive to reject writes. See docs/day0.md for evidence.

### No-envoy decision and main-agent swap, 2026-11-05

PLAN.md dropped envoys (main agents now talk directly in the DM room) and swapped main
agents: Om's is Hermes (`om-hermes`, via `tn mcp`), Rahul's is a managed Codex agent
(`rahul-agent`) on `rahul-vm`. `depends_on` changed from phase 13/13b to 11 (gate runtime) and
12 (share card, repurposed from the envoy brief) — the old envoy-lifecycle dependency no
longer applies. Two things this phase needs that don't exist yet, flagged for whoever
implements it: (1) `tn mcp` needs `dm_read`/`dm_post` tools (phase 17) before Hermes can carry
the plain-language side of the conversation; (2) there is no managed-agent template for
`rahul-agent`/`rahul-home` yet (phase 16) — `om-agent`'s `templates/home.template.yaml` is the
closest precedent but targets a Discord channel, not an agent-only Switch room. Until both
exist, build and demo this phase against `tn --as om`/`tn --as rahul` CLI stand-ins.

### Implementation and live evidence, 2026-11-05

Latest instruction supersedes the managed-Codex design above: both main agents are
Hermes, using separate Discord bots/profiles. Switch identities are `om-hermes` and
`rahul-hermes`; both fixtures use `consent.default: via-agent`. No envoy is started.
PLAN.md and other phases are left to the concurrent documentation pass.

Implemented `gate/dm.py`, runtime dispatch/watchers, explicit cross-owner invitations,
and `tn --as <person> dm-read <room>` / `dm-post <room> "<text>"`.
CLI reads SWITCH_URL and <PERSON>_GATE_KEY from the process environment; it retains
main-agent credentials in gitignored data/main-agents/<person>.json (0600). It resolves
room names or IDs against the authenticated agent's memberships and rejects non-DM
and archived rooms. Gate-to-gate join-dm and consent require the friend's gate identity,
verified Switch ownership, a trusted room membership, and the sorted connection name.
Consent remains a relay-only dispatch seam for phase 15; it never invokes owner yes.
The local identity exporter now maps UUID/transport aliases to server agent names,
so gate identity checks work on live events as well as FakeSwitch.

`uv run python -m scripts.dm_live_probe` drove the live exchange via the same
`tn.dm.operate` function as the CLI. It used retained gate credentials, refreshed
server identity metadata, and copies of fixtures under data/phase14-profiles.
Final DM: `68656dd7-bb6d-4d02-878c-96bfa6408edc`, four agents present.
Explicit invitations, internal_only=True, as phase 04 check 7 requires.
Transcript excerpt:

- om-hermes: "Om is vegetarian and likes bowling. Is Sunday at 9pm good after cricket?"
- rahul-hermes: "Rahul has cricket until 8:30. 9pm works; how about dinner afterwards?"
- om-hermes: "Budget is 1500 each. Dinner after bowling sounds good."
- rahul-hermes: "Agreed on a draft. We should ask both people before committing."

Both private share cards were delivered to their respective home inbox rooms,
with local 0600 JSON copies; no card appeared in the DM. Both gates reached 12
actual main-agent messages, posted short latest-message summaries to their home
rooms and archived the room. Switch emits main-agent join greetings, which also
count as main-agent messages. The stand-in refuses archived-room posts; gates
also stop answering there, including after restart via Switch's archived flag.
Earlier disposable DM probes were archived. The retained transcript is in Switch;
local raw evidence is gitignored data/phase14-live.log. The existing clock-driven
watch tests cover 600 seconds as well as 12 turns. Active watch counters are in
memory; process restarts reset active counters. Archive enforcement survives restart.

The earlier brief had already led to creating managed `rahul-agent` on rahul-vm
with both flags false, and `rahul-home` (`de6858ea-cfaf-4dce-9572-c7173a9e591c`).
It remains out of the flow. Its server agent/client identity aliases are
`5d7af283-cb55-449b-9ae2-d8e2f63d33b5` and
`76d4a6b9-ffce-426a-bd7f-eebc131f4bd0`. Approval investigation was cancelled by
Om's update; no claim about per-tool or plain-reply approval was verified.
Existing om-agent, gates and envoy registrations were preserved.

Phase 17 handoff interface:

- `post_home(person, text, client=gate)` is the canonical inbox delivery point.
  DM setup invites `<person>-hermes` to `<person>-home`; MCP inbox must read only
  that identity's home membership using its own credentials, returning message IDs
  for phase 15's pending ask/proposal correlation. Home rooms are gate-to-MCP
  inboxes; people answer through their own Hermes on Discord.
- Optional local card copy: `resolve_data_dir(person)/share-cards/<room UUID>.json`,
  mode 0600, fields `room`, `friend`, `agent`, `text`, `created_at` (ISO timestamp).
  The VM must receive copies if using this local interface across machines; the
  Switch home inbox is the network handoff and needs no file replication.
- MCP dm_read/dm_post should reuse `trustnet.tn.dm.operate`, whose access check
  scopes reads/posts to active DM memberships. No general Switch posting tool.

Phase 15 still owns inbox/answer/dm CLI commands, pending questions and proposal
state, personal-agent consent registration, gate consent relays and agreement-driven
closure/calendar writes. Both Hermes identities must be registered as permitted
personal agents when calling authorize for yes/no/answer. This phase's live setup
calls the gate setup function; the owner dm command is exercised end-to-end in
FakeSwitch. No full consent/calendar Scene 1 completion is claimed here.

Validation: `make check`: ruff format and lint passed; 455 pytest tests passed.
