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

## Read more

- [PLAN.md](PLAN.md): design, trust rules, safety model and known gaps
- [PROTOCOL.md](PROTOCOL.md): the gate-to-gate protocol
- [skills/trust-network/SKILL.md](skills/trust-network/SKILL.md): how an agent uses the tools
- [docs/setup-laptop.md](docs/setup-laptop.md) and [docs/setup-vm.md](docs/setup-vm.md): running it
- [phases/](phases/README.md): how it was built, phase by phase

## Develop

```sh
make check   # ruff format check, ruff lint, pytest
```
