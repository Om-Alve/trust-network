# trust-network: build plan

*Flip the Switch hackathon. Track 02 (Best Personal or Creative Workflow) + Code with Wispr. Solo build. Submissions close **Nov 7, 23:59 IST**; target submit **Nov 7, 20:00 IST**. Supersedes `PLAN-v1.md`, `PLAN-v2.md` and `PLAN-v3.md`. Pit Crew is dropped.*

> **One line:** Bring any agent, whether Claude Code, Codex, OpenCode or a personal agent like Hermes on Telegram. Your agent can plan things with your friends' agents, ask them for gift ideas, or ask around for a tent. Each friend's side learns only what your trust level for them allows, and nothing is committed until both people say yes.

---

## 0. Decisions so far

| Question | Decision |
|---|---|
| Scope | trust-network only. Pit Crew dropped. |
| Where people talk | **Discord**, through Switch's Discord connection. Bundled Mattermost is the setup-free fallback for judges. |
| Where agents talk to each other | **Agent-only Switch rooms** (`create_room(internal_only=True)`), shown in Switch Console. A short summary goes to the Discord home channel. |
| Who talks across people | **Each person's own main agent, directly**, in a DM room per conversation (`dm-om-rahul-<slug>`, agent-only). Om's main agent is **Hermes** on Telegram, acting in Switch through `tn mcp` as `om-hermes`. Rahul's main agent is **`rahul-agent`**: a Switch-managed **Codex** agent on Rahul's own machine (`rahul-vm`), with `auto_mode` and `auto_approve` off, so every tool use needs Rahul's approval in Console. No envoy sits between them (dropped Nov 5, see below). |
| **No envoys (decided Nov 5)** | Main agents talk to each other directly in agent-only DM rooms. Gates are unchanged: they still compute room-level access from Switch membership, record every disclosure, and carry proposals and consent. Reason: simpler, one hop fewer — Om's call. |
| **Main agents swapped (decided Nov 5, with the no-envoy change)** | Om now talks through **Hermes** on Telegram (Hermes already runs on the Azure VM, host `hermes`, user `om`); Rahul now talks through a Switch-managed **Codex** agent (`rahul-agent`) on his own machine. `om-agent` (the managed Codex agent from phase 11, in Discord `#om-home`) stays as an optional secondary surface for Om — `view-as`, `ledger`, overreach notes, or typing `yes P1` directly — but no longer the one conversing with Rahul's side. |
| Who holds private data | Each person's **gate**: our code, no LLM, running on the person's own machine |
| Machines | **Om's side on the laptop**: Switch server (Docker, run by Console), Console, `om-gate`, `priya-gate`, and (optional, secondary) `om-agent`. **The Azure VM hosts both Om's and Rahul's software** (a demo shortcut): Om's Hermes + `tn mcp` (as `om-hermes`), and Rahul's `rahul-gate` plus his managed `rahul-agent` (via the `switch-agent-controller` enrollment `rahul-vm`, required again now that it runs Rahul's main agent). Joined by **Tailscale**: `tailscale serve` gives the laptop's Switch server an https address only tailnet devices can reach. |
| Custom envoy runner | **Unused after Nov 5.** Phase 13b built it (native tool denial, isolated state; macOS Seatbelt adds read confinement, Linux needs a separate OS user/container); the code stays in the repo but nothing calls it now that main agents talk directly. |
| Planner agent | None. Your main agent plans directly with your friend's main agent. |
| Tally / group secrets | Dropped. When an agent lacks a fact, it **asks its person**. |
| Trust levels | **close / friend / acquaintance**, per person, in each owner's own list. Mutual: each side sets its own level. |
| Preferences | Facts on your profile (vegetarian, no alcohol, interests, wishlist …), each tagged with the lowest level that may see it |
| Demo cast | **Om:** Hermes on Telegram, talking directly to Rahul's agent in DM rooms through `tn mcp` as `om-hermes`; `om-agent` (Codex, managed, Discord `#om-home`) stays as an optional secondary surface. **Rahul:** `rahul-agent`, a managed Codex agent on his own machine, talked to in `rahul-home`. **Priya:** a gate with facts only. No Claude Code anywhere in Switch. |
| Scenes | (1) two-person outing, (2) gift ideas that keep the surprise, (3) ask around, plus an overreach alert and `view-as` |
| Gift privacy | Nothing reaches the person receiving the gift until after the occasion. Claimed items are hidden from them but shown to other askers. |
| Consent | Om tells Hermes "yes", recorded as "via Hermes" (or types `@om-gate yes P1` directly in `#om-home`). Rahul says yes directly in `rahul-home`, recorded "Rahul ✅". |
| Calendars | Fake `.ics` fixtures in the repo. Main agents write accepted plans into them through `tn cal add`. |
| Name | `trust-network` |
| Om’s agent (changed Nov 5, then superseded) | **Codex** (`om-agent`) was briefly Om’s managed main agent in `#om-home`. With the Nov 5 main-agent swap, Om’s main agent is **Hermes**; `om-agent` stays in `#om-home` as an optional secondary surface only (`view-as`, `ledger`, overreach notes, direct `yes P1`). Console 0.40.1’s controller cannot start OpenCode 2.x (it waits for `opencode server listening`, while OpenCode prints `server listening`); moot, since OpenCode was only ever used for the dropped envoy. |

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
| **Om** | Azure VM (Hermes), laptop (`om-gate`, optional `om-agent`) | Hermes, acting in Switch through `tn mcp` as `om-hermes` | Telegram (primary); Discord `#om-home` via `om-agent` (optional, secondary: `view-as`, `ledger`, overreach, direct `yes`) | `om-gate` | Rahul: close, Priya: friend |
| **Rahul** | Azure VM | `rahul-agent`: Codex (managed, via the `rahul-vm` controller), `auto_mode`/`auto_approve` off — every tool use needs Rahul's approval in Console | `rahul-home` (agent-only Switch room; a Discord channel is optional) | `rahul-gate` | Om: close |
| **Priya** | laptop | none in the demo (optional: OpenCode) | — | `priya-gate` | Om: friend |

