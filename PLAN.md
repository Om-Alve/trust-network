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
| Who talks across people | **Envoys**: OpenCode with OpenCode Go DeepSeek V4.1 Flash for Om and Codex for Rahul, launched by the trust-network runner (phase 13b). One envoy per friend. Its **instructions are the brief**, rewritten before each conversation, holding only what the trust level allows. File and shell tools are off. Each DM room gets a fresh session. Main agents never meet other people's agents. |
| Who holds private data | Each person's **gate**: our code, no LLM, running on the person's own machine |
| Machines | **Om's side on the laptop**: Switch server (Docker, run by Console), Console, `om-gate`, `priya-gate`. **Rahul's side on the Azure VM**: `rahul-gate`, Hermes, and Switch's headless `switch-agent-controller` running his envoy. Joined by **Tailscale**: `tailscale serve` gives the laptop's Switch server an https address only tailnet devices can reach. |
| Custom envoy runner | **Selected by Day-0**. Phase 13b runs both envoys with native tool denial and isolated state; macOS Seatbelt adds read confinement. Linux requires a separate OS user/container. |
| Planner agent | None. Your envoy plans with their envoy. |
| Tally / group secrets | Dropped. When an agent lacks a fact, it **asks its person**. |
| Trust levels | **close / friend / acquaintance**, per person, in each owner's own list. Mutual: each side sets its own level. |
| Preferences | Facts on your profile (vegetarian, no alcohol, interests, wishlist …), each tagged with the lowest level that may see it |
| Demo cast | **Om:** Codex, managed in Discord `#om-home`. **Rahul:** Hermes on Telegram. **Priya:** a gate with facts only. Envoys: Om → OpenCode (OpenCode Go DeepSeek V4.1 Flash), via the trust-network runner, Rahul → Codex. No Claude Code anywhere in Switch. |
| Scenes | (1) two-person outing, (2) gift ideas that keep the surprise, (3) ask around, plus an overreach alert and `view-as` |
| Gift privacy | Nothing reaches the person receiving the gift until after the occasion. Claimed items are hidden from them but shown to other askers. |
| Consent | Om types `yes P1` in Discord. Rahul says yes to Hermes, recorded as "via Hermes". |
| Calendars | Fake `.ics` fixtures in the repo. Main agents write accepted plans into them through `tn cal add`. |
| Name | `trust-network` |
| Om's agent (changed Nov 5) | **Codex** is Om's managed main agent in `#om-home`, with no model override, on `Om’s MacBook Pro`. His envoy stays OpenCode with OpenCode Go DeepSeek V4.1 Flash (`opencode-go/deepseek-v4.1-flash`) via the trust-network runner (phase 13b). Console 0.40.1's controller cannot start OpenCode 2.x: it waits for `opencode server listening`, while OpenCode prints `server listening`. |

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

