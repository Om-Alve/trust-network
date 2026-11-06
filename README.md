# trust-network

**Let your AI agent make plans with your friends' agents, sharing only what you've trusted each friend with, enforced in code you can read, not by a prompt.**

[![Demo video](https://img.youtube.com/vi/miKu7P17yJY/maxresdefault.jpg)](https://youtu.be/miKu7P17yJY)

▶ **[Watch the demo (2:31)](https://youtu.be/miKu7P17yJY)**

Built for the Flip the Switch hackathon (Track 02 · Code with Wispr), on [Switch](https://docs.switchagents.ai/switch-rooms/getting-started/add-a-server).

## The idea

Your agent already knows everything about you: your calendar, your budget, where you live. To plan with a friend's agent it can either share nothing, and be useless, or share everything, and your whole life goes with it.

trust-network gives every person a **gate**. You write down who you trust and how much (`acquaintance < friend < close`), and tag each fact with the lowest level that may see it. Friends' agents talk to your gate, and the gate shares exactly what that level allows. Nothing is committed until both people say yes.

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
- **Ask everyone at once.** One question goes to every friend's gate. Priya's gate answers from her facts without bothering her.
- **Private stays private.** Rahul's agent asks for Om's address. Om's gate refuses, and Om is told. `view-as rahul` shows exactly what Rahul's side can learn.

Bring your own agent: anything that speaks MCP joins through `tn mcp`.

## Set up your connection

Install from this checkout, then use the invite your organizer gives you:

```sh
uv tool install .
tn setup '<invite-from-organizer>' --agent codex
tn doctor
```

Choose `codex`, `claude`, `opencode` or `manual`. Setup keeps your profile and
credentials on this machine, registers your gate and agent, creates a private
home, starts the gate and configures MCP. It preserves your data when repeated.
Manual mode writes `mcp.json` in the local configuration directory for import
into another MCP client. Discord and a VM are optional.

Add each friend explicitly with `tn trust <name> <level>`. New profiles have no
trusted people or shared facts. Agent onboarding can suggest private facts and
sharing requests for your review.

`tn doctor` checks your profile, Switch connection, home, trusted identities,
running gate and MCP configuration. Configuration lives under
`~/.config/trust-network`, or `TN_CONFIG_DIR` when set. Setup logs stay there.

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
