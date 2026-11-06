"""Home-room delivery and gift-room detection for surprise mode."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

#: Gift rooms are named ``gift-<asker>-<for>-<slug>`` (PLAN.md §2).
GIFT_ROOM_PREFIX: Final = "gift-"


async def post_home(person, text, *, client):
    detail = await client.get_agent_detail(client.agent_id)
    name = person + "-home"
    room = next(
        (
            r["room_id"]
            for r in detail["rooms"]
            if r["room_name"].lstrip("#") == name and not r.get("archived")
        ),
        None,
    )
    if room is None:
        if person == "om":
            raise RuntimeError("Create om-home with the Discord template first")
        result = await client.create_room(
            name, "Trust network home", [person + "-gate"], internal_only=True
        )
        room = result.get("room_id", result.get("id"))
    await client.connect_to_room(room)
    return await client.post_message(text)


def is_gift_room(room: str | Mapping[str, Any]) -> bool:
    """Recognize a gift flag or the gift- room-name prefix."""
    if isinstance(room, Mapping):
        if room.get("gift") is True:
            return True
        name = room.get("name") or room.get("room_name") or ""
    else:
        name = room
    return isinstance(name, str) and name.strip().lower().startswith(GIFT_ROOM_PREFIX)
