"""End-to-end group plan lifecycle over FakeSwitch.

These scenarios drive real :class:`trustnet.gate.runtime.Gate` objects over the
fake Switch transport, with the production runtime's fresh-membership, identity
and room-level checks. Calendar enqueue failures are injected at the outbox
boundary; the product scenarios additionally verify the durable calendar queue.

Failure modes this suite must catch
-----------------------------------
Identity and authority
1. A home ``plan-request`` is accepted from anyone other than the owner's own
   main agent for create/revise, or from a main agent whose consent mode is
   ``direct`` for vote/cancel.
2. A peer relay is accepted from a main agent, from a non-participant, or from
   a gate other than the exact ``<person>-gate`` named in the payload.
3. A peer gate forges another participant's vote by setting ``voter`` to a
   different person.
4. A plan is created for an unknown, missing-identity or untrusted participant,
   or when one participant does not trust every other member of the group room.
5. A malformed JSON command escapes dispatch instead of being refused quietly.

Plan identity and durability
6. A retried create token creates a second plan or a second group room.
7. A vote/relay with a stale fingerprint, stale revision or stale participant
   set is recorded.
8. Replayed vote relays apply twice or flip a recorded vote.
9. A plan disappears after the gate is restarted, or its pending outbox is not
   retried after a restart.
10. A failed relay or failed calendar enqueue is lost instead of retried.

Consensus and calendar
11. A calendar event is enqueued before every participant has explicitly voted
    yes, or twice for one revision.
12. A confirmed plan is revised; the old confirmed plan must stay effective
    until every participant approves the replacement, and the replacement must
    reuse the same stable calendar UID with ``action="update"``.
13. A declined replacement must not discard the previously confirmed plan.

Cancellation and timing
14. Cancellation before, during or after confirmation (including after a
    restart) fails to reach every member, or cancels a confirmed plan without
    enqueueing a calendar cancel.
15. A late vote after cancellation, decline or expiry changes the state.
16. Human replies that take days are rejected by a 30-minute planning window;
    an unanswered plan instead expires only after the multi-day window.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime

import pytest
import yaml
from scenario_harness import build_world, personal_session

from trustnet.gate import group_plans
from trustnet.gate.runtime import Gate
from trustnet.tn import personal, plans

CONTENT = {
    "start": "2026-11-20T19:00:00+05:30",
    "minutes": 120,
    "title": "Group dinner",
    "place": "Cafe",
}
CONTENT_2 = {
    "start": "2026-12-01T20:00:00+05:30",
    "minutes": 90,
    "title": "Group lunch",
    "place": "Terrace",
}
CONTENT_3 = {
    "start": "2026-12-05T18:30:00+05:30",
    "minutes": 60,
    "title": "Group coffee",
    "place": "Corner",
}

#: Everyone trusts everyone else, so every gate accepts the shared room.
DEFAULT_TRUST = {
    "om": {"rahul": "close", "priya": "friend"},
    "rahul": {"om": "close", "priya": "friend"},
    "priya": {"om": "friend", "rahul": "friend"},
}

#: Set by the most recent scenario so the artifact runner can dump it.
LAST_WORLD = None


class CalendarQueue:
    """The parent's synchronous durable ``calendar_jobs.queue`` contract."""

    def __init__(self):
        self.calls = []

    def __call__(self, person, ref, plan, *, action, uid):
        self.calls.append(
            {
                "person": person,
                "ref": ref,
                "plan": deepcopy(plan),
                "action": action,
                "uid": uid,
            }
        )
        return {"queued": True}


def _restart(world):
    """A new process holding the same durable owner files."""
    world.gates = {
        person: Gate(person, client, lambda: world.identities, clock=world.clock)
        for person, client in world.gate_clients.items()
    }


async def _world(root, monkeypatch, *, trust=None, people=("om", "rahul", "priya")):
    global LAST_WORLD
    world = await build_world(
        root,
        monkeypatch=monkeypatch,
        people=people,
        trust=DEFAULT_TRUST if trust is None else trust,
    )
    world.calendar = CalendarQueue()
    monkeypatch.setattr(group_plans, "queue_calendar", world.calendar)
    monkeypatch.setattr(personal, "session", personal_session(world))
    LAST_WORLD = world
    return world


