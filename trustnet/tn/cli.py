"""Local data commands and Switch-connected personal-agent operations.

TN_PERSON or --as selects the owner. Commands emit text or --json output.
Naive calendar times use Asia/Kolkata.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Final

import dateparser
import yaml
from icalendar import Calendar

from trustnet.gate.calendar import TIME_ZONE, CalendarError, add_event
from trustnet.gate.facts import (
    FACTS_FILENAME,
    TRUST_FILENAME,
    Fact,
    FactsError,
    Level,
    PersonPermissions,
    Profile,
    TrustList,
    field_key,
    load_profile,
    load_trust,
    resolve_data_dir,
    save_profile,
    save_trust,
)
from trustnet.gate.policy import Actor, can_set_level
from trustnet.gate.view_as import ViewAsError, format_value, view_as
from trustnet.switch_client import SwitchError

__all__ = ["main"]

CALENDAR_FILENAME: Final = "calendar.ics"

#: Fact levels a person may tag a fact with (``self`` is a room view, not a tag).
FACT_LEVEL_NAMES: Final = "acquaintance, friend, close or private"
VIEWER_LEVEL_NAMES: Final = "acquaintance, friend or close"

#: The fixed form's limits, shared with the gate's proposal validation.
MAX_TITLE: Final = 60
MAX_PLACE: Final = 60
_PLACE_RE: Final = re.compile(r"[A-Za-z0-9 ,.'&-]+")
_TITLE_FORBIDDEN: Final = frozenset('\n\r"@')

_DURATION_RE: Final = re.compile(
    r"^\s*(?:(?P<hours>\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h))?"
    r"\s*(?:(?P<minutes>\d+(?:\.\d+)?)\s*(?:minutes?|mins?|m))?\s*$",
    re.IGNORECASE,
)
_PROPOSAL_ID_RE: Final = re.compile(r"P\d+", re.IGNORECASE)

Handler = Callable[["Context", argparse.Namespace], int]


class CliError(ValueError):
    """A command cannot run as written; the message is shown to the person."""


@dataclass(frozen=True, slots=True)
class Context:
    """Who the command acts for, and how to print its result."""

    person: str | None
    json: bool

    def owner(self) -> str:
        """The person named by ``--as`` or ``$TN_PERSON``; error when neither."""
        name = (self.person or os.environ.get("TN_PERSON", "")).strip().lower()
        if not name:
            raise CliError("pass --as <person> or set TN_PERSON")
        return name

    def emit(self, payload: dict[str, Any], text: str) -> int:
        """Print one result: ``payload`` as JSON, or ``text`` for people."""
        if self.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(text)
        return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _global_options(*, suppress: bool) -> argparse.ArgumentParser:
    """A parent parser holding ``--as`` and ``--json``.

    The subparser copies use ``SUPPRESS`` defaults, so they never reset a flag
    given before the subcommand: both ``tn --as om view-as rahul`` and
    ``tn view-as rahul --as om`` work. Using ``set_defaults`` here instead
    would mutate the shared action and break the first form.
    """
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "-a",
        "--as",
        dest="person",
        metavar="PERSON",
        default=argparse.SUPPRESS if suppress else None,
        help="whose data to act on (default: $TN_PERSON)",
    )
    parent.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS if suppress else False,
        help="print machine-readable JSON instead of text",
    )
    return parent


def _build_parser() -> argparse.ArgumentParser:
    """Build the parser. Phase 15 adds its Switch commands beside these."""
    common = _global_options(suppress=True)
    parser = argparse.ArgumentParser(
        prog="tn",
        description=(
            "Your own trust-network data: trust levels, facts, calendar and view-as. "
            "dm-read and dm-post connect to Switch using your main-agent identity."
        ),
        parents=[_global_options(suppress=False)],
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")

    init = commands.add_parser(
        "init",
        parents=[common],
        help="create an empty profile for a person",
        description="Create trust.yaml, facts.yaml and calendar.ics for a person.",
    )
    init.add_argument("person_name", nargs="?", metavar="person", help="default: --as / $TN_PERSON")
    init.add_argument("--force", action="store_true", help="overwrite an existing profile")
    init.set_defaults(handler=_cmd_init)

    trust = commands.add_parser(
        "trust",
        parents=[common],
        help="set the level you give a person",
        description=f"Set a person's level in your trust list ({VIEWER_LEVEL_NAMES}).",
    )
    trust.add_argument("person_name", metavar="person")
    trust.add_argument("level", metavar="level")
    trust.add_argument(
        "--allow",
        action="append",
        metavar="FIELD[,FIELD]",
        help="share named fields above this person's level (deny still wins)",
    )
    trust.add_argument(
        "--deny",
        action="append",
        metavar="FIELD[,FIELD]",
        help="hide named fields from this person regardless of level",
    )
    trust.add_argument(
        "--calendar-titles",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="opt this person in to event titles (default: hidden)",
    )
    trust.add_argument(
        "--ask-around",
        choices=["agent", "person", "off"],
        default=None,
        help="who hears this friend's ask-around: your agent, you, or nobody",
    )
    trust.add_argument(
        "--clear-permissions",
        action="store_true",
        help="reset allow/deny, calendar titles and ask-around routing before applying flags",
    )
    trust.set_defaults(handler=_cmd_trust)

    for name, help_text in (
        ("untrust", "remove a person from your trust list"),
        ("block", "remove a person and remember a block until an explicit unblock"),
        ("unblock", "lift a block without re-adding the person"),
    ):
        sub = commands.add_parser(name, parents=[common], help=help_text)
        sub.add_argument("person_name", metavar="person")
        sub.set_defaults(handler=_cmd_trust_removal, action=name)
    blocked = commands.add_parser(
        "blocked", parents=[common], help="list people blocked from your trust list"
    )
    blocked.set_defaults(handler=_cmd_blocked)

    fact = commands.add_parser(
        "fact",
        parents=[common],
        help="read or tighten your facts",
        description="Your facts, tagged with the lowest level that may see them.",
    )
    fact_commands = fact.add_subparsers(dest="fact_command", required=True, metavar="command")

    fact_get = fact_commands.add_parser(
        "get",
        parents=[common],
        help="show facts from the owner's own view",
    )
    fact_get.add_argument("keys", nargs="*", metavar="key", help="default: every fact")
    fact_get.set_defaults(handler=_cmd_fact_get)

    fact_set = fact_commands.add_parser(
        "set",
        parents=[common],
        help="tighten a fact (use share-request to ask for wider visibility)",
    )
    fact_set.add_argument("key", metavar="key")
    fact_set.add_argument("--level", required=True, metavar="level")
    fact_set.add_argument(
        "--value",
        metavar="VALUE",
        help="new value; a value starting with [ or { is read as YAML",
    )
    fact_set.set_defaults(handler=_cmd_fact_set)

    for name in ("add", "share-request", "approve", "decline"):
        action = fact_commands.add_parser(name, parents=[common])
        if name == "add":
            action.add_argument("key")
            action.add_argument("--value", required=True)
        elif name == "share-request":
            action.add_argument("key")
            action.add_argument("level")
            action.add_argument("--reason", default="")
        else:
            action.add_argument("refs", nargs="+")
        action.set_defaults(handler=_cmd_fact_change, action=name)

    suggestion = commands.add_parser("trust-suggest", parents=[common])
    suggestion.add_argument("friend")
    suggestion.add_argument("level")
    suggestion.add_argument("reason")
    suggestion.set_defaults(handler=_cmd_fact_change, action="trust-suggest")
    review = commands.add_parser("review", parents=[common])
    group = review.add_mutually_exclusive_group()
    group.add_argument("--approve", nargs="+")
    group.add_argument("--decline", nargs="+")
    review.set_defaults(handler=_cmd_fact_change, action="review")

    cal = commands.add_parser(
        "cal",
        parents=[common],
        help="read or write your calendar",
        description="Your .ics calendar (Asia/Kolkata).",
    )
    cal_commands = cal.add_subparsers(dest="cal_command", required=True, metavar="command")

    cal_add = cal_commands.add_parser(
        "add",
        parents=[common],
        help="add an accepted plan to the calendar",
        description='Append an event: cal add <start> <duration> "<title>" @ "<place>" [--id P1]',
    )
    cal_add.add_argument("start", metavar="start", help="2026-11-08T21:00, Sun 9pm, ...")
    cal_add.add_argument("duration", metavar="duration", help="2h, 90m, 1h30m")
    cal_add.add_argument("title", metavar="title")
    cal_add.add_argument("at", metavar="@", help="the literal @ before the place")
    cal_add.add_argument("place", metavar="place")
    cal_add.add_argument("--id", dest="event_id", metavar="ID", help="event id, e.g. P1")
    cal_add.set_defaults(handler=_cmd_cal_add)

    view = commands.add_parser(
        "view-as",
        parents=[common],
        help="show exactly what a person's side can learn",
        description="Print the field-by-field table for one person's trust level.",
    )
    view.add_argument("person_name", metavar="person")
    view.add_argument(
        "--days", type=int, default=7, metavar="N", help="calendar window (default 7)"
    )
    view.set_defaults(handler=_cmd_view_as)

    for name in ("gift-ideas", "claim"):
        sub = commands.add_parser(name, parents=[common])
        sub.add_argument("friend")
        if name == "gift-ideas":
            sub.add_argument("occasion")
            sub.add_argument("date")
            sub.add_argument("budget", type=int)
        else:
            sub.add_argument("item")
        sub.set_defaults(handler=_cmd_gift)

    for name in ("inbox", "watch", "answer", "dm", "ask-around"):
        sub = commands.add_parser(name, parents=[common])
        if name == "ask-around":
            sub.add_argument("question")
            sub.add_argument(
                "--to",
                action="append",
                metavar="PERSON[,PERSON]",
                help="ask only these friends (default: everyone on your trust list)",
            )
        if name == "answer":
            sub.add_argument("id")
            sub.add_argument("text")
        if name == "dm":
            sub.add_argument("friend")
            sub.add_argument("goal")
        sub.set_defaults(handler=_cmd_personal)

    for name in ("dm-read", "dm-post"):
        sub = commands.add_parser(name, parents=[common])
        sub.add_argument("room")
        if name == "dm-post":
            sub.add_argument("text")
        sub.set_defaults(handler=_cmd_dm)
    mcp = commands.add_parser("mcp", parents=[common], help="run the personal MCP server")
    mcp.set_defaults(handler=_cmd_mcp)
    wake = commands.add_parser(
        "wake", parents=[common], help="run any CLI agent as this person's agent"
    )
    agent = wake.add_mutually_exclusive_group(required=True)
    from trustnet.tn.wake import PRESETS

    agent.add_argument("--agent", choices=list(PRESETS), help="a known agent CLI")
    agent.add_argument("--cmd", help="any agent command: prompt on stdin, reply on stdout")
    defaults = ", ".join(
        f"{name}: {p.model or 'its configured model'}" for name, p in PRESETS.items()
    )
    wake.add_argument("--model", help=f"model for --agent ({defaults})")
    wake.add_argument("--every", type=float, default=15.0, help="seconds between watches")
    wake.set_defaults(handler=_cmd_wake)
    from trustnet.tn.setup import add_commands

    add_commands(commands, common)

    outbox = commands.add_parser(
        "outbox", parents=[common], help="review exact outgoing agent messages"
    )
    outbox.add_argument("action", choices=("list", "approve", "decline"), default="list", nargs="?")
    outbox.add_argument("ref", nargs="?")
    outbox.set_defaults(handler=_cmd_outbox)
    from trustnet.tn.host import add_commands as add_host_commands

    add_host_commands(commands, common)
    return parser


def _cmd_outbox(context, args):
    from trustnet.tn import outgoing

    person = context.owner()
    if args.action == "list":
        items = outgoing.pending(person)
        return context.emit({"pending": items}, json.dumps(items, ensure_ascii=False, indent=2))
    if not args.ref:
        raise CliError("Supply the outgoing reference you reviewed")
    item = (
        asyncio.run(outgoing.release(person, args.ref))
        if args.action == "approve"
        else outgoing.decline(person, args.ref)
    )
    return context.emit(item, f"{item['ref']}: {item['status']}")


def main(argv: list[str] | None = None) -> int:
    """Run one ``tn`` command and return its exit code (0 ok, 1 refused, 2 usage)."""
    from trustnet.tn.configuration import apply

    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # --help, or a usage error: return, don't exit
        return exc.code if isinstance(exc.code, int) else 0

    context = Context(
        person=getattr(args, "person", None),
        json=bool(getattr(args, "json", False)),
    )
    handler: Handler = args.handler
    try:
        apply()
        return handler(context, args)
    except (CliError, FactsError, CalendarError, ViewAsError, SwitchError) as exc:
        print(f"tn: error: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"tn: error: {exc}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def _cmd_init(context: Context, args: argparse.Namespace) -> int:
    person = (args.person_name or context.owner()).strip().lower()
    directory = resolve_data_dir(person)
    files = (TRUST_FILENAME, FACTS_FILENAME, CALENDAR_FILENAME)
    existing = [name for name in files if (directory / name).exists()]
    if existing and not args.force:
        found = ", ".join(existing)
        raise CliError(f"{directory} already has {found}; pass --force to overwrite")

    directory.mkdir(parents=True, exist_ok=True)
    _write_empty_calendar(directory / CALENDAR_FILENAME)
    save_trust(TrustList(), directory / TRUST_FILENAME)
    save_profile(
        Profile(
            owner=person,
            facts={},
            calendar_path=(directory / CALENDAR_FILENAME).resolve(),
        ),
        directory / FACTS_FILENAME,
    )

    payload = {
        "person": person,
        "data_dir": str(directory),
        "files": list(files),
        "overwrote": bool(existing),
    }
    return context.emit(payload, f"created {person} in {directory} ({', '.join(files)})")


def _write_empty_calendar(path: Path) -> None:
    calendar = Calendar()
    calendar.add("PRODID", "-//trust-network//tn init//EN")
    calendar.add("VERSION", "2.0")
    calendar.add("CALSCALE", "GREGORIAN")
    calendar.add("X-WR-TIMEZONE", TIME_ZONE.key)
    path.write_bytes(calendar.to_ical())


# ---------------------------------------------------------------------------
# trust
# ---------------------------------------------------------------------------


def _cmd_trust(context: Context, args: argparse.Namespace) -> int:
    from trustnet.gate.fact_changes import editing

    with editing(context.owner()):
        return _cmd_trust_locked(context, args)


def _cmd_trust_locked(context: Context, args: argparse.Namespace) -> int:
    owner = context.owner()
    trust = load_trust(owner)
    if trust.is_blocked(args.person_name):
        person = args.person_name.strip().lower()
        raise CliError(f"{person} is blocked; run `tn unblock {person}` first")
    previous = trust.level_for(args.person_name)  # validates the name
    level = _parse_level(args.level, viewer=True)
    person = trust.grant(args.person_name, level)

    requested = any(
        (
            args.allow is not None,
            args.deny is not None,
            args.calendar_titles is not None,
            args.ask_around is not None,
            args.clear_permissions,
        )
    )
    permissions = trust.permissions_for(person)
    if requested:
        permissions = trust.permissions.setdefault(person, PersonPermissions())
        if args.clear_permissions:
            permissions.allow.clear()
            permissions.deny.clear()
            permissions.calendar_titles = False
            permissions.ask_around = "agent"
        if args.allow is not None:
            permissions.allow = _field_names(args.allow)
        if args.deny is not None:
            permissions.deny = _field_names(args.deny)
        if args.calendar_titles is not None:
            permissions.calendar_titles = args.calendar_titles
        if args.ask_around is not None:
            permissions.ask_around = args.ask_around
        if permissions.is_default():
            trust.permissions.pop(person, None)
    save_trust(trust, resolve_data_dir(owner) / TRUST_FILENAME)

    payload = {
        "owner": owner,
        "person": person,
        "level": level.value,
        "previous": previous.value if previous is not None else None,
    }
    if requested:
        payload["permissions"] = _permissions_payload(permissions)
    if previous is None:
        text = f"{owner} trusts {person} at {level.value}"
    elif previous is level:
        text = f"{owner} trusts {person} at {level.value}"
    else:
        text = f"{owner} trusts {person}: {previous.value} → {level.value}"
    if requested:
        text += _permissions_summary(permissions)
    return context.emit(payload, text)


def _field_names(values: list[str] | None) -> set[str]:
    """Parse repeated/comma-separated field flags into a normalized set."""
    names: set[str] = set()
    for value in values or []:
        for part in value.replace(" ", ",").split(","):
            if part.strip():
                names.add(field_key(part))
    return names


def _permissions_payload(permissions: PersonPermissions) -> dict[str, Any]:
    return {
        "allow": sorted(permissions.allow),
        "deny": sorted(permissions.deny),
        "calendar_titles": permissions.calendar_titles,
        "ask_around": permissions.ask_around,
    }


def _permissions_summary(permissions: PersonPermissions) -> str:
    parts: list[str] = []
    if permissions.allow:
        parts.append("allow " + ", ".join(sorted(permissions.allow)))
    if permissions.deny:
        parts.append("deny " + ", ".join(sorted(permissions.deny)))
    parts.append("titles " + ("on" if permissions.calendar_titles else "off"))
    parts.append("ask-around " + permissions.ask_around)
    return " · " + "; ".join(parts)


def _cmd_trust_removal(context: Context, args: argparse.Namespace) -> int:
    from trustnet.gate.fact_changes import editing

    owner = context.owner()
    with editing(owner):
        trust = load_trust(owner)
        person = args.person_name.strip().lower()
        if not person:
            raise CliError("a person is required")
        if args.action == "untrust":
            if trust.is_blocked(person):
                raise CliError(f"{person} is blocked; run `tn unblock {person}` first")
            if person not in trust.people:
                raise CliError(f"{person} is not on {owner}'s trust list")
            trust.people.pop(person, None)
            trust.permissions.pop(person, None)
            text = f"{owner} no longer trusts {person}"
        elif args.action == "block":
            trust.block(person)
            text = f"{owner} blocked {person}; run `tn unblock {person}` before adding them again"
        else:
            trust.unblock(person)
            text = f"{owner} unblocked {person}; add them again with `tn trust {person} <level>`"
        save_trust(trust, resolve_data_dir(owner) / TRUST_FILENAME)
        payload = {
            "owner": owner,
            "person": person,
            "action": args.action,
            "blocked": trust.is_blocked(person),
            "people": sorted(trust.people),
        }
    return context.emit(payload, text)


def _cmd_blocked(context: Context, args: argparse.Namespace) -> int:
    owner = context.owner()
    trust = load_trust(owner)
    payload = {"owner": owner, "blocked": list(trust.blocked)}
    text = ", ".join(trust.blocked) if trust.blocked else f"{owner} has no blocked people"
    return context.emit(payload, text)


# ---------------------------------------------------------------------------
# fact get / fact set
# ---------------------------------------------------------------------------


def _cmd_fact_get(context: Context, args: argparse.Namespace) -> int:
    from trustnet.gate import fact_changes

    fact_changes.recover(context.owner())
    owner = context.owner()
    profile = load_profile(owner)
    from trustnet.gate.surprise import owner_value

    names = tuple(key.strip() for key in args.keys if key.strip())
    if names:
        missing = [name for name in names if name not in profile.facts]
        if missing:
            available = ", ".join(profile.facts) or "none"
            raise CliError(f"no fact named {', '.join(missing)} (have: {available})")
    else:
        names = tuple(profile.facts)

    payload = {
        "owner": owner,
        "facts": {
            name: {
                "value": _jsonable(owner_value(owner, name, profile.facts[name].value)),
                "level": profile.facts[name].level.value,
            }
            for name in names
        },
    }
    if not names:
        return context.emit(payload, f"{owner} has no facts yet")

    width = max(len(name) for name in names)
    level_width = max(len(profile.facts[name].level.value) for name in names)
    count = len(names)
    lines = [f"{owner} — {count} {'fact' if count == 1 else 'facts'}"]
    for name in names:
        fact = profile.facts[name]
        lines.append(
            f"  {name:<{width}}  {fact.level.value:<{level_width}}  {format_value(owner_value(owner, name, fact.value))}"
        )
    return context.emit(payload, "\n".join(lines))


def _cmd_fact_change(context: Context, args: argparse.Namespace) -> int:
    from trustnet.gate import fact_changes as changes

    owner = context.owner()
    if args.action == "add":
        result = changes.add(owner, args.key, args.value)
    elif args.action == "share-request":
        result = changes.suggest(owner, args.key, args.level, args.reason)
    elif args.action == "trust-suggest":
        result = changes.suggest(owner, args.friend, args.level, args.reason, trust=True)
    elif args.action in {"approve", "decline"}:
        result = changes.decide(owner, args.refs, args.action == "approve")
    elif args.approve or args.decline:
        result = changes.decide(owner, args.approve or args.decline, bool(args.approve))
    else:
        result = {"pending": changes.review(owner)}
    return context.emit(result, json.dumps(result, ensure_ascii=False, indent=2))


def _cmd_fact_set(context: Context, args: argparse.Namespace) -> int:
    from trustnet.gate.fact_changes import editing

    with editing(context.owner()):
        return _cmd_fact_set_locked(context, args)


def _cmd_fact_set_locked(context: Context, args: argparse.Namespace) -> int:
    owner = context.owner()
    profile = load_profile(owner)
    key = args.key.strip()
    if not key:
        raise CliError("a fact needs a name")
    level = _parse_level(args.level, viewer=False)

    fact = profile.facts.get(key)
    if fact is None:
        if args.value is None:
            raise CliError(f"no fact named {key!r}; pass --value to create it")
        fact = Fact(value=_parse_value(args.value), level=level)
        profile.facts[key] = fact
        previous: Level | None = None
    else:
        if not can_set_level(fact.level, level, Actor.AGENT):
            raise CliError(
                f"refusing to loosen {key}: {fact.level.value} → {level.value}; "
                "edit facts.yaml by hand to loosen"
            )
        previous = fact.level
        fact.level = level
        if args.value is not None:
            fact.value = _parse_value(args.value)

    save_profile(profile, resolve_data_dir(owner) / FACTS_FILENAME)
    payload = {
        "owner": owner,
        "fact": key,
        "value": _jsonable(fact.value),
        "level": fact.level.value,
        "previous_level": previous.value if previous is not None else None,
        "created": previous is None,
    }
    if previous is None:
        text = f"created {key} at {fact.level.value}: {format_value(fact.value)}"
    elif previous is fact.level:
        text = f"{key}: {fact.level.value} ({format_value(fact.value)})"
    else:
        text = f"{key}: {previous.value} → {fact.level.value} ({format_value(fact.value)})"
    return context.emit(payload, text)


def _parse_level(raw: str, *, viewer: bool) -> Level:
    try:
        level = Level(raw.strip().lower())
    except ValueError:
        allowed = VIEWER_LEVEL_NAMES if viewer else FACT_LEVEL_NAMES
        raise CliError(f"unknown level {raw!r} (expected {allowed})") from None
    if viewer and not level.is_viewer:
        raise CliError(f"a trust level must be {VIEWER_LEVEL_NAMES}, not {raw!r}")
    if not viewer and not level.is_fact_tag:
        raise CliError(f"a fact level must be {FACT_LEVEL_NAMES}, not {raw!r}")
    return level


def _parse_value(text: str) -> Any:
    """Keep plain text as a string; read lists and mappings as YAML."""
    if text.strip()[:1] in ("[", "{"):
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise CliError(f"--value is not valid YAML: {exc}") from None
    return text


# ---------------------------------------------------------------------------
# cal add
# ---------------------------------------------------------------------------


def _cmd_cal_add(context: Context, args: argparse.Namespace) -> int:
    owner = context.owner()
    profile = load_profile(owner)
    if args.at.strip() != "@":
        raise CliError(
            'put "@" between the title and the place, e.g. 2h "Bowling + dinner" @ "Smaaash"'
        )

    start = _parse_start(args.start)
    duration = _parse_duration(args.duration)
    title = _parse_title(args.title)
    place = _parse_place(args.place)
    event_id = _parse_event_id(args.event_id) if args.event_id else None

    block = add_event(profile.calendar_path, start, duration, title, place, uid=event_id)
    payload = {
        "owner": owner,
        "id": event_id,
        "start": block.start.isoformat(),
        "end": block.end.isoformat(),
        "title": block.title,
        "place": place,
        "calendar": str(profile.calendar_path),
    }
    text = (
        f"{event_id or 'event'}  {block.start:%a %b} {block.start.day}, "
        f"{block.start:%H:%M}–{block.end:%H:%M}  {block.title} @ {place}"
    )
    return context.emit(payload, text)


def _parse_start(text: str) -> datetime:
    settings = {
        "TIMEZONE": TIME_ZONE.key,
        "RETURN_AS_TIMEZONE_AWARE": True,
        "PREFER_DATES_FROM": "future",
    }
    try:
        parsed = dateparser.parse(text, settings=settings)
    except (OverflowError, TypeError, ValueError):
        parsed = None
    if parsed is None:
        raise CliError(f"could not read the start {text!r} (try 2026-11-08T21:00 or Sun 9pm)")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TIME_ZONE)
    return parsed.astimezone(TIME_ZONE)


def _parse_duration(text: str) -> timedelta:
    match = _DURATION_RE.fullmatch(text)
    if not match or (not match["hours"] and not match["minutes"]):
        raise CliError(f"could not read the duration {text!r} (try 2h, 90m or 1h30m)")
    minutes = round(float(match["hours"] or 0) * 60 + float(match["minutes"] or 0))
    if minutes < 1 or minutes > 24 * 60:
        raise CliError("a duration must be between 1 minute and 24 hours")
    return timedelta(minutes=minutes)


def _parse_title(value: str) -> str:
    title = value.strip()
    if not title:
        raise CliError("an event needs a title")
    if len(title) > MAX_TITLE:
        raise CliError(f"a title must be {MAX_TITLE} characters or fewer")
    if any(char in title for char in _TITLE_FORBIDDEN):
        raise CliError("a title cannot contain quotes, @ or line breaks")
    return title


def _parse_place(value: str) -> str:
    place = value.strip()
    if not place:
        raise CliError("an event needs a place")
    if len(place) > MAX_PLACE:
        raise CliError(f"a place must be {MAX_PLACE} characters or fewer")
    if not _PLACE_RE.fullmatch(place):
        raise CliError("a place may only contain letters, digits, spaces and , . ' & -")
    return place


def _parse_event_id(value: str) -> str:
    event_id = value.strip()
    if not event_id:
        raise CliError("--id cannot be empty")
    return event_id.upper() if _PROPOSAL_ID_RE.fullmatch(event_id) else event_id


# ---------------------------------------------------------------------------
# view-as
# ---------------------------------------------------------------------------


def _cmd_view_as(context: Context, args: argparse.Namespace) -> int:
    from trustnet.gate import fact_changes

    fact_changes.recover(context.owner())
    owner = context.owner()
    profile = load_profile(owner)
    trust = load_trust(owner)
    if args.days <= 0:
        raise CliError("--days must be a positive number")
    from trustnet.gate.surprise import claims

    result = view_as(profile, trust, args.person_name, days=args.days, claims=claims(owner))

    payload = {
        "owner": owner,
        "person": result.person,
        "level": result.level.value if result.level is not None else None,
        "facts": [
            {"name": row.name, "visible": row.visible, "value": _jsonable(row.value)}
            for row in result.rows
        ],
        "calendar": [
            {"start": row.start.isoformat(), "end": row.end.isoformat(), "title": row.title}
            for row in result.calendar
        ],
        "titles_visible": result.titles_visible,
        "window": {
            "start": result.window[0].isoformat(),
            "end": result.window[1].isoformat(),
        },
        "days": result.days,
    }
    return context.emit(payload, result.render())


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def _jsonable(value: Any) -> Any:
    """Turn a YAML value into something ``json`` accepts, keeping its shape."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return str(value)


