# Azure VM deployment (phase 16)

Run from the laptop checkout:

```sh
scripts/vm_up.sh                         # defaults to om@hermes.<tailnet>.ts.net
scripts/vm_up.sh om@hermes.<tailnet>.ts.net
```

The script sends a filtered `git archive HEAD` snapshot over SSH because this
repository has no remote. Only committed source is deployed, so commit phase
15/17 changes before redeploying them. Om/Priya example directories are omitted.
This is a source snapshot, not a VM git checkout. It installs missing git/uv,
selects Python 3.12 and syncs the lockfile. SSH, sudo and Tailscale connectivity
must already work. Node, codex, controller and Hermes are optional and untouched.

Local `.env` must contain SWITCH_URL and RAHUL_GATE_KEY; retained registration
must exist in `data/day0-state.json`. Only those two env entries and Rahul's
registration are transferred, with non-secret server identity aliases. Temporary
local files and VM secrets use restrictive permissions; nothing prints keys.
No Hermes registration keys are transferred yet. Future phases must provision
those separately without replacing Om's existing Hermes configuration.

VM paths:

- Source and venv: `/home/om/trust-network`
- Environment: `/home/om/.config/trust-network/rahul.env` (0600)
- Retained registration: `data/rahul-state.json` (0600, Rahul only)
- Trusted aliases: `data/gate-identities.json` (0600)
- Mutable profile: `data/profiles/rahul/`, seeded once from examples/rahul
- User unit: `~/.config/systemd/user/rahul-gate.service`

Re-running syncs source and restarts the service but preserves existing profile
files and registration. It refuses known local gates/probes to prevent duplicate
Rahul consumers. Do not start old two-gate live probes concurrently.

```sh
ssh om@hermes.<tailnet>.ts.net 'systemctl --user status rahul-gate --no-pager'
ssh om@hermes.<tailnet>.ts.net 'systemctl --user restart rahul-gate; systemctl --user show rahul-gate -p ActiveState -p SubState -p NRestarts'
ssh om@hermes.<tailnet>.ts.net 'loginctl show-user om -p Linger'
ssh om@hermes.<tailnet>.ts.net 'cd ~/trust-network; ~/.local/bin/uv run tn --help'
ssh om@hermes.<tailnet>.ts.net 'journalctl --user -u rahul-gate -n 20 --no-pager'
```

Measured: enabled, active/running after restart, linger yes; second deployment
succeeds. **Command handling is blocked**: the gate entrypoint invokes the
laptop's macOS Switch Python to refresh identities. Ubuntu raises FileNotFoundError
on addressed commands despite an active transport connection. Phase 15 must add
a supported external identity map/refresh path; then redeploy and verify actual
free/ask replies. The local repeatable probe and redacted output are retained in
`data/phase16-probe.py` and `data/phase16-evidence.log`; run from the laptop with
`PYTHONPATH=. uv run python data/phase16-probe.py`. It creates an internal room,
sends a dated free query, records replies excluding join greetings, and deletes
the room in finally. See the phase 16 Log for IDs and outcome. Reboot, Tailscale
drop recovery and full Scene 1 are still unverified.

Switch stays on the laptop with Om/Priya gate ownership. Rahul's canonical gate
service is on the VM. Om's existing Hermes and optional controller remain as-is.
Phase 17 supplies tn mcp; phase 18 creates Rahul's Hermes profile/Discord bot and
wires both profiles to their own MCP identity, credentials, home inbox and consent.

The following is the historical phase 02 runbook; its controller/envoy requirements
are optional under the current design. The measured day0 checks supersede guessed
paths and installer flags below.

---

# VM setup (Rahul's machine, Azure)

> **As actually done on 2026-11-05 (supersedes the steps below where they differ):**
> SSH via Tailscale SSH (`ssh om@hermes.<tailnet>.ts.net`). Install with the tagged installer:
> `gh api 'repos/sandbox-quantum/switch/contents/console/packages/agent-controller/install.sh?ref=switch-agent-controller-v0.31.0' --jq .content | base64 -d > install.sh; sh install.sh --version 0.31.0`.
> Mint the code as Rahul with `POST /gateway/management/enrollment-codes` (Gateway API, signed in
> with `RAHUL_SWITCH_PASSWORD`), then `switch-agent-controller enroll --server $SWITCH_URL --code <code> --name rahul-vm`
> and `switch-agent-controller install-service`. `SWITCH_CONTROLLER_SELF_UPDATE` does not exist in
> 0.31.0 and is not needed (see `day0.md` check 3). switch-core has no `/v1/` prefix: probe with
> `ws_probe.py --path /health --ws-path /agents/probe/connection/ws`.


Phase 02 runbook: join the VM to Om's tailnet, prove it can reach the laptop's
switch-core over HTTPS and WebSockets (check 2), and enrol Rahul's
`switch-agent-controller` (check 3).

This machine runs only Switch's headless controller for now. `rahul-gate`,
Hermes and `tn mcp` are phases 16 and 18. There is **no Switch Console** here
(PLAN.md §2).

