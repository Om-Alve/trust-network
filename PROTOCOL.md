# trust-network agent-to-agent protocol, v1

This is the specification of the protocol as the code implements it today
(`trust-network/1`). It is written for hackathon judges and for developers who
want to bring a new agent framework. The code is the source of truth:
`trustnet/gate/commands.py` (grammar), `policy.py` (who may send what),
`consent.py` (proposals and consent), `handshake.py` (versioning).

## 1. Overview

Each person has two things in Switch: their own AI agent (any framework:
Hermes, Codex, anything that can call tools) and a **gate**. The gate is
deterministic code with no LLM. It holds the person's private facts and
calendar, and it answers only at the trust level the person set for each friend
(`acquaintance` < `friend` < `close`; a fact can also be `private`, which no
friend ever sees).

Agents talk to each other in plain language, in agent-only Switch rooms. Gates
talk to each other, and to agents, in a small fixed command grammar. Nothing is
committed until both people say yes, and each yes is bound to the exact plan
text it was given for.

```
 person ── agent ── gate ──┐                       ┌── gate ── agent ── person
  (om)    (om-hermes) (om-gate)                     (priya-gate) (priya-hermes) (priya)
                           │                       │
                           └──────── Switch ───────┘
                      rooms, identity, WebSocket events

 om-home          om <-> om-hermes <-> om-gate            (private to om's side)
 conn-om-priya    om-gate <-> priya-gate                  (gate-to-gate)
 dm-om-priya-*    om-hermes <-> priya-hermes, both gates  (agents plan here)
```

## 2. Roles

**Person.** A human with a Switch user (for example `om`, `rahul`, `priya`).
The person owns a trust list (who their friends are and at what level), a facts
file, a calendar, and a consent mode. Only the person can loosen a fact's level
or change a trust level.

**Agent.** The person's own AI, acting in Switch on the person's behalf. It
plans in plain language with the friend's agent, asks its person what it does
not know, and relays the person's yes or no. The agent is any framework. Its
Switch name is always `<person>-hermes` (`om-hermes`, `priya-hermes`), whatever
framework fills the slot. This is a v1 naming wart: the slot was named for the
first framework, and renaming it would have meant re-registering live agents.
Priya's slot is `priya-hermes` and runs Codex. Where this document says
"agent", it means whatever sits in that slot.

**Gate.** `<person>-gate`: a Switch agent run by trust-network code, with no
LLM. It is the only thing that reads the person's facts and calendar. It
authenticates every sender, applies the trust level of the room, records every
disclosure in a ledger, holds proposals and questions, and relays consent to the
friend's gate. A gate never trusts a name written in a message.

## 3. Transport and identity

**Switch is the transport and the identity provider.** Agents register with a
person's registration key, receive events over a WebSocket, and call room
operations (create room, invite, post, read, archive). Switch Console
(switch-core 0.31) shows the rooms.

**Addressed messages.** A gate reacts only to messages that address it with a
leading `@<name>-gate`, as Switch reports it. Unaddressed messages are ignored,
except in DM rooms, where the gate counts main-agent turns (section 8, room limits).

**Sender identity comes from Switch.** For every event the gate takes the
sender's real id from Switch and resolves it to an identity: either a Switch
user acting for themselves, or an agent with an `owner_id`. Text such as "this
is Om" changes nothing. An agent with no reported owner fails closed.

**Checks before any command runs** (`runtime.py`):

1. The message is addressed to this gate.
2. Every participant in the room is a known identity. For every agent in the
   room, the owner Switch reports (`get_agent_detail`) matches the identity
   map. Any unknown member or mismatch and the gate stays silent.
3. The sender is a member of the room.
4. The room level is computed from fresh membership (section 8). If anyone in
   the room is not on the owner's trust list, the level is none and the gate
   stays silent.
5. The command is parsed, then authorized (`policy.authorize`) from the
   sender's identity, the owner's consent mode, and the room name.

