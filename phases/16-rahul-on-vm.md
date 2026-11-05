---
id: "16"
title: Rahul's side on the Azure VM
status: todo
priority: P1
owner: human + agent
depends_on: ["15"]
plan_refs: ["§2 Machines and network", "§5 scripts/vm_up.sh", "§8 checks 2–3"]
target: Nov 6 night
---

# 16 · Rahul's side on the Azure VM

> Cut line: if this slips, Rahul's controller and gate stay on the laptop (separate `--data-dir`, `localhost`). Nothing else changes.

## Goal
Rahul's gate and his main agent (his own **Hermes** profile, acting as `rahul-hermes`, on Discord) run on the Azure VM, reaching Om's Switch server through Tailscale Serve. The same VM also hosts Om's Hermes (host `hermes`, user `om`) — a demo shortcut, called out so it's never mistaken for a security boundary; the two are kept apart by Switch identity, not by machine.

> Repurposed, 2026-11-05 (no-envoy decision, then both people on Hermes via Discord): there's no
> envoy, and no managed `rahul-agent`, for the VM to run anymore. This phase now does double
> duty for **both** main agents: it's where **Om's Hermes** lives (acting as `om-hermes` via
> `tn mcp`), and where **Rahul's own Hermes** (a second profile, its own Discord bot, acting as
> `rahul-hermes`) is stood up. Neither is a Switch-managed agent, so the `rahul-vm`
> `switch-agent-controller` enrollment (phase 02/03) is **not** needed by this flow — it stays
> enrolled, unused and optional, kept only in case a managed agent is ever wanted again.

## Tasks
- [ ] `scripts/vm_up.sh` (idempotent, Ubuntu): installs Node 22, `uv`, Tailscale (if missing); installs `switch-agent-controller` 0.31.0 and enrolls with a one-time code passed as an argument (kept for optional future use, not required by any flow here); sets `SWITCH_CONTROLLER_SELF_UPDATE=off`; clones/updates this repo; writes a systemd unit for `rahul-gate` (`uv run python -m trustnet.gate --person rahul`, env from `/etc/trust-network/rahul.env`); confirms or writes Om's Hermes config (already installed at `~/.local/bin/hermes` under user `om` per the Nov 5 note) and prints its `mcp_servers` entry for `tn mcp --as om`; installs and configures a **second** Hermes profile for Rahul, with its own Discord bot token, and prints its `mcp_servers` entry for `tn mcp --as rahul` (both used in phase 18).
- [ ] Data dir on the VM: `TN_DATA_DIR` with Rahul's fixtures copied in.
- [ ] **Stand up Rahul's Hermes profile.** No Switch agent-management placement is needed (unlike the dropped managed-Codex plan) — Rahul's Hermes registers itself directly through `tn mcp --as rahul`, the same code path Om's Hermes uses. `rahul-home` is a plain agent-only Switch room holding `rahul-gate` and `rahul-hermes`, created the same way `conn-*`/`dm-*` rooms are (no template needed).
- [ ] **[human]** Run `vm_up.sh` on the VM; confirm `systemctl status rahul-gate`, and that both Hermes profiles (`om-hermes`, `rahul-hermes`) are reachable on their own Discord bots.

## Done when
- [ ] `shellcheck scripts/vm_up.sh` is clean (or warnings explained in *Log*), and a second run of the script changes nothing.
- [ ] `rahul-gate` survives a VM reboot (systemd) and reconnects after a Tailscale drop.
- [ ] Scene 1 (CLI version from phase 15) passes again with `rahul-gate` and a live `rahul-hermes` on the VM, and Om driven through his own Hermes (also on the VM) or its CLI stand-in; Gateway's Machines page shows the laptop and the VM (screenshot in *Log*).

## Commit
`phase 16: vm_up.sh, rahul-gate and both Hermes profiles on the Azure VM`

## Log
<!-- evidence, deviations, notes -->

### No-envoy decision and main-agent swap, 2026-11-05

This phase changed scope: it no longer places an envoy on the VM; it now places Rahul's main
agent (`rahul-agent`, managed Codex, in a new `rahul-home` room) and confirms Om's Hermes
(already installed on this VM, host `hermes`, user `om`) is wired to `tn mcp --as om`. The
`rahul-vm` controller enrollment, optional immediately after the no-envoy decision, is required
again now that it runs Rahul's real main agent. The biggest open gap: there is no template for
an agent-only-room equivalent of `templates/home.template.yaml` yet, so `rahul-agent`'s setup
may need to be a documented manual Console sequence until one is written.

### Both on Hermes, on Discord — 2026-11-05

Superseded the above the same evening: `rahul-agent` (managed Codex) is dropped. Rahul's main
agent is now his own **Hermes** profile, `rahul-hermes`, a second Discord bot on the same VM.
This closes the exact gap the previous entry flagged: no template or managed-agent placement is
needed at all now, since Hermes registers itself directly via `tn mcp --as rahul`, the same way
`om-hermes` does. The `rahul-vm` controller enrollment reverts to optional/unused — nothing in
this phase's critical path needs it. Goal, tasks and Done-when above are rewritten accordingly;
`status` unchanged (`todo`).
