"""Trust lists and personal facts, loaded from and saved to YAML.

Every gate module works with the typed objects in this module, never with raw
YAML: a :class:`Level` decides what a room may see, a :class:`Profile` holds the
owner's facts, and a :class:`TrustList` holds the owner's levels for friends.

Data lives in ``TN_DATA_DIR/<person>/`` when that environment variable is set,
otherwise in ``examples/<person>/`` at the repository root. The default is
resolved from this file's location, not from the current directory, so commands
behave the same wherever they are run from.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, Literal

import yaml

__all__ = [
    "ASK_AROUND_ROUTES",
    "AskAroundRoute",
    "FACTS_FILENAME",
    "Fact",
    "FactsError",
    "Level",
    "PersonPermissions",
    "Profile",
    "TrustList",
    "TRUST_FILENAME",
    "field_key",
    "load_profile",
    "load_profile_file",
    "load_trust",
    "load_trust_file",
    "resolve_data_dir",
    "save_profile",
    "save_trust",
]

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
EXAMPLES_DIR: Final = REPO_ROOT / "examples"
TRUST_FILENAME: Final = "trust.yaml"
FACTS_FILENAME: Final = "facts.yaml"

ConsentMode = Literal["direct", "via-agent"]
CONSENT_MODES: Final[frozenset[str]] = frozenset({"direct", "via-agent"})

#: How a friend's ask-around reaches this owner: their agent, the person
#: directly, or nobody at all.
AskAroundRoute = Literal["agent", "person", "off"]
ASK_AROUND_ROUTES: Final[frozenset[str]] = frozenset({"agent", "person", "off"})

_PERSON_RE: Final = re.compile(r"[a-z0-9][a-z0-9_-]*")
_FIELD_RE: Final = re.compile(r"[a-z][a-z0-9_-]{0,63}")


class FactsError(ValueError):
    """A profile, trust list or calendar file is missing or malformed."""


class Level(StrEnum):
    """Ordered trust levels, plus the owner's own view.

    ``acquaintance < friend < close < private``. A room sits at one of the first
    three, a fact may also be tagged ``private`` (never shared), and ``self`` is
    the view used when only the owner and the owner's own agents are present.
    """

    ACQUAINTANCE = "acquaintance"
    FRIEND = "friend"
    CLOSE = "close"
    PRIVATE = "private"
    SELF = "self"

    @property
    def rank(self) -> int:
        return _RANKS[self]

    @property
    def is_viewer(self) -> bool:
        """Whether a room can be at this level."""
        return self in VIEWER_LEVELS

    @property
    def is_fact_tag(self) -> bool:
        """Whether a fact may carry this level."""
        return self in FACT_LEVELS

    def __lt__(self, other: object) -> bool:
        if isinstance(other, Level):
            return self.rank < other.rank
        return NotImplemented

    def __le__(self, other: object) -> bool:
        if isinstance(other, Level):
            return self.rank <= other.rank
        return NotImplemented

    def __gt__(self, other: object) -> bool:
        if isinstance(other, Level):
            return self.rank > other.rank
        return NotImplemented

    def __ge__(self, other: object) -> bool:
        if isinstance(other, Level):
            return self.rank >= other.rank
        return NotImplemented


_RANKS: Final[dict[Level, int]] = {
    Level.ACQUAINTANCE: 0,
    Level.FRIEND: 1,
    Level.CLOSE: 2,
    Level.PRIVATE: 3,
    Level.SELF: 4,
}
VIEWER_LEVELS: Final[frozenset[Level]] = frozenset({Level.ACQUAINTANCE, Level.FRIEND, Level.CLOSE})
FACT_LEVELS: Final[frozenset[Level]] = frozenset(
    {Level.ACQUAINTANCE, Level.FRIEND, Level.CLOSE, Level.PRIVATE}
)


@dataclass(slots=True)
class Fact:
    """One preference, possession or recommendation, tagged with its level."""

    value: Any
    level: Level

    def __post_init__(self) -> None:
        if not isinstance(self.level, Level) or not self.level.is_fact_tag:
            raise FactsError(f"a fact level must be one of {_names(FACT_LEVELS)}")


@dataclass(slots=True)
class Profile:
    """A person's facts and the calendar that belongs to them."""

    owner: str
    facts: dict[str, Fact]
    calendar_path: Path


def field_key(name: str) -> str:
    """Normalize a fact field name used in a per-person permission."""
    if not isinstance(name, str):
        raise FactsError(f"a fact field must be a name, not {name!r}")
    key = name.strip().lower()
    if not _FIELD_RE.fullmatch(key):
        raise FactsError(
            f"invalid fact field {name!r} (use lowercase letters, digits, _ and -, starting "
            "with a letter)"
        )
    return key