def _state(person):
    return group_plans.projection(person)


def _plan(person, reference=None):
    state = _state(person)
    stored = state.get("plans", {})
    if reference is None:
        return next(iter(stored.values()), None)
    if reference in stored:
        return stored[reference]
    token = state.get("tokens", {}).get(reference)
    return stored.get(token["plan"]) if token else None


def _calls(world, ref=None, action=None):
    return [
        call
        for call in world.calendar.calls
        if (ref is None or call["ref"] == ref) and (action is None or call["action"] == action)
    ]


async def _create(world, person="om", *, participants=("rahul", "priya"), content=None):
    token = await plans.request(
        person,
        "create",
        participants=list(participants),
        content=content or CONTENT,
    )
    await world.settle()
    plan = _plan(person, token)
    assert plan is not None, _state(person)
    return token, plan


async def _vote(world, person, reference, value="yes", *, agent=True):
    current = _plan(person, reference)
    exact = {"revision": current["revision"], "fingerprint": current["fingerprint"]}
    if agent:
        await plans.request(person, "vote", plan=reference, vote=value, **exact)
    else:
        payload = {"action": "vote", "plan": reference, "vote": value, **exact}
        await world.say(
            world.homes[person],
            person,
            f"@{person}-gate plan-request {json.dumps(payload)}",
            kind="user",
        )
    await world.settle()


async def _cancel(world, person, reference, *, agent=True, reason="plans changed"):
    current = _plan(person, reference)
    payload = {
        "action": "cancel",
        "plan": reference,
        "reason": reason,
        "revision": current["revision"],
        "fingerprint": current["fingerprint"],
    }
    if agent:
        await plans.request(person, "cancel", **{k: v for k, v in payload.items() if k != "action"})
    else:
        await world.say(
            world.homes[person],
            person,
            f"@{person}-gate plan-request {json.dumps(payload)}",
            kind="user",
        )
    await world.settle()


def _relay(plan, *, action, sender, **changes):
    payload = {
        "action": action,
        "from": sender,
        "voter": sender,
        "plan": plan["id"],
        "revision": plan["revision"],
        "fingerprint": plan["fingerprint"],
        "participants": list(plan["participants"]),
        "content": dict(plan["content"]),
        "vote": True,
        "via": "via-agent",
    }
    payload.update(changes)
    return json.dumps(payload)


async def consensus_and_calendar(root, monkeypatch):
    world = await _world(root, monkeypatch)
    token, plan = await _create(world)
    plan_id = plan["id"]

    assert plan["status"] == "pending"
    assert sorted(plan["participants"]) == ["om", "priya", "rahul"]
    assert token in plan["tokens"]
    assert world.switch.rooms[plan["room"]]["name"] == f"group-{plan_id}"
    assert {"om-gate", "rahul-gate", "priya-gate"} <= world.switch.rooms[plan["room"]]["members"]
    for person in ("om", "rahul", "priya"):
        assert _plan(person, plan_id)["status"] == "pending"
    assert not world.calendar.calls
    assert any(item["id"] == plan_id for item in group_plans.pending("om"))

    await _vote(world, "om", plan_id)
    await _vote(world, "rahul", plan_id, agent=False)
    assert not world.calendar.calls, "no calendar write before every participant votes"

    await _vote(world, "priya", plan_id)
    for person in ("om", "rahul", "priya"):
        current = _plan(person, plan_id)
        assert current["status"] == "confirmed"
        assert current["confirmed"]["revision"] == 1
        assert sum("✅" in body and plan_id in body for body in world.home_bodies(person)) == 1
    booked = _calls(world, plan_id)
    assert len(booked) == 3
    assert {call["person"] for call in booked} == {"om", "rahul", "priya"}
    assert {call["action"] for call in booked} == {"create"}
    assert {call["uid"] for call in booked} == {f"trustnet-group-{plan_id}"}
    for call in booked:
        assert call["plan"]["minutes"] == 120
        assert call["plan"]["title"] == CONTENT["title"]
        assert datetime.fromisoformat(call["plan"]["start"]).tzinfo is not None

    assert not any(item["id"] == plan_id for item in group_plans.pending("om"))
    await _vote(world, "priya", plan_id)  # late duplicate vote
    _restart(world)
    for gate in world.gates.values():
        await group_plans.recover(gate)
    await world.settle()
    assert len(_calls(world, plan_id)) == 3
    assert plans.status("om", token)["status"] == "confirmed"
    assert plans.status("om", plan_id)["status"] == "confirmed"
    assert any(item["id"] == plan_id for item in plans.list("om"))


