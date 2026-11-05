"""Typed commands and a forgiving parser for the trust-network gates.

Everything that crosses a gate boundary is a fixed form (:data:`PLAN.md` §3
Rule 4): the parser turns message text into one of the dataclasses in this
module, validates the parts that the rule pins down, and wraps every free-text
question or goal in :class:`Quoted` so a handler can never mistake text for an
instruction.

The grammar (``<gate>`` is the leading ``@om-gate``, optional in this module):

Cross-boundary commands
    free <date|range>
        ``@om-gate free 2026-11-08..2026-11-09``
    ask <fact> [<fact> ...]
        ``@om-gate ask diet interests``
    ask-owner Q<n> "<question>"
        ``@om-gate ask-owner Q3 "Is ₹1,500 per person okay?"``
    propose P<n> <start> <duration> "<title>" @ "<place>"
        ``@om-gate propose P1 2026-11-08T21:00 2h "Bowling + dinner" @ "Smaaash, Indiranagar"``
    counter P<n> P<n> <start> <duration> "<title>" @ "<place>"
        ``@om-gate counter P1 P2 2026-11-09T19:00 2h "Bowling + dinner" @ "Smaaash, Indiranagar"``
    gift-ideas <occasion> <date> [budget <amount> | ₹<amount>]
        ``@om-gate gift-ideas birthday 2026-11-20 budget<=3000``
    claim "<item>"
        ``@om-gate claim "Catan Seafarers"``
    ask-around "<question>"
        ``@om-gate ask-around "tent to borrow, Nov 14-16"``

Owner-only commands
    dm <person> "<goal>"
        ``@om-gate dm rahul "something fun Sunday evening, not pricey"``
    yes P<n> | no P<n>
        ``@om-gate yes P1``
    answer <Q<n>|P<n>> "<text>"
        ``@om-gate answer Q3 "yes, up to ₹1,500"``
    trust <person> <level>
        ``@om-gate trust priya close``
    view-as <person>
        ``@om-gate view-as rahul``
    ledger
        ``@om-gate ledger``

Gate-to-gate commands (not in the plan; needed by phase 14)
    join-dm <room> "<goal>"
        ``@rahul-gate join-dm dm-om-rahul-sun "something fun Sunday evening"``
    consent P<n> yes|no via-agent|direct
        ``@rahul-gate consent P1 yes via-agent``

Dates go through :mod:`dateparser` with ``Asia/Kolkata`` and
``PREFER_DATES_FROM: future``. Time is injectable through ``parse(..., now=)``
so tests do not depend on the day they run; the demo's outing day,
2026-11-08, is a Sunday.

Malformed commands raise :class:`ParseError` carrying a correct example, which
the gate posts back. Unrecognised text becomes :class:`Unknown` so the gate can
answer with the command list (and phase 21 can add an overreach note).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Final, Literal, TypeAlias
from zoneinfo import ZoneInfo

import dateparser

from trustnet.gate.facts import Level

__all__ = [
    "EXAMPLES",
    "Ask",
    "AskAround",
    "AskOwner",
    "Answer",
    "Claim",
    "Command",
    "Consent",
    "Counter",
    "Dm",
    "Free",
    "GiftIdeas",
    "JoinDm",
    "Ledger",
    "No",
    "ParseError",
    "Propose",
    "Quoted",
    "Trust",
    "Unknown",
    "ViewAs",
    "Yes",
    "parse",
]

IST: Final[ZoneInfo] = ZoneInfo("Asia/Kolkata")
MAX_TITLE: Final = 60
MAX_PLACE: Final = 60
MAX_QUESTION: Final = 140
MAX_CLAIM: Final = 80
MAX_DURATION: Final = timedelta(hours=24)

ConsentVia: TypeAlias = Literal["direct", "via-agent"]

_PERSON_RE: Final = re.compile(r"[a-z0-9][a-z0-9_-]*")
_FACT_RE: Final = re.compile(r"[a-z][a-z0-9_-]*")
_ROOM_RE: Final = re.compile(r"[a-z0-9][a-z0-9_-]*")
_PROPOSAL_ID_RE: Final = re.compile(r"P\d+", re.IGNORECASE)
_REFERENCE_RE: Final = re.compile(r"[QP]\d+", re.IGNORECASE)
_PLACE_RE: Final = re.compile(r"[A-Za-z0-9 ,.'&-]+")
_TITLE_FORBIDDEN: Final = frozenset('\n\r"@')
_DURATION_RE: Final = re.compile(
    r"^(?:(?P<hours>\d+)\s*(?:hours?|hrs?|h))?(?:\s*(?P<minutes>\d+)\s*(?:minutes?|mins?|m))?$",
    re.IGNORECASE,
)

#: One correct example per command; every :class:`ParseError` carries one.
EXAMPLES: Final[dict[str, str]] = {
    "free": "@om-gate free 2026-11-08..2026-11-09",
    "ask": "@om-gate ask diet interests",
    "ask-owner": '@om-gate ask-owner Q3 "Is ₹1,500 per person okay?"',
    "propose": '@om-gate propose P1 2026-11-08T21:00 2h "Bowling + dinner" @ "Smaaash, Indiranagar"',
    "counter": (
        '@om-gate counter P1 P2 2026-11-09T19:00 2h "Bowling + dinner" @ "Smaaash, Indiranagar"'
    ),
    "gift-ideas": "@om-gate gift-ideas birthday 2026-11-20 budget<=3000",
    "claim": '@om-gate claim "Catan Seafarers"',
    "ask-around": '@om-gate ask-around "tent to borrow, Nov 14-16"',
    "dm": '@om-gate dm rahul "something fun Sunday evening, not pricey"',
    "yes": "@om-gate yes P1",
    "no": "@om-gate no P1",
    "answer": '@om-gate answer Q3 "yes, up to ₹1,500"',
    "trust": "@om-gate trust priya close",
    "view-as": "@om-gate view-as rahul",
    "ledger": "@om-gate ledger",
    "join-dm": '@rahul-gate join-dm dm-om-rahul-sun "something fun Sunday evening"',
    "consent": "@rahul-gate consent P1 yes via-agent",
}


class ParseError(ValueError):
    """A known command was written badly; ``example`` shows the fixed form."""

    def __init__(self, message: str, *, example: str, raw: str = "") -> None:
        self.message = message
        self.example = example
        self.raw = raw
        super().__init__(f"{message} — try: {example}")


@dataclass(frozen=True, slots=True)
class Quoted:
    """Free text coming from a boundary command, only ever rendered quoted.

    The wrapper is the boundary: handlers receive ``Quoted`` instead of ``str``,
    and ``str(question)`` produces the quoted rendering. Text is capped at 140
    characters (Rule 4) and may not contain a double quote, so the rendering is
    unambiguous.
    """

    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise ValueError("quoted text must be a string")
        text = self.text.strip()
        if not text:
            raise ValueError("quoted text must not be empty")
        if len(text) > MAX_QUESTION:
            raise ValueError(f"quoted text must be {MAX_QUESTION} characters or fewer")
        if "\n" in text or "\r" in text:
            raise ValueError("quoted text must be one line")
        if '"' in text:
            raise ValueError("quoted text cannot contain a double quote")
        object.__setattr__(self, "text", text)

    def __str__(self) -> str:
        return f'"{self.text}"'

    def render(self) -> str:
        """Return the quoted rendering (same as ``str(self)``)."""
        return str(self)


@dataclass(frozen=True, slots=True)
class _Addressed:
    """The ``@gate-name`` a command was sent to, if the text named one."""

    target: str | None = field(default=None, kw_only=True)


@dataclass(frozen=True, slots=True)
class Free(_Addressed):
    """``free <date..date>``: busy blocks for a day or an inclusive range."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("a free range must end on or after its start")


