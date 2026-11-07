# trust-network

**Let your AI agent coordinate plans with people you trust. Gates enforce which stored facts their tools disclose; your agent uses its existing calendar tools to carry out approved plans.**

[![Demo video](https://img.youtube.com/vi/miKu7P17yJY/maxresdefault.jpg)](https://youtu.be/miKu7P17yJY)

▶ **[Watch the demo (2:31)](https://youtu.be/miKu7P17yJY)**

Built for the Flip the Switch hackathon (Track 02 · Code with Wispr), on [Switch](https://docs.switchagents.ai/switch-rooms/getting-started/add-a-server).

## The idea

Your agent already knows everything about you: your calendar, your budget, where you live. To plan with a friend's agent it can either share nothing, and be useless, or share everything, and your whole life goes with it.

trust-network gives every person a **gate**. You write down who you trust and how much (`acquaintance < friend < close`), and tag each fact with the lowest level that may see it. Friends' agents talk to your gate, and the gate shares what that person's permissions allow. Plans require everyone's approval. Calendar delivery is tracked separately, using the personal agent's existing Google Calendar, Outlook or other tools.

Your personal agent may already know private information from memory. The gate
cannot classify or restrict what the agent volunteers in automatic conversation.
Optional outgoing review lets you approve the exact text before `dm_post` sends it.
`view-as` previews gate disclosures, rather than everything an agent might say.

```yaml
# trust.yaml                      # facts.yaml
people:                           facts:
  rahul: close                      diet:      {value: vegetarian, level: acquaintance}
  priya: friend                     wishlist:  {value: [...],      level: close}
                                    address:   {value: "...",      level: private}
```

What the demo shows, all recorded live:

- **Planning with consent.** Om's and Rahul's own agents (Hermes, on Discord) negotiate a bowling night around Rahul's cricket. The plan waits for two yeses, then lands on both calendars.
- **Surprises stay surprises.** Rahul's agent gets gift ideas from Om's wishlist and claims one. Om sees nothing, and the claim is sealed until after his birthday.
- **Ask your network.** Send a question to selected friends and receive their replies.
- **Restricted fact access.** Rahul's agent asks the gate for Om's private address. The gate refuses, and Om is told. `view-as rahul` previews the gate's sharing policy.

Bring your own agent: anything that speaks MCP joins through `tn mcp`.

## Set up your connection

To join, you need an invite from someone running a Switch server and this
project's onboarding host. This repository does not supply a public hosted service.
If you are the first person, follow [Start a network](docs/setup.md#configure-the-organizers-host)
before inviting your friends.

Use macOS or Linux, Python 3.12, [uv](https://docs.astral.sh/uv/getting-started/installation/),
and an installed, signed-in agent CLI. Clone this repository and run from its root:

```sh
uv tool install .
tn setup '<invite-from-organizer>' --agent codex --consent via-agent --wake --background-service
tn doctor
```

Choose `codex`, `claude`, `opencode` or `manual`. Setup keeps your profile and
credentials on this machine, registers your gate and agent, creates a private
home, starts the gate and configures MCP. It preserves your data when repeated.
Restart your agent after setup to load the new MCP connection.
`--background-service` starts the gate and agent runner at login on macOS or
Linux. Omit it to configure the runner without starting it, then keep the printed
wake command running in a terminal. Both modes need the machine awake and online.
Choose your timezone with `--timezone <IANA-name>`. New profiles use agent calendar
delivery; existing profiles retain ICS until you choose `--calendar-delivery agent`.
Manual mode writes `mcp.json` in the local configuration directory for import
into another MCP client. Discord and a VM are optional.

[Setup and organizer instructions](docs/setup.md) cover creating invites,
running the shared identity service and repairing a connection.

Add each friend explicitly with `tn trust <name> <level>`. New profiles have no
trusted people or shared facts. Agent onboarding can suggest private facts and
sharing requests for your review.

Trust levels have per-person exceptions. For example, `tn trust rahul close
--deny wishlist --allow interests` hides your wishlist from Rahul while allowing
interests. Private facts remain private. Calendar titles are hidden unless you
explicitly add `--calendar-titles`. `tn untrust rahul` removes access;
`tn block rahul` also requires an explicit `tn unblock rahul` before re-adding.
These actions cannot retract information already shared.

Use `tn ask-around "Anyone have a tent?" --to rahul,priya` to choose an audience.
Recipients can set `--ask-around agent`, `person` or `off` on your trust entry.
The gate does not automatically dump their inventory or recommendations.
`--consent via-agent` lets your agent relay your yes or no. Without it, approval
must come directly from your Switch user account.

`tn doctor` checks your profile, Switch connection, home, trusted identities,
gate, MCP and wake runner. It reports connection and automation readiness
separately; a configured but stopped runner is not ready. `tn status` shows
processes and installed services. Configuration lives under
`~/.config/trust-network`, or `TN_CONFIG_DIR` when set. Setup logs stay there.
Use `tn stop` to stop the gate and `tn setup` to start it again. A connected MCP
server alone does not wake the agent when a friend replies. Configure the wake
runner described in [setup](docs/setup.md), or keep `tn wake --agent codex` running.

Before your first plan, give the agent access to your actual calendar and ask it
to read availability. After everyone approves, it applies `calendar_tasks` using
those existing tools and records the provider event ID with `calendar_report`.
Check the `status` tool for unfinished delivery. Local ICS files are an optional
legacy calendar mode; they do not synchronize Google Calendar or Outlook.

New plans can include two to twelve people. Ask your agent to use the group-plan
tools: everyone approves the same revision, the organizer can propose a new time,
and any participant can cancel on their person's instruction. The old confirmed
event stays until everyone approves a replacement. Every person must trust every
other participant in the shared room. Legacy `P<n>` plans retain their original
pairwise protocol; use the group workflow for new plans needing later changes.

For exact-text outgoing review, set `TN_OUTGOING=review` in the MCP environment.
Use `tn outbox list`, then `tn outbox approve <ref>` or `tn outbox decline <ref>`.
The MCP server exposes no outgoing-approval tool. Your local machine and other
agent tools remain trusted; this cannot stop an agent using a separate messaging tool.

For an existing server without an invite, run `tn setup --name <name> --server
<https-address> --identity-url <https-identity-endpoint>`. It prompts privately
for your registration key and identity token. The organizer must provision your
Switch account first. Local HTTP is supported only on loopback addresses.

## Read more

- [PROTOCOL.md](PROTOCOL.md): the gate-to-gate protocol
- [trustnet/resources/SKILL.md](trustnet/resources/SKILL.md): how an agent uses the tools (shipped in the package)
- [docs/setup-laptop.md](docs/setup-laptop.md) and [docs/setup-vm.md](docs/setup-vm.md): running it

## Develop

```sh
make check   # ruff format check, ruff lint, pytest
```
