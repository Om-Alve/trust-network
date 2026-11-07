# Product acceptance contract

The personal agent owns external calendar access. The gate owns consent and a
durable delivery request. No Google or Outlook adapter is needed in the gate.

Two designs were considered: invoke provider APIs in the gate, or hand approved
operations to the existing agent and require a receipt. The latter preserves the
user's accounts and tools and makes incomplete delivery visible. Retrying an
external write requires searching for its stable event marker before creating it.

## Calendar delivery failure cases, written before implementation

- One approval must not enqueue an event; two approvals must enqueue one per owner.
- A restart or duplicate confirmation must not create another delivery request.
- Consuming the inbox must not consume an unfinished calendar task.
- A provider failure must remain visible and retryable, without claiming delivery.
- A receipt for an older event revision must not acknowledge the current revision.
- Updating or cancelling must retain the provider event reference and stable marker.
- The agent must not create a second event after a crash between provider write
  and local acknowledgment. It must look up the marker before retrying.
- An all-day unavailable event must block the whole local day, including DST days.
- Transparent or cancelled all-day events must remain free.
- A configured timezone must apply to floating calendar times and natural dates.

## Ownership

`gate/calendar_jobs.py` stores provider-independent requests and receipts in the
owner's SQLite database. `calendar_tasks` and `calendar_report` are the agent
interface. `inbox` and `watch` retain pending work independently of message cursors.
New connections choose agent delivery; existing unconfigured profiles retain ICS.

The complete acceptance runner is `uv run python scripts/e2e_product.py`.
Its report contains approvals, delivery tasks, receipts and calendar blocks.
External provider behavior is simulated; a live provider write requires the
owner's configured agent and calendar account.

The product runner passed four scenarios on 2026-11-07. The report is
`data/product-e2e-20261107T045558844043Z/summary.txt`. `make check` passed 536 tests
with formatting and lint checks. No external calendar accounts were modified.

The integrated sharing pass adds a fifth product scenario for blocked pending
approvals and gift denials. It also checks that replaying an older calendar
operation cannot replace a later revision. `scripts/e2e_sharing.py` passed five
sharing scenarios in `data/scenarios-sharing-20261107T051615796082Z/`; the product
report is `data/product-e2e-20261107T051740033399Z/`. `make check` passed 549 tests.

## Outgoing messages

`TN_OUTGOING=review` keeps exact outgoing DM text in an owner-local outbox until
`tn outbox approve` releases it. MCP has no release tool. Revoking a friend also
blocks the personal-agent API's existing DM room. Automatic mode still depends
on the personal agent's judgement. Local shell access, direct Switch clients,
and separate messaging tools remain inside the owner's trusted environment.

## Group lifecycle verification

The production runtime now dispatches group requests and relays after identity
and membership checks. Tests do not replace that dispatch path. Every mutation
requires the exact current revision and fingerprint; only the organizer drafts
replacements. Votes cannot carry across revisions. Pending offers and replies
use canonical UTC content, independent of each gate's local timezone. Legacy
pairwise ISO offsets are preserved so consent fingerprints also match across
timezones.

`make check` passed 560 tests. `scripts/e2e_group_plans.py` passed nine scenarios,
including forged/stale votes, cancellation, delayed replies, interrupted delivery,
and revocation of queued relays. Its report is
`data/group-plans-20261107T060304077011Z/summary.txt`.
`scripts/e2e_product.py` passed seven scenarios; its three-person lifecycle checks
the real calendar task queue and MCP receipts through creation, replacement,
restart and cancellation. Its report is
`data/product-e2e-20261107T060517751426Z/summary.txt`.
Calendar provider operations are simulated, with stable provider event IDs.
No external accounts were modified. New group lifecycle tools do not convert
legacy confirmed P plans automatically.
