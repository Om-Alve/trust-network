"""End-to-end ask-around scenarios over FakeSwitch.

Om asks every listed friend. A friend's gate never dumps ``has``/``recommends``
on its own: it routes the quoted question to that person's own agent, or to the
person when they opted in (or when no agent is registered). Replies are
accepted only from that friend's gate, in that friend's connection room, before
the seven-day expiry, and one answer per friend is kept (the latest, so the
person can replace the agent's reply).
"""

from __future__ import annotations

import pytest
from scenario_harness import build_world, personal_session
from sharing_flows import SCENARIOS as SHARING_SCENARIOS

from trustnet.gate import ledger
from trustnet.tn import personal

QUESTION = "a tent to borrow, Nov 14-16"


def _complete_round(gate) -> tuple[str, dict]:
    """The first ask-around reference with an answer from both friends."""
    state = gate._around_state()
    return next((ref, entry) for ref, entry in state.items() if len(entry.get("answers", {})) == 2)


def _local(gate, peer: str = "om") -> dict:
    return next(
        value
        for key, value in gate._around_state().items()
        if key.startswith(peer + ":") and value.get("local")
    )


async def _around_world(tmp_path, monkeypatch, **kwargs):
    world = await build_world(tmp_path, monkeypatch=monkeypatch, **kwargs)
    monkeypatch.setattr(personal, "session", personal_session(world))
    monkeypatch.setattr(personal, "_now", lambda: world.clock().timestamp())
    await world.start()
    return world


async def _answer_both(world) -> dict[str, dict]:
    await world.wait_for(
        lambda: _local(world.gates["rahul"]) and _local(world.gates["priya"]),
        what="both home questions",
    )
    rahul = _local(world.gates["rahul"])
    priya = _local(world.gates["priya"])
    await personal.answer("rahul", rahul["local"], "Rahul has no tent")
    await personal.answer("priya", priya["local"], "Priya's tent is free")
    await world.wait_for(
        lambda: any(
            len(entry.get("answers", {})) == 2
            for entry in world.gates["om"]._around_state().values()
        ),
        what="both friends' answers",
    )
    return {"rahul": rahul, "priya": priya}


async def test_ask_around_routes_to_own_side_without_dumping_profile_facts(tmp_path, monkeypatch):
    world = await _around_world(tmp_path, monkeypatch)
    try:
        home_before = len(world.home_bodies("om"))
        await personal.ask_around("om", QUESTION)
        await world.wait_for(
            lambda: any(
                entry.get("question") == QUESTION
                for entry in world.gates["om"]._around_state().values()
            ),
            what="the ask-around fan-out",
        )
        entry = next(
            entry
            for entry in world.gates["om"]._around_state().values()
            if entry.get("question") == QUESTION
        )

        # Nothing was answered for the friends before their own side spoke.
        assert entry.get("answers") == {}
        await world.wait_for(
            lambda: _local(world.gates["rahul"]) and _local(world.gates["priya"]),
            what="both home questions",
        )
        rooms = {room["name"]: room for room in world.rooms_named("conn-om-")}
        assert set(rooms) == {"conn-om-priya", "conn-om-rahul"}
        for friend, room in rooms.items():
            bodies = [message["body"] for message in room["messages"]]
            assert any("ask-around" in body for body in bodies), friend
            assert all("Profile lists" not in body for body in bodies), friend
            assert all("2-person tent" not in body for body in bodies), friend

        # The default route is the recipient's agent, not the person directly.
        assert "Your agent can reply" in world.home_bodies("rahul")[-1]
        assert "Your agent can reply" in world.home_bodies("priya")[-1]

        asked = [
            record
            for record in ledger.read("om")
            if record.kind == "ask-around" and record.field == "question"
        ]
        assert {record.to for record in asked} == {"rahul", "priya"}
        ref = next(
            key
            for key, value in world.gates["om"]._around_state().items()
            if value.get("question") == QUESTION
        )
        assert ref == "A1"

        # References are short enough to read out and type (they show in chat).
        await personal.inbox("rahul")
        opened = (await personal.inbox("rahul"))["open"]
        assert opened == [{"ref": "A1", "kind": "ask-around", "from": "om", "question": QUESTION}]
        # An answer to a reference that isn't open (an old one still in the home
        # room's history) is refused out loud, naming what is open, so the agent
        # can retry instead of reporting an answer that went nowhere.
        await world.say(world.homes["rahul"], "rahul-hermes", '@rahul-gate answer A7 "no, sorry"')
        assert world.home_bodies("rahul")[-1] == (
            "A7 not sent: it isn't open (answered, expired or unknown). Open: A1 from om."
        )

        locals_ = await _answer_both(world)
        assert any(
            'rahul: "Rahul has no tent"' in body for body in world.home_bodies("om")[home_before:]
        )
        assert any(
            record.field == "ask-around-answer" and record.value == "Rahul has no tent"
            for record in ledger.read("rahul")
        )
        assert locals_["rahul"]["local"] == "A1"

        # Once answered, it's no longer open.
        await world.wait_for(
            lambda: world.gates["rahul"]._around_state()["om:A1"]["answered"] is True,
            what="Rahul's question marked answered",
        )
        assert (await personal.inbox("rahul"))["open"] == []
    finally:
        await world.stop()


