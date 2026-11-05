"""Sequential gate dispatch with fresh membership and trusted server identities."""

import logging
from datetime import datetime, time, timedelta

from trustnet.gate import commands as c
from trustnet.gate import ledger
from trustnet.gate.calendar import TIME_ZONE, busy
from trustnet.gate.facts import Level, load_profile, load_trust, resolve_data_dir, save_trust
from trustnet.gate.policy import Direction, authorize, calendar_view, room_level, visible_facts
from trustnet.gate.view_as import view_as

LOG = logging.getLogger(__name__)
COMMAND_LIST = "Commands: free, ask, view-as, ledger, trust. Other coordination commands arrive in later phases."


class Gate:
    def __init__(self, person, client, identities):
        self.person, self.client, self.identities = person, client, identities

    async def handle(self, event):
        if not event.addressed:
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
        try:
            command = c.parse(event.text)
        except c.ParseError:
            await self.client.post_message("Invalid command. " + COMMAND_LIST)
            return
        name = {c.ViewAs: "view-as", c.JoinDm: "join-dm"}.get(
            type(command), type(command).__name__.lower()
        )
        direction = Direction.OUTBOUND if sender.person == self.person else Direction.INBOUND
        decision = authorize(name, sender, self.person, trust.consent_default, direction=direction)
        LOG.info(
            "command=%s room=%s level=%s decision=%s", name, event.room_id, level, bool(decision)
        )
        if isinstance(command, c.Unknown):
            await self.client.post_message(COMMAND_LIST)
            return
        if not decision:
            return
        if isinstance(command, (c.ViewAs, c.Ledger, c.Trust)) and level != Level.SELF:
            return
        # Consent is a gate relay, never an alias for the owner's yes command.
        if isinstance(command, c.Consent):
            return
        profile = load_profile(self.person)
        disclosed = {}
        if isinstance(command, c.Ask):
            values = visible_facts(profile, level)
            disclosed = {key: values[key] for key in command.facts if key in values}
            text = "\n".join(
                f"{key}: {values.get(key, 'not shared at this level')}" for key in command.facts
            )
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

    async def run(self):
        async for event in self.client.events():
            try:
                await self.handle(event)
            except Exception as exc:
                # Exception messages can contain transport payloads or private values.
                LOG.error("gate dispatch failed: %s", type(exc).__name__)
