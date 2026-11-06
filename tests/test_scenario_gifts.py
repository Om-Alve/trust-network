"""End-to-end surprise-mode gift scenarios over FakeSwitch.

A gift room holds only the two gates. The recipient never posts home, its
wishlist entry is sealed until the day after the occasion, a second asker sees
a claimed item as taken, and the room is archived on a claim or timeout. A
malformed command in a gift room is ignored rather than raised out of dispatch.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pytest
from scenario_harness import build_world, personal_session

from trustnet.gate import ledger, surprise
from trustnet.gate.calendar import TIME_ZONE
from trustnet.gate.facts import load_profile
from trustnet.switch_client import SwitchError
from trustnet.tn import personal

OCCASION = "2026-11-20"


async def _gift_world(tmp_path, monkeypatch):
    world = await build_world(
        tmp_path,
        monkeypatch=monkeypatch,
        trust={"om": {"rahul": "close", "priya": "close"}},
    )
    monkeypatch.setattr(personal, "session", personal_session(world))
    await world.start()
    return world


async def test_two_askers_taken_items_and_the_recipients_seal(tmp_path, monkeypatch):
    world = await _gift_world(tmp_path, monkeypatch)
    try:
        before = list(world.home_bodies("om"))
        first = await personal.gift_ideas("rahul", "om", "birthday", OCCASION, 3000)
        second = await personal.gift_ideas("priya", "om", "birthday", OCCASION, 3000)

        assert (
            first["suggestions"]
            == second["suggestions"]
            == [
                {"item": "Lego Millennium Falcon", "price": 2500},
                {"item": "Hario V60", "price": 2000},
            ]
        )
        assert first["over_budget"] == [
            {"item": "Kindle Paperwhite", "price": 14000, "status": "over budget"}
        ]
        assert first["taken"] == []

        # Agents re-case brand names ("LEGO"); the claim is the wishlist's item,
        # in the wishlist's spelling.
        assert await personal.claim("rahul", "om", "LEGO  Millennium Falcon") == {
            "status": "claimed",
            "item": "Lego Millennium Falcon",
        }
        # A second asker who asked before the claim cannot take the same item.
        with pytest.raises(SwitchError, match="Item unavailable"):
            await personal.claim("priya", "om", "lego millennium falcon")

        third = await personal.gift_ideas("priya", "om", "birthday", OCCASION, 3000)
        assert third["taken"] == [{"item": "Lego Millennium Falcon", "status": "taken"}]
        assert [item["item"] for item in third["suggestions"]] == ["Hario V60"]
        assert [item["item"] for item in third["over_budget"]] == ["Kindle Paperwhite"]

        # Nothing gift-related reaches the recipient's home room.
        assert world.home_bodies("om") == before

        # The claim closed and archived the asker's room.
        room = world.rooms_named("gift-rahul-om-")[0]
        await world.wait_for(lambda: room["archived"], what="claimed gift room archived")

        # The recipient's own views hide the claimed item until the day after.
        wishlist = load_profile("om").facts["wishlist"].value
        on = datetime(2026, 11, 20, 12, 0, tzinfo=TIME_ZONE)
        after = datetime(2026, 11, 21, 12, 0, tzinfo=TIME_ZONE)
        hidden = surprise.owner_value("om", "wishlist", wishlist, now=on)
        assert [item["item"] for item in hidden] == ["Hario V60", "Kindle Paperwhite"]
        assert surprise.owner_value("om", "wishlist", wishlist, now=after) == wishlist

        sealed = ledger.format_ledger(person="om", now=on)
        opened = ledger.format_ledger(person="om", now=after)
        assert "sealed entr" in sealed and "opens Nov 21" in sealed
        assert "Lego Millennium Falcon" not in sealed
        assert "sealed entr" not in opened and "gift" in opened
    finally:
        await world.stop()


async def test_an_idle_gift_room_is_archived_after_ten_minutes(tmp_path, monkeypatch):
    world = await _gift_world(tmp_path, monkeypatch)
    try:
        await personal.gift_ideas("rahul", "om", "birthday", OCCASION, 3000)
        room = world.rooms_named("gift-rahul-om-")[0]
        assert not room["archived"]

        world.clock.advance(minutes=11)
        await surprise.expire(world.gates["om"])
        await surprise.expire(world.gates["rahul"])
        assert room["archived"]
    finally:
        await world.stop()


async def test_ask_is_refused_in_a_gift_room_without_telling_the_owner(
    tmp_path, monkeypatch, caplog
):
    world = await build_world(tmp_path, monkeypatch=monkeypatch)
    room = await world.add_room("gift-rahul-om-birthday", ["om-gate", "rahul-gate"])
    before = list(world.home_bodies("om"))

    with caplog.at_level(logging.INFO, logger="trustnet.gate.runtime"):
        await world.say(room, "rahul-gate", "@om-gate ask diet address")

    assert world.bodies(room)[-1].splitlines() == [
        "diet: not shared with you",
        "address: not shared with you",
    ]
    assert world.home_bodies("om") == before
    assert caplog.text.count("reason=gift-room") == 2


async def test_malformed_gift_traffic_is_ignored_not_raised(tmp_path, monkeypatch):
    world = await build_world(tmp_path, monkeypatch=monkeypatch)
    room = await world.add_room("gift-rahul-om-birthday", ["om-gate", "rahul-gate"])
    before = list(world.home_bodies("om"))

    # These raised ParseError out of surprise.handle before the fix.
    for text in ("@om-gate ask", "@om-gate claim"):
        await world.say(room, "rahul-gate", text)
    assert world.bodies(room) == []
    assert world.home_bodies("om") == before