| Person | Runs on | Main agent (knows their life) | Where they talk to it | Envoy (talks to other people's envoys) | Gate | Trust list |
|---|---|---|---|---|---|---|
| **Om** | laptop | Codex (managed, Switch Console) | Discord `#om-home` | `om-envoy-rahul`: OpenCode (`opencode-go/deepseek-v4.1-flash`), via the trust-network runner on the laptop | `om-gate` | Rahul: close, Priya: friend |
| **Rahul** | Azure VM | Hermes (Telegram), joined through `tn mcp` as `rahul-hermes` | Telegram | `rahul-envoy-om`: Codex via the phase 13b runner, laptop until phase 16 confinement is available | `rahul-gate` | Om: close |
| **Priya** | laptop | none in the demo (optional: OpenCode) | — | — | `priya-gate` | Om: friend |

Rahul and Priya are separate Switch users with their own registration keys. Rahul's machine is enrolled under his own account (Gateway → Machines), so his envoy is his, on his machine, and nothing of his runs under Om's account. **Rahul's side doesn't need Switch Console:** the VM runs Switch's headless agent controller.

### Machines and network

```
 LAPTOP (Om)                                               AZURE VM (Rahul), on the same tailnet
 ───────────                                               ─────────────────────────────────────
 Switch server (Docker, run by Console)  ◀──── https ────  switch-agent-controller (Rahul's machine)
   published on the tailnet by                               └─ rahul-envoy-om (Codex)
   `tailscale serve` as                                    rahul-gate (Python) ─ examples/rahul/
   https://<laptop>.<tailnet>.ts.net                       Hermes + `tn mcp` ──── Telegram
 Switch Console (Om) + its controller
   └─ om-envoy-rahul (OpenCode)
 om-gate, priya-gate (Python)
```

- **Why Tailscale Serve:** the controller only accepts an `https` server address, except for `localhost`. Serve gives a real certificate on the tailnet name (the tailnet already has HTTPS certificates on). It's tailnet-only: Serve, never Funnel.
- **Serve the switch-core port, not the Gateway's.** The controller calls `/v1/...` on switch-core. Console picks the ports, so find them with `docker ps`.
- **Everything on the VM goes through the same address:** the controller, `rahul-gate` and `tn mcp`.
- **The laptop stays awake** during the demo (`caffeinate -dims`). The controller reconnects by itself if the link drops.
- **Judges can run everything on one machine:** a second controller with its own `--data-dir`, over `localhost`, with no Tailscale. The README documents this layout.

### Rooms

| Room | Kind | Members | Purpose |
|---|---|---|---|
| `#om-home` | Discord private channel | Om, Om's Codex agent, `om-gate` | Om's requests, summaries, consent (`yes P1`), `view-as`, `ledger` |
| `rahul-home`, `priya-home` | Agent-only | the person's gate, plus `rahul-hermes` | Relays to Hermes (through `inbox`) and consent via Hermes |
| `conn-om-rahul`, `conn-om-priya` | Agent-only, one per pair | the two gates | The connection itself: ask-around traffic, and setting up conversations |
| `dm-om-rahul-<slug>` | Agent-only, one per conversation | both envoys + both gates | Envoys plan in plain language; gates answer questions and carry proposals. A new room means a fresh envoy session. Archived afterwards. |
| `gift-<asker>-<for>-<slug>` | Agent-only, created by the asker's gate, private | the asker's gate + the recipient's gate | Gift questions. Nothing is relayed to the recipient, and the log entry is sealed until the date. |

### Room map

```
 DISCORD (people)                    SWITCH, agent-only rooms (agents)                       TELEGRAM
 ─────────────────                   ──────────────────────────────────────                 ─────────
 #om-home                            dm-om-rahul-sat
   Om ⇄ Om's Codex agent               om-envoy-rahul (OpenCode) ⇄ rahul-envoy-om (Codex)
   om-gate posts summaries,            om-gate ⇄ rahul-gate (answers, ask-your-person, P1)
   proposals; Om says yes                         │                    │
                                     conn-om-rahul (om-gate ⇄ rahul-gate)                    Rahul ⇄ Hermes
                                     conn-om-priya (om-gate ⇄ priya-gate)                      │ tn mcp
                                     gift-rahul-om-bday (rahul-gate → om-gate, sealed)         ▼
                                     rahul-home (rahul-gate ⇄ rahul-hermes) ◀── inbox / answer
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
  default: direct            # Om says yes himself in #om-home
envoy:
  provider: opencode         # which agent speaks for Om
  model: opencode-go/deepseek-v4.1-flash   # optional; the provider's default if absent
  machine: <laptop machine name in Switch>
```

```yaml
# examples/rahul/trust.yaml
people:
  om: close
consent:
  default: via-agent         # Rahul's answers may come through Hermes; others see "via Hermes"
envoy:
  provider: codex
  machine: <VM machine name in Switch>
```

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
7. **Envoys are briefed at the room level and nothing more.** The gate builds the brief from the same policy code that answers `ask`, so the envoy never knows more than the other side could ask for.

### Commands any agent or gate can send to a gate (in `SKILL.md`)

```
@om-gate free 2026-11-08..2026-11-09                     → busy blocks (+ titles at friend and close)
@om-gate ask diet interests                              → values, or "<field>: not shared with you" (no hint whether it exists or its level; `view-as` shows the owner "not shared at this level")
@om-gate ask-owner Q3 "Is ₹1,500 per person okay?"       → asks Om (Discord); reply comes back as `answer Q3 …`
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

1. **In `#om-home`**, Om (dictating with Wispr) says: "@om-agent plan something fun with Rahul Sunday evening, not pricey."
2. **Om's Codex agent** sends `@om-gate dm rahul "something fun Sunday evening, not pricey"`.
3. **`om-gate`:**
   - creates `dm-om-rahul-sat` (agent-only);
   - **briefs `om-envoy-rahul`**: writes the goal plus Om's facts and busy blocks *at Rahul's level* into the envoy's instructions (`update_agent_detail`; the very first time, it creates the envoy with `create_agent` on Om's laptop);
   - invites the envoy to the DM room, and asks `rahul-gate` to join through `conn-om-rahul`.
