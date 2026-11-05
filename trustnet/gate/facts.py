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
    "FACTS_FILENAME",
    "Fact",
    "FactsError",
    "Level",
    "Profile",
    "TrustList",
    "TRUST_FILENAME",
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

_PERSON_RE: Final = re.compile(r"[a-z0-9][a-z0-9_-]*")


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


@dataclass(slots=True)
class TrustList:
    """Who an owner trusts, how consent is given, and which envoy speaks for them."""

    people: dict[str, Level] = field(default_factory=dict)
    consent_default: ConsentMode = "direct"
    envoy_provider: str = ""
    envoy_machine: str = ""
    envoy_model: str = ""  # provider model id; "" = the provider's default

    def level_for(self, person: str) -> Level | None:
        return self.people.get(_person_key(person))


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

    ``TN_DATA_DIR/<person>/`` when the variable is set, otherwise
    ``examples/<person>/`` under the repository root.
    """
    key = _person_key(person)
    base = os.environ.get("TN_DATA_DIR")
    if base:
        return Path(base).expanduser().resolve() / key
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
    path.write_text(text, encoding="utf-8")


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
    _check_keys(data, frozenset({"people", "consent", "envoy"}), str(path))

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

    return TrustList(
        people=people,
        consent_default=consent_default,
        envoy_provider=provider.strip(),
        envoy_machine=machine.strip(),
        envoy_model=model.strip(),
    )


def save_trust(trust: TrustList, path: str | Path) -> None:
    """Write a trust list. Key order is kept; YAML comments are not."""
    payload: dict[str, Any] = {
        "people": {name: level.value for name, level in trust.people.items()},
        "consent": {"default": trust.consent_default},
        "envoy": {
            "provider": trust.envoy_provider,
            "machine": trust.envoy_machine,
        },
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