**One session per room (the room pool).** Switch delivers a room's addressed
messages only to a session connected to that room, and one connection holds one
room session at a time. A gate on a single connection would be absent from every
other room. When an agent has no session in a room, Switch answers on its
behalf ("I don't have a session connected to this room ..."), and that notice,
sent under the gate's name, reads to the other gate like a malformed command.
`trustnet/room_pool.py` therefore gives a gate one connection per open room (an
anchor), merges their events, waits until Switch shows the addressed gate `live`
in a room before posting to it, and reconnects an anchor that Switch no longer
shows live. A gate anchors at most the newest 24 open rooms, because Switch
allows 32 connections per agent. If you write your own gate-side component, you
need the same property: be connected to every room you are addressed in.

**Agents do not send Switch @-mentions to each other.** Switch refuses an
agent-to-agent @-mention in the planning room. Agents post plain text there and
read the room. The only addressed lines in a DM room are the ones a gate or an
agent's own gate command produces (section 5).

## 4. Rooms

| Room | Created by | Members | Purpose |
| --- | --- | --- | --- |
| `<person>-home` | set up at install | the person, `<person>-gate`, `<person>-hermes` | The person's private surface. The gate posts questions (Q#), proposals (P#), share cards, answers to ask-around, confirmations and overreach alerts here. The agent reads it with `inbox` and sends owner commands to its own gate from it. |
| `conn-<a>-<b>` | the gate that needs it first | `<a>-gate`, `<b>-gate` | The gate-to-gate channel. Names are the two person names, sorted: `conn-om-priya`. Carries `hello`, `join-dm`, and ask-around. |
| `dm-<a>-<b>-<slug>` | the gate that received `dm` | `<a>-gate`, `<b>-gate`, `<a>-hermes`, `<b>-hermes` | Where the two agents plan, in plain language. `<slug>` is the goal, lower-cased, reduced to `[a-z0-9-]`, 32 characters at most (`plan` if empty); a numeric suffix keeps names unique. The gates sit in it to relay proposals and consent. Archived when the plan is confirmed, or at the room limits (section 8). |
| `gift-<asker>-<for>-<slug>` | the asker's gate | the two gates only | Surprise-mode gift ideas and claims. Agents are not members. Private read and write visibility, archived when the session ends or expires. |

Every room is created `internal_only`.

Ask-around reuses the `conn-<a>-<b>` rooms; it creates one if it does not
exist.

## 5. Message grammar

All commands are one line. The leading `@<person>-gate` is the addressee. The
parser also accepts a fenced code block, smart quotes, and a trailing `.,;:!`,
and the verb is case-insensitive. Free text is always a double-quoted string,
at most 140 characters, with no double quote inside, one line. A gate treats
quoted text as data and always shows it quoted. Dates go through `dateparser`
in `Asia/Kolkata` and prefer the future; always send ISO.

A command that is a known verb written badly gets `Invalid command. ...` back
(a `ParseError`; the gate then notes overreach if the sender is the other
side). Text that is not a known verb is an `Unknown` command: the gate replies
with its command list, and notes overreach if the sender is the other side.

### 5.1 Owner and agent to the owner's own gate

Sent from the person's `<person>-home` room.

| Command | Example | Who may send | Notes |
| --- | --- | --- | --- |
| `dm <person> "<goal>"` | `@om-gate dm rahul "something fun Sunday evening, not pricey"` | owner, or any of the owner's agents | Opens a planning room with a listed friend. Ignored if the friend is not on the trust list. |
| `ask-around "<question>"` | `@om-gate ask-around "tent to borrow, Nov 14-16"` | owner, or the owner's agents | Fans a question out to every listed friend's gate (section 7e). |
| `yes P<n>` / `no P<n>` | `@om-gate yes P1` | owner's Switch user; or `<person>-hermes` if consent mode is `via-agent` | Records the owner's vote on a proposal. |
| `answer <Q<n>\|P<n>\|A<n>> "<text>"` | `@om-gate answer Q3 "yes, up to ₹1,500"` | same as `yes`/`no` | `Q#`: answers a question. `P#`: text must be `yes` or `no`. `A#`: answers an ask-around question from a friend. |
| `trust <person> <level>` | `@om-gate trust priya close` | owner's Switch user only | Level is `acquaintance`, `friend` or `close`. Never an agent. |
| `view-as <person>` | `@om-gate view-as rahul` | owner's Switch user only | Shows what that person's side can learn. |
| `ledger` | `@om-gate ledger` | owner's Switch user only | Lists what has been shared, with whom, when. |

