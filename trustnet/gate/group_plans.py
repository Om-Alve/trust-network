"""Authenticated group planning: N-party plans with explicit votes and a durable outbox.

The gate is the only writer. A plan is drafted by the owner's own main agent
through a structured ``plan-request {JSON}`` line in the owner's home. The
coordinator's gate opens a dedicated ``group-<plan-id>`` room and relays an
``offer`` to every other participant's gate. Every participant then votes
explicitly through their own gate; a plan is confirmed only when every recorded
vote is yes for the same immutable random plan id, fingerprint, revision and
participant set.

Security properties enforced here, on top of the runtime's fresh membership and
room-trust checks:

- Only the owner's own main agent may draft or revise a plan.
- Only the owner's Switch user, or their main agent when consent is
  ``via-agent``, may vote or cancel.
- A relay is accepted only from the exact ``<person>-gate`` of a participant,
  and a vote relay may speak only for its own sender.
- Every gate must trust every other participant; unknown and missing identities
  are refused.
- Plan ids are random and never rebound. Fingerprints cover id, revision,
  participant set and content, so stale or replayed relays cannot be applied to
  a different plan.

Calendar integration is delegated: the parent provides
``trustnet.gate.calendar_jobs.queue(person, ref, plan, action=..., uid=...)``,
a synchronous durable local enqueue. This module never writes a provider.
Confirmed and cancelled plans are queued through the same recoverable outbox as
messages, so a crash or a transient failure is retried.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import secrets
import sqlite3
import time
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

from trustnet.gate import relay, storage
from trustnet.gate.dm import main_agent
from trustnet.gate.facts import Level, load_profile, load_trust, resolve_data_dir
from trustnet.gate.policy import SenderKind, combined_permissions, visible_facts
from trustnet.switch_client import SwitchError

LOG = logging.getLogger(__name__)

__all__ = [
    "EXPIRY",
    "handle",
    "identify",
    "pending",
    "projection",
    "queue_calendar",
    "recover",
    "status",
    "summary",
]

DOMAIN = "group-plans"

PLAN_PREFIX = "gp-"
MAX_PARTICIPANTS = 12
MAX_BODY = 20_000
MAX_TITLE = 60
MAX_PLACE = 60
RETRY_SECONDS = 2
EXPIRY = timedelta(days=30)

_PLAN_RE = re.compile(r"gp-[0-9a-f]{16}")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{8,64}")
_PERSON_RE = re.compile(r"[a-z0-9][a-z0-9_-]*")
_PLACE_RE = re.compile(r"[A-Za-z0-9 ,.'&-]+")
_HEX_RE = re.compile(r"[0-9a-f]{64}")
_TITLE_FORBIDDEN = frozenset('\n\r"@')
_SELF_ACTIONS = frozenset({"create", "propose", "revise", "replace"})
_CONSENT_ACTIONS = frozenset({"vote", "cancel"})


class PlanError(ValueError):
    """A plan command or relay is malformed or not allowed."""


def queue_calendar(person, ref, plan, *, action, uid):
    """The parent's durable calendar adapter, imported lazily.

    Tests replace this attribute with a recorder; production code must provide
    ``trustnet.gate.calendar_jobs`` with a synchronous ``queue`` function.
    """
    from trustnet.gate import calendar_jobs

    return calendar_jobs.queue(person, ref, plan, action=action, uid=uid)


# --- public state -----------------------------------------------------------


def load(person):
    state = storage.load(person, DOMAIN)
    state.setdefault("plans", {})
    state.setdefault("tokens", {})
    return state


def save(person, state):
    storage.save(person, DOMAIN, state)


def projection(person):
    """A deep copy of this owner's durable local projection (no writes, no Switch)."""
    return copy.deepcopy(_read_state(person))


def status(person, reference):
    """One plan by immutable id or submitted token, from local state only."""
    plan = _resolve(_read_state(person), reference)
    if plan is None:
        return None
    result = summary(plan)
    trust = load_trust(person)
    viewers = [p for p in plan["participants"] if p != person]
    levels = [trust.level_for(p) for p in viewers]
    result["sharing"] = (
        visible_facts(
            load_profile(person),
            min(levels, key=lambda level: level.rank),
            combined_permissions(trust, viewers),
        )
        if levels and all(level is not None for level in levels)
        else {}
    )
    return result


def pending(person):
    """Plans still waiting for votes, oldest first, from local state only."""
    plans = [
        plan for plan in _read_state(person)["plans"].values() if plan.get("status") == "pending"
    ]
    return [summary(plan) for plan in sorted(plans, key=lambda value: value.get("created_at", 0))]


