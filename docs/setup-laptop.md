# Run the demo on one machine

Start the local Switch server in Console. The example address is
`http://127.0.0.1:53330`; use the actual switch-core port from your installation.
No VM, Discord bot or Tailscale connection is required for this layout.

```sh
uv sync --locked
uv run python -m scripts.demo_up --one-machine --data-dir data/judges
```

Bootstrap creates missing demo users and keys, copies missing profiles, reuses
registered credentials and prints gate launch commands. Run each printed command
in a separate terminal. Existing gates using the same identities must be stopped.

In another terminal, use the same Switch address and profile directory:

```sh
export SWITCH_URL=http://127.0.0.1:53330
export TN_DATA_DIR="$PWD/data/judges"
export TN_STATE_DIR="$PWD/data"
uv run tn --as om dm rahul "Sunday bowling dinner"
uv run tn --as om inbox
uv run tn --as rahul inbox
```

Use `dm-read`, `dm-post` and `answer` to drive the conversation. Both approvals
queue events on the owners' local ICS calendars. An MCP agent can use the same
operations through `tn --as <person> mcp`.

The local identity exporter reads the Switch server's trusted database mapping.
It currently expects the macOS Console layout. A remote gate uses the
`TN_IDENTITY_URL` authenticated publisher and `TN_IDENTITY_TOKEN` instead.

## Reset disposable demo state

Stop the gates and agent pollers first. Preview and then run reset:

```sh
uv run python -m scripts.demo_reset --one-machine --data-dir data/judges --dry-run
uv run python -m scripts.demo_reset --one-machine --data-dir data/judges
```

Reset preserves credentials, facts and trust settings. It clears decisions,
ledger records, claims, cursors and share cards, archives demo rooms and restores
fixture calendars. Restart the gates after reset.

The live bootstrap acceptance script is `tests/e2e_demo_bootstrap.py`. It runs
Scene 1 twice with a reset between runs and saves transcripts, approvals,
ledgers and calendars. Run it only after stopping existing demo gates.