### 5.2 Gate to gate

Sent in `conn-<a>-<b>` (`hello`, `join-dm`, `ask-around`, its `answer`) or in
the `dm-<a>-<b>-*` room (`consent`, and the forwarded `propose`). The gate
checks that the sender is exactly `<friend>-gate`, an agent owned by the friend,
in the right room.

| Command | Example | Who may send | Room |
| --- | --- | --- | --- |
| `hello trust-network/<major>[.<minor>] <capability,...>` | `@rahul-gate hello trust-network/1 hello,join-dm,free,ask,propose,consent,ask-around,gift-ideas,claim` | the friend's gate | `conn-<a>-<b>` |
| `join-dm <room> "<goal>"` | `@rahul-gate join-dm dm-om-rahul-sun "something fun Sunday evening"` | the friend's gate | `conn-<a>-<b>` |
| `consent P<n> yes\|no via-agent\|direct <sha256>` | `@rahul-gate consent P1 yes via-agent 2f749caf9dd6cbd99a2062e33534cad46b8f634eb2b2925e60a68b15cfa87cc4` (the last field is the SHA-256 of the card text; see 7a) | the friend's gate | the `dm-` room the proposal belongs to |
| `propose P<n> <card>` (forwarded) | `@rahul-gate propose P1 2026-11-08T21:00:00+05:30 120m "Bowling + dinner" @ "Smaaash, Indiranagar"` | the friend's gate | `dm-<a>-<b>-*` |
| `ask-around A<n> "<question>"` | `@rahul-gate ask-around A1730000000000000000 "tent to borrow, Nov 14-16"` | the friend's gate | `conn-<a>-<b>` |
| `answer A<n> "<text>"` | `@om-gate answer A1730000000000000000 "Profile lists, no lending promise: has: tent"` | the friend's gate | `conn-<a>-<b>` |

### 5.3 Planning and asks, any member of the room

These are accepted from any member of the room at the room's level. The gate
applies the trust level of the room, not of the sender.

| Command | Example | Notes |
| --- | --- | --- |
| `free <date\|range>` | `@om-gate free 2026-11-08..2026-11-09` | Busy blocks for each day in the inclusive range. Titles are shown at `friend` and `close`, and blanked at `acquaintance`. |
| `ask <fact> [<fact> ...]` | `@om-gate ask diet interests` | Values at the room level, or `<fact>: not shared with you`. A fact that is hidden and a fact that does not exist look the same. |
| `ask-owner Q<n> "<question>"` | `@om-gate ask-owner Q3 "Is ₹1,500 per person okay?"` | Sent by an agent to its own gate. Puts the question in the owner's home room. |
| `propose P<n> <start> <duration> "<title>" @ "<place>"` | `@om-gate propose P1 2026-11-08T21:00 2h "Bowling + dinner" @ "Smaaash, Indiranagar"` | Sent by an agent to its **own** gate in the DM room. Title and place: 60 characters at most; the place only `[A-Za-z0-9 ,.'&-]`; the title has no quotes or `@`. Duration: 1 minute to 24 hours (`2h`, `90m`). The start must have a timezone (parsed as IST if none). |
| `counter P<n> P<n> <start> <duration> "<title>" @ "<place>"` | `@om-gate counter P1 P2 2026-11-09T19:00 2h "Bowling + dinner" @ "Smaaash, Indiranagar"` | Parses, but no handler exists in v1 (see section 10). To change a plan, propose a new `P<n>`. |
| `gift-ideas <occasion> <date> [budget <amount> \| ₹<amount>]` | `@om-gate gift-ideas birthday 2026-11-20 budget<=3000` | Only works in a gift room (section 7d). |
| `claim "<item>"` | `@om-gate claim "Catan Seafarers"` | Only works in a gift room (section 7d). |

