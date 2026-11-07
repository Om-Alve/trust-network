"""Run with ``uv run python -m scripts.e2e_facts_scenarios``.

Every scenario runs offline on ``FakeSwitch`` with the real gates: facts at
each trust level, a mixed-level DM room, blanked titles, a stranger, overreach
dedupe, CLI/MCP fact tightening, gifts and claims, ask-around, MCP bad input
and ``tn wake``. No Switch, no keys, no live process is touched.

Writes one transcript per scenario and a PASS/FAIL summary under
``data/scenarios-facts-<nanoseconds>/``. ``data/`` is gitignored.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import time
import traceback
from contextlib import asynccontextmanager, redirect_stderr
from datetime import datetime
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from mcp import StdioServerParameters  # noqa: E402
from mcp.client.session import ClientSession  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402
from scenario_harness import build_world, personal_session  # noqa: E402

from trustnet.gate import ledger, surprise  # noqa: E402
from trustnet.gate.calendar import TIME_ZONE  # noqa: E402
from trustnet.gate.facts import Level, load_profile  # noqa: E402
from trustnet.gate.policy import visible_facts  # noqa: E402
from trustnet.gate.view_as import format_value  # noqa: E402
from trustnet.switch_client import SwitchError  # noqa: E402
from trustnet.tn import cli, mcp, personal, wake  # noqa: E402

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=TIME_ZONE)
LEVELS = ("acquaintance", "friend", "close")
OCCASION = "2026-11-20"


@asynccontextmanager
async def world_for(base: Path, name: str, **kwargs):
    """Build a world in ``base/name`` and always restore its process hooks."""
    old = os.environ.get("TN_DATA_DIR")
    world = await build_world(base / name, now=NOW, **kwargs)
    try:
        yield world
    finally:
        await world.stop()
        world.restore()
        if old is None:
            os.environ.pop("TN_DATA_DIR", None)
        else:
            os.environ["TN_DATA_DIR"] = old


def _lines(body: str) -> dict[str, str]:
    return dict(line.split(": ", 1) for line in body.splitlines())


def _room(world, name: str) -> str:
    return world.room_named(name)["room_id"]


async def facts_levels(base: Path) -> dict:
    checks, transcript = {}, {}
    for level in LEVELS:
        async with world_for(base, f"levels-{level}", trust={"om": {"rahul": level}}) as world:
            room = await world.add_room("conn-om-rahul", ["om-gate", "rahul-gate"])
            before = len(ledger.read("om"))
            fields = " ".join([*load_profile("om").facts, "salary"])
            await world.say(room, "rahul-gate", "@om-gate ask " + fields)
            lines = _lines(world.bodies(room)[-1])
            profile = load_profile("om")
            allowed = visible_facts(profile, Level(level))
            assert set(lines) == set(profile.facts) | {"salary"}
            for name, value in allowed.items():
                assert lines[name] == format_value(value), (level, name)
            for name, line in lines.items():
                if name not in allowed:
                    assert line == "not shared with you", (level, name)
            assert lines["address"] == lines["salary"]
            entries = ledger.read("om")[before:]
            assert {entry.field for entry in entries} == set(allowed), level

            await world.say(world.homes["om"], "om", "@om-gate view-as rahul", kind="user")
            rendered = world.home_bodies("om")[-1]
            for name, value in allowed.items():
                assert any(
                    line.strip().startswith(f"✅ {name}") and format_value(value) in line
                    for line in rendered.splitlines()
                ), (level, name)
            for name in set(profile.facts) - set(allowed):
                assert any(
                    line.strip().startswith(f"❌ {name}") for line in rendered.splitlines()
                ), (level, name)
            checks[level] = {
                "visible": sorted(allowed),
                "hidden": sorted(set(profile.facts) - set(allowed) | {"salary"}),
                "reply": world.bodies(room)[-1],
                "view_as": rendered,
                "notes": world.home_bodies("om")[:-1],
            }
            transcript[level] = world.transcript()
    return {"checks": checks, "transcripts": transcript}


async def facts_mixed_room(base: Path) -> dict:
    async with world_for(
        base, "mixed-room", trust={"om": {"rahul": "close", "priya": "friend"}}
    ) as world:
        room = await world.add_room(
            "dm-om-rahul-priya-plan",
            ["om-gate", "rahul-gate", "priya-gate", "om-hermes", "rahul-hermes", "priya-hermes"],
        )
        await world.say(room, "rahul-hermes", "@om-gate ask diet wishlist address")
        lines = _lines(world.bodies(room)[-1])
        assert lines["diet"] == "vegetarian"
        assert lines["wishlist"] == lines["address"] == "not shared with you"
        assert {entry.field for entry in ledger.read("om")} == {"diet"}
        notes = world.home_bodies("om")
        assert any("wishlist (close)" in note for note in notes)
        assert any("address (private)" in note for note in notes)
        return {
            "checks": {"reply": world.bodies(room)[-1], "notes": notes},
            "transcripts": {"room": world.transcript()},
        }


async def facts_free_and_stranger(base: Path) -> dict:
    checks, transcripts = {}, {}
    async with world_for(
        base,
        "free-stranger",
        trust={"om": {"rahul": "close", "dev": "acquaintance"}},
        strangers=("dev", "eve"),
    ) as world:
        acq = await world.add_room("conn-om-dev", ["om-gate", "dev-gate"])
        close = await world.add_room("conn-om-rahul", ["om-gate", "rahul-gate"])
        for room, sender in ((acq, "dev-gate"), (close, "rahul-gate")):
            await world.say(room, sender, "@om-gate free 2026-11-08..2026-11-09")
        checks["acquaintance_free"] = world.bodies(acq)[-1]
        checks["friend_free"] = world.bodies(close)[-1]
        assert "busy" in checks["acquaintance_free"]
        assert "Family video call" not in checks["acquaintance_free"]
        assert "busy" in checks["friend_free"]
        assert "Family video call" not in checks["friend_free"]

        probe = await world.add_room("probe", ["om-gate", "eve-hermes"])
        ledger_before = len(ledger.read("om"))
        await world.say(probe, "eve-hermes", "@om-gate ask diet address")
        await world.say(probe, "eve-hermes", "@om-gate free 2026-11-08")
        assert world.bodies(probe) == []
        assert len(ledger.read("om")) == ledger_before
        checks["stranger_silent"] = True
        transcripts["world"] = world.transcript()
    return {"checks": checks, "transcripts": transcripts}


async def overreach_dedupe(base: Path) -> dict:
    async with world_for(base, "overreach", trust={"om": {"rahul": "close"}}) as world:
        room = await world.add_room("probe", ["om-gate", "rahul-gate"])

        def notes():
            return [body for body in world.home_bodies("om") if "side asked for" in body]

        await world.say(room, "rahul-gate", "@om-gate ask address")
        await world.say(room, "rahul-gate", "@om-gate ask address")
        assert len(notes()) == 1
        world.clock.advance(minutes=9)
        await world.say(room, "rahul-gate", "@om-gate ask address")
        assert len(notes()) == 1
        world.clock.advance(minutes=1)
        await world.say(room, "rahul-gate", "@om-gate ask address")
        assert len(notes()) == 2
        await world.say(room, "rahul-gate", "@om-gate ask salary")
        assert len(notes()) == 3
        return {
            "checks": {"notes": notes()},
            "transcripts": {"world": world.transcript()},
        }


async def fact_set_refusals(base: Path) -> dict:
    async with world_for(base, "fact-set") as world:
        before = load_profile("om").facts["drinks"].level.value

        stderr = StringIO()
        with redirect_stderr(stderr):
            code = cli.main(["--as", "om", "fact", "set", "drinks", "--level", "acquaintance"])
        assert code == 1 and "refusing to loosen" in stderr.getvalue()
        assert load_profile("om").facts["drinks"].level.value == before

        try:
            mcp._run_cli("om", "fact", "set", "drinks", "--level", "acquaintance")
        except ToolError as exc:
            assert "refusing to loosen" in str(exc)
        else:  # pragma: no cover - a refused edit is the whole point
            raise AssertionError("the MCP fact_set loosened a fact")
        assert load_profile("om").facts["drinks"].level.value == before

        tightened = mcp._run_cli("om", "fact", "set", "drinks", "--level", "close")
        assert tightened["level"] == "close"
        assert load_profile("om").facts["drinks"].level.value == "close"
        return {
            "checks": {
                "cli_refusal": stderr.getvalue().strip(),
                "mcp_refusal": "refusing to loosen",
                "after": tightened,
            },
            "transcripts": {"world": world.transcript()},
        }


async def gifts_and_claims(base: Path) -> dict:
    async with world_for(
        base, "gifts", trust={"om": {"rahul": "close", "priya": "close"}}
    ) as world:
        old_session = personal.session
        personal.session = personal_session(world)
        await world.start()
        try:
            home_before = list(world.home_bodies("om"))
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

            claimed = await personal.claim("rahul", "om", "Lego Millennium Falcon")
            assert claimed["status"] == "claimed"
            try:
                await personal.claim("priya", "om", "Lego Millennium Falcon")
            except SwitchError as exc:
                second_claim = str(exc)
                assert "Item unavailable" in second_claim
            else:  # pragma: no cover
                raise AssertionError("two askers claimed the same item")
            third = await personal.gift_ideas("priya", "om", "birthday", OCCASION, 3000)
            assert third["taken"] == [{"item": "Lego Millennium Falcon", "status": "taken"}]
            assert [item["item"] for item in third["suggestions"]] == ["Hario V60"]
            assert world.home_bodies("om") == home_before

            rahul_room = world.rooms_named("gift-rahul-om-")[0]
            await world.wait_for(lambda: rahul_room["archived"], what="claimed room archived")

            on = datetime(2026, 11, 20, 12, 0, tzinfo=TIME_ZONE)
            after = datetime(2026, 11, 21, 12, 0, tzinfo=TIME_ZONE)
            sealed = ledger.format_ledger(person="om", now=on)
            opened = ledger.format_ledger(person="om", now=after)
            assert "sealed entr" in sealed and "opens Nov 21" in sealed
            assert "sealed entr" not in opened and "gift" in opened

            # A separate, still-open gift room is where a fact request is
            # refused and where malformed input must not raise out of dispatch.
            idle = world.rooms_named("gift-priya-om-")[0]
            home_notes_before = list(world.home_bodies("om"))
            await world.say(idle["id"], "priya-gate", "@om-gate ask diet address")
            ask_refused = world.bodies(idle["id"])[-1]
            assert all(line.endswith("not shared with you") for line in ask_refused.splitlines())
            assert world.home_bodies("om") == home_notes_before
            await world.say(idle["id"], "priya-gate", "@om-gate ask")
            await world.say(idle["id"], "priya-gate", "@om-gate claim")
            assert world.home_bodies("om") == home_notes_before

            world.clock.advance(minutes=11)
            await surprise.expire(world.gates["om"])
            await surprise.expire(world.gates["priya"])
            assert idle["archived"]
            return {
                "checks": {
                    "ideas": first,
                    "second_ask": second,
                    "claim": claimed,
                    "double_claim": second_claim,
                    "after_claim": third,
                    "recipient_home_unchanged": True,
                    "sealed": sealed,
                    "opened": opened,
                    "ask_refused": ask_refused,
                    "idle_room_archived": idle["archived"],
                },
                "transcripts": {"world": world.transcript()},
            }
        finally:
            personal.session = old_session
            await world.stop()


def _local_question(world, person: str):
    return next(
        value for value in world.gates[person]._around_state().values() if value.get("local")
    )


async def ask_around(base: Path) -> dict:
    async with world_for(base, "around") as world:
        old_session = personal.session
        personal.session = personal_session(world)
        await world.start()
        try:
            await personal.ask_around("om", "a tent to borrow, Nov 14-16")
            await world.wait_for(
                lambda: any(
                    entry.get("question") == "a tent to borrow, Nov 14-16"
                    for entry in world.gates["om"]._around_state().values()
                ),
                what="the ask-around fan-out",
            )
            ref, entry = next(
                (ref, entry)
                for ref, entry in world.gates["om"]._around_state().items()
                if entry.get("question") == "a tent to borrow, Nov 14-16"
            )
            assert entry.get("answers") == {}
            await world.wait_for(
                lambda: all(_local_question(world, person) for person in ("rahul", "priya")),
                what="both home questions",
            )
            assert all(
                "Profile lists" not in message["body"]
                for room in world.rooms_named("conn-om-")
                for message in room["messages"]
            )

            rahul = _local_question(world, "rahul")
            priya = _local_question(world, "priya")
            await personal.answer("rahul", rahul["local"], "no, sorry")
            await personal.answer(
                "priya", priya["local"], "Priya has a 2-person tent, no promise to lend"
            )
            await world.wait_for(
                lambda: len(world.gates["om"]._around_state()[ref].get("answers", {})) == 2,
                what="both own-side answers",
            )
            entry = world.gates["om"]._around_state()[ref]
            assert set(entry["answers"]) == {"rahul", "priya"}
            assert "2-person tent" in entry["answers"]["priya"]
            assert "2-person tent" not in entry["answers"]["rahul"]

            expected = dict(world.gates["om"]._around_state()[ref]["answers"])
            probe = await world.add_room("probe-forged", ["om-gate", "rahul-gate"])
            await world.say(probe, "rahul-gate", f'@om-gate answer {ref} "forged"')
            assert world.bodies(probe) == ["Not allowed."]
            world.clock.advance(minutes=8 * 24 * 60)
            await world.say(
                entry["peers"]["rahul"], "rahul-gate", f'@om-gate answer {ref} "too late"'
            )
            assert world.gates["om"]._around_state()[ref]["answers"] == expected
            return {
                "checks": {
                    "answers": expected,
                    "conn_rooms": sorted(room["name"] for room in world.rooms_named("conn-om-")),
                    "forged_reply": world.bodies(probe)[-1],
                    "late_reply_ignored": True,
                },
                "transcripts": {"world": world.transcript()},
            }
        finally:
            personal.session = old_session
            await world.stop()


async def around_long_list(base: Path) -> dict:
    long_item = "a very long list of camping things " * 5
    async with world_for(
        base,
        "around-long",
        facts={"priya": {"has": {"value": [long_item], "level": "friend"}}},
    ) as world:
        old_session = personal.session
        personal.session = personal_session(world)
        await world.start()
        try:
            await personal.ask_around("om", "a tent to borrow, Nov 14-16")
            await world.wait_for(
                lambda: any(
                    entry.get("question") == "a tent to borrow, Nov 14-16"
                    for entry in world.gates["om"]._around_state().values()
                ),
                what="the ask-around fan-out",
            )
            entry = next(
                entry
                for entry in world.gates["om"]._around_state().values()
                if entry.get("question") == "a tent to borrow, Nov 14-16"
            )
            assert entry.get("answers") == {}
            assert all(
                long_item not in message["body"]
                for room in world.rooms_named("conn-om-")
                for message in room["messages"]
            )
            return {
                "checks": {
                    "answers": entry.get("answers", {}),
                    "profile_dumped": False,
                },
                "transcripts": {"world": world.transcript()},
            }
        finally:
            personal.session = old_session
            await world.stop()


async def mcp_bad_input(base: Path) -> dict:
    tmp = (base / "mcp").resolve()
    for person in ("om", "rahul", "priya"):
        shutil.copytree(ROOT / "examples" / person, tmp / person)
    env = {
        "PATH": os.environ["PATH"],
        "HOME": os.environ["HOME"],
        "TN_DATA_DIR": str(tmp),
    }
    cases = [
        ("dm", {"friend": "nobody", "goal": "x"}, "no friend named nobody"),
        ("dm", {"friend": "rahul", "goal": ""}, "quoted text must not be empty"),
        ("answer", {"id": "nope", "text": "yes"}, "invalid reference"),
        ("answer", {"id": "P1", "text": "maybe"}, 'must be "yes" or "no"'),
        ("ask_around", {"question": "x" * 200}, "140 characters or fewer"),
        ("ask", {"friend": "rahul", "fields": []}, "ask needs at least one fact"),
        (
            "gift_ideas",
            {"friend": "nobody", "occasion": "birthday", "date": OCCASION, "budget": 1},
            "no friend named nobody",
        ),
        (
            "gift_ideas",
            {"friend": "rahul", "occasion": "birthday", "date": "not a date", "budget": 1},
            "could not read the date",
        ),
        ("claim", {"friend": "rahul", "item": ""}, "a claim needs an item"),
        ("fact_set", {"key": "drinks", "level": "acquaintance"}, "refusing to loosen"),
        (
            "cal_add",
            {"start": "nonsense", "duration": "2h", "title": "x", "place": "y"},
            "could not read the start",
        ),
        (
            "gift_ideas",
            {"friend": "rahul", "occasion": "birthday", "date": OCCASION, "budget": "lots"},
            "validation error",
        ),
    ]
    checks = {}
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "trustnet.tn.mcp", "--as", "om"],
        env=env,
        cwd=str(tmp),
    )
    with open(os.devnull, "w") as errlog:
        async with stdio_client(params, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for tool, arguments, expected in cases:
                    result = await session.call_tool(tool, arguments)
                    text = "".join(
                        block.text for block in result.content if getattr(block, "text", None)
                    )
                    assert result.is_error and expected in text, (tool, text)
                    assert "Traceback" not in text
                    checks[f"{tool} {sorted(arguments)[:2]}"] = text[:160]

                result = await session.call_tool(
                    "cal_add",
                    {
                        "start": "2026-11-08T21:00",
                        "duration": "2h",
                        "title": "Café ☕",
                        "place": "The Park, MG Road",
                    },
                )
                assert not result.is_error
                checks["unicode_cal_add"] = json.loads(
                    "".join(block.text for block in result.content if getattr(block, "text", None))
                )["title"]
    return {"checks": checks, "transcripts": {}}


async def wake_runner(base: Path) -> dict:
    old = os.environ.get("TN_DATA_DIR")
    os.environ["TN_DATA_DIR"] = str(base / "wake")
    (base / "wake").mkdir(parents=True, exist_ok=True)
    try:
        runner = wake.Runner(
            "om",
            lambda reply: (
                [sys.executable, "-c", "import sys; sys.stdin.read(); sys.exit(3)"],
                {},
                lambda out: out,
            ),
            "Om's agent",
            15.0,
        )
        await runner.turn("news one")
        assert runner.carry == ["news one"]

        captured = (base / "wake" / "prompt.txt").resolve()
        code = f"import sys; open({str(captured)!r}, 'w').write(sys.stdin.read()); print('done')"
        runner.invoke = lambda reply: ([sys.executable, "-c", code], {}, lambda out: out)
        await runner.turn("news two")
        prompt = captured.read_text()
        assert "news one" in prompt and "news two" in prompt and runner.carry == []

        first = wake.lock("om")
        try:
            try:
                wake.lock("om")
            except SystemExit as exc:
                second_runner = str(exc)
            else:  # pragma: no cover
                raise AssertionError("a second wake runner was allowed")
        finally:
            first.close()

        async def ignore(_text):
            return None

        silent = wake.Runner(
            "om",
            lambda reply: (
                [sys.executable, "-c", "print('[SILENT]')"],
                {},
                lambda out: out,
            ),
            "Om's agent",
            15.0,
            on_reply=ignore,
        )
        await silent.turn("nothing")
        assert silent.transcript == []

        reply = wake.opencode_reply(
            "\n".join(
                [
                    '{"type":"text","part":{"messageID":"m1","text":"first"}}',
                    "null",
                    "[1,2]",
                    '{"type":"text","part":{"messageID":"m2","text":"second "}}',
                    '{"type":"text","part":{"messageID":"m2","text":"message"}}',
                ]
            )
        )
        assert reply == "second message"
        return {
            "checks": {
                "carried_prompt": captured.read_text()[-400:],
                "second_runner": second_runner,
                "silent": True,
                "opencode_reply": reply,
            },
            "transcripts": {},
        }
    finally:
        if old is None:
            os.environ.pop("TN_DATA_DIR", None)
        else:
            os.environ["TN_DATA_DIR"] = old


SCENARIOS = (
    ("facts-levels", facts_levels),
    ("facts-mixed-room", facts_mixed_room),
    ("facts-free-and-stranger", facts_free_and_stranger),
    ("overreach-dedupe", overreach_dedupe),
    ("fact-set-refusals", fact_set_refusals),
    ("gifts-and-claims", gifts_and_claims),
    ("ask-around", ask_around),
    ("ask-around-long-list", around_long_list),
    ("mcp-bad-input", mcp_bad_input),
    ("tn-wake", wake_runner),
)


def _render(report: dict) -> str:
    lines = [json.dumps(report.get("checks", {}), indent=2, ensure_ascii=False)]
    for name, transcript in report.get("transcripts", {}).items():
        lines.append(f"\n--- {name} ---")
        lines.append(json.dumps(transcript, indent=2, ensure_ascii=False))
    return "\n".join(lines) + "\n"


async def run() -> int:
    output = Path(f"data/scenarios-facts-{time.time_ns()}")
    data = output / "data"
    data.mkdir(parents=True)
    results = []
    for name, scenario in SCENARIOS:
        started = time.monotonic()
        try:
            report = await scenario(data)
            status = "PASS"
        except Exception as exc:  # a scenario failure is the artifact's job to report
            report = {
                "checks": {"error": f"{type(exc).__name__}: {exc}"},
                "transcripts": {"traceback": traceback.format_exc()},
            }
            status = "FAIL"
        elapsed = time.monotonic() - started
        (output / f"{name}.txt").write_text(_render(report))
        results.append((name, status, elapsed, report.get("checks", {})))
        print(f"{status} {name} ({elapsed:.2f}s)")
        if status == "FAIL":
            print(json.dumps(report["checks"], indent=2)[:2000])

    summary = [
        f"scenarios-facts {time.strftime('%Y-%m-%dT%H:%M:%S')}",
        *(f"{status} {name} ({elapsed:.2f}s)" for name, status, elapsed, _ in results),
        f"{sum(status == 'PASS' for _, status, _, _ in results)}/{len(results)} passed",
    ]
    (output / "summary.txt").write_text("\n".join(summary) + "\n")
    print("\n" + "\n".join(summary))
    print(f"artifacts: {output}")
    return 0 if all(status == "PASS" for _, status, _, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
