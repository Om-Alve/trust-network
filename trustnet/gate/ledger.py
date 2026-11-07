"""Append-only JSONL records of disclosures and approved visibility changes.

Malformed lines raise rather than silently dropping history. Owner views hide
sealed gift entries until their reveal date.
"""

from __future__ import annotations

import fcntl
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from trustnet.gate.calendar import TIME_ZONE
from trustnet.gate.facts import resolve_data_dir

__all__ = [
    "DEFAULT_MAX_LINES",
    "Entry",
    "KINDS",
    "Kind",
    "LEDGER_FILENAME",
    "LedgerError",
    "OwnerView",
    "format_ledger",
    "ledger_path",
    "owner_view",
    "read",
    "record",
    "record_brief",
]

LEDGER_FILENAME: Final = "ledger.jsonl"

#: The maximum number of lines :func:`format_ledger` prints.
DEFAULT_MAX_LINES: Final = 20


class LedgerError(ValueError):
    """A ledger entry is malformed, or the ledger file cannot be read."""


class Kind(StrEnum):
    """Why a fact was disclosed."""

    FACT_VISIBILITY = "fact-visibility"
    TRUST_CHANGE = "trust-change"
    ANSWER = "answer"
    BRIEF = "brief"
    PROPOSAL = "proposal"
    GIFT = "gift"
    ASK_AROUND = "ask-around"
    REQUEST = "request"


KINDS: Final[frozenset[str]] = frozenset(kind.value for kind in Kind)


@dataclass(frozen=True, slots=True)
class Entry:
    """One disclosure: a fact, who received it, where and when.

    ``ts`` is an aware Asia/Kolkata time. ``sealed_until`` is a date: the entry
    becomes visible to the owner on that day.
    """

    ts: datetime
    field: str
    value: Any
    to: str
    room: str
    kind: Kind
    sealed_until: date | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "ts", _as_ist(self.ts, "ts"))
        object.__setattr__(self, "field", _text(self.field, "field"))
        object.__setattr__(self, "to", _text(self.to, "to"))
        object.__setattr__(self, "room", _text(self.room, "room"))
        object.__setattr__(self, "kind", _as_kind(self.kind))
        if self.sealed_until is not None:
            object.__setattr__(self, "sealed_until", _as_date(self.sealed_until, "sealed_until"))

    def is_sealed(self, now: datetime) -> bool:
        """Whether the owner still cannot see this entry at ``now``."""
        return self.sealed_until is not None and _as_ist(now, "now").date() < self.sealed_until

    def to_dict(self) -> dict[str, Any]:
        """The JSON shape written to ``ledger.jsonl`` (``ts`` first)."""
        payload: dict[str, Any] = {
            "ts": self.ts.isoformat(),
            "field": self.field,
            "value": self.value,
            "to": self.to,
            "room": self.room,
            "kind": self.kind.value,
        }
        if self.sealed_until is not None:
            payload["sealed_until"] = self.sealed_until.isoformat()
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], *, where: str = "entry") -> Entry:
        """Rebuild an entry from one JSON object; ``where`` names it in errors."""
        if not isinstance(payload, Mapping):
            raise LedgerError(f"{where}: expected a JSON object, not {payload!r}")
        for key in ("ts", "field", "value", "to", "room", "kind"):
            if key not in payload:
                raise LedgerError(f"{where}: missing {key!r}")
        try:
            ts = datetime.fromisoformat(str(payload["ts"]))
        except ValueError:
            raise LedgerError(f"{where}: invalid ts {payload['ts']!r}") from None
        return cls(
            ts=ts,
            field=payload["field"],
            value=payload["value"],
            to=payload["to"],
            room=payload["room"],
            kind=payload["kind"],
            sealed_until=payload.get("sealed_until"),
        )


