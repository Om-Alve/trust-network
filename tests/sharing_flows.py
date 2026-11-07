"""End-to-end sharing flows over the repository FakeSwitch harness.

These scenarios are the behavior contract for five changes:

1. per-person, per-field allow/deny permissions layered on the trust level;
2. event titles hidden unless that person explicitly opts in;
3. ``tn untrust`` / ``tn block`` with a blocked list and explicit re-add;
4. ask-around selecting its audience and never dumping ``has``/``recommends``;
5. ask-around routing the question to the recipient's own agent, or escalating
   to the person when they opted in (or when there is no agent).

Failure cases checked before the happy paths:

- a deny is ignored because the trust level would share the field;
- an allow reveals a ``private`` fact, or overrides a deny;
- ``view-as`` and the share card disagree with what ``ask`` actually returns;
- calendar titles leak by default, or the opt-in does nothing;
- ``untrust`` removes a different friendship;
- ``block`` still lets the blocked gate read facts, or ``tn trust`` re-adds a
  blocked person without ``tn unblock``;
- ask-around sends ``has``/``recommends`` in a connection room before the
  recipient's own agent or person answers;
- ask-around always escalates to the person instead of the agent;
- an audience selection is ignored, asks everyone, or accepts a missing,
  expired or foreign token;
- an audience contains a stranger, a blocked person or the owner.
"""

from __future__ import annotations

import contextlib
import io
from datetime import date
from pathlib import Path
from typing import Any

from scenario_harness import build_world, personal_session

from trustnet.gate import ledger
from trustnet.gate.brief import build_brief
from trustnet.gate.commands import Quoted
from trustnet.gate.facts import Level, load_profile, load_trust
from trustnet.gate.view_as import view_as
from trustnet.switch_client import SwitchError
from trustnet.tn import personal
from trustnet.tn.cli import main as tn_cli

QUESTION = "a tent to borrow, Nov 14-16"
CALENDAR_DAYS = (date(2026, 11, 8), date(2026, 11, 9))


def _cli(*argv: str) -> int:
    """Run one owner-local CLI command without mixing its text into the report."""
    if len(argv) == 1 and isinstance(argv[0], list | tuple):
        argv = tuple(argv[0])
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return tn_cli(list(argv))


async def _world(root: Path, patch, **kwargs):
    """Build one FakeSwitch world with the personal-agent session patched in."""
    patch.setenv("TN_CONFIG_DIR", str(root / "config"))
    world = await build_world(root, monkeypatch=patch, **kwargs)
    patch.setattr(personal, "session", personal_session(world))
    patch.setattr(personal, "_now", lambda: world.clock().timestamp())
    return world


def _reply(world, room: str) -> dict[str, str]:
    text = world.bodies(room)[-1]
    assert text, f"no reply in {room}"
    return dict(line.split(": ", 1) for line in text.splitlines())


def _ask_round_state(world, question: str) -> dict[str, Any]:
    state = world.gates["om"]._around_state()
    return next(entry for entry in state.values() if entry.get("question") == question)


async def _wait_for_question(world, question: str) -> dict[str, Any]:
    await world.wait_for(
        lambda: any(
            entry.get("question") == question
            for entry in world.gates["om"]._around_state().values()
        ),
        what=f"ask-around state for {question!r}",
    )
    return _ask_round_state(world, question)


def _has_local(world, person: str, peer: str = "om") -> bool:
    state = world.gates[person]._around_state()
    return any(key.startswith(peer + ":") and value.get("local") for key, value in state.items())


def _local_question(world, person: str, peer: str = "om") -> dict[str, Any]:
    state = world.gates[person]._around_state()
    return next(
        value for key, value in state.items() if key.startswith(peer + ":") and value.get("local")
    )


async def _expect_switch_error(action) -> str:
    try:
        await action
    except SwitchError as exc:
        return str(exc)
    raise AssertionError("expected a SwitchError")


def snapshot_files(root: Path) -> dict[str, Any]:
    """A repeatable owner-local view: trust, ask-around state and ledgers."""
    result: dict[str, Any] = {}
    for directory in sorted(Path(root).iterdir()):
        if not directory.is_dir() or directory.name == "config":
            continue
        files: dict[str, Any] = {}
        for name in (
            "trust.yaml",
            "facts.yaml",
            "ask-around.json",
            "ledger.jsonl",
        ):
            path = directory / name
            if path.exists():
                files[name] = path.read_text(encoding="utf-8")
        requests = directory / "ask-around-requests"
        if requests.is_dir():
            files["ask-around-requests"] = {
                path.name: path.read_text(encoding="utf-8") for path in sorted(requests.iterdir())
            }
        result[directory.name] = files
    return result


