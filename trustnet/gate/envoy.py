"""Gate-side registration, brief handoff, and bounded conversation lifecycle."""

import asyncio
import json
import time
from pathlib import Path

from trustnet.gate.relay import post_home
from trustnet.switch_client import SwitchClient


async def ensure_envoy(owner, friend, *, url, key, state_dir):
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = state_dir / "credentials.json"
    if path.exists():
        data = json.loads(path.read_text())
        return SwitchClient(url, data["id"], data["api_key"])
    client = await SwitchClient.register(url, key, f"{owner}-envoy-{friend}", agent_type="codex")
    path.write_text(json.dumps({"id": client.agent_id, "api_key": client.api_key}))
    path.chmod(0o600)
    return client


def brief_envoy(envoy, brief_text, *, state_dir, room, allowed_senders, peer):
    """Call write_brief in the gate first, then hand off its text here."""
    path = Path(state_dir) / f"{room}.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "brief": brief_text,
                "allowed_senders": allowed_senders,
                "peer": peer,
                "expires_at": time.time() + 600,
            }
        )
    )
    temporary.chmod(0o600)
    temporary.replace(path)


async def start_conversation(room, envoy, *, client):
    await client.invite_agent_to_room(room, envoy)


class ConversationWatch:
    def __init__(self, room, owner, client, *, clock=time.monotonic):
        self.room, self.owner, self.client = room, owner, client
        self.clock, self.started = clock, clock()
        self.turns = []
        self.closed = False
        self.lock = asyncio.Lock()

    async def turn(self, text):
        if not self.closed:
            self.turns.append(text)
        await self.check()

    async def check(self):
        async with self.lock:
            if self.closed or (len(self.turns) < 12 and self.clock() - self.started < 600):
                return
            summary = f"Conversation {self.room} ended after {len(self.turns)} envoy turns. "
            summary += "Latest messages: " + " | ".join(t[:300] for t in self.turns[-2:])
            await post_home(self.owner, summary, client=self.client)
            await self.client.archive_room(self.room)
            self.closed = True

    async def run(self):
        while not self.closed:
            await asyncio.sleep(1)
            await self.check()
