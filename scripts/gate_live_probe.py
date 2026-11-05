"""Bounded phase 11 live checks; retained gates, disposable rooms, fixture data copy."""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from scripts.switch_users import CONSOLE_ENV, login, read_env
from trustnet.gate import ledger
from trustnet.gate.__main__ import read_identities
from trustnet.gate.runtime import Gate
from trustnet.switch_client import SwitchClient

CORE = (
    Path.home()
    / "Library/Application Support/switchdash/local-switch-server/native/switch-core/0.31.0"
)
URL = "http://127.0.0.1:53330"


async def main():
    state_path = Path("data/day0-state.json")
    state = json.loads(state_path.read_text())
    env = read_env(Path(".env"))
    if "priya" not in state:
        client = await SwitchClient.register(
            URL, env["PRIYA_GATE_KEY"], "priya-gate", agent_type="codex"
        )
        state["priya"] = {"id": client.agent_id, "api_key": client.api_key}
        state_path.write_text(json.dumps(state))
        state_path.chmod(0o600)
        await client.aclose()
    subprocess.run([str(CORE / "venv/bin/python"), "scripts/gate_identity_export.py"], check=True)
    console = read_env(CONSOLE_ENV)
    gateway = login(URL, console["GATEWAY_ADMIN_EMAIL"], console["GATEWAY_ADMIN_PASSWORD"])
    clients = {
        p: SwitchClient(URL, state[p]["id"], state[p]["api_key"]) for p in ("om", "rahul", "priya")
    }
    rooms = []
    tasks = []
    temp = tempfile.TemporaryDirectory()
    shutil.copytree("examples/om", Path(temp.name) / "om")
    os.environ["TN_DATA_DIR"] = temp.name

    def fresh_identities():
        subprocess.run(
            [str(CORE / "venv/bin/python"), "scripts/gate_identity_export.py"], check=True
        )
        return read_identities(Path("data/gate-identities.json"))

    gate = Gate("om", clients["om"], fresh_identities)
    import logging

    logging.basicConfig(level=logging.INFO)
    tasks.append(asyncio.create_task(gate.run()))

    async def drain(client):
        async for _ in client.events():
            pass

    for p in ("rahul", "priya"):
        tasks.append(asyncio.create_task(drain(clients[p])))
    try:
        for client in clients.values():
            await asyncio.wait_for(client.ready.wait(), 15)
        for p in ("rahul", "priya", "om"):
            result = await clients["om"].create_room(
                "phase11-" + p + "-" + uuid4().hex[:6],
                "Disposable gate check",
                ["om-gate"] + ([] if p == "om" else [p + "-gate"]),
                internal_only=True,
            )
            rid = result["id"]
            rooms.append(rid)
            await clients["om"].connect_to_room(rid)
            before = len(ledger.read("om"))
            if p == "om":
                owner = (await clients["om"].get_agent_detail(clients["om"].agent_id))["owner_id"]
                gateway.post(
                    "/chats/" + rid + "/members", json={"user_id": owner}
                ).raise_for_status()
                response = gateway.post(
                    "/chats/" + rid + "/messages",
                    json={
                        "request_id": str(uuid4()),
                        "body": "@om-gate free 2026-11-08..2026-11-09",
                        "mentionAgentId": clients["om"].agent_id,
                    },
                )
                response.raise_for_status()
                # The Gateway member client was created by the first post.
                subprocess.run(
                    [str(CORE / "venv/bin/python"), "scripts/gate_identity_export.py"], check=True
                )
                # Retry once after provisioning the identity mapping, with a new message id.
                response = gateway.post(
                    "/chats/" + rid + "/messages",
                    json={
                        "request_id": str(uuid4()),
                        "body": "@om-gate free 2026-11-08..2026-11-09",
                        "mentionAgentId": clients["om"].agent_id,
                    },
                )
                response.raise_for_status()
            else:
                await clients[p].connect_to_room(rid)
                await clients[p].post_message("@om-gate ask diet wishlist address")
            for _ in range(50):
                await asyncio.sleep(0.1)
                entries = ledger.read("om")[before:]
                if entries:
                    break
            history = await clients["om"].read_context(room_id=rid)
            replies = [
                t["root"]["body"]
                for t in history["threads"]
                if t["root"].get("sender_name") == "om-gate"
            ]
            assert replies, f"No gate reply for {p}"
            fields = {e.field for e in entries}
            expected = (
                {"diet", "wishlist"} if p == "rahul" else {"diet"} if p == "priya" else {"calendar"}
            )
            assert fields == expected, (p, fields, replies)
            print(json.dumps({"person": p, "reply": replies[-1], "ledger_fields": sorted(fields)}))
    finally:
        for rid in rooms:
            response = gateway.delete("/rooms/" + rid)
            print("cleanup room HTTP", response.status_code)
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        for client in clients.values():
            await client.aclose()
        gateway.close()
        temp.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
