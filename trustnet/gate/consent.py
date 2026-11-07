"""Persistent questions and immutable proposals, with authenticated consent relays."""

import hashlib
import json
import logging
import time
from datetime import datetime, timedelta

from trustnet.gate import calendar, calendar_jobs, handshake, ledger, relay, storage
from trustnet.gate import commands as c
from trustnet.gate.dm import main_agent
from trustnet.gate.facts import load_profile, load_trust
from trustnet.gate.messages import join_greeting_ids


def load(person):
    return storage.load(person, "coordination")


def save(person, state):
    storage.save(person, "coordination", state)


def enqueue(item, key, kind, **payload):
    item.setdefault("jobs", {}).setdefault(key, {"kind": kind, **payload, "done": False})


async def recover(gate, *, force=True):
    state = load(gate.person)
    for ref, item in state.items():
        if ref.startswith("P") and "jobs" not in item:
            parsed = c.parse(f"propose {ref} {item['card']}", now=gate._now())
            item["plan"] = {
                "start": parsed.start.isoformat(),
                "minutes": int(parsed.duration.total_seconds() / 60),
                "title": parsed.title,
                "place": parsed.place,
            }
            item["jobs"] = {}
            if item["status"] == "pending":
                enqueue(
                    item,
                    "offer-relay",
                    "message",
                    text=f"@{item['friend']}-gate propose {ref} {item['card']}",
                )
            if gate.person in item["votes"]:
                vote, via = item["votes"][gate.person]
                enqueue(
                    item,
                    "vote-relay",
                    "message",
                    text=f"@{item['friend']}-gate consent {ref} {'yes' if vote else 'no'} {via} {digest(item['card'])}",
                )
            if item["status"] == "confirmed":
                enqueue(item, "calendar", "calendar")
            save(gate.person, state)
        for key, job in item.get("jobs", {}).items():
            if job["done"] or (not force and job.get("retry_at", 0) > time.time()):
                continue
            if (
                job["kind"] in {"message", "document"}
                and item["friend"] != gate.person
                and load_trust(gate.person).level_for(item["friend"]) is None
            ):
                job.update(done=True, stopped="The friend is no longer trusted")
                save(gate.person, state)
                continue
            if job["kind"] == "archive" and any(
                not pending["done"] for name, pending in item["jobs"].items() if name != key
            ):
                continue
            try:
                kind = job["kind"]
                if kind == "message":
                    await gate.client.connect_to_room(item["room"])
                    await gate.client.post_message(job["text"])
                elif kind == "home":
                    await relay.post_home(gate.person, job["text"], client=gate.client)
                elif kind == "calendar":
                    plan = item["plan"]
                    uid = f"trustnet-{gate.person}-{ref}-{digest(item['card'])}"
                    if calendar_jobs.delivery_mode(gate.person) == "agent":
                        calendar_jobs.queue(gate.person, ref, plan, uid=uid)
                    else:
                        calendar.add_event(
                            load_profile(gate.person).calendar_path,
                            datetime.fromisoformat(plan["start"]),
                            timedelta(minutes=plan["minutes"]),
                            plan["title"],
                            plan["place"],
                            uid=uid,
                        )
                elif kind == "document":
                    await gate.client.connect_to_room(item["room"])
                    await gate.client.create_room_document(
                        "plan-" + gate.person + "-" + ref, "Confirmed plan", "", job["text"]
                    )
                elif kind == "ledger":
                    ledger.record(
                        ref,
                        job["text"],
                        item["friend"],
                        item["room"],
                        job.get("entry_kind", "proposal"),
                        person=gate.person,
                        operation_id=f"plan:{item['room']}:{ref}:{key}",
                    )
                elif kind == "archive":
                    await gate.client.archive_room(item["room"])
                job["done"] = True
                save(gate.person, state)
            except Exception as exc:
                job["retry_at"] = time.time() + 2
                save(gate.person, state)
                logging.getLogger(__name__).warning(
                    "delivery pending person=%s ref=%s job=%s error=%s",
                    gate.person,
                    ref,
                    key,
                    type(exc).__name__,
                )
        if item["status"] == "confirmed" and item["room"] in gate.watches:
            gate.watches[item["room"]].closed = True
            gate.watches[item["room"]].save()