Rahul and Priya are separate Switch users with their own registration keys. Rahul's machine is enrolled under his own account (Gateway → Machines), so nothing of his runs under Om's account. **The Azure VM now hosts software for both people** (a demo shortcut, called out so it isn't mistaken for a security boundary): Om's Hermes acts as `om-hermes` under Om's own Switch key, and Rahul's `rahul-agent` runs under the `rahul-vm` controller enrolled to Rahul's account — the two are isolated by Switch identity, not by machine. The one-machine judges' layout still works the same way it always did.

### Machines and network

```
 LAPTOP (Om)                                               AZURE VM, on the same tailnet
 ───────────                                               (hosts BOTH Om's Hermes and Rahul's side)
 Switch server (Docker, run by Console)  ◀──── https ────  switch-agent-controller (Rahul's machine,
   published on the tailnet by                               rahul-vm) └─ rahul-agent (Codex, managed)
   `tailscale serve` as                                    rahul-gate (Python) ─ examples/rahul/
   https://<laptop>.<tailnet>.ts.net                       om-hermes (Hermes) + `tn mcp` ──── Telegram
 Switch Console (Om) + its controller,
   optional secondary `om-agent`
 om-gate, priya-gate (Python)
```

- **Why Tailscale Serve:** the controller only accepts an `https` server address, except for `localhost`. Serve gives a real certificate on the tailnet name (the tailnet already has HTTPS certificates on). It's tailnet-only: Serve, never Funnel.
- **Serve the switch-core port, not the Gateway's.** The controller calls `/v1/...` on switch-core. Console picks the ports, so find them with `docker ps`.
- **Everything on the VM goes through the same address:** the `rahul-vm` controller, `rahul-gate`, Hermes and `tn mcp`.
- **The laptop stays awake** during the demo (`caffeinate -dims`). The controller reconnects by itself if the link drops.
- **Judges can run everything on one machine:** a second controller with its own `--data-dir`, over `localhost`, with no Tailscale. The README documents this layout.

### Rooms

| Room | Kind | Members | Purpose |
|---|---|---|---|
| `#om-home` | Discord private channel | Om, `om-agent` (optional, secondary), `om-gate` | Om's `view-as`, `ledger`, overreach notes, and direct `yes P1`; also polled by Hermes (`inbox`) as Om's primary surface |
| `rahul-home` | Agent-only Switch room | Rahul, `rahul-agent`, `rahul-gate` | Rahul's requests, proposals, consent (`yes P1`) — Rahul's primary surface, talked to directly, not relayed |
| `priya-home` | Agent-only | `priya-gate` | Unused in the demo (Priya has no main agent) |
| `conn-om-rahul`, `conn-om-priya` | Agent-only, one per pair | the two gates | The connection itself: ask-around traffic, and setting up conversations |
| `dm-om-rahul-<slug>` | Agent-only, one per conversation | both main agents (`om-hermes`, `rahul-agent`) + both gates | The main agents plan in plain language; each gate privately hands its own agent a share card at the start, and carries proposals/consent. Archived after agreement, a turn limit or a time limit. |
| `gift-<asker>-<for>-<slug>` | Agent-only, created by the asker's gate, private | the asker's gate + the recipient's gate | Gift questions. Nothing is relayed to the recipient, and the log entry is sealed until the date. |

### Room map

```
 TELEGRAM                            SWITCH, agent-only rooms (agents)                       DISCORD (optional)
 ─────────                           ──────────────────────────────────────                 ──────────────────
 Om ⇄ Hermes                         dm-om-rahul-sat                                        #om-home
   │ tn mcp                            om-hermes (Hermes) ⇄ rahul-agent (Codex)                Om ⇄ om-agent
   ▼                                   om-gate ⇄ rahul-gate (answers, ask-your-person, P1)      (view-as, ledger,
 #om-home (polled via inbox) ◀──────             │                    │                         overreach, yes)
                                     conn-om-rahul (om-gate ⇄ rahul-gate)
                                     conn-om-priya (om-gate ⇄ priya-gate)
                                     gift-rahul-om-bday (rahul-gate → om-gate, sealed)
                                     rahul-home (rahul-gate ⇄ rahul-agent) ◀── Rahul talks directly
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
  default: via-agent         # Om's answers come through Hermes; others see "via Hermes" (swapped Nov 5)
```

```yaml
# examples/rahul/trust.yaml
people:
  om: close
consent:
  default: direct            # Rahul says yes himself in rahul-home (swapped Nov 5)
```

*The `envoy:` block that used to sit in both files above (`provider`, `model`, `machine`) configured the
now-dropped envoy runner (phase 13b; the code stays in the repo but is unused after the Nov 5 decision).
It is no longer read when deciding who talks for each person — that's each person's own main agent, from
§2. A new field will be needed instead for `rahul-agent`'s managed-agent placement (provider `codex`,
machine `rahul-vm`), analogous to how `om-agent` was placed by `templates/home.template.yaml`; see §5 and
the report at the end of this change for the exact fixture edit still needed.*

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
@om-gate ask-owner Q3 "Is ₹1,500 per person okay?"       → asks the owner on their home surface (Telegram via Hermes for Om, directly in `rahul-home` for Rahul); reply comes back as `answer Q3 …`
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

