"""Four bounded headless envoy turns on one laptop; archive the probe room."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from scripts.switch_users import read_env
from trustnet.envoy_runner import generate
from trustnet.gate.envoy import ensure_envoy, start_conversation
from trustnet.switch_client import SwitchClient


async def main():
    env = read_env(Path(".env"))
    url = env.get("SWITCH_URL", "http://127.0.0.1:53330")
    state = json.loads(Path("data/day0-state.json").read_text())
    gate = SwitchClient(url, state["om"]["id"], state["om"]["api_key"])
    clients = []
    tasks = []
    room = None

    async def drain(client):
        async for _ in client.events():
            pass

    try:
        for owner, friend in [("om", "rahul"), ("rahul", "om")]:
            client = await ensure_envoy(
                owner,
                friend,
                url=url,
                key=env[owner.upper() + "_GATE_KEY"],
                state_dir=Path("data/envoys") / f"{owner}-envoy-{friend}",
            )
            clients.append(client)
        for client in [gate, *clients]:
            tasks.append(asyncio.create_task(drain(client)))
            await asyncio.wait_for(client.ready.wait(), 15)
        result = await gate.create_room(
            "probe-envoys-" + uuid4().hex[:8],
            "Phase 13b bounded probe",
            ["om-gate"],
            internal_only=True,
        )
        room = result.get("room_id", result.get("id"))
        for name in ["om-envoy-rahul", "rahul-envoy-om"]:
            await start_conversation(room, name, client=gate)
        history = [
            {
                "sender": "gate",
                "text": "Plan a vegetarian lunch Sunday. Keep each reply under 30 words.",
            }
        ]
        for turn in range(4):
            index = turn % 2
            owner = ["om", "rahul"][index]
            brief = f"You represent {owner}. You may share only that {owner} likes vegetarian lunch and is free Sunday at noon. Plan tentatively; ask both owners before committing. Reply briefly in plain text. No tools."
            reply = await generate(["opencode", "codex"][index], brief, history)
            await clients[index].connect_to_room(room)
            await clients[index].send_targeted_message(
                reply, target_names=[["rahul-envoy-om", "om-envoy-rahul"][index]]
            )
            history.append({"sender": owner + "-envoy", "text": reply})
            print(f"Turn {turn + 1} ({owner}): {reply}", flush=True)
        print("Room:", room, "turns: 4; both providers on laptop", flush=True)
        # Read back server context rather than relying solely on post responses.
        context = await gate.read_context(room_id=room)
        Path("data/envoy-probe-context.json").write_text(json.dumps(context))
        print("Server context saved to gitignored data/envoy-probe-context.json", flush=True)
    finally:
        if room:
            await gate.archive_room(room)
            print("Probe room archived", flush=True)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for client in [gate, *clients]:
            await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
