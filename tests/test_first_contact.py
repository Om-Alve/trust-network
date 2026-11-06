"""First contact for two new people over an empty state directory.

Mira and Finn have never been registered, have no home room, no retained
credentials and no inbox cursor. The only pre-existing actor is the attacker
"eve" in the last check. The test drives the real registration path
(``personal.session`` over HTTP) and the real gate startup helper, then the
first DM, without the test creating a home or a DM room itself.

What it proves:

- gate and agent registration work with ``TN_STATE_DIR`` empty;
- gate startup creates a private internal home and invites the main agent;
- the agent's first tool request bootstraps the same home instead of failing;
- both orders (gate first, agent first) converge on one active home, and the
  gate-first stub is archived rather than used;
- repeated requests are idempotent: one registration, one active home, one DM;
- a home owned by somebody else is refused, never read and never posted into.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest
import yaml
from fakes.fake_switch import FakeSwitch
from fakes.loopback_switch import LoopbackSwitch, serve

from trustnet.gate import relay
from trustnet.gate.dm import main_agent
from trustnet.gate.policy import Identity
from trustnet.gate.runtime import Gate
from trustnet.switch_client import SwitchClient, SwitchError
from trustnet.tn import personal

PEOPLE = ("mira", "finn")


def _profile(root: Path, person: str, friend: str, facts: dict) -> None:
    directory = root / person
    directory.mkdir(parents=True)
    (directory / "trust.yaml").write_text(
        yaml.safe_dump({"people": {friend: "close"}, "consent": {"default": "via-agent"}})
    )
    (directory / "calendar.ics").write_text(
        "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//trust-network//EN\nEND:VCALENDAR\n"
    )
    (directory / "facts.yaml").write_text(
        yaml.safe_dump({"calendar": "./calendar.ics", "facts": facts})
    )


async def _wait_for(predicate, *, timeout=10.0, what="state") -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"timed out waiting for {what}")


async def _register_gate(url: str, key: str, person: str) -> None:
    """Register a gate through the real client; its in-process client follows."""
    client = await SwitchClient.register(url, key, f"{person}-gate", agent_type="codex")
    await client.aclose()


async def test_first_contact_and_first_dm(tmp_path, monkeypatch):
    profiles, state = tmp_path / "profiles", tmp_path / "state"
    state.mkdir()
    _profile(profiles, "mira", "finn", {"diet": {"value": "vegetarian", "level": "acquaintance"}})
    _profile(profiles, "finn", "mira", {"diet": {"value": "vegan", "level": "acquaintance"}})
    _profile(profiles, "noa", "eve", {})
    _profile(profiles, "ada", "mira", {})

    keys = {
        "canary-mira": "mira",
        "canary-finn": "finn",
        "canary-noa": "noa",
        "canary-ada": "ada",
    }
    key_for = {person: key for key, person in keys.items()}
    for person, key in key_for.items():
        monkeypatch.setenv(f"{person.upper()}_GATE_KEY", key)
    monkeypatch.setenv("TN_DATA_DIR", str(profiles))
    monkeypatch.setenv("TN_STATE_DIR", str(state))
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")

    switch = FakeSwitch()
    loop = LoopbackSwitch(switch, keys)
    url, stop = await serve(loop.app())
    monkeypatch.setenv("SWITCH_URL", url)

    def identities():
        values = {user: Identity.user(user) for user in switch.users}
        values.update(
            {
                name: Identity.agent(name, detail["owner_id"])
                for name, detail in switch.agents.items()
            }
        )
        return values

    gates: dict[str, Gate] = {}
    tasks: list[asyncio.Task] = []
    try:
        # Gate first: Mira's gate is registered and starts before her agent exists.
        await _register_gate(url, key_for["mira"], "mira")
        mira_gate = loop.client("mira-gate", "mira")
        stub = await relay.ensure_home("mira", mira_gate)
        assert switch.rooms[stub]["members"] == {"mira", "mira-gate"}
        assert switch.rooms[stub]["read_visibility"] == "private"

        # Her first tool request registers mira-hermes and bootstraps a shared home.
        first = await personal.inbox("mira")
        mira_home = first["room"]
        assert first["threads"] == [] and first["open"] == []
        assert switch.rooms[mira_home]["members"] == {"mira", "mira-gate", "mira-hermes"}
        assert switch.rooms[mira_home]["internal_only"] is True
        assert switch.rooms[mira_home]["read_visibility"] == "private"
        assert switch.rooms[mira_home]["write_visibility"] == "private"

        # Finn first: his gate is registered only after his agent bootstrapped.
        await _register_gate(url, key_for["finn"], "finn")
        finn_first = await personal.inbox("finn")
        finn_home = finn_first["room"]
        assert switch.rooms[finn_home]["members"] == {"finn", "finn-gate", "finn-hermes"}

        # The gate's next startup/relay picks the shared home and retires its stub.
        assert await relay.ensure_home("mira", mira_gate) == mira_home
        assert switch.rooms[stub]["archived"] is True
        finn_gate = loop.client("finn-gate", "finn")
        assert await relay.ensure_home("finn", finn_gate) == finn_home

        gates = {
            "mira": Gate("mira", mira_gate, identities),
            "finn": Gate("finn", finn_gate, identities),
        }
        tasks = [asyncio.create_task(gate.run()) for gate in gates.values()]

        # First contact repeats: one registration, one active home, same room.
        second = await personal.inbox("mira")
        assert second["room"] == mira_home
        assert loop.registrations.count("mira-hermes") == 1
        active = [
            room
            for room in switch.rooms.values()
            if room["name"] == "mira-home" and not room["archived"]
        ]
        assert len(active) == 1
        assert await relay.ensure_home("mira", mira_gate) == mira_home

        # The first DM is opened by the gates; the test creates no room here.
        await personal.dm("mira", "finn", "Sunday coffee")
        await _wait_for(
            lambda: any(room["name"].startswith("dm-finn-mira-") for room in switch.rooms.values()),
            what="the gate-opened DM room",
        )
        room = next(
            room for room in switch.rooms.values() if room["name"].startswith("dm-finn-mira-")
        )
        await _wait_for(
            lambda: room["id"] in gates["mira"].watches and room["id"] in gates["finn"].watches,
            what="both gates to set up the DM",
        )
        assert {
            "mira-gate",
            "finn-gate",
            "mira-hermes",
            "finn-hermes",
        } <= room["members"]
        assert any(
            "Share card" in message["body"] for message in switch.rooms[mira_home]["messages"]
        )
        assert any(
            "Share card" in message["body"] for message in switch.rooms[finn_home]["messages"]
        )
        assert all(
            (profiles / person / "share-cards" / f"{room['id']}.json").exists() for person in PEOPLE
        )

        line = "Mira likes filter coffee and is free after 7."
        await personal.dm_post("mira", room["name"], line)
        assert any(message["body"] == line for message in room["messages"])
        read = await personal.dm_read("finn", room["id"])
        assert [thread["root"]["body"] for thread in read["threads"]][-1] == line

        # A watcher and a tool call can race on first contact. The bootstrap
        # lock makes them converge on one registration and one home.
        await _register_gate(url, key_for["ada"], "ada")
        raced = await asyncio.gather(personal.inbox("ada"), personal.inbox("ada"))
        assert raced[0]["room"] == raced[1]["room"]
        assert loop.registrations.count("ada-hermes") == 1
        active_ada = [
            room
            for room in switch.rooms.values()
            if room["name"] == "ada-home" and not room["archived"]
        ]
        assert len(active_ada) == 1
        assert active_ada[0]["members"] == {"ada", "ada-gate", "ada-hermes"}

        # Register noa-hermes first so eve can invite it into her squatted room.
        switch.client(main_agent("noa"), "noa")
        eve_client = switch.client("eve-hermes", "eve")
        eve_room = (
            await eve_client.create_room(
                "noa-home",
                "Not Noa's home",
                ["eve-hermes"],
                internal_only=True,
                read_visibility="private",
                write_visibility="private",
            )
        )["room_id"]
        await eve_client.invite_agent_to_room(eve_room, main_agent("noa"))
        with pytest.raises(SwitchError, match="another owner"):
            await personal.inbox("noa")
        assert switch.rooms[eve_room]["messages"] == []
        assert len([room for room in switch.rooms.values() if room["name"] == "noa-home"]) == 1

        # Her gate recovers without ever writing into the squatted room: it
        # ignores the foreign home and creates a private one of its own. The
        # agent's next tool request then finds that safe home.
        await _register_gate(url, key_for["noa"], "noa")
        noa_gate = loop.client("noa-gate", "noa")
        await eve_client.invite_agent_to_room(eve_room, "noa-gate")
        safe = await relay.ensure_home("noa", noa_gate)
        assert safe != eve_room
        assert switch.rooms[eve_room]["messages"] == []
        assert switch.rooms[safe]["read_visibility"] == "private"
        assert switch.rooms[safe]["members"] == {"noa", "noa-gate", "noa-hermes"}
        assert (await personal.inbox("noa"))["room"] == safe

        # The private home is unreadable and unwritable for that other owner.
        with pytest.raises(PermissionError):
            await eve_client.read_context(room_id=mira_home, limit=10)
        with pytest.raises(PermissionError):
            await eve_client.connect_to_room(mira_home)

        artifact = {
            "people": PEOPLE,
            "homes": {
                "mira": mira_home,
                "finn": finn_home,
                "mira_gate_stub": stub,
                "noa_recovered": safe,
            },
            "dm": {"room": room["name"], "members": sorted(room["members"])},
            "registrations": loop.registrations,
            "checks": {
                "mira_home_private": switch.rooms[mira_home]["read_visibility"] == "private",
                "stub_archived": switch.rooms[stub]["archived"],
                "concurrent_first_contact": len(active_ada) == 1,
                "identity_refusal": "another owner",
                "gate_ignored_squatted_home": switch.rooms[eve_room]["messages"] == [],
            },
        }
        output = tmp_path / "first-contact"
        output.mkdir()
        (output / "transcript.json").write_text(json.dumps(artifact, indent=2))
        print(f"\nfirst-contact artifact: {output / 'transcript.json'}")
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await stop()
