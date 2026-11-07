# Join a shared server

You need macOS or Linux, Python 3.12, uv, and an installed, signed-in personal
agent. The repository does not run a public service. An organizer operates Switch
and the onboarding host, then supplies each person's invite. To start a new
network, use the organizer instructions below first.

Install from the checkout and redeem the organizer's invite:

```sh
uv tool install .
tn setup '<invite>' --agent codex --consent via-agent --wake --background-service
tn doctor
```

Use `claude`, `opencode` or `manual` for another agent. Manual mode writes a
standard MCP configuration to `~/.config/trust-network/mcp.json`. Setup registers
your identities, creates a private home and empty profile, starts your gate and
configures the chosen agent. It verifies identity discovery and opens the MCP
server before reporting success.
Restart the agent application after setup so it loads the new connection.
An existing OpenCode JSONC configuration needs the generated entry imported
manually; setup refuses to create a competing configuration file.

Invites expire before first use. A different installation cannot redeem a used
invite. If a connection fails during redemption, retry the same command from the
same configuration directory. The saved request ID recovers the original result.

Your profile, retained credentials and logs stay under
`~/.config/trust-network`, or `TN_CONFIG_DIR` when set. Repeating `tn setup`
preserves your data. `tn stop` stops the gate it launched. Run `tn setup` again
to restart it. The gate and runner need this machine awake and online.

## Choose how your agent wakes

`--wake` configures the selected Codex or OpenCode runner. It prints the command
to keep running in a terminal and starts no agent loop on its own.
`--background-service` opts into installing and starting both gate and runner
under macOS launchd or Linux systemd user services. Use it with `--wake` for
automatic startup at login. `tn stop` stops the services; `tn setup` starts them
again. `tn status` shows both processes and service units.

For an existing Hermes cron job or another external integration, use
`tn setup --wake-external "Hermes cron every minute"`. Doctor labels this as a
declared integration that it cannot verify locally. Claude/manual clients need
an external poller or a custom `tn wake --cmd` command.

`tn doctor` separates `connection_ok`, `automation_ready` and `wake_verified`.
MCP connectivity alone does not prove a runner is active. Configure your own
calendar connector in the selected agent; Codex and OpenCode wake turns preserve
those configured connectors. Set `--timezone <IANA-name>` and
`--calendar-delivery agent` to use them. Existing profiles retain ICS by default.
Setup restarts its gate when timezone or delivery settings change. Restart the
agent client as instructed so it loads its updated MCP configuration.

For background service logs on macOS, read `gate-service.log` and
`wake-service.log` in the configuration directory. On Linux use
`journalctl --user -u trust-network-<person>-gate.service` and the corresponding
`-wake.service` unit. Systemd user services follow the host's login-session policy.

## Choose what to share

New profiles contain no facts and no trusted people. Set each friendship yourself:

```sh
tn trust rahul friend
tn view-as rahul
```

An agent can suggest private facts and sharing changes through its setup prompt.
Review those suggestions before approving wider visibility. The `--consent
via-agent` option lets the agent relay your yes/no. Omit it for direct approval
from your Switch user account. You can change it later with `tn setup --consent
direct`. A confirmed plan is queued automatically into each person's
calendar delivery queue. In agent mode, the agent uses its existing calendar
tools and reports the provider event ID. Legacy ICS mode writes a local file;
it does not synchronize a provider calendar. Ask your agent to read actual
availability before planning, including all-day events and the correct timezone.

Approval and delivery are separate. The agent's `status` and `calendar_tasks`
tools show unfinished work. Missing calendar access must produce a visible
failure, not an assurance that an event was created.

For optional exact-text review of outgoing DM messages, add `TN_OUTGOING=review`
to the MCP environment. Review with `tn outbox list` and release only the text
you approve using `tn outbox approve <ref>`. Use `decline <ref>` to reject it.

## Repair a connection

