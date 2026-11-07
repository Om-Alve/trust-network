"""``tn wake``: turn failures, the lock, silence and OpenCode's JSON stream.

The runner is driven with real local subprocesses, so a failing or timed-out
turn is a real process. Nothing here touches Switch except ``watch``, which
reads a fake ``FakeSwitch`` through the personal layer.
"""

from __future__ import annotations

import sys
import time

import pytest
from scenario_harness import build_world, personal_session

from trustnet.gate import relay
from trustnet.switch_client import SwitchError
from trustnet.tn import personal, wake


def _runner(person="om", invoke=None, on_reply=None):
    return wake.Runner(
        person,
        invoke or (lambda reply: ([sys.executable, "-c", "pass"], {}, lambda out: out)),
        "Om's agent",
        15.0,
        on_reply=on_reply,
    )


async def test_a_failed_turn_is_carried_into_the_next_prompt(tmp_path):
    runner = _runner(
        invoke=lambda reply: (
            [sys.executable, "-c", "import sys; sys.stdin.read(); sys.exit(3)"],
            {},
            lambda out: out,
        )
    )
    await runner.turn("news one")
    assert runner.carry == ["news one"]

    captured = tmp_path / "prompt.txt"
    code = f"import sys; open({str(captured)!r}, 'w').write(sys.stdin.read()); print('done')"
    runner.invoke = lambda reply: ([sys.executable, "-c", code], {}, lambda out: out)
    seen: list[str] = []

    async def on_reply(text):
        seen.append(text)

    runner.on_reply = on_reply
    await runner.turn("news two")

    prompt = captured.read_text()
    assert "news one" in prompt and "news two" in prompt
    assert runner.carry == []
    assert seen == ["done"]
    assert runner.transcript[-1].endswith("done")


async def test_a_timed_out_turn_is_killed_and_carried(tmp_path, monkeypatch):
    monkeypatch.setattr(wake, "TURN_TIMEOUT", 0.2)
    runner = _runner(
        invoke=lambda reply: (
            [sys.executable, "-c", "import time; time.sleep(10)"],
            {},
            lambda out: out,
        )
    )
    started = time.monotonic()
    await runner.turn("slow news")
    assert time.monotonic() - started < 5
    assert runner.carry == ["slow news"]
    assert runner.transcript == []


def test_a_second_runner_for_one_person_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("TN_DATA_DIR", str(tmp_path))
    first = wake.lock("om")
    try:
        with pytest.raises(SystemExit, match="already running"):
            wake.lock("om")
    finally:
        first.close()
    third = wake.lock("om")
    third.close()


@pytest.mark.parametrize("output", ["[SILENT]", "", "   "])
async def test_silence_is_not_shown_to_the_person(output):
    replies: list[str] = []

    async def on_reply(text):
        replies.append(text)

    runner = _runner(
        invoke=lambda reply: (
            [sys.executable, "-c", f"import sys; sys.stdout.write({output!r})"],
            {},
            lambda out: out,
        ),
        on_reply=on_reply,
    )
    await runner.turn("nothing needs you")
    assert replies == []
    assert runner.transcript == []


def test_opencode_reply_takes_the_last_assistant_message_and_skips_junk():
    stdout = "\n".join(
        [
            '{"type":"text","part":{"messageID":"m1","text":"first"}}',
            "null",
            "[1, 2]",
            "not json at all",
            '{"type":"text","part":"not an object"}',
            '{"type":"text","part":{"messageID":"m2","text":"second "}}',
            '{"type":"text","part":{"messageID":"m2","text":"message"}}',
            '{"type":"tool","part":{"messageID":"m3","text":"ignored"}}',
        ]
    )
    assert wake.opencode_reply(stdout) == "second message"
    assert wake.opencode_reply("") == ""


async def test_watch_wakes_on_a_peer_message_once_and_not_on_our_own(tmp_path, monkeypatch):
    world = await build_world(tmp_path, monkeypatch=monkeypatch, people=("om", "rahul"))
    monkeypatch.setattr(personal, "session", personal_session(world))
    room = await world.add_room(
        "dm-om-rahul-tent",
        ["om-gate", "rahul-gate", "om-hermes", "rahul-hermes"],
    )
    await relay.post_home("om", "Q1: Is 1500 okay?", client=world.gate_clients["om"])

    await world.agent_clients["rahul"].connect_to_room(room)
    await world.agent_clients["rahul"].post_message("Rahul: I have a tent.")
    first = await personal.watch("om")
    assert first["inbox_unread"] >= 1
    assert [update["room"] for update in first["dm_updates"]] == [room]
    assert first["dm_updates"][0]["from"] == "rahul-hermes"

    assert (await personal.watch("om"))["dm_updates"] == []

    await world.agent_clients["om"].connect_to_room(room)
    await world.agent_clients["om"].post_message("Om: great, thanks.")
    assert (await personal.watch("om"))["dm_updates"] == []

    await world.agent_clients["rahul"].connect_to_room(room)
    await world.agent_clients["rahul"].post_message("Rahul: it is a 2-person tent.")
    again = await personal.watch("om")
    assert [update["room"] for update in again["dm_updates"]] == [room]