4. **`rahul-gate`** (on the VM) joins and does the same for **`rahul-envoy-om`** (Codex, on the VM), with Rahul's brief at Om's level. It drops a line into `rahul-home`. Hermes picks it up on its next `inbox` check and tells Rahul on Telegram: "Om's agent is planning Sunday with you."
5. **The envoys talk in plain language.** "Om's vegetarian and into bowling; free after 7." / "Rahul has cricket until 8:30; 9 pm works."
6. **When an envoy needs something that isn't in its brief,** it asks its own person. rahul-envoy-om sends `@rahul-gate ask-owner Q1 "Is ₹1,500 per person okay?"`, which reaches Rahul on Telegram through Hermes. Rahul says "yes", Hermes calls `answer`, and rahul-gate posts the answer in the DM room.
7. **An envoy proposes:** `@om-gate propose P1 …` and `@rahul-gate propose P1 …`.
8. **Both people say yes:**
   - `om-gate` posts P1 in `#om-home`, and Om types `@om-gate yes P1`;
   - `rahul-gate` puts P1 in Rahul's `inbox`, Rahul tells Hermes "sure", and Hermes calls `answer(P1, yes)`.
9. **Both gates post the confirmation.** `#om-home` shows "✅ P1: Sat 21:00, Bowling + dinner @ Smaaash · Om ✅ · Rahul ✅ via Hermes".
10. **Each main agent adds the event** with `tn cal add` (Hermes uses the MCP tool). The DM room is archived, and both ledgers record what was shared.

### Scene 2: gift ideas that keep the surprise (P1)

1. **Rahul tells Hermes on Telegram:** "Om's birthday is the 20th. Gift ideas under ₹3k?"
2. **Hermes** calls `gift_ideas(om, birthday, 2026-11-20, 3000)` on `tn mcp`.
3. **`rahul-gate`** creates `gift-rahul-om-bday` (agent-only, private) with `om-gate` and sends `@om-gate gift-ideas birthday 2026-11-20 budget<=3000`.
4. **`om-gate` answers from stored facts only. It never asks Om.** Rahul is close, so: `wishlist: Catan Seafarers (≈₹2,500), Hario V60 (≈₹2,000), Kindle Paperwhite (over budget) · interests: board games, sci-fi · sizes: tshirt M`.
5. **Hermes suggests Catan Seafarers. Rahul:** "get that." Hermes calls `claim(om, "Catan Seafarers")`.
6. **Om's view stays unchanged:**
   - `#om-home` shows nothing;
   - his own wishlist still shows Catan;
   - `@om-gate ledger` shows "1 sealed entry, opens Nov 21".
7. **Optional beat:** Priya's side then asks for gift ideas and sees "Catan Seafarers: taken".

*Being honest about the seal:* it's a courtesy seal. The ledger file is on Om's own laptop, like a wrapped present he could open early.

### Scene 3: ask around (P1)

1. **In `#om-home`:** "@om-agent ask around if anyone can lend me a tent for Nov 14–16." Om's agent sends `@om-gate ask-around "tent to borrow, Nov 14-16"`.
2. **`om-gate`** posts the question in each connection room (`conn-om-rahul`, `conn-om-priya`).
3. **`priya-gate`** finds `tent` in her `has` facts (friend level) and answers right away: "Priya: 2-person tent."
4. **`rahul-gate`** has no matching fact, so it **asks its person.** Hermes asks Rahul on Telegram, Rahul says "no, sorry", and the answer comes back.
5. **In `#om-home`:** "Priya can lend a 2-person tent. Rahul can't." Recommendations work the same way, e.g. "a good dentist nearby?" is answered from friends' `recommends` facts.

