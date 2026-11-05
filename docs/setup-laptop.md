# Laptop setup (Om's machine)

Phase 02 runbook: turn the laptop into the Switch server, the Console host, and
the tailnet address the Azure VM uses.

Read this with [day0.md](day0.md) open beside it. Every result goes there; every
key goes into `.env` and nowhere else.

Commands come from PLAN.md §2, §8 and §11 where the step is marked **[PLAN]**.
Steps marked **[not in PLAN.md]** are standard tool or UI paths that PLAN.md does
not spell out. Where PLAN.md is silent about a flag or a page name, this runbook
says so instead of guessing.

Phase 02's checkboxes in `phases/02-infra-day0-checks.md` map to the steps below.

---

## 0. Checklist

- [ ] Docker running
- [ ] Switch Console **0.40.1**, local Switch server up, switch-core **0.31.0**
- [ ] switch-core host port written into `day0.md` (not the Gateway's)
- [ ] Users `rahul`, `priya`; registration keys for Om, Rahul, Priya in `.env`
- [ ] `tailscale serve --bg <switch-core port>`; `SWITCH_URL` in `.env`
- [ ] `caffeinate -dims` running
- [ ] Discord bot with both intents, invited; Switch connection configured; Om linked

---

## 1. Docker

**[PLAN]** PLAN.md §8 assumes Docker is running; it gives no start command.

```sh
docker info >/dev/null && echo "docker: ok"
```

If that fails, start Docker Desktop (macOS):

```sh
open -a Docker        # [not in PLAN.md]
```

Wait for the whale icon to settle, then repeat `docker info`. Do not continue
while the daemon is down: Console cannot start switch-core without it.

---

## 2. Switch Console 0.40.1 and switch-core 0.31.0

**[PLAN]** §11 pins the versions: Console `0.40.1`, switch-core `0.31.0`,
controller `0.31.0`. PLAN.md gives **no download URL and no install command** for
Console. Get the installer from Switch's getting-started page (PLAN.md §Sources:
"Add a server"), install `0.40.1`, and only then move on.

Start the local Switch server from Console (the "local server" / "add a server"
flow described in that same doc). Console runs switch-core in Docker.

Verify what is actually running:

```sh
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'
```

- The switch-core container's image tag must read `0.31.0`.
- If `docker ps` truncates the image, ask Docker directly:

```sh
docker inspect --format '{{.Config.Image}}' <container>
```

If the tag is not `0.31.0`, stop. Updating or downgrading Console is a Console UI
step that PLAN.md does not name; use the version picker in Console's server
settings or reinstall the pinned Console. A mismatch invalidates every later
check, because phases 04–13 assume the pinned protocol.

Check that Console itself is `0.40.1` in its about/version screen (PLAN.md does
not name the screen). Record both versions in `day0.md` if they differ.

---

## 3. Find the switch-core port

**[PLAN]** "Serve the switch-core port, not the Gateway's" (§2). Console picks
the ports, so read them off Docker.

```sh
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'
```

Two published ports matter:

