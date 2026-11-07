"""End-to-end facts scenarios over FakeSwitch: levels, mixed rooms, previews.

Each test drives a real ``Gate`` object. The failure modes are listed in
`the original build record` under B; the ones already covered elsewhere
(overreach cooldown, CLI/MCP loosen refusal) are not repeated here.
"""

from __future__ import annotations

import pytest
from scenario_harness import build_world

from trustnet.gate import ledger
from trustnet.gate.facts import Level, load_profile
from trustnet.gate.policy import visible_facts
from trustnet.gate.view_as import NOT_SHARED, format_value

LEVELS = ("acquaintance", "friend", "close")


def _ask(world, room: str) -> dict[str, str]:
    """Return the last ``ask`` reply as field -> value line."""
    reply = world.bodies(room)[-1]
    assert reply
    return dict(line.split(": ", 1) for line in reply.splitlines())


@pytest.mark.parametrize("level", LEVELS)
async def test_ask_shows_only_the_rooms_level_and_records_only_what_it_shows(
    tmp_path, monkeypatch, level
):
    world = await build_world(tmp_path, monkeypatch=monkeypatch, trust={"om": {"rahul": level}})
    room = await world.add_room("conn-om-rahul", ["om-gate", "rahul-gate"])
    fields = " ".join([*load_profile("om").facts, "salary"])
    await world.say(room, "rahul-gate", "@om-gate ask " + fields)
    lines = _ask(world, room)

    profile = load_profile("om")
    allowed = visible_facts(profile, Level(level))
    assert set(lines) == set(profile.facts) | {"salary"}
    for name, value in allowed.items():
        assert lines[name] == format_value(value)
    for name, line in lines.items():
        if name in allowed:
            continue
        assert line == "not shared with you", name

    # The hidden and the nonexistent field read exactly the same; neither names
    # a level or says whether the owner has the fact.
    assert lines["address"] == lines["salary"] == "not shared with you"
    for line in lines.values():
        assert "private" not in line and "close" not in line

    entries = ledger.read("om")
    assert {entry.field for entry in entries} == set(allowed)
    assert {entry.to for entry in entries} == {"om", "rahul"}

    notes = world.home_bodies("om")
    assert any("asked for your address (private)" in note for note in notes)
    assert any('asked for "salary" (not a field you have)' in note for note in notes)

    # view-as is the same policy answer, field by field.
    await world.say(world.homes["om"], "om", "@om-gate view-as rahul", kind="user")
    rendered = world.home_bodies("om")[-1]
    for name, value in allowed.items():
        assert any(
            line.strip().startswith(f"✅ {name}") and format_value(value) in line
            for line in rendered.splitlines()
        ), name
    for name in set(profile.facts) - set(allowed):
        assert any(
            line.strip().startswith(f"❌ {name}") and NOT_SHARED in line
            for line in rendered.splitlines()
        ), name
    assert "✅ salary" not in rendered


async def test_a_dm_room_answers_at_the_lowest_friends_level(tmp_path, monkeypatch):
    world = await build_world(
        tmp_path,
        monkeypatch=monkeypatch,
        trust={"om": {"rahul": "close", "priya": "friend"}},
    )
    room = await world.add_room(
        "dm-om-rahul-priya-plan",
        ["om-gate", "rahul-gate", "priya-gate", "om-hermes", "rahul-hermes", "priya-hermes"],
    )
    await world.say(room, "rahul-hermes", "@om-gate ask diet wishlist address")
    lines = dict(line.split(": ", 1) for line in world.bodies(room)[-1].splitlines())

    # Rahul is close, Priya is only a friend, so the room is friend: the
    # close-only wishlist stays hidden even from Rahul's side.
    assert lines["diet"] == "vegetarian"
    assert lines["wishlist"] == lines["address"] == "not shared with you"
    assert {entry.field for entry in ledger.read("om")} == {"diet"}
    notes = world.home_bodies("om")
    assert any("asked for your wishlist (close)" in note for note in notes)
    assert any("asked for your address (private)" in note for note in notes)


async def test_free_keeps_busy_times_but_hides_titles_by_default(tmp_path, monkeypatch):
    world = await build_world(
        tmp_path,
        monkeypatch=monkeypatch,
        trust={"om": {"rahul": "close", "dev": "acquaintance"}},
        strangers=("dev",),
    )
    acq = await world.add_room("conn-om-dev", ["om-gate", "dev-gate"])
    close = await world.add_room("conn-om-rahul", ["om-gate", "rahul-gate"])
    for room, sender in ((acq, "dev-gate"), (close, "rahul-gate")):
        await world.say(room, sender, "@om-gate free 2026-11-08..2026-11-09")

    acquaintance = world.bodies(acq)[-1]
    close_friend = world.bodies(close)[-1]
    block = "2026-11-08T17:00:00+05:30 .. 2026-11-08T19:00:00+05:30 busy"
    assert block in acquaintance
    assert block in close_friend
    assert "Family video call" not in acquaintance
    assert "Family video call" not in close_friend


async def test_a_stranger_gets_silence_and_no_ledger_entry(tmp_path, monkeypatch):
    world = await build_world(tmp_path, monkeypatch=monkeypatch, strangers=("dev",))
    room = await world.add_room("probe", ["om-gate", "dev-hermes"])
    await world.say(room, "dev-hermes", "@om-gate ask diet address")
    await world.say(room, "dev-hermes", "@om-gate free 2026-11-08")
    assert world.bodies(room) == []
    assert ledger.read("om") == []
    assert world.home_bodies("om") == []
