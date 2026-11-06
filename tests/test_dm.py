import shutil

import pytest
from fakes.fake_switch import FakeSwitch

from trustnet.gate import dm, relay
from trustnet.gate.policy import Identity, authorize
from trustnet.gate.runtime import Gate
from trustnet.gate.watch import MAX_TURNS
from trustnet.switch_client import Event


@pytest.mark.parametrize("command", ["join-dm", "consent"])
async def test_gate_relay_identity_and_room(command):
    for sender, room, allowed in [
        (Identity.agent("rahul-gate", "rahul"), "conn-om-rahul", True),
        (Identity.agent("rahul-agent", "rahul"), "conn-om-rahul", False),
        (Identity.user("rahul"), "conn-om-rahul", False),
        (Identity.agent("rahul-gate", "rahul"), "dm-om-rahul-sun", command == "consent"),
    ]:
        assert bool(authorize(command, sender, "om", "via-agent", room_name=room)) == allowed


async def test_dm_setup_private_cards_and_limits(tmp_path, monkeypatch):
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
    # ConversationWatch imports the relay function directly.
    monkeypatch.setattr("trustnet.gate.watch.post_home", home)
    gates = {p: Gate(p, c, lambda: ids) for p, c in clients.items()}
    await gates["om"].handle(
        Event(homes["om"], "om", "user", '@om-gate dm rahul "Sunday bowling"', True)
    )
    conn = next(r for r in switch.rooms.values() if r["name"] == "conn-om-rahul")
    for message in list(conn["messages"]):  # hello, then join-dm
        if message["sender"] == "om-gate":
            await gates["rahul"].handle(
                Event(conn["id"], "om-gate", "agent", message["body"], True)
            )
    room = next(r for r in switch.rooms.values() if r["name"].startswith("dm-"))
    assert {"om-gate", "rahul-gate", "om-hermes", "rahul-hermes"} <= room["members"]
    assert room["messages"] == []
    assert len(list(tmp_path.glob("*/share-cards/*.json"))) == 2
    assert "Share card" in switch.rooms[homes["rahul"]]["messages"][-1]["body"]
    for i in range(MAX_TURNS):
        await gates["om"].handle(Event(room["id"], "om-hermes", "agent", f"Plan {i}", False))
    assert room["archived"]
    before = len(room["messages"])
    await gates["om"].handle(Event(room["id"], "rahul-agent", "agent", "@om-gate ask diet", True))
    assert len(room["messages"]) == before
    assert f"{MAX_TURNS} agent turns" in switch.rooms[homes["om"]]["messages"][-1]["body"]