@dataclass(slots=True)
class PersonPermissions:
    """Per-person field overrides and disclosure preferences.

    ``allow`` adds a field that the person's trust level would not show.
    ``deny`` hides a field the level would show. A deny wins over an allow, and
    neither can expose a fact tagged ``private``. ``calendar_titles`` is a
    separate opt-in: event titles stay blank for friends until it is set.
    ``ask_around`` chooses who hears a friend's question: this owner's agent
    (the default), the person directly, or nobody.
    """

    allow: set[str] = field(default_factory=set)
    deny: set[str] = field(default_factory=set)
    calendar_titles: bool = False
    ask_around: AskAroundRoute = "agent"

    def __post_init__(self) -> None:
        if isinstance(self.allow, str) or isinstance(self.deny, str):
            raise FactsError("allow and deny must be lists of fact field names")
        object.__setattr__(self, "allow", {field_key(name) for name in self.allow})
        object.__setattr__(self, "deny", {field_key(name) for name in self.deny})
        if not isinstance(self.calendar_titles, bool):
            raise FactsError("calendar_titles must be true or false")
        if self.ask_around not in ASK_AROUND_ROUTES:
            raise FactsError(f"ask_around must be one of: {', '.join(sorted(ASK_AROUND_ROUTES))}")

    def is_default(self) -> bool:
        return (
            not self.allow
            and not self.deny
            and not self.calendar_titles
            and self.ask_around == "agent"
        )


@dataclass(slots=True)
class TrustList:
    """Who an owner trusts, how consent is given, and which envoy speaks for them."""

    people: dict[str, Level] = field(default_factory=dict)
    consent_default: ConsentMode = "direct"
    envoy_provider: str = ""
    envoy_machine: str = ""
    envoy_model: str = ""  # provider model id; "" = the provider's default
    permissions: dict[str, PersonPermissions] = field(default_factory=dict)
    blocked: list[str] = field(default_factory=list)

    def level_for(self, person: str) -> Level | None:
        key = _person_key(person)
        if key in self.blocked:
            return None
        return self.people.get(key)

    def permissions_for(self, person: str) -> PersonPermissions:
        """The person's explicit permissions, or the defaults when none are set."""
        return self.permissions.get(_person_key(person), PersonPermissions())

    def is_blocked(self, person: str) -> bool:
        return _person_key(person) in self.blocked

    def block(self, person: str) -> str:
        """Remove a person and remember the block until an explicit unblock."""
        key = _person_key(person)
        self.people.pop(key, None)
        self.permissions.pop(key, None)
        if key not in self.blocked:
            self.blocked.append(key)
        return key

    def unblock(self, person: str) -> str:
        """Lift a block without re-adding the person to the trust list."""
        key = _person_key(person)
        if key in self.blocked:
            self.blocked.remove(key)
        return key

    def grant(self, person: str, level: Level) -> str:
        """Add or raise a person's level, refusing a still-blocked person."""
        key = _person_key(person)
        if key in self.blocked:
            raise FactsError(f"{key} is blocked; run `tn unblock {key}` first")
        self.people[key] = level
        return key


def _names(levels: frozenset[Level]) -> str:
    return ", ".join(level.value for level in sorted(levels))


def _person_key(person: str) -> str:
    if not isinstance(person, str):
        raise FactsError(f"a person must be a name, not {person!r}")
    key = person.strip().lower()
    if not _PERSON_RE.fullmatch(key):
        raise FactsError(f"invalid person name {person!r}")
    return key


def resolve_data_dir(person: str) -> Path:
    """Return the directory holding a person's files.

    ``TN_DATA_DIR/<person>/`` when the variable is set; otherwise
    ``examples/<person>/`` under the repository root. An installed wheel has no
    repository, so it asks for ``TN_DATA_DIR`` instead of reporting a missing
    file under the virtualenv.
    """
    key = _person_key(person)
    base = os.environ.get("TN_DATA_DIR")
    if base:
        return Path(base).expanduser().resolve() / key
    if not EXAMPLES_DIR.is_dir():
        raise FactsError(
            "no data directory: set TN_DATA_DIR to the directory holding each person's "
            "trust.yaml, facts.yaml and calendar.ics (create a profile with "
            "`TN_DATA_DIR=... tn --as om init`), or run inside a trust-network checkout"
        )
    return EXAMPLES_DIR / key


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FactsError(f"{path}: file not found") from None
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise FactsError(f"{path}: invalid YAML: {exc}") from None
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise FactsError(f"{path}: expected a mapping at the top level")
    return raw


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    from trustnet.gate.storage import atomic_write

    atomic_write(path, text)