def _read_state(person):
    """Read the durable projection without writing (agents read, the gate writes)."""
    directory = resolve_data_dir(person)
    path = directory / (DOMAIN + ".json")
    state = {}
    database = directory / "decisions.sqlite3"
    if database.exists():
        try:
            connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
            try:
                row = connection.execute(
                    "SELECT value FROM state WHERE domain=?", (DOMAIN,)
                ).fetchone()
            finally:
                connection.close()
            if row:
                state = json.loads(row[0])
        except (sqlite3.Error, OSError, ValueError):
            state = {}
    if not state and path.exists():
        try:
            state = json.loads(path.read_text())
        except (OSError, ValueError):
            state = {}
    if not isinstance(state, dict):
        state = {}
    state.setdefault("plans", {})
    state.setdefault("tokens", {})
    return state


def summary(plan):
    return {
        "id": plan["id"],
        "uid": plan.get("uid", ""),
        "room": plan.get("room", ""),
        "coordinator": plan.get("coordinator", ""),
        "participants": list(plan.get("participants", [])),
        "revision": plan.get("revision", 0),
        "fingerprint": plan.get("fingerprint", ""),
        "status": plan.get("status", ""),
        "content": copy.deepcopy(plan.get("content", {})),
        "votes": copy.deepcopy(plan.get("votes", {})),
        "confirmed": copy.deepcopy(plan.get("confirmed")),
        "cancelled": copy.deepcopy(plan.get("cancelled")),
        "candidate_declined": bool(plan.get("candidate_declined")),
        "created_at": plan.get("created_at", 0),
        "updated_at": plan.get("updated_at", 0),
        "expires_at": plan.get("expires_at", 0),
        "tokens": list(plan.get("tokens", [])),
    }


# --- command recognition ----------------------------------------------------


def identify(text):
    """Return ``plan-request`` / ``plan-relay`` for a plan command, else ``None``."""
    command = _command(text)
    return command[0] if command else None


def _command(text):
    if not isinstance(text, str):
        return None
    raw = text.strip()
    if raw.startswith("@"):
        parts = raw.split(None, 1)
        if len(parts) < 2:
            return None
        raw = parts[1].strip()
    verb, _, body = raw.partition(" ")
    verb = verb.lower()
    if verb in {"plan-request", "plan-relay"}:
        return verb, body.strip()
    return None


# --- dispatch ---------------------------------------------------------------


async def handle(gate, event, sender, level, room_detail) -> bool:
    """Handle one plan command after the runtime's membership/trust checks.

    Returns ``False`` when the message is not a plan command. A plan command is
    always consumed (``True``) even when it is refused, so it never falls through
    to the ordinary parser as an unknown verb.
    """
    command = _command(event.text)
    if command is None:
        return False
    verb, body = command
    try:
        await recover(gate, force=False)
    except Exception as exc:  # a recovery failure must not turn into an unknown command
        LOG.warning(
            "group plan recovery pending person=%s error=%s", gate.person, type(exc).__name__
        )

    name = _room_name(room_detail)
    if verb == "plan-request":
        if name != gate.person + "-home" or level is not Level.SELF or sender.person != gate.person:
            return True
        try:
            payload = _object(body)
        except PlanError as exc:
            await _home(gate, f"Plan request not accepted: {exc}.")
            return True
        await _request(gate, sender, payload)
        return True

    # plan-relay is only accepted in the plan's dedicated group room.
    if not name.startswith("group-"):
        return True
    if (
        sender.kind is not SenderKind.AGENT
        or sender.person is None
        or sender.id != sender.person + "-gate"
    ):
        return True
    try:
        payload = _object(body)
    except PlanError:
        return True  # a peer's malformed relay is ignored quietly
    try:
        await _relay(gate, event, sender, payload, name)
    except PlanError as exc:
        LOG.info(
            "plan relay refused person=%s sender=%s room=%s reason=%s",
            gate.person,
            sender.person,
            event.room_id,
            exc,
        )
    return True


async def _request(gate, sender, payload):
    action = payload.get("action")
    action = action.strip().lower() if isinstance(action, str) else ""
    person = gate.person
    if action in _SELF_ACTIONS:
        if (
            sender.kind is not SenderKind.AGENT
            or sender.id != main_agent(person)
            or sender.person != person
        ):
            await _home(gate, "Plan not accepted: only your own main agent may draft or revise.")
            return
        try:
            if action in {"create", "propose"}:
                await _create(gate, payload)
            else:
                await _revise(gate, payload)
        except PlanError as exc:
            await _home(gate, f"Plan not accepted: {exc}.")
        return
    if action in _CONSENT_ACTIONS:
        if not _may_consent(gate, sender):
            await _home(
                gate,
                f"Plan {action} not accepted: only you, or your main agent in via-agent "
                "consent mode, may approve.",
            )
            return
        try:
            if action == "vote":
                await _vote(gate, sender, payload)
            else:
                await _cancel(gate, sender, payload)
        except PlanError as exc:
            await _home(gate, f"Plan {action} not accepted: {exc}.")
        return
    await _home(gate, f"Plan request not accepted: unknown action {action!r}.")