@dataclass(frozen=True, slots=True)
class Ask(_Addressed):
    """``ask <fact> ...``: values at the room's level, or "not shared"."""

    facts: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.facts:
            raise ValueError("ask needs at least one fact")
        for fact in self.facts:
            if not isinstance(fact, str) or not _FACT_RE.fullmatch(fact):
                raise ValueError(f"invalid fact name {fact!r}")


@dataclass(frozen=True, slots=True)
class AskOwner(_Addressed):
    """``ask-owner Q<n> "<question>"``: relay a question to the gate's owner."""

    question_id: str
    question: Quoted

    def __post_init__(self) -> None:
        object.__setattr__(self, "question_id", _question_id(self.question_id))


@dataclass(frozen=True, slots=True)
class Propose(_Addressed):
    """``propose P<n> <start> <duration> "<title>" @ "<place>"``."""

    proposal_id: str
    start: datetime
    duration: timedelta
    title: str
    place: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposal_id", _proposal_id(self.proposal_id))
        object.__setattr__(self, "title", _title(self.title))
        object.__setattr__(self, "place", _place(self.place))
        _duration(self.duration)
        if self.start.tzinfo is None:
            raise ValueError("a proposal start needs a timezone")


@dataclass(frozen=True, slots=True)
class Counter(_Addressed):
    """``counter P<old> P<new> ...``: a fresh proposal that replaces ``of``."""

    of: str
    proposal_id: str
    start: datetime
    duration: timedelta
    title: str
    place: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "of", _proposal_id(self.of))
        object.__setattr__(self, "proposal_id", _proposal_id(self.proposal_id))
        object.__setattr__(self, "title", _title(self.title))
        object.__setattr__(self, "place", _place(self.place))
        _duration(self.duration)
        if self.start.tzinfo is None:
            raise ValueError("a counter start needs a timezone")


