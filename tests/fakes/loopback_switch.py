"""The Switch wire protocol over HTTP and one WebSocket, backed by a FakeSwitch.

Registration keys are the test's own tokens; every other operation is delegated
to a real ``FakeSwitchClient`` so gates in this process and real clients in
another process or coroutine share state. The WebSocket carries only the
connection state a client waits for before it sends operations; pushed events
are not needed by the callers this adapter serves.
"""

from __future__ import annotations

import asyncio
import json

import uvicorn
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from fakes.fake_switch import FakeSwitch, FakeSwitchClient

__all__ = ["LoopbackSwitch", "serve"]


class LoopbackSwitch:
    def __init__(self, switch: FakeSwitch, keys: dict[str, str]):
        self.switch, self.keys = switch, keys
        self.clients: dict[str, FakeSwitchClient] = {}
        self.registrations: list[str] = []

    def client(self, name: str, person: str) -> FakeSwitchClient:
        if name not in self.clients:
            self.clients[name] = self.switch.client(name, person)
        return self.clients[name]

    def app(self) -> Starlette:
        async def register(request):
            token = _bearer(request.headers.get("authorization", ""))
            person = self.keys.get(token)
            if person is None:
                return Response('{"detail": "bad key"}', status_code=401)
            body = await request.json()
            client = self.client(str(body["name"]), person)
            self.registrations.append(str(body["name"]))
            return _json({"id": client.agent_id, "api_key": token})

        async def operate(request):
            client = self.clients.get(request.path_params["agent_id"])
            if client is None:
                return Response('{"detail": "unknown agent"}', status_code=404)
            try:
                result = await client._op(request.path_params["op"], await request.json())
            except (PermissionError, ValueError, KeyError, NotImplementedError) as exc:
                return Response(json.dumps({"detail": type(exc).__name__}), status_code=400)
            return _json({"result": result})

        async def events(websocket: WebSocket):
            token = _bearer(websocket.headers.get("authorization", ""))
            if token not in self.keys or websocket.path_params["agent_id"] not in self.clients:
                await websocket.close(code=1008)
                return
            await websocket.accept()
            try:
                await websocket.send_json(
                    {"event": "connection_state", "data": {"rooms": [], "cursor": "head"}}
                )
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                return

        return Starlette(
            routes=[
                Route("/agents/register-known", register, methods=["POST"]),
                Route("/agents/{agent_id}/ops/{op}", operate, methods=["POST"]),
                WebSocketRoute("/agents/{agent_id}/connection/ws", events),
            ]
        )


def _bearer(header: str) -> str:
    return header.removeprefix("Bearer ").strip()


def _json(payload) -> Response:
    return Response(json.dumps(payload, default=list), media_type="application/json")


async def serve(app: Starlette):
    """Run uvicorn on a free port in this event loop; return (url, stop)."""
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="off")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    for _ in range(500):
        if server.started:
            break
        await asyncio.sleep(0.01)
    else:  # pragma: no cover - a broken harness, not a product failure
        raise AssertionError("loopback Switch did not start")
    port = server.servers[0].sockets[0].getsockname()[1]

    async def stop():
        server.should_exit = True
        await asyncio.wait_for(task, 10)

    return f"http://127.0.0.1:{port}", stop
