"""Live Scene 2 with CLI Hermes stand-ins and the real VM Rahul service.

Repeat: uv run python -m scripts.e2e_scene2
Failure modes: over-budget or private suggestions; duplicate claims; home/inbox
leakage; owner wishlist leakage; visible sealed details; seal opening too early.
Artifacts retain public transcripts and copied profiles, never credentials.
"""

import asyncio
import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from scripts.switch_users import read_env
from trustnet.gate import ledger
from trustnet.gate.calendar import TIME_ZONE
from trustnet.gate.identity import IdentitySource
from trustnet.gate.runtime import Gate
from trustnet.switch_client import SwitchClient
from trustnet.tn.personal import home, session


async def main():
    os.environ.update(read_env(Path(".env")))
    vm_check = await asyncio.to_thread(
        subprocess.run,
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "om@hermes.<tailnet>.ts.net",
            "systemctl --user is-active rahul-gate.service",
        ],
        capture_output=True,
        text=True,
    )
    assert vm_check.returncode == 0 and vm_check.stdout.strip() == "active"
    output = Path(f"data/scene2-{time.time_ns()}").resolve()
    output.mkdir(parents=True)
    os.environ["TN_DATA_DIR"] = str(output)
    # Retain the existing Hermes identities while using disposable profile state.
    candidates = [Path("data/main-agents"), Path("data/profiles/main-agents")]
    state_root = next(
        p.parent for p in candidates if (p / "rahul.json").exists() and (p / "om.json").exists()
    )
    os.environ["TN_STATE_DIR"] = str(state_root.resolve())
    for person in ("om", "priya"):
        shutil.copytree(
            Path("examples") / person,
            output / person,
            ignore=shutil.ignore_patterns(
                "ledger.jsonl",
                "claims.json",
                "gift-sessions.json",
                "inbox-cursor.json",
                "share-cards",
            ),
        )
    state = json.loads(Path("data/day0-state.json").read_text())
    clients = {
        p: SwitchClient(os.environ["SWITCH_URL"], state[p]["id"], state[p]["api_key"])
        for p in ("om", "priya")
    }
    identities = IdentitySource(Path("data/gate-identities.json"))
    gate = Gate("om", clients["om"], identities)
    tasks = [asyncio.create_task(gate.run())]

    async def drain():
        async for _ in clients["priya"].events():
            pass

    tasks.append(asyncio.create_task(drain()))
    artifact = {
        "calls": [],
        "checks": {},
        "courtesy_seal": "Workspace administrators can read private rooms; see docs/day0.md check 10.",
    }

    async def cli(person, *args):
        run = await asyncio.to_thread(
            subprocess.run,
            ["uv", "run", "tn", "--as", person, "--json", *args],
            capture_output=True,
            text=True,
        )
        assert run.returncode == 0, f"tn command failed: {run.stderr[:200]}"
        value = json.loads(run.stdout)
        artifact["calls"].append({"person": person, "args": args, "result": value})
        return value

    async def other_ask():
        client = clients["priya"]
        result = await client.create_room(
            f"gift-priya-om-probe-{time.time_ns()}",
            "Scene2 other asker",
            ["priya-gate"],
            internal_only=True,
            read_visibility="private",
            write_visibility="private",
        )
        room = result.get("room_id", result.get("id"))
        await client.connect_to_room(room)
        await client.invite_agent_to_room(room, "om-gate")
        await client.post_message("@om-gate gift-ideas birthday 2026-11-20 budget<=3000")
        for _ in range(200):
            context = await client.read_context(room_id=room, limit=100)
            for thread in context.get("threads", []):
                body = thread["root"]["body"]
                if body.startswith("@priya-gate gift-result "):
                    await client.archive_room(room)
                    return json.loads(body[len("@priya-gate gift-result ") :])
            await asyncio.sleep(0.1)
        raise AssertionError("No Priya gift response")

    try:
        await asyncio.wait_for(asyncio.gather(*(c.ready.wait() for c in clients.values())), 20)
        async with session("om") as om:
            home_room = await home("om", om)
            before = await om.read_context(room_id=home_room, limit=200)
            ideas = await cli("rahul", "gift-ideas", "om", "birthday", "2026-11-20", "3000")
            assert ideas["suggestions"] == [
                {"item": "Lego Millennium Falcon", "price": 2500},
                {"item": "Hario V60", "price": 2000},
            ]
            assert ideas["sizes"] == {"tshirt": "M"}
            assert ideas["over_budget"] == [
                {"item": "Kindle Paperwhite", "price": 14000, "status": "over budget"}
            ]
            assert "address" not in ideas
            claimed = await cli("rahul", "claim", "om", "Lego Millennium Falcon")
            assert claimed == {"status": "claimed", "item": "Lego Millennium Falcon"}
            own = await cli("om", "fact", "get", "wishlist")
            assert "Lego Millennium Falcon" not in json.dumps(own)
            view = await cli("om", "view-as", "rahul")
            assert "Lego Millennium Falcon" not in json.dumps(view)
            after = await om.read_context(room_id=home_room, limit=200)
            assert before == after, "Gift flow wrote to Om home"
            recipient_sessions = json.loads((output / "om/gift-sessions.json").read_text())
            gift_room = next(iter(recipient_sessions))
            detail = await clients["om"].get_room_detail(gift_room)
            artifact["gift_room"] = detail
            artifact["gift_transcript"] = await clients["om"].read_context(
                room_id=gift_room, limit=100
            )
            artifact["vm_service"] = "active"
            artifact["home_before"] = before
            artifact["home_after"] = after
            sealed = ledger.format_ledger(person="om", now=datetime(2026, 11, 20, tzinfo=TIME_ZONE))
            assert sealed == "1 sealed entry, opens Nov 21"
            opened = ledger.format_ledger(person="om", now=datetime(2026, 11, 21, tzinfo=TIME_ZONE))
            assert "sealed entry" not in opened and "gift" in opened
            artifact["ledger"] = {"before": sealed, "after": opened}
            friend = await other_ask()
            assert friend["suggestions"] == [] and friend["taken"] == [] and "sizes" not in friend
            await cli("om", "trust", "priya", "close")
            other = await other_ask()
            assert other["taken"] == [{"item": "Lego Millennium Falcon", "status": "taken"}]
            assert other["suggestions"] == [{"item": "Hario V60", "price": 2000}]
            artifact["other_askers"] = {"friend": friend, "close": other}
            artifact["checks"] = dict(
                within_budget=True,
                room_level=True,
                owner_claim_hidden=True,
                other_asker_taken=True,
                home_unchanged=True,
                sealed_until_nov21=True,
                opens_nov21=True,
            )
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for client in clients.values():
            await client.aclose()
        artifact["stored_ledger"] = (
            (output / "om/ledger.jsonl").read_text()
            if (output / "om/ledger.jsonl").exists()
            else ""
        )
        artifact["stored_claims"] = (
            json.loads((output / "om/claims.json").read_text())
            if (output / "om/claims.json").exists()
            else {}
        )
        from scripts.demo_reset import clear_local

        clear_local(output)
        assert not (output / "om/claims.json").exists()
        assert not (output / "om/gift-sessions.json").exists()
        artifact["checks"]["reset_clears_claims_and_sessions"] = True
        (output / "artifact.json").write_text(json.dumps(artifact, indent=2, ensure_ascii=False))
        print(output / "artifact.json")


if __name__ == "__main__":
    asyncio.run(main())