async def authority_and_forgery(root, monkeypatch):
    trust = {
        "om": {"rahul": "close", "priya": "friend"},
        "rahul": {"om": "close"},  # does not trust priya: rejects the shared room
        "priya": {"om": "friend", "rahul": "friend"},
    }
    world = await _world(root, monkeypatch, trust=trust)

    # 1. The owner user may not draft.
    body = {
        "action": "create",
        "token": "a" * 32,
        "participants": ["rahul", "priya"],
        "content": CONTENT,
    }
    await world.say(
        world.homes["om"], "om", f"@om-gate plan-request {json.dumps(body)}", kind="user"
    )
    await world.settle()
    assert not _state("om")["plans"]

    # 5. Malformed JSON is refused without escaping dispatch.
    await world.say(world.homes["om"], "om-hermes", "@om-gate plan-request {oops")
    await world.settle()
    assert not _state("om")["plans"]

    # 4. Unknown participant, missing identity.
    await plans.request("om", "create", participants=["ghost"], content=CONTENT)
    await world.settle()
    assert not _state("om")["plans"]

    # 1. Direct consent: the main agent cannot vote, the owner user can.
    path = root / "om" / "trust.yaml"
    data = yaml.safe_load(path.read_text())
    data["consent"]["default"] = "direct"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    token, plan = await _create(world)
    plan_id = plan["id"]
    await _vote(world, "om", plan_id)
    assert "om" not in _plan("om", plan_id)["votes"]
    await _vote(world, "om", plan_id, agent=False)
    assert _plan("om", plan_id)["votes"]["om"]["vote"] is True

    # 4. Rahul does not trust Priya, so his gate refuses the shared room.
    assert _plan("rahul", plan_id) is None

    # 3. A gate cannot forge another participant's vote.
    started = _plan("om", plan_id)
    forged = _relay(started, action="vote", sender="rahul", voter="priya")
    await world.say(started["room"], "rahul-gate", f"@om-gate plan-relay {forged}")
    await world.settle()
    assert "priya" not in _plan("om", plan_id)["votes"]

    # 2. A main agent may not send a relay.
    hermes = _relay(started, action="vote", sender="rahul", voter="rahul")
    await world.say(started["room"], "rahul-hermes", f"@om-gate plan-relay {hermes}")
    await world.settle()
    assert "rahul" not in _plan("om", plan_id)["votes"]

    # 7. A stale participant set is ignored.
    stale = _relay(
        started,
        action="vote",
        sender="rahul",
        voter="rahul",
        participants=["om", "rahul"],
    )
    await world.say(started["room"], "rahul-gate", f"@om-gate plan-relay {stale}")
    await world.settle()
    assert "rahul" not in _plan("om", plan_id)["votes"]


async def stale_fingerprint_and_replay(root, monkeypatch):
    world = await _world(
        root,
        monkeypatch,
        people=("om", "rahul"),
        trust={"om": {"rahul": "close"}, "rahul": {"om": "close"}},
    )
    token, plan = await _create(world, participants=("rahul",))
    plan_id = plan["id"]

    # 6. A retried create token is idempotent.
    await plans.request("om", "create", participants=["rahul"], content=CONTENT, token=token)
    await world.settle()
    assert len(_state("om")["plans"]) == 1
    assert len(world.rooms_named("group-")) == 1

    # 7. A wrong fingerprint does not record a vote.
    wrong = _relay(plan, action="vote", sender="rahul", fingerprint="0" * 64)
    await world.say(plan["room"], "rahul-gate", f"@om-gate plan-relay {wrong}")
    await world.settle()
    assert "rahul" not in _plan("om", plan_id)["votes"]

    # 8. A replay records one vote, not two.
    good = _relay(plan, action="vote", sender="rahul")
    await world.say(plan["room"], "rahul-gate", f"@om-gate plan-relay {good}")
    await world.settle()
    await world.say(plan["room"], "rahul-gate", f"@om-gate plan-relay {good}")
    await world.settle()
    votes = _plan("om", plan_id)["votes"]
    assert votes["rahul"]["vote"] is True
    assert list(votes) == ["rahul"]

    await _vote(world, "om", plan_id)
    assert _plan("om", plan_id)["status"] == "confirmed"
    # Rahul's own gate records its vote after the relayed replay was proven.
    await _vote(world, "rahul", plan_id)
    for person in ("om", "rahul"):
        assert _plan(person, plan_id)["status"] == "confirmed"
    assert len(_calls(world, plan_id, "create")) == 2