async def test_forged_late_and_stranger_replies_are_ignored(tmp_path, monkeypatch):
    world = await _around_world(tmp_path, monkeypatch, strangers=("dev",))
    try:
        await personal.ask_around("om", QUESTION)
        await world.wait_for(
            lambda: any(
                entry.get("question") == QUESTION
                for entry in world.gates["om"]._around_state().values()
            ),
            what="the ask-around fan-out",
        )
        await _answer_both(world)
        ref, entry = _complete_round(world.gates["om"])
        expected = dict(entry["answers"])

        # Same friend's gate, but not in the connection room the ask went to.
        probe = await world.add_room("probe-forged", ["om-gate", "rahul-gate"])
        await world.say(probe, "rahul-gate", f'@om-gate answer {ref} "forged"')
        assert world.bodies(probe) == ["Not allowed."]
        assert world.gates["om"]._around_state()[ref]["answers"] == expected

        # A person who is not on the trust list never reaches the answer map.
        stranger_room = await world.add_room("conn-om-dev", ["om-gate", "dev-gate"])
        await world.say(stranger_room, "dev-gate", f'@om-gate answer {ref} "forged"')
        assert world.bodies(stranger_room) == []

        # A stranger's ask-around gets no home question and no profile list.
        priya_before = list(world.home_bodies("priya"))
        ask_room = await world.add_room("conn-priya-dev", ["priya-gate", "dev-gate"])
        await world.say(ask_room, "dev-gate", '@priya-gate ask-around A7 "tent?"')
        assert world.bodies(ask_room) == []
        assert world.home_bodies("priya") == priya_before

        # People can reply the next day without losing their request.
        world.clock.advance(minutes=24 * 60)
        await world.say(
            entry["peers"]["rahul"], "rahul-gate", f'@om-gate answer {ref} "tomorrow works"'
        )
        expected["rahul"] = "tomorrow works"
        assert world.gates["om"]._around_state()[ref]["answers"] == expected
        # After the seven-day deadline, further replies cannot change it.
        world.clock.advance(minutes=7 * 24 * 60)
        home_before = len(world.home_bodies("om"))
        await world.say(
            entry["peers"]["rahul"],
            "rahul-gate",
            f'@om-gate answer {ref} "too late"',
        )
        assert world.gates["om"]._around_state()[ref]["answers"] == expected
        assert len(world.home_bodies("om")) == home_before
    finally:
        await world.stop()


@pytest.mark.parametrize("scenario", SHARING_SCENARIOS, ids=lambda f: f.__name__)
async def test_sharing_scenario(scenario, tmp_path, monkeypatch):
    """The permission, block and ask-around contract, one fresh world each."""
    await scenario(tmp_path / "sharing", monkeypatch)
