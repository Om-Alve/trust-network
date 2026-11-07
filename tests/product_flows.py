"""Product behavior scenarios. Failure cases are in docs/product-fixes.md."""

from datetime import datetime

from trustnet.gate import calendar_jobs, consent
from trustnet.gate.calendar import busy
from trustnet.tn import mcp, personal


async def agent_calendar_delivery(h):
    h.patch.setenv("TN_CALENDAR_DELIVERY", "agent")
    room = await h.open()
    await h.propose(room)
    await h.vote("om")
    assert calendar_jobs.pending("om") == []
    await h.vote("rahul")
    task = calendar_jobs.pending("om")[0]
    assert task["action"] == "create"
    assert task["plan"]["title"] == "Games ☕"
    assert task["status"] == "pending"
    assert len(calendar_jobs.pending("rahul")) == 1
    h.restart()
    await consent.recover(h.gates["om"])
    assert [t["token"] for t in calendar_jobs.pending("om")] == [task["token"]]
    server = mcp.build("om")
    response = await server.call_tool(
        "calendar_report",
        {"token": task["token"], "status": "failed", "error": "Provider unavailable"},
    )
    assert response.structured_content["status"] == "failed"
    assert personal.open_items("om")[-1]["kind"] == "calendar"
    response = await server.call_tool(
        "calendar_report",
        {
            "token": task["token"],
            "status": "applied",
            "provider": "google",
            "event_id": "provider-event-42",
        },
    )
    assert response.structured_content["event_id"] == "provider-event-42"
    assert calendar_jobs.pending("om") == []
    receipt = calendar_jobs.report("om", task["token"], "applied", "google", "provider-event-42")
    assert receipt["event_id"] == "provider-event-42"
    h.trace.append("Calendar provider simulated by agent; receipt google/provider-event-42")


async def calendar_revisions(h):
    h.patch.setenv("TN_CALENDAR_DELIVERY", "agent")
    plan = {
        "start": "2026-11-09T19:00:00+05:30",
        "minutes": 120,
        "title": "Dinner",
        "place": "Cafe",
    }
    first = calendar_jobs.queue("om", "P88", plan, uid="stable-event")
    calendar_jobs.report("om", first["token"], "applied", "outlook", "outlook-17")
    changed = {**plan, "start": "2026-11-10T19:00:00+05:30"}
    second = calendar_jobs.queue("om", "P89", changed, action="update", uid="stable-event")
    assert second["event_id"] == "outlook-17"
    assert second["uid"] == first["uid"]
    replayed = calendar_jobs.queue("om", "P88", plan, uid="stable-event")
    assert replayed["token"] == second["token"]
    assert calendar_jobs.pending("om")[0]["action"] == "update"
    try:
        calendar_jobs.report("om", first["token"], "applied", "outlook", "outlook-17")
    except ValueError as exc:
        assert "superseded" in str(exc)
    else:
        raise AssertionError("A stale receipt acknowledged a newer revision")
    calendar_jobs.report("om", second["token"], "applied", "outlook", "outlook-17")
    cancelled = calendar_jobs.queue("om", "P89", changed, action="cancel", uid="stable-event")
    assert cancelled["event_id"] == "outlook-17"
    assert cancelled["action"] == "cancel"
    calendar_jobs.report("om", cancelled["token"], "applied", "outlook", "outlook-17")
    assert calendar_jobs.pending("om") == []


async def all_day_availability(h):
    h.patch.setenv("TN_TIMEZONE", "America/New_York")
    path = h.root / "om" / "calendar.ics"
    path.write_text(
        "BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:holiday\n"
        "DTSTART;VALUE=DATE:20261101\nDTEND;VALUE=DATE:20261102\n"
        "SUMMARY:Unavailable\nEND:VEVENT\nEND:VCALENDAR\n"
    )
    blocks = busy(
        path,
        datetime.fromisoformat("2026-11-01T00:00:00-04:00"),
        datetime.fromisoformat("2026-11-02T00:00:00-05:00"),
    )
    assert len(blocks) == 1
    assert blocks[0].start.isoformat() == "2026-11-01T00:00:00-04:00"
    assert blocks[0].end.isoformat() == "2026-11-02T00:00:00-05:00"
    h.trace.append("DST all-day block: " + str(blocks[0]))


