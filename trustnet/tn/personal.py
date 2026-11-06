"""Hermes operations shared by CLI and MCP; credentials never leave this module."""

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - the demo runs on macOS and Linux
    fcntl = None

from trustnet.gate.commands import Answer, Dm, Quoted
from trustnet.gate.dm import main_agent
from trustnet.gate.facts import REPO_ROOT, load_trust, resolve_data_dir
from trustnet.gate.relay import find_home, home_name
from trustnet.room_pool import wait_until_live
from trustnet.switch_client import SwitchClient, SwitchError

#: How long one session waits for another's first contact to finish.
BOOTSTRAP_WAIT = 10.0


@asynccontextmanager
async def _bootstrap_lock(directory, person):
    """Serialize registration and home bootstrap for one person.

    A watcher and a tool call can start together on a new person. Without the
    lock both would register the same name and create rival homes.
    """
    if fcntl is None:
        yield
        return
    path = directory / f"{person}.lock"
    path.touch(mode=0o600, exist_ok=True)
    with path.open("a") as handle:
        deadline = asyncio.get_running_loop().time() + BOOTSTRAP_WAIT
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if asyncio.get_running_loop().time() >= deadline:
                    raise SwitchError(f"another session is still starting {person}") from None
                await asyncio.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


@asynccontextmanager
async def session(person):
    base = os.environ.get("TN_STATE_DIR") or os.environ.get("TN_DATA_DIR")
    directory = (Path(base).expanduser() if base else REPO_ROOT / "data") / "main-agents"
    if not directory.is_absolute():
        directory = REPO_ROOT / directory
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / f"{person}.json"
    url = os.environ["SWITCH_URL"]
    async with _bootstrap_lock(directory, person):
        if path.exists():
            state = json.loads(path.read_text())
            client = SwitchClient(url, state["id"], state["api_key"])
        else:
            client = await SwitchClient.register(
                url,
                os.environ[f"{person.upper()}_GATE_KEY"],
                main_agent(person),
                agent_type="codex",
            )
            path.touch(mode=0o600)
            path.write_text(json.dumps({"id": client.agent_id, "api_key": client.api_key}))

        async def drain():
            async for _ in client.events():
                pass

        stream = asyncio.create_task(drain())
        try:
            await asyncio.wait_for(client.ready.wait(), 15)
            # First contact: a new person has no home until their agent asks for it.
            await home(person, client)
        except BaseException:
            stream.cancel()
            await asyncio.gather(stream, return_exceptions=True)
            await client.aclose()
            raise
    try:
        yield client
    finally:
        stream.cancel()
        await asyncio.gather(stream, return_exceptions=True)
        await client.aclose()


async def home(person, client):
    """Return the person's private home, bootstrapping it on first contact.

    The gate also creates a home when it starts first, but that room cannot be
    seen by an agent that is not a member yet. So when the agent sees no home it
    creates one and invites its gate. A look-alike home holding another owner's
    agent is refused rather than joined or recreated: private notes must never
    land in a stranger's room.
    """
    name = home_name(person)
    gate = person + "-gate"
    agent = main_agent(person)
    chosen, safe, blocked = await find_home(
        client, person, own_names={gate, agent}, agent_name=agent
    )
    if chosen is None:
        if blocked:
            foreign = sorted({member for _room, members in blocked for member in members})
            raise SwitchError(
                f"refusing {name}: it holds another owner's agent ({', '.join(foreign)})"
            )
        result = await client.create_room(
            name,
            "Trust network home",
            [agent],
            internal_only=True,
            read_visibility="private",
            write_visibility="private",
        )
        chosen = result.get("room_id", result.get("id"))
        names = {agent}
    else:
        names = next(names for room, names in safe if room == chosen)
    if gate not in names:
        try:
            await client.invite_agent_to_room(chosen, gate)
        except (SwitchError, ValueError) as exc:
            raise SwitchError(
                f"{gate} must be registered before {person}'s home can be used"
            ) from exc
    await client.connect_to_room(chosen)
    return chosen


