---
id: "16"
title: Rahul's side on the Azure VM
status: blocked
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
- [x] Idempotent laptop-invoked Ubuntu deployment in `scripts/vm_up.sh`: check/install git and uv, sync committed source, `uv sync --locked --python 3.12`, install systemd user service. Node/codex/controller remain optional and untouched.
- [x] Seed `TN_DATA_DIR` with only Rahul's fixtures; retain his registration and transfer only `RAHUL_GATE_KEY` and `SWITCH_URL` in a mode-0600 environment file.
- [x] Check laptop for duplicate gate processes; install, enable and restart VM service.
- [x] Addressed `free` / `ask` round-trip with both gates across machines.
- [ ] Phase 17: provide `tn mcp` on the VM, using each main agent's own credentials.
- [ ] Phase 18: create Rahul's Hermes profile, Discord bot and home room; wire both profiles to MCP. Om's existing Hermes configuration remains untouched in this phase.

## Done when
- [x] Shellcheck passes; repeated deployment succeeds without replacing Rahul's mutable profile or registration.
- [x] User service is enabled, linger is on, and explicit restart returns active/running.
- [x] Explicit service restart and identity publisher outage recovery verified. Full VM reboot and Tailscale interruption deferred to avoid disrupting both Hermes profiles.
- [ ] Live gate command exchange and full Scene 1 with both main agents pass.
- [ ] Both Hermes Discord profiles and Machines-page screenshot verified (phase 18).

## Commit
`phase 16: rahul-gate on the VM, vm_up.sh`

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

### VM deployment — 2026-11-05

Deployed committed source snapshot `ffe1751` to `/home/om/trust-network` using
`git archive HEAD` over SSH. This is a source snapshot rather than a remote clone:
there is no remote, and archiving committed paths excludes the other agent's
unfinished phase 15 changes, `.env`, `data/`, and Om's uncommitted AGENTS.md edit.
Om/Priya example directories are omitted as well. Re-running after a phase 15/17
commit updates the source. No production Om/Priya data or credentials were copied.
The generated archive and filtered secrets exist only in a temporary 0700 local
directory (archive 0600), deleted when SSH completes. The VM environment file is
`~/.config/trust-network/rahul.env` (0600). Identity aliases are non-secret trusted
server metadata, copied separately; no database credentials travel.

Retained Rahul registration `423f4fd8-f632-4bb3-b5a9-66ca3109436d` is in VM
`data/rahul-state.json` (0600, Rahul entry only). No re-registration was needed.
Laptop process inspection found no persistent gate processes; phase 11/14 probes
owned their gates for bounded runs. Do not run those old two-gate probes while
this service is running: they reuse the same Rahul registration. The deployment
refuses known local gate/probe processes. This is an operational check, not a
cross-machine lock; future bootstrap code must respect VM ownership.

`systemctl --user show rahul-gate -p ActiveState -p SubState -p NRestarts` after
restart: `ActiveState=active`, `SubState=running`, `NRestarts=0`.
`loginctl show-user om -p Linger`: `Linger=yes`. Controller and Hermes gateway
were already active and were not reconfigured. `uv run tn --help` succeeds.
Second `scripts/vm_up.sh` run succeeded (resolved/audited existing dependencies).
Re-running intentionally restarts the service; it preserves mutable profile and
registration files. It does not promise an unchanged PID.

Live artifact: gitignored `data/phase16-evidence.log`, produced by
`PYTHONPATH=. uv run python data/phase16-probe.py` (retained local probe).
Room `8bc80b5e-9cfe-4516-8ebb-9d7c1eb1cfb2` contained om-gate and rahul-gate.
Om posted `@rahul-gate free 2026-11-08..2026-11-09`; the VM made successful
get_room_detail/connect_to_room/list_participants HTTP 200 calls, then logged
`ERROR:trustnet.gate.runtime:gate dispatch failed: FileNotFoundError`.
There were zero Rahul command replies (server join greetings excluded).
Room deletion returned HTTP 200. An earlier connectivity-only room
`55212b0b-9ee1-4fa3-8bf0-eae6ce41681a` was also deleted (HTTP 200).
No free/ask round-trip or Scene 1 success is claimed.

Blocking code change, owned by phase 15: `trustnet/gate/__main__.py` always runs
`~/Library/Application Support/switchdash/local-switch-server/native/switch-core/0.31.0/venv/bin/python`
to export identities on every addressed command. This macOS executable and local
server database do not exist on Ubuntu. `--identity-map` selects the output file,
not a read-only external-map mode. Add a supported remote identity source (or an
explicit pre-exported-map mode with a trusted refresh procedure), then redeploy
and repeat free/ask both ways, restart, network recovery and Scene 1. Do not copy
Switch's database password or Om's private data onto the VM as a workaround.
No gate or tn code was edited by this phase.