def _check_keys(mapping: dict[Any, Any], allowed: frozenset[str], where: str) -> None:
    unknown = [key for key in mapping if key not in allowed]
    if unknown:
        found = ", ".join(repr(key) for key in unknown)
        raise FactsError(f"{where}: unknown key(s) {found} (allowed: {', '.join(sorted(allowed))})")


def _parse_level(raw: Any, allowed: frozenset[Level], where: str) -> Level:
    if not isinstance(raw, str):
        raise FactsError(f"{where}: expected a level name, got {raw!r}")
    try:
        level = Level(raw.strip().lower())
    except ValueError:
        raise FactsError(
            f"{where}: unknown level {raw!r} (expected one of: {_names(allowed)})"
        ) from None
    if level not in allowed:
        raise FactsError(
            f"{where}: level {raw!r} is not allowed here (expected one of: {_names(allowed)})"
        )
    return level


def load_trust_file(path: str | Path) -> TrustList:
    """Load ``trust.yaml`` from an explicit path."""
    path = Path(path)
    data = _read_yaml(path)
    _check_keys(
        data,
        frozenset({"people", "consent", "envoy", "permissions", "blocked"}),
        str(path),
    )

    people_raw = data.get("people") or {}
    if not isinstance(people_raw, dict):
        raise FactsError(f"{path}: 'people' must be a mapping of person to level")
    people: dict[str, Level] = {}
    for name, raw_level in people_raw.items():
        key = _person_key(name)
        people[key] = _parse_level(raw_level, VIEWER_LEVELS, f"{path}: people.{key}")

    consent_raw = data.get("consent") or {}
    if not isinstance(consent_raw, dict):
        raise FactsError(f"{path}: 'consent' must be a mapping")
    _check_keys(consent_raw, frozenset({"default"}), f"{path}: consent")
    consent_default = consent_raw.get("default", "direct")
    if consent_default not in CONSENT_MODES:
        raise FactsError(
            f"{path}: consent.default must be one of: {', '.join(sorted(CONSENT_MODES))}"
        )

    envoy_raw = data.get("envoy") or {}
    if not isinstance(envoy_raw, dict):
        raise FactsError(f"{path}: 'envoy' must be a mapping")
    _check_keys(envoy_raw, frozenset({"provider", "machine", "model"}), f"{path}: envoy")
    provider = envoy_raw.get("provider", "")
    machine = envoy_raw.get("machine", "")
    model = envoy_raw.get("model", "")
    for key, value in (("provider", provider), ("machine", machine), ("model", model)):
        if not isinstance(value, str):
            raise FactsError(f"{path}: envoy.{key} must be a string")

    blocked_raw = data.get("blocked") or []
    if not isinstance(blocked_raw, list):
        raise FactsError(f"{path}: 'blocked' must be a list of person names")
    blocked: list[str] = []
    for name in blocked_raw:
        key = _person_key(name)
        if key not in blocked:
            blocked.append(key)

    permissions_raw = data.get("permissions") or {}
    if not isinstance(permissions_raw, dict):
        raise FactsError(f"{path}: 'permissions' must be a mapping of person to permissions")
    permissions: dict[str, PersonPermissions] = {}
    for name, entry in permissions_raw.items():
        key = _person_key(name)
        where = f"{path}: permissions.{key}"
        if not isinstance(entry, dict):
            raise FactsError(f"{where}: expected a mapping")
        _check_keys(entry, frozenset({"allow", "deny", "calendar_titles", "ask_around"}), where)
        allow = entry.get("allow") or []
        deny = entry.get("deny") or []
        if not isinstance(allow, list) or not isinstance(deny, list):
            raise FactsError(f"{where}: 'allow' and 'deny' must be lists of field names")
        calendar_titles = entry.get("calendar_titles", False)
        if not isinstance(calendar_titles, bool):
            raise FactsError(f"{where}: 'calendar_titles' must be true or false")
        ask_around = entry.get("ask_around", "agent")
        if ask_around not in ASK_AROUND_ROUTES:
            raise FactsError(
                f"{where}: ask_around must be one of: {', '.join(sorted(ASK_AROUND_ROUTES))}"
            )
        permissions[key] = PersonPermissions(
            allow={field_key(name) for name in allow},
            deny={field_key(name) for name in deny},
            calendar_titles=calendar_titles,
            ask_around=ask_around,
        )

    return TrustList(
        people=people,
        consent_default=consent_default,
        envoy_provider=provider.strip(),
        envoy_machine=machine.strip(),
        envoy_model=model.strip(),
        permissions=permissions,
        blocked=blocked,
    )


