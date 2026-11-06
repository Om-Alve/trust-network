"""The gate handshake: ``hello trust-network/<major> <capabilities>``.

Before two gates plan anything, each tells the other which protocol version it
speaks and which gate-to-gate commands it accepts. The opening gate says hello in
the gates' connection room right before ``join-dm``; the other records it and says
hello back once. A gate refuses to join a planning room opened by, or take a
forwarded proposal from, a peer gate that hasn't said a compatible hello (same
major version). Peers are remembered per person in ``peers.json``.

Who may say hello is policy (``authorize("hello", …)``): only the friend's own gate,
and only in their ``conn-<pair>`` room.
"""

import json
from datetime import datetime, timezone

from trustnet.gate import commands as c
from trustnet.gate.facts import resolve_data_dir

PROTOCOL = "trust-network/1"
MAJOR = 1
#: Gate-to-gate commands this gate accepts from a peer gate.
CAPABILITIES = (
    "hello",
    "join-dm",
    "free",
    "ask",
    "propose",
    "consent",
    "ask-around",
    "gift-ideas",
    "claim",
)


def line(friend: str) -> str:
    return f"@{friend}-gate hello {PROTOCOL} {','.join(CAPABILITIES)}"


def _path(person):
    return resolve_data_dir(person) / "peers.json"


def load(person) -> dict:
    path = _path(person)
    return json.loads(path.read_text()) if path.exists() else {}


def peer(person, friend) -> dict | None:
    return load(person).get(friend)


def problem(person, friend) -> str | None:
    """Why this gate can't work with ``friend``'s gate yet, or None if it can."""
    known = peer(person, friend)
    if known is None:
        return f"{friend}'s gate hasn't said hello (no {PROTOCOL} handshake)"
    if known["major"] != MAJOR:
        return f"{friend}'s gate speaks {known['protocol']}; this gate speaks {PROTOCOL}"
    return None


def _record(person, friend, command: c.Hello, room) -> None:
    state = load(person)
    state[friend] = {
        "protocol": command.protocol,
        "major": command.major,
        "capabilities": list(command.capabilities),
        "room": room,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    path = _path(person)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.touch(mode=0o600)
    temp.write_text(json.dumps(state))
    temp.replace(path)


async def say(gate, room, friend) -> None:
    """Post this gate's hello to ``friend``'s gate in ``room`` (the connection room)."""
    gate.hellos.add(room)
    await gate.client.connect_to_room(room)
    await gate.client.post_message(line(friend))


async def handle(gate, event, command: c.Hello, sender) -> None:
    _record(gate.person, sender.person, command, event.room_id)
    if event.room_id not in gate.hellos:
        await say(gate, event.room_id, sender.person)
