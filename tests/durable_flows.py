"""Planning recovery scenarios exercised through real gate commands."""

import asyncio
import json
import os
import subprocess
import sys

from icalendar import Calendar
from planning_flows import CARD

from trustnet.gate import consent, fact_changes, ledger
from trustnet.gate.facts import load_profile


def events(h, person):
    path = h.root / person / "calendar.ics"
    return [
        e
        for e in Calendar.from_ical(path.read_bytes()).walk("VEVENT")
        if str(e.get("UID", "")).startswith("trustnet-")
    ]


async def calendar_delivery(h):
    room = await h.open()
    await h.propose(room)
    await h.vote("om")
    assert not events(h, "om") and not events(h, "rahul")
    await h.vote("rahul")
    h.restart()
    for gate in h.gates.values():
        await consent.recover(gate)
        await consent.recover(gate)
    for person in ("om", "rahul"):
        booked = events(h, person)
        assert len(booked) == 1
        assert str(booked[0]["SUMMARY"]) == "Games ☕"
        assert str(booked[0]["LOCATION"]) == "Dialogues"
        assert booked[0].decoded("DTSTART").isoformat() == "2026-11-09T19:00:00+05:30"


async def interrupted_vote(h):
    room = await h.open()
    await h.propose(room)
    client = h.clients["om"]
    original = client.post_message

    async def fail_relay(body, *args, **kwargs):
        if body.startswith("@rahul-gate consent"):
            raise ConnectionError("interrupted before consent delivery")
        return await original(body, *args, **kwargs)

    with h.patch.context() as patch:
        patch.setattr(client, "post_message", fail_relay)
        try:
            await h.vote("om")
        except ConnectionError:
            pass
    assert consent.load("om")["P1"]["votes"]["om"][0] is True
    h.restart()
    await consent.recover(h.gates["om"])
    await h.drain()
    assert consent.load("rahul")["P1"]["votes"]["om"][0] is True
    await h.vote("rahul")
    assert all(consent.load(p)["P1"]["status"] == "confirmed" for p in ("om", "rahul"))


