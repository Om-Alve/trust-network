import shutil

import pytest
from fakes.fake_switch import FakeSwitch

from trustnet.gate import ledger, relay
from trustnet.gate.policy import Identity
from trustnet.gate.runtime import Gate
from trustnet.switch_client import Event


async def _no_home(person, text, *, client):
    """Keep the pre-phase-21 gate tests free of home-room traffic."""
    return None


@pytest.mark.parametrize(
    "peer,level", [("rahul", "close"), ("priya", "friend"), ("stranger", None), ("om", "self")]
)
async def test_gate_disclosures(tmp_path, monkeypatch, peer, level):
    shutil.copytree("examples/om", tmp_path / "om")
    monkeypatch.setenv("TN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(relay, "post_home", _no_home)
    switch = FakeSwitch()
    client = switch.client("om-gate", "om")
    switch.client(peer + "-agent", peer)
    result = await client.create_room("probe", "", ["om-gate", peer + "-agent"], internal_only=True)
    rid = result["room_id"]
    ids = {
        "om": Identity.user("om"),
        "om-gate": Identity.agent("om-gate", "om"),
        peer: Identity.user(peer),
        peer + "-agent": Identity.agent(peer + "-agent", peer),
    }
    gate = Gate("om", client, lambda: ids)
    await gate.handle(
        Event(rid, peer + "-agent", "unknown", "@om-gate ask diet wishlist address", True)
    )
    messages = switch.rooms[rid]["messages"]
    if level is None:
        assert messages == []
        return
    text = messages[-1]["body"]
    assert "diet: vegetarian" in text.lower()
    assert ("wishlist: not shared" in text) == (level == "friend")
    assert ("address: not shared" in text) == (level != "self")
    fields = {e.field for e in ledger.read("om")}
    assert fields == (
        {"diet"}
        if level == "friend"
        else {"diet", "wishlist"}
        if level == "close"
        else {"diet", "wishlist", "address"}
    )
    before = len(messages)
    await gate.handle(Event(rid, peer + "-agent", "user", "@om-gate trust stranger close", True))
    if level == "self":
        # The owner's own agent is not another side: no refusal, no note.
        assert len(messages) == before
    else:
        # Phase 21: an owner-only command from another side is refused, not ignored.
        assert len(messages) == before + 1
        assert messages[-1]["body"] == "Not allowed."


async def test_unknown_identity_and_unaddressed_are_silent(tmp_path, monkeypatch):
    shutil.copytree("examples/om", tmp_path / "om")
    monkeypatch.setenv("TN_DATA_DIR", str(tmp_path))
    switch = FakeSwitch()
    client = switch.client("om-gate", "om")
    rid = (await client.create_room("home", "", ["om-gate"], internal_only=True))["room_id"]
    ids = {"om": Identity.user("om"), "om-gate": Identity.agent("om-gate", "om")}
    gate = Gate("om", client, lambda: ids)
    for sender, text, addressed in [
        ("forged", "@om-gate ask address", True),
        ("om", "@om-gate ask address", False),
    ]:
        await gate.handle(Event(rid, sender, "user", text, addressed))
    assert switch.rooms[rid]["messages"] == []
    await gate.handle(Event(rid, "om", "user", "@om-gate consent P1 yes direct", True))
    assert [m["body"] for m in switch.rooms[rid]["messages"]] == [
        "Not allowed: gate relay requires the matching connection."
    ]
    await gate.handle(Event(rid, "om", "unknown", "@om-gate nonsense", True))
    assert "Commands:" in switch.rooms[rid]["messages"][-1]["body"]


async def test_owner_calendar_and_views(tmp_path, monkeypatch):
    shutil.copytree("examples/om", tmp_path / "om")
    monkeypatch.setenv("TN_DATA_DIR", str(tmp_path))
    switch = FakeSwitch()
    client = switch.client("om-gate", "om")
    rid = (await client.create_room("home", "", ["om-gate"], internal_only=True))["room_id"]
    ids = {"om": Identity.user("om"), "om-gate": Identity.agent("om-gate", "om")}
    gate = Gate("om", client, lambda: ids)
    for text in ["free 2026-11-08..2026-11-09", "view-as priya", "ledger", "trust priya close"]:
        await gate.handle(Event(rid, "om", "unknown", "@om-gate " + text, True))
    messages = [m["body"] for m in switch.rooms[rid]["messages"]]
    assert "Family video call" in messages[0]
    assert "wishlist" in messages[1] and "not shared at this level" in messages[1]
    assert "calendar" in messages[2]
    assert messages[3] == "Trust for priya: close"