async def permissions_and_titles(root: Path, patch) -> dict[str, Any]:
    """A deny hides a close fact; an allow shares one; private stays private."""
    world = await _world(root, patch)

    # Rahul is close, but he may not see his own wishlist. Priya is only a
    # friend, but the owner explicitly lets her see it. The allow never reveals
    # a private fact, and a deny wins over an allow.
    assert _cli(["--as", "om", "trust", "rahul", "close", "--deny", "wishlist"]) == 0
    assert (
        _cli(
            [
                "--as",
                "om",
                "trust",
                "priya",
                "friend",
                "--allow",
                "wishlist,address",
                "--calendar-titles",
            ]
        )
        == 0
    )
    assert _cli(["--as", "om", "trust", "rahul", "close", "--allow", "wishlist"]) == 0

    rahul_room = await world.add_room("conn-om-rahul", ["om-gate", "rahul-gate"])
    priya_room = await world.add_room("conn-om-priya", ["om-gate", "priya-gate"])

    await world.say(rahul_room, "rahul-gate", "@om-gate ask diet wishlist address")
    rahul = _reply(world, rahul_room)
    assert rahul["diet"] == "vegetarian"
    assert rahul["wishlist"] == rahul["address"] == "not shared with you"

    await world.say(priya_room, "priya-gate", "@om-gate ask diet wishlist address")
    priya = _reply(world, priya_room)
    assert "Lego Millennium Falcon" in priya["wishlist"]
    assert priya["address"] == "not shared with you"

    profile = load_profile("om")
    trust = load_trust("om")
    rahul_permissions = trust.permissions_for("rahul")
    assert rahul_permissions.deny == {"wishlist"}
    assert "wishlist" in rahul_permissions.allow  # kept, but deny wins in policy

    rahul_view = view_as(profile, trust, "rahul", now=world.clock())
    priya_view = view_as(profile, trust, "priya", now=world.clock())
    assert "wishlist" not in rahul_view.visible_values
    assert "address" not in rahul_view.visible_values
    assert "wishlist" in priya_view.visible_values
    assert "address" not in priya_view.visible_values

    # Titles are hidden unless the person opted in. Priya did; Rahul did not.
    assert rahul_view.titles_visible is False
    assert {row.title for row in rahul_view.calendar} == {""}
    assert priya_view.titles_visible is True
    assert "Family video call" in {row.title for row in priya_view.calendar}

    # The gate's free command reads the same opt-in.
    await world.say(rahul_room, "rahul-gate", "@om-gate free 2026-11-08..2026-11-09")
    assert "Family video call" not in world.bodies(rahul_room)[-1]
    await world.say(priya_room, "priya-gate", "@om-gate free 2026-11-08..2026-11-09")
    assert "Family video call" in world.bodies(priya_room)[-1]

    # The share card is built from the same policy answer, including titles.
    rahul_card, rahul_disclosed = build_brief(
        profile, trust, "rahul", "dm-om-rahul-x", Quoted("plan"), CALENDAR_DAYS
    )
    priya_card, priya_disclosed = build_brief(
        profile, trust, "priya", "dm-om-priya-x", Quoted("plan"), CALENDAR_DAYS
    )
    assert "wishlist" not in rahul_disclosed and "address" not in rahul_disclosed
    assert "Family video call" not in rahul_card
    assert "wishlist" in priya_disclosed and "address" not in priya_disclosed
    assert "Family video call" in priya_card

    # Only what was actually shown is ledgered.
    fields = {entry.field for entry in ledger.read("om")}
    assert "address" not in fields
    assert "wishlist" in fields  # Priya's allowed ask
    return {
        "checks": {
            "rahul_ask": rahul,
            "priya_ask": priya,
            "rahul_visible": sorted(rahul_view.visible_values),
            "priya_visible": sorted(priya_view.visible_values),
            "rahul_titles_visible": rahul_view.titles_visible,
            "priya_titles_visible": priya_view.titles_visible,
            "ledger_fields": sorted(fields),
        },
        "transcript": world.transcript(),
        "files": snapshot_files(root),
    }