async def revision_keeps_confirmed(root, monkeypatch):
    world = await _world(
        root,
        monkeypatch,
        people=("om", "rahul"),
        trust={"om": {"rahul": "close"}, "rahul": {"om": "close"}},
    )
    token, plan = await _create(world, participants=("rahul",))
    plan_id = plan["id"]
    await _vote(world, "om", plan_id)
    await _vote(world, "rahul", plan_id)
    assert len(_calls(world, plan_id, "create")) == 2

    # 12. A revision is pending but the old confirmed plan still stands.
    await plans.request(
        "om",
        "revise",
        plan=plan_id,
        revision=_plan("om", plan_id)["revision"],
        fingerprint=_plan("om", plan_id)["fingerprint"],
        content=CONTENT_2,
    )
    await world.settle()
    for person in ("om", "rahul"):
        current = _plan(person, plan_id)
        assert current["status"] == "pending"
        assert current["revision"] == 2
        assert current["confirmed"]["revision"] == 1
        assert current["votes"] == {}
    assert not _calls(world, plan_id, "update")

    # 5/7. Changing the participant set is refused.
    await plans.request(
        "om",
        "revise",
        plan=plan_id,
        revision=_plan("om", plan_id)["revision"],
        fingerprint=_plan("om", plan_id)["fingerprint"],
        participants=["om", "rahul", "priya"],
        content=CONTENT_3,
    )
    await world.settle()
    assert _plan("om", plan_id)["revision"] == 2

    # 13. A declined replacement keeps the old confirmed plan.
    await _vote(world, "rahul", plan_id, value="no")
    for person in ("om", "rahul"):
        current = _plan(person, plan_id)
        assert current["status"] == "confirmed"
        assert current["confirmed"]["revision"] == 1
        assert current["candidate_declined"] is True
    assert not _calls(world, plan_id, "update")
    assert len(_calls(world, plan_id, "create")) == 2

    # 12. An approved replacement updates the same stable UID.
    await plans.request(
        "om",
        "revise",
        plan=plan_id,
        revision=_plan("om", plan_id)["revision"],
        fingerprint=_plan("om", plan_id)["fingerprint"],
        content=CONTENT_3,
    )
    await world.settle()
    await _vote(world, "om", plan_id)
    await _vote(world, "rahul", plan_id)
    for person in ("om", "rahul"):
        current = _plan(person, plan_id)
        assert current["status"] == "confirmed"
        assert current["confirmed"]["revision"] == 3
    updates = _calls(world, plan_id, "update")
    assert len(updates) == 2
    assert {call["uid"] for call in updates} == {f"trustnet-group-{plan_id}"}
    assert {call["plan"]["title"] for call in updates} == {CONTENT_3["title"]}
    assert len(_calls(world, plan_id, "create")) == 2


