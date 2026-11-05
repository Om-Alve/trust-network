"""One Switch connection per room, so a gate has a live session in every room it's in.

Switch delivers a room's addressed messages only to a session connected to that
room. A single connection can hold one room session at a time, so a gate on one
connection is "absent" from every other room. Switch then answers on its behalf
("I don't have a session connected to this room …"), and that notice, sent under
the gate's name, reads to the other gate like a malformed command (a false
overreach alert).

The pool gives every open room its own connection (an anchor) and merges their
events. Ways this can go wrong, and what the pool does about each:

- the same message arrives on several connections → each message is taken only
  from its room's anchor, or from the main connection while that room has none;
- a new room gets addressed before the peer gate has anchored it → posting a line
  addressed to ``@x-gate`` waits (up to ``LIVE_WAIT`` s) until Switch reports that
  gate ``live`` in the room;
- an anchor's stream fails → it's dropped and re-created on the next sync;
- archived rooms keep connections open → the sync closes their anchors.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from typing import Any

from trustnet.switch_client import Event, SwitchClient

LOG = logging.getLogger(__name__)
LIVE_WAIT = 10.0
SYNC_EVERY = 2.0
_ADDRESSED_GATE = re.compile(r"@([a-z0-9][a-z0-9_-]*-gate)\b")


async def wait_until_live(client, room: str, body: str, timeout: float = LIVE_WAIT) -> None:
    """If ``body`` addresses ``@x-gate``, wait until Switch shows that gate live in ``room``.

    Used by the pool and by the personal tools, which post from short-lived
    connections right after a room is created.
    """
    target = _ADDRESSED_GATE.match(body)
    if not target:
        return
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        statuses = (await client.get_room_detail(room) or {}).get("agent_statuses")
        if statuses is None or statuses.get(target.group(1)) == "live":
            return  # a server that doesn't report sessions can't be waited on
        await asyncio.sleep(0.5)
    LOG.warning("%s not live in %s after %ss; posting anyway", target.group(1), room, timeout)


class RoomPool:
    def __init__(self, main: SwitchClient):
        self.main = main
        self.agent_id = main.agent_id
        self.ready = main.ready
        self.anchors: dict[str, SwitchClient] = {}
        self.pumps: dict[str, asyncio.Task] = {}
        self.current: str | None = None
        self.queue: asyncio.Queue = asyncio.Queue()
        self._locks: dict[str, asyncio.Lock] = {}
        self._tasks: list[asyncio.Task] = []

    # --- connections ----------------------------------------------------------

    async def _pump(self, client: SwitchClient, room: str | None) -> None:
        try:
            async for event in client.events():
                if room is None:
                    if event.room_id in self.anchors:
                        continue
                elif event.room_id != room:
                    continue
                await self.queue.put(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if room is None:
                await self.queue.put(exc)
            else:
                LOG.warning("anchor for %s failed: %s", room, type(exc).__name__)
                await self._drop(room)

    async def anchor(self, room: str) -> SwitchClient:
        if room in self.anchors:
            return self.anchors[room]
        async with self._locks.setdefault(room, asyncio.Lock()):
            if room in self.anchors:
                return self.anchors[room]
            client = SwitchClient(self.main.base_url, self.main.agent_id, self.main.api_key)
            pump = asyncio.create_task(self._pump(client, room))
            try:
                await asyncio.wait_for(client.ready.wait(), 20)
                await client.connect_to_room(room)
            except BaseException:
                pump.cancel()
                await asyncio.gather(pump, return_exceptions=True)
                await client.aclose()
                raise
            self.anchors[room], self.pumps[room] = client, pump
            LOG.info("anchored room=%s", room)
            return client

    async def _drop(self, room: str) -> None:
        client, pump = self.anchors.pop(room, None), self.pumps.pop(room, None)
        if pump is not None and pump is not asyncio.current_task():
            pump.cancel()
            await asyncio.gather(pump, return_exceptions=True)
        if client is not None:
            await client.aclose()

    async def sync(self) -> None:
        rooms = (await self.main.get_agent_detail(self.agent_id))["rooms"]
        for room in rooms:
            if room.get("archived"):
                if room["room_id"] in self.anchors:
                    await self._drop(room["room_id"])
            else:
                try:
                    await self.anchor(room["room_id"])
                except Exception as exc:
                    LOG.warning("could not anchor %s: %s", room["room_id"], type(exc).__name__)

    async def _sync_forever(self) -> None:
        while True:
            try:
                await self.sync()
            except Exception as exc:
                LOG.warning("room sync failed: %s", type(exc).__name__)
            await asyncio.sleep(SYNC_EVERY)

    def start(self) -> None:
        self._tasks.append(asyncio.create_task(self._pump(self.main, None)))

    async def start_sync(self) -> None:
        await self.sync()
        self._tasks.append(asyncio.create_task(self._sync_forever()))

    async def aclose(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        for room in list(self.anchors):
            await self._drop(room)
        await self.main.aclose()

    # --- the SwitchAPI surface the gate uses ------------------------------------

    async def events(self) -> AsyncIterator[Event]:
        while True:
            item = await self.queue.get()
            if isinstance(item, Exception):
                raise item
            yield item

    async def connect_to_room(self, room_id: str, include_general_instructions: bool = True):
        await self.anchor(room_id)
        self.current = room_id
        return {"room_id": room_id}

    def _here(self) -> SwitchClient:
        if self.current is None or self.current not in self.anchors:
            return self.main
        return self.anchors[self.current]

    async def post_message(self, body: str, thread_id: str | None = None) -> Any:
        if self.current is not None:
            await wait_until_live(self.main, self.current, body)
        return await self._here().post_message(body, thread_id)

    async def list_participants(self) -> Any:
        return await self._here().list_participants()

    async def create_room_document(self, *args, **kwargs) -> Any:
        return await self._here().create_room_document(*args, **kwargs)

    async def update_room_document(self, *args, **kwargs) -> Any:
        return await self._here().update_room_document(*args, **kwargs)

    async def send_targeted_message(self, *args, **kwargs) -> Any:
        return await self._here().send_targeted_message(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        # Room-independent operations (create/invite/archive/detail/read_context).
        return getattr(self.main, name)
