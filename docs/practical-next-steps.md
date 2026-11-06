# Practical next steps

The strongest first use case is making a plan between two people who already
trust each other. Equipment lending can reuse ask-around, but an inventory match
must remain separate from permission to lend. Gift coordination works within a
shared workspace when participants accept that its administrator can read rooms.

These are open engineering issues, ordered by their effect on that first use case.
They are outside the behavior-preserving cleanup in phase 29.

## TN-01 · Complete the calendar handoff

`trustnet/gate/consent.py` confirms a proposal and creates a room document after
both approvals. It does not call `calendar.add_event`. The calendar write is a
separate CLI/MCP action. The README's claim that approval lands a plan on both
calendars therefore depends on the agents performing that action afterward.

Make confirmation produce a durable calendar-write job per owner. Use a stable
event UID so retries do not duplicate bookings. Keep provider adapters behind
that job so local ICS, Google Calendar and Outlook can share the consent flow.

Acceptance requires an E2E run that approves both sides, restarts between
confirmation and delivery, and finds exactly one event in each calendar.

## TN-02 · Recover interrupted approvals

`trustnet/gate/consent.py` saves votes before sending the consent relay. A crash
after saving can leave a peer waiting, while a repeated vote is refused.
`trustnet/gate/fact_changes.py` also writes profiles, request state and ledger
entries separately. Its lock prevents concurrent edits but does not make those
writes transactional.

Use transactional local storage and an outbox for external effects. Verify by
killing the process between each durable write and message send. Restart must
converge on one decision and one disclosure record without a missing relay.

## TN-03 · Install outside the checkout

`pyproject.toml` packages Python modules, while `brief.py` loads a template from
the repository's `templates/` directory. `wake.py` also reads the repository's
skill and watcher prompt. A wheel installed elsewhere lacks those files.

Package runtime resources and load them through `importlib.resources`. An E2E
check must build a wheel, install it in a clean environment, change outside the
checkout, render a share card and start a configured agent runner.

## TN-04 · Enforce disclosure beyond tool calls

`trustnet/gate/dm.py` invites both main agents into the same DM room. Their gate
limits tool answers, but a main agent can already know private facts from its
own memory. A share card is guidance and cannot constrain those direct messages.

For use with sensitive personal information, require outgoing disclosures to
pass through an enforced boundary or use a conversation agent given only the
approved data. Test with an agent that already knows a private address. It must
be unable to transmit that address to the friend through any available tool.
Do not judge the meaning of outgoing prose with keyword lists.

## TN-05 · Support plan revisions explicitly

`commands.py` parses `counter` and `policy.py` allows it, but `runtime.py` does
not dispatch Counter to a handler. It returns the command list. Before offering
plan revisions, either implement a superseding proposal that invalidates the old
votes, or remove the advertised command. An E2E check must show that approval of
the old proposal cannot confirm a superseded plan.

## TN-06 · Make first contact work for new people

`relay.post_home` creates a new person's home with only the gate as an agent
member. `personal.home` requires the main agent to be a member already. Om also
has a special case requiring a pre-created Discord home. Add a bootstrap flow
that registers the person's agent and creates or joins its private home before
the first tool request. Verify it with two new names and empty state directories.

Agent identity also uses the fixed `<person>-hermes` convention throughout
authorization. Supporting several registered agents per person requires an
explicit identity registry and consent permissions for each agent.