- the **Gateway** (Switch's web UI / admin side);
- **switch-core**, which serves `/v1/...` and the agent WebSocket.

PLAN.md does not give the container names, so identify them by image
(`switch-core` vs the Gateway image). When in doubt, the port that answers on
`/v1/...` is switch-core; the other one serves the UI.

The host side of the mapping is what you need:

```text
0.0.0.0:54321->8000/tcp
        ^^^^^ host port to serve
```

Confirm it listens:

```sh
nc -z 127.0.0.1 <switch-core-port> && echo "listening"
lsof -nP -iTCP:<switch-core-port> -sTCP:LISTEN   # [not in PLAN.md]
```

Record it in the Infrastructure facts table in `day0.md`. Keep it in a shell
variable for the next steps:

```sh
PORT=<switch-core-port>
```

---

## 4. Users and registration keys

**[PLAN]** §8 check 1: users `rahul` and `priya` exist, each with a registration
key created in **Gateway → API Keys, signed in as each**. Om needs his own key too.

PLAN.md does **not** name the page where users are created. In Gateway, find the
user administration page (the account/user list — not API Keys) and create
`rahul` and `priya`. Note the page you used in `day0.md` the first time, so the
next person does not have to hunt.

Then, for each of Om, Rahul and Priya:

1. Sign in to Gateway as that user (use a private window or separate browser
   profile so sessions do not mix — **[not in PLAN.md]**, but the check requires
   being signed in *as each*).
2. Gateway → API Keys → create a key. Copy it once; most gateways show it only at
   creation.
3. Put it in `.env` under `OM_GATE_KEY`, `RAHUL_GATE_KEY`, `PRIYA_GATE_KEY`.
   Leave `RAHUL_HERMES_KEY` empty: that key belongs to phase 18.

Create `.env` from the example if it does not exist, then lock it down:

```sh
cp -n .env.example .env
chmod 600 .env
```

Fill `.env` (values shown as placeholders, never commit real ones):

```dotenv
SWITCH_URL=https://<laptop>.<tailnet>.ts.net
OM_GATE_KEY=<om key>
RAHUL_GATE_KEY=<rahul key>
PRIYA_GATE_KEY=<priya key>
RAHUL_HERMES_KEY=
TN_DATA_DIR=
```

Verify it is ignored before you type a single key:

```sh
git check-ignore -v .env        # must print .env
git status --short              # must not list .env
```

Do not paste key values into `day0.md`, chat, screenshots or shell history.

---

## 5. Tailscale Serve

**[PLAN]** §8 check 2 and §2: `tailscale serve --bg <switch-core port>`. Serve,
never Funnel: it must be reachable only from the tailnet.

```sh
tailscale status
tailscale serve --bg "$PORT"
tailscale serve status
```

`--bg` keeps the proxy running after the shell exits. `serve status` must show the
switch-core port mapped to the tailnet name over HTTPS.

Refuse to use Funnel:

```sh
tailscale funnel status       # must not list switch-core
```

Record the tailnet DNS name. PLAN.md does not give a command for this; this reads
it from `tailscale status`:

```sh
tailscale status --json \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))'
```

HTTPS certificates must be enabled for the tailnet (PLAN.md §2 says they already
are). If the name resolves but TLS fails, that setting is the first thing to check
(Tailscale's "HTTPS certificates" doc is in PLAN.md §Sources).

Put the address in `.env`, no trailing slash:

```dotenv
SWITCH_URL=https://<laptop>.<tailnet>.ts.net
```

Smoke-test from the laptop:

```sh
curl -sS -o /dev/null -w '%{http_code}\n' "$SWITCH_URL/v1/<path>"
```

PLAN.md writes the path as `/v1/…` and never names an endpoint. Take the real
path from Switch's agent-protocol doc (PLAN.md §Sources) and use the same value
for `--path` on the VM, where `scripts/ws_probe.py` does the full check.

A `200`, `401` or `403` means Serve is working. `502` means Serve cannot reach the
port (wrong port, or switch-core stopped). `404` usually means the path is wrong.

---

## 6. Keep the laptop awake

**[PLAN]** §2 and §8:

```sh
caffeinate -dims
```

Leave it in its own terminal during work sessions and the demo (`-d` display,
`-i` idle, `-m` disk, `-s` AC power). `Ctrl-C` ends it. The controller reconnects
by itself if the link drops (PLAN.md §2), but a sleeping laptop still breaks the
demo.

---

## 7. Discord bot

**[PLAN]** §8 check 12: bot with **Message Content** and **Server Members**
intents, invited to the guild; Switch's Discord connection configured; Om's
Discord account linked. The `#om-home` channel itself is phase 11's template.

PLAN.md does not name most of the UI here. The steps below mark what is missing.

1. **Create the app.** [not in PLAN.md] Discord Developer Portal →
   <https://discord.com/developers/applications> → **New Application**. Name it
   something recognisable in the demo.
2. **Intents.** [PLAN] Bot → **Privileged Gateway Intents** → enable
   **Message Content Intent** and **Server Members Intent**. Both are required;
   the bot silently misses messages without the first.
3. **Invite it.** [PLAN] "invited to the guild". PLAN.md does not list scopes or
   permissions. Use OAuth2 → URL Generator with the `bot` scope, and the minimum
   permissions that let it read and send messages and create private channels
   (phase 11's template creates a private `#om-home`). Open the generated URL and
   pick the demo guild. If you do not have a guild yet, create one — PLAN.md does
   not say which guild.
4. **Configure Switch's Discord connection.** [PLAN] "Switch's Discord connection
   configured"; PLAN.md does **not** name the page. In Console or Gateway, open
   the messaging-apps / connections settings (PLAN.md §Sources: "Connect
   Discord") and paste the bot token from the Developer Portal's Bot page.
   The token goes into Switch, never into `.env` or the repo.
5. **Link Om.** [PLAN] "Om's Discord account linked"; the exact path is not in
   PLAN.md. It is the account-linking step in the same Discord connection
   settings — link Om's own Discord account, not the bot's. Rahul and Priya do
   not need Discord in the demo (Rahul is on Telegram, Priya is facts-only).
6. **Record 12a** in `day0.md`: intents on, bot in the guild, connection
   configured, Om linked. Leave 12b pending until phase 11 runs the template.

Secrets: the bot token and client secret are credentials. Do not paste them into
a terminal you share or into shell history, and never commit them.

---

## 8. Hand-off to the VM

Give the VM only these three values:

- `SWITCH_URL` (the tailnet address);
- the switch-core port (for troubleshooting);
- the `/v1/...` HTTP path and WebSocket path you used above.

Then follow [setup-vm.md](setup-vm.md) from the VM.

---

## What this runbook does not cover

- Switch Console updates and license/account setup beyond installing `0.40.1`.
- The Gateway's agent-management toggle ("can manage agents"), which phase 04
  turns on for `om-gate` and `rahul-gate`.
- `#om-home` and `templates/home.template.yaml` (phase 11).
- `scripts/demo_up.py` (phase 22), which automates the repeatable parts of this.

## Gate identity publisher

The exporter uses Console's application `DB_USER` and `DB_PASSWORD`, in a
read-only transaction. On Switch 0.31.0 this role can SELECT the required
columns in users, clients, agents and client_rooms. No owner credentials are
used. If a future installation restricts this role, provision a dedicated
login with a separately generated password. Set TN_IDENTITY_DB_USER and
TN_IDENTITY_DB_PASSWORD in the publisher environment for that role.
The minimum grants are:

```sql
CREATE ROLE trustnet_identity LOGIN;
GRANT CONNECT ON DATABASE switch TO trustnet_identity;
GRANT USAGE ON SCHEMA public TO trustnet_identity;
GRANT SELECT (id,email) ON users TO trustnet_identity;
GRANT SELECT (id,matrix_user_id,user_id,type) ON clients TO trustnet_identity;
GRANT SELECT (id,name,owner_id,client_id) ON agents TO trustnet_identity;
GRANT SELECT (room_id,client_id) ON client_rooms TO trustnet_identity;
ALTER ROLE trustnet_identity SET default_transaction_read_only = on;
```

Set its password interactively with psql's `\password trustnet_identity`.
The database name must match the installation. Keep credentials on the laptop.

For this deployment, LaunchAgent `net.trust-network.identities` runs
`.venv/bin/python -m scripts.identity_serve` in this checkout. Its mode-0600
plist contains only the publisher bearer token, copied from gitignored `.env`
(`TN_IDENTITY_TOKEN`). The server binds 127.0.0.1:8792.
`tailscale serve --bg --https=8666 http://127.0.0.1:8792` adds a tailnet-only
mapping; never use Funnel. Existing ports 443, 8443 and 8554 stay intact.
GET /identities requires the bearer token and regenerates the non-secret map.
No request headers are logged. Only the three explicit demo emails map to people.

The exporter sets transaction-local app.tenant_id to Switch's tenant-zero UUID.
Set TN_SWITCH_TENANT in the publisher environment for another tenant. The
application role enforces row-level security; a column-only LIMIT 0 query does
not exercise that policy.