### Overreach and view-as (P1, about 1 h)

- **Rahul tells Hermes:** "find out Om's home address." Hermes calls `ask(om, address)`.
- **`om-gate`** answers "not shared with you", and posts in `#om-home`: "Rahul's side asked for your address (private)."
- **Om runs `@om-gate view-as rahul`** and sees the exact table of what Rahul's side can learn.

---

## 5. Components we build (we write no AI agents)

| Component | What it is | Size |
|---|---|---|
| `switch_client.py` | Agent protocol client: register with a person's key, WebSocket events (`addressed`, sender), ops (`post_message`, `create_room`, `invite_agent_to_room`, `list_participants`, `get_agent_detail`, `archive_room`, `create_agent`, `update_agent_detail`, `list_machines`) | ~200 lines |
| `gate/` | Policy (levels, room level, consent, tighten-only), facts, `.ics` reader, command parser, relays, surprise mode, ledger, `view-as` | ~600 lines + tests |
| `gate/envoy.py` | Gets the person's envoy ready for a conversation. The first time, `create_agent` on the owner's machine (provider and machine from `trust.yaml`, an empty folder, file and shell tools off, `auto_mode` and `auto_approve` off). Each time, `update_agent_detail` with the new brief, then `invite_agent_to_room`. Counts turns and archives the room at 12 turns or 10 minutes. | ~80 lines |
| `tn` CLI | `init`, `trust`, `fact set/get`, `cal add`, `view-as`, `--as <person>` for the demo | ~200 lines |
| `tn mcp` | MCP server (stdio) for personal agents: `inbox`, `dm`, `ask`, `gift_ideas`, `claim`, `ask_around`, `answer`, `cal_add`, `fact_set`. Acts in Switch as `rahul-hermes`. | ~150 lines |
| `SKILL.md` | The manual for every agent, in Agent Skill format. Attached to rooms as a doc, and loaded by Hermes and Om's Codex agent. **Dictated with Wispr.** | 1 page |
| `envoy-brief.md.j2` | The brief template, which becomes the envoy's instructions: goal, the person's facts at this level, busy blocks, "only state what's here; otherwise `ask-owner`; you can't commit; propose through the gate" | ½ page |
| `templates/home.template.yaml` | Om's Discord home: private channel, a managed Codex main agent (`provider: codex`, no model override, `allow_existing`), `om-gate`, the `SKILL.md` doc | YAML |
| `scripts/demo_up.py` | Registers gates from keys, writes example data, sets addressing, prints the remaining clicks (turn on "can manage agents" for each gate, enroll the VM) | ~100 lines |
| `scripts/vm_up.sh` | Sets up Rahul's side on a Linux box: Node 22, `codex`, `uv`, the controller (enroll with a one-time code), `rahul-gate` as a service, Hermes's `tn mcp` entry | ~40 lines |
| `examples/{om,rahul,priya}/` | `trust.yaml`, `facts.yaml`, `calendar.ics` | fixtures |
| *(Fallback)* `envoy_runner.py` | Only if checks 3–5 fail: registers an envoy under its person's key and runs their agent CLI headless in an empty folder with tools off (`opencode run -m opencode-go/deepseek-v4.1-flash` for Om, `codex exec` for Rahul) | ~200 lines |

```
trust-network/
├── trustnet/
│   ├── switch_client.py
│   ├── gate/  (policy.py, facts.py, calendar.py, commands.py, relay.py, surprise.py, ledger.py, envoy.py, __main__.py)
│   └── tn/    (cli.py, mcp.py)
├── skills/trust-network/SKILL.md
├── templates/ (home.template.yaml, envoy-brief.md.j2)
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
| **envoy** | yes (the other envoy) | **no**: only a brief at this level, file and shell tools off, an empty folder, can't commit | yes | It can't leak what it was never told. Commitments need both people's yes. |
| **Om's Codex agent** | **no**: only `#om-home` | yes | provider approvals | Only Om can address it. What crosses into the home room is fixed forms and quoted questions of 140 characters or fewer. |
| **Hermes via `tn mcp`** | yes (your chats) | **little**: nine purpose-built tools, can only tighten facts | yes | The worst a tricked Hermes can do: say yes to a plan you allowed it to answer, or make a fact more private |

