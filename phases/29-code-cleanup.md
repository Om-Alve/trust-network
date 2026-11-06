---
id: "29"
title: Remove unused code and simplify agent access
status: done
priority: P1
owner: agent
depends_on: ["28"]
---

# 29 · Code cleanup

## Tasks
- [x] Capture the existing check and scenario baseline before editing.
- [x] Remove unused transport code and consolidate DM access.
- [x] Render the current share card directly without rewriting an envoy prompt.
- [x] Review practical deployment gaps separately from structural changes.

## Done when
- [x] CLI and MCP behavior checks pass with `make check`.
- [x] Existing scenario runners pass and save repeatable evidence.
- [x] Delivered share-card text matches the captured baseline.

## Commit
`phase 29: remove unused code and simplify agent access`

## Log
Baseline `make check` passed with 507 tests. Planning scenarios passed 8/8,
facts scenarios passed 10/10, and both agent-fact scenarios passed.
Evidence is in `data/cleanup/` and the scenario directories recorded there.

The data shapes remain the existing typed commands, room memberships and
per-person state. This phase changes ownership of existing code only.
Verification uses the existing scenario runners rather than new unit tests.

Final checks passed with 506 tests and 20 scenario flows. One prose snapshot
was removed per the project rule against change-detector tests. Delivered card
text is equivalent except one trimmed trailing space. DeepSeek Flash reviewed
the diff and evidence with no blocking findings. Its stale-comment findings
were corrected. Scenario transcripts and the TSV trail under `data/cleanup/`
are local-only artifacts. Reproduce them with:

```sh
make check
uv run python scripts/e2e_planning_scenarios.py
uv run python scripts/e2e_facts_scenarios.py
uv run python scripts/e2e_agent_facts_scenarios.py
```
