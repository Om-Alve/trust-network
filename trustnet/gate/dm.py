"""Main-agent DM setup and private share-card delivery."""

import json
import re
from datetime import timedelta

from trustnet.gate import relay
from trustnet.gate.brief import write_brief
from trustnet.gate.envoy import ConversationWatch
from trustnet.gate.facts import load_profile, load_trust, resolve_data_dir
from trustnet.gate.policy import room_level


def main_agent(person):
    return person + "-hermes"


async def setup(gate, friend, goal, room=None):
    client, person = gate.client, gate.person
    trust = load_trust(person)
    if trust.level_for(friend) is None:
        return
    pair = "-".join(sorted((person, friend)))
    if room is None:
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
    text = card.text.replace("envoy", "main agent")
    text = text.replace(
        "This brief is your only source about", "This card lists permitted disclosures about"
    )
    start = text.find("You have no files, no shell")
    end = text.find("\n", start)
    if start >= 0:
        text = text[:start] + text[end:]
    text = "Share card: guidance only; your existing knowledge is not confined.\n" + text
    directory = resolve_data_dir(person) / "share-cards"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / f"{room}.json"
    path.touch(mode=0o600)
    path.write_text(
        json.dumps(
            {
                "room": room,
                "friend": friend,
                "agent": main_agent(person),
                "text": text,
                "created_at": gate._now().isoformat(),
            }
        )
    )
    gate.watches[room] = ConversationWatch(room, person, client)
    await relay.post_home(person, f"Planning with {friend} in {room}", client=client)
    await relay.post_home(person, text, client=client)
    own_detail = await client.get_agent_detail(client.agent_id)
    home = next(
        r["room_id"]
        for r in own_detail["rooms"]
        if r["room_name"].lstrip("#") == person + "-home" and not r.get("archived")
    )
    await client.invite_agent_to_room(home, main_agent(person))
