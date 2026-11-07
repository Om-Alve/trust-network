"""A small world of real :class:`Gate` objects over ``FakeSwitch``.

The scenario tests build one of these, drive messages through the same event
path Switch uses, and read the rooms back. Only the transport is fake: the
gates, policy, ledger, gift and ask-around code are the production modules.

Two modes are supported:

- ``await world.start()`` runs each gate's real ``run()`` loop, which is what
  the gift and ask-around flows need (they post to each other repeatedly);
- without ``start()`` a test can call ``await world.say(...)`` and inspect the
  reply deterministically.

``build_world`` copies the committed fixtures so a test never writes to
``examples/``. A scenario may override a trust level or a fact value before any
gate handles a message.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from fakes.fake_switch import FakeSwitch, FakeSwitchClient

from trustnet.gate import relay
from trustnet.gate.calendar import TIME_ZONE
from trustnet.gate.dm import main_agent
from trustnet.gate.facts import FACTS_FILENAME, TRUST_FILENAME
from trustnet.gate.policy import Identity
from trustnet.gate.runtime import Gate
from trustnet.switch_client import Event

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NOW = datetime(2026, 11, 5, 12, 0, tzinfo=TIME_ZONE)
OWNER_RE = re.compile(r"@(?P<gate>[a-z0-9][a-z0-9_-]*-gate)\b")


class Clock:
    """A mutable clock the gates read instead of wall time."""

    def __init__(self, now: datetime = DEFAULT_NOW):
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> None:
        self.now += timedelta(**delta)


@dataclass
class World:
    """All gates, clients, rooms and identities for one scenario."""

    tmp: Path
    switch: FakeSwitch
    gates: dict[str, Gate]
    gate_clients: dict[str, FakeSwitchClient]
    agent_clients: dict[str, FakeSwitchClient]
    identities: dict[str, Identity]
    homes: dict[str, str]
    clock: Clock
    tasks: list[asyncio.Task] = field(default_factory=list)
    _restore: list[tuple[object, str, object]] = field(default_factory=list)

    # -- rooms and transcripts ------------------------------------------------

    def bodies(self, room: str) -> list[str]:
        return [message["body"] for message in self.switch.rooms[room]["messages"]]

    def home_bodies(self, person: str) -> list[str]:
        return self.bodies(self.homes[person])

    def room_named(self, name: str) -> dict:
        return next(room for room in self.switch.rooms.values() if room["name"] == name)

    def rooms_named(self, prefix: str) -> list[dict]:
        return [room for room in self.switch.rooms.values() if room["name"].startswith(prefix)]

    async def add_room(self, name: str, agents: list[str]) -> str:
        """Create an internal room whose members are agents (and the owner user)."""
        creator = agents[0].rsplit("-", 1)[0]
        result = await self.gate_clients[creator].create_room(name, "", agents, internal_only=True)
        return result["room_id"]

    # -- driving messages -----------------------------------------------------

    async def say(self, room: str, sender: str, text: str, *, kind: str = "agent"):
        """Deliver one addressed message to the gate its ``@<person>-gate`` names."""
        match = OWNER_RE.search(text)
        if match is None:
            raise AssertionError(f"not an addressed command: {text!r}")
        person = match["gate"].removeprefix("@").removesuffix("-gate")
        await self.gates[person].handle(Event(room, sender, kind, text, True))

    async def settle(self, rounds: int = 200) -> None:
        """Drain every gate's event queue without running their main loops."""
        for _ in range(rounds):
            moved = False
            for person, client in self.gate_clients.items():
                while not client.queue.empty():
                    await self.gates[person].handle(client.queue.get_nowait())
                    moved = True
            if not moved:
                return

    async def wait_for(self, predicate, *, timeout: float = 10.0, what: str = "state") -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            await asyncio.sleep(0.02)
        raise AssertionError(f"timed out waiting for {what}")

    # -- gate loops -----------------------------------------------------------

    async def start(self) -> None:
        self.tasks = [asyncio.create_task(gate.run()) for gate in self.gates.values()]
        await asyncio.sleep(0)

    async def stop(self) -> None:
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []

    def restore(self) -> None:
        """Undo the process-wide hooks ``build_world`` installed."""
        for module, name, value in reversed(self._restore):
            setattr(module, name, value)
        self._restore = []

    # -- artifacts ------------------------------------------------------------

    def transcript(self) -> dict:
        return {
            "rooms": {
                room["name"]: {
                    "archived": room["archived"],
                    "messages": [
                        {"sender": message["sender"], "body": message["body"]}
                        for message in room["messages"]
                    ],
                }
                for room in self.switch.rooms.values()
            },
            "homes": {person: self.home_bodies(person) for person in self.homes},
        }