async def untrust_and_block(root: Path, patch) -> dict[str, Any]:
    """Removal is explicit, per person, and a block needs an explicit unblock."""
    world = await _world(root, patch)
    rahul_room = await world.add_room("conn-om-rahul", ["om-gate", "rahul-gate"])

    assert _cli(["--as", "om", "untrust", "rahul"]) == 0
    trust = load_trust("om")
    assert trust.level_for("rahul") is None
    assert trust.level_for("priya") is Level.FRIEND
    assert trust.is_blocked("rahul") is False

    await world.say(rahul_room, "rahul-gate", "@om-gate ask diet")
    assert world.bodies(rahul_room) == []
    assert ledger.read("om") == []

    # An untrusted person can be re-added without an unblock.
    assert _cli(["--as", "om", "trust", "rahul", "close"]) == 0
    await world.say(rahul_room, "rahul-gate", "@om-gate ask diet")
    assert _reply(world, rahul_room)["diet"] == "vegetarian"

    assert _cli(["--as", "om", "block", "rahul"]) == 0
    trust = load_trust("om")
    assert trust.is_blocked("rahul") is True
    assert trust.level_for("rahul") is None
    assert trust.level_for("priya") is Level.FRIEND

    # A blocked person cannot be re-added until the owner unblocks them.
    assert _cli(["--as", "om", "trust", "rahul", "close"]) == 1
    trust = load_trust("om")
    assert trust.is_blocked("rahul") is True and trust.level_for("rahul") is None

    # The gate stays silent: no new reply after the block.
    before = len(world.bodies(rahul_room))
    await world.say(rahul_room, "rahul-gate", "@om-gate ask diet")
    assert len(world.bodies(rahul_room)) == before

    assert _cli(["--as", "om", "unblock", "rahul"]) == 0
    assert load_trust("om").is_blocked("rahul") is False
    assert load_trust("om").level_for("rahul") is None
    assert _cli(["--as", "om", "trust", "rahul", "close"]) == 0
    trust = load_trust("om")
    assert trust.level_for("rahul") is Level.CLOSE
    assert trust.level_for("priya") is Level.FRIEND

    # Blocking one person leaves the other friendship alone.
    assert _cli(["--as", "om", "block", "priya"]) == 0
    trust = load_trust("om")
    assert trust.level_for("rahul") is Level.CLOSE
    assert trust.level_for("priya") is None and trust.is_blocked("priya") is True
    assert _cli(["--as", "om", "blocked"]) == 0
    return {
        "checks": {
            "blocked": list(trust.blocked),
            "people": {name: level.value for name, level in trust.people.items()},
            "final_rahul": trust.level_for("rahul").value,
        },
        "transcript": world.transcript(),
        "files": snapshot_files(root),
    }


async def ask_around_routes_to_agent_or_person(root: Path, patch) -> dict[str, Any]:
    """No profile dump: the recipient's own side answers, or the person opts in."""
    world = await _world(root, patch)
    # Priya wants ask-around questions from Om to reach her directly. Rahul
    # leaves the default: route to his own agent, not straight to him.
    assert _cli(["--as", "priya", "trust", "om", "friend", "--ask-around", "person"]) == 0
    await world.start()
    try:
        await personal.ask_around("om", QUESTION)
        entry = await _wait_for_question(world, QUESTION)
        await world.wait_for(
            lambda: _has_local(world, "rahul") and _has_local(world, "priya"),
            what="both home questions",
        )

        # No automatic has/recommends reply crossed the connection rooms.
        assert entry.get("answers") == {}
        for room in world.rooms_named("conn-om-"):
            bodies = [message["body"] for message in room["messages"]]
            assert all("Profile lists" not in body for body in bodies)
            assert all(not body.startswith("has:") for body in bodies)

        rahul_ask = _local_question(world, "rahul")
        priya_ask = _local_question(world, "priya")
        rahul_home = world.home_bodies("rahul")[-1]
        priya_home = world.home_bodies("priya")[-1]
        assert "Your agent can reply" in rahul_home
        assert "Your agent can reply" not in priya_home
        assert "Reply with answer" in priya_home

        await personal.answer("rahul", rahul_ask["local"], "Rahul has no tent to lend")
        await personal.answer("priya", priya_ask["local"], "Priya's tent is free that weekend")
        await world.wait_for(
            lambda: set(_ask_round_state(world, QUESTION).get("answers", {})) == {"rahul", "priya"},
            what="both own-side answers",
        )
        answers = _ask_round_state(world, QUESTION)["answers"]
        assert answers["rahul"] == "Rahul has no tent to lend"
        assert answers["priya"] == "Priya's tent is free that weekend"
        assert any("Rahul has no tent" in body for body in world.home_bodies("om"))

        # Neither gate disclosed a has/recommends fact before the answer.
        rahul_fields = {record.field for record in ledger.read("rahul")}
        priya_fields = {record.field for record in ledger.read("priya")}
        assert "has" not in rahul_fields and "recommends" not in rahul_fields
        assert "has" not in priya_fields and "recommends" not in priya_fields
        assert "ask-around-answer" in rahul_fields
        assert "ask-around-answer" in priya_fields

        # Opting out means the question is stored but the person is not pinged.
        assert _cli(["--as", "rahul", "trust", "om", "close", "--ask-around", "off"]) == 0
        before = len(world.home_bodies("rahul"))
        second = "a ladder to borrow, Nov 20"
        await personal.ask_around("om", second)
        await _wait_for_question(world, second)
        await world.wait_for(
            lambda: any(
                value.get("question") == second
                for value in world.gates["rahul"]._around_state().values()
            ),
            what="Rahul's stored off-route question",
        )
        assert len(world.home_bodies("rahul")) == before
        return {
            "checks": {
                "answers": answers,
                "rahul_home": rahul_home,
                "priya_home": priya_home,
                "off_route_stayed_quiet": True,
            },
            "transcript": world.transcript(),
            "files": snapshot_files(root),
        }
    finally:
        await world.stop()


