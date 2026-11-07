# My agent knows too much to plan my weekend

How I built trust-network, a gate made of code that decides what each friend's AI agent may learn about you, so two agents can plan a Sunday evening while their people send one message each.

By Om Alve · Flip the Switch hackathon · Track 02, Best Personal or Creative Workflow

## Forty-seven messages

It's Thursday, and I want to go bowling on Sunday with Rahul and Priya. I post in the group chat. Rahul has cricket until 8:30. Priya asks whether I mean this Sunday or next. Someone asks what it costs, I say about ₹1,200 each, and Priya replies with a grimace. Then I remember I need a tent for the 14th, and the bowling thread becomes a camping thread. Forty-seven messages later we still don't have a time.

Every fact that thread needed was already written down somewhere. My calendar knows I'm free after 7:30. Rahul's calendar knows about cricket. My AI agent knows my budget because I've told it a dozen times. Priya's notes say she owns a two-person tent. We spent an evening copying facts between people by hand.

The obvious fix is to let my agent talk to Rahul's agent. I built trust-network to find out what that takes. The answer turned out to be less about the agents and more about what they're allowed to say.

## Share nothing, or share everything

My agent knows a lot about me. It knows my neighbourhood, my T-shirt size, my wishlist, my dentist and my home address. That's why it's useful, and it's why I don't want it chatting with someone else's agent unsupervised.

Today an agent acting for me has two settings. It shares nothing and is useless: "I don't know Rahul's schedule." Or it shares whatever it knows, and Rahul's agent can learn my address by asking politely.

People don't work like either setting. I'd tell Rahul, a close friend, what's on my wishlist. I'd tell Priya, a friend, that I'm vegetarian and don't drink. I wouldn't tell an acquaintance where I live. Agents need the same line.

I could write that line into a prompt: "Never share my address." But a prompt is a request to a language model, and the other side of the conversation is another language model that can ask in a hundred different ways. I wanted the line held by code that doesn't try to read English for meaning at all.

## What trust-network does

Every person gets a gate. A gate is a small Python process with no LLM in it. It holds the person's facts and calendar, and it answers each friend's side only at the trust level the person set for that friend: `acquaintance`, `friend` or `close`. A fact can also be `private`, which no friend ever sees.

The agents talk to each other in plain language in Switch rooms. Gates talk to agents, and to each other, in a small fixed command grammar. Nothing is booked until every person says yes. Then each agent writes the event to its own person's calendar.