async def inbox(person, consume=True):
    """Return unread home threads; persist consumed message IDs unless peeking."""
    path = resolve_data_dir(person) / "inbox-cursor.json"
    seen = set(json.loads(path.read_text())) if path.exists() else set()
    async with session(person) as client:
        room = await home(person, client)
        context = await client.read_context(room_id=room, limit=200)
    threads = context.get("threads", [])
    unread = [t for t in threads if t["root"]["id"] not in seen]
    if consume:
        seen.update(t["root"]["id"] for t in unread)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(mode=0o600)
        path.write_text(json.dumps(sorted(seen)))
    return {"room": room, "threads": unread, "open": open_items(person)}


#: Wall time, as the gate reads it live (tests point this at their gate clock).
_now = time.time


def open_items(person):
    """What still waits for the person's answer, read or not.

    A watcher reads the inbox to tell the person about a question; the person
    replies later, often without the reference. Unread threads alone would be
    empty by then, so the agent couldn't answer. These come from the gate's own
    state: ask-around questions from friends not yet answered or expired, the
    agent's own questions (Q#) not yet answered, and proposals (P#) still
    waiting for this person's vote.
    """
    directory = resolve_data_dir(person)

    def read(name):
        path = directory / name
        return json.loads(path.read_text()) if path.exists() else {}

    items = [
        {"ref": v["local"], "kind": "ask-around", "from": v["peer"], "question": v["question"]}
        for v in read("ask-around.json").values()
        if v.get("local") and v.get("answered") is False and v.get("expires", 0) > _now()
    ]
    for ref, v in read("coordination.json").items():
        if v.get("status") != "pending":
            continue
        if ref.startswith("Q"):
            items.append({"ref": ref, "kind": "question", "question": v["card"]})
        elif person not in v.get("votes", {}):
            items.append({"ref": ref, "kind": "proposal", "with": v["friend"], "plan": v["card"]})
    from trustnet.gate.fact_changes import review

    return items + review(person)


async def watch(person):
    """Report what needs the agent now, without consuming the inbox.

    Unread home threads, plus each active DM room whose newest message is someone
    else's and changed since the previous watch. Only the newest DM message IDs are
    remembered (``watch-state.json``), so a room wakes the agent once per change.
    """
    path = resolve_data_dir(person) / "watch-state.json"
    last = json.loads(path.read_text()) if path.exists() else {}
    unread = (await inbox(person, consume=False))["threads"]
    newest, updates = {}, []
    async with session(person) as client:
        detail = await client.get_agent_detail(client.agent_id)
        for membership in detail["rooms"]:
            if not membership["room_name"].startswith("dm-") or membership.get("archived"):
                continue
            rid = membership["room_id"]
            context = await client.read_context(room_id=rid, limit=50)
            messages = [
                m for t in context.get("threads", []) for m in (t["root"], *t.get("replies", []))
            ]
            if not messages:
                continue
            latest = max(messages, key=lambda m: m.get("timestamp", 0))
            newest[rid] = latest["id"]
            if latest["id"] != last.get(rid) and latest.get("sender_name") != main_agent(person):
                updates.append(
                    {
                        "room": rid,
                        "name": membership["room_name"],
                        "from": latest.get("sender_name"),
                        "text": latest["body"][:280],
                    }
                )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600)
    path.write_text(json.dumps(newest))
    return {"inbox_unread": len(unread), "dm_updates": updates}


def known_friend(person: str, friend: str) -> str:
    """Return a listed friend's key.

    The gate silently ignores a `dm` for someone not on the trust list, so the
    tool refuses it here instead: an agent that gets an event id back would
    wait forever for a room that will never open.
    """
    key = Dm(person=friend, goal=Quoted("Friend check")).person
    if load_trust(person).level_for(key) is None:
        raise SwitchError(f"no friend named {key}; add them to {person}'s trust list first")
    return key


async def answer(person, id, text):
    """Send an answer as the registered Hermes; the gate authenticates consent."""
    command = Answer(reference=id, text=Quoted(text))
    if command.reference.startswith("P") and command.text.text.strip().lower() not in {
        "yes",
        "no",
    }:
        raise ValueError('a proposal answer must be "yes" or "no"')
    async with session(person) as client:
        await client.connect_to_room(await home(person, client))
        return await client.post_message(
            f"@{person}-gate answer {command.reference} {command.text}"
        )


