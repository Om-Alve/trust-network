"""Sequential gate dispatch with fresh membership and trusted server identities.

Beyond answering commands, the gate guards its owner's boundary: when another
side asks for a fact its room may not see, asks for a fact that does not exist,
sends something that is not a command, or tries a command only the owner may
use, the asker gets a refusal with no hint about what the owner has, and the
owner gets one alert in their home room. Gift rooms are the exception (surprise
mode): there the gate logs the overreach and posts nothing home.
"""

import asyncio
import logging
from collections.abc import Callable, Mapping
from datetime import datetime, time, timedelta
from typing import Any

from trustnet.gate import commands as c
from trustnet.gate import dm, ledger, relay
from trustnet.gate.calendar import TIME_ZONE, busy
from trustnet.gate.facts import Level, load_profile, load_trust, resolve_data_dir, save_trust
from trustnet.gate.policy import (
    DenialCode,
    Direction,
    authorize,
    calendar_view,
    room_level,
    visible_facts,
)
from trustnet.gate.view_as import view_as

LOG = logging.getLogger(__name__)
COMMAND_LIST = "Commands: free, ask, view-as, ledger, trust. Other coordination commands arrive in later phases."

#: What an asker outside the owner's side ever hears about a hidden fact.
NOT_SHARED = "not shared with you"

#: One overreach note per person and field in this window.
NOTE_COOLDOWN = timedelta(minutes=10)

#: Free text in an owner note is quoted and cut to this many characters.
MAX_SNIPPET = 60


class Gate:
    def __init__(self, person, client, identities, *, clock=None, gift_room=None):
        self.person, self.client, self.identities = person, client, identities
        self._clock: Callable[[], datetime] = clock or (lambda: datetime.now(TIME_ZONE))
        self._gift_room = gift_room or relay.is_gift_room
        self.watches = {}
        self._dispatch_lock = asyncio.Lock()
        self._notes: dict[tuple[str, str], datetime] = {}

    async def handle(self, event):
        async with self._dispatch_lock:
            await self._handle(event)

    async def _handle(self, event):
        watch = self.watches.get(event.room_id)
        if watch:
            if watch.closed:
                return
            identity = self.identities().get(event.sender_id)
            if (
                identity
                and identity.id in {dm.main_agent(self.person), dm.main_agent(identity.person)}
                and identity.person
            ):
                await watch.turn(event.text)
            if watch.closed:
                return
        if not event.addressed:
            return
        room_detail = await self._room_detail(event.room_id)
        if room_detail and room_detail.get("archived"):
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
        own_side = _is_own_side(self.person, sender)
        try:
            command = c.parse(event.text)
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
        name = {c.ViewAs: "view-as", c.JoinDm: "join-dm"}.get(
            type(command), type(command).__name__.lower()
        )
        direction = Direction.OUTBOUND if sender.person == self.person else Direction.INBOUND
        decision = authorize(
            name,
            sender,
            self.person,
            trust.consent_default,
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
                await self.client.post_message("Not allowed.")
                await self._overreach(
                    event,
                    sender,
                    "command:" + name,
                    f"{_display(sender.person)}'s side tried a command only you can use ({name})",
                )
            return
        if isinstance(command, (c.ViewAs, c.Ledger, c.Trust)) and level != Level.SELF:
            return
        # Consent is a gate relay, never an alias for the owner's yes command.
        if isinstance(command, c.Consent):
            return
        if isinstance(command, c.Dm):
            if level == Level.SELF:
                await dm.setup(self, command.person, command.goal)
            return
        if isinstance(command, c.JoinDm):
            await dm.setup(self, sender.person, command.goal, command.room)
            return
        profile = load_profile(self.person)
        disclosed = {}
        overreach: list[tuple[str, str]] = []
        if isinstance(command, c.Ask):
            values = visible_facts(profile, level)
            fields = list(dict.fromkeys(command.facts))
            disclosed = {key: values[key] for key in fields if key in values}
            lines = []
            for key in fields:
                if key in values:
                    lines.append(f"{key}: {values[key]}")
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
                overreach.append((f"fact:{key}", note))
            text = "\n".join(lines)
        elif isinstance(command, c.Free):
            start = datetime.combine(command.start, time.min, TIME_ZONE)
            end = datetime.combine(command.end + timedelta(days=1), time.min, TIME_ZONE)
            blocks = calendar_view(busy(profile.calendar_path, start, end), level)
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
            text = view_as(profile, trust, command.person).render()
        elif isinstance(command, c.Ledger):
            text = ledger.format_ledger(person=self.person)
        elif isinstance(command, c.Trust):
            trust.people[command.person] = command.level
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
            return value.replace(tzinfo=TIME_ZONE)
        return value.astimezone(TIME_ZONE)

    async def _timeouts(self):
        while True:
            await asyncio.sleep(1)
            async with self._dispatch_lock:
                for watch in list(self.watches.values()):
                    await watch.check()

    async def run(self):
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