**Stronger on the VM (P2):** `install-service --separate-users` runs each envoy as its own Linux user that sees only its own folder, can't read the home directories or the gate's files, and can't reach the cloud metadata address. Codex has no per-tool switch in Switch's settings, so this is its real sandbox.

**Known gaps (say these in the README):**
- **The 140-character questions** that envoys ask their person reach the main agent as text, which leaves a small injection channel. They're shown quoted, and `SKILL.md` tells main agents to pass them to the human without acting on them.
- **The gift seal is a courtesy,** because the ledger file is on the recipient's own laptop.
- **Whoever runs the Switch server** can read every room.
- **Codex envoys** rely on `auto_mode` off and an empty folder until `--separate-users` is on.
- **Every device on Om's tailnet** can reach the Switch server (it still needs a Switch credential).

---

## 7. Switch features used (README table)

| Switch feature | Where trust-network uses it |
|---|---|
| **Agent-only rooms** (`create_room(internal_only=True)`) | Envoy DMs, connection rooms, gift rooms |
| **Agent management**: `create_agent`, "can manage agents", managed agents placed on a named machine | Gates create and re-brief their own person's envoys. No agent code of our own. |
| **Headless agent controller** (`switch-agent-controller`) and the **Machines** page | Rahul's envoy runs on his own machine, the Azure VM, without Switch Console |
| **Agent instructions** | The level-filtered brief |
| **Per-room sessions** | Each DM room is a fresh envoy session |
| **Agent protocol** (register under a person's key, WebSocket events, ops) | Gates, `rahul-hermes` |
| **Discord connection**: one bot, each agent under its own name, private channels Switch creates | `#om-home` |
| **Templates** with `provider: "{param}"`, `allow_existing`, `docs:` | Home channel setup |
| **Addressing**: `owner`, custom rules, visible refusals | Main agents answer only their owner; gates take owner commands only from their owner; each envoy answers only its gate and the friend's envoy |
| **Membership as server truth** (`list_participants`, `get_agent_detail`) | Room level |
| **Agents inherit their owner's permissions** | Why each gate and envoy belongs to its own person, on its own person's machine |
| **Private rooms** (`read_visibility`) | Gift rooms |
| **Room documents** | `SKILL.md` in rooms; the `plan` record in DM rooms |
| **Archive room** | DM and gift rooms when done |
| **Switch Console** | Om's main agent and Om's envoy; reading the envoys' DM transcript (a video shot) |
| **Multiple providers** | Managed Codex for Om in `#om-home`, OpenCode with OpenCode Go DeepSeek V4.1 Flash for his envoy via the trust-network runner, and Hermes for Rahul |
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
| 11 | Hermes on the VM: a Telegram bot; `tn mcp` under `mcp_servers`; the skill loads; a cron job every 2 min calls `inbox` and messages Telegram | `tn --as rahul inbox` / `answer` from the terminal (same code path) |
| 12 | Discord: bot with Message Content + Server Members intents; `#om-home` created as a private channel by the template; Om's Discord linked | Mattermost |

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
| **Nov 6 afternoon** | `gate/envoy.py` (create, brief, invite), `dm`, DM rooms, the brief template, `ask-owner`/`answer`, `propose`/`yes`, `tn cal add`. `rahul-gate` on the VM. Rahul driven from the CLI (`tn --as rahul`). | **Scene 1 runs end to end** without Hermes |
| **Nov 6 night** | `tn mcp`, Hermes + Telegram + cron on the VM, `SKILL.md` | Scene 1 with Rahul on Telegram |
| **Nov 7 morning** | Gift rooms + surprise mode + claims; ask-around; overreach note | Scenes 2 and 3 run |
| **Nov 7 afternoon** | README (Switch features table, room and machine maps, safety model, one-machine setup), fresh-clone test, record the video, Wispr Insights screenshot | Submitted by 20:00 IST |

**Cut lines.**
- **P0 (must ship):**
  - gate core, consent, ledger, `view-as`;
  - `#om-home` on Discord;
  - envoy DMs with ask-your-person, envoys as managed agents (or the fallback runner if checks 4–5 fail);
  - Scene 1 with Rahul through Hermes, or through the CLI if Hermes slips.
- **P1:**
  - Rahul's side on the Azure VM (otherwise his controller runs on the laptop; nothing else changes);
  - Hermes on Telegram, if it slipped from P0;
  - Scene 2 (gifts);
  - Scene 3 (ask around);
  - the overreach note.
- **P2:**
  - `--separate-users` on the VM;
  - an envoy template (`run_template` creates managed agents since 0.31);
  - counter-proposals;
  - Priya's own main agent (OpenCode);
  - OpenClaw and Grok Bot recipes;
  - Mattermost instructions.

---

## 10. Demo video (3 minutes)

| Time | Beat | On screen |
|---|---|---|
| 0:00 | **Hook.** Everyone has an agent now; they can't work together without oversharing. Instinct's answer is one vendor whose agent enforces its own rules. Ours: bring any agent, and the rules live in code. | Title, one line on Instinct |
| 0:15 | **Cast.** Om on managed Codex (Discord), his envoy on OpenCode with OpenCode Go DeepSeek V4.1 Flash via the trust-network runner, Rahul on Hermes (Telegram), Priya's gate. Trust: Rahul close, Priya friend. Two machines: Om's laptop, Rahul's VM. | Discord + phone + `trust.yaml` + Gateway Machines page |
| 0:30 | **Outing.** Om dictates the request. The envoys DM each other in Switch Console (OpenCode on the laptop ↔ Codex on the VM). Rahul's envoy asks him about budget on Telegram, P1 is proposed, Om types `yes`, Rahul says "sure". Then "Om ✅ · Rahul ✅ via Hermes", and both calendars update. | Split: Discord / Console / phone |
| 1:35 | **Gift.** Rahul asks Hermes for ideas, gets the wishlist, claims Catan. Om's Discord is silent; `ledger` shows "1 sealed entry, opens Nov 21". | Phone, then Discord |
| 2:05 | **Ask around.** "Anyone have a tent?" Priya's gate answers instantly; Rahul is asked on Telegram and says no. | Discord + phone |
| 2:25 | **Overreach.** Hermes asks for Om's address, gets "not shared", and an alert appears in `#om-home`. `view-as rahul`. | Discord |
| 2:45 | **Close.** Room map, three-factor table, "we wrote zero AI agents", Switch features. | Slides |

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| The managed-agent path fails (`create_agent`, re-briefing, envoys addressing each other) | The fallback envoy runner, headless CLIs (checks 4–5) |
| Tailscale or the laptop drops mid-demo | `caffeinate`; the controller reconnects by itself; scenes are recorded separately; the one-machine layout as backup (check 2) |
| Cross-owner invites to agent-only rooms are refused | Rooms readable across the workspace + `connect_to_room`; gifts fall back to the courtesy seal (check 7) |
| Envoys make up facts about their person | The brief says to state only what's in it and otherwise `ask-owner`. Proposals need both people's yes. |
| Managed OpenCode agents don't start: Console 0.40.1's controller waits for `opencode server listening`, OpenCode 2.x prints `server listening` (found in phase 04). Managed agents can only deny tools for the Claude provider. | Envoys use the fallback runner (phase 13b) with `opencode run` / `codex exec` and CLI-level tool denial. Report the OpenCode prefix mismatch upstream. |
| Envoys chat forever | The gate counts turns and archives the DM room at 12 turns or 10 minutes, with a summary |
| `archive_room` doesn't block writes (upstream archive is reversible metadata; found in phase 03) | Gates track archived rooms themselves and ignore or refuse anything posted there after archiving |
| `internal_only` only removes the external bridge (Discord/Mattermost); it doesn't hide the room from Console users (found in phase 03) | Check 10 decides whether gift rooms need the courtesy seal. Never rely on `internal_only` alone for privacy. |
| Room-scoped ops (`post_message` etc.) act on the agent's connected room and take no `room_id` (found in phase 03) | Phase 04 confirms how a gate that sits in several rooms picks the room (e.g. `connect_to_room` before posting); phases 11 and 14 are built around the answer |
| Hermes setup varies by version | `tn --as rahul` CLI fallback uses the same code path; Hermes moves to P1 if needed |
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

- [ ] Dictate the Claude Code prompts, `SKILL.md`, the envoy brief template, the README and the video script.
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