@dataclass(frozen=True, slots=True)
class GiftIdeas(_Addressed):
    """``gift-ideas <occasion> <date> [budget ...]``: facts only, never a relay."""

    occasion: str
    on: date
    budget: int | None = None

    def __post_init__(self) -> None:
        occasion = self.occasion.strip().lower()
        if not occasion or len(occasion) > 40:
            raise ValueError("a gift occasion must be 1 to 40 characters")
        object.__setattr__(self, "occasion", occasion)
        if self.budget is not None and self.budget <= 0:
            raise ValueError("a gift budget must be a positive number")


@dataclass(frozen=True, slots=True)
class Claim(_Addressed):
    """``claim "<item>"``: mark a wishlist item taken, sealed from its owner."""

    item: str

    def __post_init__(self) -> None:
        item = self.item.strip()
        if not item:
            raise ValueError("a claim needs an item")
        if len(item) > MAX_CLAIM:
            raise ValueError(f"a claimed item must be {MAX_CLAIM} characters or fewer")
        if '"' in item or "\n" in item or "\r" in item:
            raise ValueError("a claimed item must be one plain line")
        object.__setattr__(self, "item", item)


@dataclass(frozen=True, slots=True)
class AskAround(_Addressed):
    """``ask-around "<question>"``: inbound from a friend's gate, or owner-sent."""

    question: Quoted


@dataclass(frozen=True, slots=True)
class Dm(_Addressed):
    """``dm <person> "<goal>"``: the owner starts a conversation."""

    person: str
    goal: Quoted

    def __post_init__(self) -> None:
        object.__setattr__(self, "person", _person(self.person))


@dataclass(frozen=True, slots=True)
class Yes(_Addressed):
    """``yes P<n>``: the owner agrees to a proposal."""

    proposal_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposal_id", _proposal_id(self.proposal_id))


@dataclass(frozen=True, slots=True)
class No(_Addressed):
    """``no P<n>``: the owner declines a proposal."""

    proposal_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposal_id", _proposal_id(self.proposal_id))


@dataclass(frozen=True, slots=True)
class Answer(_Addressed):
    """``answer Q<n> "<text>"`` (or ``answer P<n> yes|no`` for a proposal)."""

    reference: str
    text: Quoted

    def __post_init__(self) -> None:
        object.__setattr__(self, "reference", _reference(self.reference))


@dataclass(frozen=True, slots=True)
class Trust(_Addressed):
    """``trust <person> <level>``: owner-only, viewer levels only."""

    person: str
    level: Level

    def __post_init__(self) -> None:
        object.__setattr__(self, "person", _person(self.person))
        if not isinstance(self.level, Level) or not self.level.is_viewer:
            raise ValueError("a trust level must be acquaintance, friend or close")