Remaining phase 17/18 steps: deploy their committed implementation with vm_up;
provide `tn mcp`, separate main-agent registration credentials and state; create
Rahul's separate Hermes/Discord profile and home room; configure Om's MCP only
under phase 18 authorization; verify consent/calendar Scene 1 through both bots.
Hermes keys must go in separate 0600 files; vm_up intentionally transfers no
Hermes keys yet. Reboot and Tailscale interruption still need live verification.

Deviations: user instructions narrow the older PLAN §5 row and phase tasks:
Node 26 is already installed, controller is optional, systemd is a user service,
and Hermes configuration belongs to phase 18. Source deployment uses a filtered
git archive rather than clone/bundle/rsync to avoid uncommitted concurrent work.

Validation: `uvx --from shellcheck-py shellcheck scripts/vm_up.sh` and
`bash -n scripts/vm_up.sh` passed. `git diff --check` passed. `make check` was
run before committing, twice, but stopped at ruff format: concurrent phase 15
file `scripts/e2e_scene1.py:31` needs a blank line after its logging import
(86 other files formatted). That file is outside this phase's ownership and
was left untouched; pytest did not run in those attempts. Phase remains blocked.
VM stat confirmed 0600 for env/registration. All three user services
`rahul-gate`, `hermes-gateway`, `switch-agent-controller` were active after
the repeated deployment.


### Remote identity resolution, 2026-11-05

Replaced the macOS-only launch assumption with IdentitySource. --identity-url /
TN_IDENTITY_URL selects HTTPS; absent either, the single-machine local exporter
still works. The callback and five-second background refresh share a lock.
Unknown lookups refresh at most once per second. Failed fetches clear all
aliases; an unknown sender remains unknown. HTTP requests have a five-second
timeout and bounded response size. Credentials never travel in URLs or logs.

The publisher is a localhost stdlib HTTP server on 8792, exposed with a new
tailnet-only Tailscale Serve HTTPS mapping on 8666. Existing 443, 8443 and 8554
mappings were preserved; Funnel was not used. GET /identities regenerates the
map, avoiding a file-sync scheduler and stale remote copies after registration
or membership changes. A bearer token was generated into laptop .env and
transferred via SSH by vm_up into the mode-0600 VM service environment.
LaunchAgent net.trust-network.identities keeps the laptop publisher alive.

The exporter now connects as DB_USER, never DB_OWNER_USER, in a read-only
transaction. The initial LIMIT 0 permission check passed but missed RLS:
actual clients reads require app.tenant_id. Transaction-local tenant-zero
context fixes that while preserving RLS. Actual full exports and the live
round trip passed with the application role; no dedicated role was necessary.
The fallback column grants and optional dedicated credentials are documented
in setup-laptop. client_rooms is required for existing authoritative membership
aliases in addition to users/clients/agents.

Live repeatable artifact: run uv run python -m scripts.identity_live_probe.
It writes gitignored data/phase16-evidence.json and deletes its probe room in
finally. First successful room 8f5e591b-f9cd-4d8e-8bd9-9df3acf38de6:
laptop om-gate asked VM rahul-gate free 2026-11-08..2026-11-09 and received
15:00–20:30 Cricket, including the title allowed at close. Rahul's authenticated
Gateway user then sent @om-gate ask diet neighbourhood address in that room.
The laptop gate replied vegetarian, Indiranagar, and address: not shared with
you. This checks acquaintance/close facts and private-field refusal with live
transport identity. Cleanup HTTP 200. No second Rahul gate consumer was started.

Explicit VM service restart returned active. Unloading the laptop publisher
produced an empty identity map on fetch and a fail-closed warning. Reloading
the publisher and rerunning the same live probe verified recovery. An
unauthenticated HTTPS request returned 401. This is a publisher-path outage,
not a full Tailscale disconnect; no VM reboot was performed, to avoid
interrupting the existing Hermes profiles.

Validation: make check passed, 455 tests; bash -n and shellcheck passed.
No unit tests were added after implementation. The live probe is the
repeatable behavioral artifact. Remaining blockers are phases 17/18: deploy
their MCP/Hermes integration, run full Scene 1 via both bots and capture their
Machines/Discord evidence. Phase status remains blocked only on that work.

Final shared-tree check caveat: the earlier 455-test make check passed before
concurrent phase 17/20 edits. The final make check invocation stops at phase
17's trustnet/tn/mcp.py:184 F841 (unused exc). That owned file was not edited.
Live probes also wrote a ledger into examples/om before isolation was added;
the ignored ledger was preserved in data/phase16-fixture-ledgers/om-ledger.jsonl
so tests that copy example profiles do not inherit live disclosures. The
committed probe now uses a temporary profile tree. Recovery probe room
060517e1-1a90-4a55-907b-9252c2332ecb passed both commands and cleanup HTTP 200.
