---
id: "28"
title: Your agent adds private facts and requests sharing
status: done
priority: P1
owner: agent
depends_on: ["27"]
plan_refs: ["§3 Rule 3"]
target: Nov 6
---

# 28 · Agent facts

## Tasks
- [x] Write and run FakeSwitch scenarios before implementation.
- [x] Add private-only creation and visibility requests through CLI and MCP.
- [x] Add consent, expiry, decline, inbox and ledger support.
- [x] Update skill, protocol and trust rule.

- [x] Add the setup prompt, T suggestions, bulk review and fake-memory E2E.

## Done when
- [x] All seven requested E2E behaviors pass with a saved artifact.
- [x] Owner approval, stale requests, replay and malformed input are exercised.
- [x] `make check` passes and this phase is committed.

## Commit
`phase 28: the agent adds facts (private) and asks before sharing them`

## Log
Scenarios written first: private phone must stay hidden on add and while F1 is
pending; approving F1 via agent must change both view-as and a real gate ask.
Declined and expired refs must never apply. Direct consent must refuse the agent
but permit the owner. Duplicate creation must preserve the old value. Tightening
must apply immediately. Replays and changed facts/audiences must refuse approval.
Invalid keys, oversized values and malformed YAML must leave the profile unchanged.

Security: with via-agent consent, a fully fooled agent could create and approve
its own F ref. This is the same trust as plan consent today. Use the stricter
`consent.default: direct` owner mode when consent must come from the owner.

Added scope before implementation: setup prompt scans only the person's own memory;
private additions plus F suggestions and T trust suggestions wait for review.
Bulk review approves all selected refs independently, preserving an excluded ref.
T approval must be the first write of the suggested trust entry. Fake memory E2E
must show no new disclosure before consent and exactly approved facts afterward.
Suggestions live seven days so onboarding can be reviewed later. Secret exclusion
is primarily an explicit agent instruction; length limits cannot identify secrets.

Implementation and evidence:
- The first E2E run failed before implementation with `Unknown tool: fact_add`.
  Artifact: `/var/folders/4w/mkzvkfmx46gbh1y1zn4mqcpw0000gn/T/trustnet-phase28-bp04xke6/report.json`.
- Added owner-local persistence for F/T refs, seven-day TTL, monotonic IDs,
  per-person locking, replay refusal, stale value/level/audience checks and
  a shared pure consent decision in `policy.py` using the existing plan policy.
- Added private creation, visibility requests, trust suggestions, review and
  bulk approval/decline through MCP and CLI. Switch user yes/no/answer accepts
  F/T refs. Approved refs have individual before/after ledger entries.
- `setup` is an MCP prompt, advertised in server instructions and SKILL.md.
  Keys use the ask grammar, capped at 64 characters; values at 16,384 characters;
  reasons at 280. YAML must be JSON-compatible. These checks do not classify
  secrets; the prompt and skill explicitly forbid storing credentials and IDs.
- Two FakeSwitch E2E scenarios exercise all seven original cases plus memory
  onboarding, bulk approval with an exclusion, T approval, two-day review delay,
  direct owner CLI/Switch approval, stale values/audiences, replay and bad inputs.
  They also run in pytest through `tests/test_agent_facts_scenarios.py`.
- `make check`: ruff format and lint passed; **511 passed**.

Deviations and limits:
- All suggestion refs expire after seven days, including ordinary F requests,
  rather than splitting onboarding and ad hoc requests into different TTLs.
  This gives the person time to review the single onboarding summary.
- The existing owner-only mode is named `direct`; no new `owner` alias was added.
- Unpriced wishes use private `wishlist_notes`, because existing gift requests
  require wishlist maps with numeric prices. The prompt never invents a price.
- Bulk changes run in supplied order and stop on refusal. Earlier successful
  refs remain recorded; review again after changing an audience.
- Profile, request and ledger files are separate writes, as with existing plan
  state. Crash recovery across those writes is not transactional.
- The first `make check` invoked the existing MCP test which wrote its artifact
  under `data/mcp-e2e`. That test now writes under pytest's temporary directory;
  the new runner always writes outside `data/`. No profiles, running gates,
  services or deployments were changed. AGENTS.md was not staged or committed.

Final repeatable artifact:
- Command: `uv run python scripts/e2e_agent_facts_scenarios.py`.
- Result: PASS for original fact/consent and fake-memory onboarding flows.
- Artifact: `/var/folders/4w/mkzvkfmx46gbh1y1zn4mqcpw0000gn/T/trustnet-phase28-3qvlcxmq/report.json`.