def _cmd_dm(context, args):
    import asyncio

    from trustnet.tn.personal import dm_operate

    result = asyncio.run(dm_operate(context.owner(), args.room, getattr(args, "text", None)))
    return context.emit(result, json.dumps(result, ensure_ascii=False))


def _cmd_gift(context, args):
    import asyncio

    from trustnet.tn import personal

    if args.command == "gift-ideas":
        result = asyncio.run(
            personal.gift_ideas(context.owner(), args.friend, args.occasion, args.date, args.budget)
        )
    else:
        result = asyncio.run(personal.claim(context.owner(), args.friend, args.item))
    return context.emit(result, json.dumps(result, ensure_ascii=False))


def _cmd_mcp(context, args):
    from trustnet.tn import mcp

    return mcp.main(["--as", context.owner()])


def _cmd_wake(context, args):
    from trustnet.tn import wake

    return wake.main(context.owner(), args)


def _cmd_personal(context, args):
    import asyncio

    from trustnet.tn import personal

    values = {
        "inbox": (),
        "watch": (),
        "ask-around": (getattr(args, "question", None),),
        "answer": (getattr(args, "id", None), getattr(args, "text", None)),
        "dm": (getattr(args, "friend", None), getattr(args, "goal", None)),
    }
    if args.command == "ask-around":
        audience = _audience_option(getattr(args, "to", None))
        result = asyncio.run(
            personal.ask_around(context.owner(), values["ask-around"][0], audience=audience)
        )
    else:
        result = asyncio.run(
            getattr(personal, args.command.replace("-", "_"))(
                context.owner(), *values[args.command]
            )
        )
    return context.emit(result, json.dumps(result, ensure_ascii=False))


def _audience_option(values: list[str] | None) -> list[str] | None:
    """Turn repeated/comma-separated ``--to`` values into one audience list."""
    if values is None:
        return None
    names: list[str] = []
    for value in values:
        for name in value.replace(" ", ",").split(","):
            if name.strip():
                names.append(name.strip())
    return names


if __name__ == "__main__":
    sys.exit(main())
