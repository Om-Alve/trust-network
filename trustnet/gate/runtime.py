"""Sequential gate dispatch with fresh membership and trusted server identities.

Beyond answering commands, the gate guards its owner's boundary: when another
side asks for a fact its room may not see, asks for a fact that does not exist,
sends something that is not a command, or tries a command only the owner may
use, the asker gets a refusal with no hint about what the owner has, and the
owner gets one alert in their home room. Gift rooms are the exception (surprise
mode): there the gate logs the overreach and posts nothing home.
"""

import asyncio
import fcntl
import json
import logging
from collections.abc import Callable, Mapping
from datetime import datetime, time, timedelta
from typing import Any

from trustnet.gate import ask_room, consent, dm, group_plans, handshake, ledger, relay, surprise
from trustnet.gate import commands as c
from trustnet.gate.calendar import busy, time_zone
from trustnet.gate.facts import (
    FactsError,
    Level,
    load_profile,
    load_trust,
    resolve_data_dir,
    save_trust,
)
from trustnet.gate.policy import (
    DenialCode,
    Direction,
    authorize,
    calendar_view,
    combined_permissions,
    room_level,
    visible_facts,
)
from trustnet.gate.view_as import format_value, view_as
from trustnet.gate.watch import ConversationWatch

LOG = logging.getLogger(__name__)
COMMAND_LIST = (
    "Commands: free, ask, ask-owner, propose, answer, yes, no, dm, ask-around, gift-ideas,"
    " claim, view-as, ledger, trust. See PROTOCOL.md for the forms."
)

#: What an asker outside the owner's side ever hears about a hidden fact.
NOT_SHARED = "not shared with you"

#: One overreach note per person and field in this window.
NOTE_COOLDOWN = timedelta(minutes=10)
ASK_AROUND_TTL = 7 * 24 * 60 * 60

#: Free text in an owner note is quoted and cut to this many characters.
MAX_SNIPPET = 60


