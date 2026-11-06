"""The trust policy: what a room may learn, and who may command the gate.

This is the security core, so the module is pure: it takes typed inputs and
returns decisions. It never reads a message body, never calls Switch and never
touches a file. Callers resolve room membership and sender identity from Switch
metadata (``list_participants``, ``get_agent_detail``) and pass them in; text
from a message is data, never an identity.

``PLAN.md`` §3 lives here:

- :func:`visible_facts` and :func:`calendar_view` are the levels/facts table.
- :func:`room_level` is Rule 1: the lowest level the owner gives anyone in the
  room, and ``None`` (the gate stays silent) when someone is not on the list.
- :func:`authorize` is Rule 2: consent is judged by the sender's Switch
  identity, so it cannot be faked.
- :func:`can_set_level` is Rule 3: agents only tighten, the owner may loosen.

Command names are PLAN.md's names (``"yes"``, ``"ask-around"``, ...), exported
as sets so the parser and the gate runtime can map parsed commands onto them.
``ask-around`` is the one name that means two things: pass
:data:`Direction.INBOUND` for the cross-boundary form, which arrives from
another gate.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Literal

from trustnet.gate.calendar import Block
from trustnet.gate.facts import CONSENT_MODES, ConsentMode, FactsError, Level, Profile, TrustList

__all__ = [
    "Actor",
    "Allowed",
    "CROSS_BOUNDARY_COMMANDS",
    "Decision",
    "DecisionMode",
    "DenialCode",
    "Denied",
    "Direction",
    "Identity",
    "KNOWN_COMMANDS",
    "OWNER_AGENT_COMMANDS",
    "OWNER_COMMANDS",
    "OWNER_DIRECT_COMMANDS",
    "OWNER_ONLY_COMMANDS",
    "PolicyError",
    "SenderKind",
    "authorize",
    "calendar_view",
    "can_set_level",
    "fact_is_visible",
    "room_level",
    "visible_facts",
]

# Commands that carry the owner's consent. Rule 2: the owner's Switch user, or
# the owner's registered personal agent when consent.default is "via-agent".
OWNER_DIRECT_COMMANDS: Final[frozenset[str]] = frozenset({"yes", "no", "answer"})

# Commands only the owner's Switch user may use, never an agent.
OWNER_ONLY_COMMANDS: Final[frozenset[str]] = frozenset({"trust", "view-as", "ledger"})

# Commands the owner or any of the owner's own agents may use (outbound form).
OWNER_AGENT_COMMANDS: Final[frozenset[str]] = frozenset({"dm", "ask-around"})

# Commands another gate may send; the handler applies the room level.
CROSS_BOUNDARY_COMMANDS: Final[frozenset[str]] = frozenset(
    {"free", "ask", "ask-owner", "propose", "counter", "gift-ideas", "claim", "ask-around"}
)

OWNER_COMMANDS: Final[frozenset[str]] = (
    OWNER_DIRECT_COMMANDS | OWNER_ONLY_COMMANDS | OWNER_AGENT_COMMANDS
)
KNOWN_COMMANDS: Final[frozenset[str]] = (
    OWNER_COMMANDS | CROSS_BOUNDARY_COMMANDS | {"join-dm", "consent", "around-reply", "hello"}
)

DecisionMode = Literal["direct", "via-agent", "cross-boundary"]


class PolicyError(ValueError):
    """An argument to the policy is malformed; the caller has a bug."""


class SenderKind(StrEnum):
    """Whether a sender is a Switch user or an agent acting for its owner."""

    USER = "user"
    AGENT = "agent"


class Direction(StrEnum):
    """Where a command came from, for the names that mean two things."""

    OUTBOUND = "outbound"  # the owner's side sends it
    INBOUND = "inbound"  # another gate sends it across the boundary


class Actor(StrEnum):
    """Who edits a fact: the owner by hand, or an agent."""

    OWNER = "owner"
    AGENT = "agent"


class DenialCode(StrEnum):
    """Stable reason codes, safe to log and to test against."""

    UNKNOWN_COMMAND = "unknown-command"
    NOT_OWNER = "not-owner"
    NOT_OWNER_AGENT = "not-owner-agent"
    CONSENT_MODE = "consent-mode"
    OWNER_COMMAND = "owner-command"


@dataclass(frozen=True, slots=True)
class Identity:
    """A sender as reported by Switch, never as claimed by a message.

    A user acts for themselves. An agent acts for its owner: ``owner_id`` comes
    from ``get_agent_detail``. ``owner_id=None`` means Switch did not report an
    owner, and every check here fails closed on it.
    """

    kind: SenderKind
    id: str
    owner_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SenderKind):
            raise PolicyError(f"a sender kind must be SenderKind.USER or AGENT, not {self.kind!r}")
        object.__setattr__(self, "id", _name(self.id, "sender id"))
        if self.owner_id is not None:
            object.__setattr__(self, "owner_id", _name(self.owner_id, "agent owner id"))

    @property
    def person(self) -> str | None:
        """The person this sender acts as, or ``None`` for an ownerless agent."""
        if self.kind is SenderKind.USER:
            return _key(self.id)
        return None if self.owner_id is None else _key(self.owner_id)

    @classmethod
    def user(cls, id: str) -> Identity:
        """A Switch user acting for themselves."""
        return cls(SenderKind.USER, id)

    @classmethod
    def agent(cls, id: str, owner_id: str | None = None) -> Identity:
        """An agent acting for ``owner_id``, as ``get_agent_detail`` reports it."""
        return cls(SenderKind.AGENT, id, owner_id)


@dataclass(frozen=True, slots=True)
class Allowed:
    """The command may run; ``mode`` says how the sender was accepted."""

    mode: DecisionMode

    def __post_init__(self) -> None:
        if self.mode not in ("direct", "via-agent", "cross-boundary"):
            raise PolicyError(f"unknown decision mode {self.mode!r}")

    @property
    def allowed(self) -> bool:
        return True

    def __bool__(self) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class Denied:
    """The command must not run; the gate stays silent and logs the reason."""

    code: DenialCode
    reason: str

    @property
    def allowed(self) -> bool:
        return False

    def __bool__(self) -> bool:
        return False


Decision = Allowed | Denied


def visible_facts(profile: Profile, level: Level) -> dict[str, Any]:
    """Return the facts a room at ``level`` may see, as ``{name: value}``.

    The §3 table: ``acquaintance`` facts at every level, ``friend`` at friend
    and close, ``close`` at close only, ``private`` never. ``self`` (the owner
    and the owner's own agents alone) sees every fact. Values are copies, so a
    caller cannot mutate the profile through the result.
    """
    _check_view_level(level)
    return {
        name: copy.deepcopy(fact.value)
        for name, fact in profile.facts.items()
        if fact_is_visible(fact.level, level)
    }


def fact_is_visible(fact_level: Level, level: Level) -> bool:
    """Whether a fact tagged ``fact_level`` is shared in a room at ``level``."""
    _check_view_level(level)
    if not isinstance(fact_level, Level) or not fact_level.is_fact_tag:
        raise PolicyError(f"a fact tag must be a fact level, not {fact_level!r}")
    if level is Level.SELF:
        return True
    return fact_level.rank <= level.rank


def calendar_view(blocks: Iterable[Block], level: Level) -> list[Block]:
    """Return ``blocks`` as a room at ``level`` may see them.

    Busy times are visible at every level; event titles only at friend and
    close (and to the owner). At acquaintance each block keeps its times and
    loses its title.
    """
    _check_view_level(level)
    if level is Level.ACQUAINTANCE:
        return [Block(block.start, block.end, "") for block in blocks]
    return list(blocks)


def room_level(owner: str, participants: Iterable[Identity], trust: TrustList) -> Level | None:
    """Return the level a room sits at for ``owner`` (Rule 1).

    ``participants`` are the room's humans and agents with the owners Switch
    reports. The owner and the owner's own agents are skipped; the room sits at
    the lowest level the owner gives any remaining person. An agent whose owner
    Switch did not report, or anyone not on the trust list, gives ``None``: the
    gate stays silent rather than guessing. A room holding only the owner and
    the owner's own agents sits at ``self``.
    """
    owner_key = _key(_name(owner, "owner"))
    lowest: Level | None = None
    for participant in participants:
        if not isinstance(participant, Identity):
            raise PolicyError(f"a participant must be an Identity, not {participant!r}")
        person = participant.person
        if person is None:
            return None  # an agent with no owner: fail closed
        if person == owner_key:
            continue
        try:
            level = trust.level_for(person)
        except FactsError:
            return None  # not a name the trust list can hold: treat as a stranger
        if level is None:
            return None
        if lowest is None or level.rank < lowest.rank:
            lowest = level
    return Level.SELF if lowest is None else lowest


def authorize(
    command: str,
    sender: Identity,
    owner: str,
    consent_mode: ConsentMode,
    personal_agents: Iterable[str] = (),
    direction: Direction = Direction.OUTBOUND,
    room_name: str = "",
) -> Decision:
    """Decide whether ``sender`` may run ``command`` for ``owner`` (Rule 2).

    ``command`` is PLAN.md's command name, never raw message text. ``sender``
    is resolved from Switch metadata before the call, so a message that claims
    "from Om" changes nothing. ``personal_agents`` are the agent ids the owner
    registered as their own voice (e.g. Rahul's Hermes); they may carry consent
    only when ``consent_mode`` is ``"via-agent"``.

    Owner consent (``yes``, ``no``, ``answer``) is ``Allowed("direct")`` from
    the owner's Switch user and ``Allowed("via-agent")`` from a registered
    personal agent in via-agent mode. ``trust``, ``view-as`` and ``ledger`` are
    the owner's user only. ``dm`` and outbound ``ask-around`` also accept the
    owner's own agents. Cross-boundary commands are allowed for any sender and
    return ``Allowed("cross-boundary")``; the handler applies the room level.
    """
    name = _command_name(command)
    if not isinstance(sender, Identity):
        raise PolicyError(f"a sender must be an Identity, not {sender!r}")
    owner_key = _key(_name(owner, "owner"))
    if consent_mode not in CONSENT_MODES:
        raise PolicyError(
            f"consent mode must be one of {sorted(CONSENT_MODES)}, not {consent_mode!r}"
        )
    if not isinstance(direction, Direction):
        raise PolicyError(f"direction must be a Direction, not {direction!r}")

    if name not in KNOWN_COMMANDS:
        return Denied(DenialCode.UNKNOWN_COMMAND, f"unknown command {name!r}")

    if name in {"join-dm", "consent", "around-reply", "hello"}:
        pair = "-".join(sorted((owner_key, sender.person or "")))
        if (
            sender.kind is SenderKind.AGENT
            and sender.person != owner_key
            and sender.id == f"{sender.person}-gate"
            and (
                room_name == f"conn-{pair}"
                or (name == "consent" and room_name.startswith(f"dm-{pair}-"))
            )
        ):
            return Allowed("cross-boundary")
        return Denied(DenialCode.NOT_OWNER_AGENT, "gate relay requires the matching connection")

    if direction is Direction.INBOUND:
        if name in OWNER_DIRECT_COMMANDS or name in OWNER_ONLY_COMMANDS or name == "dm":
            return Denied(
                DenialCode.OWNER_COMMAND,
                f"{name} is an owner command and is never accepted across the boundary",
            )
        return Allowed("cross-boundary")

    if name in OWNER_ONLY_COMMANDS:
        if _is_owner_user(sender, owner_key):
            return Allowed("direct")
        return Denied(DenialCode.NOT_OWNER, f"{name} is accepted only from the owner's Switch user")

    if name in OWNER_DIRECT_COMMANDS:
        return _consent(sender, owner_key, consent_mode, personal_agents, name)

    if name in OWNER_AGENT_COMMANDS:
        if _is_owner_user(sender, owner_key):
            return Allowed("direct")
        if _is_owner_agent(sender, owner_key):
            return Allowed("via-agent")
        return _not_owner(sender, name, "is accepted only from the owner or the owner's own agents")

    return Allowed("cross-boundary")


def can_set_level(old: Level, new: Level, actor: Actor) -> bool:
    """Whether ``actor`` may retag a fact from ``old`` to ``new`` (Rule 3).

    Tightening means moving toward ``private``, so fewer people see the fact.
    An agent may only tighten or leave the level alone; the owner editing by
    hand may loosen it.
    """
    for level in (old, new):
        if not isinstance(level, Level) or not level.is_fact_tag:
            raise PolicyError(f"a fact level must be a fact tag, not {level!r}")
    if not isinstance(actor, Actor):
        raise PolicyError(f"actor must be Actor.OWNER or Actor.AGENT, not {actor!r}")
    if actor is Actor.OWNER:
        return True
    return new.rank >= old.rank


def _consent(
    sender: Identity,
    owner_key: str,
    consent_mode: ConsentMode,
    personal_agents: Iterable[str],
    command: str,
) -> Decision:
    """Rule 2 for the commands that carry the owner's consent."""
    if _is_owner_user(sender, owner_key):
        return Allowed("direct")
    if sender.kind is not SenderKind.AGENT or sender.owner_id is None:
        return _not_owner(
            sender, command, "is accepted only from the owner's Switch user or a personal agent"
        )
    if _key(sender.owner_id) != owner_key:
        return _not_owner(sender, command, "came from an agent owned by someone else")
    if _key(sender.id) not in _agent_keys(personal_agents):
        return Denied(
            DenialCode.NOT_OWNER_AGENT,
            f"{command} came from an agent that is not one of the owner's personal agents",
        )
    if consent_mode != "via-agent":
        return Denied(
            DenialCode.CONSENT_MODE,
            f"{command} from an agent needs consent.default: via-agent, not {consent_mode}",
        )
    return Allowed("via-agent")


def _not_owner(sender: Identity, command: str, detail: str) -> Denied:
    """A denial that names who the sender was, without echoing message text."""
    if sender.kind is SenderKind.AGENT:
        return Denied(
            DenialCode.NOT_OWNER_AGENT, f"{command} {detail}; this agent is not the owner's"
        )
    return Denied(DenialCode.NOT_OWNER, f"{command} {detail}")


def _is_owner_user(sender: Identity, owner_key: str) -> bool:
    return sender.kind is SenderKind.USER and _key(sender.id) == owner_key


def _is_owner_agent(sender: Identity, owner_key: str) -> bool:
    return (
        sender.kind is SenderKind.AGENT
        and sender.owner_id is not None
        and _key(sender.owner_id) == owner_key
    )


def _check_view_level(level: Level) -> None:
    """Reject a level a room cannot sit at (``private`` is a fact tag only)."""
    if not isinstance(level, Level) or level is Level.PRIVATE:
        raise PolicyError(
            f"a room level must be acquaintance, friend, close or self, not {level!r}"
        )


def _command_name(command: str) -> str:
    if not isinstance(command, str):
        raise PolicyError(f"a command must be a string, not {command!r}")
    return command.strip().lower()


def _agent_keys(agents: Iterable[str]) -> frozenset[str]:
    keys: set[str] = set()
    for agent in agents:
        if not isinstance(agent, str) or not agent.strip():
            raise PolicyError(f"a personal agent id must be a non-empty string, not {agent!r}")
        keys.add(_key(agent))
    return frozenset(keys)


def _name(value: str, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolicyError(f"a {what} must be a non-empty string, not {value!r}")
    return value.strip()


def _key(value: str) -> str:
    """Normalize a Switch id or person name the way the trust list does."""
    return value.strip().lower()


def share_consent(
    sender: Identity,
    owner: str,
    consent_mode: ConsentMode,
    personal_agents: Iterable[str] = (),
) -> Decision:
    """Fact/trust review carries exactly the same authority as plan consent."""
    return authorize("yes", sender, owner, consent_mode, personal_agents)