async def interrupted_calendar(h):
    from trustnet.gate import calendar

    room = await h.open()
    await h.propose(room)
    await h.vote("om")
    original = calendar.add_event

    def written_then_crash(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError("interrupted after calendar write")

    with h.patch.context() as patch:
        patch.setattr(calendar, "add_event", written_then_crash)
        try:
            await h.vote("rahul")
        except OSError:
            pass
    h.restart()
    for _ in range(3):
        for gate in h.gates.values():
            await consent.recover(gate)
        await h.drain()
    assert all(len(events(h, p)) == 1 for p in ("om", "rahul"))
    assert all(consent.load(p)["P1"]["status"] == "confirmed" for p in ("om", "rahul"))


async def counter_supersedes(h):
    room = await h.open()
    await h.propose(room)
    await h.vote("om")
    await h.send(room, "rahul-hermes", f"@rahul-gate counter P1 P2 {CARD}")
    for person in ("om", "rahul"):
        state = consent.load(person)
        assert state["P1"]["status"] == "superseded"
        assert state["P2"]["votes"] == {}
    await h.vote("rahul", "P1")
    fingerprint = consent.digest(consent.load("om")["P1"]["card"])
    await h.send(room, "rahul-gate", f"@om-gate consent P1 yes direct {fingerprint}")
    assert not events(h, "om") and not events(h, "rahul")
    await h.vote("om", "P2")
    await h.vote("rahul", "P2")
    assert all(consent.load(p)["P2"]["status"] == "confirmed" for p in ("om", "rahul"))
    assert all(len(events(h, p)) == 1 for p in ("om", "rahul"))
    await h.send(room, "rahul-hermes", f"@rahul-gate counter P2 P3 {CARD}")
    assert all("P3" not in consent.load(p) for p in ("om", "rahul"))


async def interrupted_fact(h):
    fact_changes.add("om", "phone", "555-0100")
    ref = fact_changes.suggest("om", "phone", "close")["ref"]
    original = fact_changes._record

    def recorded_then_crash(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError("interrupted after approval ledger write")

    with h.patch.context() as patch:
        patch.setattr(fact_changes, "_record", recorded_then_crash)
        try:
            fact_changes.decide("om", ref, True)
        except OSError:
            pass
    fact_changes.recover("om")
    fact_changes.recover("om")
    assert load_profile("om").facts["phone"].level.value == "close"
    assert not any(item["ref"] == ref for item in fact_changes.review("om"))
    records = [
        e
        for e in ledger.read("om")
        if e.field == "phone" and isinstance(e.value, dict) and e.value.get("ref") == ref
    ]
    assert len(records) == 1


async def killed_approval_process(h):
    for index, boundary in enumerate(("profile", "ledger", "trust"), 1):
        key = f"phone{index}"
        if boundary == "trust":
            ref = fact_changes.suggest("om", "newfriend", "friend", trust=True)["ref"]
            target = "save_trust"
        else:
            fact_changes.add("om", key, "555-0100")
            ref = fact_changes.suggest("om", key, "close")["ref"]
            target = "save_profile" if boundary == "profile" else "_record"
        program = f"""
import os
from trustnet.gate import fact_changes
original = fact_changes.{target}
def crash(*args, **kwargs):
    original(*args, **kwargs)
    os._exit(73)
fact_changes.{target} = crash
fact_changes.decide('om', {ref!r}, True)
"""
        result = subprocess.run(
            [sys.executable, "-c", program], env={**os.environ, "TN_DATA_DIR": str(h.root)}
        )
        assert result.returncode == 73
        fact_changes.recover("om")
        fact_changes.recover("om")
        assert not any(item["ref"] == ref for item in fact_changes.review("om"))
        records = [
            e for e in ledger.read("om") if isinstance(e.value, dict) and e.value.get("ref") == ref
        ]
        assert len(records) == 1
        if boundary == "trust":
            from trustnet.gate.facts import load_trust

            assert load_trust("om").level_for("newfriend").value == "friend"
        else:
            assert load_profile("om").facts[key].level.value == "close"
        h.trace.append(f"process killed after {boundary}; {ref} recovered once")


async def delivered_vote_replay(h):
    room = await h.open()
    await h.propose(room)
    client = h.clients["om"]
    original = client.post_message

    async def delivered_then_crash(body, *args, **kwargs):
        result = await original(body, *args, **kwargs)
        if body.startswith("@rahul-gate consent"):
            raise ConnectionError("interrupted after successful send")
        return result

    with h.patch.context() as patch:
        patch.setattr(client, "post_message", delivered_then_crash)
        try:
            await h.vote("om")
        except ConnectionError:
            pass
    h.restart()
    await consent.recover(h.gates["om"])
    await h.drain()
    await h.vote("rahul")
    for gate in h.gates.values():
        await consent.recover(gate)
    await h.drain()
    assert all(len(events(h, p)) == 1 for p in ("om", "rahul"))
    assert len(h.switch.rooms[room]["documents"]) == 2


async def legacy_vote_recovery(h):
    room = await h.open()
    await h.propose(room)
    for person in ("om", "rahul"):
        state = consent.load(person)
        state["P1"].pop("jobs")
        state["P1"].pop("plan")
        if person == "om":
            state["P1"]["votes"]["om"] = [True, "direct"]
        (h.root / person / "coordination.json").write_text(json.dumps(state))
        (h.root / person / "decisions.sqlite3").unlink()
    h.restart()
    for gate in h.gates.values():
        await consent.recover(gate)
    await h.drain()
    assert consent.load("rahul")["P1"]["votes"]["om"] == [True, "direct"]
    await h.vote("rahul")
    assert all(len(events(h, p)) == 1 for p in ("om", "rahul"))


async def failed_home_does_not_block(h):
    from trustnet.gate import relay

    room = await h.open()
    await h.propose(room)

    async def unavailable(*args, **kwargs):
        raise ConnectionError("home unavailable")

    with h.patch.context() as patch:
        patch.setattr(relay, "post_home", unavailable)
        await h.vote("om")
        await h.vote("rahul")
        assert all(consent.load(p)["P1"]["status"] == "confirmed" for p in ("om", "rahul"))
        assert all(len(events(h, p)) == 1 for p in ("om", "rahul"))
    for gate in h.gates.values():
        await consent.recover(gate)
    assert all(
        sum(b.startswith("✅ P1:") for b in h.bodies(h.homes[p])) == 1 for p in ("om", "rahul")
    )


async def gate_single_writer(h):
    from trustnet.gate.runtime import Gate

    running = asyncio.create_task(h.gates["om"].run())
    await asyncio.sleep(0)
    try:
        duplicate = Gate("om", h.clients["om"], lambda: h.ids)
        try:
            await duplicate.run()
        except RuntimeError as exc:
            assert "already running" in str(exc)
        else:
            raise AssertionError("two gates accepted the same owner")
    finally:
        running.cancel()
        await asyncio.gather(running, return_exceptions=True)
    restarted = asyncio.create_task(h.gates["om"].run())
    await asyncio.sleep(0)
    assert not restarted.done()
    restarted.cancel()
    await asyncio.gather(restarted, return_exceptions=True)


async def counter_waits_for_original_delivery(h):
    room = await h.open()
    original = h.clients["om"].post_message

    async def unavailable(body, *args, **kwargs):
        if body.startswith("@rahul-gate propose"):
            raise ConnectionError("original proposal not delivered")
        return await original(body, *args, **kwargs)

    with h.patch.context() as patch:
        patch.setattr(h.clients["om"], "post_message", unavailable)
        await h.propose(room)
        await h.send(room, "om-hermes", f"@om-gate counter P1 P2 {CARD}")
        assert consent.load("om")["P1"]["status"] == "pending"
        assert "P2" not in consent.load("om")
    await consent.recover(h.gates["om"])
    await h.drain()
    await h.send(room, "om-hermes", f"@om-gate counter P1 P2 {CARD}")
    assert all(consent.load(p)["P1"]["status"] == "superseded" for p in ("om", "rahul"))
    assert all(consent.load(p)["P2"]["status"] == "pending" for p in ("om", "rahul"))


async def concurrent_trust_approval(h):
    from trustnet.gate import surprise
    from trustnet.gate.facts import load_trust

    ref = fact_changes.suggest("om", "newfriend", "friend", trust=True)["ref"]
    original = surprise.handle

    async def approve_during_dispatch(*args, **kwargs):
        fact_changes.decide("om", ref, True)
        return await original(*args, **kwargs)

    with h.patch.context() as patch:
        patch.setattr(surprise, "handle", approve_during_dispatch)
        await h.send(h.homes["om"], "om", "@om-gate trust rahul friend")
    trust = load_trust("om")
    assert trust.level_for("newfriend").value == "friend"
    assert trust.level_for("rahul").value == "friend"


SCENARIOS = [
    calendar_delivery,
    interrupted_vote,
    interrupted_calendar,
    counter_supersedes,
    interrupted_fact,
    killed_approval_process,
    delivered_vote_replay,
    legacy_vote_recovery,
    failed_home_does_not_block,
    gate_single_writer,
    counter_waits_for_original_delivery,
    concurrent_trust_approval,
]