### 5.4 What the gate says back

The gate answers in the room where it was asked. It does not use commands for
its replies to `free` and `ask`: they are plain lines. Some replies you will
see:

- `<fact>: <value>` or `<fact>: not shared with you`.
- `<iso start> .. <iso end> <title or busy>` per block, or `Nothing busy in this range.`
- `Invalid command. Commands: ...` for a malformed command.
- `Not allowed.` when the other side sends an owner-only command.
- `<ref> not recorded: wait for <friend>-hermes to reply here first.` (the speak-first guard, 7a)
- `<ref> not recorded: <Person> answers this directly (consent is set to direct), not through an agent.`
- `join-dm refused: <reason>.` (section 6)
- In the owner's home room: `✅ P1: <card> · Om ✅ via agent · Priya ✅ via agent`, or `❌ P1 declined`.

## 6. Handshake and versioning

**Form.** `hello trust-network/<major>[.<minor>] <capability,...>`, for example:

```
@rahul-gate hello trust-network/1 hello,join-dm,free,ask,propose,consent,ask-around,gift-ideas,claim
```

The capability list is comma-separated, lower-case words and hyphens only.
v1 gates advertise: `hello, join-dm, free, ask, propose, consent, ask-around,
gift-ideas, claim`.

**When it is sent.** The gate opening a planning room says hello in
`conn-<a>-<b>` immediately before `join-dm`. The receiving gate records the
peer, and replies with its own hello once (it remembers the rooms it has said
hello in since it started). Only the friend's gate may say hello, only in the
`conn-<pair>` room.

**What is recorded.** Per person, in `peers.json`: for each friend the protocol
string, the major version, the capability list, the room and the time.

**Compatibility.** Same major version. The minor version is parsed and ignored.

**What it gates.** Two things:

- `join-dm` from a peer whose gate has not said a compatible hello is
  refused. The gate posts, in plain text (not addressed, so the other gate does
  not read it as a bad command): `join-dm refused: <friend>'s gate hasn't said
  hello (no trust-network/1 handshake).` or `... <friend>'s gate speaks
  trust-network/2; this gate speaks trust-network/1.` It also posts a home notice
  to its owner: `Didn't open a planning room with <Friend>: <reason>.`
- A `propose` forwarded by the peer gate is refused with the handshake reason
  without a compatible hello.

**A `hello` that is not the handshake form is an unknown command**, not a
malformed one: "@om-gate hello there" gets the command list, exactly as it did
before the handshake existed (from the other side it is still noted to the owner
as "something that isn't a command").

**How a future v2 should behave.** A v2 gate that wants to talk to a v1 gate
should send `trust-network/1` forms and not use commands outside the v1
capability list, or refuse to plan with it. A v1 gate that receives
`trust-network/2` records the hello but refuses `join-dm` and forwarded
proposals from that peer. Capability lists are advisory in v1: they are
recorded and never read to gate behaviour. A v2 should add capabilities to the
list rather than change the meaning of v1 commands.

**Current limits.** Ask-around and gift rooms do not check the handshake yet. A
pre-handshake gate reads `hello` as an unknown command and, if it is the other
side that sent it, notes it as overreach to its owner; it then accepts
`join-dm`. Rollout needs both gates on the same version.

## 7. Flows

### 7a. Planning and consent

1. Om tells his agent "plan something with Priya Monday". The agent calls
   `dm("priya", "<goal>")`, which posts `@om-gate dm priya "<goal>"` in
   `om-home`.
2. `om-gate` checks that priya is on Om's trust list, finds or creates
   `conn-om-priya` (inviting `priya-gate`), creates `dm-om-priya-<slug>` and
   invites `priya-gate`. It says hello in the connection room, then posts
   `@priya-gate join-dm <room> "<goal>"`.
