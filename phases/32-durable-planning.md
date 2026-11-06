---
id: "32"
title: Recover approvals, deliver calendars and revise plans
status: done
priority: P1
owner: agent
depends_on: ["29"]
---

# 32 · Durable planning

## Tasks
- [x] Write and run E2E failure scenarios before implementation.
- [x] Persist approvals and delivery work together.
- [x] Recover fact approvals across profile, request and ledger writes.
- [x] Deliver confirmed plans once to each owner's calendar.
- [x] Implement counter proposals and invalidate superseded votes.

## Done when
- [x] Interrupted votes and delivery recover after restart without another yes.
- [x] Calendar replay produces exactly one event per approved plan per owner.
- [x] Old votes cannot confirm a superseded plan.
- [x] Fact approval recovery leaves one applied decision and one ledger record.
- [x] E2E artifacts and `make check` pass.

## Commit
`phase 32: recover approvals and deliver revised plans to calendars`

## Log
Failure boundaries include a saved vote without a relay, confirmation without a
calendar event, a successful external write without a saved acknowledgment,
profile changes without a ledger record, stale votes after a revision, and a
truncated calendar file. Scenarios must exercise these boundaries on temp data.

Scenarios were written first and all five initial flows failed before product
changes. The final twelve flows passed, including real os._exit process deaths
following profile, trust and ledger writes; retries after successful delivery;
legacy saved-vote migration; unavailable home notifications; and a duplicate
gate process refusing startup. Existing planning scenarios still enforce timed
room closure and replay refusal.

Design comparison chose per-owner SQLite decisions with pending effects over a
shared JSON journal. SQLite commits accepted state and jobs together. JSON is a
repairable compatibility projection. Calendar and ledger outputs use stable IDs
and locked atomic replacement. A per-owner gate process lock serializes planning
writers. Fact approvals retain their existing interprocess edit lock.

Review caught a counter race, unbounded retry feedback and stale legacy votes.
The initiating person must not have voted; failed jobs have a retry deadline;
legacy votes seed relay jobs. Failed notifications do not block calendar work.
Remote messages and documents have at-least-once semantics. Their transport has
no demonstrated idempotency key; local calendar and approval ledger projections
are idempotent. Resource/provider calendar adapters remain separate work.

Local artifacts are under `data/scenarios-durable-20261106T183035690371Z/`.
Repeat with `uv run python scripts/e2e_durable_scenarios.py` and `make check`.
The full check passed with 518 tests including final documentation cleanup.

Final review also required original-offer delivery before a counter and a fresh
trust read under the fact-edit lock. The extra E2Es verify both ordering cases.
