---
id: "24"
title: Video and submission
status: todo
priority: P0
owner: human
depends_on: ["23"]
plan_refs: ["§10 Demo video", "§12 Code with Wispr", "header (deadlines)"]
target: Nov 7 — submit by 20:00 IST (hard close 23:59 IST)
---

# 24 · Video and submission

## Goal
A 3-minute video following PLAN.md §10, and a submission in by **20:00 IST on Nov 7**.

## Tasks
- [ ] **[human]** Dictate and time the video script with Wispr (Nov 7 morning). Agent can draft beat timings from §10 into `docs/video-script.md`.
- [ ] **[human]** Record each scene separately (`demo_reset.py` between takes): hook, cast, outing (split Discord / Console / phone), gift, ask around, overreach + view-as, close slides (room map, three-factor table, "we wrote zero AI agents", Switch features).
- [ ] **[human]** Edit to ≤ 3:00. If over, cut ask-around first (§11).
- [ ] **[human]** Screenshot the Wispr Flow **Insights** tab right before submitting.
- [ ] Final repo pass: README links to the video; tag `v1.0-submission`.
- [ ] **[human]** Submit to Track 02 + Code with Wispr.

## Done when
- [ ] Video ≤ 3:00, uploaded, linked from the README.
- [ ] Wispr Insights screenshot attached to the submission.
- [ ] Submission confirmation received before 20:00 IST Nov 7 (time noted in *Log*).
- [ ] PLAN.md §12 checkboxes ticked.

## Commit
`phase 24: link demo video, tag submission`

## Log
<!-- evidence, deviations, notes -->

### Both on Hermes, on Discord — 2026-11-05

Cast for this video is now: Om on his own Hermes, in Discord; Rahul on his own Hermes, a second
Discord bot/account Om records from; Priya's gate. No Telegram, no managed Codex main agent.
`docs/video/script.md` is updated in full to match (every beat, the shot list and the
teleprompter), still ≤ 3:00. This phase's own tasks/Done-when are unaffected — they just point at
whatever `docs/video/script.md` says to record.

### Ready to record — 2026-11-06 17:35 IST (agent)
Beats 3–6 run live through both Hermes on the merged code: outing + consent (P1 confirmed both
sides, both calendars), gift (Lego Millennium Falcon claimed, Om's side silent), ask-around (Priya's
gate instant, Rahul "A1: no, sorry"), overreach (address refused, Om's Hermes relays it). Fixes found
on the way: claim matching ignores case and names what can be claimed; short ask-around refs (A1);
`inbox` lists open items; a stale A-ref answer is refused out loud; `scene_reset.sh --deploy`
restarts the demo Hermes gateways (their `tn mcp` servers had run ~20 h on old code). Script
updated: "via agent", one side proposes, Lego set, no budget-question line, plus a *Recording notes*
table of exactly what each person types.

