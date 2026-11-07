# Behavior and remaining work

Confirmed plans enqueue calendar operations for each person. New connections use
the personal agent's existing provider tools and return provider/event receipts;
unconfigured legacy profiles keep local ICS delivery. Accepted
votes and delivery jobs commit together in owner-local SQLite. Restart retries
unfinished deliveries. Calendar events and approval ledger entries use stable
IDs so replay does not duplicate them. Switch messages and documents can repeat
after an interrupted acknowledgment.

Fact and trust approvals record a durable decision before updating the profile
and ledger. Pending plans can be revised with `counter` before the initiating
person votes. Superseded votes cannot confirm the replacement.

Runtime templates, agent instructions, watcher prompts and the identity exporter
ship in the wheel. New people get a private home automatically on first contact.

## Remaining limitations

- A main agent can already know private data from its own memory. Gates restrict
  tool disclosures; share cards cannot enforce what an agent says directly in a
  DM. Sensitive deployments need an enforced outgoing boundary or an agent given
  only approved conversation data.
- Calendar access comes from the personal agent's existing tools. The gate tracks
  pending operations and receipts, but cannot independently verify a provider
  write. Agents must search for the stable event marker before retrying.
- Authorization recognizes one registered `<person>-hermes` alias per person.
  Several agents per person need explicit identity and consent permissions.

Exact-text outgoing review is available with `TN_OUTGOING=review`; the owner
approves messages using `tn outbox`. Automatic conversations still depend on the
agent's judgement. Local shell access and other messaging tools remain trusted.

The first practical use case is planning between people who already trust each
other. Ask-around can support equipment lending, but an inventory match does not
constitute permission to lend. Gift rooms assume participants accept that the
Switch administrator can read workspace rooms.
