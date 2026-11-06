"""The gate handshake: a gate works only with peer gates that said a compatible hello.

Ways it could fail, each covered below:
- a peer gate opens a planning room without saying hello (an old or foreign gate);
- a peer speaks a different major version of the protocol;
- something other than the friend's gate, or a hello outside the gates' connection
  room, tries to register a peer;
- a peer that never said hello forwards a proposal into a planning room.
The two-gate flow (hello both ways, then the room opens) is the existing DM path.
"""

import shutil

import pytest
from fakes.fake_switch import FakeSwitch

from trustnet.gate import commands as c
from trustnet.gate import consent, dm, handshake, relay
from trustnet.gate.policy import Identity, authorize
from trustnet.gate.runtime import Gate
from trustnet.switch_client import Event


async def two_gates(tmp_path, monkeypatch):
    for person in ("om", "rahul"):
        shutil.copytree("examples/" + person, tmp_path / person)
    monkeypatch.setenv("TN_DATA_DIR", str(tmp_path))
    switch = FakeSwitch()
    clients = {p: switch.client(p + "-gate", p) for p in ("om", "rahul")}
    for p in clients:
        switch.client(dm.main_agent(p), p)
    ids = {p: Identity.user(p) for p in clients}
    ids.update({n: Identity.agent(n, a["owner_id"]) for n, a in switch.agents.items()})
    homes = {}
    for p, client in clients.items():
        homes[p] = (await client.create_room(p + "-home", "", [p + "-gate"], internal_only=True))[
            "room_id"
        ]

    async def home(person, text, *, client):
        await client.connect_to_room(homes[person])
        await client.post_message(text)

    monkeypatch.setattr(relay, "post_home", home)
    monkeypatch.setattr("trustnet.gate.watch.post_home", home)
    gates = {p: Gate(p, cl, lambda: ids) for p, cl in clients.items()}
    return switch, gates, homes


def conn_room(switch):
    return next(r for r in switch.rooms.values() if r["name"] == "conn-om-rahul")


async def deliver(switch, room, sender, gate, start=0):
    """Hand ``gate`` every message ``sender`` posted in ``room`` from index ``start``."""
    for message in list(room["messages"])[start:]:
        if message["sender"] == sender:
            await gate.handle(Event(room["id"], sender, "agent", message["body"], True))


def bodies(switch, room_id):
    return [m["body"] for m in switch.rooms[room_id]["messages"]]


async def test_planning_opens_after_hellos_both_ways(tmp_path, monkeypatch):
    switch, gates, homes = await two_gates(tmp_path, monkeypatch)
    await gates["om"].handle(
        Event(homes["om"], "om", "user", '@om-gate dm rahul "Sunday bowling"', True)
    )
    conn = conn_room(switch)
    assert conn["messages"][0]["body"].startswith("@rahul-gate hello trust-network/1 ")
    await deliver(switch, conn, "om-gate", gates["rahul"])
    assert any(m["body"].startswith("@om-gate hello trust-network/1 ") for m in conn["messages"])
    await deliver(switch, conn, "rahul-gate", gates["om"])

    assert any(r["name"].startswith("dm-om-rahul-") for r in switch.rooms.values())
    assert "Share card" in bodies(switch, homes["rahul"])[-1]
    assert handshake.peer("om", "rahul")["protocol"] == "trust-network/1"


async def test_join_without_hello_is_refused(tmp_path, monkeypatch):
    switch, gates, homes = await two_gates(tmp_path, monkeypatch)
    await gates["om"].handle(
        Event(homes["om"], "om", "user", '@om-gate dm rahul "Sunday bowling"', True)
    )
    conn = conn_room(switch)
    join = next(m["body"] for m in conn["messages"] if " join-dm " in m["body"])
    await gates["rahul"].handle(Event(conn["id"], "om-gate", "agent", join, True))

    assert not (tmp_path / "rahul" / "share-cards").exists()
    assert (
        "rahul-hermes"
        not in next(r for r in switch.rooms.values() if r["name"].startswith("dm-"))["members"]
    )
    assert "hasn't said hello" in bodies(switch, homes["rahul"])[-1]
    # The refusal in the connection room is plain text: addressing om-gate would
    # read as a malformed command there.
    assert not bodies(switch, conn["id"])[-1].startswith("@")


async def test_other_major_version_is_refused(tmp_path, monkeypatch):
    switch, gates, homes = await two_gates(tmp_path, monkeypatch)
    await gates["om"].handle(
        Event(homes["om"], "om", "user", '@om-gate dm rahul "Sunday bowling"', True)
    )
    conn = conn_room(switch)
    join = next(m["body"] for m in conn["messages"] if " join-dm " in m["body"])
    hello = "@rahul-gate hello trust-network/2 free,ask,propose,consent,join-dm"
    await gates["rahul"].handle(Event(conn["id"], "om-gate", "agent", hello, True))
    await gates["rahul"].handle(Event(conn["id"], "om-gate", "agent", join, True))

    assert not (tmp_path / "rahul" / "share-cards").exists()
    assert "trust-network/2" in bodies(switch, homes["rahul"])[-1]


@pytest.mark.parametrize(
    "sender, room, allowed",
    [
        (Identity.agent("rahul-gate", "rahul"), "conn-om-rahul", True),
        (Identity.agent("rahul-hermes", "rahul"), "conn-om-rahul", False),
        (Identity.user("rahul"), "conn-om-rahul", False),
        (Identity.agent("rahul-gate", "rahul"), "dm-om-rahul-sun", False),
        (Identity.agent("rahul-gate", "rahul"), "conn-om-priya", False),
    ],
)
def test_hello_only_from_the_friends_gate_in_the_connection_room(sender, room, allowed):
    assert bool(authorize("hello", sender, "om", "via-agent", room_name=room)) == allowed


def test_hello_parses_to_a_fixed_form():
    command = c.parse("@om-gate hello trust-network/1 free,ask,propose")
    assert isinstance(command, c.Hello)
    assert (command.protocol, command.major) == ("trust-network/1", 1)
    assert command.capabilities == ("free", "ask", "propose")
    # Anything else stays what it was before the handshake: an unknown command.
    for other in ("@om-gate hello", "@om-gate hello there", "@om-gate hello trust-network/x"):
        assert isinstance(c.parse(other), c.Unknown)


async def test_forwarded_proposal_needs_the_peers_hello(tmp_path, monkeypatch):
    switch, gates, homes = await two_gates(tmp_path, monkeypatch)
    await gates["om"].handle(
        Event(homes["om"], "om", "user", '@om-gate dm rahul "Sunday bowling"', True)
    )
    conn = conn_room(switch)
    await deliver(switch, conn, "om-gate", gates["rahul"])  # rahul now knows om, not vice versa
    room = next(r for r in switch.rooms.values() if r["name"].startswith("dm-"))
    forwarded = '@om-gate propose P1 2026-11-08T21:00 2h "Bowling" @ "Smaaash"'
    await gates["om"].handle(Event(room["id"], "rahul-gate", "agent", forwarded, True))
    assert "P1" not in consent.load("om")

    await deliver(switch, conn, "rahul-gate", gates["om"])
    await gates["om"].handle(Event(room["id"], "rahul-gate", "agent", forwarded, True))
    assert consent.load("om")["P1"]["status"] == "pending"