async def build_world(
    tmp_path: Path,
    *,
    people: tuple[str, ...] = ("om", "rahul", "priya"),
    strangers: tuple[str, ...] = (),
    trust: dict[str, dict[str, str]] | None = None,
    facts: dict[str, dict[str, dict]] | None = None,
    now: datetime = DEFAULT_NOW,
    monkeypatch=None,
) -> World:
    """Copy the fixtures and build gates, agents, homes and identities.

    ``trust`` overrides entries in ``<person>/trust.yaml`` (the copy, never the
    fixture). ``facts`` overrides one fact's ``value``/``level`` in the same
    way. ``strangers`` get a gate and an agent identity but no data directory,
    which is how a room containing someone not on the trust list is built.
    ``monkeypatch`` is pytest's fixture when a test builds the world; without it
    the caller owns ``world.restore()`` and the ``TN_DATA_DIR`` variable.
    """
    everyone = (*people, *strangers)
    for person in people:
        if (ROOT / "examples" / person).is_dir():
            shutil.copytree(ROOT / "examples" / person, tmp_path / person)
            continue
        (tmp_path / person).mkdir()
        (tmp_path / person / "calendar.ics").touch()
        (tmp_path / person / FACTS_FILENAME).write_text("calendar: ./calendar.ics\nfacts: {}\n")
        (tmp_path / person / TRUST_FILENAME).write_text(
            "people: {}\nconsent:\n  default: via-agent\n"
        )
    for person, levels in (trust or {}).items():
        path = tmp_path / person / TRUST_FILENAME
        data = yaml.safe_load(path.read_text())
        data["people"].update(levels)
        path.write_text(yaml.safe_dump(data, sort_keys=False))
    for person, overrides in (facts or {}).items():
        path = tmp_path / person / FACTS_FILENAME
        data = yaml.safe_load(path.read_text())
        data["facts"].update(overrides)
        path.write_text(yaml.safe_dump(data, sort_keys=False))

    if monkeypatch is not None:
        monkeypatch.setenv("TN_DATA_DIR", str(tmp_path))
    else:
        os.environ["TN_DATA_DIR"] = str(tmp_path)

    switch = FakeSwitch()
    gate_clients = {person: switch.client(f"{person}-gate", person) for person in everyone}
    agent_clients = {person: switch.client(main_agent(person), person) for person in everyone}
    identities = {person: Identity.user(person) for person in everyone}
    identities.update(
        {name: Identity.agent(name, detail["owner_id"]) for name, detail in switch.agents.items()}
    )

    homes: dict[str, str] = {}
    for person, client in gate_clients.items():
        result = await client.create_room(
            f"{person}-home", "", [f"{person}-gate", main_agent(person)], internal_only=True
        )
        homes[person] = result["room_id"]

    async def post_home(person: str, text: str, *, client) -> None:
        await client.connect_to_room(homes[person])
        await client.post_message(text)

    world = World(
        tmp=tmp_path,
        switch=switch,
        gates={},
        gate_clients=gate_clients,
        agent_clients=agent_clients,
        identities=identities,
        homes=homes,
        clock=Clock(now),
    )
    if monkeypatch is not None:
        monkeypatch.setattr(relay, "post_home", post_home)
        monkeypatch.setattr("trustnet.gate.watch.post_home", post_home)
    else:
        import trustnet.gate.watch as watch

        world._restore = [
            (relay, "post_home", relay.post_home),
            (watch, "post_home", watch.post_home),
        ]
        relay.post_home = post_home
        watch.post_home = post_home

    world.gates = {
        person: Gate(person, client, lambda: identities, clock=world.clock)
        for person, client in gate_clients.items()
    }
    return world


def personal_session(world: World):
    """An async context manager yielding each person's registered main agent."""

    @asynccontextmanager
    async def session(person: str):
        yield world.agent_clients[person]

    return session