async def cancellation_lifecycle(root, monkeypatch):
    world = await _world(
        root,
        monkeypatch,
        people=("om", "rahul"),
        trust={"om": {"rahul": "close"}, "rahul": {"om": "close"}},
    )

    # 14. Cancel after confirmation, after a restart.
    token, plan = await _create(world, participants=("rahul",))
    plan_id = plan["id"]
    await _vote(world, "om", plan_id)
    await _vote(world, "rahul", plan_id)
    assert len(_calls(world, plan_id, "create")) == 2
    _restart(world)
    await _cancel(world, "rahul", plan_id, agent=False)
    for person in ("om", "rahul"):
        current = _plan(person, plan_id)
        assert current["status"] == "cancelled"
        assert current["confirmed"]["revision"] == 1
    cancelled = _calls(world, plan_id, "cancel")
    assert len(cancelled) == 2
    assert {call["uid"] for call in cancelled} == {f"trustnet-group-{plan_id}"}
    await _vote(world, "om", plan_id)
    assert _plan("om", plan_id)["status"] == "cancelled"

    # 14. Cancel before confirmation: no calendar job exists yet.
    _, early = await _create(world, participants=("rahul",), content=CONTENT_2)
    await _cancel(world, "om", early["id"])
    assert _plan("om", early["id"])["status"] == "cancelled"
    assert _plan("rahul", early["id"])["status"] == "cancelled"
    assert not _calls(world, early["id"], "create")

    # 14. Cancel during confirmation: still no calendar commit.
    _, midway = await _create(world, participants=("rahul",), content=CONTENT_3)
    await _vote(world, "om", midway["id"])
    assert not _calls(world, midway["id"], "create")
    await _cancel(world, "rahul", midway["id"], agent=False)
    assert _plan("om", midway["id"])["status"] == "cancelled"
    assert _plan("rahul", midway["id"])["status"] == "cancelled"
    assert not _calls(world, midway["id"], "create")


async def delayed_replies_and_expiry(root, monkeypatch):
    world = await _world(
        root,
        monkeypatch,
        people=("om", "rahul"),
        trust={"om": {"rahul": "close"}, "rahul": {"om": "close"}},
    )
    token, plan = await _create(world, participants=("rahul",))
    plan_id = plan["id"]

    # 16. Three days later is still inside the multi-day window.
    world.clock.advance(days=3)
    await _vote(world, "om", plan_id)
    await _vote(world, "rahul", plan_id)
    assert _plan("om", plan_id)["status"] == "confirmed"
    assert len(_calls(world, plan_id, "create")) == 2

    # 16. An abandoned plan expires only after the multi-day window.
    _, abandoned = await _create(world, participants=("rahul",), content=CONTENT_2)
    abandoned_id = abandoned["id"]
    world.clock.advance(days=31)
    for gate in world.gates.values():
        await group_plans.recover(gate)
    await world.settle()
    for person in ("om", "rahul"):
        assert _plan(person, abandoned_id)["status"] == "expired"
    await _vote(world, "om", abandoned_id)
    assert _plan("om", abandoned_id)["status"] == "expired"


async def durable_outbox(root, monkeypatch):
    world = await _world(
        root,
        monkeypatch,
        people=("om", "rahul"),
        trust={"om": {"rahul": "close"}, "rahul": {"om": "close"}},
    )
    client = world.gate_clients["om"]
    original_post = client.post_message

    async def relay_down(body, *args, **kwargs):
        if body.startswith("@rahul-gate plan-relay"):
            raise ConnectionError("relay down")
        return await original_post(body, *args, **kwargs)

    monkeypatch.setattr(client, "post_message", relay_down)
    token = await plans.request("om", "create", participants=["rahul"], content=CONTENT)
    await world.settle()
    plan = _plan("om", token)
    assert plan is not None
    assert _plan("rahul", plan["id"]) is None
    assert any(not job["done"] for job in plan["jobs"].values())

    # 9/10. A restart retries the durable outbox and delivers the offer.
    monkeypatch.setattr(client, "post_message", original_post)
    _restart(world)
    for gate in world.gates.values():
        await group_plans.recover(gate)
    await world.settle()
    assert _plan("rahul", plan["id"]) is not None

    # 10. A failed calendar enqueue remains pending and is retried once.
    attempts = {"om": 0}

    def flaky_calendar(person, ref, booked, *, action, uid):
        if person == "om" and attempts["om"] == 0:
            attempts["om"] += 1
            raise ConnectionError("calendar unavailable")
        return world.calendar(person, ref, booked, action=action, uid=uid)

    monkeypatch.setattr(group_plans, "queue_calendar", flaky_calendar)
    await _vote(world, "om", plan["id"])
    await _vote(world, "rahul", plan["id"])
    assert not any(call["person"] == "om" for call in world.calendar.calls)
    assert any(call["person"] == "rahul" for call in world.calendar.calls)

    _restart(world)
    for gate in world.gates.values():
        await group_plans.recover(gate, force=True)
    await world.settle()
    assert (
        sum(call["person"] == "om" and call["ref"] == plan["id"] for call in world.calendar.calls)
        == 1
    )
    for gate in world.gates.values():
        await group_plans.recover(gate, force=True)
    assert (
        sum(call["person"] == "om" and call["ref"] == plan["id"] for call in world.calendar.calls)
        == 1
    )


