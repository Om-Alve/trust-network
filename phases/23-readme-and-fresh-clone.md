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
  3. How it works: cast, room map and machine map (§2);
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