def _may_consent(gate, sender) -> bool:
    if sender.kind is SenderKind.USER and sender.id == gate.person:
        return True
    if (
        sender.kind is SenderKind.AGENT
        and sender.id == main_agent(gate.person)
        and sender.person == gate.person
    ):
        return load_trust(gate.person).consent_default == "via-agent"
    return False


# --- owner-side commands ----------------------------------------------------


async def _create(gate, payload):
    person = gate.person
    state = load(person)
    token = _token(payload.get("token"))
    if token in state["tokens"]:
        existing = state["tokens"][token]["plan"]
        if existing in state["plans"]:
            await _home(gate, f"Plan {existing} is already submitted for token {token}.")
            return
    participants = _participants(payload.get("participants"), person)
    _check_participants(gate, participants)
    content = _content(payload.get("content"), gate._now())
    plan_id = _new_id(state, person, token)
    revision = 1
    fingerprint = _fingerprint(plan_id, revision, participants, content)

    name = "group-" + plan_id
    try:
        own = await gate.client.get_agent_detail(gate.client.agent_id)
        previous_room = next(
            (r for r in own.get("rooms", []) if r["room_name"].lstrip("#") == name),
            None,
        )
        if previous_room:
            if previous_room.get("archived"):
                raise PlanError("the earlier request room was archived; use a new request token")
            room = previous_room["room_id"]
            detail = await gate.client.get_room_detail(room)
            if (
                not detail.get("internal_only")
                or detail.get("read_visibility") != "private"
                or detail.get("write_visibility") != "private"
            ):
                raise PlanError("the earlier request room is not private")
        else:
            result = await gate.client.create_room(
                name,
                "Group plan",
                [person + "-gate"],
                internal_only=True,
                read_visibility="private",
                write_visibility="private",
            )
            room = result.get("room_id", result.get("id"))
        await gate.client.connect_to_room(room)
        allowed = set(participants) | {
            p + suffix for p in participants for suffix in ("-gate", "-hermes")
        }
        members = set()
        identities = gate.identities()
        for member in await gate.client.list_participants():
            identity = identities.get(member["id"])
            if identity is None or identity.id not in allowed:
                raise PlanError("the earlier request room has an unexpected participant")
            members.add(identity.id)
        for peer in participants:
            if peer != person and peer + "-gate" not in members:
                await gate.client.invite_agent_to_room(room, peer + "-gate")
    except (SwitchError, ValueError, PermissionError) as exc:
        LOG.warning("group room creation failed person=%s error=%s", person, type(exc).__name__)
        await _home(gate, "Plan not created: could not open the shared group room.")
        return

    now = gate._now()
    plan = {
        "id": plan_id,
        "uid": "trustnet-group-" + plan_id,
        "room": room,
        "coordinator": person,
        "participants": participants,
        "revision": revision,
        "fingerprint": fingerprint,
        "content": content,
        "status": "pending",
        "votes": {},
        "confirmed": None,
        "cancelled": None,
        "candidate_declined": False,
        "created_at": now.timestamp(),
        "updated_at": now.timestamp(),
        "expires_at": (now + EXPIRY).timestamp(),
        "tokens": [token],
        "jobs": {},
    }
    state["plans"][plan_id] = plan
    state["tokens"][token] = {
        "plan": plan_id,
        "action": "create",
        "created_at": now.timestamp(),
    }
    await _invite_own(gate, room)
    _job(plan, "home-created", "home", text=_drafted_text(plan, token))
    for peer in participants:
        if peer != person:
            _job(
                plan,
                f"offer-{revision}-{peer}",
                "relay",
                text=f"@{peer}-gate plan-relay {_offer_text(plan, person)}",
            )
    save(person, state)
    await recover(gate, force=False)


async def _revise(gate, payload):
    person = gate.person
    state = load(person)
    plan = _require_plan(state, payload.get("plan"))
    _exact_revision(plan, payload)
    if person != plan["coordinator"]:
        raise PlanError("ask the organizer to draft a replacement")
    if plan.get("status") == "cancelled":
        raise PlanError("the plan is cancelled")
    if payload.get("participants") is not None:
        participants = _participants(payload.get("participants"))
        if sorted(participants) != sorted(plan["participants"]):
            raise PlanError("a revision must keep the same participant set")
    participants = list(plan["participants"])
    _check_participants(gate, participants)
    content = _content(payload.get("content"), gate._now())
    if content == plan["content"]:
        raise PlanError("the revision changes nothing")

    revision = int(plan["revision"]) + 1
    fingerprint = _fingerprint(plan["id"], revision, participants, content)
    now = gate._now()
    plan.update(
        revision=revision,
        fingerprint=fingerprint,
        content=content,
        status="pending",
        votes={},
        candidate_declined=False,
        updated_at=now.timestamp(),
        expires_at=(now + EXPIRY).timestamp(),
    )
    _job(
        plan,
        f"home-revision-{revision}",
        "home",
        text=(
            f"Plan {plan['id']} revision {revision}: {_card(content)} · every participant "
            "must approve before the calendar changes."
        ),
    )
    for peer in participants:
        if peer != person:
            _job(
                plan,
                f"offer-{revision}-{peer}",
                "relay",
                text=f"@{peer}-gate plan-relay {_offer_text(plan, person)}",
            )
    save(person, state)
    await recover(gate, force=False)


