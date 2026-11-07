"""Main-agent DM setup and private share-card delivery."""

import json
import re
from datetime import timedelta

from trustnet.gate import handshake, relay
from trustnet.gate.brief import write_brief
from trustnet.gate.facts import load_profile, load_trust, resolve_data_dir
from trustnet.gate.policy import room_level
from trustnet.gate.watch import ConversationWatch


def main_agent(person):
    return person + relay.AGENT_SUFFIX


async def setup(gate, friend, goal, room=None):
    client, person = gate.client, gate.person
    trust = load_trust(person)
    if trust.level_for(friend) is None:
        return
    pair = "-".join(sorted((person, friend)))
    opened_by = person if room is None else friend
    if room is None:
        detail = await client.get_agent_detail(client.agent_id)
        # Reuse an open, unarchived, not-limit-closed planning room with this
        # friend instead of opening another: an agent that calls dm() repeatedly
        # with slightly different goal wording must not sprawl one room per call.
        existing = next(
            (
                r["room_id"]
                for r in detail.get("rooms", [])
                if r["room_name"].startswith(f"dm-{pair}-")
                and not r.get("archived")
                and not (r["room_id"] in gate.watches and gate.watches[r["room_id"]].closed)
            ),
            None,
        )
        if existing is not None:
            card = resolve_data_dir(person) / "share-cards" / f"{existing}.json"
            if card.exists():
                # This person's own request now drives the planning in this room.
                data = json.loads(card.read_text())
                data["opened_by"] = person
                card.write_text(json.dumps(data))
            await relay.post_home(
                person, f"Planning continues with {friend} in {existing}", client=client
            )
            return
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
        slug = re.sub("[^a-z0-9]+", "-", goal.text.lower()).strip("-")[:32] or "plan"
        names = {r["room_name"] for r in detail.get("rooms", [])}
        name = f"dm-{pair}-{slug}"
        base, suffix = name, 2
        while name in names:
            name = f"{base}-{suffix}"
            suffix += 1
        result = await client.create_room(
            name, "Main agents planning", [person + "-gate"], internal_only=True
        )
        room = result.get("room_id", result.get("id"))
        await client.connect_to_room(room)
        await client.invite_agent_to_room(room, friend + "-gate")
        await handshake.say(gate, conn, friend)
        await client.connect_to_room(conn)
        await client.post_message(f"@{friend}-gate join-dm {room} {goal}")
    else:
        detail = await client.get_room_detail(room)
        if not detail.get("name", detail.get("room_name", "")).startswith(f"dm-{pair}-"):
            return
        if detail.get("archived"):
            return
    if room in gate.watches:
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
    await client.invite_agent_to_room(room, main_agent(person))
    today = gate._now().date()
    card = write_brief(
        load_profile(person), trust, friend, room, goal, (today, today + timedelta(days=7))
    )
    directory = resolve_data_dir(person) / "share-cards"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / f"{room}.json"
    path.touch(mode=0o600)
    path.write_text(
        json.dumps(
            {
                "room": room,
                "friend": friend,
                "opened_by": opened_by,
                "agent": main_agent(person),
                "text": card.text,
                "created_at": gate._now().isoformat(),
            }
        )
    )
    gate.watches[room] = ConversationWatch(room, person, client, persistent=True)
    await relay.post_home(person, f"Planning with {friend} in {room}", client=client)
    await relay.post_home(person, card.text, client=client)
    await relay.ensure_home(person, client, agent_name=main_agent(person))
