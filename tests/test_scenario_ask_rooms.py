"""End-to-end fact-request rooms and DM room reuse over FakeSwitch.

These scenarios prove the two live-agent findings are fixed structurally.

Ways each could fail, checked before the happy paths:

- an ``ask`` still routes through a planning DM: the recipient's own agent is
  invited into the room, or the recipient's home shows a "Planning with …"
  notice or a share card;
- the asker's gate creates an ``ask-`` room but the friend's gate still invites
  its own agent or posts home (a leak that only moves the room name);
- the friend's gate answers an ``ask`` it should refuse because the room's fresh
  membership or level is wrong, or because the sender is not the friend's gate
  in the connection room;
- a ``join-ask`` from a gate that has not said hello, or for a room not named
  ``ask-<pair>-*``, is accepted;
- a hidden field marked ``quiet: true`` still raises a real-time overreach note,
  or a hidden non-quiet field silently stops alerting, or a quiet request is not
  written to the ledger;
- a peer whose gate has not advertised ``join-ask`` no longer works at all
  (the fallback must keep the legacy ``dm "Facts request"`` path);
- a second ``dm`` to the same friend opens another room instead of reusing the
  open, unarchived, not-limit-closed one, or reuses a limit-closed room.
"""

from __future__ import annotations

import json

from scenario_harness import build_world, personal_session

from trustnet.gate import handshake, ledger
from trustnet.tn import personal


async def _ask_world(tmp_path, monkeypatch, *, trust=None, facts=None):
    world = await build_world(tmp_path, monkeypatch=monkeypatch, trust=trust, facts=facts)
    monkeypatch.setattr(personal, "session", personal_session(world))
    return world


def _record_peer_hello(world, asker: str, friend: str, *, with_join_ask: bool):
    """Record ``friend``'s advertised capabilities in ``asker``'s ``peers.json``.

    ``personal.ask`` reads this file to choose between the quiet ``ask-`` room and
    the legacy DM. Writing it directly simulates a peer that has already said
    hello with (or without) the ``join-ask`` capability, without a live exchange
    that would have the gate re-advertise its own full capability list.
    """
    capabilities = list(handshake.CAPABILITIES)
    if not with_join_ask:
        capabilities.remove("join-ask")
    path = world.tmp / asker / "peers.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                friend: {
                    "protocol": "trust-network/1",
                    "major": 1,
                    "capabilities": capabilities,
                    "room": "conn",
                    "at": "2026-11-05T00:00:00+00:00",
                }
            }
        )
    )


async def test_ask_room_returns_close_wishlist_without_recipient_agent_or_notice(
    tmp_path, monkeypatch
):
    """Rahul (close) asks Om for Om's wishlist through the quiet ask room."""
    world = await _ask_world(tmp_path, monkeypatch)
    _record_peer_hello(world, "rahul", "om", with_join_ask=True)
    await world.start()
    try:
        om_home_before = list(world.home_bodies("om"))
        result = await personal.ask("rahul", "om", ["wishlist"])
        room = result["room"]
        await world.wait_for(
            lambda: any(body.startswith("wishlist:") for body in world.bodies(room)),
            what="the wishlist answer",
        )
        answer = next(body for body in world.bodies(room) if body.startswith("wishlist:"))
        assert "Lego Millennium Falcon" in answer

        ask_room = world.switch.rooms[room]
        assert ask_room["name"].startswith("ask-om-rahul-")
        # The asker's agent is in the room; the recipient's agent is not.
        assert "rahul-hermes" in ask_room["members"]
        assert "om-hermes" not in ask_room["members"]
        # The recipient's gate was the only non-asker member invited.
        assert not world.rooms_named("dm-om-rahul-")
        # The recipient's home gets no planning notice or share card.
        assert world.home_bodies("om") == om_home_before
    finally:
        await world.stop()