async def _vote(gate, sender, payload):
    person = gate.person
    state = load(person)
    plan = _require_plan(state, payload.get("plan"))
    _exact_revision(plan, payload)
    if plan.get("status") == "cancelled":
        raise PlanError("the plan is cancelled")
    value = _vote_value(payload.get("vote"))
    if plan.get("status") != "pending":
        if plan.get("status") == "confirmed" and plan.get("confirmed", {}).get(
            "revision"
        ) == plan.get("revision"):
            raise PlanError("this revision is already confirmed")
        raise PlanError("the plan is not pending")
    existing = plan["votes"].get(person)
    if existing:
        if bool(existing.get("vote")) == value:
            await _home(gate, f"Plan {plan['id']}: your vote is already recorded.")
            return
        raise PlanError("a recorded vote cannot be changed")
    now = gate._now()
    via = "direct" if sender.kind is SenderKind.USER else "via-agent"
    plan["votes"][person] = {
        "vote": value,
        "via": via,
        "revision": plan["revision"],
        "fingerprint": plan["fingerprint"],
        "at": now.isoformat(),
    }
    plan["updated_at"] = now.timestamp()
    if not value:
        _decline(plan, person, now, gate)
    elif _all_yes(plan):
        _confirm(plan, now, gate)
    else:
        _job(
            plan,
            f"home-vote-{plan['revision']}-{person}",
            "home",
            text=(
                f"Plan {plan['id']}: {person} voted yes. Waiting for {', '.join(_waiting(plan))}."
            ),
        )
    for peer in plan["participants"]:
        if peer == person:
            continue
        _job(
            plan,
            f"vote-{plan['revision']}-{plan['fingerprint'][:8]}-{peer}",
            "relay",
            text=f"@{peer}-gate plan-relay {_vote_text(plan, person, value, via)}",
        )
    save(person, state)
    await recover(gate, force=False)


async def _cancel(gate, sender, payload):
    person = gate.person
    state = load(person)
    plan = _require_plan(state, payload.get("plan"))
    _exact_revision(plan, payload)
    if plan.get("status") == "cancelled":
        await _home(gate, f"Plan {plan['id']} is already cancelled.")
        return
    now = gate._now()
    _cancel_plan(plan, person, now)
    reason = payload.get("reason")
    for peer in plan["participants"]:
        if peer == person:
            continue
        _job(
            plan,
            f"cancel-{plan['revision']}-{plan['fingerprint'][:8]}-{peer}",
            "relay",
            text=f"@{peer}-gate plan-relay {_cancel_text(plan, person, reason)}",
        )
    save(person, state)
    await recover(gate, force=False)


# --- peer relays ------------------------------------------------------------