Commands come from PLAN.md where marked **[PLAN]**; standard install steps PLAN.md
does not spell out are marked **[not in PLAN.md]**. Where PLAN.md is silent about
a flag or a path, this runbook says so rather than guessing.

Record results in [day0.md](day0.md): check 2 (HTTP + WebSocket) and check 3
(enrolment, `codex login`, `doctor`).

---

## 0. Checklist

- [ ] VM joined to the same tailnet as the laptop
- [ ] `curl` to `https://<laptop>.<tailnet>.ts.net/v1/…` reaches switch-core
- [ ] WebSocket upgrade succeeds (`scripts/ws_probe.py`)
- [ ] Gateway → Machines shows the VM (check 3)
- [ ] `install.sh --server … --code <code>` succeeded
- [ ] `SWITCH_CONTROLLER_SELF_UPDATE=off` exported and persisted
- [ ] `codex login` done
- [ ] `switch-agent-controller doctor` passes
- [ ] controller pinned to `0.31.0`

---

## 1. Join the tailnet

**[PLAN]** §2: the VM is "on the same tailnet"; §8 check 3 assumes it can reach
the laptop's tailnet name. PLAN.md gives no Tailscale install command for the VM.

The standard Linux install (Tailscale's documented script, **[not in PLAN.md]**):

```sh
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

`tailscale up` prints a login URL. Sign in with the **same tailnet** as the
laptop. Then confirm both machines see each other:

```sh
tailscale status
tailscale ping <laptop-name>
```

`tailscale status` lists the laptop as `<laptop>.<tailnet>.ts.net`. That exact
name is the host in `SWITCH_URL`. If the laptop is missing, the VM is on the
wrong tailnet — stop and fix that before probing.

---

## 2. Prepare the probe

**[not in PLAN.md]** PLAN.md §8 says "e.g. `websocat` or a 5-line Python script
the agent writes in `scripts/ws_probe.py`", and this repo has the script.

The VM needs `python3` with `httpx` and `websockets`, and a copy of the script.
PLAN.md does not say the repo is cloned on the VM. Either is fine:

```sh
# copy the script from the laptop (run this on the laptop)
scp scripts/ws_probe.py <vm-user>@<vm-host>:~
```

```sh
# on the VM
python3 --version
python3 -m pip install --user httpx websockets    # or: uv run --with httpx --with websockets ...
```

If the repo is already cloned on the VM, run it from the repo root instead:
`uv run --with httpx --with websockets python scripts/ws_probe.py …`.

---

## 3. Reachability, HTTP half of check 2

**[PLAN]** §8 check 2: a request to `https://<laptop>.<tailnet>.ts.net/v1/…`
reaches switch-core.

```sh
export SWITCH_URL=https://<laptop>.<tailnet>.ts.net
curl -sS -o /dev/null -w '%{http_code}\n' "$SWITCH_URL/v1/<path>"
```

PLAN.md only writes `/v1/…` — it never names a concrete endpoint. Take the path
from Switch's agent-protocol doc (PLAN.md §Sources) and write it into
`docs/day0.md` under **Infrastructure facts** so later phases reuse it.

How to read the code:

| Code | Meaning |
|---|---|
| `200` | reachable, path correct |
| `401` / `403` | reachable, path exists, needs a credential — **this is a pass for check 2** |
| `404` | TLS and Serve work; the path is probably wrong |
| `502` | Serve works but cannot reach switch-core: wrong port, or switch-core is down on the laptop |
| connection refused / TLS error | tailnet, Serve or the certificate is broken — see step 7 |

---

## 4. Reachability, WebSocket half of check 2

**[PLAN]** §8 check 2: "WebSockets included". `scripts/ws_probe.py` does the GET
and the WebSocket upgrade and exits non-zero if either fails.

```sh
python3 ws_probe.py \
  --base-url "$SWITCH_URL" \
  --path /v1/<http-path> \
  --ws-path /v1/<ws-path>
```

- `--base-url` falls back to `SWITCH_URL` if omitted.
- `--path` defaults to `/v1/health` and `--ws-path` to `/v1/ws`. **Both defaults
  are guesses**: PLAN.md does not name switch-core's endpoints. Change them until
  the server answers; note the working paths in `docs/day0.md`.
- Output is two lines, `PASS`/`FAIL` for the GET and the upgrade. Exit code `0`
  means both passed.

`websocat` is the other option PLAN.md mentions, but PLAN.md gives no install
command for it, so the Python script is the supported path.

---

## 5. Record check 2

In `docs/day0.md`, set check 2 to `pass` only when **both** the HTTP request and
the WebSocket upgrade work. Evidence: the `curl` status code plus the two
`ws_probe.py` lines, pasted.

If either half fails, stop and use the fallback in step 8 before spending time on
check 3 — enrolment needs the same network path.

---

## 6. Enrol the controller (check 3)

**[PLAN]** §8 check 3: Gateway shows **Machines** (agent management on). Signed in
as Rahul, create a one-time code; on the VM run
`install.sh --server https://<laptop>.<tailnet>.ts.net --code <code>`; then
`codex login`; then `switch-agent-controller doctor` passes.

### 6.1 Laptop: one-time code

1. In Gateway, confirm the **Machines** page exists. PLAN.md does not name the
   agent-management toggle — it says only "(agent management on)".
2. Sign in **as Rahul** and create a one-time enrolment code there. The code is a
   secret: paste it straight into the command below, not into `day0.md`.

### 6.2 VM: install

**[PLAN]** gives the flags but **not** where to fetch `install.sh` from. PLAN.md
§Sources points at the controller README; use the install line printed there.
Do not invent a `curl` URL.

```sh
export SWITCH_CONTROLLER_SELF_UPDATE=off
bash install.sh --server "$SWITCH_URL" --code <code>
```

`--server` takes the HTTPS tailnet address: the controller accepts `https`, or
`localhost` (PLAN.md §2). That is why check 2 has to pass first.

### 6.3 VM: pin 0.31.0

```sh
switch-agent-controller --version     # must print 0.31.0
```

PLAN.md pins the version (§11) but does not give a version flag for
`install.sh`. Check `install.sh --help`; if it cannot pin, install the `0.31.0`
release from the controller repo. Do not let it drift onto `main`.

### 6.4 VM: disable self-update for good

`export` only affects the current shell. Add it to the shell profile of the user
that runs the controller:

```sh
echo 'export SWITCH_CONTROLLER_SELF_UPDATE=off' >> ~/.bashrc   # ~/.zshrc if zsh
```

**[not in PLAN.md]** If the controller was installed as a systemd service, shell
exports do not reach it. PLAN.md does not describe the service setup, so check how
`install.sh` installed it and set the variable in the unit's environment before
trusting the pin. Verify after a restart.

### 6.5 VM: Codex

```sh
codex login
```

PLAN.md gives only this command. On a headless VM it prints a device-code or URL
to finish in a browser on another machine. Log in as the **same user that runs
the controller**, otherwise the Codex envoy has no credentials: PLAN.md does not
state this, but the envoy runs under the controller's user.

Node 22 is what the later `scripts/vm_up.sh` installs for Codex (PLAN.md §5). If
`codex` is missing here, install Node 22 first; PLAN.md does not spell out the
Node steps for this phase.

### 6.6 VM: doctor

```sh
switch-agent-controller doctor
```

Must pass, as the user that runs the controller. If it complains about the
server, re-run step 3 and 4: `doctor` fails the same way the probe does.

### 6.7 Record check 3

- Result and date in `docs/day0.md`.
- Evidence: the `doctor` output, `switch-agent-controller --version`, and a
  screenshot of Gateway → Machines showing the laptop and the VM. Save the
  screenshot under `docs/` and put its path in the evidence slot.
- Write the VM's machine name into the **Infrastructure facts** table.

---

## 7. Troubleshooting the path

- **`tailscale status` does not list the laptop** → different tailnet, or the
  laptop is logged out. Nothing below will work.
- **`curl` fails TLS** → HTTPS certificates are off for the tailnet, or Serve is
  not up. On the laptop: `tailscale serve status`. PLAN.md §2 says certificates
  are already on.
- **`502`** → Serve is proxying a port nothing listens on. Re-read the switch-core
  port from `docker ps` (the Gateway's port is the common mistake) and restart
  Serve with the right one.
- **`404` everywhere** → you are probably on the Gateway port, or the `/v1/` path
  is wrong. The Gateway serves a UI; switch-core serves the API.
- **Tailnet ACLs** — PLAN.md does not configure any; §6 records "Every device on
  Om's tailnet can reach the Switch server (it still needs a Switch credential)"
  as a known gap.

---

## 8. One-machine fallback

Use the [one-machine judges' layout](setup-laptop.md#one-machine-judges-layout).
All three gates and both Hermes CLI stand-ins run locally against port 53330.
No second controller, VM or Tailscale is needed. Stop the VM Rahul service
before starting the same registration locally, then restore it afterwards.

---

## What this runbook does not cover

- `rahul-gate`, Hermes, Telegram and `tn mcp` — phases 16 and 18. This VM is not
  given the repo's gate code in phase 02.
- `--separate-users` hardening (P2, PLAN.md §6).
- `scripts/vm_up.sh`, which later automates Node, `codex`, `uv`, enrolment and the
  gate service (PLAN.md §5).

## Remote gate identities

Set `TN_IDENTITY_URL=https://<laptop-tailnet-name>:8666/identities` and
`TN_IDENTITY_TOKEN` in the laptop's gitignored mode-0600 .env. The token must
match the laptop publisher. `scripts/vm_up.sh` transfers both over SSH without
printing them, into the mode-0600 rahul.env service environment.
No database credentials or macOS executable are needed on the VM.

The gate accepts `--identity-url` or TN_IDENTITY_URL; without either it uses the
local exporter for a single-machine installation. It refreshes every five
seconds and on unknown lookup, at most once per second. Fetch failures clear
the map, so commands receive no disclosure until a successful refresh.
Restart with `systemctl --user restart rahul-gate`; inspect state with
`systemctl --user is-active rahul-gate`. Re-deploy after committing changes.
