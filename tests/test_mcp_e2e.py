"""End-to-end: a real ``python -m trustnet.tn.mcp`` stdio server, driven by the MCP SDK.

The MCP client below is the real client over real stdio; the server is a separate
process. Only the Switch server is replaced: a loopback adapter serves the narrow
wire protocol ``trustnet.switch_client`` speaks, backed by the same ``FakeSwitch``
the other tests use. The phase 14/15 gates run in this process against it.

Failure modes the test is built around, before any happy path:
- anything the tools or the CLI print reaches stdout and breaks the protocol;
- the server exposes more than its purpose-built tools (a raw Switch or file tool);
- ``dm_read``/``dm_post`` reach a room the caller does not belong to, or a non-DM room;
- ``fact_set`` loosens a fact;
- a registration key leaks into the artifact or the server log;
- ``inbox``'s consumed cursor is not persisted, so a second poll re-delivers.

The run ends in the pytest temporary directory at ``mcp-e2e/<timestamp>/transcript.json``: tool list and
descriptions, every call, the DM transcript, both inboxes, coordination, ledgers,
calendars and share cards.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml
from fakes.fake_switch import FakeSwitch
from fakes.loopback_switch import LoopbackSwitch, serve
from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client

from trustnet.gate.dm import main_agent
from trustnet.gate.policy import Identity
from trustnet.gate.runtime import Gate

PERSONS = ("om", "rahul")
TOOLS = {
    "gift_ideas",
    "claim",
    "ask",
    "inbox",
    "answer",
    "dm",
    "dm_read",
    "dm_post",
    "ask_around",
    "cal_add",
    "cal_apply",
    "fact_set",
    "fact_add",
    "fact_share_request",
    "fact_share_approve",
    "fact_share_decline",
    "trust_suggest",
    "review",
    "calendar_tasks",
    "calendar_report",
    "status",
    "group_plan_create",
    "group_plan_vote",
    "group_plan_revise",
    "group_plan_cancel",
    "group_plans",
    "group_plan_status",
}


async def _wait_for(predicate, *, timeout=10.0, what="gate state"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"timed out waiting for {what}")


async def _call(session, transcript, name, arguments=None):
    result = await session.call_tool(name, arguments or {})
    text = "".join(block.text for block in result.content if getattr(block, "text", None))
    entry = {"tool": name, "arguments": arguments or {}, "is_error": bool(result.is_error)}
    if result.is_error:
        entry["error"] = text
        transcript.append(entry)
        return False, text
    entry["result"] = json.loads(text)
    transcript.append(entry)
    return True, entry["result"]


def _bodies(threads):
    return [thread["root"]["body"] for thread in threads]


def _coordination(tmp_path, person):
    path = tmp_path / person / "coordination.json"
    return json.loads(path.read_text()) if path.exists() else {}


def _fact_level(tmp_path, person, key):
    data = yaml.safe_load((tmp_path / person / "facts.yaml").read_text())
    return data["facts"][key]["level"]


async def test_mcp_stdio_end_to_end(tmp_path, monkeypatch):
    root = Path.cwd()
    artifact_dir = tmp_path / "mcp-e2e" / str(time.time_ns())
    artifact = {
        "description": "tn mcp over real stdio against a loopback Switch and fake gates",
        "tools": [],
        "calls": [],
        "checks": {},
    }

    for person in PERSONS:
        shutil.copytree(
            root / "examples" / person,
            tmp_path / person,
            ignore=shutil.ignore_patterns("ledger.jsonl", "share-cards"),
        )
    monkeypatch.setenv("TN_DATA_DIR", str(tmp_path))

    switch = FakeSwitch()
    switch.agents.update(
        {
            agent: {"id": agent, "name": agent, "owner_id": agent.split("-")[0]}
            for agent in ("om-gate", "rahul-gate", "om-hermes", "rahul-hermes")
        }
    )
    identities = {p: Identity.user(p) for p in PERSONS}
    identities.update({a: Identity.agent(a, d["owner_id"]) for a, d in switch.agents.items()})
    gate_clients = {p: switch.client(p + "-gate", p) for p in PERSONS}
    homes = {}
    for person, client in gate_clients.items():
        homes[person] = (
            await client.create_room(
                person + "-home",
                "Trust network home",
                [person + "-gate", main_agent(person)],
                internal_only=True,
            )
        )["room_id"]
    gates = {person: Gate(person, gate_clients[person], lambda: identities) for person in PERSONS}
    gate_tasks = [asyncio.create_task(gate.run()) for gate in gates.values()]

    keys = {f"canary-om-{time.time_ns()}": "om", f"canary-rahul-{time.time_ns()}": "rahul"}
    url, stop = await serve(LoopbackSwitch(switch, keys).app())
    token = {person: key for key, person in keys.items()}
    env = {
        **os.environ,
        "SWITCH_URL": url,
        "OM_GATE_KEY": token["om"],
        "RAHUL_GATE_KEY": token["rahul"],
        "TN_DATA_DIR": str(tmp_path),
        "NO_PROXY": "127.0.0.1,localhost",
    }
    env.pop("TN_PERSON", None)
    log = (tmp_path / "server.log").open("w+")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "trustnet.tn.mcp", "--as", "om"],
        env=env,
        cwd=str(tmp_path),
    )
    try:
        async with stdio_client(params, errlog=log) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                listed = await session.list_tools()
                artifact["tools"] = [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "schema": tool.input_schema,
                    }
                    for tool in listed.tools
                ]
                assert {tool.name for tool in listed.tools} == TOOLS

                ok, empty = await _call(session, artifact["calls"], "inbox")
                assert ok and empty["threads"] == [] and empty["room"] == homes["om"]

                ok, posted = await _call(
                    session, artifact["calls"], "dm", {"friend": "rahul", "goal": "Sunday bowling"}
                )
                assert ok and posted["event_id"]
                await _wait_for(
                    lambda: any(
                        r["name"].startswith("dm-om-rahul-") for r in switch.rooms.values()
                    ),
                    what="the DM room",
                )
                room = next(
                    r for r in switch.rooms.values() if r["name"].startswith("dm-om-rahul-")
                )
                await _wait_for(
                    lambda: (
                        room["id"] in gates["om"].watches and room["id"] in gates["rahul"].watches
                    ),
                    what="both gates to set up the DM",
                )
                assert {
                    "om-gate",
                    "rahul-gate",
                    "om-hermes",
                    "rahul-hermes",
                } <= room["members"]
                cards = [
                    tmp_path / person / "share-cards" / f"{room['id']}.json" for person in PERSONS
                ]
                assert all(card.exists() for card in cards)
                artifact["checks"]["dm_members"] = sorted(room["members"])
                artifact["checks"]["share_cards"] = {
                    person: json.loads(card.read_text())
                    for person, card in zip(PERSONS, cards, strict=True)
                }

                ok, telling = await _call(session, artifact["calls"], "inbox")
                assert ok
                bodies = _bodies(telling["threads"])
                assert any(room["id"] in body for body in bodies)
                assert any("Share card" in body for body in bodies)
                artifact["checks"]["first_inbox"] = bodies

                ok, consumed = await _call(session, artifact["calls"], "inbox")
                assert ok and consumed["threads"] == []

                line = "Om likes bowling. Sunday at 9pm?"
                ok, _ = await _call(
                    session, artifact["calls"], "dm_post", {"room": room["id"], "text": line}
                )
                assert ok and room["messages"][-1]["body"] == line

                ok, transcript = await _call(
                    session, artifact["calls"], "dm_read", {"room": room["id"]}
                )
                assert ok and _bodies(transcript["threads"])[-1] == line

                ok, _ = await _call(
                    session,
                    artifact["calls"],
                    "dm_post",
                    {"room": room["id"], "text": '@om-gate ask-owner Q1 "Is 1500 each okay?"'},
                )
                assert ok
                await _wait_for(lambda: "Q1" in _coordination(tmp_path, "om"), what="Q1")

                ok, asking = await _call(session, artifact["calls"], "inbox")
                assert ok and any(body.startswith("Q1:") for body in _bodies(asking["threads"]))

                ok, _ = await _call(
                    session,
                    artifact["calls"],
                    "answer",
                    {"id": "Q1", "text": "Yes, 1500 each is okay."},
                )
                assert ok
                answer = 'Q1 answer from om: "Yes, 1500 each is okay."'
                await _wait_for(
                    lambda: answer in [m["body"] for m in room["messages"]], what="the answer"
                )
                ok, answered = await _call(
                    session, artifact["calls"], "dm_read", {"room": room["id"]}
                )
                assert ok and answer in _bodies(answered["threads"])

                ok, refused = await _call(
                    session, artifact["calls"], "dm_read", {"room": homes["om"]}
                )
                assert not ok and "An active DM membership is required" in refused
                ok, refused = await _call(
                    session, artifact["calls"], "dm_post", {"room": homes["om"], "text": "no"}
                )
                assert not ok and "An active DM membership is required" in refused
                ok, refused = await _call(
                    session, artifact["calls"], "dm_read", {"room": homes["rahul"]}
                )
                assert not ok and "An active DM membership is required" in refused

                ok, tightened = await _call(
                    session,
                    artifact["calls"],
                    "fact_set",
                    {"key": "interests", "level": "close"},
                )
                assert ok and tightened["level"] == "close"
                assert _fact_level(tmp_path, "om", "interests") == "close"
                ok, refused = await _call(
                    session,
                    artifact["calls"],
                    "fact_set",
                    {"key": "interests", "level": "friend"},
                )
                assert not ok and "refusing to loosen" in refused
                assert _fact_level(tmp_path, "om", "interests") == "close"

                ok, event = await _call(
                    session,
                    artifact["calls"],
                    "cal_add",
                    {
                        "start": "2026-11-08T21:00",
                        "duration": "2h",
                        "title": "Personal reminder",
                        "place": "Smaaash, Indiranagar",
                        "id": "manual-reminder",
                    },
                )
                assert ok and event["id"] == "manual-reminder"
                calendar = (tmp_path / "om" / "calendar.ics").read_text()
                assert "UID:manual-reminder" in calendar and "Personal reminder" in calendar

                ok, _ = await _call(
                    session,
                    artifact["calls"],
                    "ask_around",
                    {"question": "a tent to borrow, Nov 14-16"},
                )
                assert ok
                homes_now = [m["body"] for m in switch.rooms[homes["om"]]["messages"]]
                assert any(body.startswith("@om-gate ask-around ") for body in homes_now)

                ok, asked = await _call(
                    session,
                    artifact["calls"],
                    "ask",
                    {"friend": "rahul", "fields": ["diet", "address"]},
                )
                assert ok
                await _wait_for(
                    lambda: any(
                        m["sender"] == "rahul-gate" and "diet:" in m["body"]
                        for m in switch.rooms[asked["room"]]["messages"]
                    )
                )
                ok, facts = await _call(
                    session, artifact["calls"], "dm_read", {"room": asked["room"]}
                )
                assert ok
                assert "non-vegetarian" in json.dumps(facts)
                assert "18, 5th Block" not in json.dumps(facts)

                # Om's default level for Rahul is close. Recipient never gets a home post.
                async with stdio_client(
                    StdioServerParameters(
                        command=sys.executable,
                        args=["-m", "trustnet.tn.mcp", "--as", "rahul"],
                        env=env,
                        cwd=str(tmp_path),
                    ),
                    errlog=log,
                ) as (rr, rw):
                    async with ClientSession(rr, rw) as rahul:
                        await rahul.initialize()
                        before = list(switch.rooms[homes["om"]]["messages"])
                        ok, gifts = await _call(
                            rahul,
                            artifact["calls"],
                            "gift_ideas",
                            {
                                "friend": "om",
                                "occasion": "birthday",
                                "date": "2026-11-20",
                                "budget": 3000,
                            },
                        )
                        assert ok
                        assert gifts["suggestions"] == [
                            {"item": "Lego Millennium Falcon", "price": 2500},
                            {"item": "Hario V60", "price": 2000},
                        ]
                        ok, claimed = await _call(
                            rahul,
                            artifact["calls"],
                            "claim",
                            {"friend": "om", "item": "Lego Millennium Falcon"},
                        )
                        assert ok and claimed == {
                            "status": "claimed",
                            "item": "Lego Millennium Falcon",
                        }
                        assert switch.rooms[homes["om"]]["messages"] == before
                        gift_rooms = [
                            r
                            for r in switch.rooms.values()
                            if r["name"].startswith("gift-rahul-om-")
                        ]
                        assert len(gift_rooms) == 1
                        assert gift_rooms[0]["archived"]
                        assert gift_rooms[0]["read_visibility"] == "private"
                        with pytest.raises(PermissionError):
                            await switch.client("om-hermes", "om").read_context(
                                room_id=gift_rooms[0]["id"]
                            )

                        from datetime import datetime

                        from trustnet.gate import ledger, surprise
                        from trustnet.gate.calendar import TIME_ZONE

                        sealed = ledger.format_ledger(
                            person="om", now=datetime(2026, 11, 20, tzinfo=TIME_ZONE)
                        )
                        assert "1 sealed entry, opens Nov 21" in sealed
                        assert "Lego Millennium Falcon" not in json.dumps(
                            surprise.owner_value(
                                "om",
                                "wishlist",
                                [{"item": "Lego Millennium Falcon", "price": 2500}],
                            )
                        )
                        opened = ledger.format_ledger(
                            person="om", now=datetime(2026, 11, 21, tzinfo=TIME_ZONE)
                        )
                        assert "sealed entry" not in opened and "gift" in opened
                        ok, other = await _call(
                            rahul,
                            artifact["calls"],
                            "gift_ideas",
                            {
                                "friend": "om",
                                "occasion": "birthday",
                                "date": "2026-11-20",
                                "budget": 3000,
                            },
                        )
                        assert ok and other["taken"] == [
                            {"item": "Lego Millennium Falcon", "status": "taken"}
                        ]
                        ok, _ = await _call(
                            rahul,
                            artifact["calls"],
                            "dm_post",
                            {"room": room["id"], "text": "Sunday bowling works for me."},
                        )
                        assert ok
                        ok, _ = await _call(
                            session,
                            artifact["calls"],
                            "dm_post",
                            {
                                "room": room["id"],
                                "text": '@om-gate propose P1 2026-11-09T21:00 2h "Bowling" @ "Smaaash"',
                            },
                        )
                        assert ok
                        await _wait_for(
                            lambda: all("P1" in _coordination(tmp_path, p) for p in PERSONS),
                            what="both proposals",
                        )
                        ok, _ = await _call(
                            session, artifact["calls"], "answer", {"id": "P1", "text": "yes"}
                        )
                        assert ok
                        ok, _ = await _call(
                            rahul, artifact["calls"], "answer", {"id": "P1", "text": "yes"}
                        )
                        assert ok
                        await _wait_for(
                            lambda: all(
                                (tmp_path / p / "calendar.ics").read_text().count("UID:trustnet-")
                                == 1
                                for p in PERSONS
                            ),
                            what="automatic calendar delivery for both people",
                        )
                        calendar = (tmp_path / "om" / "calendar.ics").read_text()
                        artifact["gift"] = {
                            "ideas": gifts,
                            "claim": claimed,
                            "other_ask": other,
                            "sealed": sealed,
                            "opened": opened,
                            "recipient_home_unchanged": True,
                        }

                artifact.update(
                    {
                        "room": room["id"],
                        "room_name": room["name"],
                        "transcript": [
                            {"sender": message["sender"], "body": message["body"]}
                            for message in room["messages"]
                        ],
                        "coordination": {
                            person: _coordination(tmp_path, person) for person in PERSONS
                        },
                        "ledgers": {
                            person: (tmp_path / person / "ledger.jsonl").read_text()
                            if (tmp_path / person / "ledger.jsonl").exists()
                            else ""
                            for person in PERSONS
                        },
                        "calendars": {"om": calendar},
                    }
                )
    finally:
        log.close()
        await stop()
        for task in gate_tasks:
            task.cancel()
        await asyncio.gather(*gate_tasks, return_exceptions=True)
        artifact["server_log"] = (tmp_path / "server.log").read_text()
        artifact_dir.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(artifact, ensure_ascii=False, indent=2)
        (artifact_dir / "transcript.json").write_text(serialized)
        assert token["om"] not in serialized
        assert token["rahul"] not in serialized
        assert token["om"] not in artifact["server_log"]
        print(f"\nMCP artifact: {artifact_dir / 'transcript.json'}")


def test_mcp_requires_a_person(tmp_path):
    env = {**os.environ}
    env.pop("TN_PERSON", None)
    result = subprocess.run(
        [sys.executable, "-m", "trustnet.tn.mcp"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "--as" in result.stderr


async def test_a_missing_environment_is_a_readable_tool_error(tmp_path):
    """A misconfigured Hermes entry must get a named variable, not a crash traceback."""
    env = {**os.environ, "TN_DATA_DIR": str(tmp_path)}
    for name in ("SWITCH_URL", "OM_GATE_KEY", "RAHUL_GATE_KEY"):
        env.pop(name, None)
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "trustnet.tn.mcp", "--as", "om"],
        env=env,
        cwd=str(tmp_path),
    )
    with open(os.devnull, "w") as errlog:
        async with stdio_client(params, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("inbox", {})
                assert result.is_error
                text = "".join(b.text for b in result.content if getattr(b, "text", None))
                assert "missing environment variable SWITCH_URL" in text


@pytest.mark.parametrize("person", PERSONS)
async def test_each_person_gets_the_same_tools(person):
    """The server is generic in ``--as``: same tool contract for both Hermes profiles."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "trustnet.tn.mcp", "--as", person],
        env=os.environ,
    )
    with open(os.devnull, "w") as errlog:
        async with stdio_client(params, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                assert {tool.name for tool in listed.tools} == TOOLS
