---
id: "26"
title: Agent protocol — spec, gate handshake, any-agent runner
status: done
priority: P1
owner: agent
depends_on: ["18"]
plan_refs: ["§3 Rules and commands", "§9 Cut lines"]
target: Nov 6 afternoon
---

# 26 · Agent protocol — spec, gate handshake, any-agent runner

## Goal
Turn trust-network from "two Hermes bots" into an agent-to-agent protocol any agent can speak:
a written spec, a versioned handshake between gates, and proof that different agent
frameworks plan together (Om's Hermes ↔ Priya's Codex) with the same consent rules.

Added 2026-11-06 at Om's request ("turn it into a complete agent-to-agent communication
solution"); scope chosen: spec + handshake + a second framework.

## Tasks
- [x] `PROTOCOL.md`: roles (person, agent, gate), transport (Switch rooms), identity, rooms,
  the full message grammar, flows (plan, consent, questions, gifts, ask-around), security
  properties, versioning, and how to bring a new agent framework.
- [x] Gate handshake: `hello trust-network/<major> <capabilities>` exchanged in the gates'
  connection room; a gate refuses to open or join a planning room with a peer gate that hasn't
  said a compatible hello.
- [x] `tn wake`: an agent-agnostic runner. Polls `tn watch`, wakes any CLI agent on news, and
  lets the person talk to their agent in the same terminal. Preset for Codex.
- [x] Priya's agent runs on Codex through `tn mcp` (`examples/priya/agent.md` persona).
- [x] E2E: Om's Hermes plans with Priya's Codex agent; both people say yes; confirmed on both
  sides; artifact in `data/`.

## Done when
- [x] `make check` passes.
- [x] A Hermes ↔ Codex plan is confirmed end to end, with both people's yes; transcript saved.
- [x] A gate without a compatible hello is refused (test).

## Commit
`phase 26: <item>`

## Log
<!-- evidence, deviations, notes -->
- Switch sets an agent's profile (`description`) only at registration (`register-known` →
  409 for an existing name; `update_agent_detail` on itself → 403), so gates can't publish a
  card on their profile. The card is exchanged as a `hello` handshake instead.
- The agent slot keeps the Switch name `<person>-hermes` whatever framework fills it
  (renaming would re-register both live Hermes); the spec calls it the person's agent.
- Codex: `codex exec` refuses MCP tool calls unless the server sets
  `default_tools_approval_mode="approve"` (passed with `-c`, user config ignored).
- **Hermes ↔ Codex E2E passed — 2026-11-06 14:44 IST.** `tn --as priya wake --agent codex`
  (gpt-6.1-sol) as Priya; Om's Hermes (om profile) as Om. Om's Hermes opened the room; Priya's
  agent offered Mon 9 Nov 19:30 and asked for a venue; Om's offered Dialogues ₹700–900; Priya's
  narrowed it to ₹700–800; Om's agreed and proposed P1 through om-gate, forwarded to priya-gate.
  Priya typed `yes` in her terminal, Om said yes to his Hermes. Both home rooms:
  `✅ P1: 2026-11-09T19:30:00+05:30 120m "Board games evening" @ "Dialogues, Koramangala" · Om ✅ via Hermes · Priya ✅ via Hermes`;
  both calendars have it. Artifact: `data/phase26-hermes-codex-20261106-1444.txt`.
- Bugs the E2E found, fixed in this commit:
  - Pool: a sync whose room listing predates a new room released that room's fresh anchor, so
    posts fell back to the main connection's room. Now only rooms the listing shows archived or
    past the cap are released.
  - Pool: a script connecting with a gate's key moved the gate's room session; when it closed the
    gate had none (`no_session`, posts failed). The pool now checks itself `live` before posting
    and every 30 s, and reconnects.
  - A refused own-side answer (consent set to `direct`) was silent, so Priya's agent reported a
    yes that was never recorded. The gate now says why in the room.
  - The share card still told agents to propose through both gates and named the friend's gate
    (`@priya-gate …`), which Switch flagged in the home room. It now says own gate only.
  - The confirmation said "via Hermes" for any agent; now "via agent".
- Deviation: Priya's example consent default `direct` → `via-agent` (she now has an agent and
  no Switch user to answer directly from).
- Handshake: `tests/test_handshake.py` (written first): hellos both ways open the room;
  `join-dm` without a hello, or with `trust-network/2`, is refused with a plain-text line in the
  connection room and a home notice; hello is accepted only from the friend's gate in their
  `conn-<pair>` room; a forwarded proposal from a peer without a hello isn't recorded. A
  `hello` that isn't the handshake form ("hello there") stays an unknown command, as it
  was before the handshake, rather than becoming a malformed one. Peers live in `peers.json` (cleared by
  `demo_reset`). Live, laptop: om-gate and priya-gate recorded each other's
  `trust-network/1` hello in `conn-om-priya`. A pre-handshake gate (the VM before deploy) reads
  hello as an unknown command and notes it as overreach, then accepts `join-dm`: rollout
  needs both gates on the same commit.
- `PROTOCOL.md` (v1 spec, drafted by a Sonnet docs agent from the code, reviewed here): roles,
  transport, rooms, grammar, handshake/versioning, five flows, security properties, how to bring
  a framework, known limits. `tests/test_skill_doc.py` now parses every command line in it
  (code blocks and inline) so the spec can't drift from the parser. The review also found the
  gate's unknown-command reply listed five commands ("others arrive in later phases"); it now
  lists them all and points to PROTOCOL.md.
- Known v1 limits are listed in PROTOCOL.md §10 (e.g. `counter` parses but has no handler;
  ask-around and gift rooms don't check the handshake; capabilities are recorded, never read).
- `make check`: 474 passed.
- Follow-up: `tn wake --agent opencode` (DeepSeek, `opencode-go/deepseek-v4.1-flash`) runs OpenCode on a private
  `XDG_CONFIG_HOME` config with only the `tn mcp` server and its shell/file/web tools denied
  (checked: `ls /` and reading `/etc/hosts` both refused, trustnet tools work). The Codex
  preset now runs without its shell tool and web search.
