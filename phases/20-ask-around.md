---
id: "20"
title: Ask around → Scene 3
status: done
priority: P1
owner: agent
depends_on: ["15"]
plan_refs: ["§4 Scene 3", "§3 commands `ask-around`"]
target: Nov 7 morning
---

# 20 · Ask around → Scene 3

## Goal
Om asks all his friends at once ("anyone have a tent for Nov 14–16?"). Each friend's gate answers from facts if it can, otherwise asks its person, and Om gets one summary.

> Note, 2026-11-05: ask-around was always gate-to-gate, never routed through an envoy or a main
> agent. After the main-agent swap, Om triggers this through his own Hermes (`ask_around` over
> `tn mcp`) on Discord, and Rahul's gate relays its "I don't know" case to `rahul-home`, where
> Rahul's own Hermes picks it up and relays it to Rahul on Discord.

## Tasks
- [x] Owner command `ask-around "<question>"` (≤140 chars): post `@<friend>-gate ask-around Ak "<question>"` into every connection room the owner has (creating conn rooms for listed friends if missing). Gate-to-gate transport; main agents trigger requests and judge relevance.
- [x] Receiving gate:
  - return quoted, level-filtered `has` and `recommends` profile facts without judging relevance;
  - label profile items as unconfirmed, never as a promise to lend;
  - if its person has a registered main agent, relay the quoted question to their home/inbox;
    their `answer Ak "…"` returns through their gate;
  - Priya has only a gate, so her profile reply needs no agent confirmation;
  - ledger entries on each side for disclosures.
- [x] Asker gate collects answers for up to N minutes and posts combined quoted updates in the home room as they arrive. Profile facts do not imply consent to lend.
- [x] Same flow covers recommendations ("a good dentist nearby?" → `recommends.dentist`).
- [x] Offline tests: Priya answers from facts without asking; Rahul's side asks its person; a close-level `has` fact is not used in a friend-level conn room.

## Done when
- [x] `make check` passes, or only parallel phase 17 lint remains with owned paths clean.
- [x] **Scene 3:** live Om/Priya plus offline three-gate flow. Om's tent request, via his own Hermes on Discord (or directly in `#om-home`) → Priya's gate answers instantly → Rahul's own Hermes relays the question to him on Discord (or `tn --as rahul inbox` stands in) and he says "no, sorry" → Om's Hermes tells him the combined summary (or it shows in `#om-home`). Evidence in *Log*.

## Commit
`phase 20: ask around (Scene 3)`

## Log
<!-- evidence, deviations, notes -->

### No-envoy decision and main-agent swap, 2026-11-05

No mechanics changed — ask-around was always gate-to-gate. Updated the demo narrative: Om now
asks through Hermes, and Rahul now answers directly in `rahul-home` rather than via Hermes on
Telegram, following the Nov 5 main-agent swap.

### Both on Hermes, on Discord — 2026-11-05

Superseded the above the same day: Rahul's answer no longer goes through `rahul-home` to a
managed `rahul-agent` — it goes to his own Hermes (`rahul-hermes`), which relays to him on
Discord and relays his "no, sorry" back. Mechanics unchanged.

### Implementation evidence, 2026-11-05

- Added `personal.ask_around(person: str, question: str)` and CLI `tn --as om ask-around "…"`.
  `personal.answer(person, id, text)` now accepts `A<n>` references as well as Q/P references.
- Persistent request IDs, five-minute reply window, gate-only connection relays, quoted text,
  room-level filtering, per-person inbox prompts, combined home updates and both-side ledgers.
- `uv run python -m scripts.e2e_scene3` passed. Artifact:
  `data/scene3-offline-1793887756915813000/artifact.json`. Exercises three gates,
  Rahul's `answer`, close inventory hidden at friend level, stranger silence, forged reply
  rejection and oversized text rejection. Uses the fake Switch protocol harness, not live transport.
- `uv run python -m scripts.e2e_scene3 --live` passed against local Switch with Om and Priya.
  Artifact: `data/scene3-live-1793887740321548000/artifact.json`.
  Rahul VM `systemctl --user is-active rahul-gate.service` returned `active`.
  No local Rahul gate was started and the VM service was not stopped.
  Live commands use the shared personal functions as Hermes/CLI stand-ins.
  Newly created connection rooms are archived in finally; existing rooms are retained.
- `make check`: 455 passed before final documentation edits; rerun before commit.

Design decision accepted by Om: AGENTS.md forbids regex/keyword bandaids for judging meaning.
Gates remain LLM-free and keyword-free. They return raw quoted, level-filtered `has`/`recommends`
items; the asker's main agent judges relevance. Profile items are not promises to lend.
Only recipients with a registered main agent get a home question relay. Priya has a gate only.
The live Rahul branch and actual Discord interaction remain unverified; the accepted offline
three-gate run covers Rahul's inbox/answer branch while his VM service remains running.

Phase 17 handoff: `tn mcp` tool `ask_around` must describe answers as raw quoted profile items.
Hermes decides relevance and must never treat a listed item as a promise to lend.
Signature: `async personal.ask_around(person: str, question: str)` returns the Switch
`post_message` result. `personal.answer(person, id, text)` accepts A IDs.

Final artifacts after applying the accepted design:
- Offline: `data/scene3-offline-1793887839698305000/artifact.json`.
- Live: see final verification entry below.

Final verification: `make check` passed, 455 tests. Live accepted-design artifact:
`data/scene3-live-1793887858519702000/artifact.json`. Probe connection rooms archived.
