"""Home-room delivery, first-contact bootstrap and gift-room detection.

A person's home is a private, internal Switch room holding the person, their
gate and their own main agent. It is created on demand by whichever side needs
it first: the gate at startup or before a home post, the personal agent on its
first tool request. Both sides accept only a home whose agent members belong to
the person, so a look-alike room owned by somebody else is never posted into.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Final

from trustnet.switch_client import SwitchError

LOG = logging.getLogger(__name__)

#: Gift rooms are named ``gift-<asker>-<for>-<slug>`` (the original design §2).
GIFT_ROOM_PREFIX: Final = "gift-"

HOME_SUFFIX: Final = "-home"

#: The fixed personal-agent name authorization assumes (``gate.dm.main_agent``).
#: Supporting several registered agents per person needs an explicit identity
#: registry and per-agent consent permissions; first contact does not (TN-06).
AGENT_SUFFIX: Final = "-hermes"

__all__ = [
    "AGENT_SUFFIX",
    "GIFT_ROOM_PREFIX",
    "HOME_SUFFIX",
    "ensure_home",
    "find_home",
    "home_name",
    "is_gift_room",
    "post_home",
]


def home_name(person: str) -> str:
    return person + HOME_SUFFIX


async def _inspect(client, room_id, *, owner_id, own_names):
    """Return the room's agent names and any agent that belongs to someone else."""
    await client.connect_to_room(room_id)
    participants = await client.list_participants()
    names = {p.get("name") or p["id"] for p in participants if p.get("type") == "agent"}
    foreign = []
    for participant in participants:
        if participant.get("type") != "agent" or participant.get("id") == client.agent_id:
            continue
        name = participant.get("name") or participant["id"]
        try:
            reported = (await client.get_agent_detail(participant["id"])).get("owner_id")
        except (SwitchError, ValueError):
            foreign.append(name)  # an unreadable owner is not ours: fail closed
            continue
        if reported is not None and owner_id is not None:
            if reported != owner_id:
                foreign.append(name)
        elif name not in own_names:
            foreign.append(name)
    return names, foreign


async def find_home(client, person, *, own_names, agent_name):
    """Classify the homes the caller can see.

    Returns ``(chosen, safe, blocked)``. ``safe`` is a list of ``(room_id,
    agent_names)`` for rooms whose agents all share the caller's Switch owner,
    ``blocked`` pairs a room with the foreign agent names found in it, and
    ``chosen`` prefers a safe home that already holds ``agent_name``.
    """
    detail = await client.get_agent_detail(client.agent_id)
    owner_id = detail.get("owner_id")
    rooms = [
        room
        for room in detail.get("rooms", [])
        if room["room_name"].lstrip("#") == home_name(person) and not room.get("archived")
    ]
    safe, blocked = [], []
    for room in rooms:
        names, foreign = await _inspect(
            client, room["room_id"], owner_id=owner_id, own_names=own_names
        )
        if foreign:
            blocked.append((room["room_id"], foreign))
        else:
            safe.append((room["room_id"], names))
    chosen = next((room for room, names in safe if agent_name in names), None)
    if chosen is None and safe:
        chosen = safe[0][0]
    return chosen, safe, blocked


async def ensure_home(person, client, *, agent_name=None):
    """Return the person's home, creating it and inviting the main agent.

    The gate calls this at startup and before every home post, so it is
    idempotent. A home created before the main agent registered is superseded
    once a shared home exists; the empty stub is archived so only one active
    home remains.
    """
    agent_name = agent_name or person + AGENT_SUFFIX
    chosen, safe, blocked = await find_home(
        client, person, own_names={person + "-gate", agent_name}, agent_name=agent_name
    )
    for room, foreign in blocked:
        LOG.warning(
            "ignoring room=%s for %s: another owner's agents %s", room, person, ",".join(foreign)
        )
    if chosen is None:
        result = await client.create_room(
            home_name(person),
            "Trust network home",
            [person + "-gate"],
            internal_only=True,
            read_visibility="private",
            write_visibility="private",
        )
        chosen = result.get("room_id", result.get("id"))
        names = {person + "-gate"}
    else:
        names = next(names for room, names in safe if room == chosen)
    if agent_name not in names:
        try:
            await client.invite_agent_to_room(chosen, agent_name)
        except (SwitchError, ValueError):
            LOG.info(
                "home for %s exists before %s registered; it joins on first use",
                person,
                agent_name,
            )
    for room, names in safe:
        if room != chosen and names <= {person + "-gate"}:
            await _archive_if_empty(client, room)
    await client.connect_to_room(chosen)
    return chosen


async def _archive_if_empty(client, room):
    """Retire a gate-only home stub left by a gate that started before the agent."""
    try:
        context = await client.read_context(room_id=room, limit=1)
    except (SwitchError, ValueError):
        return
    if context.get("threads"):
        return
    try:
        await client.archive_room(room)
        LOG.info("archived empty home stub room=%s", room)
    except (SwitchError, ValueError):
        return


async def post_home(person, text, *, client):
    room = await ensure_home(person, client)
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
