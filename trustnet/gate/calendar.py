"""Busy blocks and event writing for local ``.ics`` calendars.

The gate only ever needs two things from a calendar: what its owner is busy
with (so a friend's agent can propose a time) and a place to put a plan both
people accepted. :func:`busy` answers the first, :func:`add_event` writes the
second.

Decisions this module makes, so the rest of the gate can rely on them:

- **Time zone.** Every ``datetime`` is aware, using ``TN_TIMEZONE`` or the legacy
  ``Asia/Kolkata`` default. Floating times use that configured zone.
- **Half-open blocks.** A :class:`Block` covers ``start`` up to but not
  including ``end``, so 19:00–20:00 and 20:00–21:00 only touch, they don't
  overlap.
- **Clipping.** ``busy`` returns the part of each event that falls inside the
  requested range, never the whole event.
- **Merging.** Overlapping *and* touching blocks are merged, because a person
  with back-to-back events is busy for the whole stretch. The merged block's
  title joins the distinct titles of its events in time order with ``" + "``
  (e.g. ``"Cricket + Dinner"``); a run of events that share one title keeps
  that title unchanged.
- **All-day events.** Opaque all-day events block their local calendar dates.
  ``TRANSP:TRANSPARENT`` and ``STATUS:CANCELLED`` events do not block time.
- **Recurrence.** Weekly/monthly rules are expanded with
  ``recurring-ical-events``; every occurrence is clipped and merged like a
  normal event.

A calendar file is the source of truth: :func:`add_event` never rewrites an
existing event. Re-adding the same ``uid`` is a no-op, which is what makes
``tn cal add`` safe to retry after a dropped message.
"""

from __future__ import annotations

import fcntl
import os
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import recurring_ical_events
from icalendar import Calendar, Event

__all__ = ["Block", "CalendarError", "TIME_ZONE", "add_event", "busy"]

TIME_ZONE = ZoneInfo("Asia/Kolkata")


def time_zone():
    return ZoneInfo(os.environ.get("TN_TIMEZONE", "Asia/Kolkata"))


MERGE_SEPARATOR = " + "


class CalendarError(ValueError):
    """A calendar file is missing or malformed, or an argument makes no sense."""


@dataclass(frozen=True, slots=True, order=True)
class Block:
    """A stretch of busy time, in Asia/Kolkata, with a calendar title.

    ``title`` may be empty when the event has no ``SUMMARY``; the gate decides
    separately whether a room is allowed to see titles. Naive times are read as
    India time, aware times are converted, so blocks are always comparable.
    """

    start: datetime
    end: datetime
    title: str = ""

    def __post_init__(self) -> None:
        start = _as_ist(self.start, "start")
        end = _as_ist(self.end, "end")
        if end <= start:
            raise CalendarError(f"a block must end after it starts ({start} .. {end})")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "title", str(self.title).strip())


def busy(path: str | Path, start: datetime, end: datetime) -> list[Block]:
    """Return the busy blocks in ``path`` between ``start`` and ``end``.

    Recurrences are expanded, each occurrence is clipped to the range, and
    overlapping or touching blocks are merged. The result is sorted by start.
    """
    path = Path(path)
    range_start = _as_ist(start, "start")
    range_end = _as_ist(end, "end")
    if range_end <= range_start:
        raise CalendarError(f"the range must end after it starts ({range_start} .. {range_end})")

    calendar = _load(path)
    try:
        occurrences = recurring_ical_events.of(calendar).between(range_start, range_end)
    except ValueError as exc:
        raise CalendarError(f"{path}: cannot expand recurrences: {exc}") from None

    blocks: list[Block] = []
    for event in occurrences:
        if _is_excluded(event):
            continue
        span = _span(event)
        if span is None:
            continue
        event_start, event_end = span
        if not isinstance(event_start, datetime):
            event_start = datetime.combine(event_start, datetime.min.time(), time_zone())
        if not isinstance(event_end, datetime):
            event_end = datetime.combine(event_end, datetime.min.time(), time_zone())
            if event_end <= event_start:
                event_end = event_start + timedelta(days=1)
        clipped_start = max(_as_ist(event_start, "start"), range_start)
        clipped_end = min(_as_ist(event_end, "end"), range_end)
        if clipped_end <= clipped_start:
            continue
        blocks.append(Block(clipped_start, clipped_end, _title(event)))

    return _merge(blocks)


