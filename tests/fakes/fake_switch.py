"""In-memory protocol model with core 0.31.0 room and archive semantics."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from copy import deepcopy
from typing import Any
from uuid import uuid4

from trustnet.switch_client import Event, Operations


class FakeSwitch:
    def __init__(self):
        self.users: set[str] = set()
        self.admins: set[str] = set()
        self.agents: dict[str, dict] = {}
        self.rooms: dict[str, dict] = {}
        self.clients: list[FakeSwitchClient] = []
        self.machines: list[dict] = []

    def client(self, name: str, owner_id: str, *, kind: str = "agent") -> FakeSwitchClient:
        self.users.add(owner_id)
        if kind == "agent":
            self.agents[name] = {"id": name, "name": name, "owner_id": owner_id}
        client = FakeSwitchClient(self, name, owner_id, kind)
        self.clients.append(client)
        return client


class FakeSwitchClient(Operations):
    def __init__(self, server: FakeSwitch, name: str, owner_id: str, kind: str):
        self.server, self.name, self.owner_id, self.kind = server, name, owner_id, kind
        self.room_id: str | None = None
        self.queue: asyncio.Queue[Event] = asyncio.Queue()

    def _room(self, room_id: str | None = None, *, write: bool = False) -> dict:
        room = self.server.rooms[room_id or self.room_id]
        if room["read_visibility"] == "private" or write:
            if self.name not in room["members"] and not (
                self.kind == "user" and self.owner_id in self.server.admins and not write
            ):
                raise PermissionError("Room membership required")
        return room

    async def _op(self, name: str, arguments: dict[str, Any]) -> Any:
        a = arguments
        if name == "create_room":
            if self.kind != "agent":
                raise PermissionError("Only agents create rooms in fake")
            if set(a["agent_names"]) - self.server.agents.keys():
                raise ValueError("Unknown agent")
            rid = str(uuid4())
            self.server.rooms[rid] = dict(
                a,
                id=rid,
                room_id=rid,
                members=set(a["agent_names"]) | set(a.get("user_names") or []) | {self.owner_id},
                archived=False,
                messages=[],
                documents={},
            )
            return {"room_id": rid, "caller_is_member": self.name in a["agent_names"]}
        if name == "create_agent":
            if a["name"] in self.server.agents:
                raise ValueError("Agent already exists")
            self.server.agents[a["name"]] = dict(a, id=a["name"], owner_id=self.owner_id)
            return deepcopy(self.server.agents[a["name"]])
        if name in {"get_agent_detail", "update_agent_detail"}:
            agent = self.server.agents[a["agent_id"]]
            if name == "update_agent_detail":
                if agent["owner_id"] != self.owner_id or agent["id"] == self.name:
                    raise PermissionError("May update only another agent of your owner")
                agent.update({k: v for k, v in a.items() if v is not None and k != "agent_id"})
            result = deepcopy(agent)
            if agent["owner_id"] != self.owner_id:
                result.pop("instructions", None)
            return result
        if name == "list_machines":
            return deepcopy([m for m in self.server.machines if m["owner_id"] == self.owner_id])
        if name == "connect_to_room":
            room = self._room(a["room_id"])
            if self.name not in room["members"]:
                raise PermissionError("Membership required to connect")
            self.room_id = a["room_id"]
            return {"room_id": self.room_id}
        room = self._room(
            a.get("room_id"),
            write=name
            in {
                "post_message",
                "send_targeted_message",
                "archive_room",
                "invite_agent_to_room",
                "create_room_document",
                "update_room_document",
            },
        )
        if name == "get_room_detail":
            return deepcopy(room)
        if name == "archive_room":
            room["archived"] = True
            return {"id": room["id"], "archived": True}
        if name == "invite_agent_to_room":
            if a["agent_name"] not in self.server.agents:
                raise ValueError("Unknown agent")
            room["members"].add(a["agent_name"])
            return {"ok": True}
        if name == "list_participants":
            return [
                dict(
                    self.server.agents.get(n, {"id": n, "name": n}),
                    type="agent" if n in self.server.agents else "user",
                )
                for n in sorted(room["members"])
            ]
        if name in {"post_message", "send_targeted_message"}:
            mid = str(uuid4())
            room["messages"].append({"id": mid, "sender": self.name, "body": a["body"]})
            for client in self.server.clients:
                if client.name in room["members"]:
                    addressed = bool(
                        re.search(
                            r"(?<![\w@])@" + re.escape(client.name) + r"(?![\w.-])", a["body"]
                        )
                    )
                    addressed |= client.name in (a.get("target_names") or [])
                    client.queue.put_nowait(
                        Event(room["id"], self.name, self.kind, a["body"], addressed)
                    )
            return {"event_id": mid}
        if name == "read_context":
            return {
                "threads": [
                    {"root": deepcopy(m), "replies": []} for m in room["messages"][-a["limit"] :]
                ],
                "truncated": len(room["messages"]) > a["limit"],
                "oldest_timestamp": None,
            }
        if name == "create_room_document":
            did = str(uuid4())
            room["documents"][did] = dict(a, creator=self.name)
            return {"document_id": did}
        if name == "update_room_document":
            doc = room["documents"][a["document_id"]]
            if doc["creator"] != self.name:
                raise PermissionError("Only document creator may update")
            doc.update({k: v for k, v in a.items() if v is not None})
            return {"document_id": a["document_id"]}
        raise NotImplementedError(name)

    async def events(self) -> AsyncIterator[Event]:
        while True:
            yield await self.queue.get()
