"""``view-as``: exactly what one person's side can learn, field by field.

The owner types ``view-as rahul`` and sees the table their own gate would
answer Rahul's side with. This module is a view over the policy, not a second
policy: every ✅ comes from :func:`trustnet.gate.policy.visible_facts` and every
calendar row from :func:`trustnet.gate.policy.calendar_view`, so the two can
never disagree. It reads the owner's facts and calendar and returns a result
that renders as text; it calls no Switch and no network.

A person who is not on the owner's trust list gets the whole thing: nothing is
shared with them, so the result has no rows and says ``not on your list →
nothing``.

Gift claims (phase 19) are a hook here: pass the claims the owner must not see
yet and any claimed wishlist item is dropped from the rendered value until its
``reveal_after`` day. With the default empty claims set nothing is hidden.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Final

from trustnet.gate.calendar import TIME_ZONE, Block, busy
from trustnet.gate.facts import FactsError, Level, Profile, TrustList
from trustnet.gate.policy import calendar_view, visible_facts

__all__ = [
    "CalendarRow",
    "Claim",
    "DEFAULT_DAYS",
    "FactRow",
    "NOT_SHARED",
    "ViewAsError",
    "ViewAsResult",
    "format_value",
    "view_as",
]

#: The default calendar window ``view-as`` shows, in days from ``now``.
DEFAULT_DAYS: Final = 7

NOT_SHARED: Final = "not shared at this level"


class ViewAsError(ValueError):
    """An argument to ``view_as`` is malformed; the caller has a bug."""


@dataclass(frozen=True, slots=True)
class Claim:
    """A gift claim to hide from the owner's view until ``reveal_after``.

    Phase 19 stores claims in ``claims.json``. ``view_as`` only needs these two
    fields, so a phase-19 claim record with ``item`` and ``reveal_after`` works
    as-is.
    """

    item: str
    reveal_after: date

    def __post_init__(self) -> None:
        if not isinstance(self.item, str) or not self.item.strip():
            raise ViewAsError(f"a claim item must be a non-empty string, not {self.item!r}")
        object.__setattr__(self, "item", self.item.strip())
        if isinstance(self.reveal_after, datetime):
            revealed = self.reveal_after.date()
        elif isinstance(self.reveal_after, date):
            revealed = self.reveal_after
        else:
            raise ViewAsError(f"reveal_after must be a date, not {self.reveal_after!r}")
        object.__setattr__(self, "reveal_after", revealed)

    @property
    def key(self) -> str:
        return self.item.casefold()


@dataclass(frozen=True, slots=True)
class FactRow:
    """One fact in the table: shown value, or a cross at this level."""

    name: str
    visible: bool
    value: Any = None


@dataclass(frozen=True, slots=True)
class CalendarRow:
    """One busy block as the other side sees it (``title=""`` when hidden)."""

    start: datetime
    end: datetime
    title: str = ""


@dataclass(frozen=True, slots=True)
class ViewAsResult:
    """What one person's side can learn, plus everything they cannot.

    ``rows`` holds every fact the owner has, visible or not, so the owner sees
    the gaps too. ``level`` is ``None`` when the person is not on the list, and
    then there are no rows and no calendar at all.
    """

    person: str
    level: Level | None
    rows: tuple[FactRow, ...]
    calendar: tuple[CalendarRow, ...]
    titles_visible: bool
    window: tuple[datetime, datetime]
    days: int

    @property
    def visible_values(self) -> dict[str, Any]:
        """The ✅ rows as ``{name: value}``; equals ``policy.visible_facts``."""
        return {row.name: row.value for row in self.rows if row.visible}

    def render(self) -> str:
        """The table Om reads in ``#om-home`` / ``tn view-as``."""
        if self.level is None:
            return f"view-as {self.person} — not on your list → nothing"

        lines = [f"view-as {self.person} — {self.level.value}"]
        width = max((len(row.name) for row in self.rows), default=0)
        for row in self.rows:
            mark = "✅" if row.visible else "❌"
            text = format_value(row.value) if row.visible else NOT_SHARED
            lines.append(f"  {mark} {row.name:<{width}}  {text}")

        start, end = self.window
        titles = "with titles" if self.titles_visible else "busy blocks only, no titles"
        lines.append("")
        lines.append(f"Calendar · next {self.days} days ({_day(start)} – {_day(end)}) · {titles}")
        if not self.calendar:
            lines.append("  nothing busy")
        for row in self.calendar:
            label = row.title if row.title else "busy"
            lines.append(f"  {_weekday(row.start)}  {row.start:%H:%M}–{row.end:%H:%M}  {label}")
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.render()


