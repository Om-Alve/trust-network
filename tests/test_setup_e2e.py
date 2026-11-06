"""Drive the installed CLI onboarding path against a real HTTP Switch adapter."""

import asyncio
import json
import os
import signal
import sys
from pathlib import Path

from fakes.fake_switch import FakeSwitch
from fakes.loopback_switch import LoopbackSwitch, serve
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from starlette.responses import JSONResponse
from starlette.routing import Route


async def test_setup_and_doctor(tmp_path):
    switch = FakeSwitch()
    wire = LoopbackSwitch(switch, {"setup-key": "mira"})
    app = wire.app()

    async def identities(request):
        if request.headers.get("authorization") != "Bearer identity-key":
            return JSONResponse({}, status_code=401)
        values = {p: {"kind": "user", "id": p} for p in switch.users}
        values.update(
            {
                name: {"kind": "agent", "id": name, "owner_id": a["owner_id"]}
                for name, a in switch.agents.items()
            }
        )
        return JSONResponse(values)

    app.routes.append(Route("/identities", identities))
    url, stop = await serve(app)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("TN_") and key != "SWITCH_URL"
    }
    env.update(
        TN_CONFIG_DIR=str(tmp_path / "config"),
        SETUP_KEY="setup-key",
        SETUP_IDENTITIES="identity-key",
        NO_PROXY="127.0.0.1,localhost",
    )
    transcript = []

    async def cli(*args, expected=0):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "trustnet.tn.cli",
            *args,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(process.communicate(), 30)
        transcript.append(
            {"args": args, "exit": process.returncode, "out": out.decode(), "err": err.decode()}
        )
        assert process.returncode == expected, transcript[-1]
        assert "setup-key" not in out.decode() + err.decode()
        return json.loads(out) if out else {}

    pid = None
    try:
        result = await cli(
            "setup",
            "--name",
            "mira",
            "--server",
            url,
            "--key-env",
            "SETUP_KEY",
            "--identity-url",
            url + "/identities",
            "--identity-token-env",
            "SETUP_IDENTITIES",
            "--agent",
            "manual",
            "--json",
        )
        pid = result["gate_pid"]
        assert result["person"] == "mira"
        assert len(wire.registrations) == 2
        settings = json.loads((tmp_path / "config/config.json").read_text())
        profile = Path(settings["data_dir"]) / "mira"
        assert json.loads((tmp_path / "config/mcp.json").read_text())["mcpServers"][
            "trust-network"
        ]["args"]
        assert (tmp_path / "config/config.json").stat().st_mode & 0o777 == 0o600
        assert "people: {}" in (profile / "trust.yaml").read_text()
        assert "facts: {}" in (profile / "facts.yaml").read_text()
        report = await cli("doctor", "--json")
        assert report["ok"] is True
        assert {check["name"] for check in report["checks"] if check["ok"]} >= {
            "profile",
            "server",
            "home",
            "identities",
            "gate",
            "mcp",
        }
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "trustnet.tn.mcp"],
            env={**env, "TN_CONFIG_DIR": str(tmp_path / "config")},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                reply = await session.call_tool("inbox", {})
                assert not reply.is_error
        before = (profile / "facts.yaml").read_bytes()
        await cli("setup", "--json")
        assert (profile / "facts.yaml").read_bytes() == before
        assert len(wire.registrations) == 2
        assert (await cli("fact", "get", "--json"))["owner"] == "mira"
        os.kill(pid, signal.SIGTERM)
        for _ in range(100):
            await asyncio.sleep(0.02)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
        report = await cli("doctor", "--json", expected=1)
        assert any(c["name"] == "gate" and not c["ok"] and c["fix"] for c in report["checks"])
        (tmp_path / "config/config.json").write_text("{broken")
        await cli("doctor", "--json", expected=1)
        assert "Traceback" not in transcript[-1]["err"]
    finally:
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        await stop()
        (tmp_path / "setup-transcript.json").write_text(json.dumps(transcript, indent=2))