class Gate:
    def __init__(self, person, client, identities, *, clock=None, gift_room=None):
        self.person, self.client, self.identities = person, client, identities
        self._clock: Callable[[], datetime] = clock or (lambda: datetime.now(time_zone()))
        self._gift_room = gift_room or relay.is_gift_room
        self.watches = {
            path.stem: ConversationWatch(path.stem, person, client, persistent=True)
            for path in (resolve_data_dir(person) / "room-watches").glob("*.json")
        }
        self.hellos: set[str] = set()  # rooms this gate has said hello in since it started
        self._dispatch_lock = asyncio.Lock()
        self._notes: dict[tuple[str, str], datetime] = {}

    async def handle(self, event):
        async with self._dispatch_lock:
            await self._handle(event)

    async def _handle(self, event):
        await consent.recover(self, force=False)
        await group_plans.recover(self, force=False)
        from trustnet.gate import fact_changes

        fact_changes.recover(self.person)
        watch = self.watches.get(event.room_id)
        if watch:
            if watch.closed:
                try:
                    command = c.parse(event.text)
                except c.ParseError:
                    return
                if (
                    not isinstance(command, c.Consent)
                    or consent.load(self.person).get(command.proposal_id, {}).get("status")
                    != "confirmed"
                ):
                    return
            identity = self.identities().get(event.sender_id)
            if (
                identity
                and identity.id in {dm.main_agent(self.person), dm.main_agent(identity.person)}
                and identity.person
            ):
                await watch.turn(event.text)
            if watch.closed and not isinstance(c.parse(event.text), c.Consent):
                return
        if not event.addressed:
            return
        room_detail = await self._room_detail(event.room_id)
        if room_detail and room_detail.get("archived"):
            try:
                if not isinstance(c.parse(event.text), c.Consent):
                    return
            except c.ParseError:
                return
        await self.client.connect_to_room(event.room_id)
        participants = await self.client.list_participants()
        identities = self.identities()
        members = []
        sender = identities.get(event.sender_id)
        for participant in participants:
            identity = identities.get(participant["id"])
            if identity is None:
                LOG.info(
                    "command=unknown room=%s level=None decision=unknown-member", event.room_id
                )
                return
            if participant["type"] == "agent":
                detail = await self.client.get_agent_detail(participant["id"])
                # Check the exported server mapping against current ownership.
                owner = identities.get(detail.get("owner_id"))
                if owner is None or identity.owner_id != owner.id:
                    return
            members.append(identity)
        members.extend(
            value
            for key, value in identities.items()
            if key.startswith("room:" + event.room_id + ":") and value not in members
        )
        trust = load_trust(self.person)
        level = room_level(self.person, members, trust)
        if level is None or sender is None or sender not in members:
            LOG.info("command=unknown room=%s level=%s decision=silent", event.room_id, level)
            return
        permissions = combined_permissions(
            trust,
            (member.person for member in members if member.person and member.person != self.person),
        )
        if await surprise.handle(self, event, sender, level, room_detail):
            return
        if await group_plans.handle(self, event, sender, level, room_detail):
            return
        own_side = _is_own_side(self.person, sender)
        try:
            command = c.parse(event.text, now=self._now())
        except c.ParseError:
            await self.client.post_message("Invalid command. " + COMMAND_LIST)
            if not own_side:
                await self._overreach(
                    event,
                    sender,
                    "command:malformed",
                    f"{_display(sender.person)}'s side sent a malformed command"
                    f" ({_snippet(event.text)})",
                )
            return
        name = {
            c.ViewAs: "view-as",
            c.JoinDm: "join-dm",
            c.JoinAsk: "join-ask",
            c.AskRoom: "ask-room",
            c.AskOwner: "ask-owner",
        }.get(type(command), type(command).__name__.lower())
        direction = Direction.OUTBOUND if sender.person == self.person else Direction.INBOUND
        if isinstance(command, c.AskAround):
            name = "ask-around"
        if isinstance(command, c.Answer) and command.reference.startswith("A") and not own_side:
            name = "around-reply"
        decision = authorize(
            name,
            sender,
            self.person,
            trust.consent_default,
            personal_agents=(dm.main_agent(self.person),),
            direction=direction,
            room_name=room_detail.get("name", room_detail.get("room_name", ""))
            if room_detail
            else "",
        )
        LOG.info(
            "command=%s room=%s level=%s decision=%s", name, event.room_id, level, bool(decision)
        )
        if isinstance(command, c.Unknown):
            await self.client.post_message(COMMAND_LIST)
            if not own_side:
                await self._overreach(
                    event,
                    sender,
                    "command:unknown",
                    f"{_display(sender.person)}'s side sent something that isn't a command"
                    f" ({_snippet(event.text)})",
                )
            return
        if not decision:
            if own_side:
                if decision.code is DenialCode.CONSENT_MODE:
                    # Say why, or the agent reports a yes that was never recorded.
                    ref = getattr(command, "reference", None) or getattr(command, "proposal_id", "")
                    await self.client.post_message(
                        f"{ref} not recorded: {_display(self.person)} answers this directly"
                        f" (consent is set to direct), not through an agent."
                    )
                elif name in {"answer", "yes", "no", "consent", "join-dm", "hello"}:
                    await self.client.post_message(f"Not allowed: {decision.reason}.")
                return
            if decision.code is DenialCode.UNKNOWN_COMMAND:
                await self.client.post_message(COMMAND_LIST)
                await self._overreach(
                    event,
                    sender,
                    "command:unknown",
                    f"{_display(sender.person)}'s side sent something that isn't a command"
                    f" ({_snippet(event.text)})",
                )
            else:
                text = (
                    f"Not allowed: {decision.reason}."
                    if name in {"answer", "yes", "no", "consent", "join-dm", "hello"}
                    else "Not allowed."
                )
                await self.client.post_message(text)
                await self._overreach(
                    event,
                    sender,
                    "command:" + name,
                    f"{_display(sender.person)}'s side tried a command only you can use ({name})",
                )
            return
        if isinstance(command, (c.ViewAs, c.Ledger, c.Trust)) and level != Level.SELF:
            return
        if isinstance(command, c.AskAround) or (
            isinstance(command, c.Answer) and command.reference.startswith("A")
        ):
            await self._around(event, command, sender, level, own_side, room_detail)
            return
        if isinstance(command, c.Hello):
            await handshake.handle(self, event, command, sender)
            return
        # Consent is a gate relay, never an alias for the owner's yes command.
        if isinstance(
            command, (c.AskOwner, c.Answer, c.Propose, c.Counter, c.Yes, c.No, c.Consent)
        ):
            await consent.handle(self, event, command, sender, decision.mode)
            return
        if isinstance(command, c.Dm):
            if level == Level.SELF:
                await dm.setup(self, command.person, command.goal)
            return
        if isinstance(command, c.AskRoom):
            if level == Level.SELF:
                await ask_room.setup(self, command.person)
            return
        if isinstance(command, c.JoinDm):
            reason = handshake.problem(self.person, sender.person)
            if reason:
                # Plain text: addressing the peer gate would read as a malformed command.
                await self.client.post_message(f"join-dm refused: {reason}.")
                await relay.post_home(
                    self.person,
                    f"Didn't open a planning room with {_display(sender.person)}: {reason}.",
                    client=self.client,
                )
                return
            await dm.setup(self, sender.person, command.goal, command.room)
            return
        if isinstance(command, c.JoinAsk):
            reason = handshake.problem(self.person, sender.person)
            if reason:
                await self.client.post_message(f"join-ask refused: {reason}.")
                await relay.post_home(
                    self.person,
                    f"Didn't answer a fact request from {_display(sender.person)}: {reason}.",
                    client=self.client,
                )
                return
            await ask_room.join(self, sender.person, command.room)
            return
        profile = load_profile(self.person)
        disclosed = {}
        overreach: list[tuple[str, str]] = []
        quiet: list[tuple[str, str]] = []
        if isinstance(command, c.Ask):
            values = {
                k: surprise.owner_value(self.person, k, v, self._now()) if own_side else v
                for k, v in visible_facts(profile, level, permissions).items()
            }
            fields = list(dict.fromkeys(command.facts))
            disclosed = {key: values[key] for key in fields if key in values}
            lines = []
            for key in fields:
                if key in values:
                    lines.append(f"{key}: {format_value(values[key])}")
                    continue
                lines.append(f"{key}: {NOT_SHARED}")
                if own_side:
                    continue
                fact = profile.facts.get(key)
                if fact is None:
                    note = (
                        f"{_display(sender.person)}'s side asked for {_snippet(key, limit=40)}"
                        " (not a field you have)"
                    )
                else:
                    note = (
                        f"{_display(sender.person)}'s side asked for your {key}"
                        f" ({fact.level.value})"
                    )
                if fact is not None and fact.quiet:
                    # An explicit owner choice: record the request, stay quiet.
                    quiet.append((key, note))
                else:
                    overreach.append((f"fact:{key}", note))
            text = "\n".join(lines)
        elif isinstance(command, c.Free):
            start = datetime.combine(command.start, time.min, time_zone())
            end = datetime.combine(command.end + timedelta(days=1), time.min, time_zone())
            blocks = calendar_view(
                busy(profile.calendar_path, start, end), level, titles=permissions.calendar_titles
            )
            value = [
                {"start": b.start.isoformat(), "end": b.end.isoformat(), "title": b.title}
                for b in blocks
            ]
            disclosed = {"calendar": value}
            text = (
                "\n".join(
                    f"{b.start.isoformat()} .. {b.end.isoformat()} {b.title or 'busy'}"
                    for b in blocks
                )
                or "Nothing busy in this range."
            )
        elif isinstance(command, c.ViewAs):
            text = view_as(
                profile, trust, command.person, now=self._now(), claims=surprise.claims(self.person)
            ).render()
        elif isinstance(command, c.Ledger):
            text = ledger.format_ledger(person=self.person, now=self._now())
        elif isinstance(command, c.Trust):
            with fact_changes.editing(self.person):
                trust = load_trust(self.person)
                try:
                    trust.grant(command.person, command.level)
                except FactsError as exc:
                    await self.client.post_message(f"Not recorded: {exc}")
                    return
                save_trust(trust, resolve_data_dir(self.person) / "trust.yaml")
            text = f"Trust for {command.person}: {command.level}"
        else:
            text = COMMAND_LIST
        await self.client.post_message(text)
        for recipient in sorted({m.person for m in members if m.person}):
            for field, value in disclosed.items():
                ledger.record(field, value, recipient, event.room_id, "answer", person=self.person)
        for field, note in overreach:
            await self._overreach(event, sender, field, note)
        for key, note in quiet:
            fact = profile.facts[key]
            ledger.record(
                key,
                f"not shared ({fact.level.value})",
                sender.person,
                event.room_id,
                "request",
                person=self.person,
            )

    def _around_state(self):
        path = resolve_data_dir(self.person) / "ask-around.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def _save_around(self, state):
        path = resolve_data_dir(self.person) / "ask-around.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(mode=0o600)
        path.write_text(json.dumps(state))

    async def _around(self, event, command, sender, level, own_side, detail):
        state = self._around_state()
        if isinstance(command, c.AskAround) and own_side:
            if level != Level.SELF:
                return
            trust = load_trust(self.person)
            audience = await self._around_audience(command, trust)
            if audience is None:
                return
            ref = _next_around_ref(state)
            entry = {
                "question": command.question.text,
                "expires": self._now().timestamp() + ASK_AROUND_TTL,
                "peers": {},
                "answers": {},
                "audience": list(audience),
            }
            state[ref] = entry
            self._save_around(state)
            memberships = (await self.client.get_agent_detail(self.client.agent_id))["rooms"]
            for friend in audience:
                name = "conn-" + "-".join(sorted((self.person, friend)))
                room = next(
                    (
                        r["room_id"]
                        for r in memberships
                        if r["room_name"].lstrip("#") == name and not r.get("archived")
                    ),
                    None,
                )
                if room is None:
                    result = await self.client.create_room(
                        name, "Gate connection", [self.person + "-gate"], internal_only=True
                    )
                    room = result.get("room_id", result.get("id"))
                    await self.client.connect_to_room(room)
                    await self.client.invite_agent_to_room(room, friend + "-gate")
                entry["peers"][friend] = room
                self._save_around(state)
                await self.client.connect_to_room(room)
                await self.client.post_message(
                    f"@{friend}-gate ask-around {ref} {command.question}"
                )
                ledger.record(
                    "question",
                    command.question.text,
                    friend,
                    room,
                    "ask-around",
                    person=self.person,
                )
            if command.reference is None:
                notice = f"{ref} asking around: {command.question}"
            else:
                notice = f"{ref} asking {', '.join(audience)}: {command.question}"
            await relay.post_home(self.person, notice, client=self.client)
            return
        if isinstance(command, c.AskAround):
            pair = "-".join(sorted((self.person, sender.person)))
            name = (detail or {}).get("name", (detail or {}).get("room_name", "")).lstrip("#")
            if (
                sender.id != sender.person + "-gate"
                or name != "conn-" + pair
                or not command.reference
            ):
                return
            key = sender.person + ":" + command.reference
            if key in state:
                return
            state[key] = {
                "room": event.room_id,
                "peer": sender.person,
                "reference": command.reference,
                "expires": self._now().timestamp() + ASK_AROUND_TTL,
                "question": command.question.text,
                "answered": False,
            }
            self._save_around(state)
            # Never dump profile facts: route the question to the owner's own
            # agent, or escalate to the person only when they opted in (or when
            # there is no registered agent to ask).
            trust = load_trust(self.person)
            route = trust.permissions_for(sender.person).ask_around
            if route == "off":
                return
            if route == "agent" and not any(
                i.id == dm.main_agent(self.person) and i.person == self.person
                for i in self.identities().values()
            ):
                route = "person"
            local = _next_around_ref(state)
            state[key]["local"] = local
            state[key]["route"] = route
            self._save_around(state)
            if route == "person":
                notice = (
                    f"{local} {_display(sender.person)} asks {command.question}. "
                    f"Reply with answer {local}."
                )
            else:
                notice = (
                    f"{local} {_display(sender.person)} asks {command.question}. "
                    f"Your agent can reply with answer {local}, or ask you first."
                )
            await relay.post_home(self.person, notice, client=self.client)
            return
        ref = command.reference
        if own_side:
            if level != Level.SELF:
                return
            key = next((k for k, v in state.items() if v.get("local") == ref), None)
            now = self._now().timestamp()
            if key is None or state[key]["answered"] or state[key]["expires"] < now:
                # Say so: an agent answering an old reference (still in the home
                # room's history) would otherwise report an answer that went nowhere.
                still = [
                    f"{v['local']} from {v['peer']}"
                    for v in state.values()
                    if v.get("local") and v.get("answered") is False and v["expires"] >= now
                ]
                listed = f"Open: {', '.join(still)}." if still else "Nothing is open."
                await self.client.post_message(
                    f"{ref} not sent: it isn't open (answered, expired or unknown). {listed}"
                )
                return
            pending = state[key]
            # Membership and trust must still permit disclosure at answer time.
            await self.client.connect_to_room(pending["room"])
            ids = self.identities()
            members = [ids.get(p["id"]) for p in await self.client.list_participants()]
            if None in members or room_level(self.person, members, load_trust(self.person)) is None:
                return
            await self._around_send(state, key, command.text)
            return
        entry = state.get(ref)
        if not entry or entry.get("expires", 0) < self._now().timestamp():
            return
        if entry.get("peers", {}).get(sender.person) != event.room_id:
            return
        entry["answers"][sender.person] = command.text.text
        self._save_around(state)
        ledger.record(
            "answer:" + sender.person,
            command.text.text,
            self.person,
            event.room_id,
            "ask-around",
            person=self.person,
        )
        summary = "\n".join(f"{p}: {c.Quoted(t)}" for p, t in entry["answers"].items())
        await relay.post_home(
            self.person,
            f"{ref} answers to {c.Quoted(entry['question'])}:\n{summary}",
            client=self.client,
        )

    async def _around_audience(self, command, trust) -> list[str] | None:
        """The friends to ask, or ``None`` after explaining a refusal in home.

        No reference means the legacy "ask every listed friend" form. A
        reference names a short-lived owner-local request written by the CLI or
        MCP tool before it posts; it carries the explicit audience and the exact
        question, so a stale or forged token asks nobody.
        """
        if command.reference is None:
            return [name for name in trust.people if not trust.is_blocked(name)]

        request = _read_audience_request(
            self.person, command.reference, command.question.text, self._now().timestamp()
        )
        if request is None:
            await relay.post_home(
                self.person,
                f"{command.reference} not sent: that ask-around audience request is missing or "
                "expired.",
                client=self.client,
            )
            return None

        audience: list[str] = []
        for raw in request["audience"]:
            if not isinstance(raw, str) or not raw.strip():
                problem = "every audience entry must be a friend's name"
            else:
                key = raw.strip().lower()
                try:
                    if key == self.person:
                        problem = "you cannot add yourself to an ask-around audience"
                    elif trust.level_for(key) is None:
                        problem = f"{key} is not a friend on your trust list"
                    else:
                        problem = ""
                except FactsError as exc:
                    problem = str(exc)
            if problem:
                await relay.post_home(
                    self.person,
                    f"{command.reference} not sent: {problem}.",
                    client=self.client,
                )
                return None
            if key not in audience:
                audience.append(key)
        if not audience:
            await relay.post_home(
                self.person,
                f"{command.reference} not sent: the audience is empty.",
                client=self.client,
            )
            return None
        return audience

    async def _around_send(self, state, key, text):
        entry = state[key]
        if entry["answered"] or entry["expires"] < self._now().timestamp():
            return
        await self.client.connect_to_room(entry["room"])
        await self.client.post_message(f"@{entry['peer']}-gate answer {entry['reference']} {text}")
        ledger.record(
            "ask-around-answer",
            text.text,
            entry["peer"],
            entry["room"],
            "ask-around",
            person=self.person,
        )
        entry["answered"] = True
        self._save_around(state)

    async def _overreach(self, event, sender, field, text):
        """Alert the owner about one boundary breach, unless surprise mode applies."""
        person = sender.person
        if person is None or _is_own_side(self.person, sender):
            return
        detail = await self._room_detail(event.room_id)
        if detail is None:
            LOG.info(
                "overreach person=%s field=%s room=%s decision=log-only reason=room-unknown",
                person,
                field,
                event.room_id,
            )
            return
        if self._gift_room(detail):
            LOG.info(
                "overreach person=%s field=%s room=%s decision=log-only reason=gift-room",
                person,
                field,
                event.room_id,
            )
            return
        if not self._note_due(person, field):
            LOG.info(
                "overreach person=%s field=%s room=%s decision=deduped",
                person,
                field,
                event.room_id,
            )
            return
        name = _room_name(detail)
        try:
            await relay.post_home(self.person, f"{text} · room: {name}", client=self.client)
        except Exception as exc:
            # A missing home room or a transport error must not lose the reply.
            LOG.warning("overreach note failed: %s", type(exc).__name__)
            return
        self._notes[(person, field)] = self._now()
        LOG.info("overreach person=%s field=%s room=%s decision=note", person, field, event.room_id)

    async def _room_detail(self, room_id) -> Mapping[str, Any] | None:
        """Read the room's name and flags; ``None`` means fail closed."""
        try:
            detail = await self.client.get_room_detail(room_id)
        except Exception as exc:
            LOG.info("room detail unavailable room=%s: %s", room_id, type(exc).__name__)
            return None
        return detail if isinstance(detail, Mapping) else None

    def _note_due(self, person: str, field: str) -> bool:
        last = self._notes.get((person, field))
        return last is None or self._now() - last >= NOTE_COOLDOWN

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime):
            raise TypeError("the gate clock must return a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=time_zone())
        return value.astimezone(time_zone())

    async def _timeouts(self):
        while True:
            await asyncio.sleep(1)
            async with self._dispatch_lock:
                try:
                    await consent.recover(self, force=False)
                    await group_plans.recover(self, force=False)
                    from trustnet.gate import fact_changes

                    fact_changes.recover(self.person)
                    await surprise.expire(self)
                    for watch in list(self.watches.values()):
                        await watch.check()
                except Exception as exc:
                    LOG.warning("recovery pending: %s", type(exc).__name__)

    async def run(self):
        directory = resolve_data_dir(self.person)
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "gate.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError(f"a gate is already running for {self.person}") from None
            await consent.recover(self)
            await group_plans.recover(self)
            timer = asyncio.create_task(self._timeouts())
            try:
                await self._events()
            finally:
                timer.cancel()
                await asyncio.gather(timer, return_exceptions=True)

    async def _events(self):
        async for event in self.client.events():
            try:
                await self.handle(event)
            except Exception as exc:
                # Exception messages can contain transport payloads or private values.
                LOG.error("gate dispatch failed: %s", type(exc).__name__)


def _next_around_ref(state: dict) -> str:
    """The next free ``A<n>`` for this person: short, because people see and say it.

    Refs this gate assigns (its own ask-arounds, and the local question it puts to
    its person for a friend's ask-around) share one counter, so they never collide.
    A friend's ref is stored under ``<friend>:<ref>`` and doesn't take a number here.
    """
    used = {k for k in state if ":" not in k} | {v.get("local") for v in state.values()}
    n = 1
    while f"A{n}" in used:
        n += 1
    return f"A{n}"


def _read_audience_request(person: str, reference: str, question: str, now: float):
    """Read and consume one owner-written audience request, or return ``None``.

    The request is a local file keyed by the reference in the owner's command.
    It must carry the same question and a fresh expiry; anything else is a
    forged, stale or mismatched token and asks nobody.
    """
    path = resolve_data_dir(person) / "ask-around-requests" / f"{reference}.json"
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("question") != question:
        return None
    expires = payload.get("expires")
    audience = payload.get("audience")
    if isinstance(expires, bool) or not isinstance(expires, int | float) or expires < now:
        return None
    if not isinstance(audience, list) or not audience:
        return None
    try:
        path.unlink()
    except OSError:
        pass
    return {"audience": audience}


def _is_own_side(person: str, sender) -> bool:
    """Whether ``sender`` is the owner or an agent acting for the owner."""
    return sender.person is not None and sender.person == person.strip().lower()


def _display(person: str) -> str:
    """A person key as the owner note shows it (``rahul`` → ``Rahul``)."""
    return person[:1].upper() + person[1:]


def _snippet(text: Any, limit: int = MAX_SNIPPET) -> str:
    """Quote free text for an owner note: one line, no quotes inside, capped."""
    raw = text if isinstance(text, str) else str(text)
    line = " ".join(raw.split()).replace('"', "'")
    if len(line) > limit:
        line = line[: limit - 1].rstrip() + "…"
    return f'"{line}"'


def _room_name(detail: Mapping[str, Any]) -> str:
    """The room's display name, capped, never an empty string."""
    name = detail.get("name") or detail.get("room_name") or detail.get("id")
    if not isinstance(name, str) or not name.strip():
        return "unknown room"
    return _snippet(name.strip(), limit=60)[1:-1]
