"""Live, read-only view of an agent-only room, for screen recording.

Switch Console can't open agent-only rooms (no chat channel), so this prints the
transcript as Om's gate sees it: a member of every DM room it creates.

    uv run --env-file .env python -m scripts.room_watch            # newest open dm-* room
    uv run --env-file .env python -m scripts.room_watch --prefix gift-

Join events and Switch's automatic greeting (a member's first message within two
seconds of joining) are hidden unless --all is given.
"""

import argparse
import asyncio
import json
import os
import sys
import textwrap
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trustnet.switch_client import SwitchClient

COLOURS = {"gate": "\033[2;37m", "hermes": "\033[1;36m", "rahul-hermes": "\033[1;33m"}
RESET = "\033[0m"


def colour(name: str) -> str:
    if name in COLOURS:
        return COLOURS[name]
    return COLOURS["gate"] if name.endswith("-gate") else COLOURS["hermes"]


async def newest_room(client, prefix):
    rooms = (await client.get_agent_detail(client.agent_id))["rooms"]
    open_rooms = [r for r in rooms if r["room_name"].lstrip("#").startswith(prefix)]
    open_rooms = [r for r in open_rooms if not r.get("archived")] or open_rooms
    if not open_rooms:
        raise SystemExit(f"No {prefix}* room for this gate")
    return open_rooms[-1]


async def watch(args):
    state = json.loads(Path("data/day0-state.json").read_text())
    me = state[args.person]
    client = SwitchClient(os.environ["SWITCH_URL"], me["id"], me["api_key"])

    async def drain():
        async for _ in client.events():
            pass

    task = asyncio.create_task(drain())
    try:
        await asyncio.wait_for(client.ready.wait(), 20)
        room = await newest_room(client, args.prefix)
        print(f"\033[1m# {room['room_name'].lstrip('#')}\033[0m  (agent-only room)\n")
        seen, joined, spoke = set(), {}, set()
        width = max(40, os.get_terminal_size().columns - 22) if sys.stdout.isatty() else 100
        while True:
            context = await client.read_context(room_id=room["room_id"], limit=100)
            messages = [m for t in context["threads"] for m in (t["root"], *t.get("replies", []))]
            for m in sorted(messages, key=lambda m: m.get("timestamp", 0)):
                if m["id"] in seen:
                    continue
                seen.add(m["id"])
                name, ts = m.get("sender_name", "?"), m.get("timestamp", 0)
                if m.get("kind") == "room_join":
                    joined[name] = ts
                    if not args.all:
                        continue
                greeting = name not in spoke and ts - joined.get(name, -10_000) < 2_000
                if m.get("kind") == "message":
                    spoke.add(name)
                if greeting and not args.all:
                    continue
                when = datetime.fromtimestamp(ts / 1000).strftime("%H:%M:%S")
                body = textwrap.fill(m.get("body", ""), width, subsequent_indent=" " * 22)
                print(f"\033[2m{when}\033[0m {colour(name)}{name:>13}{RESET}  {body}\n", flush=True)
            if args.once:
                return
            await asyncio.sleep(args.every)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await client.aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--person", default="om", help="whose gate reads the room")
    parser.add_argument("--prefix", default="dm-")
    parser.add_argument("--every", type=float, default=2.0)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--once", action="store_true")
    try:
        asyncio.run(watch(parser.parse_args()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
