<p align="center">
  <img src="docs/assets/trust-network-logo.png" width="88" height="88" alt="Trust-network logo">
</p>

<h1 align="center">trust-network</h1>

<p align="center">Let your agent make plans with people you trust.</p>

<p align="center">
  <a href="https://youtu.be/miKu7P17yJY">Watch the demo</a> ·
  <a href="#try-it-without-an-invite">Try it without an invite</a> ·
  <a href="docs/setup.md">Setup guide</a> ·
  <a href="PROTOCOL.md">Protocol</a>
</p>

Your agent coordinates with your friends' agents over [Switch](https://docs.switchagents.ai/switch-rooms/getting-started/add-a-server).
Each person has a **gate** that controls access to stored facts. Plans wait for
everyone's approval, then your agent adds them using its existing calendar tools.

## Join a network

A network is a group of friends sharing one Switch server. Its **organizer** is
the person who hosts that server and the onboarding host, and gives each member
an invite. There is no public service, so you need an invite from your group's
organizer. If you are the first in your group,
[become the organizer](docs/setup.md#configure-the-organizers-host) and invite your friends.

With your invite, paste this into your coding agent:

```text
Read https://github.com/Om-Alve/trust-network/blob/main/docs/agent-setup.md and set up trust-network for me.
```

Your agent installs trust-network, configures MCP and background startup, then
checks the connection. It asks for your invite and any missing details. You need
macOS or Linux and a signed-in agent with terminal access. See
[manual setup](docs/setup.md) to do it yourself.

## How it works

1. **Choose who you trust.** Set each friend's level and exceptions for individual
   fields. Preview what you share with `tn view-as <friend>`.
2. **Let agents coordinate.** They exchange availability and suggestions using
   the facts you've chosen to share, in rooms on the organizer's Switch server.
3. **Approve the plan.** Everyone approves the same revision. Each agent then
   writes to its person's calendar and reports the event ID.

Plan with two to twelve people, propose a new time, or cancel an agreed plan.
You can also ask selected friends a question or coordinate a surprise gift.
[How trust-network uses Switch](docs/switch.md) covers the accounts, rooms and
identity checks.

## Your data and your agent

Facts start private. Sharing levels run from `acquaintance` to `friend` to
`close`, with per-person allow and deny settings. Calendar titles require an
explicit opt-in. You can untrust or block someone at any time.

Gates control disclosures from stored facts. Your agent's own messages and the
Switch administrator remain trusted. Optional outgoing review lets you approve
the exact text of messages sent through `dm_post`. Calendar credentials stay in
your agent's own connector; the gate only records the event ID it reports.
Your gate and agent need an awake, connected machine.

## Try it without an invite

From a fresh clone on macOS or Linux with Python 3.12 and [uv](https://docs.astral.sh/uv/):

```sh
uv sync --locked && make check
cp -R examples /tmp/tn-examples
TN_DATA_DIR=/tmp/tn-examples uv run tn -a om view-as rahul
TN_DATA_DIR=/tmp/tn-examples uv run tn -a om view-as priya
```

Om trusts Rahul as `close` and Priya as `friend`. Rahul sees Om's neighbourhood,
sizes and wishlist; Priya does not. Neither sees his address. The
[verification guide](docs/verification.md) has the acceptance scenarios and a
run with real agents.

Built for the Flip the Switch hackathon, Track 02 · Code with Wispr.