async def _relay(gate, event, sender, payload, name):
    action = payload.get("action")
    action = action.strip().lower() if isinstance(action, str) else ""
    plan_id = _plan_id(payload.get("plan"))
    if name != "group-" + plan_id:
        raise PlanError("relay is not in the plan's own room")
    claimed_from = payload.get("from")
    if claimed_from is not None:
        if not isinstance(claimed_from, str) or claimed_from.strip().lower() != sender.person:
            raise PlanError("relay from does not match its sender")
    participants = _participants(payload.get("participants"))
    if gate.person not in participants or sender.person not in participants:
        raise PlanError("relay is not from a participant")
    _check_participants(gate, participants)
    revision = _revision(payload.get("revision"))
    fingerprint = _hex(payload.get("fingerprint"))
    content = _content(payload.get("content"), gate._now(), future=action == "offer")
    if _fingerprint(plan_id, revision, participants, content) != fingerprint:
        raise PlanError("fingerprint does not match the relayed plan")
    coordinator = payload.get("coordinator")
    if coordinator is not None:
        if not isinstance(coordinator, str):
            raise PlanError("invalid coordinator")
        coordinator = coordinator.strip().lower()
        if coordinator not in participants:
            raise PlanError("coordinator is not a participant")

    state = load(gate.person)
    plan = state["plans"].get(plan_id)
    if plan is None:
        if action == "cancel":
            if not _is_self_voter(payload.get("voter"), sender.person):
                raise PlanError("a gate may relay only its own cancellation")
            if coordinator is None:
                raise PlanError("relay has no coordinator")
            # A cancellation can overtake the offer; record it so the offer
            # cannot resurrect the plan when it arrives.
            now = gate._now()
            plan = {
                "id": plan_id,
                "uid": "trustnet-group-" + plan_id,
                "room": event.room_id,
                "coordinator": coordinator,
                "participants": participants,
                "revision": revision,
                "fingerprint": fingerprint,
                "content": content,
                "status": "cancelled",
                "votes": {},
                "confirmed": None,
                "cancelled": {"by": sender.person, "at": now.isoformat()},
                "candidate_declined": False,
                "created_at": now.timestamp(),
                "updated_at": now.timestamp(),
                "expires_at": (now + EXPIRY).timestamp(),
                "tokens": [],
                "jobs": {},
            }
            token = _optional_token(payload.get("token"))
            if token:
                plan["tokens"].append(token)
                state["tokens"][token] = {
                    "plan": plan_id,
                    "action": "cancel",
                    "created_at": now.timestamp(),
                }
            state["plans"][plan_id] = plan
            _job(
                plan,
                f"home-cancelled-{revision}",
                "home",
                text=f"❌ Plan {plan_id} cancelled by {sender.person}.",
            )
            save(gate.person, state)
            await recover(gate, force=False)
            return
        if action != "offer" or revision != 1:
            raise PlanError("unknown plan")
        if coordinator is None:
            raise PlanError("relay has no coordinator")
        if sender.person != coordinator:
            raise PlanError("only the coordinator opens a plan")
        now = gate._now()
        plan = {
            "id": plan_id,
            "uid": "trustnet-group-" + plan_id,
            "room": event.room_id,
            "coordinator": coordinator,
            "participants": participants,
            "revision": revision,
            "fingerprint": fingerprint,
            "content": content,
            "status": "pending",
            "votes": {},
            "confirmed": None,
            "cancelled": None,
            "candidate_declined": False,
            "created_at": now.timestamp(),
            "updated_at": now.timestamp(),
            "expires_at": (now + EXPIRY).timestamp(),
            "tokens": [],
            "jobs": {},
        }
        token = _optional_token(payload.get("token"))
        if token:
            plan["tokens"].append(token)
            state["tokens"][token] = {
                "plan": plan_id,
                "action": "offer",
                "created_at": now.timestamp(),
            }
        state["plans"][plan_id] = plan
        await _invite_own(gate, event.room_id)
        _job(
            plan,
            "home-offer-1",
            "home",
            text=(
                f"Plan {plan_id} from {coordinator}: {_card(content)} · with "
                f"{', '.join(participants)} · vote when you are ready."
            ),
        )
        save(gate.person, state)
        await recover(gate, force=False)
        return

    if sorted(participants) != sorted(plan["participants"]):
        raise PlanError("stale participant set")
    if event.room_id != plan.get("room"):
        raise PlanError("relay is not in the plan's own room")
    if coordinator is not None and coordinator != plan["coordinator"]:
        raise PlanError("stale coordinator")
    if revision < plan["revision"]:
        raise PlanError("stale revision")

    if action == "offer":
        if sender.person != plan["coordinator"]:
            raise PlanError("only the organizer may revise the plan")
        if revision == plan["revision"]:
            if fingerprint != plan["fingerprint"]:
                raise PlanError("stale fingerprint")
            return  # idempotent replay
        if revision != plan["revision"] + 1:
            raise PlanError("revision gap")
        if plan.get("status") == "cancelled":
            raise PlanError("the plan is cancelled")
        now = gate._now()
        plan.update(
            revision=revision,
            fingerprint=fingerprint,
            content=content,
            status="pending",
            votes={},
            candidate_declined=False,
            updated_at=now.timestamp(),
            expires_at=(now + EXPIRY).timestamp(),
        )
        _job(
            plan,
            f"home-revision-{revision}",
            "home",
            text=(
                f"Plan {plan_id} revision {revision}: {_card(content)} · every participant "
                "must approve before the calendar changes."
            ),
        )
        save(gate.person, state)
        await recover(gate, force=False)
        return

    if revision != plan["revision"]:
        raise PlanError("stale revision")
    if fingerprint != plan["fingerprint"]:
        raise PlanError("stale fingerprint")

    if action == "vote":
        if not _is_self_voter(payload.get("voter"), sender.person):
            raise PlanError("a gate may relay only its own vote")
        if plan.get("status") != "pending":
            raise PlanError("the plan is not pending")
        value = _vote_value(payload.get("vote"))
        existing = plan["votes"].get(sender.person)
        if existing:
            if bool(existing.get("vote")) == value:
                return
            raise PlanError("conflicting replayed vote")
        now = gate._now()
        plan["votes"][sender.person] = {
            "vote": value,
            "via": payload.get("via")
            if payload.get("via") in {"direct", "via-agent"}
            else "via-agent",
            "revision": revision,
            "fingerprint": fingerprint,
            "at": now.isoformat(),
        }
        plan["updated_at"] = now.timestamp()
        if not value:
            _decline(plan, sender.person, now, gate)
        elif _all_yes(plan):
            _confirm(plan, now, gate)
        else:
            _job(
                plan,
                f"home-peer-vote-{revision}-{sender.person}",
                "home",
                text=(
                    f"Plan {plan_id}: {sender.person} voted yes. Waiting for "
                    f"{', '.join(_waiting(plan))}."
                ),
            )
        save(gate.person, state)
        await recover(gate, force=False)
        return

    if action == "cancel":
        if not _is_self_voter(payload.get("voter"), sender.person):
            raise PlanError("a gate may relay only its own cancellation")
        if plan.get("status") == "cancelled":
            return
        _cancel_plan(plan, sender.person, gate._now())
        save(gate.person, state)
        await recover(gate, force=False)
        return

    raise PlanError("unknown relay action")


