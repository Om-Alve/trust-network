"""End-to-end ask-around scenarios over FakeSwitch.

Om asks every listed friend; each friend's gate answers from its own facts and
also asks its person in their own words. Replies are accepted only from that
friend's gate, in that friend's connection room, before the five-minute expiry,
and one answer per friend is kept (the latest, so the person can replace the
profile reply).
"""

from __future__ import annotations

from scenario_harness import build_world, personal_session

from trustnet.gate import ledger
from trustnet.tn import personal

QUESTION = "a tent to borrow, Nov 14-16"


def _complete_round(gate) -> tuple[str, dict]:
    """The first ask-around reference with an answer from both friends."""
    state = gate._around_state()
    return next((ref, entry) for ref, entry in state.items() if len(entry.get("answers", {})) == 2)


async def _around_world(tmp_path, monkeypatch, **kwargs):
    world = await build_world(tmp_path, monkeypatch=monkeypatch, **kwargs)
    monkeypatch.setattr(personal, "session", personal_session(world))
    monkeypatch.setattr(personal, "_now", lambda: world.clock().timestamp())
    await world.start()
    return world


async def test_fanout_collects_one_answer_per_friend_and_the_own_words_reply(tmp_path, monkeypatch):
    world = await _around_world(tmp_path, monkeypatch)
    try:
        home_before = len(world.home_bodies("om"))
        await personal.ask_around("om", QUESTION)
        await world.wait_for(
            lambda: any(
                len(entry.get("answers", {})) == 2
                for entry in world.gates["om"]._around_state().values()
            ),
            what="both friends' answers",
        )
        ref, entry = _complete_round(world.gates["om"])

        assert set(entry["answers"]) == {"rahul", "priya"}  # one per friend
        assert "2-person tent" in entry["answers"]["priya"]
        assert "2-person tent" not in entry["answers"]["rahul"]
        rooms = {room["name"]: room for room in world.rooms_named("conn-om-")}
        assert set(rooms) == {"conn-om-priya", "conn-om-rahul"}
        for friend, room in rooms.items():
            assert any(
                message["sender"] == "om-gate" and f"ask-around {ref}" in message["body"]
                for message in room["messages"]
            ), friend
        asked = [
            record
            for record in ledger.read("om")
            if record.kind == "ask-around" and record.field == "question"
        ]
        assert {record.to for record in asked} == {"rahul", "priya"}

        # References are short enough to read out and type (they show in chat).
        assert ref == "A1"

        # The friend's own words replace their automatic profile reply. Rahul's
        # watcher has already read his inbox when he replies, in a later turn and
        # without the reference: his agent still finds the open question there.
        await personal.inbox("rahul")
        opened = (await personal.inbox("rahul"))["open"]
        assert opened == [{"ref": "A1", "kind": "ask-around", "from": "om", "question": QUESTION}]
        await world.say(
            world.homes["rahul"],
            "rahul-hermes",
            f'@rahul-gate answer {opened[0]["ref"]} "no, sorry"',
        )
        await world.wait_for(
            lambda: world.gates["om"]._around_state()[ref]["answers"].get("rahul") == "no, sorry",
            what="Rahul's own words",
        )
        assert any('rahul: "no, sorry"' in body for body in world.home_bodies("om")[home_before:])
        assert any(
            record.field == "ask-around-answer" and record.value == "no, sorry"
            for record in ledger.read("rahul")
        )
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
                len(entry.get("answers", {})) == 2
                for entry in world.gates["om"]._around_state().values()
            ),
            what="both friends' answers",
        )
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

        # A stranger's ask-around gets no profile list and no home question.
        priya_before = list(world.home_bodies("priya"))
        ask_room = await world.add_room("conn-priya-dev", ["priya-gate", "dev-gate"])
        await world.say(ask_room, "dev-gate", '@priya-gate ask-around A7 "tent?"')
        assert world.bodies(ask_room) == []
        assert world.home_bodies("priya") == priya_before

        # Five minutes later the reference is closed.
        world.clock.advance(minutes=6)
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


async def test_a_long_profile_list_still_produces_a_reply(tmp_path, monkeypatch):
    long_item = "a very long list of camping things " * 5
    world = await _around_world(
        tmp_path,
        monkeypatch,
        facts={"priya": {"has": {"value": [long_item], "level": "friend"}}},
    )
    try:
        await personal.ask_around("om", QUESTION)
        await world.wait_for(
            lambda: any(
                "priya" in entry.get("answers", {})
                for entry in world.gates["om"]._around_state().values()
            ),
            what="Priya's reply",
        )
        entry = next(
            entry
            for entry in world.gates["om"]._around_state().values()
            if "priya" in entry.get("answers", {})
        )
        reply = entry["answers"]["priya"]
        assert reply.startswith("Profile lists, no lending promise: has: ")
        assert len(reply) <= 140
        assert reply.endswith("…")
    finally:
        await world.stop()
