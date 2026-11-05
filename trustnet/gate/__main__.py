"""Run a gate using retained credentials and a trusted server identity export."""

import argparse
import asyncio
import json
import logging
import os
import subprocess
from pathlib import Path

from trustnet.gate.policy import Identity, SenderKind
from trustnet.gate.runtime import Gate
from trustnet.switch_client import SwitchClient


def read_identities(path):
    return {
        key: Identity(SenderKind(value["kind"]), value["id"], value.get("owner_id"))
        for key, value in json.loads(path.read_text()).items()
    }


async def run(args):
    state = json.loads(args.state.read_text())
    credentials = state.get(args.person)
    if credentials is None:
        client = await SwitchClient.register(
            os.environ["SWITCH_URL"],
            os.environ[args.key_env],
            args.person + "-gate",
            agent_type="codex",
        )
        state[args.person] = {"id": client.agent_id, "api_key": client.api_key}
        args.state.write_text(json.dumps(state))
        args.state.chmod(0o600)
    else:
        client = SwitchClient(os.environ["SWITCH_URL"], credentials["id"], credentials["api_key"])
    try:

        def identities():
            core = (
                Path.home()
                / "Library/Application Support/switchdash/local-switch-server/native/switch-core/0.31.0"
            )
            exporter = Path(__file__).resolve().parents[2] / "scripts/gate_identity_export.py"
            subprocess.run(
                [str(core / "venv/bin/python"), str(exporter)],
                check=True,
                env={**os.environ, "TN_IDENTITY_MAP": str(args.identity_map)},
            )
            return read_identities(args.identity_map)

        await Gate(args.person, client, identities).run()
    finally:
        await client.aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--person", required=True)
    parser.add_argument("--key-env", required=True)
    parser.add_argument("--state", type=Path, default=Path("data/day0-state.json"))
    parser.add_argument("--identity-map", type=Path, default=Path("data/gate-identities.json"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
