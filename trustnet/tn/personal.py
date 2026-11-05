"""Hermes operations shared by CLI and MCP; credentials never leave this module."""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from trustnet.gate.commands import Answer, Dm, Quoted
from trustnet.gate.dm import main_agent
from trustnet.gate.facts import resolve_data_dir
from trustnet.switch_client import SwitchClient, SwitchError


@asynccontextmanager
async def session(person):
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
        yield client
    finally:
        stream.cancel()
        await asyncio.gather(stream, return_exceptions=True)
        await client.aclose()


async def home(person, client):
    detail = await client.get_agent_detail(client.agent_id)
    rooms = [
        r
        for r in detail["rooms"]
        if r["room_name"].lstrip("#") == person + "-home" and not r.get("archived")
    ]
    if not rooms:
        raise SwitchError(
            "Home membership is required; invite the registered Hermes identity first"
        )
    return rooms[0]["room_id"]


async def inbox(person):
    """Return unread home threads; persist consumed message IDs per person."""
    path = resolve_data_dir(person) / "inbox-cursor.json"
    seen = set(json.loads(path.read_text())) if path.exists() else set()
    async with session(person) as client:
        room = await home(person, client)
        context = await client.read_context(room_id=room, limit=200)
    threads = context.get("threads", [])
    unread = [t for t in threads if t["root"]["id"] not in seen]
    seen.update(t["root"]["id"] for t in unread)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600)
    path.write_text(json.dumps(sorted(seen)))
    return {"room": room, "threads": unread}


async def answer(person, id, text):
    """Send an answer as the registered Hermes; the gate authenticates consent."""
    command = Answer(reference=id, text=Quoted(text))
    async with session(person) as client:
        await client.connect_to_room(await home(person, client))
        return await client.post_message(
            f"@{person}-gate answer {command.reference} {json.dumps(text, ensure_ascii=False)}"
        )


async def dm(person, friend, goal):
    """Request a DM through the owner's gate from their home membership."""
    command = Dm(person=friend, goal=Quoted(goal))
    async with session(person) as client:
        await client.connect_to_room(await home(person, client))
        return await client.post_message(f"@{person}-gate dm {command.person} {command.goal}")


async def dm_read(person, room):
    from trustnet.tn.dm import operate

    return await operate(person, room)


async def dm_post(person, room, text):
    from trustnet.tn.dm import operate

    return await operate(person, room, text)
