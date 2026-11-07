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
        assert result["wake"] is None
        assert result["wake_command"] is None
        assert result["self_check"] == "tn doctor"
        assert result["next_steps"]
        assert result["readiness"] == {"connection": True, "automation": False}
        assert result["calendar"] == {"delivery": "agent", "timezone": "Asia/Kolkata"}
        assert len(wire.registrations) == 2
        settings = json.loads((tmp_path / "config/config.json").read_text())
        profile = Path(settings["data_dir"]) / "mira"
        assert settings["calendar_delivery"] == "agent"
        assert settings["timezone"] == "Asia/Kolkata"
        assert json.loads((tmp_path / "config/mcp.json").read_text())["mcpServers"][
            "trust-network"
        ]["args"]
        assert (tmp_path / "config/config.json").stat().st_mode & 0o777 == 0o600
        assert "people: {}" in (profile / "trust.yaml").read_text()
        assert "facts: {}" in (profile / "facts.yaml").read_text()
        not_ready = await cli("doctor", "--json", expected=1)
        assert not_ready["connection_ok"] is True
        assert not_ready["automation_ready"] is False
        assert {c["name"] for c in not_ready["checks"] if not c["ok"]} == {
            "wake-config",
            "wake-runner",
        }
        assert any("external poller" in note for note in not_ready["notes"])
        declared = await cli("setup", "--wake-external", "test harness poller", "--json")
        assert declared["wake"] == {
            "mode": "external",
            "external": "test harness poller",
        }
        assert declared["readiness"]["automation"] is True
        report = await cli("doctor", "--json")
        assert report["ok"] is True
        assert report["automation_ready"] is True
        assert report["wake_verified"] is False
        assert {
            "profile",
            "server",
            "home",
            "identities",
            "gate",
            "mcp",
            "wake-config",
            "wake-external",
        } <= {check["name"] for check in report["checks"] if check["ok"]}
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "trustnet.tn.mcp"],
            env={
                **env,
                "TN_CONFIG_DIR": str(tmp_path / "config"),
                "SWITCH_URL": "http://127.0.0.1:1",
            },
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
        await cli("setup", "--consent", "via-agent", "--json")
        assert "default: via-agent" in (profile / "trust.yaml").read_text()
        await cli("setup", "--json")
        assert "default: via-agent" in (profile / "trust.yaml").read_text()
        assert (await cli("fact", "get", "--json"))["owner"] == "mira"
        await cli("setup", "--timezone", "Asia/Tokyo", "--calendar-delivery", "ics", "--json")
        configured = json.loads((tmp_path / "config/config.json").read_text())
        assert configured["timezone"] == "Asia/Tokyo"
        assert configured["calendar_delivery"] == "ics"
        await cli("setup", "--timezone", "Not/AZone", "--json", expected=1)
        assert "Unknown timezone" in transcript[-1]["err"]
        await cli("setup", "--calendar-delivery", "bogus", "--json", expected=2)
        legacy = json.loads((tmp_path / "config/config.json").read_text())
        legacy.pop("calendar_delivery")
        legacy.pop("timezone")
        (tmp_path / "config/config.json").write_text(json.dumps(legacy))
        await cli("setup", "--json")
        retained = json.loads((tmp_path / "config/config.json").read_text())
        assert retained["calendar_delivery"] == "ics"
        assert retained["timezone"] == "Asia/Kolkata"
        env["WRONG_IDENTITIES"] = "wrong-token"
        await cli(
            "setup",
            "--identity-url",
            url + "/identities",
            "--identity-token-env",
            "WRONG_IDENTITIES",
            "--json",
            expected=1,
        )
        assert "Ready" not in transcript[-1]["out"]
        repaired = await cli(
            "setup",
            "--identity-url",
            url + "/identities",
            "--identity-token-env",
            "SETUP_IDENTITIES",
            "--json",
        )
        pid = repaired["gate_pid"]
        assert (await cli("doctor", "--json"))["ok"] is True
        mcp_path = tmp_path / "config/mcp.json"
        mcp_saved = mcp_path.read_text()
        mcp_broken = json.loads(mcp_saved)
        mcp_broken["mcpServers"]["trust-network"]["command"] = "/missing/python"
        mcp_path.write_text(json.dumps(mcp_broken))
        broken = await cli("doctor", "--json", expected=1)
        assert any(c["name"] == "mcp" and not c["ok"] for c in broken["checks"])
        mcp_path.write_text(mcp_saved)
        env["SWITCH_URL"] = "http://127.0.0.1:1"
        await cli("doctor", "--json", expected=1)
        assert "conflicts" in transcript[-1]["err"]
        env.pop("SWITCH_URL")
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
        (tmp_path / "config/config.json").write_text('{"person":"mira"}')
        await cli("doctor", "--json", expected=1)
        assert "Traceback" not in transcript[-1]["err"]
    finally:
        process_file = tmp_path / "config/gate-process.json"
        if process_file.exists():
            pid = json.loads(process_file.read_text())["pid"]
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        await stop()
        (tmp_path / "setup-transcript.json").write_text(json.dumps(transcript, indent=2))


async def test_wake_codex_keeps_user_config_and_reads_stdin(tmp_path):
    """The Codex preset must not isolate away the person's own MCP connectors."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "codex"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "args = sys.argv[1:]\n"
        "open(os.environ['FAKE_CODEX_ARGS'], 'w').write('\\n'.join(args))\n"
        "open(os.environ['FAKE_CODEX_STDIN'], 'w').write(sys.stdin.read())\n"
        "reply = args[args.index('-o') + 1]\n"
        "open(reply, 'w').write('fake reply from codex\\n')\n"
    )
    fake.chmod(0o755)
    data = tmp_path / "data"
    (data / "mira").mkdir(parents=True)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("TN_") and key != "SWITCH_URL"
    }
    env.update(
        TN_CONFIG_DIR=str(tmp_path / "config"),
        TN_DATA_DIR=str(data),
        PATH=f"{bindir}:{os.environ['PATH']}",
        FAKE_CODEX_ARGS=str(tmp_path / "codex-args.txt"),
        FAKE_CODEX_STDIN=str(tmp_path / "codex-stdin.txt"),
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "trustnet.tn.cli",
        "--as",
        "mira",
        "wake",
        "--agent",
        "codex",
        "--every",
        "3600",
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    output = ""

    async def until(marker, timeout=20):
        nonlocal output
        deadline = asyncio.get_running_loop().time() + timeout
        while marker not in output and asyncio.get_running_loop().time() < deadline:
            try:
                chunk = await asyncio.wait_for(process.stdout.read(4096), 0.2)
            except TimeoutError:
                continue
            if not chunk:
                break
            output += chunk.decode()
        assert marker in output, output
        return output

    try:
        await until("agent for Mira")
        process.stdin.write(b"hello agent\n")
        await process.stdin.drain()
        await until("fake reply from codex")
    finally:
        process.terminate()
        await asyncio.wait_for(process.wait(), 5)

    argv = (tmp_path / "codex-args.txt").read_text().splitlines()
    assert "--ignore-user-config" not in argv
    assert 'mcp_servers.trust-network.default_tools_approval_mode="approve"' in argv
    assert any(arg.startswith("mcp_servers.trust-network.args=") for arg in argv)
    prompt = (tmp_path / "codex-stdin.txt").read_text()
    assert "Mira says: hello agent" in prompt
    assert "trust-network skill" in prompt
