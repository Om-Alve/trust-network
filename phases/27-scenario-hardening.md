---
id: "27"
title: Scenario hardening — many end-to-end scenarios, refined by Codex and DeepSeek
status: in-progress
priority: P1
owner: agent
depends_on: ["26"]
plan_refs: ["§3 Rules and commands", "§8 Security"]
target: Nov 6 evening
---

# 27 · Scenario hardening

## Goal
Exercise the whole system end to end in many scenarios (happy paths, refusals, races,
hostile peers, odd input), fix what breaks, and leave each scenario as a repeatable test.
Added 2026-11-06 at Om's request: "have Codex and OpenCode Go DeepSeek work on everything in
the codebase … refine it as much as possible."

Two areas, worked in parallel on separate branches, then merged:
- **A (Codex, gpt-6.1-sol):** planning rooms and consent: `dm`/`join-dm`, share cards, the
  handshake, `propose`/`answer`/`consent`, `ask-owner`, speak-first, room limits and archive,
  `RoomPool`, `PROTOCOL.md` §7a/§7b.
- **B (OpenCode, DeepSeek v4.1 flash):** facts and trust levels (`ask`, `free`, `view-as`,
  overreach notes, ledger), gifts and claims, ask-around, the `tn` CLI and `tn mcp` tools,
  `tn wake`, `PROTOCOL.md` §7c–§7e.

## Tasks
- [ ] A: scenarios written down (failure modes first), run in-process on `FakeSwitch` with the
  real gate code, bugs fixed, `PROTOCOL.md` kept true.
- [ ] B: the same for its area.
- [ ] Merged; live re-check of Scene 1 on the real Switch.

## Done when
- [ ] `make check` passes on the merged branch.
- [ ] Every scenario in both lists has a test or a written reason it can't have one.
- [ ] Scene 1 still passes live after the merge.

## Commit
`phase 27: <item>`

## Log
### A

### B