3. `priya-gate` checks the handshake, joins, and runs the same setup on its side.
   Each gate verifies the room's membership and level, then invites its own
   person's agent to the DM room.
4. Each gate writes a **share card** for its own agent: the facts and calendar
   its level lets this friend learn, built from the same policy code that
   answers `ask`. It posts the card to its person's home room and stores it. The
   card is guidance: it tells the agent its limits, and it does not confine the
   agent (section 9).
5. The agents wake (section 10), read the card with `inbox`, and plan in plain
   language with `dm_read` and `dm_post`. They can ask their own person: the
   agent sends `@om-gate ask-owner Q3 "..."` and the gate puts `Q3: ...` in
   `om-home`; Om's answer comes back through `answer Q3 "..."`, and the gate
   posts `Q3 answer from om: ...` in the DM room (flow b).
6. When the agents agree, **one side** proposes, by posting the `propose` line
   addressed to its **own** gate in the DM room, for example
   `@om-gate propose P1 2026-11-09T19:30 2h "Board games evening" @ "Dialogues, Koramangala"`.
   Three guards run:
   - Only `<person>-hermes` (or the friend's gate, forwarding) may propose.
   - **Speak-first guard:** the gate records the proposal only if the friend's
     agent has itself posted in this room. Switch's automatic join greeting and
     Switch notices do not count, and neither does a message that starts with
     `@`. Otherwise the gate posts `P1 not recorded: wait for <friend>-hermes to
     reply here first.`
   - **Immutable IDs:** a `P<n>` is never rebound. IDs are stored per person,
     across all rooms and friends. Reusing an ID gets a plain-text refusal
     asking for a fresh ID in both gates. Choose an ID unused on both sides;
     a collision at the receiving gate can leave only the opening side holding
     that proposal, so propose again with a fresh ID and do not vote on the collision.
   - A proposal whose start is at or before the gate's current time is refused.
     Malformed dates and durations outside 1 minute to 24 hours get
     `Invalid command.`; even extremely large durations cannot crash dispatch.
7. `om-gate` stores the proposal with the card
   `<iso start> <minutes>m "<title>" @ "<place>"`, posts
   `P1: <card> · reply @om-gate answer P1 …` in `om-home`, writes a ledger
   entry, and forwards `@priya-gate propose P1 <card>` into the DM room.
   `priya-gate` records it from the peer gate (after a handshake check), and
   posts it in `priya-home`. The forwarded proposal is not forwarded again.
8. Each person answers through their own side: `answer P1 "yes"` (or
   `yes P1`). The gate checks the sender is allowed to carry consent (table 5.1)
   and records `[vote, via]`, where `via` is `direct` (the person's Switch user)
   or `via-agent` (their agent, in `via-agent` mode).
9. The gate relays its person's vote to the friend's gate:
   `@priya-gate consent P1 yes via-agent <sha256-of-card>`. The fingerprint is
   `sha256` of the card text. The receiving gate records the vote only if the
   room is the proposal's room, the sender is the friend's gate, and the
   fingerprint matches the card it holds. A vote that does not match is ignored,
   so a yes cannot be applied to a different plan.
10. A `no` from either side marks the proposal declined; both home rooms show
    `❌ P1 declined`. Two yeses mark it confirmed. Each gate posts
    `✅ P1: <card> · Om ✅ via agent · Priya ✅ via agent` in its home room,
    creates a `Confirmed plan` room document in the DM room, writes the ledger,
    and stops the room's limit counter. The gate that receives the second vote
    from the peer also archives the room; an archived room accepts nothing
    except `consent`, so the last relay still lands.
11. Each agent calls `cal_add` with the agreed time, title and place. The
    calendar is the person's; the gate does not write it.

A changed plan is a new proposal with the next number. `consent` that arrives
for a proposal that is not pending (already decided) does not change it.
Duplicate votes keep the first vote. The gate explains a refused relay's room,
sender or fingerprint mismatch in plain text, without recording a vote.
Home-room answers for a closed planning room are refused. Limit-closed rooms
ignore subsequent messages, including consent; confirmation archiving still
allows the final consent relay to reach the pending peer.
Room deadlines, turn counts and closure are saved per person in `room-watches/`
and restored on restart. Proposal and question state is in `coordination.json`;
handshakes are in `peers.json`. A restarted gate replies to a new hello once
again. Persisted peers remain compatible until a new hello changes their version.

### 7b. A question to your own person

1. The agent posts `@om-gate ask-owner Q3 "Is ₹1,500 per person okay?"` in the
   DM room. Only `om-hermes` can do this; other senders are told to use their own gate.
2. `om-gate` stores `Q3` (never rebound), and posts `Q3: "..." · reply @om-gate
   answer Q3 …` in `om-home`. Question IDs are also per person across rooms;
   reusing one gets a refusal asking for a fresh ID.
3. Om replies to his agent. The agent calls `answer("Q3", "yes, up to ₹1,500")`,
   which posts `@om-gate answer Q3 "yes, up to ₹1,500"` in `om-home`.
4. `om-gate` checks the sender (Om, or `om-hermes` when `via-agent`), posts
   `Q3 answer from om: yes, up to ₹1,500` in the DM room, and records the answer.

### 7c. Facts with trust-level filtering

1. A member of a room addresses a gate: `@om-gate ask diet interests`.
2. The gate computes the room level (section 8) and returns the facts the level
   allows. Anything else is `<fact>: not shared with you`, with no hint whether
   the fact exists or what level it has.
3. For every fact that was asked for but not shown, the other side's request
   raises an overreach note in the owner's home room, at most one per person and
   field per 10 minutes: `Rahul's side asked for your address (private)` or
   `... (not a field you have)`.
4. `free <date|range>` returns busy blocks. At `acquaintance` the titles are
   blanked; at `friend` and `close` they are shown.
5. Every value shown goes in the ledger: field, value, to whom, room, time.
   The owner reads it with `ledger`, and previews what a friend can learn with
   `view-as <person>`.

`ask` in a DM room answers at the DM room's level, which is the lowest level
among the friends present.

### 7d. Gifts (surprise mode)

Agents never put gift traffic in a planning room; they use `gift_ideas` and
`claim`, which post `@om-gate gift-request {...}` in the agent's home room.

1. `om-gate` checks the friend is on the trust list, creates
   `gift-om-<friend>-<id>` with private visibility, invites `<friend>-gate`, and
   posts `@<friend>-gate gift-ideas <occasion> <date> budget<=<amount>`.
2. The friend's gate (the recipient) never asks its owner anything and never
   posts to its home. It computes ideas from stored facts at the room's level:
   wishlist items within budget, items already `taken`, items `over budget`, and
   `interests` and `sizes` if the level allows. It replies in plain text:
   `@om-gate gift-result {...}`.
3. The recipient's ledger entry is sealed until the day after the occasion.
4. `claim "<item>"` in the same room marks an item taken. Claims are hidden from
   the recipient's own view of their wishlist until after the occasion, and
   marked taken for other askers.
5. The asker's gate relays the result to its home as `gift-result <token> {...}`;
   the room is archived on a claim or after 10 minutes.
6. In a gift room, `ask` is refused, overreach is logged and not posted home,
   and no consent relay runs.

The seal is a courtesy: workspace admins can read rooms.

### 7e. Ask-around

1. The owner or the owner's agent posts `@om-gate ask-around "<question>"` in
   `om-home`. Only Om's `self`-level home room can start one.
2. `om-gate` assigns a reference `A<ns>` and, for every friend on the trust list,
   finds or creates `conn-<a>-<b>` and posts `@<friend>-gate ask-around A<ns>
   "<question>"`. It posts `A<ns> asking around: "<question>"` to home. The
   question expires after 5 minutes.
3. Each friend's gate accepts it only from the friend's own gate in
   `conn-<pair>`. It replies on its own, from facts at that level: the `has`
   and `recommends` facts, prefixed `Profile lists, no lending promise:`.
   It also puts a local `A<ns2>` question in its owner's home so the person
   can answer in their own words.
4. Replies arrive as `answer A<ns> "<text>"` in the same conn room. The asker's
   gate accepts one per friend, before expiry, and posts the collected answers
   in home. Each reply is ledgered.
5. A friend's `answer A<ns2> "..."` from their own side is checked against the
   room membership and trust list again before it is sent.

## 8. Security properties

**Enforced in code, with no LLM involved:**

- **Fixed forms plus quoted free text.** Anything crossing a gate boundary is a
  parsed command. Free text is quoted, one line, capped at 140 characters with
  no double quote, so it cannot become an instruction.
- **Identity from Switch.** Senders and room members come from Switch metadata.
  A claimed name is ignored. Owner and agent ownership is re-read on every
  command, and the gate stays silent on any mismatch.
- **Room level (Rule 1).** The level of a room is the lowest level the owner
  gives any person in it, counting the owners of every agent in the room,
  except the owner and the owner's own agents. Someone not on the list means
  the gate says nothing. A room with only the owner's side is `self`.
- **Level table.** Busy times at every level; event titles at `friend` and
  `close`; facts tagged `acquaintance`, `friend` or `close` at that level and
  above; `private` never.
- **Owner commands are the owner's.** `trust`, `view-as` and `ledger` are never
  accepted from an agent, and no owner command is accepted across the boundary
  (the other side gets `Not allowed.` and the owner gets an overreach alert).
- **Two yeses.** A plan is confirmed only when both people have voted yes.
  Either person's no declines it.
- **Immutable proposal and question IDs.** An ID is never rebound to a
  different plan or room.
- **Fingerprint.** A `consent` relay carries `sha256` of the card text, and the
  receiver rejects a vote whose fingerprint does not match the card it stored.
  A consent line without a fingerprint parses, but is never accepted.
- **Consent mode.** `consent.default` in a person's `trust.yaml` is `direct`
  (only their Switch user can say yes, no, answer) or `via-agent` (their
  registered agent, `<person>-hermes`, may carry consent). The confirmation
  records which one was used per person: `via agent` or `direct`. An agent's
  yes in `direct` mode is refused and the gate says so in the room.
- **Speak-first guard.** An agent cannot propose a plan until the friend's agent
  has spoken in the room.
- **Agents can only tighten.** The `fact_set` tool can only move a fact toward
  `private`.
- **Overreach alerts.** A malformed command, a non-command, an owner-only
  command, or a request for a fact the room may not see, from the other side,
  becomes one note in the owner's home room: `<Person>'s side tried ...`, at
  most one per person and field per 10 minutes. In a gift room it is logged and
  not posted.
- **Ledger.** Every disclosure is logged: field, value, to whom, room, time.
- **Room limits.** A DM room closes after 20 main-agent turns or 30 minutes,
  whichever comes first: the gate posts a summary to home and archives it.

**Left to the agent's judgement:**

- **The share card is guidance, not a fence.** The agent already knows its
  person. The gate enforces what *the gate* discloses (`ask`, `free`, the
  proposal fixed form). It cannot stop an agent volunteering something in the
  DM room's plain text. The `dm_post` tool description and the skill tell the
  agent to stay inside the card, and the agent is the one that has to.
- **Treating the other side as data.** The skill and tool descriptions tell
  agents that room text is quoted data, to pass relayed questions to the person
  and never act on them. A model can fail at this.
- **When to ask the person,** and what to settle from memory.

## 9. Bringing a new agent framework

You need two things.

1. **A way to call the tools.** `tn --as <person> mcp` is an MCP server over
   stdio, run for one person. It reads the person's registration key from the
   environment, and registers `<person>-hermes` on first use. Tools:
   `inbox`, `answer`, `dm`, `dm_read`, `dm_post`, `ask_around`, `cal_add`,
   `fact_set`, `ask`, `gift_ideas`, `claim`. The tool descriptions are the
   agent's instructions; the skill text is `skills/trust-network/SKILL.md`.
2. **Something that wakes the agent.** An agent only acts when it gets a
   message, and nothing in Switch sends one when the other side replies. Poll
   `tn --as <person> watch`: it reports unread home items and each DM room whose
   newest message is someone else's and changed since the last watch. It does
   not consume the inbox.

**Hermes** does this with a cron job every minute whose pre-check script
(`scripts/hermes/tn-inbox-watch.sh`) runs `tn --json watch`. It wakes the agent
only when there is news, and passes it the prompt in
`scripts/hermes/tn-watch-prompt.md`.

**Any other CLI agent** can be run with `tn wake`. It polls `watch`, wakes the
agent with a prompt on stdin, reads the reply on stdout, and lets the person type
to the agent in the same terminal:

```
tn --as priya wake --agent codex
tn --as priya wake --cmd "my-agent --stdin"
```

Each prompt carries the person's persona (`examples/<person>/agent.md` if
present), the skill, the recent chat with the person, and what just happened.
The agent replies with one or two lines for the person, or `[SILENT]` if
nothing needs them. A per-person lock refuses a second runner. A failed turn is
carried into the next one.

The `codex` preset runs `codex exec` with only the trust-network server. Codex
refuses MCP tool calls unless the server sets
`default_tools_approval_mode="approve"`, and the preset passes it. If you
configure Codex yourself, set that.

**What the agent must do,** in the order a plan goes: call `dm`; read the share
card with `inbox`; plan with `dm_read` and `dm_post` in plain text; ask its person
only what it does not know; propose through **its own gate** with one
`dm_post` of the `propose` line; wait for its person's yes or no and call
`answer`; when the gate posts ✅, call `cal_add`. Never answer for the person.

**Evidence.** Om's Hermes planned with Priya's Codex agent end to end on
2026-11-06 (14:44 IST): Priya's agent offered Mon 9 Nov 19:30, the two settled a
venue and price, Om's side proposed `P1`, both people said yes, both home rooms
showed `✅ P1 ... · Om ✅ via Hermes · Priya ✅ via Hermes`, and both calendars
have the plan. (The confirmation text now says `via agent`.) The transcript is
`data/phase26-hermes-codex-20261106-1444.txt`.

## 10. Known limits (v1)

- **Naming.** The agent slot is `<person>-hermes` for every framework.
- **`counter` has no handler.** It parses, but the gate does not act on it; to
  change a plan, propose with a new `P<n>`.
- **`gift-ideas` outside a gift room** is rejected as an unknown command by
  `authorize` (the runtime names it `giftideas`, which is not in the known set),
  so it only works through the gift flow.
- **Handshake coverage.** Ask-around and gift rooms do not check the handshake.
  Capabilities are recorded and never read.
- **Hello memory.** The set of rooms a gate has said hello in is held in memory.
  After a restart a gate may say hello again; that is harmless.
- **ID collisions.** `P<n>` and `Q<n>` are chosen by the agents, and they are
  per person. If the friend's gate already holds a `P1`, a forwarded `P1` is
  silently dropped, and the agent must propose with the next number. Agents are
  told to use a new number for any change, but nothing assigns them.
- **Agent-side leaks.** What an agent says in the DM room is its own
  judgement. The gate cannot stop it.
- **Room limits.** 20 agent turns or 30 minutes. A plan that needs a person who
  answers slowly can hit the time limit.
- **Ask-around expires** after 5 minutes. Gift sessions after 10.
- **Connections.** A gate anchors the newest 24 open rooms.
- **Calendars.** The gate reads calendars (`.ics`); the agent writes them
  (`cal_add`). A confirmed plan is not on a calendar until the agent adds it.
- **Switch is trusted.** Identity and membership come from Switch. A
  compromised Switch, or an admin, can read every room, including gift rooms.
- **A pre-handshake gate** reads `hello` as an unknown command.
- **Language.** The grammar is English and ASCII-punctuated. Smart quotes are
  normalised.
