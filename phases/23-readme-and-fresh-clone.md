---
id: "23"
title: README and fresh-clone test
status: todo
priority: P0
owner: human + agent
depends_on: ["22"]
plan_refs: ["§1 Why this matters", "§2 maps", "§6 Safety model + known gaps", "§7 Switch features table", "§9 Nov 7 afternoon", "§12 Code with Wispr"]
target: Nov 7 afternoon
---

# 23 · README and fresh-clone test

## Goal
A README a judge can follow from a clean clone, which also tells the story. Then prove it by following it.

## Tasks
- [ ] **[human]** Om dictates the README prose with Wispr; the agent assembles structure, tables and code blocks.
- [ ] README sections:
  1. One line + why it matters (PLAN.md §1, Instinct comparison);
  2. Demo video link + screenshots;
  3. How it works: cast, room map and machine map (§2) — main agents (Hermes on Discord for both Om and Rahul, each their own profile) talk directly in DM rooms; no envoys, no managed Codex main agent;
  4. Trust model: levels table and the seven rules (§3);
  5. Safety model: three-factor table and **known gaps**, stated plainly (§6);
  6. Switch features used (§7 table);
  7. Run it: two-machine layout (Tailscale Serve) and one-machine layout; `demo_up.py`; Mattermost fallback if no Discord bot;
  8. Project layout and `make check`;
  9. What's next (P2 list).
- [ ] Folding in `docs/setup-laptop.md`, `docs/setup-vm.md`, `docs/day0.md` findings where relevant.
- [ ] Fresh-clone test: `git clone` into a temp dir, follow the README word for word on the one-machine layout, fix every step that's wrong or missing.

## Done when
- [ ] `make check` passes on the fresh clone.
- [ ] The fresh-clone run reaches Scene 1 (CLI version) using only README instructions; each fix made is listed in *Log*.
- [ ] Known gaps from PLAN.md §6 all appear in the README.
- [ ] No secrets, tailnet names, or personal tokens in the repo (`git grep` for key prefixes and `.ts.net` returns nothing sensitive).

## Commit
`phase 23: README and fresh-clone fixes`

## Log
<!-- evidence, deviations, notes -->

### No-envoy decision and main-agent swap, 2026-11-05

This phase pulls its cast/room-map and safety-model content from PLAN.md §2 and §6, both
updated for the Nov 5 no-envoy decision and main-agent swap (Om ↔ Hermes, Rahul ↔ `rahul-agent`).
No other change needed here beyond sourcing the current versions of those sections and making
sure the README's known-gaps list includes the new "main agent overshares beyond the level" gap.

### Both on Hermes, on Discord — 2026-11-05

Superseded the `rahul-agent` framing above the same day: PLAN.md §2 and §6 now describe **both**
Om and Rahul on their own Hermes, on Discord, with no managed Codex main agent anywhere. This
phase's cast/room-map/safety-model sourcing is unaffected in mechanism — still "pull current §2
and §6" — but the README's known-gaps list should now read the no-per-message-check gap as
symmetric across both sides, per §6.