@dataclass(frozen=True, slots=True)
class ViewAs(_Addressed):
    """``view-as <person>``: what that person's side can learn, field by field."""

    person: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "person", _person(self.person))


@dataclass(frozen=True, slots=True)
class Ledger(_Addressed):
    """``ledger``: what the owner has shared, with whom and when."""


@dataclass(frozen=True, slots=True)
class JoinDm(_Addressed):
    """``join-dm <room> "<goal>"``: gate-to-gate invitation to a DM room."""

    room: str
    goal: Quoted

    def __post_init__(self) -> None:
        object.__setattr__(self, "room", _room(self.room))


@dataclass(frozen=True, slots=True)
class Consent(_Addressed):
    """``consent P<n> yes|no via-agent|direct``: one side's recorded answer."""

    proposal_id: str
    agreed: bool
    via: ConsentVia = "direct"

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposal_id", _proposal_id(self.proposal_id))
        if self.via not in ("direct", "via-agent"):
            raise ValueError("consent must be via 'direct' or 'via-agent'")


@dataclass(frozen=True, slots=True)
class Unknown(_Addressed):
    """Text that is not a command; the gate replies with the command list."""

    raw: str


Command: TypeAlias = (
    Free
    | Ask
    | AskOwner
    | Propose
    | Counter
    | GiftIdeas
    | Claim
    | AskAround
    | Dm
    | Yes
    | No
    | Answer
    | Trust
    | ViewAs
    | Ledger
    | JoinDm
    | Consent
    | Unknown
)


def parse(text: str, *, now: datetime | None = None) -> Command:
    """Parse one message into a typed command.

    ``now`` pins the clock for relative dates (``Sat 9pm``, ``tomorrow``);
    tests pass a fixed value. Without it the current ``Asia/Kolkata`` time is
    used.
    """
    raw = text if isinstance(text, str) else str(text)
    body = _normalize(raw)
    target, body = _split_target(body)
    if not body:
        return Unknown(raw=raw.strip(), target=target)
    verb, _, args = body.partition(" ")
    command = verb.lower().rstrip(_VERB_TRAILING)
    handler = _HANDLERS.get(command)
    if handler is None:
        return Unknown(raw=raw.strip(), target=target)
    return handler(
        _trim_args(command, args.strip()),
        target=target,
        now=_clock(now),
        raw=raw,
    )


# --- parsing helpers ---------------------------------------------------------


