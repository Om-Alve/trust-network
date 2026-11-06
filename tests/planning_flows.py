"""Offline planning flows shared by pytest and the artifact runner."""

import asyncio
import shutil
from datetime import datetime

import yaml
from fakes.fake_switch import FakeSwitch, FakeSwitchClient

from trustnet import room_pool
from trustnet.gate import consent, dm, handshake, relay
from trustnet.gate.calendar import TIME_ZONE
from trustnet.gate.envoy import MAX_SECONDS, MAX_TURNS
from trustnet.gate.policy import Identity
from trustnet.gate.runtime import Gate

NOW = datetime(2026, 11, 6, 12, tzinfo=TIME_ZONE)
CARD = '2026-11-09T19:00 2h "Games ☕" @ "Dialogues"'


class Planning:
    def __init__(self, root, patch):
        self.root, self.patch = root, patch
        self.switch = FakeSwitch()
        self.clients, self.homes, self.gates = {}, {}, {}
        self.trace = []

    async def setup(self):
        self.patch.setenv("TN_DATA_DIR", str(self.root))
        for p in ("om", "priya", "rahul"):
            shutil.copytree("examples/" + p, self.root / p)
            self.clients[p] = self.switch.client(p + "-gate", p)
            self.switch.client(dm.main_agent(p), p)
            self.switch.client(p, p, kind="user")
        self.ids = {p: Identity.user(p) for p in self.clients}
        self.ids.update(
            {n: Identity.agent(n, a["owner_id"]) for n, a in self.switch.agents.items()}
        )
        for p, client in self.clients.items():
            self.homes[p] = (
                await client.create_room(
                    p + "-home", "", [p + "-gate", p + "-hermes"], internal_only=True
                )
            )["room_id"]

        async def home(person, text, *, client):
            await client.connect_to_room(self.homes[person])
            await client.post_message(text)

        self.patch.setattr(relay, "post_home", home)
        self.patch.setattr("trustnet.gate.envoy.post_home", home)
        self.restart()

    def restart(self):
        self.gates = {
            p: Gate(p, c, lambda: self.ids, clock=lambda: NOW) for p, c in self.clients.items()
        }
        self.trace.append("restart all gates")

    async def drain(self):
        for _ in range(100):
            active = False
            for p, client in self.clients.items():
                while not client.queue.empty():
                    active = True
                    event = client.queue.get_nowait()
                    if p + "-gate" in self.switch.rooms[event.room_id]["members"]:
                        await self.gates[p].handle(event)
            if not active:
                return
        raise AssertionError("gate event loop did not settle")

    async def send(self, room, sender, text, *, drain=True):
        client = next(c for c in self.switch.clients if c.name == sender)
        await client.connect_to_room(room)
        await client.post_message(text)
        self.trace.append(f"{sender} in {self.switch.rooms[room]['name']}: {text}")
        if drain:
            await self.drain()

    def bodies(self, room):
        return [m["body"] for m in self.switch.rooms[room]["messages"]]

    async def open(self, friend="rahul", goal="Games"):
        before = set(self.switch.rooms)
        await self.send(self.homes["om"], "om-hermes", f'@om-gate dm {friend} "{goal}"')
        room = next(
            r
            for r in self.switch.rooms.values()
            if r["id"] not in before and r["name"].startswith("dm-")
        )
        assert {"om-hermes", friend + "-hermes", "om-gate", friend + "-gate"} <= room["members"]
        return room["id"]

    async def propose(self, room, ref="P1", friend="rahul"):
        await self.send(room, friend + "-hermes", "Games sounds good.")
        await self.send(room, "om-hermes", f"@om-gate propose {ref} {CARD}")

    async def vote(self, person, ref="P1", vote="yes"):
        await self.send(self.homes[person], person, f"@{person}-gate {vote} {ref}")

    def snapshot(self):
        return {
            "steps": self.trace,
            "rooms": list(self.switch.rooms.values()),
            "coordination": {p: consent.load(p) for p in self.clients},
        }


async def three_people(h):
    rooms = {p: await h.open(p) for p in ("priya", "rahul")}
    for index, (p, room) in enumerate(rooms.items(), 1):
        ref = f"P{index}"
        await h.propose(room, ref, p)
        assert consent.load(p)[ref]["friend"] == "om"
        await h.vote("om", ref)
        await h.vote(p, ref)
        for person in ("om", p):
            assert consent.load(person)[ref]["status"] == "confirmed"
            assert sum(b.startswith(f"✅ {ref}:") for b in h.bodies(h.homes[person])) == 1
        assert h.switch.rooms[room]["archived"]
        assert len(h.switch.rooms[room]["documents"]) == 2
    assert len(list(h.root.glob("*/share-cards/*.json"))) == 4


