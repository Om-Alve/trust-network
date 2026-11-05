import json
from pathlib import Path

import httpx
import pytest
import websockets

from trustnet.switch_client import SwitchClient, SwitchError, parse_event


@pytest.mark.parametrize("sender_kind", ["agent", "user", "platform", "unknown"])
def test_frames(sender_kind):
    frame = json.loads((Path("tests/data/switch_frames") / f"{sender_kind}.json").read_text())
    event = parse_event(frame)
    assert (event.room_id, event.sender_id, event.sender_kind, event.text, event.addressed) == (
        "room-1",
        "sender-1",
        sender_kind,
        "@gate hello",
        True,
    )


async def test_timeout_and_payload():
    client = SwitchClient("http://switch", "gate", "secret", timeout=1)

    async def handle(request):
        assert request.url.path == "/agents/gate/ops/post_message"
        assert json.loads(request.content) == {"body": "hello", "thread_id": None}
        raise httpx.ReadTimeout("drop", request=request)

    await client.http.aclose()
    client.http = httpx.AsyncClient(base_url="http://switch", transport=httpx.MockTransport(handle))
    with pytest.raises(SwitchError, match="post_message timed out.*outcome unknown"):
        await client.post_message("hello")
    await client.aclose()


async def test_reconnect():
    connections = []

    async def serve(socket):
        connections.append(socket.request.path)
        await socket.send(
            json.dumps({"event": "connection_state", "data": {"rooms": ["room-1"], "cursor": 0}})
        )
        if len(connections) == 1:
            await socket.close(code=1011)
        else:
            frame = json.loads(Path("tests/data/switch_frames/agent.json").read_text())
            await socket.send(json.dumps(frame))
            await socket.wait_closed()

    async with websockets.serve(serve, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        client = SwitchClient(f"http://127.0.0.1:{port}", "gate", "secret", backoff=0.001)
        stream = client.events()
        import asyncio

        event = await asyncio.wait_for(anext(stream), 2)
        assert event.sender_kind == "agent"
        assert len(connections) == 2
        assert "rooms=room-1" in connections[1]
        assert "start_from=0" in connections[1]
        await stream.aclose()
        await client.aclose()