def view_as(
    profile: Profile,
    trust: TrustList,
    person: str,
    *,
    now: datetime | None = None,
    days: int = DEFAULT_DAYS,
    claims: Iterable[Claim] = (),
) -> ViewAsResult:
    """Return what ``person``'s side can learn about ``profile``'s owner.

    ``person`` is looked up in ``trust`` (case-insensitive, like every other
    name). Someone not on the list, or an id the list cannot hold, is a
    stranger: the result shares nothing. ``now`` and ``days`` pick the calendar
    window, and the policy decides whether titles appear in it. ``claims`` are
    gift claims hidden from the owner until ``reveal_after``.
    """
    if not isinstance(profile, Profile):
        raise ViewAsError(f"profile must be a Profile, not {profile!r}")
    if not isinstance(trust, TrustList):
        raise ViewAsError(f"trust must be a TrustList, not {trust!r}")
    name = _person_name(person)
    if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
        raise ViewAsError(f"days must be a positive integer, not {days!r}")
    moment = _as_ist(now, "now")
    window = (moment, moment + timedelta(days=days))

    try:
        level = trust.level_for(name)
    except FactsError:
        level = None
    if level is None:
        return ViewAsResult(
            person=name,
            level=None,
            rows=(),
            calendar=(),
            titles_visible=False,
            window=window,
            days=days,
        )

    allowed = visible_facts(profile, level)
    hidden = _hidden_items(claims, moment)
    rows: list[FactRow] = []
    for fact_name in profile.facts:
        if fact_name in allowed:
            rows.append(FactRow(fact_name, True, _hide_claimed(allowed[fact_name], hidden)))
        else:
            rows.append(FactRow(fact_name, False))

    blocks = busy(profile.calendar_path, window[0], window[1])
    shown = calendar_view(blocks, level)
    return ViewAsResult(
        person=name,
        level=level,
        rows=tuple(rows),
        calendar=tuple(CalendarRow(block.start, block.end, block.title) for block in shown),
        titles_visible=_titles_visible(level, moment),
        window=window,
        days=days,
    )


def _titles_visible(level: Level, moment: datetime) -> bool:
    """Ask the policy, rather than repeat its rule, whether titles survive."""
    probe = Block(moment, moment + timedelta(minutes=1), "probe")
    return list(calendar_view([probe], level)) == [probe]


def _hidden_items(claims: Iterable[Claim], now: datetime) -> frozenset[str]:
    hidden: set[str] = set()
    for claim in claims:
        try:
            item, reveal_after = claim.item, claim.reveal_after
        except AttributeError:
            raise ViewAsError(f"a claim needs .item and .reveal_after, not {claim!r}") from None
        if isinstance(reveal_after, datetime):
            reveal_after = reveal_after.date()
        if not isinstance(reveal_after, date):
            raise ViewAsError(f"a claim's reveal_after must be a date, not {reveal_after!r}")
        if now.date() < reveal_after:
            hidden.add(str(item).strip().casefold())
    return frozenset(hidden)


def _hide_claimed(value: Any, hidden: frozenset[str]) -> Any:
    """Drop claimed wishlist entries from a visible value, keeping the rest."""
    if not hidden or not isinstance(value, list | tuple):
        return value
    kept: list[Any] = []
    for item in value:
        if isinstance(item, Mapping) and "item" in item:
            if str(item["item"]).strip().casefold() in hidden:
                continue
        kept.append(item)
    return kept


def format_value(value: Any) -> str:
    """Render one fact value as the short line people read.

    ``ask``, ask-around replies and ``view-as`` all use this, so a value never
    reads as a Python list in one place and prose in another.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, list | tuple):
        return ", ".join(format_value(item) for item in value)
    if isinstance(value, Mapping):
        if "item" in value:
            item = str(value["item"])
            price = value.get("price")
            if isinstance(price, int | float) and not isinstance(price, bool):
                return f"{item} (≈₹{price:,})"
            return item
        return ", ".join(f"{key}: {format_value(item)}" for key, item in value.items())
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _weekday(value: datetime) -> str:
    return f"{value:%a %b} {value.day}"


def _day(value: datetime) -> str:
    return f"{value:%b} {value.day}"


def _person_name(person: str) -> str:
    if not isinstance(person, str) or not person.strip():
        raise ViewAsError(f"a person must be a non-empty string, not {person!r}")
    return person.strip().lower()


def _as_ist(value: datetime | None, label: str) -> datetime:
    if value is None:
        return datetime.now(TIME_ZONE)
    if not isinstance(value, datetime):
        raise ViewAsError(f"{label} must be a datetime, not {value!r}")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=TIME_ZONE)
    return value.astimezone(TIME_ZONE)