async def reviewed_outgoing(h):
    from trustnet.tn import outgoing

    room = await h.open()
    h.patch.setenv("TN_OUTGOING", "review")
    # Use the personal-agent API, not the gate's internal Switch client.
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def session(person):
        yield next(c for c in h.switch.clients if c.name == person + "-hermes")

    h.patch.setattr(personal, "session", session)
    draft = await personal.dm_post("om", room, "I can meet at seven.")
    assert draft["status"] == "awaiting-owner"
    assert "I can meet at seven." not in h.bodies(room)
    approved = await outgoing.release("om", draft["ref"])
    assert approved["status"] == "sent"
    assert h.bodies(room).count("I can meet at seven.") == 1
    await outgoing.release("om", draft["ref"])
    assert h.bodies(room).count("I can meet at seven.") == 1
    rejected = await personal.dm_post("om", room, "Private detail I should not share")
    outgoing.decline("om", rejected["ref"])
    assert "Private detail I should not share" not in h.bodies(room)
    from trustnet.gate.facts import load_trust, save_trust

    trust = load_trust("om")
    del trust.people["rahul"]
    save_trust(trust, h.root / "om" / "trust.yaml")
    try:
        await personal.dm_post("om", room, "Stale room after revocation")
    except ValueError as exc:
        assert "trust" in str(exc)
    else:
        raise AssertionError("Revoked friendship retained outgoing access")


async def blocked_approval_and_gift_permissions(h):
    import json

    from trustnet.gate import fact_changes
    from trustnet.gate.facts import Level, PersonPermissions, load_trust, save_trust

    pending = fact_changes.suggest("om", "sam", "friend", trust=True)
    trust = load_trust("om")
    trust.block("sam")
    trust.permissions["rahul"] = PersonPermissions(deny={"wishlist", "interests", "sizes"})
    save_trust(trust, h.root / "om" / "trust.yaml")
    try:
        fact_changes.decide("om", pending["ref"], True)
    except ValueError as exc:
        assert "blocked" in str(exc)
    else:
        raise AssertionError("A stale trust review approved a blocked person")
    await h.send(h.homes["om"], "om", "@om-gate trust sam close")
    assert load_trust("om").level_for("sam") is None
    # A rejected approval must not poison future local edits.
    assert fact_changes.suggest("om", "alex", "friend", trust=True)["status"] == "pending"
    request = {
        "friend": "om",
        "token": "a" * 32,
        "action": "ideas",
        "occasion": "birthday",
        "date": "2026-11-20",
        "budget": 3000,
    }
    await h.send(
        h.homes["rahul"], "rahul-hermes", "@rahul-gate gift-request " + json.dumps(request)
    )
    result = next(
        body
        for body in h.bodies(h.homes["rahul"])
        if body.startswith("gift-result " + "a" * 32 + " ")
    )
    payload = json.loads(result.removeprefix("gift-result " + "a" * 32 + " "))
    assert payload == {"suggestions": [], "taken": [], "over_budget": []}
    assert load_trust("om").level_for("rahul") is Level.CLOSE