def add_event(
    path: str | Path,
    start: datetime,
    duration: timedelta | int | float,
    title: str,
    place: str = "",
    uid: str | None = None,
) -> Block:
    """Append one event to ``path`` and return it as a :class:`Block`.

    ``duration`` is a :class:`~datetime.timedelta` or a number of minutes.
    ``uid`` identifies the event across writes; re-adding a ``uid`` that is
    already in the file leaves the file untouched and returns the stored block.
    A missing or blank ``uid`` gets a generated one, so pass one whenever the
    caller might retry. A missing or empty file becomes a new ``VCALENDAR``.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        start_ist = _as_ist(start, "start")
        length = _as_duration(duration)
        title = str(title).strip()
        place = str(place).strip()
        uid = str(uid).strip() if uid is not None else ""

        calendar = _load_or_new(path)
        if uid:
            existing = _find_event(calendar, uid)
            if existing is not None:
                stored = _block_from_event(existing)
                if stored is not None:
                    return stored
                raise CalendarError(f"{path}: event {uid!r} has no timed start or end")

        uid = uid or f"{uuid.uuid4().hex}@trust-network"
        event = Event()
        event.add("UID", uid)
        event.add("DTSTAMP", datetime.now(timezone.utc))
        event.add("DTSTART", start_ist)
        event.add("DTEND", start_ist + length)
        event.add("SUMMARY", title)
        if place:
            event.add("LOCATION", place)
        calendar.add_component(event)

        from trustnet.gate.storage import atomic_write

        atomic_write(path, calendar.to_ical())
        return Block(start_ist, start_ist + length, title)


def put_event(
    path: str | Path,
    start: datetime,
    duration: timedelta | int | float,
    title: str,
    place: str,
    uid: str,
    weekly: int | None = None,
) -> Block:
    """Create or replace the event ``uid`` in ``path`` with exactly these details.

    ``weekly`` repeats it that many times, one week apart.
    """
    path = Path(path)
    remove_event(path, uid)
    block = add_event(path, start, duration, title, place, uid=uid)
    if weekly:
        with path.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            calendar = _load(path)
            _find_event(calendar, uid).add("RRULE", {"FREQ": "WEEKLY", "COUNT": int(weekly)})
            from trustnet.gate.storage import atomic_write

            atomic_write(path, calendar.to_ical())
    return block


def remove_event(path: str | Path, uid: str) -> bool:
    """Remove the event ``uid`` from ``path``; ``False`` when it was not there."""
    path = Path(path)
    if not path.is_file():
        return False
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        calendar = _load_or_new(path)
        event = _find_event(calendar, uid)
        if event is None:
            return False
        calendar.subcomponents.remove(event)
        from trustnet.gate.storage import atomic_write

        atomic_write(path, calendar.to_ical())
        return True


def _as_ist(value: datetime, label: str) -> datetime:
    """Read a naive time as India time and convert an aware one to it."""
    if not isinstance(value, datetime):
        raise CalendarError(f"{label} must be a datetime, not {value!r}")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=time_zone())
    return value.astimezone(time_zone())


def _as_duration(value: timedelta | int | float) -> timedelta:
    """Turn a duration argument into a positive ``timedelta``; numbers are minutes."""
    if isinstance(value, bool):
        raise CalendarError(f"duration must be a timedelta or minutes, not {value!r}")
    if isinstance(value, timedelta):
        length = value
    elif isinstance(value, int | float):
        length = timedelta(minutes=value)
    else:
        raise CalendarError(f"duration must be a timedelta or minutes, not {value!r}")
    if length <= timedelta(0):
        raise CalendarError(f"duration must be positive, not {value!r}")
    return length


def _load(path: Path) -> Calendar:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise CalendarError(f"{path}: file not found") from None
    try:
        calendar = Calendar.from_ical(data)
    except ValueError as exc:
        raise CalendarError(f"{path}: invalid iCalendar: {exc}") from None
    if not isinstance(calendar, Calendar):
        raise CalendarError(f"{path}: not a VCALENDAR")
    return calendar


def _load_or_new(path: Path) -> Calendar:
    if path.is_file() and path.read_bytes().strip():
        return _load(path)
    calendar = Calendar()
    calendar.add("PRODID", "-//trust-network//calendar//EN")
    calendar.add("VERSION", "2.0")
    calendar.add("CALSCALE", "GREGORIAN")
    calendar.add("X-WR-TIMEZONE", TIME_ZONE.key)
    return calendar


def _find_event(calendar: Calendar, uid: str) -> Event | None:
    for event in calendar.walk("VEVENT"):
        if str(event.get("UID", "")).strip() == uid:
            return event
    return None


def _span(event: Event) -> tuple[date | datetime, date | datetime] | None:
    """Return an event's start and end, using ``DURATION`` when ``DTEND`` is absent."""
    start = event.decoded("DTSTART", None)
    if not isinstance(start, date | datetime):
        return None
    end = event.decoded("DTEND", None)
    if not isinstance(end, date | datetime):
        duration = event.decoded("DURATION", None)
        end = (
            start + duration
            if isinstance(duration, timedelta)
            else (start if isinstance(start, datetime) else start + timedelta(days=1))
        )
    return start, end


def _title(event: Event) -> str:
    return str(event.get("SUMMARY", "")).strip()


def _is_excluded(event: Event) -> bool:
    if str(event.get("STATUS", "")).upper() == "CANCELLED":
        return True
    return str(event.get("TRANSP", "")).upper() == "TRANSPARENT"


def _merge(blocks: list[Block]) -> list[Block]:
    merged: list[Block] = []
    for block in sorted(blocks):
        if merged and block.start <= merged[-1].end:
            previous = merged[-1]
            merged[-1] = Block(
                previous.start,
                max(previous.end, block.end),
                _merge_titles(previous.title, block.title),
            )
        else:
            merged.append(block)
    return merged


def _merge_titles(first: str, second: str) -> str:
    titles: list[str] = []
    for title in (first, second):
        for part in title.split(MERGE_SEPARATOR):
            part = part.strip()
            if part and part not in titles:
                titles.append(part)
    return MERGE_SEPARATOR.join(titles)


def _block_from_event(event: Event) -> Block | None:
    span = _span(event)
    if span is None:
        return None
    start, end = span
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        return None
    return Block(start, end, _title(event))
