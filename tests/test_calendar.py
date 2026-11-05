"""Tests for reading busy blocks out of ``.ics`` files and writing events back."""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from icalendar import Calendar

from trustnet.gate.calendar import Block, CalendarError, add_event, busy
from trustnet.gate.facts import EXAMPLES_DIR

IST = ZoneInfo("Asia/Kolkata")
OM = EXAMPLES_DIR / "om" / "calendar.ics"
RAHUL = EXAMPLES_DIR / "rahul" / "calendar.ics"


def at(*args: int) -> datetime:
    """An Asia/Kolkata datetime: ``at(2026, 11, 8, 21, 0)``."""
    return datetime(*args, tzinfo=IST)


def write_calendar(path: Path, *events: str) -> Path:
    """Write a minimal VCALENDAR whose body is the given VEVENT blocks."""
    body = "".join(event.strip() + "\n" for event in events)
    path.write_text(
        "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//trust-network//test//EN\n"
        + body
        + "END:VCALENDAR\n",
        encoding="utf-8",
    )
    return path


def copy_fixture(person: str, target: Path) -> Path:
    """Copy a fixture calendar to ``target`` so a test can write to it."""
    target.write_bytes((EXAMPLES_DIR / person / "calendar.ics").read_bytes())
    return target


def uids(path: Path) -> list[str]:
    calendar = Calendar.from_ical(Path(path).read_bytes())
    return [str(event.get("UID")) for event in calendar.walk("VEVENT")]


# --- busy(): clipping, recurrence, merging ---------------------------------


def test_busy_clips_an_event_to_the_range() -> None:
    blocks = busy(OM, at(2026, 11, 8, 18), at(2026, 11, 8, 20))

    assert blocks == [
        Block(at(2026, 11, 8, 18), at(2026, 11, 8, 19), "Family video call"),
    ]


def test_busy_expands_weekly_recurrences() -> None:
    first_week = busy(OM, at(2026, 11, 9), at(2026, 11, 16))
    second_week = busy(OM, at(2026, 11, 16), at(2026, 11, 23))

    assert first_week == [
        Block(at(2026, 11, 10, 20), at(2026, 11, 10, 21, 30), "Badminton"),
        Block(at(2026, 11, 12, 19), at(2026, 11, 12, 20), "Spanish class"),
    ]
    assert second_week == [
        Block(at(2026, 11, 17, 20), at(2026, 11, 17, 21, 30), "Badminton"),
        Block(at(2026, 11, 19, 19), at(2026, 11, 19, 20), "Spanish class"),
    ]


def test_busy_merges_overlapping_and_touching_blocks(tmp_path: Path) -> None:
    path = write_calendar(
        tmp_path / "merge.ics",
        """
BEGIN:VEVENT
UID:a
DTSTART;TZID=Asia/Kolkata:20261108T090000
DTEND;TZID=Asia/Kolkata:20261108T100000
SUMMARY:Breakfast
END:VEVENT
""",
        """
BEGIN:VEVENT
UID:b
DTSTART;TZID=Asia/Kolkata:20261108T093000
DTEND;TZID=Asia/Kolkata:20261108T103000
SUMMARY:Bowling
END:VEVENT
""",
        """
BEGIN:VEVENT
UID:c
DTSTART;TZID=Asia/Kolkata:20261108T103000
DTEND;TZID=Asia/Kolkata:20261108T110000
SUMMARY:Dinner
END:VEVENT
""",
        """
BEGIN:VEVENT
UID:d
DTSTART;TZID=Asia/Kolkata:20261108T120000
DTEND;TZID=Asia/Kolkata:20261108T130000
SUMMARY:Errands
END:VEVENT
""",
    )

    blocks = busy(path, at(2026, 11, 8, 8), at(2026, 11, 8, 14))

    assert blocks == [
        Block(at(2026, 11, 8, 9), at(2026, 11, 8, 11), "Breakfast + Bowling + Dinner"),
        Block(at(2026, 11, 8, 12), at(2026, 11, 8, 13), "Errands"),
    ]