async def group_calendar_lifecycle(h):
    from contextlib import asynccontextmanager

    from trustnet.gate import group_plans
    from trustnet.gate.facts import Level, load_trust, save_trust

    h.patch.setenv("TN_CALENDAR_DELIVERY", "agent")
    for person in h.clients:
        trust = load_trust(person)
        for peer in h.clients:
            if peer != person:
                trust.grant(peer, Level.FRIEND)
        save_trust(trust, h.root / person / "trust.yaml")

    @asynccontextmanager
    async def session(person):
        yield next(c for c in h.switch.clients if c.name == person + "-hermes")

    h.patch.setattr(personal, "session", session)

    async def call(person, tool, **arguments):
        response = await mcp.build(person).call_tool(tool, arguments)
        await h.drain()
        return response.structured_content

    token = (
        await call(
            "om",
            "group_plan_create",
            participants=["rahul", "priya"],
            start="2026-11-20T19:00:00+05:30",
            minutes=120,
            title="Dinner",
            place="Cafe",
        )
    )["token"]
    plan = group_plans.status("om", token)
    assert plan is not None
    reference, uid = plan["id"], plan["uid"]
    assert all(group_plans.status(p, reference)["status"] == "pending" for p in h.clients)
    assert any(item["kind"] == "group-plan" for item in personal.open_items("rahul"))

    async def vote(person):
        current = group_plans.status(person, reference)
        await call(
            person,
            "group_plan_vote",
            reference=reference,
            vote="yes",
            revision=current["revision"],
            fingerprint=current["fingerprint"],
        )

    await vote("om")
    await vote("rahul")
    assert all(calendar_jobs.pending(p) == [] for p in h.clients)
    await vote("priya")
    for person in h.clients:
        task = calendar_jobs.pending(person)[0]
        assert task["action"] == "create"
        assert task["uid"] == uid
        calendar_jobs.report(person, task["token"], "applied", "outlook", person + "-event")

    stale = group_plans.status("om", reference)
    await call(
        "om",
        "group_plan_revise",
        reference=reference,
        revision=stale["revision"],
        fingerprint=stale["fingerprint"],
        start="2026-11-21T19:00:00+05:30",
        minutes=90,
        title="Dinner",
        place="Terrace",
    )
    await call(
        "rahul",
        "group_plan_vote",
        reference=reference,
        vote="yes",
        revision=stale["revision"],
        fingerprint=stale["fingerprint"],
    )
    assert group_plans.status("rahul", reference)["votes"] == {}
    for person in h.clients:
        assert calendar_jobs.pending(person) == []
        await vote(person)
    for person in h.clients:
        task = calendar_jobs.pending(person)[0]
        assert task["action"] == "update"
        assert task["uid"] == uid
        assert task["event_id"] == person + "-event"
        assert task["plan"]["place"] == "Terrace"
        calendar_jobs.report(person, task["token"], "applied", "outlook", person + "-event")
    current = group_plans.status("rahul", reference)
    await call(
        "rahul",
        "group_plan_cancel",
        reference=reference,
        reason="Plans changed",
        revision=current["revision"],
        fingerprint=current["fingerprint"],
    )
    for person in h.clients:
        assert group_plans.status(person, reference)["status"] == "cancelled"
        task = calendar_jobs.pending(person)[0]
        assert task["action"] == "cancel"
        assert task["event_id"] == person + "-event"
    h.restart()
    for gate in h.gates.values():
        await group_plans.recover(gate)
    assert all(len(calendar_jobs.pending(p)) == 1 for p in h.clients)
    for person in h.clients:
        task = calendar_jobs.pending(person)[0]
        await call(
            person,
            "calendar_report",
            token=task["token"],
            status="applied",
            provider="outlook",
            event_id=person + "-event",
        )
        assert calendar_jobs.pending(person) == []
    h.trace.append(
        "Three-person approval, stale vote rejection, same-event update and cancellation"
    )


async def cross_timezone_consent(h):
    from pytest import MonkeyPatch

    h.patch.setenv("TN_CALENDAR_DELIVERY", "agent")
    zones = {"om": "America/New_York", "rahul": "Asia/Kolkata", "priya": "UTC"}
    for person, gate in h.gates.items():
        original = gate.handle

        async def handle(event, person=person, original=original):
            with MonkeyPatch.context() as patch:
                patch.setenv("TN_TIMEZONE", zones[person])
                await original(event)

        h.patch.setattr(gate, "handle", handle)
    room = await h.open()
    await h.propose(room)
    assert consent.load("om")["P1"]["card"] == consent.load("rahul")["P1"]["card"]
    await h.vote("om")
    await h.vote("rahul")
    assert all(consent.load(p)["P1"]["status"] == "confirmed" for p in ("om", "rahul"))
    assert calendar_jobs.pending("om")[0]["plan"]["start"] == "2026-11-09T19:00:00-05:00"
    assert calendar_jobs.pending("rahul")[0]["plan"]["start"] == "2026-11-09T19:00:00-05:00"


SCENARIOS = [
    agent_calendar_delivery,
    calendar_revisions,
    all_day_availability,
    reviewed_outgoing,
    blocked_approval_and_gift_permissions,
    group_calendar_lifecycle,
    cross_timezone_consent,
]
