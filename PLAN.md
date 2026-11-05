# trust-network: build plan

*Flip the Switch hackathon. Track 02 (Best Personal or Creative Workflow) + Code with Wispr. Solo build. Submissions close **Nov 7, 23:59 IST**; target submit **Nov 7, 20:00 IST**. Supersedes `PLAN-v1.md`, `PLAN-v2.md` and `PLAN-v3.md`. Pit Crew is dropped.*

> **One line:** Bring any agent, whether Claude Code, Codex, OpenCode or a personal agent like Hermes on Discord. Your agent can plan things with your friends' agents, ask them for gift ideas, or ask around for a tent. Each friend's side learns only what your trust level for them allows, and nothing is committed until both people say yes.

---

## 0. Decisions so far

| Question | Decision |
|---|---|
| Scope | trust-network only. Pit Crew dropped. |
| Where people talk | **Discord** — but each person DMs (or uses a private channel with) **their own Hermes bot**, not Switch's own Discord connection. Switch's own Discord bridge / `#om-home` stays optional, for Om's secondary `view-as`/`ledger` surface only; bundled Mattermost remains the setup-free fallback for judges on that optional path. |
| Where agents talk to each other | **Agent-only Switch rooms** (`create_room(internal_only=True)`), shown in Switch Console. A short summary goes to each person's own Hermes (optionally also the Discord home channel). |
| Who talks across people | **Each person's own main agent, directly**, in a DM room per conversation (`dm-om-rahul-<slug>`, agent-only). **Both people's main agent is their own Hermes, on Discord** (decided Nov 5, see below): Om's Hermes acts in Switch through `tn mcp` as `om-hermes`; Rahul's Hermes — a second profile with its own Discord bot — acts as `rahul-hermes`. No envoy sits between them (dropped Nov 5, see below), and no managed Codex agent is in the flow. |
| **No envoys (decided Nov 5)** | Main agents talk to each other directly in agent-only DM rooms. Gates are unchanged: they still compute room-level access from Switch membership, record every disclosure, and carry proposals and consent. Reason: simpler, one hop fewer — Om's call. |
| **Both on Hermes, on Discord (decided Nov 5)** | Om's main agent is his existing Hermes (Agent v0.22.5, already running on the Azure VM, host `hermes`, user `om`), acting in Switch as `om-hermes`; Rahul's main agent is a second Hermes profile on the same VM, with its own Discord bot, acting as `rahul-hermes` — both talked to on Discord, not Telegram, and Rahul is played from a different Discord account Om records from. History in one line: earlier the same day Om had briefly swapped to Hermes/Telegram for himself while planning a Switch-managed Codex agent (`rahul-agent`) for Rahul; this decision drops `rahul-agent` and settles both people on Hermes via Discord instead. `om-agent` (managed Codex, Discord `#om-home`) stays as Om's optional secondary surface only — `view-as`, `ledger`, overreach notes, or typing `yes P1` directly. |
| Who holds private data | Each person's **gate**: our code, no LLM, running on the person's own machine |
| Machines | **Om's side on the laptop**: Switch server (Docker, run by Console), Console, `om-gate`, `priya-gate`, and (optional, secondary) `om-agent`. **The Azure VM hosts both people's agents** (a demo shortcut): both Hermes profiles (`om-hermes`, `rahul-hermes`), each with its own `tn mcp` instance and Discord bot, plus Rahul's `rahul-gate`. The `rahul-vm` `switch-agent-controller` enrollment (phase 02/03) is no longer needed by any flow now that no managed agent runs through it — it's optional, left enrolled. Joined by **Tailscale**: `tailscale serve` gives the laptop's Switch server an https address only tailnet devices can reach. |
| Custom envoy runner | **Unused after Nov 5.** Phase 13b built it (native tool denial, isolated state; macOS Seatbelt adds read confinement, Linux needs a separate OS user/container); the code stays in the repo but nothing calls it now that main agents talk directly. |
| Planner agent | None. Your main agent plans directly with your friend's main agent. |
| Tally / group secrets | Dropped. When an agent lacks a fact, it **asks its person**. |
| Trust levels | **close / friend / acquaintance**, per person, in each owner's own list. Mutual: each side sets its own level. |
| Preferences | Facts on your profile (vegetarian, no alcohol, interests, wishlist …), each tagged with the lowest level that may see it |
| Demo cast | **Om:** his own Hermes, on Discord, talking directly to Rahul's Hermes in DM rooms through `tn mcp` as `om-hermes`; `om-agent` (Codex, managed, Discord `#om-home`) stays as an optional secondary surface. **Rahul:** his own Hermes, on Discord (a second Discord bot/account, same VM as Om's for the demo), talking through `tn mcp` as `rahul-hermes`. **Priya:** a gate with facts only. No Claude Code, and no managed Codex main agent, anywhere in Switch. |
| Scenes | (1) two-person outing, (2) gift ideas that keep the surprise, (3) ask around, plus an overreach alert and `view-as` |
| Gift privacy | Nothing reaches the person receiving the gift until after the occasion. Claimed items are hidden from them but shown to other askers. |
| Consent | Both say yes to **their own Hermes, in Discord**: Om's is recorded "Om ✅ via Hermes" (or he types `@om-gate yes P1` directly in `#om-home`); Rahul's is recorded "Rahul ✅ via Hermes". Both `trust.yaml` files set `consent.default: via-agent` — a fixture change phase 14 makes; see §3. |
| Calendars | Fake `.ics` fixtures in the repo. Main agents write accepted plans into them through `tn mcp`'s `cal_add` tool (both sides now, since neither runs a shell-capable managed agent). |
| Name | `trust-network` |
| Om’s agent (changed Nov 5, then superseded) | **Codex** (`om-agent`) was briefly Om’s managed main agent in `#om-home`. With the Nov 5 main-agent swap, Om’s main agent is **Hermes**; `om-agent` stays in `#om-home` as an optional secondary surface only (`view-as`, `ledger`, overreach notes, direct `yes P1`). Console 0.40.1’s controller cannot start OpenCode 2.x (it waits for `opencode server listening`, while OpenCode prints `server listening`); moot, since OpenCode was only ever used for the dropped envoy. |
| Rahul’s agent (changed Nov 5, then superseded the same day) | A Switch-managed **Codex** agent (`rahul-agent`, on `rahul-vm`) was briefly planned as Rahul’s main agent. Dropped the same evening: Rahul’s main agent is his own **Hermes** profile (`rahul-hermes`), on Discord, same as Om’s. No managed Codex main agent remains anywhere in the design; the `rahul-vm` controller enrollment stays, unused and optional. |

