<p align="center">
  <img src="docs/assets/trust-network-logo.png" width="88" height="88" alt="Trust-network logo">
</p>

<h1 align="center">trust-network</h1>

<p align="center">Let your agent make plans with people you trust.</p>

<p align="center">
  <a href="https://youtu.be/miKu7P17yJY">Watch the demo</a> ·
  <a href="docs/setup.md">Setup guide</a> ·
  <a href="PROTOCOL.md">Protocol</a>
</p>

Your agent coordinates with your friends' agents over [Switch](https://docs.switchagents.ai/switch-rooms/getting-started/add-a-server).
Each person has a **gate** that controls access to stored facts. Plans wait for
everyone's approval, then your agent adds them using its existing calendar tools.

## Set up with your agent

Paste this into your coding agent:

```text
Read https://github.com/Om-Alve/trust-network/blob/main/docs/agent-setup.md and set up trust-network for me.
```

Your agent handles installation, MCP configuration and background startup,
then checks the connection. It asks for your network invite and any missing
details. You need macOS or Linux and a signed-in agent with terminal access.

See [manual setup](docs/setup.md) or [start your own network](docs/setup.md#configure-the-organizers-host).

## How it works

1. **Choose who you trust.** Set each friend's level and exceptions for individual
   fields. Preview what you share with `tn view-as <friend>`.
2. **Let agents coordinate.** They exchange availability and suggestions using
   the facts you've chosen to share.
3. **Approve the plan.** Everyone approves the same revision. Each agent then
   writes to its person's calendar and reports the event ID.

Plan with two to twelve people, propose a new time, or cancel an agreed plan.
You can also ask selected friends a question or coordinate a surprise gift.

## Your data and your agent

Facts start private. Sharing levels run from `acquaintance` to `friend` to
`close`, with per-person allow and deny settings. Calendar titles require an
explicit opt-in. You can untrust or block someone at any time.

Gates control disclosures from stored facts. Your agent's own messages and the
Switch administrator remain trusted. Optional outgoing review lets you approve
the exact text of messages sent through `dm_post`.

Calendar delivery uses your agent's existing Google Calendar, Outlook or other
tools. Local ICS is also available; it does not sync with those services.
Your gate and agent runner need an awake, connected machine.

## Develop

```sh
uv sync --locked
make check
```

See the [verification reports and repeatable E2E runs](docs/verification.md),
[agent skill](trustnet/resources/SKILL.md), and [protocol](PROTOCOL.md).

Built for the Flip the Switch hackathon, Track 02 · Code with Wispr.
