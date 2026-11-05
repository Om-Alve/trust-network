---
id: "02"
title: Infrastructure and Day-0 checks 1–3, 12
status: blocked
priority: P0
owner: human + agent
depends_on: []
plan_refs: ["§2 Machines and network", "§8 checks 1, 2, 3, 12", "§11 Risks (version pins)"]
target: Nov 5 evening
---

# 02 · Infrastructure and Day-0 checks 1–3, 12

## Goal
Every external piece the code will talk to exists and is reachable: Switch server + Console on the laptop, test users and keys, Discord bot, Tailscale Serve, Rahul's machine enrolled on the VM. Each check's result is written down, because the result decides a design choice.

## Tasks

**Agent:**
- [x] Create `docs/day0.md` with one section per check (1–12) from PLAN.md §8: *Check*, *Result* (pass / fail / partial), *Date*, *Evidence*, *Decision taken*. Phases 02, 04, 11 and 18 fill it in.
- [x] Write a runbook in `docs/setup-laptop.md` and `docs/setup-vm.md` with the exact commands below, so they can be re-run and later folded into the README.

**[human] Laptop:**
- [x] Docker running. Switch Console **0.40.1** installed, local Switch server started (switch-core **0.31.0**).
- [x] `docker ps` → write down the **switch-core** port (not the Gateway's) in `docs/day0.md`.
- [x] Check 1: Switch users `rahul` and `priya` exist; a registration key for each (Gateway → API Keys, signed in as each), plus Om's. Keys go into `.env` only.
- [x] Check 2: `tailscale serve --bg <switch-core port>` (Serve, never Funnel). Record the `https://<laptop>.<tailnet>.ts.net` address as `SWITCH_URL` in `.env`.
- [ ] `caffeinate -dims` during work sessions and the demo.

**[human] VM:**
- [x] VM joined to the same tailnet. From the VM, `curl https://<laptop>.<tailnet>.ts.net/v1/…` reaches switch-core, and a WebSocket upgrade works (e.g. `websocat` or a 5-line Python script the agent writes in `scripts/ws_probe.py`).
- [x] Check 3: Gateway shows **Machines**. Signed in as Rahul, create a one-time code; on the VM, `install.sh --server https://<laptop>.<tailnet>.ts.net --code <code>`; `export SWITCH_CONTROLLER_SELF_UPDATE=off`; `codex login`; `switch-agent-controller doctor` passes. Pin controller **0.31.0**.

**[human] Discord:**
- [ ] Check 12 (first half): bot with **Message Content** and **Server Members** intents, invited to the guild; Switch's Discord connection configured; Om's Discord account linked. (The `#om-home` channel itself is created by the template in phase 11, which finishes check 12.)

## Done when
- [ ] `docs/day0.md` has a recorded result for checks 1, 2, 3 and the first half of 12.
- [ ] For each failed check, the fallback from PLAN.md §8 is written under *Decision taken* (e.g. check 2 fails → Rahul's controller runs on the laptop with its own `--data-dir` over `localhost`).
- [x] Gateway's Machines page shows the laptop and the VM (screenshot path in *Log*), or the fallback is recorded.
- [x] `.env` has `SWITCH_URL` and the keys; `git check-ignore .env` confirms it's ignored.

## Commit
`phase 02: day-0 infra checks and setup runbooks`

## Log
<!-- evidence, deviations, notes -->

Prep done 2026-11-05. Agent side is complete; the phase is blocked on Om.

Files: `docs/day0.md` (all 12 checks, results `pending`, §8 fallbacks prefilled),
`docs/setup-laptop.md`, `docs/setup-vm.md`, `scripts/ws_probe.py` (ruff-clean;
GET + WebSocket probe, exit non-zero on fail). Runbooks mark every step PLAN.md
does not specify instead of inventing flags.

**Ask for Om — work through the two runbooks, recording results in `docs/day0.md`:**

1. **Laptop** (`docs/setup-laptop.md` steps 1–6): Docker up; Console **0.40.1**
   with switch-core **0.31.0**; `docker ps` → write the **switch-core** host port
   into `docs/day0.md`; users `rahul` and `priya` plus registration keys
   (Gateway → API Keys, signed in as each) into `.env` only; `tailscale serve --bg
   <switch-core port>` (Serve, never Funnel) and `SWITCH_URL` into `.env`;
   `caffeinate -dims` for the session.
2. **VM** (`docs/setup-vm.md` steps 1–6): join the tailnet; run `curl` plus
   `python3 scripts/ws_probe.py` against `$SWITCH_URL` (check 2); then Gateway →
   Machines as Rahul → one-time code → `install.sh --server … --code …`,
   `export SWITCH_CONTROLLER_SELF_UPDATE=off`, `codex login`,
   `switch-agent-controller doctor`, pin **0.31.0** (check 3).
3. **Discord** (`docs/setup-laptop.md` step 7): bot with **Message Content** and
   **Server Members** intents, invited to the guild; Switch's Discord connection
   configured; Om's account linked (12a; `#om-home` is phase 11's template).

Then set checks 1, 2, 3 and 12a to `pass`/`fail` in `docs/day0.md` with date and
evidence. On fail, keep the §8 fallback already under *Decision taken*; if check 2
fails, use `docs/setup-vm.md` §8 (Rahul's controller on the laptop, own
`--data-dir`, localhost).

### Ambiguities found in PLAN.md

- No concrete `/v1/…` HTTP or WebSocket endpoint is named, so `ws_probe.py` takes
  both paths as options with commented, unverified defaults.
- Not in PLAN.md: where to get the Console installer, the page where users are
  created, the Discord invite scopes, the Switch Discord-connection page, the
  account-link page, and the controller pin/version flag. The runbooks say so.
- Check 2's fallback moves only the controller, but `rahul-gate` and Hermes also
  need to reach switch-core. If check 2 fails they must run on the laptop too, or
  phase 16 is cut (PLAN.md §9). Noted in `docs/setup-vm.md` §8.

### Progress 2026-11-05 (laptop side)

- Switch Console 0.40.1 runs switch-core 0.31.0 **natively, not in Docker** (deviation from
  PLAN.md §2 "Docker, run by Console"). switch-core is `127.0.0.1:53330`; the port map is in
  `~/Library/Application Support/switchdash/local-switch-server/ports.json`, not `docker ps`.
- Check 1 **pass**: users and keys created by `scripts/switch_users.py --console-env`
  through the Gateway API (no UI clicks). Om is the local `admin@switch.local` account.
- Check 2 laptop half: `tailscale serve --bg --https=8443 http://127.0.0.1:53330` (443 was
  already serving another local app). `SWITCH_URL=https://<your-mac>.<tailnet>.ts.net:8443`;
  `/health` → 200 from the laptop. VM half pending.
- `.env` has `SWITCH_URL` and the three keys; `git check-ignore .env` → `.env`.
- Still open: VM (checks 2 VM half, 3; needs SSH access to `hermes`), Discord (12a), caffeinate.

### Progress 2026-11-05 (VM side)

- Check 2 **pass** from the VM (HTTPS 200 + WebSocket upgrade through Tailscale Serve).
- Check 3 **pass**: controller 0.31.0 enrolled as `rahul-vm` under Rahul, running as a systemd
  user service, `doctor` ok for codex. Machines (via `GET /gateway/management/controllers`):
  Rahul → `rahul-vm`; Om → `Om’s MacBook Pro`. API output stands in for the screenshot.
- Deviations: no `/v1/` prefix on switch-core; `SWITCH_CONTROLLER_SELF_UPDATE` doesn't exist in
  0.31.0 (pin holds because the server names no release; PLAN.md §11 updated); codex was
  already logged in on the VM.
- Remaining: check 12a (Discord bot) and `caffeinate -dims` — both Om's.
