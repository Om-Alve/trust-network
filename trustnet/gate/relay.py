"""Home-room relays and the gift-room hook.

``post_home`` reaches the owner's ``<person>-home`` room through the gate's own
memberships. ``is_gift_room`` is the surprise-mode seam: phase 19 owns gift rooms
and may replace this hook, but the gate already refuses to post overreach notes
home from a room it recognises as a gift room.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

#: Gift rooms are named ``gift-<asker>-<for>-<slug>`` (PLAN.md §2).
GIFT_ROOM_PREFIX: Final = "gift-"


async def post_home(person, text, *, client):
    detail = await client.get_agent_detail(client.agent_id)
    name = person + "-home"
    room = next(
        (r["room_id"] for r in detail["rooms"] if r["room_name"] == name and not r.get("archived")),
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
    """Whether ``room`` is a gift room, where surprise mode forbids home posts.

    Accepts a room name or a ``get_room_detail`` mapping, so the same hook works
    from the runtime and from tests. A room is a gift room when its detail sets
    ``gift: true`` (the flag phase 19 can add) or when its name starts with
    ``gift-`` (the name convention PLAN.md §2 already uses). Replace this hook
    when phase 19 stores gift-ness somewhere else.
    """
    if isinstance(room, Mapping):
        if room.get("gift") is True:
            return True
        name = room.get("name") or room.get("room_name") or ""
    else:
        name = room
    return isinstance(name, str) and name.strip().lower().startswith(GIFT_ROOM_PREFIX)