def test_busy_keeps_one_title_for_a_run_of_the_same_event(tmp_path: Path) -> None:
    path = write_calendar(
        tmp_path / "gym.ics",
        """
BEGIN:VEVENT
UID:gym-1
DTSTART;TZID=Asia/Kolkata:20261108T090000
DTEND;TZID=Asia/Kolkata:20261108T100000
SUMMARY:Gym
END:VEVENT
""",
        """
BEGIN:VEVENT
UID:gym-2
DTSTART;TZID=Asia/Kolkata:20261108T100000
DTEND;TZID=Asia/Kolkata:20261108T110000
SUMMARY:Gym
END:VEVENT
""",
    )

    assert busy(path, at(2026, 11, 8, 8), at(2026, 11, 8, 12)) == [
        Block(at(2026, 11, 8, 9), at(2026, 11, 8, 11), "Gym"),
    ]


def test_busy_skips_all_day_transparent_and_cancelled_events(tmp_path: Path) -> None:
    path = write_calendar(
        tmp_path / "skips.ics",
        """
BEGIN:VEVENT
UID:all-day
DTSTART;VALUE=DATE:20261108
SUMMARY:Holiday
END:VEVENT
""",
        """
BEGIN:VEVENT
UID:free
DTSTART;TZID=Asia/Kolkata:20261108T120000
DTEND;TZID=Asia/Kolkata:20261108T130000
SUMMARY:Open house
TRANSP:TRANSPARENT
END:VEVENT
""",
        """
BEGIN:VEVENT
UID:cancelled
DTSTART;TZID=Asia/Kolkata:20261108T140000
DTEND;TZID=Asia/Kolkata:20261108T150000
SUMMARY:Cancelled class
STATUS:CANCELLED
END:VEVENT
""",
        """
BEGIN:VEVENT
UID:real
DTSTART;TZID=Asia/Kolkata:20261108T160000
DTEND;TZID=Asia/Kolkata:20261108T170000
SUMMARY:Real plan
END:VEVENT
""",
    )

    assert busy(path, at(2026, 11, 8), at(2026, 11, 9)) == [
        Block(at(2026, 11, 8, 16), at(2026, 11, 8, 17), "Real plan"),
    ]


def test_floating_times_are_read_as_asia_kolkata(tmp_path: Path) -> None:
    path = write_calendar(
        tmp_path / "floating.ics",
        """
BEGIN:VEVENT
UID:floating
DTSTART:20261108T210000
DTEND:20261108T220000
SUMMARY:Floating dinner
END:VEVENT
""",
    )

    blocks = busy(path, at(2026, 11, 8, 20), at(2026, 11, 9, 0))

    assert blocks == [Block(at(2026, 11, 8, 21), at(2026, 11, 8, 22), "Floating dinner")]
    assert blocks[0].start.utcoffset() == timedelta(hours=5, minutes=30)


def test_block_reads_naive_times_as_asia_kolkata() -> None:
    block = Block(datetime(2026, 11, 8, 21), datetime(2026, 11, 8, 23), " Dinner ")

    assert block == Block(at(2026, 11, 8, 21), at(2026, 11, 8, 23), "Dinner")
    assert block.start.tzinfo == IST


# --- busy(): errors --------------------------------------------------------


def test_busy_rejects_an_empty_range() -> None:
    with pytest.raises(CalendarError, match="range must end after"):
        busy(OM, at(2026, 11, 8, 20), at(2026, 11, 8, 20))


def test_busy_reports_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CalendarError, match="file not found"):
        busy(tmp_path / "missing.ics", at(2026, 11, 8), at(2026, 11, 9))


# --- add_event(): write, read back, idempotency ----------------------------