async def ask_around_escalates_without_an_agent(root: Path, patch) -> dict[str, Any]:
    """With no registered agent, the question falls back to the person."""
    world = await _world(root, patch)
    home = world.homes["priya"]
    world.switch.rooms[home]["members"].discard("priya-hermes")
    world.identities.pop("priya-hermes", None)
    await world.start()
    try:
        await personal.ask_around("om", QUESTION)
        await _wait_for_question(world, QUESTION)
        await world.wait_for(
            lambda: _local_question(world, "priya"), what="Priya's escalated question"
        )
        body = world.home_bodies("priya")[-1]
        assert "Reply with answer" in body
        assert "Your agent" not in body

        question = _local_question(world, "priya")
        await world.say(
            home,
            "priya",
            f'@priya-gate answer {question["local"]} "Ask me again next week"',
            kind="user",
        )
        await world.wait_for(
            lambda: (
                _ask_round_state(world, QUESTION)["answers"].get("priya")
                == "Ask me again next week"
            ),
            what="the person's own answer",
        )
        return {
            "checks": {
                "home": body,
                "answer": _ask_round_state(world, QUESTION)["answers"]["priya"],
            },
            "transcript": world.transcript(),
            "files": snapshot_files(root),
        }
    finally:
        await world.stop()


async def ask_around_audience_selection(root: Path, patch) -> dict[str, Any]:
    """A selection asks only that audience; a bad or forged selection fails closed."""
    world = await _world(root, patch)
    await world.start()
    try:
        priya_before = list(world.home_bodies("priya"))
        await personal.ask_around("om", QUESTION, audience=["rahul"])
        entry = await _wait_for_question(world, QUESTION)
        assert set(entry["peers"]) == {"rahul"}
        assert entry.get("audience") == ["rahul"]
        assert world.home_bodies("priya") == priya_before
        assert not any(
            value.get("peer") == "om" for value in world.gates["priya"]._around_state().values()
        )
        priya_conn = world.rooms_named("conn-om-priya")
        assert all(
            "ask-around" not in message["body"]
            for room in priya_conn
            for message in room["messages"]
        )

        second = "a projector for Friday"
        await personal.ask_around("om", second, audience=["priya"])
        second_entry = await _wait_for_question(world, second)
        assert set(second_entry["peers"]) == {"priya"}
        assert second_entry["audience"] == ["priya"]

        # A stranger, the owner and an empty list are refused before anything
        # is posted; duplicates collapse to one target.
        assert "no friend named dev" in await _expect_switch_error(_run_ask("om", "x", ["dev"]))
        assert "audience" in (await _expect_switch_error(_run_ask("om", "x", []))).lower()
        assert "cannot ask yourself" in await _expect_switch_error(_run_ask("om", "x", ["om"]))
        await personal.ask_around("om", "a duplicate", audience=["rahul", "rahul"])
        duplicated = await _wait_for_question(world, "a duplicate")
        assert duplicated["audience"] == ["rahul"]

        # A missing request token is refused in home and asks nobody.
        home_before = len(world.home_bodies("om"))
        await world.say(
            world.homes["om"],
            "om",
            '@om-gate ask-around A999 "a forged selection"',
            kind="user",
        )
        assert len(world.home_bodies("om")) == home_before + 1
        assert world.home_bodies("om")[-1] == (
            "A999 not sent: that ask-around audience request is missing or expired."
        )
        return {
            "checks": {
                "first_audience": entry["audience"],
                "second_audience": second_entry["audience"],
                "priya_untouched": True,
                "forged": world.home_bodies("om")[-1],
            },
            "transcript": world.transcript(),
            "files": snapshot_files(root),
        }
    finally:
        await world.stop()


async def _run_ask(person: str, question: str, audience: list[str]) -> None:
    await personal.ask_around(person, question, audience=audience)


SCENARIOS = (
    permissions_and_titles,
    untrust_and_block,
    ask_around_routes_to_agent_or_person,
    ask_around_escalates_without_an_agent,
    ask_around_audience_selection,
)
