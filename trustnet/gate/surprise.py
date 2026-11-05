"""Gate-only gift conversations, owner-safe views and courtesy seals."""

import json
import uuid
from datetime import date, datetime, timedelta

from trustnet.gate import commands as c
from trustnet.gate import ledger, relay
from trustnet.gate.facts import Level, load_profile, load_trust, resolve_data_dir
from trustnet.gate.policy import visible_facts
from trustnet.gate.view_as import Claim, _hidden_items, _hide_claimed


def read(person, name):
    path = resolve_data_dir(person) / name
    return json.loads(path.read_text()) if path.exists() else {}


def save(person, name, value):
    path = resolve_data_dir(person) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.touch(mode=0o600)
    temporary.write_text(json.dumps(value))
    temporary.replace(path)


def claims(person):
    return [
        Claim(v["item"], date.fromisoformat(v["reveal_after"]))
        for v in read(person, "claims.json").values()
    ]


def owner_value(person, name, value, now=None):
    if name != "wishlist":
        return value
    from trustnet.gate.calendar import TIME_ZONE

    return _hide_claimed(value, _hidden_items(claims(person), now or datetime.now(TIME_ZONE)))


async def handle(gate, event, sender, level, detail):
    """Intercept gift traffic after fresh membership/ownership checks."""
    person, client = gate.person, gate.client
    name = (detail or {}).get("name", (detail or {}).get("room_name", "")).lstrip("#")
    body = event.text.removeprefix(f"@{person}-gate ").strip()
    sessions = read(person, "gift-sessions.json")
    if body.startswith("gift-request "):
        if level != Level.SELF or sender.id != person + "-hermes" or name != person + "-home":
            return True
        request = json.loads(body[len("gift-request ") :])
        friend, token = request["friend"], request["token"]
        c.Dm(person=friend, goal=c.Quoted("Gift request"))
        if (
            not isinstance(token, str)
            or len(token) != 32
            or any(ch not in "0123456789abcdef" for ch in token)
        ):
            return True
        if friend == person or load_trust(person).level_for(friend) is None:
            await relay.post_home(
                person,
                f"gift-result {token} " + json.dumps({"error": "Friend membership required"}),
                client=client,
            )
            return True
        if request["action"] == "ideas":
            command = c.parse(
                f"gift-ideas {request['occasion']} {request['date']} budget<={request['budget']}"
            )
            if not isinstance(command, c.GiftIdeas):
                return True
            room_name = f"gift-{person}-{friend}-{uuid.uuid4().hex[:12]}"
            result = await client.create_room(
                room_name,
                "Gift courtesy seal",
                [person + "-gate"],
                internal_only=True,
                read_visibility="private",
                write_visibility="private",
            )
            room = result.get("room_id", result.get("id"))
            await client.connect_to_room(room)
            await client.invite_agent_to_room(room, friend + "-gate")
            sessions[room] = {
                "friend": friend,
                "expires": gate._now().timestamp() + 600,
                "token": token,
                "role": "asker",
            }
            save(person, "gift-sessions.json", sessions)
            await client.post_message(
                f"@{friend}-gate gift-ideas {command.occasion} {command.on.isoformat()} budget<={command.budget}"
            )
        elif request["action"] == "claim":
            active = [
                (r, v)
                for r, v in sessions.items()
                if v["role"] == "asker"
                and v["friend"] == friend
                and not v.get("closed")
                and v["expires"] > gate._now().timestamp()
            ]
            if not active:
                await relay.post_home(
                    person,
                    f"gift-result {token} " + json.dumps({"error": "Request gift ideas first"}),
                    client=client,
                )
                return True
            room, entry = active[-1]
            command = c.Claim(item=request["item"])
            entry["token"] = token
            save(person, "gift-sessions.json", sessions)
            await client.connect_to_room(room)
            await client.post_message(f'@{friend}-gate claim "{command.item}"')
        return True
    if not relay.is_gift_room(detail or {}):
        return False
    # Refuse ordinary fact requests without falling through to owner relays.
    if body.startswith("ask "):
        command = c.parse(event.text)
        if isinstance(command, c.Ask):
            await client.post_message(
                "\n".join(f"{field}: not shared with you" for field in command.facts)
            )
            for field in command.facts:
                await gate._overreach(event, sender, f"fact:{field}", "Gift room fact request")
        return True
    # No general command, owner fallback, consent relay or home alert can run here.
    if sender.id != (sender.person or "") + "-gate" or sender.person == person:
        return True
    if body.startswith("gift-result "):
        entry = sessions.get(event.room_id)
        if (
            not entry
            or entry["role"] != "asker"
            or entry["friend"] != sender.person
            or entry.get("closed")
        ):
            return True
        payload = json.loads(body[len("gift-result ") :])
        await relay.post_home(
            person, f"gift-result {entry['token']} " + json.dumps(payload), client=client
        )
        if payload.get("status") == "claimed":
            entry["closed"] = True
            save(person, "gift-sessions.json", sessions)
            await client.archive_room(event.room_id)
        return True
    if not name.startswith(f"gift-{sender.person}-{person}-"):
        return True
    command = c.parse(event.text, now=gate._now())
    values = visible_facts(load_profile(person), level)
    taken = read(person, "claims.json")
    if isinstance(command, c.GiftIdeas):
        if event.room_id in sessions:
            return True
        reveal = command.on + timedelta(days=1)
        items = []
        unavailable = []
        over = []
        for item in values.get("wishlist", []):
            if item["item"].casefold() in taken:
                unavailable.append({"item": item["item"], "status": "taken"})
            elif command.budget is not None and item["price"] > command.budget:
                over.append({**item, "status": "over budget"})
            else:
                items.append(item)
        payload = {
            "suggestions": items,
            "taken": unavailable,
            "over_budget": over,
            **{k: values[k] for k in ("interests", "sizes") if k in values},
        }
        sessions[event.room_id] = {
            "role": "recipient",
            "friend": sender.person,
            "reveal_after": reveal.isoformat(),
            "offered": [i["item"] for i in items],
            "expires": gate._now().timestamp() + 600,
        }
        save(person, "gift-sessions.json", sessions)
        ledger.record(
            "gift ideas",
            payload,
            sender.person,
            event.room_id,
            "gift",
            person=person,
            sealed_until=reveal,
            now=gate._now(),
        )
    elif isinstance(command, c.Claim):
        entry = sessions.get(event.room_id)
        if (
            not entry
            or entry["role"] != "recipient"
            or entry["friend"] != sender.person
            or entry["expires"] <= gate._now().timestamp()
        ):
            return True
        key = command.item.casefold()
        permitted = [i["item"] for i in values.get("wishlist", [])]
        if command.item not in entry["offered"] or command.item not in permitted or key in taken:
            payload = {"error": "Item unavailable"}
        else:
            taken[key] = {
                "item": command.item,
                "claimer": sender.person,
                "reveal_after": entry["reveal_after"],
            }
            save(person, "claims.json", taken)
            payload = {"status": "claimed", "item": command.item}
    else:
        return True
    await client.post_message(f"@{sender.person}-gate gift-result " + json.dumps(payload))
    return True


async def expire(gate):
    sessions = read(gate.person, "gift-sessions.json")
    changed = False
    for room, entry in sessions.items():
        if not entry.get("closed") and entry["expires"] <= gate._now().timestamp():
            await gate.client.archive_room(room)
            entry["closed"] = True
            changed = True
    if changed:
        save(gate.person, "gift-sessions.json", sessions)
