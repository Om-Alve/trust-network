"""Switch wire client. Operation signatures follow upstream definitions (see phase 03 log)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import websockets


class SwitchError(RuntimeError):
    """An operation failed or the event stream cannot safely continue."""


@dataclass(frozen=True)
class Event:
    room_id: str
    sender_id: str
    sender_kind: str
    text: str
    addressed: bool


def parse_event(frame: dict[str, Any]) -> Event | None:
    if frame.get("event") != "message":
        return None
    data = frame["data"]
    payload = data["payload"]
    if not isinstance(payload.get("addressed"), bool):
        raise SwitchError("Message has no boolean addressed field")
    # Core 0.31.0 emits null for ordinary senders and transport IDs, not participant UUIDs.
    # Keep unknown explicit; authorization must resolve identity before trusting it.
    return Event(
        data["room_id"],
        payload["sender"],
        payload.get("sender_kind") or "unknown",
        payload["body"],
        payload["addressed"],
    )


class Operations:
    """Shared typed operation facade; room-scoped calls use the connected session."""

    async def _op(self, name: str, arguments: dict[str, Any]) -> Any:
        raise NotImplementedError

    async def post_message(self, body: str, thread_id: str | None = None) -> Any:
        return await self._op("post_message", {"body": body, "thread_id": thread_id})

    async def create_room(
        self,
        name: str,
        description: str,
        agent_names: list[str],
        user_names: list[str] | None = None,
        channel_type: str | None = None,
        bridge_id: str | None = None,
        internal_only: bool = False,
        admin_mode: bool = False,
        security_config: dict[str, Any] | None = None,
        instructions: str | None = None,
        reference_ids: list[str] | None = None,
        package_ids: list[str] | None = None,
        linked_rooms: list[dict[str, str]] | None = None,
        read_visibility: str = "public",
        write_visibility: str = "public",
        group_name: str | None = None,
        roles: list[dict[str, Any]] | None = None,
        include_subagents_for: list[str] | None = None,
        join_event_listeners: list[str] | None = None,
        aliases: dict[str, str] | None = None,
    ) -> Any:
        return await self._op(
            "create_room",
            {
                "name": name,
                "description": description,
                "agent_names": agent_names,
                "user_names": user_names,
                "channel_type": channel_type,
                "bridge_id": bridge_id,
                "internal_only": internal_only,
                "admin_mode": admin_mode,
                "security_config": security_config,
                "instructions": instructions,
                "reference_ids": reference_ids,
                "package_ids": package_ids,
                "linked_rooms": linked_rooms,
                "read_visibility": read_visibility,
                "write_visibility": write_visibility,
                "group_name": group_name,
                "roles": roles,
                "include_subagents_for": include_subagents_for,
                "join_event_listeners": join_event_listeners,
                "aliases": aliases,
            },
        )

    async def invite_agent_to_room(
        self, room_id: str, agent_name: str, include_subagents: bool = False
    ) -> Any:
        return await self._op(
            "invite_agent_to_room",
            {"room_id": room_id, "agent_name": agent_name, "include_subagents": include_subagents},
        )

    async def connect_to_room(self, room_id: str, include_general_instructions: bool = True) -> Any:
        return await self._op(
            "connect_to_room",
            {"room_id": room_id, "include_general_instructions": include_general_instructions},
        )

    async def list_participants(self) -> Any:
        return await self._op("list_participants", {})

    async def get_agent_detail(self, agent_id: str) -> Any:
        return await self._op("get_agent_detail", {"agent_id": agent_id})

    async def get_room_detail(self, room_id: str) -> Any:
        return await self._op("get_room_detail", {"room_id": room_id})

    async def archive_room(self, room_id: str) -> Any:
        return await self._op("archive_room", {"room_id": room_id})

    async def create_agent(
        self,
        name: str,
        description: str,
        machine: str,
        provider: str,
        model: str | None = None,
        advanced_config: dict[str, Any] | None = None,
        instructions: str = "",
        directory: str | None = None,
        auto_mode: bool = True,
        auto_approve: bool = False,
        display_name: str | None = None,
        icon_url: str | None = None,
        start: bool = True,
    ) -> Any:
        return await self._op(
            "create_agent",
            {
                "name": name,
                "description": description,
                "machine": machine,
                "provider": provider,
                "model": model,
                "advanced_config": advanced_config,
                "instructions": instructions,
                "directory": directory,
                "auto_mode": auto_mode,
                "auto_approve": auto_approve,
                "display_name": display_name,
                "icon_url": icon_url,
                "start": start,
            },
        )

    async def update_agent_detail(
        self,
        agent_id: str,
        name: str | None = None,
        description: str | None = None,
        display_name: str | None = None,
        icon_url: str | None = None,
        addressing: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        advanced_config: dict[str, Any] | None = None,
        instructions: str | None = None,
        auto_mode: bool | None = None,
        auto_approve: bool | None = None,
        directory: str | None = None,
        isolation: str | None = None,
        machine: str | None = None,
        desired_state: str | None = None,
    ) -> Any:
        return await self._op(
            "update_agent_detail",
            {
                "agent_id": agent_id,
                "name": name,
                "description": description,
                "display_name": display_name,
                "icon_url": icon_url,
                "addressing": addressing,
                "provider": provider,
                "model": model,
                "advanced_config": advanced_config,
                "instructions": instructions,
                "auto_mode": auto_mode,
                "auto_approve": auto_approve,
                "directory": directory,
                "isolation": isolation,
                "machine": machine,
                "desired_state": desired_state,
            },
        )

    async def create_room_document(
        self, name: str, description: str, instructions: str, content: str
    ) -> Any:
        return await self._op(
            "create_room_document",
            {
                "name": name,
                "description": description,
                "instructions": instructions,
                "content": content,
            },
        )

    async def update_room_document(
        self,
        document_id: str,
        name: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        content: str | None = None,
    ) -> Any:
        return await self._op(
            "update_room_document",
            {
                "document_id": document_id,
                "name": name,
                "description": description,
                "instructions": instructions,
                "content": content,
            },
        )

    async def read_context(
        self,
        limit: int = 50,
        since: str | None = None,
        before: str | None = None,
        room_id: str | None = None,
    ) -> Any:
        return await self._op(
            "read_context", {"limit": limit, "since": since, "before": before, "room_id": room_id}
        )


class SwitchClient(Operations):
    def __init__(
        self,
        base_url: str,
        agent_id: str,
        api_key: str,
        *,
        timeout: float = 15,
        backoff: float = 0.25,
        max_backoff: float = 15,
    ):
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.connection_id = str(uuid4())
        self.http = httpx.AsyncClient(
            base_url=self.base_url + "/",
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        self.api_key = api_key
        self.timeout = timeout
        self.backoff = backoff
        self.max_backoff = max_backoff
        self.cursor: int | str = "head"
        self.rooms: list[str] = []
        self.ready = asyncio.Event()

    @classmethod
    async def register(
        cls,
        base_url: str,
        registration_key: str,
        name: str,
        *,
        agent_type: str,
        description: str = "",
        options: dict | None = None,
        timeout: float = 15,
    ) -> SwitchClient:
        async with httpx.AsyncClient(timeout=timeout) as http:
            try:
                response = await http.post(
                    base_url.rstrip("/") + "/agents/register-known",
                    headers={"Authorization": f"Bearer {registration_key}"},
                    json={
                        "agent_type": agent_type,
                        "name": name,
                        "description": description,
                        "options": options or {},
                    },
                )
                response.raise_for_status()
            except httpx.TimeoutException as exc:
                raise SwitchError("Registration timed out") from exc
            except httpx.HTTPError as exc:
                raise SwitchError(
                    "Registration failed; check bridge URL, key and agent name"
                ) from exc
        data = response.json()
        return cls(base_url, data["id"], data["api_key"], timeout=timeout)

    async def aclose(self) -> None:
        await self.http.aclose()

    async def _op(self, name: str, arguments: dict[str, Any]) -> Any:
        try:
            response = await self.http.post(
                f"agents/{self.agent_id}/ops/{name}",
                headers={"X-Switch-Connection-Id": self.connection_id},
                json=arguments,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise SwitchError(f"{name} timed out after {self.timeout}s; outcome unknown") from exc
        except httpx.HTTPStatusError as exc:
            raise SwitchError(f"{name} failed: HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise SwitchError(f"{name} transport failed; outcome unknown") from exc
        return response.json()["result"]

    async def events(self) -> AsyncIterator[Event]:
        delay = self.backoff
        while True:
            params = urlencode(
                {
                    "connection_id": self.connection_id,
                    "scope": "all",
                    "filter": "all",
                    "start_from": self.cursor,
                    "rooms": ",".join(self.rooms),
                }
            )
            url = self.base_url.replace("https://", "wss://").replace("http://", "ws://")
            try:
                async with websockets.connect(
                    f"{url}/agents/{self.agent_id}/connection/ws?{params}",
                    additional_headers={"Authorization": f"Bearer {self.api_key}"},
                    open_timeout=self.timeout,
                ) as socket:
                    async for raw in socket:
                        frame = json.loads(raw)
                        kind, data = frame["event"], frame["data"]
                        if kind == "ping":
                            await socket.send(json.dumps({"type": "pong", "cursor": self.cursor}))
                            continue
                        if kind in {"refused", "gap", "evicted"}:
                            raise SwitchError(f"Stream {kind}: {data}")
                        if kind == "connection_state":
                            self.rooms = data["rooms"]
                            self.cursor = data["cursor"]
                            delay = self.backoff
                            self.ready.set()
                        if "id" in frame:
                            self.cursor = frame["id"]
                        event = parse_event(frame)
                        if event is not None:
                            yield event
            except (OSError, TimeoutError, websockets.ConnectionClosed):
                pass
            await asyncio.sleep(delay)
            delay = min(delay * 2, self.max_backoff)
