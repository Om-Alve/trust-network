"""Bounded Switch access shared by the CLI and future MCP tools."""

import asyncio
import json
import os
from pathlib import Path

from trustnet.gate.dm import main_agent
from trustnet.switch_client import SwitchClient, SwitchError


async def operate(person, room, text=None):
    # Credentials stay outside the data exposed to a main agent.
    directory = Path("data/main-agents")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / f"{person}.json"
    url = os.environ["SWITCH_URL"]
    if path.exists():
        state = json.loads(path.read_text())
        client = SwitchClient(url, state["id"], state["api_key"])
    else:
        client = await SwitchClient.register(
            url, os.environ[f"{person.upper()}_GATE_KEY"], main_agent(person), agent_type="codex"
        )
        path.touch(mode=0o600)
        path.write_text(json.dumps({"id": client.agent_id, "api_key": client.api_key}))

    async def drain():
        async for _ in client.events():
            pass

    stream = asyncio.create_task(drain())
    try:
        await asyncio.wait_for(client.ready.wait(), 15)
        detail = await client.get_agent_detail(client.agent_id)
        rooms = [r for r in detail["rooms"] if room in (r["room_id"], r["room_name"])]
        if not rooms or not rooms[0]["room_name"].startswith("dm-") or rooms[0].get("archived"):
            raise SwitchError("An active DM membership is required")
        rid = rooms[0]["room_id"]
        await client.connect_to_room(rid)
        if text is not None:
            return await client.post_message(text)
        return await client.read_context(room_id=rid)
    finally:
        stream.cancel()
        await asyncio.gather(stream, return_exceptions=True)
        await client.aclose()