async def _friend_spoke(client, room, agent):
    """Whether ``agent`` has posted in ``room`` itself.

    Not counted: Switch's automatic greeting (under the agent's name within the
    greeting window of its join; the rule is shared with the personal watcher)
    and Switch's notices, which start by addressing whoever triggered them
    (``@om-hermes You're not permitted …``).
    """
    context = await client.read_context(room_id=room, limit=200)
    messages = [m for t in context.get("threads", []) for m in (t["root"], *t.get("replies", []))]
    greetings = join_greeting_ids(messages, sender=agent)
    for m in sorted(messages, key=lambda m: m.get("timestamp", 0)):
        if (m.get("sender_name") or m.get("sender")) != agent:
            continue
        if m.get("kind") == "room_join":
            continue
        if m.get("id") in greetings:
            continue
        if not m.get("body", "").lstrip().startswith("@"):
            return True
    return False


def digest(card):
    return hashlib.sha256(card.encode()).hexdigest()


async def handle(gate, event, command, sender, mode):
    await recover(gate, force=False)
    person, client = gate.person, gate.client
    if isinstance(command, (c.Answer, c.Yes, c.No)):
        ref = command.reference if isinstance(command, c.Answer) else command.proposal_id
        if ref.startswith(("F", "T")):
            from trustnet.gate import fact_changes

            try:
                if isinstance(command, c.Answer):
                    text = command.text.text.strip().lower()
                    if text not in {"yes", "no"}:
                        raise ValueError("review answer must be yes or no")
                    approve = text == "yes"
                else:
                    approve = isinstance(command, c.Yes)
                result = fact_changes.decide(person, ref, approve, sender=sender)
                text = json.dumps(result, ensure_ascii=False)
            except ValueError as exc:
                text = f"Not recorded: {exc}"
            await client.connect_to_room(event.room_id)
            await client.post_message(text)
            return
    state = load(person)

    async def refuse(reason):
        await client.connect_to_room(event.room_id)
        await client.post_message(f"Not recorded: {reason}.")

    if isinstance(command, (c.AskOwner, c.Propose, c.Counter)):
        detail = await client.get_room_detail(event.room_id)
        name = detail.get("name", detail.get("room_name", ""))
        friends = [p for p in name.removeprefix("dm-").split("-")[:2] if p != person]
        if isinstance(command, (c.Propose, c.Counter)) and (
            not name.startswith("dm-") or len(friends) != 1
        ):
            return
        friend = friends[0] if name.startswith("dm-") and len(friends) == 1 else person
        if isinstance(command, c.AskOwner):
            if sender.id != main_agent(person):
                await refuse("send ask-owner through your own gate")
                return
            ref, card = command.question_id, str(command.question)
        else:
            if sender.id not in {main_agent(person), friend + "-gate"}:
                await refuse("send proposals through your own gate")
                return
            ref = command.proposal_id
            if sender.id == friend + "-gate" and handshake.problem(person, friend):
                await refuse(handshake.problem(person, friend))
                return
            if command.start <= gate._now():
                await refuse("the proposal starts in the past; choose a future time")
                return
            if (
                isinstance(command, c.Propose)
                and sender.id == main_agent(person)
                and not await _friend_spoke(client, event.room_id, main_agent(friend))
            ):
                # A plan is agreed between two agents; one alone can't propose it.
                await client.connect_to_room(event.room_id)
                await client.post_message(
                    f"{ref} not recorded: wait for {main_agent(friend)} to reply here first."
                )
                return
            card = (
                f"{command.start.isoformat()} {int(command.duration.total_seconds() / 60)}m "
                f'"{command.title}" @ "{command.place}"'
            )
        if ref in state:
            existing = state[ref]
            if (
                sender.id == friend + "-gate"
                and existing["room"] == event.room_id
                and existing["card"] == card
            ):
                return
            await refuse(f"{ref} is already used for this person; choose a fresh ID in both gates")
            return
        if isinstance(command, c.Counter):
            if sender.id == main_agent(person) and "counter" not in (
                handshake.peer(person, friend) or {}
            ).get("capabilities", []):
                await refuse("the peer gate does not advertise counter support")
                return
            old = state.get(command.of)
            if (
                not old
                or old["status"] != "pending"
                or old["room"] != event.room_id
                or old["friend"] != friend
            ):
                await refuse("counter requires a pending proposal in this room")
                return
            if (
                sender.id == main_agent(person)
                and not old.get("jobs", {}).get("offer-relay", {"done": True})["done"]
            ):
                await refuse("wait for the original proposal to be delivered before countering")
                return
            initiator = person if sender.id == main_agent(person) else friend
            if initiator in old["votes"]:
                await refuse("a recorded vote cannot be revoked by a counter")
                return
            old["status"] = "superseded"
            old["superseded_by"] = ref
            for job in old.get("jobs", {}).values():
                if job["kind"] == "message":
                    job["done"] = True
        item = {
            "room": event.room_id,
            "friend": friend,
            "card": card,
            "votes": {},
            "status": "pending",
        }
        state[ref] = item
        enqueue(
            item, "offered", "home", text=f"{ref}: {card} · reply @{person}-gate answer {ref} …"
        )
        if isinstance(command, (c.Propose, c.Counter)):
            item["plan"] = {
                "start": command.start.isoformat(),
                "minutes": int(command.duration.total_seconds() / 60),
                "title": command.title,
                "place": command.place,
            }
            if isinstance(command, c.Counter):
                item["supersedes"] = command.of
            enqueue(item, "proposal-ledger", "ledger", text=card)
            if sender.id == main_agent(person):
                verb = f"counter {command.of}" if isinstance(command, c.Counter) else "propose"
                enqueue(item, "offer-relay", "message", text=f"@{friend}-gate {verb} {ref} {card}")
        save(person, state)
        await recover(gate, force=False)
        return
    ref = command.reference if isinstance(command, c.Answer) else command.proposal_id
    item = state.get(ref)
    if not item or item["status"] != "pending":
        await refuse(f"{ref} is not pending")
        return
    room, friend = item["room"], item["friend"]
    if not isinstance(command, c.Consent):
        detail = await client.get_room_detail(room)
        if detail.get("archived") or (room in gate.watches and gate.watches[room].closed):
            await refuse(f"{ref}'s planning room is closed; open a new room")
            return
    if isinstance(command, c.Consent):
        if (
            event.room_id != room
            or sender.id != friend + "-gate"
            or command.fingerprint != digest(item["card"])
        ):
            await refuse("consent must match the proposal room, friend gate and fingerprint")
            return
        who, vote, via = friend, command.agreed, command.via
    elif ref.startswith("Q"):
        if not isinstance(command, c.Answer):
            return
        item["status"] = "answered"
        enqueue(item, "answer", "message", text=f"{ref} answer from {person}: {command.text}")
        enqueue(item, "answer-ledger", "ledger", text=command.text.text, entry_kind="answer")
        save(person, state)
        await recover(gate, force=False)
        return
    else:
        if isinstance(command, c.Answer):
            if command.text.text.lower() not in {"yes", "no"}:
                return
            vote = command.text.text.lower() == "yes"
        else:
            vote = isinstance(command, c.Yes)
        who, via = person, mode
    if who in item["votes"]:
        await refuse(f"{ref} already has {who}'s vote")
        return
    item["votes"][who] = [vote, via]
    if who == person:
        enqueue(
            item,
            "vote-relay",
            "message",
            text=f"@{friend}-gate consent {ref} {'yes' if vote else 'no'} {via} {digest(item['card'])}",
        )
    votes = item["votes"]
    if not vote:
        item["status"] = "declined"
        enqueue(item, "declined", "home", text=f"❌ {ref} declined")
    elif set(votes) == {person, friend} and all(v[0] for v in votes.values()):
        item["status"] = "confirmed"
        labels = " · ".join(
            f"{p.title()} ✅ " + ("via agent" if votes[p][1] == "via-agent" else "direct")
            for p in sorted(votes)
        )
        text = f"✅ {ref}: {item['card']} · {labels}"
        if "plan" not in item:
            parsed = c.parse(f"propose {ref} {item['card']}", now=gate._now())
            item["plan"] = {
                "start": parsed.start.isoformat(),
                "minutes": int(parsed.duration.total_seconds() / 60),
                "title": parsed.title,
                "place": parsed.place,
            }
        enqueue(item, "calendar", "calendar")
        enqueue(item, "confirmed", "home", text=text)
        enqueue(item, "document", "document", text=text)
        enqueue(item, "confirmed-ledger", "ledger", text=text)
        if who != person:
            enqueue(item, "archive", "archive")
    save(person, state)
    await recover(gate, force=False)