# --- plan transitions -------------------------------------------------------


def _decline(plan, by, now, gate):
    plan["candidate_declined"] = True
    if plan.get("confirmed"):
        plan["status"] = "confirmed"
        suffix = " The previously confirmed plan still stands."
    else:
        plan["status"] = "declined"
        suffix = ""
    plan["updated_at"] = now.timestamp()
    _job(
        plan,
        f"home-declined-{plan['revision']}",
        "home",
        text=f"Plan {plan['id']} revision {plan['revision']} declined by {by}.{suffix}",
    )


def _confirm(plan, now, gate):
    previous = plan.get("confirmed")
    revision = plan["revision"]
    fingerprint = plan["fingerprint"]
    content = copy.deepcopy(plan["content"])
    plan["status"] = "confirmed"
    plan["candidate_declined"] = False
    plan["confirmed"] = {
        "revision": revision,
        "fingerprint": fingerprint,
        "content": copy.deepcopy(content),
        "at": now.isoformat(),
    }
    plan["updated_at"] = now.timestamp()
    action = "update" if previous else "create"
    _job(
        plan,
        f"calendar-{action}-{revision}-{fingerprint[:8]}",
        "calendar",
        action=action,
        uid=plan["uid"],
        content=copy.deepcopy(content),
    )
    _job(
        plan,
        f"home-confirmed-{revision}-{fingerprint[:8]}",
        "home",
        text=_confirmed_text(plan),
    )
    if gate.person == plan["coordinator"]:
        # Switch allows one document per name in a room; it belongs to the organizer.
        _job(
            plan,
            f"document-{revision}-{fingerprint[:8]}",
            "document",
            doc_id=f"group-plan-{plan['id']}-{revision}",
            text=_confirmed_text(plan),
        )


def _cancel_plan(plan, by, now):
    plan["status"] = "cancelled"
    plan["cancelled"] = {"by": by, "at": now.isoformat()}
    plan["updated_at"] = now.timestamp()
    confirmed = plan.get("confirmed")
    if confirmed:
        _job(
            plan,
            f"calendar-cancel-{confirmed['revision']}-{confirmed['fingerprint'][:8]}",
            "calendar",
            action="cancel",
            uid=plan["uid"],
            content=copy.deepcopy(confirmed["content"]),
        )
    _job(
        plan,
        f"home-cancelled-{plan['revision']}",
        "home",
        text=f"❌ Plan {plan['id']} cancelled by {by}.",
    )


def _expire(plan, gate, now):
    if plan.get("status") != "pending":
        return False
    if (
        plan.get("expires_at", 0) > now.timestamp()
        and datetime.fromisoformat(plan["content"]["start"]) > now
    ):
        return False
    if plan.get("confirmed"):
        plan["status"] = "confirmed"
        plan["candidate_declined"] = True
        text = (
            f"⌛ Plan {plan['id']} revision {plan['revision']} expired without every vote; "
            "the previously confirmed plan stands."
        )
    else:
        plan["status"] = "expired"
        text = f"⌛ Plan {plan['id']} expired without every vote."
    plan["updated_at"] = now.timestamp()
    _job(plan, f"home-expired-{plan['revision']}", "home", text=text)
    return True


def _all_yes(plan):
    return all(
        plan.get("votes", {}).get(participant, {}).get("vote") is True
        for participant in plan["participants"]
    )


def _waiting(plan):
    return [
        participant
        for participant in plan["participants"]
        if participant not in plan.get("votes", {})
    ]


# --- durable outbox ---------------------------------------------------------


async def recover(gate, *, force=True):
    """Retry the durable outbox and expire abandoned pending plans."""
    state = load(gate.person)
    now = gate._now()
    changed = False
    for plan in list(state["plans"].values()):
        if _expire(plan, gate, now):
            changed = True
            save(gate.person, state)
        for key, job in list(plan.get("jobs", {}).items()):
            if job.get("done"):
                continue
            if job["kind"] in {"relay", "document"} and any(
                peer != gate.person and load_trust(gate.person).level_for(peer) is None
                for peer in plan["participants"]
            ):
                job.update(done=True, stopped="A participant is no longer trusted")
                save(gate.person, state)
                continue
            if not force and job.get("retry_at", 0) > time.time():
                continue
            try:
                await _run_job(gate, plan, job)
            except Exception as exc:
                job["retry_at"] = time.time() + RETRY_SECONDS
                LOG.warning(
                    "group plan delivery pending person=%s ref=%s job=%s error=%s",
                    gate.person,
                    plan.get("id"),
                    key,
                    type(exc).__name__,
                )
            else:
                job["done"] = True
            save(gate.person, state)
            changed = True
    if changed:
        save(gate.person, state)


