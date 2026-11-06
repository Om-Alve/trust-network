"""Bounded lifecycle for agent-only DM rooms: close after too many turns or too long."""

import asyncio
import json
import time

from trustnet.gate.facts import resolve_data_dir
from trustnet.gate.relay import post_home

# A DM room closes after this many main-agent turns or seconds, whichever comes first.
# Both Hermes wake on a 1-minute watcher and wait on their people, so 10 minutes was
# too short for one plan; 30 minutes still bounds an agent-to-agent loop.
MAX_TURNS = 20
MAX_SECONDS = 1800


class ConversationWatch:
    def __init__(self, room, owner, client, *, clock=time.time, persistent=False):
        self.room, self.owner, self.client = room, owner, client
        self.clock, self.started = clock, clock()
        self.turns = []
        self.closed = False
        self.lock = asyncio.Lock()
        self.path = (
            resolve_data_dir(owner) / "room-watches" / f"{room}.json" if persistent else None
        )
        if self.path and self.path.exists():
            state = json.loads(self.path.read_text())
            self.started, self.turns, self.closed = (
                state["started"],
                state["turns"],
                state["closed"],
            )
        self.save()

    def save(self):
        """Keep deadlines and closure across restarts; never reset a room's limits."""
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp = self.path.with_suffix(".tmp")
        temp.touch(mode=0o600)
        temp.write_text(
            json.dumps({"started": self.started, "turns": self.turns, "closed": self.closed})
        )
        temp.replace(self.path)

    async def turn(self, text):
        if not self.closed:
            self.turns.append(text)
            self.save()
        await self.check()

    async def check(self):
        async with self.lock:
            if self.closed or (
                len(self.turns) < MAX_TURNS and self.clock() - self.started < MAX_SECONDS
            ):
                return
            summary = f"Conversation {self.room} ended after {len(self.turns)} agent turns. "
            summary += "Latest messages: " + " | ".join(t[:300] for t in self.turns[-2:])
            await post_home(self.owner, summary, client=self.client)
            await self.client.archive_room(self.room)
            self.closed = True
            self.save()
