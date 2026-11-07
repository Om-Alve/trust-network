"""Policy-filtered share cards and disclosure recording for planning rooms.

Callers must verify the room contains only the owner and the trusted friend.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Final

from jinja2 import DictLoader, Environment, StrictUndefined, TemplateError

from trustnet import resources
from trustnet.gate import ledger
from trustnet.gate.calendar import Block, CalendarError, busy, time_zone
from trustnet.gate.commands import Quoted
from trustnet.gate.facts import FactsError, Level, Profile, TrustList
from trustnet.gate.policy import calendar_view, visible_facts
from trustnet.gate.view_as import format_value

__all__ = ["Brief", "BriefError", "build_brief", "write_brief"]

#: Command examples are parsed by the behavioral checks.
ASK_OWNER_EXAMPLE: Final = '@{gate} ask-owner Q1 "Is ₹1,500 per person okay?"'
PROPOSE_EXAMPLE: Final = (
    '@{gate} propose P1 2026-11-08T21:00 2h "Dinner and a walk" @ "The Park, MG Road"'
)
_ENVIRONMENT: Final = Environment(
    loader=DictLoader(
        {resources.SHARE_CARD_TEMPLATE: resources.read_text(resources.SHARE_CARD_TEMPLATE)}
    ),
    undefined=StrictUndefined,
    autoescape=False,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


class BriefError(ValueError):
    """A brief argument is malformed, or the brief cannot be built."""


@dataclass(frozen=True, slots=True)
class Brief:
    """A rendered brief and the disclosures writing it made.

    ``disclosed_facts`` is the mapping the brief was built from (normally
    ``policy.visible_facts``), so a caller can assert or display it.
    ``entries`` are the ledger entries written by :func:`write_brief`.
    """

    text: str
    level: Level
    disclosed_facts: dict[str, Any]
    entries: tuple[ledger.Entry, ...]


def build_brief(
    profile: Profile,
    trust: TrustList,
    friend: str,
    room: str,
    goal: Quoted | str,
    date_range: tuple[date, date],
) -> tuple[str, dict[str, Any]]:
    """Render the brief for ``profile``'s owner talking to ``friend``.

    ``date_range`` is two inclusive India dates; each is read at 00:00 and the
    window ends at the start of the day after the second date. The goal is free
    text, so it is wrapped in :class:`Quoted` and appears only quoted. The
    returned mapping is exactly the set of facts the brief states, which equals
    what ``ask`` answers at this level.

    This function has no side effects and writes no ledger entry; call
    :func:`write_brief` to both render and record a brief.
    """
    text, facts, _level, _blocks = _compose(profile, trust, friend, room, goal, date_range)
    return text, facts


def write_brief(
    profile: Profile,
    trust: TrustList,
    friend: str,
    room: str,
    goal: Quoted | str,
    date_range: tuple[date, date],
    *,
    now: datetime | None = None,
) -> Brief:
    """Render a brief and record everything it disclosed (Rule 6).

    Every fact gets one ``brief`` ledger entry through
    :func:`trustnet.gate.ledger.record_brief`; the busy blocks get one
    ``calendar`` entry, already filtered by the policy, so a title the level
    hides never reaches the ledger either. ``now`` pins the timestamp for tests
    and demos.
    """
    text, facts, level, blocks = _compose(profile, trust, friend, room, goal, date_range)
    entries = ledger.record_brief(
        facts, friend.strip().lower(), room, person=profile.owner, now=now
    )
    calendar_entry = ledger.record(
        "calendar",
        [
            {"start": block.start.isoformat(), "end": block.end.isoformat(), "title": block.title}
            for block in blocks
        ],
        friend.strip().lower(),
        room,
        "brief",
        person=profile.owner,
        now=now,
    )
    return Brief(
        text=text,
        level=level,
        disclosed_facts=facts,
        entries=(*entries, calendar_entry),
    )


def _compose(
    profile: Profile,
    trust: TrustList,
    friend: str,
    room: str,
    goal: Quoted | str,
    date_range: tuple[date, date],
) -> tuple[str, dict[str, Any], Level, list[Block]]:
    """Validate the arguments, ask the policy, and render the template."""
    if not isinstance(profile, Profile):
        raise BriefError(f"profile must be a Profile, not {profile!r}")
    if not isinstance(trust, TrustList):
        raise BriefError(f"trust must be a TrustList, not {trust!r}")
    if not isinstance(profile.owner, str) or not profile.owner.strip():
        raise BriefError("the profile needs an owner name")
    if not isinstance(room, str) or not room.strip():
        raise BriefError(f"room must be a non-empty string, not {room!r}")

    friend_key = _friend_key(friend)
    try:
        level = trust.level_for(friend_key)
    except FactsError:
        level = None
    if level is None:
        raise BriefError(f"{friend_key!r} is not on {profile.owner}'s trust list")
    if not level.is_viewer:
        raise BriefError(f"a room cannot sit at {level.value!r}")

    quoted_goal = _as_quoted(goal)
    start_day, end_day = _date_range(date_range)
    start = datetime.combine(start_day, time.min, tzinfo=time_zone())
    end = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=time_zone())

    facts = visible_facts(profile, level)
    try:
        blocks = calendar_view(busy(profile.calendar_path, start, end), level)
    except CalendarError as exc:
        raise BriefError(str(exc)) from None

    owner_gate = f"{profile.owner}-gate"
    context = {
        "owner": _display(profile.owner),
        "friend": _display(friend_key),
        "owner_gate": owner_gate,
        "goal": quoted_goal,
        "facts": [(name, format_value(value)) for name, value in facts.items()],
        "blocks": [_block_row(block) for block in blocks],
        "date_start": _day_label(start_day),
        "date_end": _day_label(end_day),
        "ask_owner": ASK_OWNER_EXAMPLE.format(gate=owner_gate),
        "propose_own": PROPOSE_EXAMPLE.format(gate=owner_gate),
    }
    try:
        text = _ENVIRONMENT.get_template(resources.SHARE_CARD_TEMPLATE).render(**context)
    except TemplateError as exc:
        raise BriefError(f"{resources.SHARE_CARD_TEMPLATE}: {exc}") from None
    return text, facts, level, blocks


def _friend_key(friend: str) -> str:
    if not isinstance(friend, str) or not friend.strip():
        raise BriefError(f"a friend must be a non-empty name, not {friend!r}")
    return friend.strip().lower()


def _as_quoted(goal: Quoted | str) -> Quoted:
    if isinstance(goal, Quoted):
        return goal
    if not isinstance(goal, str):
        raise BriefError(f"the goal must be text or a Quoted, not {goal!r}")
    try:
        return Quoted(goal)
    except ValueError as exc:
        raise BriefError(f"the goal cannot be shown as quoted data: {exc}") from None


def _date_range(date_range: tuple[date, date]) -> tuple[date, date]:
    if not isinstance(date_range, tuple | list) or len(date_range) != 2:
        raise BriefError(f"date_range must be two dates, not {date_range!r}")
    start, end = (_as_day(value) for value in date_range)
    if end < start:
        raise BriefError(f"the date range must end on or after its start ({start} .. {end})")
    return start, end


def _as_day(value: date) -> date:
    if isinstance(value, datetime):
        return value.astimezone(time_zone()).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    raise BriefError(f"a date range needs dates, not {value!r}")


def _display(name: str) -> str:
    return name[:1].upper() + name[1:]


def _day_label(day: date) -> str:
    return f"{day:%a %b} {day.day}"


def _block_row(block: Block) -> dict[str, str]:
    """One calendar row; the title is empty when the policy stripped it."""
    return {
        "day": _day_label(block.start),
        "start": f"{block.start:%H:%M}",
        "end": f"{block.end:%H:%M}",
        "title": block.title,
    }