async def collisions_and_decline(h):
    first = await h.open()
    second = await h.open(goal="Other games")
    third = await h.open("priya")
    await h.propose(first)
    for room, friend in ((second, "rahul"), (third, "priya")):
        await h.propose(room, friend=friend)
        assert any("already used" in b and "fresh" in b for b in h.bodies(room))
        assert consent.load("om")["P1"]["room"] == first
    await h.vote("rahul", vote="no")
    assert consent.load("om")["P1"]["status"] == "declined"
    assert not h.switch.rooms[first]["archived"]
    await h.send(first, "om-hermes", f"@om-gate propose P2 {CARD}")
    await h.vote("om", "P2")
    await h.vote("rahul", "P2")
    assert consent.load("om")["P2"]["status"] == "confirmed"


async def consent_replays_and_restart(h):
    room = await h.open()
    other = await h.open(goal="Another plan")
    await h.propose(room)
    digest = consent.digest(consent.load("om")["P1"]["card"])
    for rid, sender, fingerprint in (
        (room, "rahul-gate", "0" * 64),
        (other, "rahul-gate", digest),
        (room, "rahul-hermes", digest),
    ):
        await h.send(rid, sender, f"@om-gate consent P1 yes direct {fingerprint}")
        assert consent.load("om")["P1"]["votes"] == {}
    await h.vote("om")
    await h.vote("om", vote="no")  # first vote wins
    h.restart()
    await h.vote("rahul")
    assert consent.load("om")["P1"]["status"] == "confirmed"
    await h.vote("om")
    await h.send(room, "rahul-gate", f"@om-gate consent P1 no direct {digest}")
    assert consent.load("om")["P1"]["status"] == "confirmed"
    assert len(h.switch.rooms[room]["documents"]) == 2
    # Both local yeses may be processed before either peer sees the relay.
    await h.propose(other, "P2")
    await h.send(h.homes["om"], "om", "@om-gate yes P2", drain=False)
    await h.send(h.homes["rahul"], "rahul", "@rahul-gate yes P2", drain=False)
    await h.drain()
    assert consent.load("om")["P2"]["status"] == "confirmed"
    assert consent.load("rahul")["P2"]["status"] == "confirmed"
    assert len(h.switch.rooms[other]["documents"]) == 2


async def authority_and_questions(h):
    room = await h.open()
    await h.send(room, "om-hermes", f"@om-gate propose P1 {CARD}")
    assert "P1" not in consent.load("om")
    assert "wait for rahul-hermes" in h.bodies(room)[-1]
    await h.send(room, "rahul-hermes", f"@om-gate propose P1 {CARD}")
    assert "P1" not in consent.load("om")
    assert any("own gate" in b for b in h.bodies(room))
    await h.propose(room)
    await h.send(room, "rahul-hermes", '@om-gate answer P1 "yes"')
    assert consent.load("om")["P1"]["votes"] == {}
    path = h.root / "om" / "trust.yaml"
    trust = yaml.safe_load(path.read_text())
    trust["consent"]["default"] = "direct"
    path.write_text(yaml.safe_dump(trust))
    await h.send(h.homes["om"], "om-hermes", '@om-gate answer P1 "yes"')
    assert "answers this directly" in h.bodies(h.homes["om"])[-1]
    await h.send(room, "om-hermes", '@om-gate ask-owner Q1 "Budget?"')
    h.restart()
    await h.send(h.homes["om"], "om", '@om-gate answer Q1 "1500"')
    await h.send(h.homes["om"], "om", '@om-gate answer Q1 "3000"')
    assert sum("Q1 answer from om:" in b for b in h.bodies(room)) == 1
    assert 'Q1 answer from om: "1500"' in h.bodies(room)


async def malformed_plans(h):
    room = await h.open()
    await h.send(room, "rahul-hermes", "Ready to plan.")
    for card in (
        'not-a-date 2h "Games" @ "Cafe"',
        '2026-11-09T19:00 999999999999999999999h "Games" @ "Cafe"',
        '2026-11-09T19:00 2h "A "quoted" title" @ "Cafe"',
    ):
        await h.send(room, "om-hermes", f"@om-gate propose P1 {card}")
        assert "P1" not in consent.load("om")
        assert h.bodies(room)[-1].startswith("Invalid command.")
    await h.send(room, "om-hermes", '@om-gate propose P1 2026-11-05T19:00 2h "Past" @ "Cafe"')
    assert "P1" not in consent.load("om")
    assert "past" in h.bodies(room)[-1]
    await h.send(room, "om-hermes", f"@om-gate propose P1 {CARD}")
    assert consent.load("om")["P1"]["card"] == consent.load("rahul")["P1"]["card"]
    assert "Games ☕" in consent.load("rahul")["P1"]["card"]


