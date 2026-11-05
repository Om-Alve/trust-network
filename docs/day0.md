# Day-0 checks

Every check in PLAN.md §8 is recorded here with its result, because each result
picks a design branch. A check is `pending` until someone runs it and writes the
date and evidence. Use `pass`, `fail` or `partial` in **Result**.

Rules for this file:

- Never paste a key, token or enrollment code. Record *where* the secret lives
  (`.env`, Switch, Discord) and its variable name.
- Evidence is a command output, a screenshot path, or a room/agent/machine name.
- If a check fails, the prefilled **Decision taken** line is the fallback from
  PLAN.md §8. Keep it, and add what was actually done.

## Who fills in what

| Check | Filled in by | Kind |
|---|---|---|
| 1, 2, 3 | phase 02 | human, laptop + VM |
| 12a (bot, intents, invite, Switch connection, Om linked) | phase 02 | human |
| 12b (`#om-home` created by the template) | phase 11 | human |
| 4–10 | phase 04 | agent + human |
| 11 | phase 18 | human + agent |

Check 8 has an event half (sender ID and `addressed`) that phase 03 can observe
while building `switch_client.py`; phase 04 records the result.

## Infrastructure facts

Fill these in first. They are referenced by almost every later phase.

| Item | Value | How it was found |
|---|---|---|
| switch-core host port | `53330` (binds `127.0.0.1`) | Console 0.40.1 runs switch-core **natively, not in Docker**: `~/Library/Application Support/switchdash/local-switch-server/ports.json` (`api`), process `switch-core/0.31.0/venv/bin/python -m switch_core.main`; `curl http://127.0.0.1:53330/health` → `{"status":"ok"}` (2026-11-05) |
| Gateway host port | `53329` | `ports.json` (`gateway`); also mattermost `53331`, postgres `53332`. `docker ps` shows no Switch containers. Note: `switch-core.env` sets `GATEWAY_PUBLIC_URL`/`FRONTEND_BASE_URL` to `http://localhost:53330`, so links Gateway generates may point at localhost |
| `SWITCH_URL` | `https://<your-mac>.<tailnet>.ts.net:8443` | `tailscale serve --bg --https=8443 http://127.0.0.1:53330` (port 443 was already serving another local app, so switch-core is on 8443). Tailnet only, no Funnel. From the laptop, `curl $SWITCH_URL/health` → `{"status":"ok"}` [200] (2026-11-05). In `.env`. |
| HTTP probe path | `____` | Switch agent-protocol docs; PLAN.md only writes `/v1/…` |
| WebSocket path | `____` | same |
| Laptop machine name (Switch) | `____` | Gateway → Machines |
| VM machine name (Switch) | `____` | Gateway → Machines |
| Switch Console | `0.40.1` | confirmed: app `CFBundleShortVersionString` |
| switch-core | `0.31.0` | confirmed: install path `native/switch-core/0.31.0` |
| `switch-agent-controller` | `0.31.0` | pinned by PLAN.md §11; check with `switch-agent-controller --version` |

---

## Check 1 — Test users and keys

- **Check:** Switch users `rahul` and `priya`, and a registration key for each
  (Gateway → API Keys, signed in as each)
