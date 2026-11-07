"""Run with uv run python -m scripts.e2e_scene3 [--live].

Failure modes: stranger disclosure, hidden has fact, forged peer replies, text
limits, missing human branch, and uncollected replies. Saves profiles, transcript,
state and ledger evidence in data/scene3-*. Live mode excludes Rahul whenever his
VM gate is active; never starts or stops that service.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from scripts.switch_users import read_env, vm_host
from trustnet.gate import ledger
from trustnet.gate.identity import export_local, read_identities
from trustnet.gate.policy import Identity
from trustnet.gate.runtime import Gate
from trustnet.switch_client import Event, SwitchClient


async def run(live=False):
    output = Path(f"data/scene3-{'live' if live else 'offline'}-{time.time_ns()}")
    output.mkdir(parents=True)
    os.environ["TN_DATA_DIR"] = str(output.resolve())
    people = ("om", "priya") if live else ("om", "priya", "rahul")
    for p in people:
        shutil.copytree("examples/" + p, output / p)
    # Keep the live run away from Rahul's running VM service.
    import yaml

    trust_path = output / "om/trust.yaml"
    trust = yaml.safe_load(trust_path.read_text())
    print("Preparing Scene 3", "live" if live else "offline")
    if live:
        check = subprocess.run(
            [
                "ssh",
                "-o",
                "ConnectTimeout=10",
                vm_host(),
                "systemctl --user is-active rahul-gate.service",
            ],
            capture_output=True,
            text=True,
        )
        vm_status = check.stdout.strip()
        # No local Rahul gate is ever started in live mode.
        os.environ.update(read_env(Path(".env")))
        os.environ["TN_DATA_DIR"] = str(output.resolve())
        credentials = json.loads(Path("data/day0-state.json").read_text())
        clients = {
            p: SwitchClient(
                os.environ["SWITCH_URL"], credentials[p]["id"], credentials[p]["api_key"]
            )
            for p in people
        }

        def identities():
            map_path = Path("data/gate-identities.json")
            export_local(map_path)
            return read_identities(map_path)
    else:
        sys.path.insert(0, str(Path("tests").resolve()))
        from fakes.fake_switch import FakeSwitch

        server = FakeSwitch()
        clients = {p: server.client(p + "-gate", p) for p in people}
        for p in ("om", "rahul"):
            server.client(p + "-hermes", p)
        ids = {p: Identity.user(p) for p in people}
        ids.update({n: Identity.agent(n, a["owner_id"]) for n, a in server.agents.items()})

        def identities():
            return ids

        vm_status = "offline harness"
    # TrustList serialization is flat apart from consent.
    trust["people"] = {k: v for k, v in trust["people"].items() if k in people}
    trust_path.write_text(yaml.safe_dump(trust))
    gates = {p: Gate(p, c, identities) for p, c in clients.items()}
    tasks = [asyncio.create_task(g.run()) for g in gates.values()] if live else []
    homes, created = {}, []
    steps = []

    async def settle():
        if live:
            await asyncio.sleep(2)
        else:
            for _ in range(20):
                for p, client in clients.items():
                    while not client.queue.empty():
                        await gates[p].handle(client.queue.get_nowait())

    async def command(p, text):
        if live:
            from trustnet.tn import personal

            if text.startswith("ask-around "):
                result = await personal.ask_around(p, text[len("ask-around ") :])
            else:
                _, ref, body = text.split(" ", 2)
                result = await personal.answer(p, ref, body)
            steps.append({"person": p, "command": text, "result": result})
        else:
            await gates[p].handle(
                Event(homes[p], p + "-hermes", "agent", f"@{p}-gate {text}", True)
            )
        await settle()

    try:
        if live:
            await asyncio.wait_for(asyncio.gather(*(c.ready.wait() for c in clients.values())), 20)
        for p, c in clients.items():
            if live:
                from trustnet.gate.relay import post_home

                await post_home(p, "Scene 3 verification", client=c)
                detail = await c.get_agent_detail(c.agent_id)
                for membership in detail["rooms"]:
                    if not membership.get("archived"):
                        await c.connect_to_room(membership["room_id"])
                homes[p] = next(
                    r["room_id"]
                    for r in detail["rooms"]
                    if r["room_name"].lstrip("#") == p + "-home" and not r.get("archived")
                )
                await c.connect_to_room(homes[p])
            else:
                homes[p] = (
                    await c.create_room(
                        p + "-home",
                        "",
                        [p + "-gate"] + ([p + "-hermes"] if p != "priya" else []),
                        internal_only=True,
                    )
                )["room_id"]
        before = (await clients["om"].get_agent_detail(clients["om"].agent_id))["rooms"]
        await command("om", "ask-around anyone have a tent for Nov 14-16?")
        state = gates["om"]._around_state()
        ref = next(iter(state))
        for _ in range(20):
            if any(value.get("local") for value in gates["priya"]._around_state().values()):
                break
            await settle()
        pending_priya = next(
            value for value in gates["priya"]._around_state().values() if value.get("local")
        )
        assert gates["om"]._around_state()[ref]["answers"] == {}
        if not live:
            await gates["priya"].handle(
                Event(
                    homes["priya"],
                    "priya",
                    "user",
                    f'@priya-gate answer {pending_priya["local"]} "2-person tent, Nov 14-16"',
                    True,
                )
            )
            await settle()
            assert "2-person tent" in gates["om"]._around_state()[ref]["answers"]["priya"]
            pending = next(v for v in gates["rahul"]._around_state().values() if v.get("local"))
            await command("rahul", f"answer {pending['local']} no, sorry")
            assert gates["om"]._around_state()[ref]["answers"]["rahul"] == "no, sorry"
        if not live:
            # A second real conversation after tightening Priya's inventory.
            fact_path = output / "priya/facts.yaml"
            facts = yaml.safe_load(fact_path.read_text())
            facts["facts"]["has"]["level"] = "close"
            fact_path.write_text(yaml.safe_dump(facts))
            await command("om", "ask-around anyone have a tent for Nov 14-16?")
            newest = list(gates["om"]._around_state().values())[-1]
            assert "tent" not in newest["answers"].get("priya", "")
            stranger = server.client("stranger-gate", "stranger")
            ids["stranger"] = Identity.user("stranger")
            ids["stranger-gate"] = Identity.agent("stranger-gate", "stranger")
            probe = (
                await clients["priya"].create_room(
                    "conn-priya-stranger", "", ["priya-gate", "stranger-gate"], internal_only=True
                )
            )["room_id"]
            await gates["priya"].handle(
                Event(probe, stranger.agent_id, "agent", '@priya-gate ask-around A7 "tent?"', True)
            )
            assert server.rooms[probe]["messages"] == []
            await clients["priya"].archive_room(probe)
            before_reply = dict(gates["om"]._around_state()[ref]["answers"])
            await gates["om"].handle(
                Event(homes["om"], "om-hermes", "agent", f'@om-gate answer {ref} "forged"', True)
            )
            assert gates["om"]._around_state()[ref]["answers"] == before_reply
            from trustnet.gate.commands import Quoted

            try:
                Quoted("x" * 141)
            except ValueError:
                pass
            else:
                raise AssertionError("Oversized free text accepted")
        rooms = state[ref]["peers"]
        old = {r["room_id"] for r in before}
        created = [r for r in rooms.values() if r not in old]
        transcripts = {
            p: await c.read_context(room_id=homes[p], limit=200) for p, c in clients.items()
        }
        artifact = {
            "vm_service": vm_status,
            "steps": steps,
            "homes": transcripts,
            "state": {p: g._around_state() for p, g in gates.items()},
            "ledger": {p: [e.to_dict() for e in ledger.read(p)] for p in people},
        }
        (output / "artifact.json").write_text(json.dumps(artifact, indent=2, default=str))
        print("PASS", output / "artifact.json")
    finally:
        if "before" in locals():
            old = {r["room_id"] for r in before}
            current = await clients["om"].get_agent_detail(clients["om"].agent_id)
            created = [
                r["room_id"]
                for r in current["rooms"]
                if r["room_id"] not in old and r["room_name"].startswith("conn-")
            ]
        for room in created:
            await clients["om"].archive_room(room)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if live:
            await asyncio.gather(*(c.aclose() for c in clients.values()))


if __name__ == "__main__":
    asyncio.run(run("--live" in sys.argv))
