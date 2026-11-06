import pytest

from trustnet.gate.watch import MAX_SECONDS, MAX_TURNS, ConversationWatch


class Client:
    agent_id = "om-gate"

    def __init__(self):
        self.messages = []
        self.archives = []

    async def connect_to_room(self, room):
        self.room = room

    async def get_agent_detail(self, agent):
        return {"rooms": [{"room_name": "om-home", "room_id": "home"}]}

    async def post_message(self, text):
        self.messages.append((self.room, text))

    async def archive_room(self, room):
        self.archives.append(room)


@pytest.mark.asyncio
@pytest.mark.parametrize("timer", [False, True])
async def test_limits(timer):
    now = [0]
    client = Client()
    watch = ConversationWatch("dm", "om", client, clock=lambda: now[0])
    if timer:
        now[0] = MAX_SECONDS
        await watch.check()
    else:
        for _ in range(MAX_TURNS):
            await watch.turn("proposal")
    await watch.check()
    assert client.archives == ["dm"]
    assert client.messages[0][0] == "home"
    assert "ended after" in client.messages[0][1]
