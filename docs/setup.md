# Join a shared server

Install from the checkout and redeem the organizer's invite:

```sh
uv tool install .
tn setup '<invite>' --agent codex --consent via-agent
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
to restart it. The gate runs in the background while this machine is awake;
setup does not install an OS login service.

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
local ICS calendar; the agent must not add it a second time.

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
