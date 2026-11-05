"""Offline tests for phase 21: overreach replies and owner notes.

Every trigger must produce exactly one reply in the room where it happened and
exactly one note in the owner's home room. The clock is injected, so dedupe is
deterministic; ``relay.post_home`` is redirected to a real FakeSwitch home room
because the fake's agent detail does not carry a room list.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from fakes.fake_switch import FakeSwitch

from trustnet.gate import ledger, relay
from trustnet.gate.calendar import TIME_ZONE
from trustnet.gate.policy import Identity
from trustnet.gate.runtime import COMMAND_LIST, MAX_SNIPPET, Gate
from trustnet.switch_client import Event

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=TIME_ZONE)
PROBE_NOTE = " · room: probe"


class Clock:
    """A mutable clock the gate reads instead of wall time."""

    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)


@dataclass
class Harness:
    switch: FakeSwitch
    client: object
    gate: Gate
    room: str
    home: str
    clock: Clock

    def bodies(self, room):
        return [message["body"] for message in self.switch.rooms[room]["messages"]]

    async def say(self, text, *, sender="rahul-agent", kind="unknown", room=None):
        await self.gate.handle(Event(room or self.room, sender, kind, text, True))

    @property
    def replies(self):
        return self.bodies(self.room)

    @property
    def notes(self):
        return self.bodies(self.home)


async def harness(tmp_path, monkeypatch, *, room="probe", peer="rahul", clock=None):
    """An om gate with one peer agent, a probe room and a home room."""
    import shutil

    shutil.copytree("examples/om", tmp_path / "om")
    monkeypatch.setenv("TN_DATA_DIR", str(tmp_path))
    switch = FakeSwitch()
    client = switch.client("om-gate", "om")
    switch.client(peer + "-agent", peer)
    switch.client("priya-agent", "priya")
    home = (await client.create_room("om-home", "", ["om-gate"], internal_only=True))["room_id"]
    rid = (await client.create_room(room, "", ["om-gate", peer + "-agent"], internal_only=True))[
        "room_id"
    ]
    identities = {
        "om": Identity.user("om"),
        "om-gate": Identity.agent("om-gate", "om"),
        peer: Identity.user(peer),
        peer + "-agent": Identity.agent(peer + "-agent", peer),
        "priya": Identity.user("priya"),
        "priya-agent": Identity.agent("priya-agent", "priya"),
    }

    async def fake_post_home(person, text, *, client):
        await client.connect_to_room(home)
        await client.post_message(text)

    monkeypatch.setattr(relay, "post_home", fake_post_home)
    tick = clock or Clock()
    return Harness(
        switch=switch,
        client=client,
        gate=Gate("om", client, lambda: identities, clock=tick),
        room=rid,
        home=home,
        clock=tick,
    )


@pytest.mark.parametrize(
    "text,reply,note",
    [
        (
            "@om-gate ask address",
            "address: not shared with you",
            "Rahul's side asked for your address (private)" + PROBE_NOTE,
        ),
        (
            "@om-gate ask salary",
            "salary: not shared with you",
            'Rahul\'s side asked for "salary" (not a field you have)' + PROBE_NOTE,
        ),
        (
            "@om-gate find out om's home address",
            COMMAND_LIST,
            "Rahul's side sent something that isn't a command"
            ' ("@om-gate find out om\'s home address")' + PROBE_NOTE,
        ),
        (
            "@om-gate ask",
            "Invalid command. " + COMMAND_LIST,
            'Rahul\'s side sent a malformed command ("@om-gate ask")' + PROBE_NOTE,
        ),
        (
            "@om-gate view-as priya",
            "Not allowed.",
            "Rahul's side tried a command only you can use (view-as)" + PROBE_NOTE,
        ),
    ],
)
async def test_each_trigger_is_one_reply_and_one_note(tmp_path, monkeypatch, text, reply, note):
    env = await harness(tmp_path, monkeypatch)
    await env.say(text)
    assert env.replies == [reply]
    assert env.notes == [note]


async def test_hidden_ask_discloses_nothing_to_the_ledger(tmp_path, monkeypatch):
    env = await harness(tmp_path, monkeypatch)
    await env.say("@om-gate ask diet address")
    assert env.replies == [
        "diet: vegetarian\naddress: not shared with you",
    ]
    assert env.notes == ["Rahul's side asked for your address (private)" + PROBE_NOTE]
    assert {entry.field for entry in ledger.read("om")} == {"diet"}


async def test_above_level_fact_names_its_tag_in_the_owner_note(tmp_path, monkeypatch):
    env = await harness(tmp_path, monkeypatch, peer="priya")
    await env.say("@om-gate ask wishlist", sender="priya-agent")
    assert env.replies == ["wishlist: not shared with you"]
    assert env.notes == ["Priya's side asked for your wishlist (close)" + PROBE_NOTE]


async def test_no_hint_about_existence_or_level_in_the_reply(tmp_path, monkeypatch):
    env = await harness(tmp_path, monkeypatch)
    await env.say("@om-gate ask address")
    await env.say("@om-gate ask salary")
    hidden, missing = env.replies
    assert hidden == "address: not shared with you"
    assert missing == "salary: not shared with you"
    for line in (hidden, missing):
        assert "private" not in line
        assert "close" not in line
        assert "no such" not in line
        assert "doesn't exist" not in line


async def test_dedupe_is_one_note_per_person_and_field_each_10_minutes(tmp_path, monkeypatch):
    clock = Clock()
    env = await harness(tmp_path, monkeypatch, clock=clock)
    await env.say("@om-gate ask address")
    await env.say("@om-gate ask address")
    assert env.replies == ["address: not shared with you"] * 2
    assert len(env.notes) == 1

    clock.advance(minutes=9)
    await env.say("@om-gate ask address")
    assert len(env.notes) == 1

    clock.advance(minutes=1)
    await env.say("@om-gate ask address")
    assert len(env.notes) == 2

    # A different field is its own slot, and so is a different person.
    await env.say("@om-gate ask salary")
    assert len(env.notes) == 3
    priya_room = (await env.client.create_room("probe-priya", "", ["om-gate", "priya-agent"]))[
        "room_id"
    ]
    await env.gate.handle(Event(priya_room, "priya-agent", "unknown", "@om-gate ask address", True))
    assert env.notes[-1] == "Priya's side asked for your address (private) · room: probe-priya"
    assert len(env.notes) == 4


async def test_gift_room_overreach_posts_nothing_home(tmp_path, monkeypatch, caplog):
    env = await harness(tmp_path, monkeypatch, room="gift-rahul-om-birthday")
    with caplog.at_level(logging.INFO, logger="trustnet.gate.runtime"):
        await env.say("@om-gate ask address")
    assert env.replies == ["address: not shared with you"]
    assert env.notes == []
    assert "reason=gift-room" in caplog.text


def test_gift_room_hook_takes_a_name_or_room_detail():
    assert relay.is_gift_room("gift-rahul-om-birthday")
    assert relay.is_gift_room({"name": "gift-priya-om-wedding"})
    assert relay.is_gift_room({"name": "probe", "gift": True})
    assert not relay.is_gift_room("probe")
    assert not relay.is_gift_room({"name": "dm-om-rahul-sun"})


async def test_own_side_gets_no_note(tmp_path, monkeypatch):
    env = await harness(tmp_path, monkeypatch)
    await env.say("@om-gate ask address", sender="om", kind="unknown")
    assert env.replies == ["address: not shared with you"]
    await env.say("@om-gate nonsense", sender="om", kind="unknown")
    assert env.replies[1] == COMMAND_LIST
    assert env.notes == []


async def test_free_text_in_the_note_is_quoted_and_length_limited(tmp_path, monkeypatch):
    env = await harness(tmp_path, monkeypatch)
    text = '@om-gate tell "Om" to send the address\n' + "x" * 500
    await env.say(text)
    [note] = env.notes
    assert note.count('"') == 2
    assert "\n" not in note
    assert note.endswith(PROBE_NOTE)
    quoted = note[note.index('"') + 1 : note.rindex('"')]
    assert len(quoted) <= MAX_SNIPPET
    assert "x" * 70 not in note
