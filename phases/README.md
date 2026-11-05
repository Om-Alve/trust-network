# Phases

`PLAN.md` split into commit-sized phases. Each phase file says what to build, which parts of `PLAN.md` it covers, and the conditions that must hold before it counts as **done**.

## How agents use this folder

1. **Pick work.** Choose the lowest-numbered phase with `status: todo` whose `depends_on` phases are all `done` (or `skipped`). Phases with no dependency on each other can run in parallel. The graph below shows which.
2. **Claim it.** Set `status: in-progress` in the phase's front matter before you start.
3. **Track progress.** Tick task checkboxes (`- [x]`) as you finish them.
4. **Finish it.** A phase is `done` only when **every** item under *Done when* holds. Paste the evidence (command output, screenshot path, room name) into the phase's *Log* section. If a condition can't be met, set `status: blocked` and write why in *Log*.
5. **Commit.** One commit per phase (a phase may take 2–3 commits if it grows, but never mix phases in one commit). Use the message in the phase's *Commit* section.
6. **Human steps.** Tasks marked **[human]** need Om (accounts, clicks, devices, dictation). Agents prepare everything around them and stop with `status: blocked` and a short ask in *Log*.

See every phase's status at once:

```sh
grep -H '^status:' phases/[0-9]*.md
```

Front matter is the single source of truth for status. The index table below has no status column on purpose, so the two can't drift apart.

## Every phase is done only if (in addition to its own conditions)

- `make check` passes (ruff format check, ruff lint, pytest). This applies from phase 01 onwards.
- No secrets in git: keys live in `.env` (gitignored), never in YAML, fixtures, or logs.
- The phase file's front matter `status` and *Log* are updated in the same commit.
- Anything that differs from `PLAN.md` is written in *Log* under "Deviations", and `PLAN.md` gets updated too if the change matters beyond this phase.

## Index

| # | Phase | Priority | Owner | Depends on | Target window |
|---|---|---|---|---|---|
| 01 | [Scaffold and dev tooling](01-scaffold-and-tooling.md) | P0 | agent | – | Nov 5 evening |
| 02 | [Infrastructure and Day-0 checks 1–3, 12](02-infra-day0-checks.md) | P0 | human + agent | – | Nov 5 evening |
| 03 | [Switch protocol client + fake Switch](03-switch-client.md) | P0 | agent | 01 | Nov 5 evening |
| 04 | [Day-0 protocol checks 4–10](04-day0-protocol-checks.md) | P0 | agent + human | 02, 03 | Nov 5 night |
| 05 | [Fixtures and profile loading](05-fixtures-and-profiles.md) | P0 | agent | 01 | Nov 6 morning |
| 06 | [Calendar](06-calendar.md) | P0 | agent | 05 | Nov 6 morning |
| 07 | [Policy engine](07-policy.md) | P0 | agent | 05, 06 | Nov 6 morning |
| 08 | [Ledger and view-as](08-ledger-and-view-as.md) | P0 | agent | 07 | Nov 6 morning |
| 09 | [Command parser](09-command-parser.md) | P0 | agent | 05 | Nov 6 morning |
| 10 | [`tn` CLI (offline commands)](10-tn-cli.md) | P0 | agent | 06, 07, 08 | Nov 6 morning |
| 11 | [Gate runtime: `free` / `ask` live](11-gate-runtime.md) | P0 | agent + human | 03, 04, 07, 08, 09 | Nov 6 morning |
| 12 | [Share card (was: envoy brief, repurposed Nov 5)](12-envoy-brief.md) | P0 | agent + human | 07, 08 | Nov 6 afternoon |
| 13 | [Envoy lifecycle (managed agents) — skipped, superseded by the no-envoy decision](13-envoy-lifecycle.md) | P0 | agent | 04, 11, 12 | Nov 6 afternoon |
| 13b | [Fallback envoy runner — built, unused after the no-envoy decision](13b-fallback-envoy-runner.md) | P0 if needed | agent | 04, 11, 12 | Nov 6 afternoon |
| 14 | [DM rooms between main agents](14-dm-rooms.md) | P0 | agent | 11, 12 | Nov 6 afternoon |
| 15 | [Ask-your-person and consent → Scene 1 via CLI](15-ask-owner-and-consent.md) | P0 | agent | 14, 10 | Nov 6 afternoon |
| 16 | [Azure VM: om-hermes, rahul-gate, rahul-agent](16-rahul-on-vm.md) | P1 | human + agent | 15 | Nov 6 night |
| 17 | [`tn mcp` server](17-tn-mcp.md) | P0 | agent | 15 | Nov 6 night |
| 18 | [Hermes, Telegram and `SKILL.md` → Scene 1 on Telegram](18-hermes-and-skill.md) | P0 (P1 if it slips) | human + agent | 17 | Nov 6 night |
| 19 | [Gift rooms and surprise mode → Scene 2](19-gifts-surprise-mode.md) | P1 | agent | 15, 17 | Nov 7 morning |
| 20 | [Ask around → Scene 3](20-ask-around.md) | P1 | agent | 15 | Nov 7 morning |
| 21 | [Overreach alerts](21-overreach-alerts.md) | P1 | agent | 11 | Nov 7 morning |
| 22 | [Demo bootstrap and one-machine layout](22-demo-bootstrap.md) | P0 | agent | 15 | Nov 7 morning |
| 23 | [README and fresh-clone test](23-readme-and-fresh-clone.md) | P0 | human + agent | 22 | Nov 7 afternoon |
| 24 | [Video and submission](24-video-and-submission.md) | P0 | human | 23 | Nov 7, submit by 20:00 IST |
| 25 | [P2 stretch goals](25-p2-stretch.md) | P2 | agent | 18 | only if time is left |

## Dependency graph

Each layer can start once the phases it names are done. Phases in the same layer can run in parallel.

```
Layer 0  01 scaffold            02 infra (human, runs beside everything up to 04)
Layer 1  03 switch client  ← 01         05 fixtures      ← 01
Layer 2  04 protocol checks ← 02,03     06 calendar      ← 05     09 commands ← 05
Layer 3  07 policy         ← 05,06
Layer 4  08 ledger/view-as ← 07
Layer 5  10 tn CLI         ← 06,07,08   11 gate runtime  ← 03,04,07,08,09   12 share card ← 07,08
Layer 6  13 envoy lifecycle — skipped (unused)           21 overreach ← 11
         13b fallback envoy runner — built, unused after the no-envoy decision (2026-11-05)
Layer 7  14 DM rooms (main agents) ← 11,12
Layer 8  15 consent, Scene 1 via CLI ← 14,10
Layer 9  16 VM ← 15   17 tn mcp ← 15   20 ask-around ← 15   22 demo bootstrap ← 15
Layer 10 18 Hermes ← 17   19 gifts ← 15,17   23 README ← 22
Layer 11 24 video + submit ← 23   25 P2 ← 18
```

**Critical path to P0 (Scene 1):** 01 → 03 → 04 → 11 → 12 → 14 → 15 → 17 → 18 → 22 → 23 → 24.
**Parallel work:** 02 runs beside 01/03 (it's mostly Om's clicks). 05–10 are offline modules with no Switch dependency, so they can run beside 03/04.

## Cut lines (from PLAN.md §9)

If time runs short, drop in this order: 25 → 21 → 20 → 19 → 16 (Rahul's controller then runs on the laptop) → 18 (Rahul is driven by `tn --as rahul` instead of Hermes). Never cut 01–15, 22–24.
