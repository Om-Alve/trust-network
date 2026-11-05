"""Two-Hermes phase 14 live check using retained credentials; run from repo root."""

import asyncio
import json
import os
import subprocess
from pathlib import Path

from scripts.switch_users import read_env
from trustnet.gate.__main__ import read_identities
from trustnet.gate.commands import Quoted
from trustnet.gate.dm import setup
from trustnet.gate.runtime import Gate
from trustnet.switch_client import SwitchClient
from trustnet.tn.dm import operate

CORE = (
    Path.home()
    / "Library/Application Support/switchdash/local-switch-server/native/switch-core/0.31.0"
)


async def main():
    os.environ.update(read_env(Path(".env")))
    state = json.loads(Path("data/day0-state.json").read_text())
    cs = {
        p: SwitchClient(os.environ["SWITCH_URL"], state[p]["id"], state[p]["api_key"])
        for p in ("om", "rahul")
    }
    # Register Rahul's CLI identity once.
    if not Path("data/main-agents/rahul.json").exists():
        h = await SwitchClient.register(
            os.environ["SWITCH_URL"],
            os.environ["RAHUL_GATE_KEY"],
            "rahul-hermes",
            agent_type="codex",
        )
        f = Path("data/main-agents/rahul.json")
        f.touch(mode=0o600)
        f.write_text(json.dumps({"id": h.agent_id, "api_key": h.api_key}))
        await h.aclose()
    os.environ["TN_DATA_DIR"] = "data/phase14-profiles"
    import shutil

    for p in cs:
        dst = Path(os.environ["TN_DATA_DIR"]) / p
        if not dst.exists():
            shutil.copytree(
                "examples/" + p, dst, ignore=shutil.ignore_patterns("ledger.jsonl", "share-cards")
            )

    def ids():
        subprocess.run(
            [str(CORE / "venv/bin/python"), "scripts/gate_identity_export.py"], check=True
        )
        return read_identities(Path("data/gate-identities.json"))

    gates = {p: Gate(p, c, ids) for p, c in cs.items()}
    tasks = [asyncio.create_task(g.run()) for g in gates.values()]
    try:
        await asyncio.gather(*(c.ready.wait() for c in cs.values()))

        await setup(gates["om"], "rahul", Quoted("Sunday bowling dinner"))
        rid = next(iter(gates["om"].watches))
        print("DM:", rid, flush=True)
        await asyncio.sleep(3)
        assert rid in gates["rahul"].watches, "join-dm did not establish peer watch"
        await operate(
            "om", rid, "Om is vegetarian and likes bowling. Is Sunday at 9pm good after cricket?"
        )
        await operate(
            "rahul", rid, "Rahul has cricket until 8:30. 9pm works; how about dinner afterwards?"
        )
        await asyncio.sleep(1)
        context = await operate("om", rid)
        print(json.dumps(context), flush=True)
        await operate("om", rid, "Budget is 1500 each. Dinner after bowling sounds good.")
        await operate(
            "rahul", rid, "Agreed on a draft. We should ask both people before committing."
        )
        await asyncio.sleep(1)
        print(json.dumps(await operate("om", rid)), flush=True)
        Path("data/phase14-room").write_text(rid)
        for i in range(12):
            if gates["om"].watches[rid].closed:
                break
            await operate(
                "om" if i % 2 == 0 else "rahul",
                rid,
                f"Planning check {i + 1}: Sunday bowling draft, awaiting both people’s consent.",
            )
            await asyncio.sleep(0.5)
        await asyncio.sleep(2)
        assert all(g.watches[rid].closed for g in gates.values())
        print("Both gates summarized and archived at 12 actual main-agent messages", flush=True)
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for c in cs.values():
            await c.aclose()


asyncio.run(main())
