"""Run a gate using retained credentials and a trusted server identity export."""

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from trustnet.gate import relay
from trustnet.gate.identity import IdentitySource, read_identities
from trustnet.gate.runtime import Gate
from trustnet.room_pool import RoomPool
from trustnet.switch_client import SwitchClient

__all__ = ["read_identities"]


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
    # One connection per open room: Switch only delivers a room's addressed
    # messages to a session in that room (see trustnet/room_pool.py).
    pool = RoomPool(client, name=args.person + "-gate")
    try:
        identities = IdentitySource(args.identity_map, args.identity_url)

        async def refresh():
            while True:
                await asyncio.to_thread(identities.refresh)
                await asyncio.sleep(5)

        refresh_task = asyncio.create_task(refresh())
        pool.start()
        gate_task = asyncio.create_task(Gate(args.person, pool, identities).run())
        try:
            await client.ready.wait()
            await pool.start_sync()
            try:
                await relay.ensure_home(args.person, client)
            except Exception as exc:
                # The gate can still serve its rooms; the next home post retries.
                logging.getLogger(__name__).warning("home bootstrap failed: %s", type(exc).__name__)
            await gate_task
        finally:
            refresh_task.cancel()
            await asyncio.gather(refresh_task, return_exceptions=True)
            gate_task.cancel()
            await asyncio.gather(gate_task, return_exceptions=True)
    finally:
        await pool.aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--person", required=True)
    parser.add_argument("--key-env", required=True)
    parser.add_argument("--state", type=Path, default=Path("data/day0-state.json"))
    parser.add_argument("--identity-map", type=Path, default=Path("data/gate-identities.json"))
    parser.add_argument("--identity-url", default=os.environ.get("TN_IDENTITY_URL"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
