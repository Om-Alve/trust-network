"""Persistent questions and immutable proposals, with authenticated consent relays."""

import hashlib
import json

from trustnet.gate import commands as c
from trustnet.gate import handshake, ledger, relay
from trustnet.gate.dm import main_agent
from trustnet.gate.facts import resolve_data_dir


def load(person):
    path = resolve_data_dir(person) / "coordination.json"
    return json.loads(path.read_text()) if path.exists() else {}


def save(person, state):
    path = resolve_data_dir(person) / "coordination.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.touch(mode=0o600)
    temp.write_text(json.dumps(state))
    temp.replace(path)


async def _friend_spoke(client, room, agent):
    """Whether ``agent`` has posted in ``room`` itself.

    Not counted: Switch's automatic greeting (sent under the agent's name within
    two seconds of it joining) and Switch's notices, which start by addressing
    whoever triggered them (``@om-hermes You're not permitted …``).
    """
    context = await client.read_context(room_id=room, limit=200)
    messages = [m for t in context.get("threads", []) for m in (t["root"], *t.get("replies", []))]
    joined = None
    for m in sorted(messages, key=lambda m: m.get("timestamp", 0)):
        if (m.get("sender_name") or m.get("sender")) != agent:
            continue
        if m.get("kind") == "room_join":
            joined = m.get("timestamp", 0)
            continue
        if joined is not None and m.get("timestamp", 0) - joined < 2_000:
            continue
        if not m.get("body", "").lstrip().startswith("@"):
            return True
    return False


def digest(card):
    return hashlib.sha256(card.encode()).hexdigest()


async def handle(gate, event, command, sender, mode):
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

    if isinstance(command, (c.AskOwner, c.Propose)):
        detail = await client.get_room_detail(event.room_id)
        name = detail.get("name", detail.get("room_name", ""))
        friends = [p for p in name.removeprefix("dm-").split("-")[:2] if p != person]
        if isinstance(command, c.Propose) and (not name.startswith("dm-") or len(friends) != 1):
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
            if sender.id == main_agent(person) and not await _friend_spoke(
                client, event.room_id, main_agent(friend)
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
            await refuse(f"{ref} is already used for this person; choose a fresh ID in both gates")
            return  # IDs are never rebound to a different plan or room.
        state[ref] = {
            "room": event.room_id,
            "friend": friend,
            "card": card,
            "votes": {},
            "status": "pending",
        }
        save(person, state)
        await relay.post_home(
            person, f"{ref}: {card} · reply @{person}-gate answer {ref} …", client=client
        )
        if isinstance(command, c.Propose):
            ledger.record(ref, card, friend, event.room_id, "proposal", person=person)
            if sender.id == main_agent(person):
                await client.connect_to_room(event.room_id)
                await client.post_message(f"@{friend}-gate propose {ref} {card}")
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
        await client.connect_to_room(room)
        await client.post_message(f"{ref} answer from {person}: {command.text}")
        ledger.record(ref, command.text.text, friend, room, "answer", person=person)
        item["status"] = "answered"
        save(person, state)
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
    save(person, state)
    if who == person:
        await client.connect_to_room(room)
        await client.post_message(
            f"@{friend}-gate consent {ref} {'yes' if vote else 'no'} {via} {digest(item['card'])}"
        )
    votes = item["votes"]
    if not vote:
        item["status"] = "declined"
        await relay.post_home(person, f"❌ {ref} declined", client=client)
    elif set(votes) == {person, friend} and all(v[0] for v in votes.values()):
        item["status"] = "confirmed"
        labels = " · ".join(
            f"{p.title()} ✅ " + ("via agent" if votes[p][1] == "via-agent" else "direct")
            for p in sorted(votes)
        )
        text = f"✅ {ref}: {item['card']} · {labels}"
        await relay.post_home(person, text, client=client)
        await client.connect_to_room(room)
        await client.create_room_document("plan-" + person + "-" + ref, "Confirmed plan", "", text)
        ledger.record(ref, text, friend, room, "proposal", person=person)
        # The peer must consume the final relay before archive blocks dispatch.
        if who != person:
            await client.archive_room(room)
        if room in gate.watches:
            gate.watches[room].closed = True
            gate.watches[room].save()
    save(person, state)
