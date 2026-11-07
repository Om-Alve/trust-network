"""Redeem a real host invite through setup, then diagnose the resulting connection."""

import asyncio
import json
import os
import signal
import sys

from fakes.fake_switch import FakeSwitch
from fakes.loopback_switch import LoopbackSwitch, serve
from host_flows import HostHarness

from trustnet.tn import configuration


async def test_invite_to_running_connection(tmp_path):
    transcripts = []
    guests = []
    with HostHarness(tmp_path / "host") as host:
        switch = FakeSwitch()

        class Wire(LoopbackSwitch):
            def client(self, name, person):
                client = super().client(name, person)
                mapping = {p: {"kind": "user", "id": p} for p in switch.users}
                mapping.update(
                    {
                        n: {"kind": "agent", "id": n, "owner_id": a["owner_id"]}
                        for n, a in switch.agents.items()
                    }
                )
                configuration.write_json(host.identity_map, mapping)
                return client

        wire = Wire(switch, {key: person for person, key in host.env_keys.items()})
        url, stop = await serve(wire.app())
        settings = host.config()
        settings["switch_url"] = url
        configuration.write_json(host.config_dir / "host.json", settings)
        host_env = {**os.environ, "TN_CONFIG_DIR": str(host.config_dir)}
        guest_env = {
            k: v for k, v in os.environ.items() if not k.startswith("TN_") and k != "SWITCH_URL"
        }

        async def cli(env, *args, expected=0):
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "trustnet.tn.cli",
                *args,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await asyncio.wait_for(process.communicate(), 40)
            redacted = [a.split("#")[0] + "#<redacted>" if "#" in a else a for a in args]
            transcripts.append({"args": redacted, "status": process.returncode})
            assert process.returncode == expected, (redacted, out.decode(), err.decode())
            return json.loads(out) if out else {}

        try:
            invite = await cli(host_env, "invite", "create", "alice", "--json")
            guest = tmp_path / "alice"
            guests.append(guest)
            env = {**guest_env, "TN_CONFIG_DIR": str(guest)}
            ready = await cli(
                env,
                "setup",
                invite["invite_url"],
                "--agent",
                "manual",
                "--wake-external",
                "invite harness cron",
                "--json",
            )
            assert ready["person"] == "alice" and ready["gate_pid"]
            assert ready["calendar"]["delivery"] == "agent"
            assert ready["wake"] == {"mode": "external", "external": "invite harness cron"}
            report = await cli(env, "doctor", "--json")
            assert report["ok"] is True
            assert report["automation_ready"] is True
            assert report["wake_verified"] is False
            await cli(env, "setup", invite["invite_url"], "--json")
            assert wire.registrations == ["alice-gate", "alice-hermes"]
            second = tmp_path / "other"
            guests.append(second)
            await cli(
                {**guest_env, "TN_CONFIG_DIR": str(second)},
                "setup",
                invite["invite_url"],
                "--agent",
                "manual",
                "--json",
                expected=1,
            )
            expired = await cli(host_env, "invite", "create", "bob", "--ttl", "0", "--json")
            await cli(
                {**guest_env, "TN_CONFIG_DIR": str(tmp_path / "expired")},
                "setup",
                expired["invite_url"],
                "--json",
                expected=1,
            )
            assert len(wire.registrations) == 2
            stopped = await cli(env, "stop", "--json")
            assert stopped["stopped"] is True
            await cli(env, "doctor", "--json", expected=1)
            ready = await cli(env, "setup", "--json")
            assert ready["gate_pid"]
            (tmp_path / "invite-setup-report.json").write_text(
                json.dumps(
                    {
                        "status": "PASS",
                        "checks": report["checks"],
                        "second_client_refused": True,
                        "expired_refused": True,
                        "registrations": wire.registrations,
                        "commands": transcripts,
                    },
                    indent=2,
                )
            )
        finally:
            for guest in guests:
                path = guest / "gate-process.json"
                if path.exists():
                    pid = json.loads(path.read_text())["pid"]
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
            await stop()
