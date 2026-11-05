"""Bounded Switch access shared by the CLI and future MCP tools."""

from trustnet.room_pool import wait_until_live
from trustnet.switch_client import SwitchError
from trustnet.tn.personal import session


async def operate(person, room, text=None):
    async with session(person) as client:
        detail = await client.get_agent_detail(client.agent_id)
        rooms = [r for r in detail["rooms"] if room in (r["room_id"], r["room_name"])]
        if not rooms or not rooms[0]["room_name"].startswith("dm-") or rooms[0].get("archived"):
            raise SwitchError("An active DM membership is required")
        rid = rooms[0]["room_id"]
        await client.connect_to_room(rid)
        if text is not None:
            await wait_until_live(client, rid, text)
            return await client.post_message(text)
        return await client.read_context(room_id=rid)