async def test_first_contact_ask_stays_quiet_and_reuses_its_room(tmp_path, monkeypatch):
    """No pairwise room ever said hello: the ask is still quiet, and a second ask
    reuses the pair's room instead of opening another."""
    world = await _ask_world(tmp_path, monkeypatch)
    await world.start()
    try:
        om_home_before = list(world.home_bodies("om"))
        first = await personal.ask("rahul", "om", ["wishlist"])
        await world.wait_for(
            lambda: any(body.startswith("wishlist:") for body in world.bodies(first["room"])),
            what="the first wishlist answer",
        )
        second = await personal.ask("rahul", "om", ["diet"])
        await world.wait_for(
            lambda: any(body.startswith("diet:") for body in world.bodies(second["room"])),
            what="the diet answer",
        )
        assert second["room"] == first["room"]
        assert len(world.rooms_named("ask-om-rahul-")) == 1
        assert "om-hermes" not in world.switch.rooms[first["room"]]["members"]
        assert not world.rooms_named("dm-om-rahul-")
        assert world.home_bodies("om") == om_home_before
    finally:
        await world.stop()


async def test_quiet_hidden_field_ledgers_but_does_not_alert(tmp_path, monkeypatch):
    """A hidden quiet fact is ledgered; a hidden non-quiet fact still alerts."""
    world = await _ask_world(
        tmp_path,
        monkeypatch,
        trust={"om": {"rahul": "friend"}},
        facts={"om": {"sizes": {"value": {"tshirt": "M"}, "level": "close", "quiet": True}}},
    )
    room = await world.add_room("conn-om-rahul", ["om-gate", "rahul-gate"])
    await world.say(room, "rahul-gate", "@om-gate ask sizes address")

    assert world.bodies(room)[-1].splitlines() == [
        "sizes: not shared with you",
        "address: not shared with you",
    ]
    notes = world.home_bodies("om")
    assert any("asked for your address (private)" in note for note in notes)
    assert not any("sizes" in note for note in notes)

    entries = ledger.read("om")
    request = next(entry for entry in entries if entry.field == "sizes")
    assert request.kind.value == "request"
    assert request.value == "not shared (close)"
    assert {entry.field for entry in entries if entry.kind.value == "answer"} == set()


async def test_peer_without_join_ask_falls_back_to_the_dm_path(tmp_path, monkeypatch):
    """A friend whose gate never advertised ``join-ask`` still answers via a DM."""
    world = await _ask_world(tmp_path, monkeypatch)
    _record_peer_hello(world, "rahul", "om", with_join_ask=False)
    await world.start()
    try:
        result = await personal.ask("rahul", "om", ["wishlist"])
        room = result["room"]
        await world.wait_for(
            lambda: any(body.startswith("wishlist:") for body in world.bodies(room)),
            what="the wishlist answer via the legacy DM",
        )
        assert any(body.startswith("wishlist:") for body in world.bodies(room))
        assert not world.rooms_named("ask-om-rahul-")
        dm_rooms = world.rooms_named("dm-om-rahul-facts-request")
        assert dm_rooms, "expected a legacy facts-request DM room"
        # The legacy path is the leaky one: the recipient's agent is a member.
        assert "om-hermes" in world.switch.rooms[room]["members"]
    finally:
        await world.stop()


async def test_second_dm_reuses_the_open_room(tmp_path, monkeypatch):
    """Repeated ``dm`` calls with different wording share one planning room."""
    world = await _ask_world(tmp_path, monkeypatch)
    await world.start()
    try:
        await personal.dm("om", "rahul", "something fun Sunday evening")
        await world.wait_for(
            lambda: len(world.rooms_named("dm-om-rahul-")) == 1,
            what="the first planning room",
        )
        first = world.rooms_named("dm-om-rahul-")[0]

        await personal.dm("om", "rahul", "a different wording for the same plan")
        await world.wait_for(
            lambda: any(
                "Planning continues with rahul" in body for body in world.home_bodies("om")
            ),
            what="the reuse notice",
        )
        assert len(world.rooms_named("dm-om-rahul-")) == 1
        assert any(first["id"] in body for body in world.home_bodies("om"))
    finally:
        await world.stop()
