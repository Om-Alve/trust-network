"""Hermes operations shared by CLI and MCP; credentials never leave this module."""

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - the demo runs on macOS and Linux
    fcntl = None

from trustnet.gate.commands import Answer, Dm, Quoted
from trustnet.gate.dm import main_agent
from trustnet.gate.facts import REPO_ROOT, load_trust, resolve_data_dir
from trustnet.gate.messages import is_gate_traffic, join_greeting_ids
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
    from trustnet.gate import calendar_jobs, group_plans
    from trustnet.gate.fact_changes import review

    for plan in group_plans.pending(person):
        items.append(
            {
                "ref": plan["id"],
                "kind": "group-plan",
                "participants": plan["participants"],
                "revision": plan["revision"],
                "fingerprint": plan["fingerprint"],
                "plan": plan["content"],
                "waiting_for": sorted(set(plan["participants"]) - set(plan["votes"])),
            }
        )

    return (
        items
        + review(person)
        + [{"kind": "calendar", **task} for task in calendar_jobs.pending(person)]
    )


def _latest_meaningful(messages):
    """The newest message worth waking on, or ``None``.

    Switch's automatic join greetings and gate-to-gate protocol traffic (plan
    relays, forwarded proposals) are ignored. Both are recognised structurally —
    by sender identity and timing relative to a ``room_join`` — never by their
    words. ``room_join`` events themselves are not messages either.
    """
    greetings = join_greeting_ids(messages)
    meaningful = [
        m
        for m in messages
        if m.get("kind") != "room_join" and m.get("id") not in greetings and not is_gate_traffic(m)
    ]
    return max(meaningful, key=lambda m: m.get("timestamp", 0)) if meaningful else None


async def watch(person):
    """Report what needs the agent now, without consuming the inbox.

    Unread home threads, plus each active DM/group room whose newest *meaningful*
    message is someone else's and changed since the previous watch. Only the
    newest meaningful message ID per room is remembered (``watch-state.json``), so
    a room wakes the agent once per change and ignorable traffic (join greetings,
    gate-to-gate relays) never does.
    """
    path = resolve_data_dir(person) / "watch-state.json"
    last = json.loads(path.read_text()) if path.exists() else {}
    unread = (await inbox(person, consume=False))["threads"]
    newest, updates = {}, []
    async with session(person) as client:
        detail = await client.get_agent_detail(client.agent_id)
        for membership in detail["rooms"]:
            if not membership["room_name"].startswith(("dm-", "group-")) or membership.get(
                "archived"
            ):
                continue
            rid = membership["room_id"]
            context = await client.read_context(room_id=rid, limit=50)
            messages = [
                m for t in context.get("threads", []) for m in (t["root"], *t.get("replies", []))
            ]
            if not messages:
                continue
            latest = _latest_meaningful(messages)
            if latest is None:
                newest[rid] = last.get(rid)
                continue
            newest[rid] = latest["id"]
            if latest["id"] != last.get(rid) and latest.get("sender_name") != main_agent(person):
                updates.append(
                    {
                        "room": rid,
                        "name": membership["room_name"],
                        "from": latest.get("sender_name"),
                        "text": (latest.get("body") or "")[:280],
                    }
                )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600)
    path.write_text(json.dumps(newest))
    from trustnet.gate import calendar_jobs

    tasks = calendar_jobs.pending(person, due_only=True)
    return {"inbox_unread": len(unread), "dm_updates": updates, "calendar_pending": len(tasks)}


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
        if (
            not rooms
            or not rooms[0]["room_name"].startswith(("dm-", "group-", "ask-"))
            or rooms[0].get("archived")
        ):
            raise SwitchError("An active DM membership is required")
        rid = rooms[0]["room_id"]
        card_path = resolve_data_dir(person) / "share-cards" / f"{rid}.json"
        if card_path.exists():
            friend = json.loads(card_path.read_text())["friend"]
            if load_trust(person).level_for(friend) is None:
                raise ValueError(
                    "This friendship is no longer trusted; open a new room after restoring trust"
                )
        await client.connect_to_room(rid)
        if rooms[0]["room_name"].startswith("group-"):
            from trustnet.gate import group_plans

            plan = group_plans.status(person, rooms[0]["room_name"].removeprefix("group-"))
            if not plan or plan["status"] in {"cancelled", "expired"}:
                raise ValueError("This group plan is closed or unknown")
            trust = load_trust(person)
            if any(
                peer != person and trust.level_for(peer) is None for peer in plan["participants"]
            ):
                raise ValueError("A participant is no longer trusted")
            members = {*plan["participants"], *plan.get("former", [])}
            allowed = members | {p + suffix for p in members for suffix in ("-gate", "-hermes")}
            if any(p.get("name") not in allowed for p in await client.list_participants()):
                raise ValueError("Unexpected participant in the group room")
        if text is not None:
            await wait_until_live(client, rid, text)
            return await client.post_message(text)
        return await client.read_context(room_id=rid)


async def dm_read(person, room):
    return await dm_operate(person, room)


