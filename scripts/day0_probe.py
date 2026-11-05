"""Live checks 4–10. State is a mode-0600 JSON file with gate credentials.

State shape: om/rahul: {id, api_key}, om_envoy/rahul_envoy: {agent_id},
room/gift: {id}. Create disposable agents first; never commit the state file.
"""

import argparse
import asyncio
import json
import sys
from contextlib import suppress
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.switch_users import CONSOLE_ENV, login, read_env  # noqa: E402
from trustnet.switch_client import SwitchClient  # noqa: E402


def safe(value):
    if isinstance(value, dict):
        return {
            k: "[redacted]"
            if any(
                w in k.lower() for w in ("key", "token", "password", "cookie", "credential", "code")
            )
            else safe(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [safe(v) for v in value]
    return value


async def run(args):
    state = json.loads(args.state.read_text())
    clients = {
        p: SwitchClient(args.url, state[p]["id"], state[p]["api_key"]) for p in ("om", "rahul")
    }
    tasks = []

    async def errors(response):
        if response.is_error:
            await response.aread()
            print(json.dumps({"http_status": response.status_code, "raw": safe(response.json())}))

    for client in clients.values():
        client.http.event_hooks["response"] = [errors]

    async def drain(client):
        async for event in client.events():
            print(json.dumps({"event": event.__dict__}))

    async def call(label, operation):
        try:
            result = await operation
            print(json.dumps({"step": label, "raw": safe(result)}))
            return result
        except Exception as exc:
            print(json.dumps({"step": label, "error": str(exc)}))
            return None

    try:
        for client in clients.values():
            tasks.append(asyncio.create_task(drain(client)))
        for client in clients.values():
            await asyncio.wait_for(client.ready.wait(), 15)
        o, r = clients.values()
        rid = state["room"]["id"]
        for client in clients.values():
            await client.connect_to_room(rid)
        n = args.check
        passed = False
        if n == "check4":
            for p, client in clients.items():
                await call(p + " status", client._op("list_managed_agents", {}))
                await call(
                    p + " rebrief",
                    client.update_agent_detail(
                        state[p + "_envoy"]["agent_id"],
                        instructions="Reply exactly DAY0_GAMMA when asked. Never use files or shell.",
                    ),
                )
            await o.post_message("@day0-om-envoy @day0-rahul-envoy reply now")
            await asyncio.sleep(args.wait)
            history = await call("replies", o.read_context(room_id=rid))
            passed = all(
                any(
                    t["root"].get("sender_name") == "day0-" + p + "-envoy"
                    and "DAY0_GAMMA" in t["root"].get("body", "")
                    for t in history["threads"]
                )
                for p in clients
            )
        elif n == "check5":
            await call("cross-owner detail", r.get_agent_detail(state["om_envoy"]["agent_id"]))
            await call(
                "peer addressing",
                o.update_agent_detail(state["om_envoy"]["agent_id"], addressing="anyone"),
            )
            await r.update_agent_detail(
                state["rahul_envoy"]["agent_id"],
                instructions="When asked, send @day0-om-envoy DAY0_PEER once. Then stop.",
            )
            await r.post_message("@day0-rahul-envoy send the peer message now")
            fresh = await call(
                "fresh room",
                o.create_room(
                    "day0-fresh-session",
                    "Disposable session test",
                    ["om-gate", "day0-om-envoy"],
                    internal_only=True,
                ),
            )
            state["fresh"] = fresh
            args.state.write_text(json.dumps(state))
            await o.connect_to_room(fresh["id"])
            await o.post_message(
                "@day0-om-envoy What exact phrase were you asked to reply in the other room? Say UNKNOWN if you cannot remember."
            )
            await asyncio.sleep(args.wait)
            await call("fresh history", o.read_context(room_id=fresh["id"]))
            passed = False  # Redaction alone does not prove peer delivery and session isolation.
        elif n == "check6":
            result = await call(
                "OpenCode deny tools",
                o.update_agent_detail(
                    state["om_envoy"]["agent_id"],
                    advanced_config={"disallowedTools": ["Bash", "Edit", "Write"]},
                ),
            )
            await call(
                "Codex manual mode",
                r.update_agent_detail(state["rahul_envoy"]["agent_id"], auto_mode=False),
            )
            await r.post_message(
                "@day0-rahul-envoy Run echo DAY0_TOOL_CHECK in the shell, but ask approval before doing it."
            )
            await asyncio.sleep(args.wait)
            await call("tool history", r.read_context(room_id=rid))
            passed = result is not None
        elif n == "check7":
            passed = (
                await call("cross-owner invite", o.invite_agent_to_room(rid, "rahul-gate"))
                is not None
            )
        elif n == "check8":
            await call("participants", o.list_participants())
            await call("owner", r.get_agent_detail(o.agent_id))
            passed = False  # Frames have null kind and transport IDs, not participant IDs.
        elif n == "check9":
            passed = (
                await call(
                    "self addressing", o.update_agent_detail(o.agent_id, addressing="anyone")
                )
                is not None
            )
        elif n == "check10":
            env = read_env(CONSOLE_ENV)
            gateway = login(
                args.url,
                env.get("GATEWAY_ADMIN_EMAIL", "admin@switch.local"),
                env["GATEWAY_ADMIN_PASSWORD"],
            )
            statuses = []
            for kind in ("room", "gift"):
                response = gateway.get("/rooms/" + state[kind]["id"])
                print(
                    json.dumps(
                        {"step": kind, "status": response.status_code, "raw": safe(response.json())}
                    )
                )
                statuses.append(response.status_code)
            gateway.close()
            passed = statuses == [200, 403]
        print(("PASS" if passed else "FAIL") + " " + n)
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        for client in clients.values():
            await client.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:53330")
    parser.add_argument("--wait", type=float, default=20)
    commands = parser.add_subparsers(dest="check", required=True)
    for check in range(4, 11):
        commands.add_parser("check" + str(check))
    asyncio.run(run(parser.parse_args()))