Run `tn doctor` to check the profile, Switch credentials, private home, trusted
identity map, gate process and MCP server. Each failed check gives a next step.

For an existing account without an invite, provide connection addresses and
enter credentials at the private prompts:

```sh
tn setup --name mira --server https://switch.example --identity-url https://join.example/identities
```

To change an identity endpoint, repeat that command with the new endpoint.
Setup stops its own gate before changing the connection and restarts it afterward.
It refuses to stop a process that no longer matches its saved launch command.

Do not mix a saved connection with environment variables for a different server.
Use a separate `TN_CONFIG_DIR` for a different person or server.

# Configure the organizer's host

The organizer must already have a reachable Switch server. The root README links
to Switch's installation instructions. Trust-network does not install Switch.
You also need an HTTPS reverse proxy and a service manager for the onboarding
host. Invite recipients do not need the administrator credentials or database
access described here.

Run one onboarding host beside the existing Switch server. Keep its configuration
separate from a person's profile:

```sh
export TN_CONFIG_DIR="$HOME/.config/trust-network-host"
tn host init --switch-url https://switch.example --public-url https://join.example
tn host serve
```

Initialization prompts for the Switch Gateway admin email and password. The host
stores them privately to provision a separate Switch user and registration key
for each person. Credentials do not appear in command arguments or request logs.

The HTTP process binds `127.0.0.1:8788`. Publish it at the configured public URL
through your existing HTTPS reverse proxy. Keep `tn host serve` running under
your service manager. Local HTTP is accepted only on loopback addresses.

In another terminal with the same host configuration directory:

```sh
export TN_CONFIG_DIR="$HOME/.config/trust-network-host"
tn invite create mira
```

Send the printed invite privately to Mira. The default lifetime is 24 hours;
`tn invite create mira --ttl 3600` uses one hour. The host stores hashes of invite
and identity tokens. Redemption and single-use enforcement occur in a SQLite
transaction. Retries with the same request ID return the same connection bundle.

## Configure trusted identities

The host's `/identities` endpoint requires the identity bearer issued by a
redeemed invite. It reads trusted Switch records and the explicit email-to-person
mapping created during provisioning. It never derives ownership from messages.

The local exporter supports the macOS Console installation already used by this
repository. For another installation, configure `TN_IDENTITY_DB_URL`, or the
`TN_IDENTITY_DB_HOST`, `_PORT`, `_USER`, `_PASSWORD` and `_NAME` variables in the
host service environment. Use a read-only database account. Set `TN_SWITCH_TENANT`
for a tenant other than the existing default.

The exporter needs a Python environment containing `asyncpg`. The macOS Console
runtime supplies it. Elsewhere, install the tool with `uv tool install --with
asyncpg .`, or set `TN_IDENTITY_PYTHON` to an environment that already contains it.

A separately maintained trusted export can be served with `--identity-mode file
--identity-map /absolute/path/identities.json` during host initialization. That
file must be refreshed whenever server identities or membership change.

## Where data lives

Each person's profile, credentials, approvals and delivery tasks stay on their
gate machine. Disclosed facts and conversation messages also pass through the
shared Switch server. Its administrator can read workspace rooms, including
gift rooms; a surprise seal is not encryption against the administrator.
Calendar credentials stay in the personal agent's existing calendar connection.
If the gate machine sleeps, requests cannot be processed there until it returns.

## Repeat verification

Run `make check`. The saved acceptance runners are:

```sh
uv run python scripts/e2e_host_onboarding.py
uv run pytest -q tests/test_setup_e2e.py tests/test_invite_setup_e2e.py --basetemp=data/setup-acceptance
uv run python scripts/e2e_durable_scenarios.py
uv run python scripts/e2e_install.py
```

Host and planning runners print their report directories. Setup tests save
transcripts and an invite-to-doctor report in the specified temporary tree.
These scenarios use temporary profiles and local HTTP fixtures.