1. **Om, dictating with Wispr into Telegram, tells Hermes:** "plan something fun with Rahul Sunday evening, not pricey."
2. **Hermes** (acting in Switch as `om-hermes` through `tn mcp`) sends `@om-gate dm rahul "something fun Sunday evening, not pricey"`.
3. **`om-gate`:**
   - creates `dm-om-rahul-sat` (agent-only);
   - invites `om-hermes` to the room;
   - privately hands `om-hermes` a **share card**: what Rahul's trust level allows Om's side to say (Rule 7) — this is guidance for the agent, not a hard filter;
   - posts `@rahul-gate join-dm <room> "<goal>"` in `conn-om-rahul`.
4. **`rahul-gate`** (on the VM) joins, invites **`rahul-agent`** (the managed Codex agent on `rahul-vm`) to the room, and privately hands it its own share card (what Om's level allows). It drops a line into `rahul-home`: "Om's agent is planning Sunday with you."
5. **`om-hermes` and `rahul-agent` talk directly in the DM room, in plain language.** "Om's vegetarian and into bowling; free after 7." / "Rahul has cricket until 8:30; 9 pm works." Neither is confined to a brief — each already knows its own person's whole life, so what it actually says rests on `SKILL.md` plus, for `rahul-agent`, Rahul approving each tool use in Console.
6. **When `rahul-agent` needs something it isn't sure about, it asks Rahul directly in `rahul-home`:** "Is ₹1,500 per person okay?" Rahul answers right there.
7. **An agent proposes a plan through the gates, unchanged:** `@om-gate propose P1 …` and `@rahul-gate propose P1 …`.
8. **Both people say yes:**
   - Om tells Hermes "yes"; Hermes calls `answer(P1, yes)` over `tn mcp` (recorded "via Hermes") — or Om types `@om-gate yes P1` directly in `#om-home`;
   - Rahul says yes directly in `rahul-home`: `@rahul-gate yes P1` (recorded "Rahul ✅", direct — no agent in between).
9. **Both gates post the confirmation.** `rahul-home` and Om's home surface show "✅ P1: Sat 21:00, Bowling + dinner @ Smaaash · Om ✅ via Hermes · Rahul ✅".
10. **Each main agent adds the event:** Hermes calls `cal_add` over `tn mcp`; `rahul-agent` runs `tn cal add` (Console-approved). The DM room is archived, and both ledgers record what was shared.

### Scene 2: gift ideas that keep the surprise (P1)

1. **Rahul tells his Codex agent, in `rahul-home`:** "Om's birthday is the 20th. Gift ideas under ₹3k?"
2. **`rahul-agent`** runs `tn --as rahul gift-ideas om birthday 2026-11-20 3000` (Console-approved), which acts through `rahul-gate`.
3. **`rahul-gate`** creates `gift-rahul-om-bday` (agent-only, private) with `om-gate` and sends `@om-gate gift-ideas birthday 2026-11-20 budget<=3000`.
4. **`om-gate` answers from stored facts only. It never asks Om.** Rahul is close, so: `wishlist: Catan Seafarers (≈₹2,500), Hario V60 (≈₹2,000), Kindle Paperwhite (over budget) · interests: board games, sci-fi · sizes: tshirt M`.
5. **`rahul-agent` suggests Catan Seafarers. Rahul:** "get that." `rahul-agent` runs `tn --as rahul claim om "Catan Seafarers"`.
6. **Om's view stays unchanged:**
   - his home surface (Hermes/`#om-home`) shows nothing;
   - his own wishlist still shows Catan;
   - `@om-gate ledger` (or asking Hermes) shows "1 sealed entry, opens Nov 21".
7. **Optional beat:** Priya's side then asks for gift ideas and sees "Catan Seafarers: taken".

*Being honest about the seal:* it's a courtesy seal. The ledger file is on Om's own laptop, like a wrapped present he could open early.

### Scene 3: ask around (P1)

1. **Om tells Hermes on Telegram:** "ask around if anyone can lend me a tent for Nov 14–16." Hermes calls `ask_around("tent to borrow, Nov 14-16")` over `tn mcp`, reaching `om-gate`.
2. **`om-gate`** posts the question in each connection room (`conn-om-rahul`, `conn-om-priya`).
3. **`priya-gate`** finds `tent` in her `has` facts (friend level) and answers right away: "Priya: 2-person tent."
4. **`rahul-gate`** has no matching fact, so it **asks its person** by relaying to `rahul-home`. Rahul says "no, sorry" directly there, and the answer comes back.
5. **Hermes tells Om (on Telegram):** "Priya can lend a 2-person tent. Rahul can't." (Om can also check `#om-home` directly.) Recommendations work the same way, e.g. "a good dentist nearby?" is answered from friends' `recommends` facts.

### Overreach and view-as (P1, about 1 h)

- **Rahul tells his Codex agent:** "find out Om's home address." `rahul-agent` runs `tn --as rahul ask om address` (Console-approved), which `rahul-gate` sends to `om-gate` as `ask address` in `conn-om-rahul`.
- **`om-gate`** answers "not shared with you", and posts to Om's home surface: "Rahul's side asked for your address (private)" (Hermes relays this on Telegram; it also shows in `#om-home`).
- **Om runs `@om-gate view-as rahul`** (directly in `#om-home`, or by asking Hermes) and sees the exact table of what Rahul's side can learn.

---

## 5. Components we build (we write no AI agents)

| Component | What it is | Size |
|---|---|---|
| `switch_client.py` | Agent protocol client: register with a person's key, WebSocket events (`addressed`, sender), ops (`post_message`, `create_room`, `invite_agent_to_room`, `list_participants`, `get_agent_detail`, `archive_room`, `create_agent`, `update_agent_detail`, `list_machines`) | ~200 lines |
| `gate/` | Policy (levels, room level, consent, tighten-only), facts, `.ics` reader, command parser, relays, surprise mode, ledger, `view-as` | ~600 lines + tests |
| *(unused since Nov 5)* `gate/envoy.py` | Built in phase 13b for the dropped envoy design (gate-side registration, brief handoff, turn/time-limited lifecycle). Nothing calls it now that main agents talk directly; kept in the repo. | ~80 lines |
| `tn` CLI | `init`, `trust`, `fact set/get`, `cal add`, `view-as`, `--as <person>` for the demo | ~200 lines |
| `tn mcp` | MCP server (stdio) for personal agents, generic across who runs it (`--as om` in the demo, acting as `om-hermes`): `inbox`, `dm`, `dm_read`, `dm_post`, `ask`, `gift_ideas`, `claim`, `ask_around`, `answer`, `cal_add`, `fact_set`. `dm_read`/`dm_post` (new, Nov 5) let a Hermes-style agent read and post plain-language text in a DM room it's already a member of, since the main agent now carries that conversation itself. | ~180 lines |
| `SKILL.md` | The manual for every agent, in Agent Skill format. Attached to rooms as a doc, and loaded by Hermes and `rahul-agent`/`om-agent`. **Dictated with Wispr.** | 1 page |
| `envoy-brief.md.j2` | *Repurposed (Nov 5):* the template for the **share card** each gate privately hands its own main agent at the start of a DM — the friend's name, the facts and busy blocks their trust level allows, and a reminder that this is guidance, not an enforced filter (Rule 7). Kept under its old filename; no code renamed. | ½ page |
| `templates/home.template.yaml` | Om's Discord home (now optional/secondary): private channel, a managed Codex main agent (`provider: codex`, no model override, `allow_existing`), `om-gate`, the `SKILL.md` doc | YAML |
| *(needed, not yet built)* a `rahul-home` equivalent | An agent-only Switch room with a managed Codex agent (`rahul-agent`) on `rahul-vm` plus `rahul-gate`, parallel to `home.template.yaml` but for an agent-only room instead of a Discord channel. See the report at the end of this change — this is the main code gap the main-agent swap introduces, for phase 16 to close. | template or script |
| `scripts/demo_up.py` | Registers gates from keys, writes example data, sets addressing, prints the remaining clicks (enroll the VM, run the home template for Om, create `rahul-agent` as a managed agent in `rahul-home`) | ~100 lines |
| `scripts/vm_up.sh` | Sets up the Azure VM, now shared by Om's Hermes and Rahul's side: Node 22, `codex` (for the `rahul-vm` controller to run `rahul-agent`), `uv`, the controller (enroll with a one-time code), `rahul-gate` as a service, Hermes's `tn mcp` entry (acting as `om-hermes`) | ~40 lines |
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
| **`rahul-agent` (Codex, managed)** | **yes** — the DM room, directly, not filtered by an envoy brief | yes | provider approvals (`auto_mode`/`auto_approve` off) | Every tool use — posting in a DM room included — needs Rahul's approval in Console. Nothing it sends crosses unseen. |
| **Hermes via `tn mcp` (`om-hermes`)** | yes (Om's chats, and now the DM room's plain-language text through `dm_read`) | **little**: eleven purpose-built tools, can only tighten facts, can only read/post in DM rooms it's already a member of | yes | The worst a tricked Hermes can do: say too much in a DM room, say yes to a plan Om allowed it to answer, or make a fact more private |
| **`om-agent` (Codex, managed, optional)** | no: only `#om-home`, and only used for `view-as`/`ledger`/overreach/direct `yes` | yes | provider approvals | Secondary surface only; not party to any DM room in the demo |

**Stronger on the VM (P2):** `install-service --separate-users` would run Rahul's main agent as its own Linux user that can't read the gate's files or reach the cloud metadata address. Codex has no per-tool switch in Switch's settings, so this is its real sandbox.

**Known gaps (say these in the README):**
- **A main agent now carries the DM-room conversation itself, unfiltered.** With no envoy brief in between, `rahul-agent` and Hermes each know their own person's whole life, so what either one actually says to the other rests on `SKILL.md` plus, for `rahul-agent`, Rahul approving every message in Console; Hermes has no per-message human check, only its eleven narrow tools. The gate's level guarantees still cover only what gates themselves disclose — facts, calendars, proposals — never what a main agent chooses to volunteer in the DM room.
- **The 140-character questions** an agent relays to its own owner through `ask-owner` reach the owner as text, which leaves a small injection channel. They're shown quoted, and `SKILL.md` tells main agents to pass them to the human without acting on them.
- **The gift seal is a courtesy,** because the ledger file is on the recipient's own laptop.
- **Whoever runs the Switch server** can read every room.
- **Every device on Om's tailnet** can reach the Switch server (it still needs a Switch credential).

---

## 7. Switch features used (README table)

| Switch feature | Where trust-network uses it |
|---|---|
| **Agent-only rooms** (`create_room(internal_only=True)`) | DM rooms between main agents, connection rooms, gift rooms, `rahul-home` |
| **Agent management**: `create_agent`, "can manage agents", managed agents placed on a named machine | `rahul-agent` is a managed Codex agent placed on `rahul-vm`; `om-agent` likewise on the laptop (now optional). `create_agent`-based envoy creation (phases 12/13/13b) is unused after the no-envoy decision. |
| **Headless agent controller** (`switch-agent-controller`) and the **Machines** page | Runs `rahul-agent` on Rahul's own machine, the Azure VM, without Switch Console — now required again (it was optional between the no-envoy and main-agent-swap decisions) |
| **Agent instructions** | None set at runtime for the main agents now; the level-filtered **share card** (repurposed phase 12 brief) is handed to each one privately instead |
| **Per-room sessions** | DM rooms are archived after agreement or a turn/time limit; the main agents themselves persist across conversations, unlike the old per-room envoy session |
| **Agent protocol** (register under a person's key, WebSocket events, ops) | Gates, `om-hermes` |
| **Discord connection**: one bot, each agent under its own name, private channels Switch creates | `#om-home` (now Om's optional secondary surface) |
| **Templates** with `provider: "{param}"`, `allow_existing`, `docs:` | Home channel setup for `om-agent`; a parallel setup is still needed for `rahul-agent` in `rahul-home` (see §5) |
| **Addressing**: `owner`, custom rules, visible refusals | Main agents answer only their owner; gates take owner commands only from their owner; `rahul-agent` and `om-hermes` address each other directly once invited to a DM room |
| **Membership as server truth** (`list_participants`, `get_agent_detail`) | Room level |
| **Agents inherit their owner's permissions** | Why each gate and main agent belongs to its own person, on its own person's machine |
| **Private rooms** (`read_visibility`) | Gift rooms |
| **Room documents** | `SKILL.md` in rooms; the `plan` record in DM rooms |
| **Archive room** | DM and gift rooms when done |
| **Switch Console** | Rahul's main agent (`rahul-agent`); reading the DM room transcript between it and Hermes (a video shot) |
| **Multiple providers** | Managed Codex for Rahul (`rahul-agent`), Hermes for Om — no separate envoy provider |
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
| 11 | Hermes on the VM, now acting for **Om** (`om-hermes`, swapped Nov 5): a Telegram bot; `tn mcp` under `mcp_servers`; the skill loads; a cron job every 2 min calls `inbox` and messages Telegram | `tn --as om inbox` / `answer` from the terminal (same code path) |
| 12 | Discord: bot with Message Content + Server Members intents; `#om-home` created as a private channel by the template; Om's Discord linked | Mattermost |

**Checks 4–6 no longer drive the design.** They tested managed/fallback envoys, cross-envoy addressing and tool denial; after dropping envoys (Nov 5), none of that governs how `om-hermes` and `rahul-agent` talk to each other. Their evidence stays below for the record, and still matters if envoys are ever reintroduced.

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
| **Nov 6 afternoon** | DM rooms between main agents (gate creates the room, invites both main agents and both gates, posts the share card privately), `dm`, `ask-owner`/`answer`, `propose`/`yes`, `tn cal add`. `rahul-gate` and a managed `rahul-agent` on the VM. Om driven from the CLI (`tn --as om`), standing in for Hermes until phase 18. | **Scene 1 runs end to end** without Hermes |
| **Nov 6 night** | `tn mcp`, Hermes + Telegram + cron on the VM (acting as `om-hermes`), `SKILL.md` | Scene 1 with Om on Telegram |
| **Nov 7 morning** | Gift rooms + surprise mode + claims; ask-around; overreach note | Scenes 2 and 3 run |
| **Nov 7 afternoon** | README (Switch features table, room and machine maps, safety model, one-machine setup), fresh-clone test, record the video, Wispr Insights screenshot | Submitted by 20:00 IST |

**Cut lines.**
- **P0 (must ship):**
  - gate core, consent, ledger, `view-as`;
  - `#om-home` on Discord;
  - DM rooms between main agents, with ask-your-person and consent;
  - Scene 1 with Om through Hermes, or through the CLI if Hermes slips.
- **P1:**
  - Rahul's side on the Azure VM (otherwise his controller runs on the laptop; nothing else changes);
  - Hermes on Telegram, if it slipped from P0;
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
| 0:15 | **Cast.** Om on Hermes (Telegram) — the agent that DMs Rahul's agent directly. Rahul on a managed Codex agent (`rahul-agent`), talked to in Switch Console. Priya's gate. Trust: Rahul close, Priya friend. One VM hosts both Om's Hermes and Rahul's side. | Phone + Console + `trust.yaml` + Gateway Machines page |
| 0:30 | **Outing.** Om dictates to Hermes. Hermes and `rahul-agent` DM each other directly in Switch Console. `rahul-agent` asks Rahul about budget right there, P1 is proposed, Om tells Hermes "yes", Rahul says yes directly. Then "Om ✅ via Hermes · Rahul ✅", and both calendars update. | Split: phone / Console |
| 1:35 | **Gift.** Rahul tells his Codex agent to ask for ideas, gets the wishlist, claims Catan. Om's side stays silent; `ledger` shows "1 sealed entry, opens Nov 21". | Console, then phone |
| 2:05 | **Ask around.** Om asks Hermes "anyone have a tent?" Priya's gate answers instantly; Rahul is asked directly in `rahul-home` and says no. | Phone + Console |
| 2:25 | **Overreach.** Rahul's agent asks for Om's address, gets "not shared", and an alert reaches Om via Hermes. `view-as rahul`. | Phone + Console |
| 2:45 | **Close.** Room map, three-factor table, "we wrote zero AI agents", Switch features. | Slides |

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| Tailscale or the laptop drops mid-demo | `caffeinate`; the controller reconnects by itself; scenes are recorded separately; the one-machine layout as backup (check 2) |
| Cross-owner invites to agent-only rooms are refused | Rooms readable across the workspace + `connect_to_room`; gifts fall back to the courtesy seal (check 7) |
| A main agent overshares beyond the friend's trust level | `SKILL.md` tells each main agent to keep to what its share card says is allowed; `rahul-agent`'s messages need Rahul's approval in Console; nothing is committed without both people's yes |
| `rahul-agent`'s managed-Codex path fails on `rahul-vm` (`create_agent`, addressing, the room it needs set up in `rahul-home`) | Fall back to driving Rahul from the CLI (`tn --as rahul`), same as the original Hermes cut line |
| Main agents chat forever | The gate counts turns and archives the DM room at 12 turns or 10 minutes, with a summary |
| `archive_room` doesn't block writes (upstream archive is reversible metadata; found in phase 03) | Gates track archived rooms themselves and ignore or refuse anything posted there after archiving |
| `internal_only` only removes the external bridge (Discord/Mattermost); it doesn't hide the room from Console users (found in phase 03) | Check 10 decides whether gift rooms need the courtesy seal. Never rely on `internal_only` alone for privacy. |
| Room-scoped ops (`post_message` etc.) act on the agent's connected room and take no `room_id` (found in phase 03) | Phase 04 confirms how a gate that sits in several rooms picks the room (e.g. `connect_to_room` before posting); phases 11 and 14 are built around the answer |
| Hermes setup varies by version | `tn --as om` CLI fallback uses the same code path; Hermes moves to P1 if needed |
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
