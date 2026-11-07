"""Gate-only fact-request rooms: a quiet ``ask`` without a planning DM.

A facts request must never look like a planning DM. The asker's gate opens a
dedicated ``ask-<a>-<b>-<n>`` room holding only the asker's gate, the asker's own
main agent and the friend's gate, then invites the friend's gate with the
``join-ask <room>`` gate-to-gate verb. The friend's gate verifies the invitation
exactly like ``join-dm`` — sender, room name, fresh membership and the room's
trust level — and then answers ``ask`` and ``free`` there at the room level. It
never invites its own agent, never writes a share card and never posts a
planning notice home, so the recipient's agent cannot see that a friend is
asking about their facts.
"""

from trustnet.gate import handshake
from trustnet.gate.dm import main_agent
from trustnet.gate.facts import load_trust
from trustnet.gate.policy import room_level

__all__ = ["join", "setup"]


async def setup(gate, friend):
    """Open a fact-request room with ``friend`` from the asker's gate.

    Returns the new room id, or ``None`` when the friend is no longer trusted.
    The room holds the asker's gate, the asker's main agent and the friend's
    gate; the friend's gate is told to join via ``join-ask`` in the connection
    room, immediately after the usual hello.
    """
    client, person = gate.client, gate.person
    trust = load_trust(person)
    if trust.level_for(friend) is None:
        return None
    pair = "-".join(sorted((person, friend)))
    detail = await client.get_agent_detail(client.agent_id)
    conn = next(
        (
            r["room_id"]
            for r in detail.get("rooms", [])
            if r["room_name"] == "conn-" + pair and not r.get("archived")
        ),
        None,
    )
    if conn is None:
        result = await client.create_room(
            "conn-" + pair, "Gate connection", [person + "-gate"], internal_only=True
        )
        conn = result.get("room_id", result.get("id"))
        await client.connect_to_room(conn)
        await client.invite_agent_to_room(conn, friend + "-gate")
    names = {r["room_name"] for r in detail.get("rooms", [])}
    number = 1
    name = f"ask-{pair}-{number}"
    while name in names:
        number += 1
        name = f"ask-{pair}-{number}"
    result = await client.create_room(name, "Fact request", [person + "-gate"], internal_only=True)
    room = result.get("room_id", result.get("id"))
    await client.connect_to_room(room)
    await client.invite_agent_to_room(room, friend + "-gate")
    await client.invite_agent_to_room(room, main_agent(person))
    await handshake.say(gate, conn, friend)
    await client.connect_to_room(conn)
    await client.post_message(f"@{friend}-gate join-ask {room}")
    return room


async def join(gate, friend, room):
    """Verify and join a fact-request room, without the DM setup that leaks.

    Mirrors ``dm.setup``'s receiving verification: the sender was already checked
    by policy and the handshake, the room name must be ``ask-<pair>-*``, and the
    membership and level come from fresh Switch data. Unlike ``dm.setup`` it never
    invites the owner's agent, writes no share card and posts nothing home.
    """
    client, person = gate.client, gate.person
    trust = load_trust(person)
    if trust.level_for(friend) is None:
        return
    pair = "-".join(sorted((person, friend)))
    detail = await client.get_room_detail(room)
    if not detail.get("name", detail.get("room_name", "")).startswith(f"ask-{pair}-"):
        return
    if detail.get("archived"):
        return
    await client.connect_to_room(room)
    identities = gate.identities()
    members = []
    for participant in await client.list_participants():
        identity = identities.get(participant["id"])
        if identity is None:
            return
        if participant["type"] == "agent":
            agent = await client.get_agent_detail(participant["id"])
            owner = identities.get(agent.get("owner_id"))
            if owner is None or owner.id != identity.owner_id:
                return
        members.append(identity)
    if room_level(person, members, trust) != trust.level_for(friend):
        return
