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
Rahul's gate and his main agent (`rahul-agent`, a managed Codex agent) run on his own machine (the VM), reaching Om's Switch server through Tailscale Serve. The same VM also hosts Om's Hermes (host `hermes`, user `om`) — a demo shortcut, called out so it's never mistaken for a security boundary; the two are kept apart by Switch identity, not by machine.

> Repurposed, 2026-11-05 (no-envoy decision + main-agent swap): there's no envoy for the VM to
> run anymore. Instead this phase now does double duty: it's where **Om's Hermes** lives (acting
> as `om-hermes` via `tn mcp`), and where **Rahul's main agent** (`rahul-agent`, managed Codex)
> needs to be stood up — the `rahul-vm` controller enrollment (phase 02) is required again, not
> optional, because it now runs Rahul's actual main agent, not a dropped envoy.

## Tasks
- [ ] `scripts/vm_up.sh` (idempotent, Ubuntu): installs Node 22, `codex` (needed for the `rahul-vm` controller to run `rahul-agent`), `uv`, Tailscale (if missing); installs `switch-agent-controller` 0.31.0 and enrolls with a one-time code passed as an argument; sets `SWITCH_CONTROLLER_SELF_UPDATE=off`; clones/updates this repo; writes a systemd unit for `rahul-gate` (`uv run python -m trustnet.gate --person rahul`, env from `/etc/trust-network/rahul.env`); confirms or writes Om's Hermes config (already installed at `~/.local/bin/hermes` under user `om` per the Nov 5 note) and prints its `mcp_servers` entry for `tn mcp --as om` (used in phase 18).
- [ ] Data dir on the VM: `TN_DATA_DIR` with Rahul's fixtures copied in.
- [ ] **New: stand up `rahul-agent`.** Create it as a Switch-managed Codex agent on the `rahul-vm` controller (`provider: codex`, no model override, `auto_mode`/`auto_approve` off), placed in an agent-only Switch room `rahul-home` alongside `rahul-gate`, opened in Console signed in as Rahul (a Discord channel is optional). This is the parallel of `templates/home.template.yaml`, but for an agent-only room instead of a Discord channel; no such template exists yet — write one (`templates/rahul-home.template.yaml` or equivalent) or document the manual Console steps if templating an agent-only room isn't supported.
- [ ] **[human]** Run `vm_up.sh` on the VM; confirm `systemctl status rahul-gate`, `switch-agent-controller doctor`, and that `rahul-agent` answers in `rahul-home`.

## Done when
- [ ] `shellcheck scripts/vm_up.sh` is clean (or warnings explained in *Log*), and a second run of the script changes nothing.
- [ ] `rahul-gate` survives a VM reboot (systemd) and reconnects after a Tailscale drop.
- [ ] Scene 1 (CLI version from phase 15) passes again with `rahul-gate` and a live `rahul-agent` on the VM, and Om driven through Hermes (also on the VM) or its CLI stand-in; Gateway's Machines page shows the laptop and `rahul-vm` (screenshot in *Log*).

## Commit
`phase 16: vm_up.sh, rahul-gate, rahul-agent and om-hermes on the Azure VM`

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
