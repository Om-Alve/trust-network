# Behavior and remaining work

Confirmed plans automatically create local ICS events for both people. Accepted
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
- Calendar delivery currently writes local ICS files. Google Calendar and Outlook
  adapters are not implemented.
- Authorization recognizes one registered `<person>-hermes` alias per person.
  Several agents per person need explicit identity and consent permissions.

The first practical use case is planning between people who already trust each
other. Ask-around can support equipment lending, but an inventory match does not
constitute permission to lend. Gift rooms assume participants accept that the
Switch administrator can read workspace rooms.