async def limits_and_restart(h):
    room = await h.open()
    await h.propose(room)
    await h.vote("om")
    # Restart must keep both the turn count and its deadline.
    count = len(h.gates["om"].watches[room].turns)
    h.restart()
    assert len(h.gates["om"].watches[room].turns) == count
    for i in range(MAX_TURNS - count):
        await h.send(room, "om-hermes", f"Still planning {i}")
    assert h.switch.rooms[room]["archived"]
    h.restart()
    fingerprint = consent.digest(consent.load("om")["P1"]["card"])
    await h.send(room, "rahul-gate", f"@om-gate consent P1 yes direct {fingerprint}")
    assert consent.load("om")["P1"]["status"] == "pending"
    await h.send(h.homes["rahul"], "rahul", "@rahul-gate yes P1")
    assert "rahul" not in consent.load("rahul")["P1"]["votes"]
    assert "closed" in h.bodies(h.homes["rahul"])[-1]
    assert len(h.switch.rooms[room]["documents"]) == 0
    timed = await h.open(goal="Timed room")
    watch = h.gates["om"].watches[timed]
    watch.started -= MAX_SECONDS
    await watch.check()
    assert h.switch.rooms[timed]["archived"]


async def handshake_restart(h):
    # Open without delivering the setup's hello; then try old and compatible peers.
    before = set(h.switch.rooms)
    await h.send(h.homes["om"], "om-hermes", '@om-gate dm rahul "Handshake"', drain=False)
    event = h.clients["om"].queue.get_nowait()
    await h.gates["om"].handle(event)
    conn = next(r for r in h.switch.rooms.values() if r["name"] == "conn-om-rahul")
    room = next(
        r for r in h.switch.rooms.values() if r["id"] not in before and r["name"].startswith("dm-")
    )
    for client in h.clients.values():
        while not client.queue.empty():
            client.queue.get_nowait()
    join = f'@rahul-gate join-dm {room["id"]} "Handshake"'
    await h.send(conn["id"], "om-gate", join)
    assert "hasn't said hello" in h.bodies(h.homes["rahul"])[-1]
    await h.send(conn["id"], "om-gate", "@rahul-gate hello trust-network/0 free,propose")
    await h.send(conn["id"], "om-gate", join)
    assert "trust-network/0" in h.bodies(h.homes["rahul"])[-1]
    h.restart()
    await h.send(conn["id"], "om-gate", handshake.line("rahul"))
    await h.send(conn["id"], "om-gate", join)
    assert "rahul-hermes" in room["members"]
    assert handshake.problem("rahul", "om") is None


async def pool_capacity_and_failure(h):
    class Connection(FakeSwitchClient):
        def __init__(self, *args):
            super().__init__(h.switch, "om-gate", "om", "agent")
            h.switch.clients.append(self)
            self.ready = asyncio.Event()
            self.ready.set()
            self.base_url, self.api_key = "fake", "fake"
            self.closed = False

        async def aclose(self):
            self.closed = True

        async def events(self):
            while True:
                item = await self.queue.get()
                if isinstance(item, Exception):
                    raise item
                yield item

    h.patch.setattr(room_pool, "SwitchClient", Connection)
    main = Connection()
    pool = room_pool.RoomPool(main)
    try:
        rooms = [
            (await main.create_room(f"room-{i}", "", ["om-gate"]))["room_id"]
            for i in range(room_pool.MAX_ANCHORS + 3)
        ]
        await pool.sync()
        assert set(pool.anchors) == set(rooms[-room_pool.MAX_ANCHORS :])
        room = rooms[-1]
        failed = pool.anchors[room]
        pump = pool.pumps[room]
        failed.queue.put_nowait(ConnectionError("scenario stream failure"))
        await asyncio.wait_for(pump, 1)
        assert failed.closed and room not in pool.anchors
        await pool.sync()
        assert room in pool.anchors and pool.anchors[room] is not failed
        await pool.connect_to_room(room)
        await pool.post_message("recovered")
        assert h.bodies(room) == ["recovered"]
        await main.archive_room(room)
        await pool.sync()
        assert room not in pool.anchors
        h.trace.append("newest 24 anchored; failed stream dropped, reconnected and posted")
    finally:
        await pool.aclose()


SCENARIOS = [
    three_people,
    collisions_and_decline,
    consent_replays_and_restart,
    authority_and_questions,
    malformed_plans,
    limits_and_restart,
    handshake_restart,
    pool_capacity_and_failure,
]