async def exact_consent_and_revision_authority(root, monkeypatch):
    world = await _world(
        root,
        monkeypatch,
        people=("om", "rahul"),
        trust={"om": {"rahul": "close"}, "rahul": {"om": "close"}},
    )
    _, plan = await _create(world, participants=("rahul",))
    ref = plan["id"]
    await plans.request("om", "vote", plan=ref, vote="yes")
    await world.settle()
    assert _plan("om", ref)["votes"] == {}, "Missing revision cannot approve the latest plan"
    await plans.request(
        "rahul", "revise", plan=ref, content=CONTENT_2, revision=1, fingerprint=plan["fingerprint"]
    )
    await world.settle()
    assert all(_plan(p, ref)["revision"] == 1 for p in ("om", "rahul"))
    await plans.request(
        "om", "revise", plan=ref, content=CONTENT_2, revision=1, fingerprint=plan["fingerprint"]
    )
    await world.settle()
    await plans.request(
        "rahul", "vote", plan=ref, vote="yes", revision=1, fingerprint=plan["fingerprint"]
    )
    await world.settle()
    assert _plan("rahul", ref)["votes"] == {}
    await plans.request("om", "cancel", plan=ref)
    await world.settle()
    assert _plan("om", ref)["status"] == "pending"
    await _cancel(world, "om", ref)
    assert all(_plan(p, ref)["status"] == "cancelled" for p in ("om", "rahul"))


async def revoked_outbox(root, monkeypatch):
    from trustnet.gate.facts import load_trust, save_trust

    world = await _world(
        root,
        monkeypatch,
        people=("om", "rahul"),
        trust={"om": {"rahul": "close"}, "rahul": {"om": "close"}},
    )
    client = world.gate_clients["om"]
    original = client.post_message

    async def unavailable(body, *args, **kwargs):
        if body.startswith("@rahul-gate plan-relay"):
            raise ConnectionError("offline")
        return await original(body, *args, **kwargs)

    monkeypatch.setattr(client, "post_message", unavailable)
    _, plan = await _create(world, participants=("rahul",))
    trust = load_trust("om")
    trust.block("rahul")
    save_trust(trust, root / "om" / "trust.yaml")
    monkeypatch.setattr(client, "post_message", original)
    await group_plans.recover(world.gates["om"])
    await world.settle()
    assert _plan("rahul", plan["id"]) is None
    assert not any(body.startswith("@rahul-gate plan-relay") for body in world.bodies(plan["room"]))


async def interrupted_room_creation(root, monkeypatch):
    from trustnet.switch_client import SwitchError

    world = await _world(
        root,
        monkeypatch,
        people=("om", "rahul"),
        trust={"om": {"rahul": "close"}, "rahul": {"om": "close"}},
    )
    client = world.gate_clients["om"]
    original = client.create_room
    interrupted = False

    async def create(*args, **kwargs):
        nonlocal interrupted
        result = await original(*args, **kwargs)
        if args[0].startswith("group-") and not interrupted:
            interrupted = True
            raise SwitchError("Room created; acknowledgment interrupted")
        return result

    monkeypatch.setattr(client, "create_room", create)
    token = "interrupted-create-token"
    await plans.request("om", "create", token=token, participants=["rahul"], content=CONTENT)
    await world.settle()
    assert len(world.rooms_named("group-")) == 1
    await plans.request("om", "create", token=token, participants=["rahul"], content=CONTENT)
    await world.settle()
    assert len(world.rooms_named("group-")) == 1
    assert plans.status("om", token)["id"] == plans.status("rahul", token)["id"]


SCENARIOS = [
    consensus_and_calendar,
    authority_and_forgery,
    stale_fingerprint_and_replay,
    revision_keeps_confirmed,
    cancellation_lifecycle,
    delayed_replies_and_expiry,
    durable_outbox,
    exact_consent_and_revision_authority,
    revoked_outbox,
    interrupted_room_creation,
]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.__name__)
async def test_group_plan_scenario(scenario, tmp_path, monkeypatch):
    await scenario(tmp_path, monkeypatch)