def save_trust(trust: TrustList, path: str | Path) -> None:
    """Write a trust list. Key order is kept; YAML comments are not."""
    blocked = list(dict.fromkeys(trust.blocked))
    payload: dict[str, Any] = {
        "people": {
            name: level.value for name, level in trust.people.items() if name not in blocked
        },
    }
    if blocked:
        payload["blocked"] = blocked
    permissions: dict[str, Any] = {}
    for name, entry in trust.permissions.items():
        if name in blocked or entry.is_default():
            continue
        value: dict[str, Any] = {}
        if entry.allow:
            value["allow"] = sorted(entry.allow)
        if entry.deny:
            value["deny"] = sorted(entry.deny)
        if entry.calendar_titles:
            value["calendar_titles"] = True
        if entry.ask_around != "agent":
            value["ask_around"] = entry.ask_around
        if value:
            permissions[name] = value
    if permissions:
        payload["permissions"] = permissions
    payload["consent"] = {"default": trust.consent_default}
    payload["envoy"] = {
        "provider": trust.envoy_provider,
        "machine": trust.envoy_machine,
    }
    if trust.envoy_model:
        payload["envoy"]["model"] = trust.envoy_model
    _write_yaml(Path(path), payload)


def load_trust(person: str) -> TrustList:
    """Load a person's ``trust.yaml`` from their data directory."""
    return load_trust_file(resolve_data_dir(person) / TRUST_FILENAME)


def load_profile_file(path: str | Path) -> Profile:
    """Load ``facts.yaml`` from an explicit path."""
    path = Path(path)
    data = _read_yaml(path)
    _check_keys(data, frozenset({"calendar", "facts"}), str(path))

    calendar_raw = data.get("calendar")
    if not isinstance(calendar_raw, str) or not calendar_raw.strip():
        raise FactsError(f"{path}: 'calendar' must be a path to an .ics file")
    calendar_path = (path.parent / calendar_raw.strip()).resolve()
    if not calendar_path.is_file():
        raise FactsError(f"{path}: calendar file not found: {calendar_path}")

    facts_raw = data.get("facts") or {}
    if not isinstance(facts_raw, dict):
        raise FactsError(f"{path}: 'facts' must be a mapping of key to fact")
    facts: dict[str, Fact] = {}
    for key, entry in facts_raw.items():
        if not isinstance(key, str) or not key.strip():
            raise FactsError(f"{path}: fact keys must be non-empty strings")
        where = f"{path}: facts.{key}"
        if not isinstance(entry, dict):
            raise FactsError(f"{where}: expected 'value' and 'level'")
        _check_keys(entry, frozenset({"value", "level"}), where)
        if "value" not in entry:
            raise FactsError(f"{where}: missing 'value'")
        if "level" not in entry:
            raise FactsError(f"{where}: missing 'level'")
        facts[key.strip()] = Fact(
            value=entry["value"],
            level=_parse_level(entry["level"], FACT_LEVELS, where),
        )

    return Profile(
        owner=path.parent.name,
        facts=facts,
        calendar_path=calendar_path,
    )


def save_profile(profile: Profile, path: str | Path) -> None:
    """Write a profile. Key order is kept; YAML comments are not.

    The calendar is written relative to the profile file when it lives in the
    same directory, and absolute otherwise.
    """
    path = Path(path)
    calendar_path = Path(profile.calendar_path)
    try:
        relative = calendar_path.resolve().relative_to(path.resolve().parent)
    except ValueError:
        calendar_value = str(calendar_path)
    else:
        calendar_value = f"./{relative.as_posix()}"

    payload: dict[str, Any] = {
        "calendar": calendar_value,
        "facts": {
            key: {"value": fact.value, "level": fact.level.value}
            for key, fact in profile.facts.items()
        },
    }
    _write_yaml(path, payload)


def load_profile(person: str) -> Profile:
    """Load a person's ``facts.yaml`` from their data directory.

    The owner is the person's name from the data directory, so a copy under
    ``TN_DATA_DIR`` reports the same owner as the committed fixture.
    """
    directory = resolve_data_dir(person)
    profile = load_profile_file(directory / FACTS_FILENAME)
    profile.owner = _person_key(person)
    return profile
