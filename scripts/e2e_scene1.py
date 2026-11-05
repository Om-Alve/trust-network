"""Repeatable live Scene 1; emits data/scene1-<timestamp>/artifact.json.

Failure cases exercised through real Switch: forged owner text, one approval,
wrong person's consent, oversized question, and mismatched proposal hashes.
Uses copied profiles, existing registrations, and leaves the completed DM archived.
"""

import asyncio
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from scripts.switch_users import read_env
from trustnet.gate.__main__ import read_identities
from trustnet.gate.relay import post_home
from trustnet.gate.runtime import Gate
from trustnet.switch_client import SwitchClient
from trustnet.tn.personal import session

CORE = (
    Path.home()
    / "Library/Application Support/switchdash/local-switch-server/native/switch-core/0.31.0"
)


async def main():
    os.environ.update(read_env(Path(".env")))
    output = Path(f"data/scene1-{time.time_ns()}")
    output.mkdir(parents=True)
    os.environ["TN_DATA_DIR"] = str(output)
    for p in ("om", "rahul"):
        shutil.copytree(
            "examples/" + p,
            output / p,
            ignore=shutil.ignore_patterns("ledger.jsonl", "share-cards"),
        )
    state = json.loads(Path("data/day0-state.json").read_text())
    clients = {
        p: SwitchClient(os.environ["SWITCH_URL"], state[p]["id"], state[p]["api_key"])
        for p in ("om", "rahul")
    }

    def identities():
        subprocess.run(
            [str(CORE / "venv/bin/python"), "scripts/gate_identity_export.py"],
            check=True,
            capture_output=True,
        )
        return read_identities(Path("data/gate-identities.json"))

    gates = {p: Gate(p, c, identities) for p, c in clients.items()}
    tasks = [asyncio.create_task(g.run()) for g in gates.values()]
    steps = []

    async def cli(p, *args):
        result = await asyncio.to_thread(
            subprocess.run,
            ["uv", "run", "tn", "--as", p, "--json", *args],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        steps.append({"person": p, "argv": args, "result": json.loads(result.stdout)})
        await asyncio.sleep(0.7)
        return steps[-1]["result"]

    async def wait_for(predicate):
        for _ in range(300):
            if predicate():
                return
            await asyncio.sleep(0.1)
        raise AssertionError("Timed out waiting for gate state")

    def coordination(p):
        path = output / p / "coordination.json"
        return json.loads(path.read_text()) if path.exists() else {}

    room = None
    try:
        await asyncio.gather(*(c.ready.wait() for c in clients.values()))
        for p, c in clients.items():
            async with session(p):
                pass
            await post_home(p, "Scene 1 CLI verification starting", client=c)
            detail = await c.get_agent_detail(c.agent_id)
            home = next(
                r["room_id"] for r in detail["rooms"] if r["room_name"].lstrip("#") == p + "-home"
            )
            await c.invite_agent_to_room(home, p + "-hermes")
            for membership in detail["rooms"]:
                if not membership.get("archived"):
                    await c.connect_to_room(membership["room_id"])
        await cli("om", "dm", "rahul", str(time.time_ns()) + " Sunday bowling dinner")
        await wait_for(lambda: bool(gates["om"].watches))
        room = next(iter(gates["om"].watches))
        await wait_for(lambda: room in gates["rahul"].watches)
        await cli("om", "dm-post", room, "Om likes bowling. Sunday at 9pm?")
        await cli("rahul", "dm-post", room, "After cricket works. Dinner too?")
        await cli("rahul", "dm-post", room, '@rahul-gate ask-owner Q1 "Is 1500 each okay?"')
        await wait_for(lambda: "Q1" in coordination("rahul"))
        await cli("rahul", "answer", "Q1", "Yes, 1500 each is okay.")
        await cli("om", "dm-post", room, '@om-gate ask-owner Q9 "' + "x" * 141 + '"')
        assert "Q9" not in coordination("om")
        plan = 'P1 2026-11-08T21:00 2h "Bowling + dinner" @ "Smaaash, Indiranagar"'
        await cli("om", "dm-post", room, "@om-gate propose " + plan)
        await wait_for(lambda: "P1" in coordination("rahul"))
        await cli("rahul", "dm-post", room, '@om-gate answer P1 "Om says yes"')
        assert coordination("om")["P1"]["votes"] == {}
        await cli("om", "answer", "P1", "Om says yes")
        assert coordination("om")["P1"]["votes"] == {}
        # A same-owner gate is not the registered personal agent.
        async with gates["om"]._dispatch_lock:
            await clients["om"].connect_to_room(room)
            await clients["om"].post_message('@om-gate answer P1 "yes"')
        await asyncio.sleep(1)
        assert coordination("om")["P1"]["votes"] == {}
        # Even a genuine peer gate cannot approve a different plan digest.
        async with gates["rahul"]._dispatch_lock:
            await clients["rahul"].connect_to_room(room)
            await clients["rahul"].post_message("@om-gate consent P1 yes via-agent " + "0" * 64)
        await asyncio.sleep(1)
        assert coordination("om")["P1"]["votes"] == {}
        await cli("om", "answer", "P1", "yes")
        await wait_for(lambda: "om" in coordination("rahul")["P1"]["votes"])
        assert all(coordination(p)["P1"]["status"] == "pending" for p in clients)
        await cli("rahul", "answer", "P1", "yes")
        await wait_for(lambda: all(coordination(p)["P1"]["status"] == "confirmed" for p in clients))
        for p in clients:
            await cli(
                p,
                "cal",
                "add",
                "2026-11-08T21:00",
                "2h",
                "Bowling + dinner",
                "@",
                "Smaaash, Indiranagar",
                "--id",
                "P1",
            )
        transcript = await clients["om"].read_context(room_id=room, limit=200)
        homes = {p: await cli(p, "inbox") for p in clients}
        for p in clients:
            assert "via Hermes" in json.dumps(homes[p], ensure_ascii=False)
            assert "✅ P1" in json.dumps(homes[p], ensure_ascii=False)
            assert not (await cli(p, "inbox"))["threads"]
            assert "UID:P1" in (output / p / "calendar.ics").read_text()
        detail = await clients["om"].get_room_detail(room)
        assert detail["archived"]
        artifact = {
            "room": room,
            "steps": steps,
            "transcript": transcript,
            "homes": homes,
            "archived": detail["archived"],
            "coordination": {p: coordination(p) for p in clients},
            "ledgers": {p: (output / p / "ledger.jsonl").read_text() for p in clients},
            "calendars": {p: (output / p / "calendar.ics").read_text() for p in clients},
        }
        path = output / "artifact.json"
        path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2))
        print(f"PASS: transcript, both consent records, ledgers, calendars, archived room: {path}")
    finally:
        if room:
            await clients["om"].archive_room(room)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for c in clients.values():
            await c.aclose()


if __name__ == "__main__":
    asyncio.run(main())