def test_add_event_writes_an_event_that_busy_reads_back(tmp_path: Path) -> None:
    path = copy_fixture("om", tmp_path / "calendar.ics")
    start = at(2026, 11, 8, 21)

    block = add_event(
        path,
        start,
        timedelta(hours=2),
        "Bowling + dinner",
        "Smaaash, Indiranagar",
        "P1",
    )

    assert block == Block(start, at(2026, 11, 8, 23), "Bowling + dinner")
    assert busy(path, at(2026, 11, 8, 20), at(2026, 11, 9, 0)) == [block]

    event = next(
        event
        for event in Calendar.from_ical(path.read_bytes()).walk("VEVENT")
        if str(event.get("UID")) == "P1"
    )
    assert event.decoded("DTSTART") == start
    assert event.decoded("DTEND") == at(2026, 11, 8, 23)
    assert str(event.get("SUMMARY")) == "Bowling + dinner"
    assert str(event.get("LOCATION")) == "Smaaash, Indiranagar"


def test_p1_added_twice_to_om_copy_appears_once(tmp_path: Path) -> None:
    """Done-when: writing P1 into a temp copy of Om's calendar reads back once."""
    path = copy_fixture("om", tmp_path / "calendar.ics")
    start = at(2026, 11, 8, 21)

    first = add_event(path, start, timedelta(hours=2), "Bowling + dinner", "Smaaash", "P1")
    after_first = path.read_bytes()
    second = add_event(path, start, timedelta(hours=2), "Bowling + dinner", "Smaaash", "P1")

    assert second == first
    assert path.read_bytes() == after_first
    assert uids(path).count("P1") == 1
    assert busy(path, at(2026, 11, 8, 20), at(2026, 11, 9, 0)) == [first]


def test_add_event_accepts_minutes_and_generates_a_uid(tmp_path: Path) -> None:
    path = copy_fixture("rahul", tmp_path / "calendar.ics")

    block = add_event(path, at(2026, 11, 9, 20), 90, "Cricket nets")

    assert block == Block(at(2026, 11, 9, 20), at(2026, 11, 9, 21, 30), "Cricket nets")
    generated = [uid for uid in uids(path) if uid.endswith("@trust-network")]
    assert len(generated) == 1


def test_add_event_creates_a_missing_calendar(tmp_path: Path) -> None:
    path = tmp_path / "new" / "calendar.ics"

    add_event(path, at(2026, 11, 8, 21), timedelta(hours=2), "Dinner", uid="P1")

    assert path.is_file()
    assert uids(path) == ["P1"]
    assert busy(path, at(2026, 11, 8), at(2026, 11, 9)) == [
        Block(at(2026, 11, 8, 21), at(2026, 11, 8, 23), "Dinner"),
    ]


@pytest.mark.parametrize("duration", [0, -30, timedelta(0), timedelta(minutes=-5), "2h"])
def test_add_event_rejects_a_bad_duration(tmp_path: Path, duration: object) -> None:
    with pytest.raises(CalendarError, match="duration must be"):
        add_event(tmp_path / "calendar.ics", at(2026, 11, 8, 21), duration, "Dinner", uid="P1")


# --- the fixture calendars play out the scenes -----------------------------


def test_done_when_rahul_cricket_ends_at_2030() -> None:
    blocks = busy(RAHUL, at(2026, 11, 8, 18), at(2026, 11, 9, 0))

    assert blocks == [Block(at(2026, 11, 8, 18), at(2026, 11, 8, 20, 30), "Cricket")]


def test_om_is_busy_before_1900_and_free_after() -> None:
    assert busy(OM, at(2026, 11, 8, 19), at(2026, 11, 9, 0)) == []


@pytest.mark.parametrize("person", ["om", "rahul"])
def test_tent_weekend_is_free(person: str) -> None:
    path = EXAMPLES_DIR / person / "calendar.ics"

    assert busy(path, at(2026, 11, 14), at(2026, 11, 17)) == []