async def dm_post(person, room, text):
    from trustnet.tn import outgoing

    if outgoing.mode(person) == "review":
        # Check membership before retaining a draft for an arbitrary room.
        await dm_operate(person, room)
        return outgoing.draft(person, room, text)
    return await dm_operate(person, room, text)


#: How long an audience request may wait for the gate to read it.
ASK_AROUND_REQUEST_TTL = 120


def _around_audience(person: str, audience) -> list[str] | None:
    """Validate an explicit audience, or ``None`` for the legacy all-friends form."""
    if audience is None:
        return None
    values = [audience] if isinstance(audience, str) else list(audience)
    names: list[str] = []
    for raw in values:
        if not isinstance(raw, str) or not raw.strip():
            raise SwitchError("an ask-around audience must be a list of person names")
        if raw.strip().lower() == person:
            raise SwitchError("you cannot ask yourself")
        friend = known_friend(person, raw)
        if friend not in names:
            names.append(friend)
    if not names:
        raise SwitchError("an ask-around needs at least one friend in its audience")
    return names


def _write_audience_request(person: str, question: str, audience: list[str]) -> str:
    """Persist the audience for one gate command and return its ``A<digits>`` token.

    The gate and this tool share the owner's data directory. The token travels
    in the normal fixed command; the gate consumes the matching file and asks
    only that audience. A missing or stale file fails closed at the gate.
    """
    directory = resolve_data_dir(person) / "ask-around-requests"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    now = _now()
    for stale in directory.glob("A*.json"):
        try:
            payload = json.loads(stale.read_text())
            expired = float(payload.get("expires", 0)) < now
        except (OSError, ValueError, TypeError, AttributeError):
            expired = True
        if expired:
            with suppress(OSError):
                stale.unlink()
    number = time.time_ns() % 1_000_000_000
    for _ in range(1000):
        token = f"A{number:09d}"
        if not (directory / f"{token}.json").exists():
            break
        number = (number + 1) % 1_000_000_000
    else:  # pragma: no cover - a full billion-token namespace cannot be reached
        raise SwitchError("could not allocate an ask-around request token")
    payload = {
        "question": question,
        "audience": audience,
        "expires": now + ASK_AROUND_REQUEST_TTL,
    }
    from trustnet.gate.storage import atomic_write

    atomic_write(directory / f"{token}.json", json.dumps(payload))
    return token


async def ask_around(person: str, question: str, audience=None):
    """Ask the owner gate a quoted question, optionally only an explicit audience."""
    quoted = Quoted(question)
    names = _around_audience(person, audience)
    token = _write_audience_request(person, quoted.text, names) if names is not None else None
    async with session(person) as client:
        await client.connect_to_room(await home(person, client))
        prefix = f"@{person}-gate ask-around "
        if token:
            prefix += f"{token} "
        return await client.post_message(prefix + str(quoted))


async def ask(person: str, friend: str, fields: list[str]):
    """Ask a friend's gate for facts, quietly when the friend's gate allows it.

    A facts request must not read as a planning DM. The asker's own gate opens a
    dedicated ``ask-<pair>-*`` room (asker's gate, asker's agent, friend's gate
    only), or reuses the pair's open one, so the friend's agent is never invited
    and the friend's home gets no planning notice. Only a friend whose gate said
    hello without advertising ``join-ask`` falls back to the legacy
    ``dm "Facts request"`` room.
    """
    from trustnet.gate import handshake
    from trustnet.gate.commands import Ask

    command = Ask(facts=tuple(fields))
    friend = known_friend(person, friend)
    pair = "-".join(sorted((person, friend)))
    line = f"@{friend}-gate ask {' '.join(command.facts)}"
    peer = handshake.peer(person, friend)
    # A gate that never said hello gets one right before join-ask, so only a peer
    # known to lack join-ask takes the planning-DM path that invites its agent.
    use_ask_room = peer is None or "join-ask" in peer.get("capabilities", [])
    if not use_ask_room:
        await dm(person, friend, "Facts request")
    async with session(person) as client:
        if use_ask_room:
            prefix = f"ask-{pair}-"
            detail = await client.get_agent_detail(client.agent_id)
            open_rooms = [
                r["room_id"]
                for r in detail["rooms"]
                if r["room_name"].startswith(prefix) and not r.get("archived")
            ]
            if open_rooms:
                # One fact-request room per pair: rooms are never archived, and a
                # gate stays connected to at most 24 rooms.
                room = open_rooms[-1]
                await client.connect_to_room(room)
                await wait_until_live(client, room, line)
                return {"room": room, "message": await client.post_message(line)}
            await client.connect_to_room(await home(person, client))
            await client.post_message(f"@{person}-gate ask-room {friend}")
        else:
            prefix = f"dm-{pair}-facts-request"
        for _ in range(150):
            detail = await client.get_agent_detail(client.agent_id)
            rooms = [
                r
                for r in detail["rooms"]
                if r["room_name"].startswith(prefix) and not r.get("archived")
            ]
            if rooms:
                room = rooms[-1]["room_id"]
                await client.connect_to_room(room)
                await wait_until_live(client, room, line)
                result = await client.post_message(line)
                return {"room": room, "message": result}
            await asyncio.sleep(0.1)
    raise SwitchError("Timed out waiting for facts room membership")


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