- **Filled in by:** phase 02
- **Result:** `pass`
- **Date:** 2026-11-05
- **Evidence:** `uv run python scripts/switch_users.py --console-env` signed in as the
  local admin (`Admin <admin@switch.local>`, which is Om's Console account), created
  `rahul@switch.local` and `priya@switch.local` through `POST /gateway/users`, then signed in
  as each of Om, Rahul and Priya and created one registration key labelled
  `trust-network gate` (`POST /gateway/api-keys`). Keys are in `.env` as `OM_GATE_KEY`,
  `RAHUL_GATE_KEY` and `PRIYA_GATE_KEY`; Rahul's and Priya's sign-in passwords are in
  `.env` as `RAHUL_SWITCH_PASSWORD` / `PRIYA_SWITCH_PASSWORD`. The first set of keys was
  rotated after being echoed to a terminal by mistake; the old keys were deleted.
- **Decision taken:** No Console UI needed. Users are created through the Gateway API with
  the admin login Console starts switch-core with (`GATEWAY_ADMIN_EMAIL` /
  `GATEWAY_ADMIN_PASSWORD` in `switch-core.env`). Om = the local admin account.

Notes: Om's own key is needed too. Keys go into `.env` only
(`OM_GATE_KEY`, `RAHUL_GATE_KEY`, `PRIYA_GATE_KEY`); `RAHUL_HERMES_KEY` belongs
to phase 18. See [setup-laptop.md](setup-laptop.md) step 4.

---

## Check 2 — Tailscale Serve reaches switch-core, WebSockets included

- **Check:** **Tailscale:** on the laptop, `tailscale serve --bg <switch-core port>`
  (port from `docker ps`). From the VM, a request to
  `https://<laptop>.<tailnet>.ts.net/v1/…` reaches switch-core, WebSockets included.
- **Filled in by:** phase 02
- **Result:** `pending`
- **Date:** —
- **Evidence:** —
- **Decision taken:** If fail: Rahul's controller runs on the laptop with its own
  `--data-dir`, over `localhost` (the judges' layout)

Notes: Serve, never Funnel. A `401` or `403` from `/v1/…` still proves
reachability; a `404` usually means the probe path is wrong, not the network.
Use `scripts/ws_probe.py` from the VM. See [setup-vm.md](setup-vm.md) step 4–5.

---

## Check 3 — Rahul's machine is enrolled

- **Check:** **Rahul's machine:** Gateway shows **Machines** (agent management on).
  Signed in as Rahul, create a one-time code; on the VM,
  `install.sh --server https://<laptop>.<tailnet>.ts.net --code <code>`;
  `codex login` on the VM; `switch-agent-controller doctor` passes
- **Filled in by:** phase 02
- **Result:** `pending`
- **Date:** —
- **Evidence:** —
- **Decision taken:** If fail: As in check 2, or the fallback envoy runner

Notes: `doctor` must pass as the same user that runs the controller.
Controller pinned to `0.31.0`. See [setup-vm.md](setup-vm.md) step 6.

---

## Check 4 — Envoys as managed agents

- **Check:** **Envoys as managed agents:** with "can manage agents" on,
  `rahul-gate` calls `create_agent(machine=<VM>, provider="codex", instructions=…)`,
  the envoy answers in an agent-only room, and `update_agent_detail` then changes
  its instructions. Same for `om-gate` with Claude Code on the laptop.
- **Filled in by:** phase 04
- **Result:** `pending`
- **Date:** —
- **Evidence:** —
- **Decision taken:** If fail: Fallback envoy runner (headless CLIs)

---

## Check 5 — Envoys reach each other, brief stays hidden

- **Check:** **Envoys can reach each other, and nobody else can read the brief:**
  `rahul-envoy-om` can address `om-envoy-rahul` once its addressing names it (set by
  the gate, or once by Om in Gateway as part of adding a friend).
  `get_agent_detail` from `rahul-gate` on `om-envoy-rahul` doesn't show its
  instructions. A new DM room starts a fresh session.
- **Filled in by:** phase 04
- **Result:** `pending`
- **Date:** —
- **Evidence:** —
- **Decision taken:** If fail: Owner sets the addressing rule by hand per friend.
  If instructions are readable, the brief still holds only what the other side may
  see (rule 7), so say so in the README.

---

## Check 6 — Tools off

- **Check:** **Tools off:** a Claude Code envoy with file and shell tools disallowed
  still replies in the room. Codex with `auto_mode` off doesn't act without asking.
- **Filled in by:** phase 04
- **Result:** `pending`
- **Date:** —
- **Evidence:** —
- **Decision taken:** If fail: Loosen to read-only tools in an empty folder

---

## Check 7 — Agent-only rooms

- **Check:** `create_room(internal_only=True)` from `om-gate` including
  `rahul-gate`, or creating it and then calling `invite_agent_to_room`
- **Filled in by:** phase 04
- **Result:** `pending`
- **Date:** —
- **Evidence:** —
- **Decision taken:** If fail: Leave rooms readable across the workspace and let
  gates `connect_to_room` themselves. Gift rooms then fall back to the courtesy
  seal only.

This decides the room strategy for phase 14 as well.

---

## Check 8 — Events, participants and owners

- **Check:** Events carry the sender's ID and `addressed`; `list_participants` and
  `get_agent_detail` give each agent's owner
- **Filled in by:** phase 04
- **Result:** `pending`
- **Date:** —
- **Evidence:** —
- **Decision taken:** If fail: Read `users` from `get_room_detail`

---

## Check 9 — Gate addressing set to `anyone`

- **Check:** A gate's addressing set to `anyone` with `update_agent_detail`, while
  owner commands are enforced in code
- **Filled in by:** phase 04
- **Result:** `pending`
- **Date:** —
- **Evidence:** —
- **Decision taken:** If fail: Custom rules in Gateway

---

## Check 10 — Console visibility

- **Check:** Om can open an agent-only DM room in Console (wanted), but can't open
  a private gift room created by `rahul-gate` (wanted)
- **Filled in by:** phase 04
- **Result:** `pending`
- **Date:** —
- **Evidence:** —
- **Decision taken:** If fail: Show the DM through a summary doc; gifts use the
  courtesy seal

---

## Check 11 — Hermes on the VM

- **Check:** Hermes on the VM: a Telegram bot; `tn mcp` under `mcp_servers`; the
  skill loads; a cron job every 2 min calls `inbox` and messages Telegram
- **Filled in by:** phase 18
- **Result:** `pending`
- **Date:** —
- **Evidence:** —
- **Decision taken:** If fail: `tn --as rahul inbox` / `answer` from the terminal
  (same code path)

---

## Check 12 — Discord

- **Check:** Discord: bot with Message Content + Server Members intents;
  `#om-home` created as a private channel by the template; Om's Discord linked
- **Filled in by:** phase 02 (12a) and phase 11 (12b)
- **Decision taken:** If fail: Mattermost

### 12a — Bot, intents, guild, Switch connection, Om linked

- **Result:** `pending`
- **Date:** —
- **Evidence:** —
- **Decision taken:** If fail: Mattermost

Notes: see [setup-laptop.md](setup-laptop.md) step 7. The bot token lives in
Switch's Discord connection, never in this repo.

### 12b — `#om-home` created by the template

- **Result:** `pending`
- **Date:** —
- **Evidence:** —
- **Decision taken:** If fail: Mattermost

Notes: phase 11 runs `templates/home.template.yaml`. Record the channel ID or a
screenshot path, and confirm it is private and lists Om, `om-agent` and `om-gate`.