The [demo video](https://youtu.be/miKu7P17yJY) is a live run with two Hermes agents on Discord, one for me and one for Rahul:

- **Plan with consent.** I send one message. My agent and Rahul's settle on 9 pm because Rahul has cricket until 8:30. The plan waits for both yeses, then lands on both calendars.
- **Surprise gift.** Rahul's agent gets gift ideas from my wishlist and claims one. I see nothing until after my birthday, and nobody else can claim the same gift.
- **Ask around.** One question about a tent reaches several friends. Priya's gate answers from her stored facts without bothering her.
- **Refusal.** Rahul's agent asks for my home address. My gate refuses, and my agent tells me someone asked.

## The gate: two files and no model

A person's data is two YAML files. The facts file tags every fact with the lowest level that may see it:

```yaml
facts:
  diet:          {value: vegetarian,                     level: acquaintance}
  drinks:        {value: no alcohol,                     level: friend}
  interests:     {value: [bowling, board games, sci-fi], level: friend}
  has:           {value: [projector, camping stove],     level: friend}
  neighbourhood: {value: Indiranagar,                    level: close}
  wishlist:
    value:
      - {item: Lego Millennium Falcon, price: 2500}
      - {item: Hario V60, price: 2000}
    level: close
  address:       {value: "42, 12th Main, ...",          level: private}
```

The trust list says who my friends are and how much I trust each one:

```yaml
people:
  rahul: close
  priya: friend
consent:
  default: via-agent
```

From those two files the gate applies a short set of rules:

- A fact is visible at its level and above. A `private` fact is never visible.
- The calendar shows busy blocks at every level. Event titles appear only for people I opt in one by one.
- The level of a room is the lowest level I give anyone in it. If Rahul (close) and Priya (friend) are both in a room, the room is `friend`.
- If anyone in the room is not on my list, the gate says nothing at all.
- A hidden fact and a fact that doesn't exist get the same reply, `not shared with you`, so the reply gives away nothing about what I have.

I can check exactly what a friend's side can learn before anything happens. This is real output from the example data in the repo:

```text
$ tn -a om view-as rahul
view-as rahul — close
  ✅ diet           vegetarian
  ✅ interests      bowling, board games, sci-fi
  ✅ neighbourhood  Indiranagar
  ✅ wishlist       Lego Millennium Falcon (≈₹2,500), Hario V60 (≈₹2,000), Kindle Paperwhite (≈₹14,000)
  ❌ address        not shared at this level

Calendar · next 7 days (Nov 7 – Nov 14) · busy blocks only, no titles
  Sun Nov 8  17:00–19:00  busy
```

Run the same command for Priya and `neighbourhood`, `sizes` and `wishlist` flip to ❌. Neither of them ever sees the address.

Two more pieces sit around the rules. Every value the gate shows goes into a ledger with the field, the value, who saw it, the room and the time. And when the other side asks for something it can't have, I get one note in my private home room, such as "Rahul's side asked for your address (private)". The gate sends at most one note per person and field every 10 minutes, so a persistent agent can't flood me.

## Why it runs on Switch

Switch is a server where people and agents meet. It has user accounts, agents owned by those users, rooms, and messages delivered over a WebSocket. trust-network has no accounts, rooms or message transport of its own. Without Switch, agents can't reach each other and gates can't check who is asking.

```text
 person ── agent ── gate ──┐                     ┌── gate ── agent ── person
  (om)   (om-hermes) (om-gate)                   (rahul-gate) (rahul-hermes) (rahul)
                           │                     │
                           └────── Switch ───────┘
                    rooms, identity, WebSocket events

 om-home          om, om-hermes, om-gate                  my private room
 conn-om-rahul    om-gate, rahul-gate                     gate to gate
 dm-om-rahul-*    om-hermes, rahul-hermes, both gates     agents plan here
```

The design depends on three things Switch provides.

**Identity.** Each person has a Switch user. Their agent and gate are registered with that person's key, so Switch records the person as their owner. The gate takes the sender and owner of every message from Switch's metadata. A message that says "this is Om" changes nothing, and an agent with no reported owner is refused.

**Rooms.** Each person has a private home room where questions, proposals and alerts arrive. Each pair of gates shares a connection room. Each plan gets its own room, and each gift search gets a private room that only the two gates can join. Every room is created internal-only, with no bridge to outside chat apps.

**Addressed messages.** A gate acts only on messages that Switch marks as addressed to it, such as `@om-gate ask diet`. Before it runs any command, it checks that every member of the room is a known identity, that every agent's owner matches Switch's records, that the sender is in the room, and that everyone present is on my trust list. Any mismatch and the gate stays silent.

## One plan, start to finish

Here is the bowling plan from the demo, using the real room transcript.

I tell my Hermes on Discord: "Can you set up bowling with Rahul this Sunday? After 7:30pm works for me, around ₹1,200 a head, maybe Smaaash." My agent calls its `dm` tool, which posts `@om-gate dm rahul "..."` in my home room. My gate checks that Rahul is on my list, opens the connection room with Rahul's gate, and says hello with a protocol version (`trust-network/1`) so both gates know they speak the same grammar. Then it creates the planning room and asks Rahul's gate to join.

Each gate then gives its own agent a share card: the facts and calendar this friend's side may learn, built by the same code that answers `ask`. Then the agents talk:

```text
17:44:16     om-hermes  Hi Rahul's side — Om would like bowling this Sunday (Nov 8), free from
                        7:30pm, around ₹1,200 a head, Smaaash Indiranagar as the maybe.
                        Does that work for Rahul?
17:46:33  rahul-hermes  Rahul has cricket until 8:30pm Sunday, so 7:30pm won't work. Could we
                        do 9:00pm at Smaaash, Indiranagar, around ₹1,200 per person?
17:47:22     om-hermes  9:00pm Sunday works on Om's side, and Smaaash at around ₹1,200 a head
                        is fine too. I'll propose it now.
17:47:24     om-hermes  @om-gate propose P1 2026-11-08T21:00 2h "Bowling with Rahul" @ "Smaaash, Indiranagar"
17:47:24       om-gate  @rahul-gate propose P1 2026-11-08T21:00:00+05:30 120m "Bowling with Rahul" @ "Smaaash, Indiranagar"
```

The conversation is free text. The proposal is not. A proposal is one line with a start time, a duration, a title and a place, and the gate rejects anything outside that form. My gate stores the plan, shows it to me in my home room, and forwards it to Rahul's gate, which shows it to Rahul.

When I say yes, my gate sends Rahul's gate a consent line: `consent P1 yes via-agent <sha256>`. The last field is the SHA-256 of the plan text. Rahul's gate records my vote only if that fingerprint matches the plan it holds, so a yes can't be applied to a different time or place. A single no declines the plan. Two yeses confirm it. Both gates post "✅ P1 ... · Om ✅ via agent · Rahul ✅ via agent" to their home rooms, archive the planning room, and queue a calendar operation for each of us.

I sent one message and said one yes. Rahul said one yes.

## Why the gate never touches my Google account

I considered two designs for calendars. The gate could call Google and Outlook itself, which means storing everyone's calendar credentials in my code. Or the gate could hand the approved operation to the person's own agent, which already has calendar tools and accounts, and require a receipt back.

I chose the second. After two yeses, the agent's `calendar_tasks` tool returns the exact approved operation with a stable ID. The agent writes the event with whatever calendar tool its person already uses, puts that ID in the event description, and calls `calendar_report` with the provider and event ID. Until a receipt arrives, the task stays visible and the agent keeps retrying. Before any retry, the agent must search the calendar for that ID, so a crash between writing the event and reporting it can't create a duplicate.

## What fought back

**The design I threw away on the first evening.** My original plan put an envoy between people. Each friendship would get a separate, sandboxed agent whose instructions held only what that friend's level allowed, with file and shell tools turned off. My main agent, the one that knows everything, would never meet anyone else's agent. On day zero I probed Switch's managed agents, and two results settled it. Switch Console's controller couldn't start OpenCode 2.x at all, because it waits for a log line starting with `opencode server listening` and OpenCode 2.1.4 prints `server listening on ...`. And in switch-core 0.31, only Claude managed agents could have their tools turned off, so a Codex or OpenCode envoy would keep shell and file access. I built my own envoy runner as a fallback, and dropped the whole envoy layer the same evening because it added a hop and an extra agent for every friendship. Main agents now talk directly, and the gates didn't change at all. That choice has a real cost, which I cover under limits.

**Switch answered for my gate.** Switch delivers a room's addressed messages only to a session connected to that room, and one connection holds one room session. My gate had one connection, so it was absent from every room but one. When Rahul's gate addressed mine in a room where mine wasn't connected, Switch replied for it: "I don't have a session connected to this room ...". That notice went out under my gate's name. Rahul's gate read it as a malformed command from my side and raised an overreach alert to Rahul. My gate was being reported for something Switch had said. The fix is `room_pool.py`, which gives a gate one connection per open room, merges their events, and waits until Switch shows the addressed gate live before posting. Switch allows 32 connections per agent, so a gate keeps the newest 24 open rooms connected.

**Curly quotes.** Free text in a command is a double-quoted string, so it can't contain a double quote. In a seed chat, Rahul's Hermes passed a goal containing curly quotes to its `dm` tool. The tool accepted it. The gate turned the curly quotes into straight ones, found a quote inside the quoted text, and replied "Invalid command". The tool had already told the agent it succeeded. I dictate with Wispr Flow, which produces curly quotes all the time, so this would have hit real use quickly. The tool now applies the gate's own normalisation before sending, and turns curly double quotes inside text into single quotes.

**My test agent showed up knowing my API key.** To give my Hermes a demo persona, I cloned its profile from the Hermes I use every day. It came with my work memory, including a live API key. That was the most direct demonstration of the problem I was building for: a personal agent knows things you've forgotten you told it. I backed that memory up with locked-down permissions and replaced it with a persona that matches the demo facts and holds nothing at the private level.

**One agent agreeing with itself.** Both people still had to say yes, but nothing stopped my agent from proposing a plan before Rahul's agent had said a word. Rahul would then be approving a time his own agent never checked against his calendar. The gate now refuses its own agent's proposal until the friend's agent has posted in the room. Switch's automatic greeting when an agent joins doesn't count. Neither do Switch's notices, which begin with an @-mention. Switch also refuses @-mentions between agents in the planning room, so agents post plain text and read the room.

**Agents taking rooms from themselves.** Switch binds a room to an agent's newest connection. My wake runner, the MCP tools, setup and the doctor command all connect as the same agent, and they kept taking rooms from each other. Setup failed now and then on the private-home check. The client now reconnects once and retries when Switch rejects an operation.

**Every gate posting the same document.** For group plans, every participant's gate posted the confirmed-plan document under the same name. Switch accepted the first and rejected the rest, and the rest retried forever. Only the organizer's gate posts it now.

**A calendar skill that wanted a third yes.** Hermes' Google Workspace skill asked for confirmation before writing an approved event, after both people had already said yes. The prompt the agent wakes up with now says a calendar task exists only after every person's explicit yes to that exact plan. Any other calendar write still needs a yes.

Each of these passed in my offline tests. Every one came out of a run against a real Switch server with real agents.

## Testing, and what I can claim

trust-network is about 12,500 lines of Python with about 9,800 lines of tests. `make check` runs 563 tests and the linters in about 40 seconds. On top of that are end-to-end runners that drive the real CLI and MCP tools as subprocesses, and each writes a report you can check later: product flows (8 scenarios), group plans (10), sharing controls (5), setup readiness (7, plus one optional OpenCode diagnostic that timed out and is recorded as skipped), and an installed-wheel check (6).

Then there are live runs on a real Switch server:

- On 6 November my Hermes planned with Priya's Codex agent end to end. Both people said yes and both calendars got the plan.
- Two Codex agents planned through live Switch and production gates in six model turns. After one approval, both calendars were still empty, which is the consent rule working. After both, each calendar had exactly one event, with matching receipts. An earlier run with one Codex and one OpenCode agent failed when OpenCode went over its 180-second turn limit, and I don't count it.
- Gates and wake runners ran as real macOS launchd services. After `kill -9`, launchd restarted the gate, and it answered on Switch again within about 21 seconds.
- An approved plan went into Google Calendar through Hermes. The test harness read the event back by its ID with the calendar skill's client directly, not through the agent, and checked the title, time, place and ID marker. Exactly one event carried the ID.

What I have not verified: Outlook and Codex's Google Calendar plugin against real accounts, and Linux systemd services, which I've only tested against a fake `systemctl`. The gate records the receipts agents report. It does not query Google itself.

## Honest limits

- **My own agent is trusted.** The gate enforces what the gate discloses through `ask`, `free` and proposals. It cannot stop my agent from volunteering something in the planning room's plain text. The share card tells the agent its limits but doesn't confine it. Setting `TN_OUTGOING=review` makes me approve the exact text of every message my agent sends, but anything with shell access or other messaging tools can go around that.
- **Switch is trusted.** Identity and room membership come from Switch, and a Switch administrator can read every room. On day zero, my admin account could open a private gift room that Rahul's gate had created. The gift seal is a courtesy between friends, not a cryptographic promise.
- **Untrusting someone can't take anything back.** Removing a friend stops future disclosures. It doesn't erase what they already received.
- **One agent per person.** Each person's agent is always named `<person>-hermes`, even when it runs Codex. The name dates from the first framework I used, and changing it would have meant re-registering live agents.
- **There is no public service.** A network is a group of friends sharing one Switch server, hosted by one of them, the organizer, who sends invites.
- **The command grammar is English** with ASCII punctuation.
- **Planning rooms close** after 20 agent turns or seven days, so a plan waiting on someone who answers slowly can time out.

## What I learned

**Put the rule where the model can't argue with it.** Telling an agent "don't share my address" is a hope. A gate that never puts the address in any reply is a fact you can test.

**Take identity from the transport, never from the message.** Every check in the gate reads the sender and owner from Switch. Nothing an agent writes about who it is changes what the gate does.

**Tie consent to exact text.** A yes is attached to a hash of the plan it was given for. Without that, "yes" is a word an agent can move to a different plan.

**Offline tests find the bugs you imagined.** My fixtures modelled Switch the way I understood it. Each bug in the list above came from a gap between that model and the real server.

**Say plainly what you don't enforce.** The most important sentence in the protocol spec is the one saying the share card is guidance, not a fence. People should know which promises are code and which depend on an agent's judgement.

## What's next

- An enforced outgoing boundary, or an agent that only ever sees the conversation data its person approved, so the gate's promise covers everything the agent says.
- Several agents per person, with an explicit identity registry and per-agent consent permissions.
- Outlook, Codex's Google Calendar plugin and Linux systemd, verified against real accounts and machines.
- Version handshakes for ask-around and gift rooms, which planning rooms already have.

## Try it

- Demo: [youtu.be/miKu7P17yJY](https://youtu.be/miKu7P17yJY)
- Code: [github.com/Om-Alve/trust-network](https://github.com/Om-Alve/trust-network)
- Protocol: [PROTOCOL.md](https://github.com/Om-Alve/trust-network/blob/main/PROTOCOL.md)

You can see what a friend's side would learn without a Switch server or an invite. You need macOS or Linux, Python 3.12 and [uv](https://docs.astral.sh/uv/):

```sh
uv sync --locked && make check
cp -R examples /tmp/tn-examples
TN_DATA_DIR=/tmp/tn-examples uv run tn -a om view-as rahul
TN_DATA_DIR=/tmp/tn-examples uv run tn -a om view-as priya
```

To join a real network, ask your group's organizer for an invite and paste this into your coding agent:

```text
Read https://github.com/Om-Alve/trust-network/blob/main/docs/agent-setup.md and set up trust-network for me.
```

The bowling plan in the demo took me one message and one yes, and took Rahul one yes. The other forty-five messages were facts our agents already had.

AI tools used: I built trust-network with coding agents, and dictated with Wispr Flow. Inside the product, Hermes and Codex agents do the talking. No model ever decides what a gate discloses.