@dataclass(frozen=True, slots=True)
class OwnerView:
    """What the owner may see in the ledger at one moment.

    ``visible`` is newest first and holds opened entries only. ``sealed`` holds
    entries whose ``sealed_until`` is still in the future; the owner sees them
    as a count and a date (``1 sealed entry, opens Nov 21``).
    """

    visible: tuple[Entry, ...]
    sealed: tuple[Entry, ...]

    @property
    def sealed_count(self) -> int:
        return len(self.sealed)

    @property
    def sealed_opens(self) -> date | None:
        """The earliest day a still-sealed entry opens, or ``None``."""
        days = [entry.sealed_until for entry in self.sealed if entry.sealed_until is not None]
        return min(days) if days else None

    @property
    def sealed_line(self) -> str:
        """``1 sealed entry, opens Nov 21`` (empty when nothing is sealed)."""
        if not self.sealed:
            return ""
        count = len(self.sealed)
        noun = "entry" if count == 1 else "entries"
        opens = self.sealed_opens
        if opens is None:
            return f"{count} sealed {noun}"
        prefix = "opens" if count == 1 else "first opens"
        return f"{count} sealed {noun}, {prefix} {_short_date(opens)}"


def ledger_path(person: str) -> Path:
    """Return the ledger file for ``person``: ``<data dir>/ledger.jsonl``."""
    return resolve_data_dir(person) / LEDGER_FILENAME


def record(
    field: str,
    value: Any,
    to: str,
    room: str,
    kind: Kind | str,
    *,
    person: str,
    sealed_until: date | datetime | str | None = None,
    now: datetime | None = None,
    operation_id: str | None = None,
) -> Entry:
    """Append one disclosure to ``person``'s ledger and return it.

    ``person`` is the ledger's owner (the gate's person), ``to`` the person who
    received the fact, and ``kind`` one of :data:`KINDS`. ``value`` must be
    JSON-serializable. ``now`` is injectable for tests and demos.
    """
    entry = Entry(
        ts=_now(now),
        field=field,
        value=value,
        to=to,
        room=room,
        kind=kind,
        sealed_until=sealed_until,
    )
    _append(entry, ledger_path(person), operation_id=operation_id)
    return entry


def record_brief(
    brief_facts: Mapping[str, Any],
    to: str,
    room: str,
    *,
    person: str,
    sealed_until: date | datetime | str | None = None,
    now: datetime | None = None,
) -> list[Entry]:
    """Log every fact a brief disclosed (Rule 6), one entry per fact.

    ``brief_facts`` is exactly the mapping the brief was built from (normally
    :func:`trustnet.gate.policy.visible_facts`). The order of the mapping is
    kept. All entries share one timestamp and, if given, one ``sealed_until``.
    """
    if not isinstance(brief_facts, Mapping):
        raise LedgerError(f"brief_facts must be a mapping, not {brief_facts!r}")
    stamp = _now(now)
    entries: list[Entry] = []
    for field, value in brief_facts.items():
        entries.append(
            record(
                field,
                value,
                to,
                room,
                Kind.BRIEF,
                person=person,
                sealed_until=sealed_until,
                now=stamp,
            )
        )
    return entries


def read(person: str) -> list[Entry]:
    """Return every entry in ``person``'s ledger, oldest first.

    A missing file is an empty ledger. A malformed line raises
    :class:`LedgerError`; the file is never rewritten or fixed up here.
    """
    path = ledger_path(person)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise LedgerError(f"{path}: cannot read ledger: {exc}") from None

    entries: list[Entry] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"{path}:{number}: invalid JSON: {exc}") from None
        entries.append(Entry.from_dict(payload, where=f"{path}:{number}"))
    return entries


def owner_view(now: datetime | None = None, *, person: str) -> OwnerView:
    """The owner's view of the ledger at ``now``.

    Unsealed entries are returned in full, newest first. Sealed entries whose
    day has not come are collapsed into ``sealed``; once ``now`` reaches
    ``sealed_until`` they join ``visible`` like any other entry.
    """
    moment = _now(now)
    entries = read(person)
    visible = [entry for entry in entries if not entry.is_sealed(moment)]
    sealed = [entry for entry in entries if entry.is_sealed(moment)]
    visible.sort(key=lambda entry: entry.ts, reverse=True)
    sealed.sort(key=lambda entry: entry.sealed_until or date.min)
    return OwnerView(visible=tuple(visible), sealed=tuple(sealed))


