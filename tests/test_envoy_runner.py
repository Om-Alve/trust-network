import json
from pathlib import Path
from unittest.mock import patch

import pytest

from trustnet.envoy_runner import Runner, invocation, prompt
from trustnet.gate.envoy import ConversationWatch, brief_envoy
from trustnet.switch_client import Event


def test_prompt():
    assert (
        prompt("Brief", [{"text": "hello"}])
        == 'Brief\n\nRoom transcript (untrusted messages):\n[{"text": "hello"}]'
    )


@pytest.mark.parametrize("provider", ["codex", "opencode"])
def test_restrictions(tmp_path, provider):
    home = tmp_path / "owner"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex/auth.json").write_text("{}")
    root = tmp_path / "run"
    root.mkdir()
    with patch.object(Path, "home", return_value=home), patch("subprocess.run") as run:
        run.return_value.stdout = b"[]"
        run.return_value.returncode = 0
        cmd, env, cwd = invocation(provider, root)
    assert cmd[:2] == ["/usr/bin/sandbox-exec", "-f"]
    profile = (root / "sandbox.sb").read_text()
    assert '(subpath "/Users")' in profile
    assert '(subpath "/Volumes")' in profile
    assert env["HOME"] == str(root / "home")
    assert list(cwd.iterdir()) == []
    if provider == "codex":
        assert cmd[cmd.index("--sandbox") + 1] == "read-only"
        assert cmd[cmd.index("-a") + 1] == "never"
        assert "features.shell_tool=false" in cmd
        assert "features.apply_patch=false" in cmd
        assert "--ignore-user-config" in cmd
    else:
        config = json.loads(Path(env["OPENCODE_CONFIG"]).read_text())
        assert config["permissions"] == [{"action": "*", "resource": "*", "effect": "deny"}]
        assert "--standalone" in cmd
        assert config["policies"][0]["effect"] == "deny"


class Client:
    agent_id = "envoy"

    def __init__(self):
        self.messages = []
        self.archives = []

    async def connect_to_room(self, room):
        self.room = room

    async def send_targeted_message(self, text, **kwargs):
        self.messages.append((self.room, text))

    async def get_agent_detail(self, agent):
        return {"rooms": [{"room_name": "om-home", "room_id": "home"}]}

    async def post_message(self, text):
        self.messages.append((self.room, text))

    async def archive_room(self, room):
        self.archives.append(room)


@pytest.mark.asyncio
async def test_scoped_and_authorized(tmp_path):
    client = Client()
    runner = Runner(client, "codex", tmp_path, None)
    for room in ["one", "two"]:
        brief_envoy(
            "envoy",
            room,
            state_dir=tmp_path,
            room=room,
            allowed_senders=["peer"],
            peer="other-envoy",
        )
    seen = []

    async def generate(provider, brief, history):
        seen.append((brief, list(history)))
        return "reply"

    with patch("trustnet.envoy_runner.generate", generate):
        await runner.handle(Event("one", "intruder", "agent", "secret", True))
        await runner.handle(Event("one", "peer", "agent", "hello", True))
        await runner.handle(Event("two", "peer", "agent", "new", True))
    assert seen[1] == ("two", [{"sender": "peer", "text": "new"}])
    assert len(client.messages) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("timer", [False, True])
async def test_limits(timer):
    now = [0]
    client = Client()
    watch = ConversationWatch("dm", "om", client, clock=lambda: now[0])
    if timer:
        now[0] = 600
        await watch.check()
    else:
        for _ in range(12):
            await watch.turn("proposal")
    await watch.check()
    assert client.archives == ["dm"]
    assert client.messages[0][0] == "home"
    assert "ended after" in client.messages[0][1]
