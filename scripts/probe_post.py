"""Register a disposable protocol agent and post a live smoke-test message."""

import argparse
import asyncio
import os

from trustnet.switch_client import SwitchClient


async def probe(args):
    client = await SwitchClient.register(
        args.url, os.environ[args.key_env], args.name, agent_type=args.agent_type
    )
    # Registration returns a one-time key; keep it locally, never print it.
    if args.credentials:
        import json

        fd = os.open(args.credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({"id": client.agent_id, "api_key": client.api_key}, stream)
    try:
        # Om must assign this agent to the target room before connection.
        await client.connect_to_room(args.room)
        print(await client.post_message("hello from trust-network"))
    finally:
        await client.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-env", default="OM_GATE_KEY")
    parser.add_argument("--room", required=True)
    parser.add_argument("--url", default=os.environ.get("SWITCH_URL", "http://localhost:8000"))
    parser.add_argument("--name", default="trustnet-probe")
    parser.add_argument(
        "--agent-type", required=True, help="Installed known agent type from Switch"
    )
    parser.add_argument("--credentials", help="New gitignored file for one-time credentials")
    asyncio.run(probe(parser.parse_args()))