async def dm(person, friend, goal):
    """Request a DM through the owner's gate from their home membership."""
    command = Dm(person=known_friend(person, friend), goal=Quoted(goal))
    async with session(person) as client:
        await client.connect_to_room(await home(person, client))
        return await client.post_message(f"@{person}-gate dm {command.person} {command.goal}")


async def dm_operate(person, room, text=None):
    async with session(person) as client:
        detail = await client.get_agent_detail(client.agent_id)
        rooms = [r for r in detail["rooms"] if room in (r["room_id"], r["room_name"])]
        if not rooms or not rooms[0]["room_name"].startswith("dm-") or rooms[0].get("archived"):
            raise SwitchError("An active DM membership is required")
        rid = rooms[0]["room_id"]
        await client.connect_to_room(rid)
        if text is not None:
            await wait_until_live(client, rid, text)
            return await client.post_message(text)
        return await client.read_context(room_id=rid)


async def dm_read(person, room):
    return await dm_operate(person, room)


async def dm_post(person, room, text):
    return await dm_operate(person, room, text)


async def ask_around(person: str, question: str):
    """Ask the owner gate to fan out a quoted question to listed friends."""
    quoted = Quoted(question)
    async with session(person) as client:
        await client.connect_to_room(await home(person, client))
        return await client.post_message(f"@{person}-gate ask-around {quoted}")


async def ask(person: str, friend: str, fields: list[str]):
    """Ask a friend's gate through a DM at its room trust level."""
    from trustnet.gate.commands import Ask

    command = Ask(facts=tuple(fields))
    friend = known_friend(person, friend)
    await dm(person, friend, "Facts request")
    pair = "-".join(sorted((person, friend)))
    async with session(person) as client:
        for _ in range(150):
            detail = await client.get_agent_detail(client.agent_id)
            rooms = [
                r
                for r in detail["rooms"]
                if r["room_name"].startswith(f"dm-{pair}-facts-request") and not r.get("archived")
            ]
            if rooms:
                room = rooms[-1]["room_id"]
                await client.connect_to_room(room)
                line = f"@{friend}-gate ask {' '.join(command.facts)}"
                await wait_until_live(client, room, line)
                result = await client.post_message(line)
                return {"room": room, "message": result}
            await asyncio.sleep(0.1)
    raise SwitchError("Timed out waiting for facts DM membership")


async def _gift(person, friend, action, **values):
    import uuid

    friend = known_friend(person, friend)
    token = uuid.uuid4().hex
    request = {"friend": friend, "token": token, "action": action, **values}
    async with session(person) as client:
        room = await home(person, client)
        await client.connect_to_room(room)
        await client.post_message(f"@{person}-gate gift-request " + json.dumps(request))
        prefix = f"gift-result {token} "
        for _ in range(200):
            context = await client.read_context(room_id=room, limit=200)
            for thread in context.get("threads", []):
                root = thread["root"]
                text = root.get("body", root.get("text", ""))
                if text.startswith(prefix):
                    result = json.loads(text[len(prefix) :])
                    if "error" in result:
                        raise SwitchError(result["error"])
                    return result
            await asyncio.sleep(0.15)
    raise SwitchError("Timed out waiting for gift gate response")


async def gift_ideas(person: str, friend: str, occasion: str, date: str, budget: int):
    from trustnet.gate.commands import GiftIdeas, parse

    command = parse(f"gift-ideas {occasion} {date} budget<={budget}")
    if not isinstance(command, GiftIdeas):
        raise ValueError("Invalid gift request")
    return await _gift(
        person,
        friend,
        "ideas",
        occasion=command.occasion,
        date=command.on.isoformat(),
        budget=command.budget,
    )


async def claim(person: str, friend: str, item: str):
    from trustnet.gate.commands import Claim

    return await _gift(person, friend, "claim", item=Claim(item=item).item)