async def _run_job(gate, plan, job):
    kind = job.get("kind")
    if kind == "relay":
        room = plan.get("room")
        if not room:
            raise PlanError("relay has no room")
        await gate.client.connect_to_room(room)
        await gate.client.post_message(job["text"])
    elif kind == "home":
        await relay.post_home(gate.person, job["text"], client=gate.client)
    elif kind == "calendar":
        queue_calendar(
            gate.person,
            plan["id"],
            copy.deepcopy(job["content"]),
            action=job["action"],
            uid=job["uid"],
        )
    elif kind == "document":
        await gate.client.connect_to_room(plan["room"])
        await gate.client.create_room_document(
            job["doc_id"], "Confirmed group plan", "", job["text"]
        )
    else:
        raise PlanError(f"unknown job kind {kind!r}")


def _job(plan, key, kind, **payload):
    plan.setdefault("jobs", {}).setdefault(
        key, {"kind": kind, **payload, "done": False, "retry_at": 0}
    )


# --- rendering --------------------------------------------------------------


def _card(content):
    return f'{content["start"]} {content["minutes"]}m "{content["title"]}" @ "{content["place"]}"'


def _drafted_text(plan, token):
    return (
        f"Plan {plan['id']} drafted: {_card(plan['content'])} · with "
        f"{', '.join(plan['participants'])} · token {token} · every participant must vote."
    )


def _confirmed_text(plan):
    labels = " · ".join(
        f"{person.title()} ✅ "
        + ("via agent" if plan["votes"][person].get("via") == "via-agent" else "direct")
        for person in sorted(plan.get("votes", {}))
    )
    return f"✅ Plan {plan['id']}: {_card(plan['content'])} · {labels}"


def _offer_text(plan, sender):
    payload = {
        "action": "offer",
        "from": sender,
        "coordinator": plan["coordinator"],
        "plan": plan["id"],
        "revision": plan["revision"],
        "fingerprint": plan["fingerprint"],
        "participants": list(plan["participants"]),
        "content": copy.deepcopy(plan["content"]),
    }
    if plan.get("tokens"):
        payload["token"] = plan["tokens"][0]
    return _json(payload)


def _vote_text(plan, voter, value, via):
    payload = {
        "action": "vote",
        "from": voter,
        "voter": voter,
        "plan": plan["id"],
        "revision": plan["revision"],
        "fingerprint": plan["fingerprint"],
        "participants": list(plan["participants"]),
        "content": copy.deepcopy(plan["content"]),
        "coordinator": plan["coordinator"],
        "vote": value,
        "via": via,
    }
    if plan.get("tokens"):
        payload["token"] = plan["tokens"][0]
    return _json(payload)


def _cancel_text(plan, by, reason):
    payload = {
        "action": "cancel",
        "from": by,
        "voter": by,
        "plan": plan["id"],
        "revision": plan["revision"],
        "fingerprint": plan["fingerprint"],
        "participants": list(plan["participants"]),
        "content": copy.deepcopy(plan["content"]),
        "coordinator": plan["coordinator"],
    }
    if plan.get("tokens"):
        payload["token"] = plan["tokens"][0]
    if isinstance(reason, str) and reason.strip():
        payload["reason"] = reason.strip()[:200]
    return _json(payload)


def _json(payload):
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


# --- validation -------------------------------------------------------------


def _object(body):
    if len(body) > MAX_BODY:
        raise PlanError("the plan command is too large")
    try:
        value = json.loads(body)
    except ValueError:
        raise PlanError("the plan command is not valid JSON") from None
    if not isinstance(value, dict):
        raise PlanError("the plan command must be a JSON object")
    return value


def _token(value):
    if value is None:
        return secrets.token_hex(16)
    if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value.strip()):
        raise PlanError("invalid token")
    return value.strip()


def _optional_token(value):
    if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value.strip()):
        return None
    return value.strip()


def _participants(value, person=None):
    if not isinstance(value, list) or not value:
        raise PlanError("participants are required")
    names: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise PlanError("each participant must be a person name")
        key = item.strip().lower()
        if not _PERSON_RE.fullmatch(key):
            raise PlanError(f"invalid participant {key!r}")
        if key not in names:
            names.append(key)
    if person is not None and person not in names:
        names.append(person)
    names = sorted(names)
    if len(names) < 2:
        raise PlanError("a group plan needs two or more participants")
    if len(names) > MAX_PARTICIPANTS:
        raise PlanError(f"a group plan holds at most {MAX_PARTICIPANTS} participants")
    return names