def format_ledger(
    now: datetime | None = None,
    *,
    person: str,
    max_lines: int = DEFAULT_MAX_LINES,
) -> str:
    """Compact home-channel text: grouped by person, newest first.

    The result is at most ``max_lines`` lines (header and the sealed summary
    included). When entries do not fit, the oldest are replaced by a
    ``… N more entries`` line; the sealed line never gets dropped.
    """
    if isinstance(max_lines, bool) or not isinstance(max_lines, int) or max_lines < 3:
        raise LedgerError(f"max_lines must be an integer of at least 3, not {max_lines!r}")

    moment = _now(now)
    view = owner_view(moment, person=person)
    if not view.visible and not view.sealed:
        return "Nothing shared yet."
    if not view.visible:
        return view.sealed_line

    total = len(view.visible)
    people: dict[str, list[Entry]] = {}
    for entry in view.visible:
        people.setdefault(entry.to.casefold(), []).append(entry)

    grouped_label = "person" if len(people) == 1 else "people"
    lines = [
        f"Shared: {total} {'entry' if total == 1 else 'entries'} · {len(people)} {grouped_label}"
    ]

    sealed = view.sealed_line
    blocks: list[list[str]] = []
    for name, entries in people.items():
        block = [name]
        block.extend(_entry_line(entry) for entry in entries)
        blocks.append(block)

    # Reserve the header and the sealed line; if not everything fits, reserve
    # one more line for the truncation notice before filling groups.
    budget = max_lines - 1 - (1 if sealed else 0)
    fits = sum(len(block) for block in blocks) <= budget
    allowance = budget if fits else budget - 1
    used = 0
    shown_entries = 0
    for block in blocks:
        if used + len(block) <= allowance:
            lines.extend(block)
            used += len(block)
            shown_entries += len(block) - 1
            continue
        room = allowance - used
        if room > 1:  # keep the person's header with at least one entry
            lines.append(block[0])
            take = min(len(block) - 1, room - 1)
            lines.extend(block[1 : 1 + take])
            shown_entries += take
        break

    if not fits:
        remaining = total - shown_entries
        noun = "entry" if remaining == 1 else "entries"
        lines.append(f"… {remaining} more {noun}")
    if sealed:
        lines.append(sealed)
    return "\n".join(lines)


def _append(entry: Entry, path: Path, *, operation_id=None) -> None:
    from trustnet.gate.storage import atomic_write

    payload = entry.to_dict()
    if operation_id:
        payload["_operation_id"] = operation_id
    try:
        line = (json.dumps(payload, ensure_ascii=False) + "\n").encode()
    except TypeError as exc:
        raise LedgerError(f"value is not JSON-serializable: {exc}") from None
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            existing = path.read_bytes() if path.exists() else b""
            if operation_id and any(
                json.loads(line).get("_operation_id") == operation_id
                for line in existing.splitlines()
            ):
                return
            atomic_write(path, existing + line)
    except OSError as exc:
        raise LedgerError(f"{path}: cannot append to ledger: {exc}") from None


def _entry_line(entry: Entry) -> str:
    stamp = f"{entry.ts:%b} {entry.ts.day} {entry.ts:%H:%M}"
    return f"  {stamp}  {entry.room}  {entry.kind.value:<10}  {_field(entry)}"


def _field(entry: Entry) -> str:
    if entry.kind is Kind.ASK_AROUND:
        text = _compact(entry.value)
    else:
        text = f"{entry.field}: {_compact(entry.value)}"
    return text if len(text) <= 90 else text[:89] + "…"


def _compact(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return ", ".join(f"{key}: {_compact(item)}" for key, item in value.items())
    if isinstance(value, list | tuple):
        return ", ".join(_compact(item) for item in value)
    return str(value)


def _short_date(day: date) -> str:
    return f"{day:%b} {day.day}"


def _now(value: datetime | None) -> datetime:
    return datetime.now(TIME_ZONE) if value is None else _as_ist(value, "now")


def _as_ist(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime):
        raise LedgerError(f"{label} must be a datetime, not {value!r}")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=TIME_ZONE)
    return value.astimezone(TIME_ZONE)


def _as_date(value: date | datetime | str, label: str) -> date:
    if isinstance(value, datetime):
        return _as_ist(value, label).date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            raise LedgerError(f"{label} must be an ISO date (YYYY-MM-DD), not {value!r}") from None
    raise LedgerError(f"{label} must be a date, not {value!r}")


def _as_kind(value: Kind | str) -> Kind:
    if isinstance(value, Kind):
        return value
    if not isinstance(value, str) or value.strip().lower() not in KINDS:
        raise LedgerError(f"kind must be one of {sorted(KINDS)}, not {value!r}")
    return Kind(value.strip().lower())


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LedgerError(f"{label} must be a non-empty string, not {value!r}")
    return value.strip()
