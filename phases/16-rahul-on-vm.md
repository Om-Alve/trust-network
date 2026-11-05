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
Rahul's gate and envoy run on his own machine (the VM), reaching Om's Switch server through Tailscale Serve.

## Tasks
- [ ] `scripts/vm_up.sh` (idempotent, Ubuntu): installs Node 22, `codex`, `uv`, Tailscale (if missing); installs `switch-agent-controller` 0.31.0 and enrolls with a one-time code passed as an argument; sets `SWITCH_CONTROLLER_SELF_UPDATE=off`; clones/updates this repo; writes a systemd unit for `rahul-gate` (`uv run python -m trustnet.gate --person rahul`, env from `/etc/trust-network/rahul.env`); prints the Hermes `mcp_servers` entry for `tn mcp` (used in phase 18).
- [ ] Data dir on the VM: `TN_DATA_DIR` with Rahul's fixtures copied in.
- [ ] `rahul-envoy-om` created by `rahul-gate` on the VM's machine (`envoy.machine` in Rahul's `trust.yaml`).
- [ ] **[human]** Run `vm_up.sh` on the VM; confirm `systemctl status rahul-gate` and `switch-agent-controller doctor`.

## Done when
- [ ] `shellcheck scripts/vm_up.sh` is clean (or warnings explained in *Log*), and a second run of the script changes nothing.
- [ ] `rahul-gate` survives a VM reboot (systemd) and reconnects after a Tailscale drop.
- [ ] Scene 1 (CLI version from phase 15) passes again with `om-envoy-rahul` on the laptop and `rahul-envoy-om` (Codex) on the VM; Gateway's Machines page shows each envoy on its own machine (screenshot in *Log*).

## Commit
`phase 16: vm_up.sh and rahul-gate as a service on the VM`

## Log
<!-- evidence, deviations, notes -->
