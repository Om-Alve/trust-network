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


SCENARIOS = [agent_calendar_delivery, calendar_revisions, all_day_availability, reviewed_outgoing]