---

## 1. Why this matters (README opening and video hook)

- **Everyone has an agent now, but agents can't safely work with other people's agents.** They either share nothing ("when are you free?" takes a day of messages) or share whatever they're asked.
- **Instinct's Trusted Person Network proved people want this:** a $10B valuation, and 300k+ agent coordinations in its first week (per its founder). But it has two problems:
  1. **One vendor.** Both people must use Instinct.
  2. **The agent enforces its own rules.** Reviewers note its terms describe no check the agent can't bypass, and one user saw it describe somebody else's financial document.
- **trust-network:**
  - **Any agent can join.**
  - **The rules are enforced by code you can read and by Switch's identity checks,** never by a prompt.
  - **The agent that knows your whole life never talks to anyone else's agent.**
  - **Each person's data and agents stay on their own machine.**

---

## 2. Cast, machines, rooms and agents

### People and their agents (demo)

| Person | Runs on | Main agent (knows their life; talks directly to friends' agents in DM rooms) | Where they talk to it | Gate | Trust list |
|---|---|---|---|---|---|
| **Om** | Azure VM (Hermes), laptop (`om-gate`, optional `om-agent`) | His own Hermes, acting in Switch through `tn mcp` as `om-hermes` | Discord, DM (or a private channel) with his own Hermes bot (primary); Discord `#om-home` via `om-agent` (optional, secondary: `view-as`, `ledger`, overreach, direct `yes`) | `om-gate` | Rahul: close, Priya: friend |
| **Rahul** | Azure VM (a second Hermes profile, same VM as Om's for the demo) | His own Hermes, acting in Switch through `tn mcp` as `rahul-hermes` | Discord, DM with his own Hermes bot — a second Discord bot, played from a different Discord account Om records from | `rahul-gate` | Om: close |
| **Priya** | laptop | none in the demo (optional: OpenCode) | — | `priya-gate` | Om: friend |

Rahul and Priya are separate Switch users with their own registration keys. **The Azure VM now hosts software for both people** (a demo shortcut, called out so it isn't mistaken for a security boundary): `om-hermes` acts under Om's own Switch key, `rahul-hermes` acts under Rahul's own Switch key — the two are isolated by Switch identity, not by machine. Rahul's gate (`rahul-gate`) also runs on the VM. The `rahul-vm` `switch-agent-controller` enrollment (from the briefly-planned managed-Codex design) is no longer needed by any flow; it stays enrolled, unused. The one-machine judges' layout still works the same way it always did: both Hermes profiles and all gates on one machine.

### Machines and network

```
 LAPTOP (Om)                                               AZURE VM, on the same tailnet
 ───────────                                               (hosts BOTH people's Hermes)
 Switch server (Docker, run by Console)  ◀──── https ────  om-hermes (Hermes) + `tn mcp` ──── Discord (Om's bot)
   published on the tailnet by                             rahul-hermes (Hermes) + `tn mcp` ─ Discord (Rahul's bot,
   `tailscale serve` as                                    rahul-gate (Python) ─ examples/rahul/    2nd account)
   https://<laptop>.<tailnet>.ts.net                       switch-agent-controller (rahul-vm, enrolled,
 Switch Console (Om) + its controller,                       carries no live traffic — unused)
   optional secondary `om-agent`
 om-gate, priya-gate (Python)
```

- **Why Tailscale Serve:** the controller only accepts an `https` server address, except for `localhost`. Serve gives a real certificate on the tailnet name (the tailnet already has HTTPS certificates on). It's tailnet-only: Serve, never Funnel.
- **Serve the switch-core port, not the Gateway's.** The controller calls `/v1/...` on switch-core. Console picks the ports, so find them with `docker ps`.
- **Everything on the VM goes through the same address:** both Hermes profiles, their `tn mcp` instances, and `rahul-gate` (the `rahul-vm` controller enrollment stays, but nothing runs through it now).
- **The laptop stays awake** during the demo (`caffeinate -dims`). The controller reconnects by itself if the link drops.
- **Judges can run everything on one machine:** all three gates and both Hermes CLI stand-ins against `http://127.0.0.1:53330`, using the local identity exporter, with no controller, VM or Tailscale. The README documents this layout.

### Rooms

| Room | Kind | Members | Purpose |
|---|---|---|---|
| `#om-home` | Discord private channel (optional) | Om, `om-agent` (optional, secondary), `om-gate` | Om's optional secondary surface: `view-as`, `ledger`, overreach notes, and direct `yes P1`. Om's primary surface is his own Hermes bot on Discord, which polls this gate via `inbox`, not this channel. |
| `rahul-home` | Agent-only Switch room | Rahul's Hermes (`rahul-hermes`), `rahul-gate` | Rahul's requests, proposals, consent (`yes P1`); polled by `rahul-hermes` (`inbox`) and relayed to Rahul on Discord — his primary surface |
| `priya-home` | Agent-only | `priya-gate` | Unused in the demo (Priya has no main agent) |
| `conn-om-rahul`, `conn-om-priya` | Agent-only, one per pair | the two gates | The connection itself: ask-around traffic, and setting up conversations |
| `dm-om-rahul-<slug>` | Agent-only, one per conversation | both main agents (`om-hermes`, `rahul-hermes`) + both gates | The main agents plan in plain language; each gate privately hands its own agent a share card at the start, and carries proposals/consent. Archived after agreement, a turn limit or a time limit. |
| `gift-<asker>-<for>-<slug>` | Agent-only, created by the asker's gate, private | the asker's gate + the recipient's gate | Gift questions. Nothing is relayed to the recipient, and the log entry is sealed until the date. |

### Room map

```
 DISCORD (primary: each person's own Hermes bot)        SWITCH, agent-only rooms (agents)              DISCORD (optional secondary)
 ────────────────────────────────────────────────       ──────────────────────────────────────         ────────────────────────────
 Om ⇄ his Hermes bot                                    dm-om-rahul-sun                                 #om-home
   │ tn mcp (om-hermes)                                    om-hermes ⇄ rahul-hermes                       Om ⇄ om-agent
   ▼                                                       om-gate ⇄ rahul-gate (answers,                 (view-as, ledger,
 rahul-home/#om-home inbox ◀────────────────────────                ask-your-person, P1)                  overreach, yes)
                                                         conn-om-rahul (om-gate ⇄ rahul-gate)
 Rahul ⇄ his Hermes bot (2nd Discord account)           conn-om-priya (om-gate ⇄ priya-gate)
   │ tn mcp (rahul-hermes)                               gift-rahul-om-bday (rahul-gate → om-gate, sealed)
   ▼                                                     rahul-home (rahul-gate ⇄ rahul-hermes)
 rahul-home inbox ◀──────────────────────────────────
```

---

## 3. Trust model

### Levels, facts and preferences

```yaml
# examples/om/trust.yaml (only Om edits this: by hand, `tn trust`, or `@om-gate trust …` typed by Om)
people:
  rahul: close
  priya: friend
consent:
  default: via-agent         # Om's answers come through his own Hermes; others see "via Hermes" (both on Hermes, decided Nov 5)
```

```yaml
# examples/rahul/trust.yaml
people:
  om: close
consent:
  default: via-agent         # Rahul's answers come through his own Hermes too (decided Nov 5)
```

*The `envoy:` block that used to sit in both files above (`provider`, `model`, `machine`) configured the
now-dropped envoy runner (phase 13b; the code stays in the repo but is unused after the Nov 5 decision).
It is no longer read when deciding who talks for each person — that's each person's own Hermes profile,
from §2. Unlike the briefly-planned managed-Codex design for Rahul, no Switch agent-management placement
(`create_agent`, a machine, a template) is needed for either main agent now: both `om-hermes` and
`rahul-hermes` register themselves directly through `tn mcp --as <person>`, the same code path — just two
Discord bots and two Hermes profiles on the VM. See §5.*

```yaml
# examples/om/facts.yaml (Om, or Om's agent through `tn fact set`, keeps this current)
calendar: ./calendar.ics
facts:
  diet:          {value: vegetarian,                        level: acquaintance}
  city:          {value: Bangalore,                         level: acquaintance}
  drinks:        {value: no alcohol,                        level: friend}
  interests:     {value: [bowling, board games, sci-fi],    level: friend}
  has:           {value: [projector, camping stove],        level: friend}   # for ask-around
  recommends:    {value: {dentist: "Dr. Rao, 12th Main"},   level: friend}
  neighbourhood: {value: Indiranagar,                       level: close}
  sizes:         {value: {tshirt: M},                       level: close}
  wishlist:      {value: [Catan Seafarers, Kindle Paperwhite, Hario V60], level: close}
  address:       {value: "…",                               level: private}   # never shared
```

| What | acquaintance | friend | close |
|---|---|---|---|
| Busy blocks | ✅ | ✅ | ✅ |
| Event titles | ❌ | ✅ | ✅ |
| Facts tagged `acquaintance` | ✅ | ✅ | ✅ |
| Facts tagged `friend` | ❌ | ✅ | ✅ |
| Facts tagged `close` | ❌ | ❌ | ✅ |
| Facts tagged `private` | ❌ | ❌ | ❌ |
| Not on the list at all | gate answers nothing | | |

### Rules the gate enforces (in code, with tests)

1. **Room level = the lowest level the owner gives anyone in the room.** "Anyone" covers the humans and the owners of every agent in the room, except the owner and the owner's own agents. Membership comes from Switch (`list_participants`, `get_agent_detail`), never from message text. If anyone in the room isn't on the list, the gate stays silent.
2. **Consent can't be faked.** `yes`/`no`, `answer`, `trust`, `view-as` and `ledger` are accepted only:
   - from the owner's Switch user, or
   - from the owner's registered personal agent, where the consent mode allows it. Those are recorded as `via-agent`.

   `trust`, `view-as` and `ledger` are owner-only.
3. **Agents can only tighten.** `tn fact set` and the `fact_set` MCP tool can make a fact more private, never less.
4. **Fixed forms across the boundary.** Proposals carry an ID, an ISO time, a duration, a title (≤60 characters) and a place (≤60 characters, from `[A-Za-z0-9 ,.'&-]`). Free-text questions (`ask-owner`, `ask-around`) are capped at 140 characters and always shown as quoted data.
5. **Surprise mode.** In `gift-*` rooms, the gate:
   - never asks its owner anything and never relays to them;
   - writes a ledger entry sealed until `reveal_after`;
   - hides claims from its owner's own view of the wishlist.
6. **Everything disclosed is logged** to `ledger.jsonl`: field, value, to whom, which room, when. Writing a brief counts as disclosing every fact in it.
7. **Share cards, not guarantees.** At the start of a DM, each gate privately hands its own main agent a **share card** — built from the same policy code that answers `ask` — listing what the friend's trust level allows. This tells the agent its limits; it doesn't enforce them the way the old envoy brief did, because the main agent already knows its own person's whole life and isn't confined to the card's contents. What crosses the boundary through the gate (facts, calendars, proposals) is still enforced in code; what a main agent chooses to say in the DM room itself is not (see §6's new gap).

### Commands any agent or gate can send to a gate (in `SKILL.md`)

```
@om-gate free 2026-11-08..2026-11-09                     → busy blocks (+ titles at friend and close)
@om-gate ask diet interests                              → values, or "<field>: not shared with you" (no hint whether it exists or its level; `view-as` shows the owner "not shared at this level")
@om-gate ask-owner Q3 "Is ₹1,500 per person okay?"       → asks the owner on their home surface (Discord via their own Hermes, for either side); reply comes back as `answer Q3 …`
@om-gate propose P1 2026-11-08T21:00 2h "Bowling + dinner" @ "Smaaash, Indiranagar"
@om-gate counter P1 P2 2026-11-09T19:00 2h "Bowling + dinner" @ "Smaaash, Indiranagar"
@om-gate gift-ideas birthday 2026-11-20 budget<=3000     → wishlist with 'taken' flags (close), interests (friend)
@om-gate claim "Catan Seafarers"                         → hidden from Om until after the 20th
@om-gate ask-around "tent to borrow, Nov 14-16"          → gate-to-gate only
```

Anything else gets the list of commands back, plus an **overreach note** to the owner, e.g. "Rahul's side asked for your address (private)". Dates are parsed generously, because LLMs won't format them perfectly.

### Commands only the owner can use (in their home room)

```
@om-gate dm rahul "something fun Sunday evening, not pricey"
@om-gate ask-around "anyone have a tent for Nov 14-16?"
@om-gate yes P1 | no P1
@om-gate answer Q3 "yes, up to ₹1,500"
@om-gate trust priya close
@om-gate view-as rahul        → exactly what Rahul's side can learn, field by field
@om-gate ledger               → what you've shared, with whom, and when (sealed gift entries show as "1 sealed, opens Nov 21")
```

---

## 4. The three scenes, step by step

### Scene 1: two-person outing (P0)

1. **Om, dictating with Wispr into Discord, tells his Hermes:** "plan something fun with Rahul Sunday evening, not pricey."
2. **`om-hermes`** (Om's Hermes, acting in Switch through `tn mcp`) sends `@om-gate dm rahul "something fun Sunday evening, not pricey"`.
3. **`om-gate`:**
   - creates `dm-om-rahul-sun` (agent-only);
   - invites `om-hermes` to the room;
   - privately hands `om-hermes` a **share card**: what Rahul's trust level allows Om's side to say (Rule 7) — this is guidance for the agent, not a hard filter;
   - posts `@rahul-gate join-dm <room> "<goal>"` in `conn-om-rahul`.
4. **`rahul-gate`** (on the VM) joins, invites **`rahul-hermes`** (Rahul's own Hermes, a second profile on the same VM) to the room, and privately hands it its own share card (what Om's level allows). It drops a line into `rahul-home`, which `rahul-hermes` picks up via `inbox` and relays to Rahul on Discord: "Om's agent is planning Sunday with you."
5. **`om-hermes` and `rahul-hermes` talk directly in the DM room, in plain language, through `dm_read`/`dm_post`.** "Om's vegetarian and into bowling; free after 7." / "Rahul has cricket until 8:30; 9 pm works." Neither is confined to a brief — each already knows its own person's whole life, so what it actually says rests on `SKILL.md` and its own share card; neither side has a per-message human approval step (symmetric, see §6).
6. **When `rahul-hermes` needs something it isn't sure about, it asks Rahul directly on Discord:** "Is ₹1,500 per person okay?" Rahul answers his own Hermes right there, which relays the answer back into the DM room.
7. **An agent proposes a plan through the gates, unchanged:** `@om-gate propose P1 …` and `@rahul-gate propose P1 …`.
8. **Both people say yes, to their own Hermes, on Discord:**
   - Om tells his Hermes "yes"; `om-hermes` calls `answer(P1, yes)` over `tn mcp` (recorded "via Hermes") — or Om types `@om-gate yes P1` directly in `#om-home`;
   - Rahul tells his own Hermes "yes"; `rahul-hermes` calls `answer(P1, yes)` over `tn mcp` (recorded "via Hermes").
9. **Both gates post the confirmation.** `rahul-home` and Om's home surface show "✅ P1: Sat 21:00, Bowling + dinner @ Smaaash · Om ✅ via Hermes · Rahul ✅ via Hermes".
10. **Each Hermes adds the event:** both call the `cal_add` tool over `tn mcp` (symmetric now — neither side has a shell-capable managed agent). The DM room is archived, and both ledgers record what was shared.

### Scene 2: gift ideas that keep the surprise (P1)

1. **Rahul tells his own Hermes, on Discord:** "Om's birthday is the 20th. Gift ideas under ₹3k?"
2. **`rahul-hermes`** calls `gift_ideas(om, birthday, 2026-11-20, 3000)` over `tn mcp` (acting as `rahul-hermes`), which acts through `rahul-gate`.
3. **`rahul-gate`** creates `gift-rahul-om-bday` (agent-only, private) with `om-gate` and sends `@om-gate gift-ideas birthday 2026-11-20 budget<=3000`.
4. **`om-gate` answers from stored facts only. It never asks Om.** Rahul is close, so: `wishlist: Catan Seafarers (≈₹2,500), Hario V60 (≈₹2,000), Kindle Paperwhite (over budget) · interests: board games, sci-fi · sizes: tshirt M`.
5. **`rahul-hermes` suggests Catan Seafarers. Rahul:** "get that." `rahul-hermes` calls `claim(om, "Catan Seafarers")` over `tn mcp`.
6. **Om's view stays unchanged:**
   - his home surface (his own Hermes on Discord, or `#om-home`) shows nothing;
   - his own wishlist still shows Catan;
   - `@om-gate ledger` (or asking his Hermes) shows "1 sealed entry, opens Nov 21".
7. **Optional beat:** Priya's side then asks for gift ideas and sees "Catan Seafarers: taken".

*Being honest about the seal:* it's a courtesy seal. The ledger file is on Om's own laptop, like a wrapped present he could open early.

### Scene 3: ask around (P1)

1. **Om tells his own Hermes, on Discord:** "ask around if anyone can lend me a tent for Nov 14–16." `om-hermes` calls `ask_around("tent to borrow, Nov 14-16")` over `tn mcp`, reaching `om-gate`.
2. **`om-gate`** posts the question in each connection room (`conn-om-rahul`, `conn-om-priya`).
3. **`priya-gate`** returns her visible `has` and `recommends` facts immediately, including the friend-level 2-person tent. This is provisional information, not consent to lend.
4. **Each receiving gate whose person has a registered main agent asks its person** through their home inbox for a relevant answer. Priya has only a gate, so her provisional profile answer needs no confirmation. `rahul-hermes` relays Rahul's `answer A<n> "no, sorry"` back through his gate. Responses are quoted and collected for five minutes.
5. **`om-hermes` reads Om's home summary**, which updates as facts and personal answers arrive. Om's Hermes judges relevance from raw quoted profile items and must not treat ownership as a promise to lend. Gates do not judge meaning. Both `has` and `recommends` use the same level filtering.

### Overreach and view-as (P1, about 1 h)

- **Rahul tells his own Hermes, on Discord:** "find out Om's home address." `rahul-hermes` calls `ask(om, address)` over `tn mcp` (acting as `rahul-hermes`), which `rahul-gate` sends to `om-gate` as `ask address` in `conn-om-rahul`.
- **`om-gate`** answers "not shared with you" (`rahul-hermes` relays this to Rahul on Discord), and posts to Om's home surface: "Rahul's side asked for your address (private)" (Om's own Hermes relays this on Discord; it also shows in `#om-home`).
- **Om runs `@om-gate view-as rahul`** (directly in `#om-home`, or by asking his own Hermes) and sees the exact table of what Rahul's side can learn.

---

## 5. Components we build (we write no AI agents)

| Component | What it is | Size |
|---|---|---|
| `switch_client.py` | Agent protocol client: register with a person's key, WebSocket events (`addressed`, sender), ops (`post_message`, `create_room`, `invite_agent_to_room`, `list_participants`, `get_agent_detail`, `archive_room`, `create_agent`, `update_agent_detail`, `list_machines`) | ~200 lines |
| `gate/` | Policy (levels, room level, consent, tighten-only), facts, `.ics` reader, command parser, relays, surprise mode, ledger, `view-as` | ~600 lines + tests |
| `gate/envoy.py` *(partly unused since Nov 5)* | Built in phase 13b for the dropped envoy design. Its envoy creation, brief handoff and registration parts are unused; its `ConversationWatch` (12 turns / 10 minutes, then a summary home and archive) is what `gate/dm.py` uses for DM rooms between main agents. | ~80 lines |
| `tn` CLI | `init`, `trust`, `fact set/get`, `cal add`, `view-as`, `--as <person>` for the demo | ~200 lines |
| `tn mcp` | MCP server (stdio) for personal agents, generic across who runs it. **Now runs twice in the demo** (`--as om`, acting as `om-hermes`; `--as rahul`, acting as `rahul-hermes`), one instance per Hermes profile: `inbox`, `dm`, `dm_read`, `dm_post`, `ask`, `gift_ideas`, `claim`, `ask_around`, `answer`, `cal_add`, `fact_set`. `dm_read`/`dm_post` (new, Nov 5) let a Hermes-style agent read and post plain-language text in a DM room it's already a member of, since the main agent now carries that conversation itself. | ~180 lines |
| `SKILL.md` | The manual for every agent, in Agent Skill format. Attached to rooms as a doc, and loaded by both Hermes profiles and (optionally) `om-agent`. **Dictated with Wispr.** | 1 page |
| `envoy-brief.md.j2` | *Repurposed (Nov 5):* the template for the **share card** each gate privately hands its own main agent at the start of a DM — the friend's name, the facts and busy blocks their trust level allows, and a reminder that this is guidance, not an enforced filter (Rule 7). Kept under its old filename; no code renamed. | ½ page |
| `templates/home.template.yaml` | Om's Discord home (optional/secondary only): private channel, a managed Codex main agent (`provider: codex`, no model override, `allow_existing`), `om-gate`, the `SKILL.md` doc. **No equivalent template is needed for either Hermes profile** — neither is a Switch-managed agent. | YAML |
| *(dropped, 2026-11-05)* a `rahul-home` equivalent | No longer needed: Rahul's main agent is his own Hermes process, registered directly via `tn mcp --as rahul` (not a Switch-managed agent placed by a template), so there's no agent-management placement left to build for him. `rahul-home` is a plain agent-only Switch room (`rahul-gate` + `rahul-hermes`), created the same way `conn-*`/`dm-*` rooms are. | — |
| `scripts/demo_up.py` | Registers gates from keys, writes example data, sets addressing, prints the remaining clicks (enroll the VM if used, run the home template for Om's optional `om-agent`) | ~100 lines |
| `scripts/vm_up.sh` | Sets up the Azure VM, now shared by both Hermes profiles: Node 22, `uv`, the controller (enroll with a one-time code, kept but unused), `rahul-gate` as a service, both Hermes's `tn mcp` entries (acting as `om-hermes` and `rahul-hermes`) and their two Discord bot configs | ~40 lines |
| `examples/{om,rahul,priya}/` | `trust.yaml`, `facts.yaml`, `calendar.ics` | fixtures |
| *(unused since Nov 5)* `envoy_runner.py` | Built in phase 13b for the dropped envoy design: registered an envoy under its person's key and ran their agent CLI headless, tools off (`opencode run -m opencode-go/deepseek-v4.1-flash` for Om, `codex exec` for Rahul). Nothing calls it now. | ~200 lines |

```
trust-network/
├── trustnet/
│   ├── switch_client.py
│   ├── envoy_runner.py        # unused since Nov 5 (built for the dropped envoy design)
│   ├── gate/  (policy.py, facts.py, calendar.py, commands.py, relay.py, surprise.py, ledger.py,
│   │           brief.py [repurposed: share card], runtime.py, view_as.py,
│   │           envoy.py [unused since Nov 5], __main__.py)
│   └── tn/    (cli.py, mcp.py)
├── skills/trust-network/SKILL.md
├── templates/ (home.template.yaml, envoy-brief.md.j2 [repurposed: share card])
├── examples/ (om/, rahul/, priya/)
├── scripts/ (demo_up.py, vm_up.sh)
├── tests/ (test_policy.py, test_commands.py, test_surprise.py, test_brief.py)
└── README.md
```

Stack: Python 3.12, `uv`, `websockets`, `httpx`, `icalendar` + `recurring-ical-events`, `dateparser`, `pyyaml`, the `mcp` SDK (FastMCP), `pytest`. Switch agent management with `switch-agent-controller` 0.31. Tailscale Serve.

---

## 6. Safety model (Switch's three-factor test)

An agent is unsafe when all three hold: it acts unwatched, can reach something that matters, and reads content nobody vetted. Each piece is missing at least one of them.

| Piece | Reads unvetted text | Reaches what matters | Unwatched | Why it's safe |
|---|---|---|---|---|
| **gate** | yes | yes (your facts) | yes | **No LLM.** It only matches a fixed set of commands, and its rules are tested in code. |
| **Hermes via `tn mcp` (`om-hermes`)** | yes (Om's Discord chats, and the DM room's plain-language text through `dm_read`) | **little**: eleven purpose-built tools, can only tighten facts, can only read/post in DM rooms it's already a member of | yes | The worst a tricked Hermes can do: say too much in a DM room, say yes to a plan Om allowed it to answer, or make a fact more private |
| **Hermes via `tn mcp` (`rahul-hermes`)** | yes (Rahul's Discord chats, and the DM room's plain-language text through `dm_read`) | **little**: the same eleven purpose-built tools, can only tighten facts, can only read/post in DM rooms it's already a member of | yes | Same limits as `om-hermes`, symmetric — the worst it can do: say too much in a DM room, say yes to a plan Rahul allowed it to answer, or make a fact more private |
| **`om-agent` (Codex, managed, optional)** | no: only `#om-home`, and only used for `view-as`/`ledger`/overreach/direct `yes` | yes | provider approvals | Secondary surface only; not party to any DM room in the demo |

**Stronger on the VM (P2):** `install-service --separate-users` would run each Hermes process as its own Linux user that can't read the gate's files, the other person's credentials, or the cloud metadata address.

**Known gaps (say these in the README):**
- **Both main agents now carry the DM-room conversation themselves, unfiltered, and symmetrically.** With no envoy in between, `om-hermes` and `rahul-hermes` each know their own person's whole life, so what either one actually says to the other rests on `SKILL.md` and its own share card. Neither side has a per-message human approval step — unlike the briefly-planned managed-Codex design for Rahul, which would have needed Console approval per message, Hermes on either side only has its eleven narrow tools. The gate's level guarantees still cover only what gates themselves disclose — facts, calendars, proposals — never what a main agent chooses to volunteer in the DM room.
- **The 140-character questions** an agent relays to its own owner through `ask-owner` reach the owner as text, which leaves a small injection channel. They're shown quoted, and `SKILL.md` tells main agents to pass them to the human without acting on them.
- **The gift seal is a courtesy,** because the ledger file is on the recipient's own laptop.
- **Whoever runs the Switch server** can read every room.
- **Every device on Om's tailnet** can reach the Switch server (it still needs a Switch credential).

---

## 7. Switch features used (README table)

| Switch feature | Where trust-network uses it |
|---|---|
| **Agent-only rooms** (`create_room(internal_only=True)`) | DM rooms between main agents, connection rooms, gift rooms, `rahul-home` |
| **Agent management**: `create_agent`, "can manage agents", managed agents placed on a named machine | `om-agent` (optional, managed Codex) is placed on the laptop via a template. Neither Hermes profile is a Switch-managed agent — each registers itself directly through `tn mcp`. `create_agent`-based envoy creation (phases 12/13/13b) and the briefly-planned managed-Codex `rahul-agent` are both unused. |
| **Headless agent controller** (`switch-agent-controller`) and the **Machines** page | The `rahul-vm` controller enrollment (phase 02/03) is kept but carries no live traffic now — no managed agent runs on Rahul's side |
| **Agent instructions** | None set at runtime for the main agents now; the level-filtered **share card** (repurposed phase 12 brief) is handed to each one privately instead |
| **Per-room sessions** | DM rooms are archived after agreement or a turn/time limit; the main agents themselves persist across conversations, unlike the old per-room envoy session |
| **Agent protocol** (register under a person's key, WebSocket events, ops) | Gates, `om-hermes`, `rahul-hermes` |
| **Discord connection**: one bot, each agent under its own name, private channels Switch creates | **Two separate Discord bots** (one per Hermes profile) are the critical-path channel now; Switch's own Discord connection and `#om-home` remain Om's optional secondary surface |
| **Templates** with `provider: "{param}"`, `allow_existing`, `docs:` | Home channel setup for `om-agent` (optional secondary only); no template is needed for either Hermes profile |
| **Addressing**: `owner`, custom rules, visible refusals | Main agents answer only their owner; gates take owner commands only from their owner; `om-hermes` and `rahul-hermes` address each other directly once invited to a DM room |
| **Membership as server truth** (`list_participants`, `get_agent_detail`) | Room level |
| **Agents inherit their owner's permissions** | Why each gate and main agent belongs to its own person, on its own person's machine |
| **Private rooms** (`read_visibility`) | Gift rooms |
| **Room documents** | `SKILL.md` in rooms; the `plan` record in DM rooms |
| **Archive room** | DM and gift rooms when done |
| **Switch Console** | Reading the DM room transcript between `om-hermes` and `rahul-hermes` (a video shot); optionally Om's `om-agent` |
| **Multiple providers** | Hermes for both Om and Rahul (two profiles, two Discord bots); optionally managed Codex for `om-agent` as a secondary surface — no separate envoy provider |
| *(Fallback)* **Bundled Mattermost** | Judges can run it without a Discord bot |

---

## 8. Day-0 checks (tonight, Nov 5): each one decides a design choice

In dependency order. Write down each result.

| # | Check | If it fails |
|---|---|---|
| 1 | **Test users and keys:** Switch users `rahul` and `priya`, and a registration key for each (Gateway → API Keys, signed in as each) | n/a (blocking) |
| 2 | **Tailscale:** on the laptop, `tailscale serve --bg <switch-core port>` (port from `docker ps`). From the VM, a request to `https://<laptop>.<tailnet>.ts.net/v1/…` reaches switch-core, WebSockets included. | Rahul's controller runs on the laptop with its own `--data-dir`, over `localhost` (the judges' layout) |
| 3 | **Rahul's machine:** Gateway shows **Machines** (agent management on). Signed in as Rahul, create a one-time code; on the VM, `install.sh --server https://<laptop>.<tailnet>.ts.net --code <code>`; `codex login` on the VM; `switch-agent-controller doctor` passes | As in check 2, or the fallback envoy runner |
| 4 | **Envoys as managed agents:** with "can manage agents" on, `rahul-gate` calls `create_agent(machine=<VM>, provider="codex", instructions=…)`, the envoy answers in an agent-only room, and `update_agent_detail` then changes its instructions. Same for `om-gate` with OpenCode (`model="opencode-go/deepseek-v4.1-flash"`) on the laptop; the Console controller must report OpenCode sign-in `ok` (on Nov 5 it reported "could not verify"). | Fallback envoy runner (headless CLIs) |
| 5 | **Envoys can reach each other, and nobody else can read the brief:** `rahul-envoy-om` can address `om-envoy-rahul` once its addressing names it (set by the gate, or once by Om in Gateway as part of adding a friend). `get_agent_detail` from `rahul-gate` on `om-envoy-rahul` doesn't show its instructions. A new DM room starts a fresh session. | Owner sets the addressing rule by hand per friend. If instructions are readable, the brief still holds only what the other side may see (rule 7), so say so in the README. |
| 6 | **Tools off:** an OpenCode envoy (`opencode-go/deepseek-v4.1-flash`) with file and shell tools (Bash, Edit, Write) disallowed still replies in the room. Codex with `auto_mode` off doesn't act without asking. | Loosen to read-only tools in an empty folder |
| 7 | `create_room(internal_only=True)` from `om-gate` including `rahul-gate`, or creating it and then calling `invite_agent_to_room` | Leave rooms readable across the workspace and let gates `connect_to_room` themselves. Gift rooms then fall back to the courtesy seal only. |
| 8 | Events carry the sender's ID and `addressed`; `list_participants` and `get_agent_detail` give each agent's owner | Read `users` from `get_room_detail` |
| 9 | A gate's addressing set to `anyone` with `update_agent_detail`, while owner commands are enforced in code | Custom rules in Gateway |
| 10 | Om can open an agent-only DM room in Console (wanted), but can't open a private gift room created by `rahul-gate` (wanted) | Show the DM through a summary doc; gifts use the courtesy seal |
| 11 | Hermes on the VM, for **both Om and Rahul** (two profiles, decided Nov 5): each a Discord bot; `tn mcp` under `mcp_servers` for each; the skill loads; a cron job every 2 min calls `inbox` and messages Discord | `tn --as om inbox` / `tn --as rahul inbox` / `answer` from the terminal for either side (same code path) |
| 12 | Discord: **two bots, one per Hermes profile** (`om-hermes`, `rahul-hermes`), each with Message Content intent, each invited to (or DM-able by) its own person — this is now the critical path. Switch's own Discord connection, with `#om-home` created as a private channel by the template, is optional (Om's secondary surface only). | Mattermost for the optional secondary surface; `tn --as <person>` CLI stands in for either Hermes on the critical path |

**Checks 4–6 no longer drive the design.** They tested managed/fallback envoys, cross-envoy addressing and tool denial; after dropping envoys (Nov 5), none of that governs how `om-hermes` and `rahul-hermes` talk to each other. Their evidence stays below for the record, and still matters if envoys are ever reintroduced.

Protocol findings from phase 03 (source at `sandbox-quantum/switch@1c9725a`) are in `phases/03-switch-client.md` *Log* and §11; phase 04 confirms them against core 0.31.0. In short: participants carry no owner ID (use `get_agent_detail`); `internal_only` removes only the external bridge; archiving doesn't block writes; room-scoped ops use the connected room.

---

Day-0 outcome (2026-11-05, core 0.31.0): select fallback phase 13b. Managed
creation succeeds, but OpenCode tool-denial configuration is rejected and
managed OpenCode replies/rebriefing were not established. Internal cross-owner
rooms work; admin can read private gift rooms, so gifts use courtesy seals.
Gate self-addressing updates are forbidden; both gates were configured through
the owner Gateway API. Events carry transport mxids and null sender_kind;
resolve server identities before authorizing commands. See docs/day0.md.

## 9. Schedule (solo; Claude Code does most of the typing, prompts dictated with Wispr)

| When | Work | Done when |
|---|---|---|
| **Nov 5 evening** | Setup: Docker, Switch Console (local server), Discord bot + guild, test users and keys, Tailscale Serve, the VM's controller, `codex login` on the VM. Run checks 1–12. Start `switch_client.py`. | Each check has a result written down; a protocol agent posts in `#om-home`; the Machines page shows the laptop and the VM |
| **Nov 6 morning** | Gate core: policy, facts, calendar, `free`/`ask`, room level, ledger, `view-as`, tests. `home.template.yaml`. Example data. | Om's Codex agent asks `@om-gate free …` in Discord and gets a level-correct answer |
| **Nov 6 afternoon** | DM rooms between main agents (gate creates the room, invites both main agents and both gates, posts the share card privately), `dm`, `ask-owner`/`answer`, `propose`/`yes`, `tn cal add`. `rahul-gate` on the VM. Both Om and Rahul driven from the CLI (`tn --as om`, `tn --as rahul`), standing in for Hermes until phases 17–18. | **Scene 1 runs end to end** without Hermes |
| **Nov 6 night** | `tn mcp`, both Hermes profiles + Discord + cron on the VM (acting as `om-hermes` and `rahul-hermes`), `SKILL.md` | Scene 1 with both Om and Rahul on Discord |
| **Nov 7 morning** | Gift rooms + surprise mode + claims; ask-around; overreach note | Scenes 2 and 3 run |
| **Nov 7 afternoon** | README (Switch features table, room and machine maps, safety model, one-machine setup), fresh-clone test, record the video, Wispr Insights screenshot | Submitted by 20:00 IST |

**Cut lines.**
- **P0 (must ship):**
  - gate core, consent, ledger, `view-as`;
  - `#om-home` on Discord;
  - DM rooms between main agents, with ask-your-person and consent;
  - Scene 1 with Om through Hermes, or through the CLI if Hermes slips.
- **P1:**
  - Rahul's Hermes profile on the Azure VM (otherwise it runs from the laptop; nothing else changes);
  - Hermes on Discord for either side, if it slipped from P0 (fallback: `tn --as <person>` CLI);
  - Scene 2 (gifts);
  - Scene 3 (ask around);
  - the overreach note.
- **P2:**
  - counter-proposals;
  - Priya's own main agent (OpenCode);
  - OpenClaw and Grok Bot recipes;
  - Mattermost instructions.

---

## 10. Demo video (3 minutes)

| Time | Beat | On screen |
|---|---|---|
| 0:00 | **Hook.** Everyone has an agent now; they can't work together without oversharing. Instinct's answer is one vendor whose agent enforces its own rules. Ours: bring any agent, and the rules live in code. | Title, one line on Instinct |
| 0:15 | **Cast.** Om on his own Hermes, in Discord — the agent that DMs Rahul's Hermes directly. Rahul on his own Hermes, a second Discord bot/account, also acting in Switch. Priya's gate. Trust: Rahul close, Priya friend. One VM hosts both people's Hermes. | Discord (two bots/accounts) + Console + `trust.yaml` + Gateway Machines page |
| 0:30 | **Outing.** Om dictates to his Hermes on Discord. The two Hermes DM each other directly, visible in Switch Console. Rahul's Hermes asks him about budget right there on Discord, P1 is proposed, Om tells his Hermes "yes", Rahul tells his Hermes "yes". Then "Om ✅ via Hermes · Rahul ✅ via Hermes", and both calendars update. | Split: Discord / Console |
| 1:35 | **Gift.** Rahul tells his own Hermes to ask for ideas, gets the wishlist, claims Catan. Om's side stays silent; `ledger` shows "1 sealed entry, opens Nov 21". | Console, then Discord |
| 2:05 | **Ask around.** Om asks his Hermes "anyone have a tent?" on Discord. Priya's gate answers instantly; Rahul's Hermes asks him on Discord and he says no. | Discord + Console |
| 2:25 | **Overreach.** Rahul tells his Hermes to find out Om's address, gets "not shared", and an alert reaches Om via his own Hermes on Discord. `view-as rahul`. | Discord + Console |
| 2:45 | **Close.** Room map, three-factor table, "we wrote zero AI agents", Switch features. | Slides |

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| Tailscale or the laptop drops mid-demo | `caffeinate`; the controller reconnects by itself; scenes are recorded separately; the one-machine layout as backup (check 2) |
| Cross-owner invites to agent-only rooms are refused | Rooms readable across the workspace + `connect_to_room`; gifts fall back to the courtesy seal (check 7) |
| A main agent overshares beyond the friend's trust level | `SKILL.md` tells each Hermes to keep to what its share card says is allowed; neither side has a per-message human approval step (symmetric gap, see §6); nothing is committed without both people's yes |
| Hermes setup is now on the critical path **for both people**, not just Om; setup fails or is slow on either side | Fall back to driving either side from the CLI (`tn --as om` / `tn --as rahul`), the same code path Hermes's `tn mcp` calls use |
| Main agents chat forever | The gate counts turns and archives the DM room at 12 turns or 10 minutes, with a summary |
| `archive_room` doesn't block writes (upstream archive is reversible metadata; found in phase 03) | Gates track archived rooms themselves and ignore or refuse anything posted there after archiving |
| `internal_only` only removes the external bridge (Discord/Mattermost); it doesn't hide the room from Console users (found in phase 03) | Check 10 decides whether gift rooms need the courtesy seal. Never rely on `internal_only` alone for privacy. |
| Room-scoped ops (`post_message` etc.) act on the agent's connected room and take no `room_id` (found in phase 03) | Phase 04 confirms how a gate that sits in several rooms picks the room (e.g. `connect_to_room` before posting); phases 11 and 14 are built around the answer |
| Hermes setup varies by version, for either profile | `tn --as om` / `tn --as rahul` CLI fallback uses the same code path; Hermes moves to P1 for that side if needed |
| LLMs format commands badly | Generous date parsing; the gate replies with a correct example; `SKILL.md` has examples |
| Switch's `main` branch moves fast | Pin Console 0.40.1, switch-core 0.31.0, `switch-agent-controller` 0.31.0; controller 0.31.0 has no self-update switch, but only installs a release the server names, and Console's switch-core names none (`CONTROLLER_RELEASE_VERSION` unset) |
| A dense 3-minute video | Script dictated and timed on Nov 7 morning; cut ask-around first |
| Solo bandwidth | Cut lines above; P0 is Scene 1 only |
| Judges must reproduce it | `scripts/demo_up.py`, example data, the one-machine layout (no VM, no Tailscale), Mattermost fallback, no OAuth anywhere |

---

Day-0 risk update: auto_mode=False is provider approval behavior, not a tool
denylist. Use native provider restrictions in the fallback runner. Private room
visibility does not protect gifts against the workspace administrator.

## 12. Code with Wispr

- [ ] Dictate the Claude Code prompts, `SKILL.md`, the share-card template (`envoy-brief.md.j2`, repurposed), the README and the video script.
- [ ] Screenshot the Wispr Flow **Insights** tab right before submitting, and attach it.

## Sources
- [Instinct Trusted Person network (ThursdAI)](https://thursdai.news/companies/instinct) · [eesel review](https://www.eesel.ai/blog/instinct-ai-review) · [BestHub analysis](https://www.besthub.dev/articles/personal-agents-war-big-tech-sells-capabilities-instinct-builds-trust-68644b971336) · [TechCrunch Series C](https://techcrunch.com/2026/09/28/viral-ai-agent-instinct-raises-1b-series-c-at-a-10b-valuation)
- Switch: [Identity and access](https://docs.switchagents.ai/switch-rooms/internals/identity-and-access) · [Shared responsibility](https://docs.switchagents.ai/switch-rooms/resources/shared-responsibility) · [Agent protocol](https://docs.switchagents.ai/switch-rooms/internals/agent-protocol) · [Connect Discord](https://docs.switchagents.ai/switch-rooms/deploy/messaging-apps/discord) · [Messaging apps](https://docs.switchagents.ai/switch-rooms/deploy/messaging-apps/index) · [Add a server](https://docs.switchagents.ai/switch-rooms/getting-started/add-a-server) · [What keeps your agent running](https://docs.switchagents.ai/switch-rooms/getting-started/what-keeps-your-agent-running) · [Templates](https://github.com/sandbox-quantum/switch/blob/main/docs/TEMPLATES.md) · [`create_room` source](https://github.com/sandbox-quantum/switch/blob/main/core/switch_core/bridges/agent/operations/definitions.py)
- Switch agent management: [controller README](https://github.com/sandbox-quantum/switch/blob/main/console/packages/agent-controller/README.md) · [design: agent controllers v1](https://github.com/sandbox-quantum/switch/blob/main/docs/design/agent-controllers-v1.md) (`create_agent`, "can manage agents", definitions) · [CHANGELOG](https://github.com/sandbox-quantum/switch/blob/main/CHANGELOG.md) (0.30: `create_agent`; 0.31: templates create managed agents)
- Tailscale: [Serve](https://tailscale.com/kb/1312/serve) · [HTTPS certificates](https://tailscale.com/kb/1153/enabling-https)
- Hermes: [cron](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron) · [MCP setup](https://arcade.dev/blog/connect-hermes-agent-mcp-arcade/)

Phase 11 runtime note: core 0.31.0 requires a local read-only server identity
export (clients/agents/users/client_rooms) because agent operations omit the
transport mapping and Gateway members. Remote deployment needs an authenticated
server adapter; unknown identities and unlinked external users remain silent.
