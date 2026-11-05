"""Repeatable cross-machine identity check; writes redacted data/phase16-evidence.json."""

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from scripts.switch_users import CONSOLE_ENV, login, read_env
from trustnet.gate.identity import IdentitySource
from trustnet.gate.runtime import Gate
from trustnet.switch_client import SwitchClient


async def main():
    env = read_env(Path(".env"))
    os.environ.update(env)
    temporary = tempfile.TemporaryDirectory()
    shutil.copytree("examples/om", Path(temporary.name) / "om")
    os.environ["TN_DATA_DIR"] = temporary.name
    state = json.loads(Path("data/day0-state.json").read_text())
    client = SwitchClient(env["SWITCH_URL"], state["om"]["id"], state["om"]["api_key"])
    console = read_env(CONSOLE_ENV)
    gateway = login(
        env["SWITCH_URL"], console["GATEWAY_ADMIN_EMAIL"], console["GATEWAY_ADMIN_PASSWORD"]
    )
    rahul = login(env["SWITCH_URL"], "rahul@switch.local", env["RAHUL_SWITCH_PASSWORD"])
    source = IdentitySource(Path("data/gate-identities.json"), env["TN_IDENTITY_URL"])
    task = asyncio.create_task(Gate("om", client, source).run())
    room = None
    evidence = {}
    try:
        await asyncio.wait_for(client.ready.wait(), 20)
        room = (
            await client.create_room(
                "phase16-" + uuid4().hex[:8],
                "Identity E2E",
                ["om-gate", "rahul-gate"],
                internal_only=True,
            )
        )["id"]
        await client.connect_to_room(room)
        await client.post_message("@rahul-gate free 2026-11-08..2026-11-09")
        await asyncio.sleep(8)
        owner = (await client.get_agent_detail(state["rahul"]["id"]))["owner_id"]
        gateway.post("/chats/" + room + "/members", json={"user_id": owner}).raise_for_status()
        rahul.post(
            "/chats/" + room + "/messages",
            json={
                "request_id": str(uuid4()),
                "body": "@om-gate ask diet neighbourhood address",
                "mentionAgentId": client.agent_id,
            },
        ).raise_for_status()
        await asyncio.sleep(8)
        history = await client.read_context(room_id=room)
        replies = [t["root"] for t in history["threads"]]
        free = [
            r["body"]
            for r in replies
            if r.get("sender_name") == "rahul-gate" and "Cricket" in r["body"]
        ]
        ask = [
            r["body"]
            for r in replies
            if r.get("sender_name") == "om-gate" and "vegetarian" in r["body"]
        ]
        assert free, "Missing close-level calendar reply"
        assert ask and "Indiranagar" in ask[-1] and "42," not in ask[-1], "Wrong fact disclosure"
        evidence.update(room=room, calendar=free[-1], facts=ask[-1], passed=True)
    finally:
        if room:
            evidence["cleanup_http"] = gateway.delete("/rooms/" + room).status_code
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await client.aclose()
        temporary.cleanup()
        gateway.close()
        rahul.close()
        Path("data/phase16-evidence.json").write_text(json.dumps(evidence, indent=2))
        print(json.dumps(evidence))


if __name__ == "__main__":
    asyncio.run(main())