def _check_participants(gate, participants):
    person = gate.person
    if person not in participants:
        raise PlanError("the participant set must include you")
    trust = load_trust(person)
    identities = gate.identities()
    for peer in participants:
        if peer == person:
            continue
        if trust.level_for(peer) is None:
            raise PlanError(f"{peer} is not on your trust list")
        matches = {i for i in identities.values() if i.id == peer + "-gate"}
        if not matches:
            raise PlanError(f"{peer}'s gate is not a known identity")
        if any(identity.person != peer for identity in matches):
            raise PlanError(f"{peer}'s gate identity does not match")


def _content(value, now, *, future=True):
    if not isinstance(value, dict):
        raise PlanError("a plan content object is required")
    raw = value.get("start")
    if not isinstance(raw, str):
        raise PlanError("start must be an ISO date and time")
    try:
        start = datetime.fromisoformat(raw.strip())
    except ValueError:
        raise PlanError("start must be an ISO date and time") from None
    if start.tzinfo is None or start.utcoffset() is None:
        raise PlanError("start needs a timezone")
    start = start.astimezone(timezone.utc)
    if future and start <= now:
        raise PlanError("the plan starts in the past")
    minutes = value.get("minutes")
    if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= 1440:
        raise PlanError("minutes must be an integer between 1 and 1440")
    title = value.get("title")
    if not isinstance(title, str):
        raise PlanError("title must be a string")
    title = title.strip()
    if not title or len(title) > MAX_TITLE:
        raise PlanError(f"title must be 1 to {MAX_TITLE} characters")
    if any(character in _TITLE_FORBIDDEN for character in title):
        raise PlanError("title cannot contain quotes, @ or line breaks")
    place = value.get("place")
    if not isinstance(place, str):
        raise PlanError("place must be a string")
    place = place.strip()
    if not place or len(place) > MAX_PLACE or not _PLACE_RE.fullmatch(place):
        raise PlanError("place must be 1 to 60 letters, digits, spaces or , . ' & -")
    return {
        "start": start.isoformat(),
        "minutes": minutes,
        "title": title,
        "place": place,
    }


def _is_self_voter(value, person):
    if value is None:
        return True
    return isinstance(value, str) and value.strip().lower() == person


def _vote_value(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        key = value.strip().lower()
        if key in {"yes", "true", "approve"}:
            return True
        if key in {"no", "false", "decline"}:
            return False
    raise PlanError('a vote must be "yes" or "no"')


def _revision(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PlanError("revision must be a positive integer")
    return value


def _exact_revision(plan, payload):
    if _revision(payload.get("revision")) != plan["revision"]:
        raise PlanError("stale revision")
    if _hex(payload.get("fingerprint")) != plan["fingerprint"]:
        raise PlanError("stale fingerprint")


def _plan_id(value):
    if not isinstance(value, str) or not _PLAN_RE.fullmatch(value.strip().lower()):
        raise PlanError("invalid plan id")
    return value.strip().lower()


def _hex(value):
    if not isinstance(value, str) or not _HEX_RE.fullmatch(value.strip().lower()):
        raise PlanError("invalid fingerprint")
    return value.strip().lower()


def _fingerprint(plan_id, revision, participants, content):
    payload = {
        "plan": plan_id,
        "revision": revision,
        "participants": sorted(participants),
        "content": content,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _new_id(state, person, token):
    # The random request token also determines the room name after an interrupted
    # server acknowledgment, before local state has been committed.
    candidate = PLAN_PREFIX + hashlib.sha256(json.dumps([person, token]).encode()).hexdigest()[:16]
    if candidate in state["plans"]:
        raise PlanError("the request identity is already bound to a plan")
    return candidate


def _resolve(state, reference):
    if not isinstance(reference, str):
        return None
    reference = reference.strip()
    if reference in state["plans"]:
        return state["plans"][reference]
    token = state["tokens"].get(reference)
    return state["plans"].get(token["plan"]) if token else None


def _require_plan(state, reference):
    plan = _resolve(state, reference)
    if plan is None:
        raise PlanError("unknown plan")
    return plan


def _room_name(detail):
    if not isinstance(detail, Mapping):
        return ""
    name = detail.get("name") or detail.get("room_name") or ""
    return name.lstrip("#") if isinstance(name, str) else ""


# --- side effects -----------------------------------------------------------


async def _invite_own(gate, room):
    try:
        await gate.client.invite_agent_to_room(room, main_agent(gate.person))
    except (SwitchError, ValueError):
        LOG.info("own agent joins group room on first use person=%s", gate.person)


async def _home(gate, text):
    try:
        await relay.post_home(gate.person, text, client=gate.client)
    except Exception as exc:
        LOG.warning(
            "group plan home notice failed person=%s error=%s", gate.person, type(exc).__name__
        )