def _clock(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(IST)
    if now.tzinfo is None:
        return now.replace(tzinfo=IST)
    return now.astimezone(IST)


def _err(command: str, message: str, raw: str) -> ParseError:
    return ParseError(message, example=EXAMPLES[command], raw=raw)


def _proposal_id(value: str) -> str:
    value = value.strip().upper()
    if not _PROPOSAL_ID_RE.fullmatch(value):
        raise ValueError(f"invalid proposal ID {value!r} (expected P followed by digits)")
    return value


def _question_id(value: str) -> str:
    value = value.strip().upper()
    if not re.fullmatch(r"Q\d+", value):
        raise ValueError(f"invalid question ID {value!r} (expected Q followed by digits)")
    return value


def _reference(value: str) -> str:
    value = value.strip().upper()
    if not _REFERENCE_RE.fullmatch(value):
        raise ValueError(f"invalid reference {value!r} (expected Q<n> or P<n>)")
    return value


def _person(value: str) -> str:
    value = value.strip().lower()
    if not _PERSON_RE.fullmatch(value):
        raise ValueError(f"invalid person name {value!r}")
    return value


def _room(value: str) -> str:
    value = value.strip().lower()
    if not _ROOM_RE.fullmatch(value):
        raise ValueError(f"invalid room name {value!r}")
    return value


def _title(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("a proposal needs a title")
    if len(value) > MAX_TITLE:
        raise ValueError(f"a title must be {MAX_TITLE} characters or fewer")
    if any(ch in _TITLE_FORBIDDEN for ch in value):
        raise ValueError("a title cannot contain quotes, @ or line breaks")
    return value


def _place(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("a proposal needs a place")
    if len(value) > MAX_PLACE:
        raise ValueError(f"a place must be {MAX_PLACE} characters or fewer")
    if not _PLACE_RE.fullmatch(value):
        raise ValueError("a place may only contain letters, digits, spaces and , . ' & -")
    return value


def _duration(value: timedelta) -> timedelta:
    if value < timedelta(minutes=1) or value > MAX_DURATION:
        raise ValueError("a duration must be between 1 minute and 24 hours")
    return value


def _parse_duration_text(text: str, *, command: str, raw: str) -> timedelta:
    match = _DURATION_RE.fullmatch(text.strip())
    if not match or (not match["hours"] and not match["minutes"]):
        raise _err(command, f"could not read the duration {text!r} (try 2h or 90m)", raw)
    total = timedelta(
        hours=int(match["hours"] or 0),
        minutes=int(match["minutes"] or 0),
    )
    if total < timedelta(minutes=1) or total > MAX_DURATION:
        raise _err(command, "a duration must be between 1 minute and 24 hours", raw)
    return total


def _unquote(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"' and '"' not in text[1:-1]:
        return text[1:-1]
    return text


def _quoted(text: str, *, command: str, raw: str) -> Quoted:
    value = _unquote(text)
    try:
        return Quoted(value)
    except ValueError as exc:
        raise _err(command, str(exc), raw) from None


# --- normalisation -----------------------------------------------------------


_FENCE_RE: Final = re.compile(r"^```[A-Za-z0-9_-]*\s*(?P<body>.*?)\s*```$", re.DOTALL)
_TARGET_RE: Final = re.compile(r"^@(?P<target>[A-Za-z0-9][A-Za-z0-9_-]*)(?:\s+|$)")
_TRAILING: Final = ".,;:!"
_VERB_TRAILING: Final = ".,;:!?"
_FREE_TEXT: Final = frozenset({"ask-owner", "ask-around", "answer", "dm", "join-dm"})
_SMART: Final = str.maketrans(
    {
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u2032": "'",
        "\u00a0": " ",
        "\u2009": " ",
        "\u202f": " ",
    }
)


def _normalize(text: str) -> str:
    body = text.strip()
    fence = _FENCE_RE.match(body)
    if fence:
        body = fence.group("body")
    body = body.translate(_SMART)
    body = " ".join(body.split())
    while body and body[-1] in _TRAILING:
        body = body[:-1].rstrip()
    return body


def _split_target(body: str) -> tuple[str | None, str]:
    match = _TARGET_RE.match(body)
    if not match:
        return None, body
    return match.group("target").lower(), body[match.end() :].strip()


def _trim_args(command: str, args: str) -> str:
    """Drop a sentence-ending ``?`` unless it belongs to unquoted free text."""
    if not args.endswith("?"):
        return args
    quoted = args[:-1].rstrip().endswith('"')
    if command in _FREE_TEXT and not quoted:
        return args
    return args[:-1].rstrip()


# --- dates -------------------------------------------------------------------


_RANGE_SEP: Final = re.compile(r"\s*(?:\.\.|\bto\b|–|—)\s*", re.IGNORECASE)
_MONTH_DAY_RANGE: Final = re.compile(
    r"^(?P<month>[A-Za-z]{3,9})\.?\s+(?P<left>\d{1,2})\s*[-–—]\s*(?P<right>\d{1,2})"
    r"(?:,?\s*(?P<year>\d{4}))?$"
)
_DAY_MONTH_RANGE: Final = re.compile(
    r"^(?P<left>\d{1,2})\s*[-–—]\s*(?P<right>\d{1,2})\s+(?P<month>[A-Za-z]{3,9})\.?"
    r"(?:,?\s*(?P<year>\d{4}))?$"
)
_BARE_DAY: Final = re.compile(r"\d{1,2}")


def _dateparser(text: str, *, now: datetime) -> datetime | None:
    settings = {
        "TIMEZONE": "Asia/Kolkata",
        "RETURN_AS_TIMEZONE_AWARE": True,
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": now,
    }
    try:
        return dateparser.parse(text, settings=settings)
    except (OverflowError, TypeError, ValueError):
        return None


def _sane_year(value: date, *, now: datetime) -> bool:
    return now.year - 1 <= value.year <= now.year + 2


def _parse_day(text: str, *, now: datetime, raw: str, command: str) -> date:
    parsed = _dateparser(text, now=now)
    if parsed is None:
        raise _err(
            command,
            f"could not read the date {text!r} (try 2026-11-08 or Sun 9pm)",
            raw,
        )
    value = parsed.astimezone(IST).date() if parsed.tzinfo else parsed.date()
    if not _sane_year(value, now=now):
        raise _err(command, f"could not read the date {text!r}", raw)
    return value


def _parse_moment(text: str, *, now: datetime, raw: str, command: str) -> datetime:
    parsed = _dateparser(text, now=now)
    if parsed is None:
        raise _err(
            command,
            f"could not read the date and time {text!r} (try 2026-11-08T21:00 or Sun 9pm)",
            raw,
        )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    parsed = parsed.astimezone(IST)
    if not _sane_year(parsed.date(), now=now):
        raise _err(command, f"could not read the date and time {text!r}", raw)
    return parsed


def _range_parts(text: str) -> tuple[str, str] | None:
    pieces = _RANGE_SEP.split(text, maxsplit=1)
    if len(pieces) == 2 and pieces[0].strip() and pieces[1].strip():
        return pieces[0].strip(), pieces[1].strip()
    match = _MONTH_DAY_RANGE.fullmatch(text.strip())
    if match:
        left = f"{match['month']} {match['left']}"
        if match["year"]:
            left = f"{left} {match['year']}"
        return left, match["right"]
    match = _DAY_MONTH_RANGE.fullmatch(text.strip())
    if match:
        left = f"{match['left']} {match['month']}"
        if match["year"]:
            left = f"{left} {match['year']}"
        return left, match["right"]
    return None


def _date_range(text: str, *, now: datetime, raw: str, command: str) -> tuple[date, date]:
    parts = _range_parts(text)
    if parts is None:
        day = _parse_day(text, now=now, raw=raw, command=command)
        return day, day
    left, right = parts
    start = _parse_day(left, now=now, raw=raw, command=command)
    if _BARE_DAY.fullmatch(right):
        try:
            end = start.replace(day=int(right))
        except ValueError:
            raise _err(command, f"could not read the date range {text!r}", raw) from None
    else:
        end = _parse_day(right, now=now, raw=raw, command=command)
    if end < start:
        try:
            end = end.replace(year=end.year + 1)
        except ValueError:
            raise _err(command, f"could not read the date range {text!r}", raw) from None
    return start, end


# --- command handlers --------------------------------------------------------


def _handle_free(args: str, *, target: str | None, now: datetime, raw: str) -> Command:
    if not args:
        raise _err("free", "free needs a date or a range", raw)
    start, end = _date_range(args, now=now, raw=raw, command="free")
    return Free(start=start, end=end, target=target)


def _handle_ask(args: str, *, target: str | None, now: datetime, raw: str) -> Command:
    fields = tuple(part.lower() for part in re.split(r"[,\s]+", args) if part)
    if not fields:
        raise _err("ask", "ask needs at least one fact name", raw)
    for fact in fields:
        if not _FACT_RE.fullmatch(fact):
            raise _err(
                "ask",
                f"invalid fact name {fact!r} (use names like diet or interests)",
                raw,
            )
    return Ask(facts=fields, target=target)


def _handle_ask_owner(args: str, *, target: str | None, now: datetime, raw: str) -> Command:
    match = re.fullmatch(r"(?P<id>Q\d+)\s+(?P<question>.+)", args, re.IGNORECASE)
    if not match:
        raise _err(
            "ask-owner",
            "ask-owner needs a question ID and a quoted question",
            raw,
        )
    return AskOwner(
        question_id=match["id"],
        question=_quoted(match["question"], command="ask-owner", raw=raw),
        target=target,
    )


_PROPOSAL_RE: Final = re.compile(
    r"""^(?P<ids>(?:P\d+\s+)+)
        (?P<start>.+?)\s+
        (?P<duration>(?:\d+\s*(?:hours?|hrs?|h))?(?:\s*\d+\s*(?:minutes?|mins?|m))?)
        \s+(?P<title>"[^"]*"|\S+)\s+@\s*(?P<place>"[^"]*"|.+?)\s*$""",
    re.IGNORECASE | re.VERBOSE,
)


def _plan_parts(
    command: str, args: str, *, raw: str, now: datetime
) -> tuple[list[str], datetime, timedelta, str, str]:
    match = _PROPOSAL_RE.fullmatch(args)
    if not match:
        raise _err(
            command,
            f"{command} needs IDs, a start, a duration, a title and @ a place",
            raw,
        )
    ids = match["ids"].split()
    if command == "propose" and len(ids) != 1:
        raise _err("propose", "propose takes exactly one proposal ID", raw)
    if command == "counter" and len(ids) != 2:
        raise _err("counter", "counter takes the old and the new proposal ID", raw)
    for proposal_id in ids:
        if not _PROPOSAL_ID_RE.fullmatch(proposal_id):
            raise _err(command, f"invalid proposal ID {proposal_id!r}", raw)
    duration_text = match["duration"].strip()
    if not duration_text:
        raise _err(command, "a proposal needs a duration (2h or 90m)", raw)
    duration = _parse_duration_text(duration_text, command=command, raw=raw)
    start = _parse_moment(match["start"].strip(), now=now, raw=raw, command=command)
    title = _unquote(match["title"])
    place = _unquote(match["place"])
    try:
        title = _title(title)
        place = _place(place)
    except ValueError as exc:
        raise _err(command, str(exc), raw) from None
    return ids, start, duration, title, place


def _handle_propose(args: str, *, target: str | None, now: datetime, raw: str) -> Command:
    ids, start, duration, title, place = _plan_parts("propose", args, raw=raw, now=now)
    return Propose(
        proposal_id=ids[0],
        start=start,
        duration=duration,
        title=title,
        place=place,
        target=target,
    )


def _handle_counter(args: str, *, target: str | None, now: datetime, raw: str) -> Command:
    ids, start, duration, title, place = _plan_parts("counter", args, raw=raw, now=now)
    return Counter(
        of=ids[0],
        proposal_id=ids[1],
        start=start,
        duration=duration,
        title=title,
        place=place,
        target=target,
    )


_BUDGET_RE: Final = re.compile(
    r"""(?:
        \bbudget\s*(?:<=|≤|=|<|:)?\s*(?:₹|rs\.?|inr)?\s*(?P<keyed>\d[\d,]*)
        |(?:₹|rs\.?|inr)\s*(?P<symbol>\d[\d,]*)
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def _handle_gift_ideas(args: str, *, target: str | None, now: datetime, raw: str) -> Command:
    budget: int | None = None
    text = args
    budget_match = _BUDGET_RE.search(args)
    if budget_match:
        amount = budget_match.group("keyed") or budget_match.group("symbol")
        budget = int(amount.replace(",", ""))
        if budget <= 0:
            raise _err("gift-ideas", "a gift budget must be a positive number", raw)
        text = (args[: budget_match.start()] + " " + args[budget_match.end() :]).strip()
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        raise _err("gift-ideas", "gift-ideas needs an occasion and a date", raw)
    occasion, day_text = parts
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", occasion):
        raise _err("gift-ideas", f"invalid occasion {occasion!r}", raw)
    day = _parse_day(day_text.strip(), now=now, raw=raw, command="gift-ideas")
    return GiftIdeas(occasion=occasion, on=day, budget=budget, target=target)


def _handle_claim(args: str, *, target: str | None, now: datetime, raw: str) -> Command:
    item = _unquote(args)
    if not item:
        raise _err("claim", "claim needs an item name", raw)
    try:
        return Claim(item=item, target=target)
    except ValueError as exc:
        raise _err("claim", str(exc), raw) from None


def _handle_ask_around(args: str, *, target: str | None, now: datetime, raw: str) -> Command:
    if not args:
        raise _err("ask-around", "ask-around needs a quoted question", raw)
    return AskAround(
        question=_quoted(args, command="ask-around", raw=raw),
        target=target,
    )


def _handle_dm(args: str, *, target: str | None, now: datetime, raw: str) -> Command:
    parts = args.split(maxsplit=1)
    if len(parts) != 2:
        raise _err("dm", "dm needs a person and a quoted goal", raw)
    person, goal = parts
    try:
        person = _person(person)
    except ValueError as exc:
        raise _err("dm", str(exc), raw) from None
    return Dm(
        person=person,
        goal=_quoted(goal, command="dm", raw=raw),
        target=target,
    )


def _handle_yes(args: str, *, target: str | None, now: datetime, raw: str) -> Command:
    if not _PROPOSAL_ID_RE.fullmatch(args.strip()):
        raise _err("yes", "yes needs a proposal ID like P1", raw)
    return Yes(proposal_id=args.strip(), target=target)


def _handle_no(args: str, *, target: str | None, now: datetime, raw: str) -> Command:
    if not _PROPOSAL_ID_RE.fullmatch(args.strip()):
        raise _err("no", "no needs a proposal ID like P1", raw)
    return No(proposal_id=args.strip(), target=target)


def _handle_answer(args: str, *, target: str | None, now: datetime, raw: str) -> Command:
    match = re.fullmatch(r"(?P<ref>[QP]\d+)\s+(?P<text>.+)", args, re.IGNORECASE)
    if not match:
        raise _err("answer", "answer needs a question or proposal ID and a text", raw)
    return Answer(
        reference=match["ref"],
        text=_quoted(match["text"], command="answer", raw=raw),
        target=target,
    )


def _handle_trust(args: str, *, target: str | None, now: datetime, raw: str) -> Command:
    parts = args.split()
    if len(parts) != 2:
        raise _err("trust", "trust needs a person and a level", raw)
    person, level_text = parts
    try:
        person = _person(person)
        level = Level(level_text.lower())
    except ValueError as exc:
        raise _err("trust", f"invalid trust command: {exc}", raw) from None
    if not level.is_viewer:
        raise _err("trust", "a trust level must be acquaintance, friend or close", raw)
    return Trust(person=person, level=level, target=target)


def _handle_view_as(args: str, *, target: str | None, now: datetime, raw: str) -> Command:
    parts = args.split()
    if len(parts) != 1:
        raise _err("view-as", "view-as needs exactly one person", raw)
    try:
        person = _person(parts[0])
    except ValueError as exc:
        raise _err("view-as", str(exc), raw) from None
    return ViewAs(person=person, target=target)


def _handle_ledger(args: str, *, target: str | None, now: datetime, raw: str) -> Command:
    if args:
        raise _err("ledger", "ledger takes no arguments", raw)
    return Ledger(target=target)


def _handle_join_dm(args: str, *, target: str | None, now: datetime, raw: str) -> Command:
    parts = args.split(maxsplit=1)
    if len(parts) != 2:
        raise _err("join-dm", "join-dm needs a room and a quoted goal", raw)
    room, goal = parts
    try:
        room = _room(room)
    except ValueError as exc:
        raise _err("join-dm", str(exc), raw) from None
    return JoinDm(
        room=room,
        goal=_quoted(goal, command="join-dm", raw=raw),
        target=target,
    )


def _handle_consent(args: str, *, target: str | None, now: datetime, raw: str) -> Command:
    match = re.fullmatch(
        r"(?P<id>P\d+)\s+(?P<answer>yes|no)\s+(?P<via>via-agent|direct)",
        args.strip(),
        re.IGNORECASE,
    )
    if not match:
        raise _err(
            "consent",
            "consent needs a proposal ID, yes|no and via-agent|direct",
            raw,
        )
    return Consent(
        proposal_id=match["id"],
        agreed=match["answer"].lower() == "yes",
        via=match["via"].lower(),
        target=target,
    )


_Handler: TypeAlias = Callable[..., Command]

_HANDLERS: Final[dict[str, _Handler]] = {
    "free": _handle_free,
    "ask": _handle_ask,
    "ask-owner": _handle_ask_owner,
    "propose": _handle_propose,
    "counter": _handle_counter,
    "gift-ideas": _handle_gift_ideas,
    "claim": _handle_claim,
    "ask-around": _handle_ask_around,
    "dm": _handle_dm,
    "yes": _handle_yes,
    "no": _handle_no,
    "answer": _handle_answer,
    "trust": _handle_trust,
    "view-as": _handle_view_as,
    "ledger": _handle_ledger,
    "join-dm": _handle_join_dm,
    "consent": _handle_consent,
}