async def test_answer_keeps_backslashes_and_refuses_an_ambiguous_proposal(tmp_path, monkeypatch):
    world = await build_world(tmp_path, monkeypatch=monkeypatch, people=("om", "rahul"))
    monkeypatch.setattr(personal, "session", personal_session(world))

    await personal.answer("om", "Q1", r"C:\Users\om")
    assert world.home_bodies("om")[-1] == '@om-gate answer Q1 "C:\\Users\\om"'

    with pytest.raises(ValueError, match='must be "yes" or "no"'):
        await personal.answer("om", "P1", "maybe")

    with pytest.raises(SwitchError, match="no friend named nobody"):
        await personal.dm("om", "nobody", "plan something")


async def test_group_room_filters_greetings_and_relays(tmp_path, monkeypatch):
    """A group room's Switch noise never wakes the agent; a real message does.

    Ways this could fail, and what the assertions catch:
    - a join greeting (posted under a member's own name within the greeting window
      of its ``room_join``) is reported as a new message from someone else;
    - gate-to-gate protocol traffic (a gate addressing another gate, e.g. a
      plan-relay envelope) is reported as a new message;
    - a real agent message is missed, or reported again on the next watch because
      a later greeting advanced the cursor past it;
    - a real message followed by an ignorable greeting is not reported at all.
    """
    world = await build_world(tmp_path, monkeypatch=monkeypatch, people=("om", "rahul", "priya"))
    monkeypatch.setattr(personal, "session", personal_session(world))
    room = await world.add_room(
        "group-gp-0123456789abcdef",
        ["om-gate", "om-hermes", "rahul-gate", "rahul-hermes", "priya-gate", "priya-hermes"],
    )

    # Join greetings from several members and gate-to-gate relays: no update.
    for name in ("rahul-gate", "rahul-hermes", "priya-gate", "priya-hermes"):
        world.switch.join_greeting(room, name)
    relay = (
        '{"action":"offer","plan":"gp-0123456789abcdef","revision":1,"fingerprint":"'
        + "0" * 64
        + '","participants":["om","rahul","priya"],"content":{}}'
    )
    await world.gate_clients["rahul"].connect_to_room(room)
    await world.gate_clients["rahul"].post_message(f"@om-gate plan-relay {relay}")
    await world.gate_clients["om"].connect_to_room(room)
    await world.gate_clients["om"].post_message(f"@rahul-gate plan-relay {relay}")
    assert (await personal.watch("om"))["dm_updates"] == []

    # A real message, followed by an ignorable greeting, is reported exactly once.
    # The fake switch's timestamps advance one millisecond per message, so step the
    # clock past the greeting window before the real message lands.
    world.switch.message_seq += 3000
    await world.agent_clients["rahul"].connect_to_room(room)
    await world.agent_clients["rahul"].post_message("Rahul: shall we meet at 7?")
    world.switch.join_greeting(room, "priya-hermes")
    report = await personal.watch("om")
    assert [u["room"] for u in report["dm_updates"]] == [room]
    assert report["dm_updates"][0]["from"] == "rahul-hermes"
    assert "meet at 7" in report["dm_updates"][0]["text"]

    # A later greeting does not re-report the already-seen message.
    world.switch.join_greeting(room, "priya-gate")
    assert (await personal.watch("om"))["dm_updates"] == []


async def test_a_burst_of_messages_settles_into_one_turn(monkeypatch):
    """News found by ``Runner.poll`` is re-checked once and turned into one turn.

    Ways this could fail, and what the assertions catch:
    - each message in a burst wakes the agent once (a turn per message);
    - the settle re-check is skipped, so later messages of the burst are lost;
    - the two reports are not merged, so the turn only carries one of them;
    - the settle re-check doubles the turn when nothing new arrived.
    """
    calls = 0
    turns = []

    def update(room, text):
        return {"room": room, "name": room, "from": "rahul-hermes", "text": text}

    async def watch(person):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "inbox_unread": 0,
                "dm_updates": [update("room-a", "first")],
                "calendar_pending": 0,
            }
        if calls == 2:
            return {
                "inbox_unread": 0,
                "dm_updates": [update("room-b", "second"), update("room-c", "third")],
                "calendar_pending": 0,
            }
        raise SystemExit(0)

    monkeypatch.setattr(personal, "watch", watch)
    runner = wake.Runner(
        "om",
        lambda reply: ([sys.executable, "-c", "pass"], {}, lambda out: out),
        "Om's agent",
        every=0.001,
        settle=0,
    )

    async def turn(now):
        turns.append(now)

    runner.turn = turn
    try:
        await runner.poll()
    except SystemExit:
        pass
    assert calls == 3
    assert len(turns) == 1
    assert "first" in turns[0] and "second" in turns[0] and "third" in turns[0]
