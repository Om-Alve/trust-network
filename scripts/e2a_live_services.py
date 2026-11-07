"""Live acceptance for real launchd services and Google Calendar delivery.

Failure cases, before implementation:

Services stage (no model calls):
- setup reports ready while launchd has not loaded a unit, or loaded it without
  a running process;
- launchd runs a program other than the one its plist names, or an interpreter
  that disappears after setup;
- the launchd gate holds its lock but cannot answer on Switch, for example
  because its identity source or Switch address exists only in the shell that
  ran setup;
- status or doctor report a live runner that launchd does not have;
- a killed gate stays down, or comes back without answering;
- tn stop leaves a unit loaded, a process running, or plists that launchd loads
  again at the next login;
- tn setup after tn stop does not restart the services, or a repeated setup
  leaves two gates or two runners;
- an interrupted run leaves loaded test units or processes;
- credentials appear in the report.

Calendar stage (real Codex turns and Google Calendar):
- the Google Calendar connector is not accessible from the Codex home the wake
  service uses;
- unattended connector calls need approval in codex exec;
- the script, not the launchd wake runner, performs delivery;
- the receipt names an event that is missing or differs in title, start,
  duration, location or UID marker;
- the test event stays in the calendar;
- the local ICS side differs from the plan.

Each person is a fresh Switch user created by a private onboarding host
(``tn host``) with the Console administrator credentials, and joins with the
documented ``tn setup '<invite>' ... --background-service`` command. A launchd
unit sees only the saved configuration, so its identity endpoint must come from
the invite rather than from this script's environment. Every TN_CONFIG_DIR and
CODEX_HOME lives under data/live-services-<timestamp>/; ~/.config/trust-network
and ~/.codex/config.toml are never written. The units run an isolated
``uv tool install`` of this checkout under the same directory: the documented
install path, frozen at the tested commit and kept after the run.

    uv run python -m scripts.e2a_live_services --stage services
    uv run python -m scripts.e2a_live_services --stage calendar
    uv run python -m scripts.e2a_live_services --verify data/live-services-<timestamp>/report.json

``--verify`` re-checks a saved report and the private files beside it, with no
launchd, Switch or model call. Test Switch accounts remain for inspection.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import plistlib
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from scripts.switch_users import CONSOLE_ENV, read_env

ROOT = Path(__file__).resolve().parents[1]
LAUNCH_AGENTS = Path.home() / "Library/LaunchAgents"
DOMAIN = f"gui/{os.getuid()}"
ROLES = ("gate", "wake")
SECRET_KEYS = frozenset(
    {
        "api_key",
        "registration_key",
        "identity_token",
        "identity_token_secret",
        "password",
        "access_token",
        "refresh_token",
        "id_token",
        "OPENAI_API_KEY",
    }
)
GOOGLE_CALENDAR = "connector_947e0d954944416db111db556030eea6"
ASK = (
    "import asyncio, json, sys\n"
    "from trustnet.tn import configuration, personal\n"
    "configuration.apply(override=True)\n"
    "print(json.dumps(asyncio.run(personal.ask(sys.argv[1], sys.argv[2], ['diet']))))\n"
)


def until(probe, seconds, what):
    deadline = time.monotonic() + seconds
    while True:
        value = probe()
        if value:
            return value
        if time.monotonic() > deadline:
            raise TimeoutError(f"{what} within {seconds}s")
        time.sleep(1)


def alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def command_of(pid):
    if not pid:
        return None
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True
    )
    return result.stdout.strip() or None


def processes(person):
    listing = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True)
    found = []
    for line in listing.stdout.splitlines():
        pid, _, command = line.strip().partition(" ")
        if person in command and int(pid) != os.getpid():
            found.append({"pid": int(pid), "command": command.strip()})
    return found


def launchd_print(text):
    """Top-level ``key = value`` fields and the ``arguments`` block of ``launchctl print``."""
    fields, arguments, inside = {}, [], False
    for line in text.splitlines():
        if line == "\targuments = {":
            inside = True
        elif inside:
            if line == "\t}":
                inside = False
            else:
                arguments.append(line.strip())
        elif line.startswith("\t") and not line.startswith("\t\t") and " = " in line:
            key, _, value = line.strip().partition(" = ")
            fields.setdefault(key, value)
    return fields, arguments


def observe(person, role):
    label = f"ai.trustnetwork.{person}.{role}"
    plist = LAUNCH_AGENTS / f"{label}.plist"
    printed = subprocess.run(
        ["launchctl", "print", f"{DOMAIN}/{label}"], capture_output=True, text=True
    )
    fields, arguments = launchd_print(printed.stdout) if printed.returncode == 0 else ({}, [])
    pid = int(fields["pid"]) if fields.get("pid", "").isdigit() else None
    payload = plistlib.loads(plist.read_bytes()) if plist.exists() else {}
    return {
        "label": label,
        "plist": str(plist),
        "plist_exists": plist.exists(),
        "program_arguments": payload.get("ProgramArguments"),
        "keep_alive": payload.get("KeepAlive"),
        "throttle_interval": payload.get("ThrottleInterval"),
        "print_returncode": printed.returncode,
        "print": printed.stdout if printed.returncode == 0 else printed.stderr.strip(),
        "state": fields.get("state"),
        "pid": pid,
        "launchd_arguments": arguments,
        "alive": alive(pid),
        "ps_command": command_of(pid),
    }


def running(record):
    """launchd runs the plist's exact program, and that pid is alive with the same argv."""
    arguments = record["program_arguments"]
    return bool(
        arguments
        and record["print_returncode"] == 0
        and record["state"] == "running"
        and record["pid"]
        and record["alive"]
        and record["launchd_arguments"] == arguments
        and record["ps_command"] == " ".join(arguments)
    )


def unloaded(record):
    return record["print_returncode"] != 0


def secrets(output):
    """Every credential value saved in the private profile and host files."""
    found = set()

    def walk(value, key=None):
        if isinstance(value, dict):
            for child, item in value.items():
                walk(item, child)
        elif isinstance(value, list):
            for item in value:
                walk(item, key)
        elif isinstance(value, str) and key in SECRET_KEYS and len(value) >= 8:
            found.add(value)

    for directory in (output / "host", output / "people"):
        for path in directory.rglob("*.json") if directory.exists() else ():
            try:
                walk(json.loads(path.read_text()))
            except (OSError, ValueError, UnicodeDecodeError):
                pass
    return found


def tail(path, lines=40):
    return path.read_text(errors="replace").splitlines()[-lines:] if path.exists() else []


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class Live:
    def __init__(self, output, names, server, stamp):
        self.output, self.names, self.server, self.stamp = output, names, server, stamp
        self.env, self.evidence, self.findings = {}, {}, []
        self.invite_tokens, self.host = set(), None
        path = os.pathsep.join(
            entry
            for entry in os.environ.get("PATH", "").split(os.pathsep)
            if not entry.startswith(str(ROOT))
        )
        self.base_env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("TN_", "UV_", "CODEX_"))
            and key not in {"SWITCH_URL", "VIRTUAL_ENV", "OPENAI_API_KEY"}
        }
        self.base_env["PATH"] = path

    def cli(self, env, *args, expected=0, timeout=180):
        result = subprocess.run(
            [str(self.tn_path), "--json", *args],
            env=env,
            cwd=self.output,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if expected is not None and result.returncode != expected:
            raise RuntimeError(
                f"tn {args[0]} exited {result.returncode}: {result.stderr.strip()[-800:]}"
            )
        return json.loads(result.stdout)

    def tn(self, person, *args, expected=0, timeout=180):
        return self.cli(self.env[person], *args, expected=expected, timeout=timeout)

    def install(self):
        tools, binaries = self.output / "uv-tools", self.output / "bin"
        result = subprocess.run(
            ["uv", "tool", "install", "--python", "3.12", "--reinstall", str(ROOT)],
            env={**os.environ, "UV_TOOL_DIR": str(tools), "UV_TOOL_BIN_DIR": str(binaries)},
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode:
            raise RuntimeError("uv tool install failed: " + result.stderr[-800:])
        self.tn_path = binaries / "tn"
        self.python = tools / "trust-network" / "bin" / "python"
        self.evidence["program"] = {"tn": str(self.tn_path), "python": str(self.python)}

    def start_host(self):
        console = read_env(CONSOLE_ENV)
        port = free_port()
        self.host_env = {
            **self.base_env,
            "TN_CONFIG_DIR": str(self.output / "host"),
            "SWITCH_ADMIN_EMAIL": console["GATEWAY_ADMIN_EMAIL"],
            "SWITCH_ADMIN_PASSWORD": console["GATEWAY_ADMIN_PASSWORD"],
        }
        public = f"http://127.0.0.1:{port}"
        self.cli(
            self.host_env,
            "host",
            "init",
            "--switch-url",
            self.server,
            "--public-url",
            public,
            "--port",
            str(port),
        )
        log = (self.output / "host-serve.log").open("ab")
        self.host = subprocess.Popen(
            [str(self.tn_path), "host", "serve"],
            env=self.host_env,
            cwd=self.output,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )

        def listening():
            try:
                return httpx.get(public + "/identities", timeout=2).status_code == 401
            except httpx.HTTPError:
                return False

        until(listening, 30, "onboarding host did not listen")

    def join(self, person, *flags):
        invite = self.cli(self.host_env, "invite", "create", person)["invite_url"]
        self.invite_tokens.add(invite.split("#", 1)[1])
        home = self.output / "people" / person
        self.env[person] = {
            **self.base_env,
            "TN_CONFIG_DIR": str(home / "config"),
            "CODEX_HOME": str(home / "codex-home"),
        }
        (home / "codex-home").mkdir(parents=True, exist_ok=True)
        return self.tn(
            person,
            "setup",
            invite,
            "--agent",
            "codex",
            "--consent",
            "via-agent",
            "--wake",
            "--background-service",
            *flags,
        )

    def units(self):
        return {person: {role: observe(person, role) for role in ROLES} for person in self.names}

    def all_running(self):
        snapshot = self.units()
        return snapshot if all(running(r) for p in snapshot.values() for r in p.values()) else None

    def gate_answers(self, asker, peer):
        """``asker``'s agent asks ``peer``'s gate a fact in their DM; the gate must reply."""
        asked_at = time.time()
        result = subprocess.run(
            [str(self.python), "-c", ASK, asker, peer],
            env=self.env[asker],
            cwd=self.output,
            capture_output=True,
            text=True,
            timeout=90,
        )
        if result.returncode:
            raise RuntimeError(f"{asker} could not ask {peer}-gate: {result.stderr[-600:]}")
        room = json.loads(result.stdout.splitlines()[-1])["room"]

        def replies():
            context = self.tn(asker, "dm-read", room)
            messages = [
                m for t in context.get("threads", []) for m in (t["root"], *t.get("replies", []))
            ]
            return [
                {key: m.get(key) for key in ("id", "sender_name", "body", "timestamp")}
                for m in messages
                if m.get("sender_name") == f"{peer}-gate"
                and m.get("body", "").startswith("diet: ")
                and m.get("timestamp", 0) / 1000 >= asked_at - 1
            ]

        return {
            "asker": asker,
            "gate": f"{peer}-gate",
            "room": room,
            "asked_at": asked_at,
            "replies": until(replies, 60, f"{peer}-gate did not answer {asker}"),
        }

    def stop(self, person):
        payload = self.tn(person, "stop")
        until(lambda: not processes(person), 20, f"{person} processes remained after tn stop")
        units = {role: observe(person, role) for role in ROLES}
        claimed = [r for r in ROLES if payload.get("service", {}).get(r, {}).get("active")]
        if claimed and all(unloaded(r) for r in units.values()):
            finding = (
                "tn --json stop reports service.<role>.active true for "
                + " and ".join(claimed)
                + " although launchctl no longer has the units; stop_command returns the "
                "service state read before stopping"
            )
            if finding not in self.findings:
                self.findings.append(finding)
        return {
            "result": payload,
            "units": units,
            "processes": processes(person),
            "plists_remaining": [r["plist"] for r in units.values() if r["plist_exists"]],
            "doctor": self.tn(person, "doctor", expected=None),
        }

    def instances(self, person):
        commands = [p["command"] for p in processes(person)]
        units = {role: observe(person, role) for role in ROLES}
        return {
            role: sum(c == " ".join(units[role]["program_arguments"] or []) for c in commands)
            for role in ROLES
        }

    def cleanup(self):
        record = {"booted_out": [], "killed": [], "plists_removed": []}
        for person in self.names:
            for role in ROLES:
                if not unloaded(observe(person, role)):
                    label = f"ai.trustnetwork.{person}.{role}"
                    subprocess.run(["launchctl", "bootout", f"{DOMAIN}/{label}"])
                    record["booted_out"].append(label)
            for process in processes(person):
                try:
                    os.kill(process["pid"], signal.SIGTERM)
                    record["killed"].append(process)
                except ProcessLookupError:
                    pass
            try:
                until(lambda: not processes(person), 10, "")
            except TimeoutError:
                for process in processes(person):
                    os.kill(process["pid"], signal.SIGKILL)
            for role in ROLES:
                plist = LAUNCH_AGENTS / f"ai.trustnetwork.{person}.{role}.plist"
                if plist.exists():
                    plist.unlink()
                    record["plists_removed"].append(str(plist))
        if self.host is not None:
            self.host.terminate()
            self.host.wait(10)
        record["after"] = {
            person: {
                "loaded": [
                    r["label"] for r in (observe(person, role) for role in ROLES) if not unloaded(r)
                ],
                "processes": processes(person),
                "plists": [str(p) for p in LAUNCH_AGENTS.glob(f"ai.trustnetwork.{person}.*.plist")],
            }
            for person in self.names
        }
        for person in self.names:
            config = Path(self.env[person]["TN_CONFIG_DIR"]) if person in self.env else None
            if config:
                record.setdefault("logs", {})[person] = {
                    name: tail(config / name) for name in ("gate-service.log", "wake-service.log")
                }
        self.evidence["cleanup"] = record
        if record["plists_removed"]:
            self.findings.append(
                "tn stop unloads the units but leaves their plists in ~/Library/LaunchAgents "
                "(by design in setup._service_stop). launchd loads every plist there at the next "
                "login and both have RunAtLoad, so a stopped gate and wake runner start again "
                "after logout or reboot. Cleanup removed: " + ", ".join(record["plists_removed"])
            )


def services(live):
    a, b = live.names
    evidence = live.evidence
    live.install()
    live.start_host()
    evidence["setup"] = {person: live.join(person) for person in live.names}
    for person, peer in ((a, b), (b, a)):
        live.tn(person, "trust", peer, "friend")
    evidence["installed"] = until(live.all_running, 30, "units were not running after setup")
    evidence["status"] = {p: live.tn(p, "status") for p in live.names}
    evidence["doctor"] = {p: live.tn(p, "doctor", expected=None) for p in live.names}
    evidence["gate_reply"] = live.gate_answers(a, b)

    before = observe(a, "gate")
    supervision = {"before": before}
    evidence["supervision"] = supervision
    if not before["keep_alive"]:
        live.findings.append("The gate plist has no KeepAlive; launchd leaves a crashed gate down")
        raise AssertionError("gate unit has no KeepAlive")
    os.kill(before["pid"], signal.SIGKILL)
    killed = time.monotonic()
    supervision["killed_at"] = time.time()

    def restarted():
        record = observe(a, "gate")
        return record if running(record) and record["pid"] != before["pid"] else None

    supervision["after"] = until(restarted, 120, "launchd did not restart the killed gate")
    supervision["restart_seconds"] = round(time.monotonic() - killed, 1)
    supervision["old_pid_alive_after_kill"] = alive(before["pid"])

    def serving():
        status = live.tn(a, "status")
        return status if status["gate_running"] else None

    supervision["status_after"] = until(serving, 60, "the restarted gate never took its lock")
    supervision["serving_seconds"] = round(time.monotonic() - killed, 1)
    supervision["gate_reply_after_restart"] = live.gate_answers(b, a)

    evidence["stop"] = {p: live.stop(p) for p in live.names}
    evidence["restart"] = {p: live.tn(p, "setup") for p in live.names}
    evidence["restart_units"] = until(live.all_running, 30, "tn setup did not restart units")
    evidence["restart_doctor"] = {p: live.tn(p, "doctor", expected=None) for p in live.names}
    evidence["repeat_setup"] = {p: live.tn(p, "setup") for p in live.names}
    evidence["repeat_setup_units"] = until(live.all_running, 30, "repeated setup lost units")
    evidence["repeat_setup_instances"] = {p: live.instances(p) for p in live.names}
    evidence["final_stop"] = {p: live.stop(p) for p in live.names}


def verify_services(report, output):
    evidence, names = report["evidence"], report["people"]
    python = Path(evidence["program"]["python"])
    for person in names:
        for role in ROLES:
            installed = evidence["installed"][person][role]
            assert running(installed), f"{person} {role} was not running under launchd after setup"
            assert Path(installed["program_arguments"][0]) == python
            assert installed["keep_alive"], f"{person} {role} unit has no KeepAlive"
        doctor = evidence["doctor"][person]
        assert doctor["connection_ok"] and doctor["automation_ready"] and doctor["wake_verified"]
        status = evidence["status"][person]
        assert status["gate_running"] and status["wake"]["running"]
        assert status["service"]["gate"]["active"] and status["service"]["wake"]["active"]
    assert evidence["gate_reply"]["replies"], "the launchd gate did not answer on Switch"
    supervision = evidence["supervision"]
    assert running(supervision["before"]) and running(supervision["after"])
    assert supervision["after"]["pid"] != supervision["before"]["pid"]
    assert not supervision["old_pid_alive_after_kill"]
    assert supervision["status_after"]["gate_running"]
    after_restart = supervision["gate_reply_after_restart"]
    assert after_restart["replies"], "the restarted gate is silent"
    assert after_restart["asked_at"] > supervision["killed_at"]
    assert all(m["timestamp"] / 1000 > supervision["killed_at"] for m in after_restart["replies"])
    for phase in ("stop", "final_stop"):
        for person in names:
            stopped = evidence[phase][person]
            assert stopped["result"]["stopped"] is True, (
                f"{phase}: {person} reported nothing stopped"
            )
            assert all(unloaded(r) for r in stopped["units"].values()), f"{phase}: unit loaded"
            assert stopped["processes"] == [], f"{phase}: {person} processes remained"
            assert stopped["doctor"]["automation_ready"] is False
    for person in names:
        doctor = evidence["restart_doctor"][person]
        assert doctor["connection_ok"] and doctor["wake_verified"]
        for role in ROLES:
            restarted = evidence["restart_units"][person][role]
            assert running(restarted), f"tn setup did not restart {person} {role}"
            assert restarted["pid"] != evidence["installed"][person][role]["pid"]
            assert running(evidence["repeat_setup_units"][person][role])
        assert evidence["repeat_setup_instances"][person] == {"gate": 1, "wake": 1}
    verify_cleanup(report, output)


def verify_cleanup(report, output):
    for person, after in report["evidence"]["cleanup"]["after"].items():
        assert after == {"loaded": [], "processes": [], "plists": []}, f"{person} left {after}"
    text = json.dumps(report)
    assert not any(secret in text for secret in secrets(output)), "a credential is in the report"


# ---------------------------------------------------------------------------
# Each person's CODEX_HOME holds a copy of ~/.codex/config.toml, so tn setup's
# `codex mcp add` edits only the copy and the user's connectors and plugins stay
# configured, plus a symlink to ~/.codex/auth.json so a token refresh reaches the
# user's own file. If Codex replaces the file instead of writing through the
# link, the copies diverge; the report records whether each link survived.
#
# Known risk: wake.codex_command sets default_tools_approval_mode="approve" only
# for the trust-network MCP server. If unattended codex exec needs approval for
# Google Calendar tools, the first run fails at "A's calendar task applied": the
# task is `failed` with the refused call in its error, or stays pending while
# wake-service.log shows repeated turns. Codex's stderr for the read-back turns is
# saved beside the report. The fix then belongs in wake.codex_command.
# ---------------------------------------------------------------------------


def connector_preflight(codex_home, timeout=240):
    process = subprocess.Popen(
        ["codex", "app-server"],
        env={**os.environ, "CODEX_HOME": str(codex_home)},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    timer = threading.Timer(timeout, process.kill)
    timer.daemon = True
    timer.start()

    def call(number, method, params):
        process.stdin.write(json.dumps({"method": method, "id": number, "params": params}) + "\n")
        process.stdin.flush()
        while line := process.stdout.readline():
            message = json.loads(line)
            if message.get("id") == number:
                if "error" in message:
                    raise SystemExit(f"codex app-server {method} failed: {message['error']}")
                return message["result"]
        raise SystemExit(f"codex app-server closed or timed out during {method}")

    found, pages = None, 0
    try:
        call(1, "initialize", {"clientInfo": {"name": "trust-network-e2a", "version": "1"}})
        process.stdin.write(json.dumps({"method": "initialized"}) + "\n")
        process.stdin.flush()
        params = {"limit": 200, "forceRefetch": True}
        while found is None and params:
            pages += 1
            page = call(1 + pages, "app/list", params)
            found = next((app for app in page["data"] if app["id"] == GOOGLE_CALENDAR), None)
            params = (
                {"limit": 200, "cursor": page["nextCursor"]} if page.get("nextCursor") else None
            )
    finally:
        timer.cancel()
        process.kill()
    if not found or not found.get("isAccessible"):
        raise SystemExit(
            f"Google Calendar connector {GOOGLE_CALENDAR} is "
            + ("not listed" if not found else "listed but not accessible")
            + f" for CODEX_HOME={codex_home} after {pages} app/list page(s). Link Google Calendar "
            "in Codex with the signed-in ChatGPT account, then rerun --stage calendar."
        )
    return {key: found.get(key) for key in ("id", "name", "isAccessible", "isEnabled")}


def linked_codex_home(path):
    path.mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path.home() / ".codex/config.toml", path / "config.toml")
    (path / "auth.json").symlink_to(Path.home() / ".codex/auth.json")


def codex_json(codex_home, workdir, prompt, schema, name):
    """One fresh ``codex exec`` turn with a JSON-schema answer; its traces stay private."""
    from trustnet.tn import wake

    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / f"{name}.schema.json").write_text(json.dumps(schema))
    answer = workdir / f"{name}.json"
    result = subprocess.run(
        [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "-m",
            wake.MODELS["codex"],
            "-s",
            "read-only",
            "-C",
            str(workdir),
            "-c",
            "features.shell_tool=false",
            "-c",
            'web_search="disabled"',
            "--output-schema",
            str(workdir / f"{name}.schema.json"),
            "-o",
            str(answer),
            "-",
        ],  # fmt: skip
        input=prompt,
        env={**os.environ, "CODEX_HOME": str(codex_home)},
        capture_output=True,
        text=True,
        timeout=300,
    )
    (workdir / f"{name}.stdout").write_text(result.stdout)
    (workdir / f"{name}.stderr").write_text(result.stderr)
    if result.returncode or not answer.exists():
        raise RuntimeError(f"codex {name} turn exited {result.returncode}; see {workdir}")
    return json.loads(answer.read_text())


def strict(properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


EVENT_SCHEMA = strict(
    {
        "found": {"type": "boolean"},
        **{
            key: {"type": "string"}
            for key in ("id", "summary", "start", "end", "location", "description", "status")
        },
    }
)
DELETE_SCHEMA = strict(
    {"deleted": {"type": "boolean"}, "id": {"type": "string"}, "receipt": {"type": "string"}}
)


async def calendar(live):
    from icalendar import Calendar

    from scripts.e2a_real_agents import Acceptance, environment
    from trustnet.gate import calendar_jobs
    from trustnet.tn import wake
    from trustnet.tn.configuration import apply

    class OwnerTurns(Acceptance):
        """e2a_real_agents turn driving, limited to explicit owner messages.

        News turns belong to the launchd wake runners. Calling ``watch`` here
        would move their cursor and hide the news from them.
        """

        def attach(self, person, env):
            self.envs[person] = env
            link = self.output / "profiles" / person
            link.parent.mkdir(exist_ok=True)
            link.symlink_to(Path(env["TN_CONFIG_DIR"]) / "profiles" / person)
            invoke, label = wake.invoker(person, "codex")

            def traced(reply, invoke=invoke, person=person):
                argv, extra, reader = invoke(reply)
                count = sum(t["person"] == person for t in self.turns)
                trace = self.output / f"{person}-owner-turn-{count}"
                request = trace.with_suffix(".request.json")
                request.write_text(json.dumps({"argv": argv, "trace": str(trace)}))
                return [sys.executable, str(self.proxy), str(request)], extra, reader

            with environment(env):
                apply(override=True)
                self.runners[person] = wake.Runner(person, traced, label, every=2)

        async def turn(self, person, message):
            runner = self.runners[person]
            started = time.time()
            with environment(self.envs[person]):
                apply(override=True)
                before = len(runner.transcript)
                await runner.say(message)
            self.turns.append(
                {
                    "person": person,
                    "owner_message": message,
                    "started": started,
                    "ended": time.time(),
                    "transcript_delta": runner.transcript[before:],
                }
            )
            if runner.carry:
                raise RuntimeError(f"Owner turn failed for {person}; inspect its private trace")

    async def wait(predicate, seconds, what):
        deadline = time.monotonic() + seconds
        while not predicate():
            if time.monotonic() > deadline:
                raise TimeoutError(f"{what} within {seconds}s")
            await asyncio.sleep(3)

    a, b = live.names
    evidence = live.evidence
    homes = {p: live.output / "people" / p / "codex-home" for p in live.names}
    for home in homes.values():
        linked_codex_home(home)
    evidence["preflight"] = connector_preflight(homes[a])
    live.install()
    live.start_host()
    title = f"trust-network E2E {live.stamp}"
    place = "Cafe Test Room, Indiranagar"
    start = (
        (datetime.now(timezone.utc) + timedelta(days=3))
        .replace(hour=9, minute=0, second=0, microsecond=0)
        .isoformat()
    )
    personas = {
        a: (
            "Your calendar is Google Calendar through the Codex Google Calendar connector. "
            "For a confirmed create calendar task, first search the primary calendar for the task "
            "uid. If no event carries it, create exactly one event with the plan's title, start, "
            "duration and place as location, with the task uid in the description. Then call "
            "calendar_report with status applied, provider google-calendar and the event ID the "
            "connector returned. If the connector is missing or refuses a call, call "
            "calendar_report with status failed and the exact error. Never use cal_add."
        ),
        b: (
            "Your calendar is this test's disposable local ICS file. For a confirmed create "
            "calendar task, call cal_add with the task uid as id, then calendar_report with "
            "provider local-ics and that exact event id."
        ),
    }
    os.environ["TN_DATA_DIR"] = str(live.output / "profiles")
    turns = OwnerTurns(live.output, live.names, ["codex", "codex"], live.base_env, start)
    evidence["plan_input"] = {"title": title, "place": place, "start": start}
    for person, peer, delivery in ((a, b, "agent"), (b, a, "ics")):
        profile = live.output / "people" / person / "config" / "profiles" / person
        profile.mkdir(parents=True)
        (profile / "agent.md").write_text(
            f"You are the real personal agent for isolated test person {person}. Your peer is "
            f"{peer}. This is an acceptance run. Automatic conversation is authorized. Use only "
            "trust-network tools and the calendar named below; do not message real contacts. "
            "The owner has NOT approved any plan until a later explicit message says so. "
            + personas[person]
            + " Never report a write without a successful tool result. Do not create duplicates."
        )
        evidence.setdefault("setup", {})[person] = live.join(
            person, "--calendar-delivery", delivery, "--timezone", "Asia/Kolkata"
        )
    for person, peer in ((a, b), (b, a)):
        live.tn(person, "trust", peer, "friend")
        turns.attach(person, live.env[person])
    evidence["installed"] = until(live.all_running, 30, "units were not running after setup")

    await turns.turn(
        a,
        f"Please propose a 30-minute plan titled exactly '{title}' with {b} at '{place}' "
        f"starting {start}. Use group_plan_create, check status using its returned token, and "
        "wait for my approval. Do not vote or add an event yet.",
    )
    await wait(lambda: all(turns.plan(p) for p in live.names), 300, "both gates hold the plan")
    assert all(turns.plan(p)["votes"] == {} for p in live.names), "Agent invented owner consent"
    reference = turns.plan(a)["id"]
    await turns.turn(
        b,
        "Read the new group plan and use dm_post in its room to tell the other agent that the "
        "proposed time works. Wait for my explicit approval before voting.",
    )
    await turns.turn(
        a,
        f"I approve the exact current plan {reference}. Read its revision and fingerprint and "
        "relay my yes for that revision only.",
    )
    await wait(lambda: all(a in turns.plan(p)["votes"] for p in live.names), 300, "A's vote")
    assert all(calendar_jobs.all_tasks(p) == [] for p in live.names), "one yes queued a task"
    evidence["tasks_after_last_owner_turn_of_a"] = calendar_jobs.all_tasks(a)
    await turns.turn(
        b,
        f"I approve the exact current plan {reference}. Read its current revision and "
        "fingerprint and relay my yes.",
    )
    await wait(
        lambda: all(turns.plan(p)["status"] == "confirmed" for p in live.names), 300, "confirmed"
    )

    def delivered(person):
        tasks = calendar_jobs.all_tasks(person)
        if tasks and tasks[0]["status"] == "failed":
            raise AssertionError(f"{person}'s agent reported delivery failed: {tasks[0]['error']}")
        return bool(tasks) and all(t["status"] == "applied" for t in tasks)

    await wait(lambda: delivered(a), 900, "A's launchd wake runner did not deliver to Google")
    evidence["a_task_applied_seen"] = time.time()
    await wait(lambda: delivered(b), 600, "B's calendar task was not applied")
    task = calendar_jobs.all_tasks(a)[0]
    plan = turns.plan(a)
    work = live.output / "codex-readback"
    readback = (
        f"Use the Google Calendar connector to get the event with id {task['event_id']} from the "
        "primary calendar. Do not create, change or delete anything. Return its id, summary, "
        "start and end as RFC 3339 date-times with offsets, location, description and status "
        "exactly as the connector returns them. If it does not exist, return found false and "
        "empty strings."
    )
    evidence["readback"] = codex_json(homes[a], work, readback, EVENT_SCHEMA, "readback")
    evidence["deletion"] = codex_json(
        homes[a],
        work,
        f"Use the Google Calendar connector to delete only the event with id {task['event_id']} "
        "from the primary calendar. Return deleted true only if the connector confirmed it, the "
        "id, and the connector's response as receipt.",
        DELETE_SCHEMA,
        "delete",
    )
    evidence["readback_after_delete"] = codex_json(
        homes[a], work, readback, EVENT_SCHEMA, "readback-after-delete"
    )
    evidence["state"] = turns.snapshot()
    evidence["plan"] = plan
    evidence["owner_turns"] = turns.turns
    evidence["b_events"] = [
        str(event["UID"])
        for event in Calendar.from_ical(evidence["state"][b]["calendar"]).walk("VEVENT")
    ]
    evidence["final_stop"] = {p: live.stop(p) for p in live.names}
    evidence["codex_auth_links"] = {
        p: (home / "auth.json").is_symlink()
        and (home / "auth.json").resolve() == (Path.home() / ".codex/auth.json").resolve()
        for p, home in homes.items()
    }


def verify_calendar(report, output):
    from icalendar import Calendar

    evidence, (a, b) = report["evidence"], report["people"]
    assert evidence["preflight"]["isAccessible"] is True
    for person in (a, b):
        for role in ROLES:
            assert running(evidence["installed"][person][role]), f"{person} {role} not running"
    state = evidence["state"]
    plans = [next(iter(state[p]["plans"]["plans"].values())) for p in (a, b)]
    assert len({plan["fingerprint"] for plan in plans}) == 1, "Participants disagree"
    plan = plans[0]
    content = plan["content"]
    assert plan["status"] == "confirmed" and set(plan["votes"]) == {a, b}
    assert content["title"] == evidence["plan_input"]["title"]
    start = datetime.fromisoformat(content["start"])
    assert start - datetime.fromisoformat(report["started_at"]) >= timedelta(days=2)
    assert evidence["tasks_after_last_owner_turn_of_a"] == [], "A's task existed during its turn"
    last_a_turn = max(t["ended"] for t in evidence["owner_turns"] if t["person"] == a)
    assert last_a_turn < evidence["a_task_applied_seen"]
    (task,) = state[a]["calendar_jobs"]
    assert task["status"] == "applied" and task["uid"] == plan["uid"]
    assert task["provider"] and task["event_id"]
    event = evidence["readback"]
    assert event["found"] and event["id"] == task["event_id"]
    assert event["summary"] == content["title"]
    assert event["location"] == content["place"]
    assert datetime.fromisoformat(event["start"]) == start
    assert datetime.fromisoformat(event["end"]) - start == timedelta(minutes=content["minutes"])
    assert plan["uid"] in event["description"], "the UID marker is missing from the event"
    assert evidence["deletion"]["deleted"] and evidence["deletion"]["id"] == task["event_id"]
    gone = evidence["readback_after_delete"]
    assert not gone["found"] or gone["status"] == "cancelled", "the test event still exists"
    (ics_task,) = state[b]["calendar_jobs"]
    assert ics_task["status"] == "applied" and ics_task["provider"] == "local-ics"
    (ics,) = Calendar.from_ical(state[b]["calendar"]).walk("VEVENT")
    assert str(ics["UID"]) == plan["uid"] and str(ics["SUMMARY"]) == content["title"]
    assert str(ics["LOCATION"]) == content["place"] and ics.decoded("DTSTART") == start
    assert ics.decoded("DTEND") - ics.decoded("DTSTART") == timedelta(minutes=content["minutes"])
    actual = output / "profiles" / b / "calendar.ics"
    assert actual.read_text() == state[b]["calendar"], "saved ICS differs from the report"
    for person in (a, b):
        stopped = evidence["final_stop"][person]
        assert all(unloaded(r) for r in stopped["units"].values()) and not stopped["processes"]
    assert all(evidence["codex_auth_links"].values()), "a CODEX_HOME auth link was replaced"
    verify_cleanup(report, output)


STAGES = {"services": (services, verify_services), "calendar": (calendar, verify_calendar)}


def main(args):
    if sys.platform != "darwin":
        raise SystemExit("This acceptance drives macOS launchd")
    started = datetime.now(timezone.utc)
    output = ROOT / "data" / ("live-services-" + started.strftime("%Y%m%dT%H%M%S"))
    output.mkdir(mode=0o700, parents=True)
    prefix = {"services": "lsv", "calendar": "lcal"}[args.stage]
    names = [f"{prefix}{int(started.timestamp())}{s}" for s in "ab"]
    live = Live(output, names, args.server, started.strftime("%Y%m%dT%H%M%S"))
    report = {
        "stage": args.stage,
        "started_at": started.isoformat(),
        "people": names,
        "switch": args.server,
        "launch_agents": str(LAUNCH_AGENTS),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "git_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True)),
    }
    stage, verify = STAGES[args.stage]
    error = None
    try:
        if args.stage == "services":
            stage(live)
        else:
            asyncio.run(stage(live))
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        live.cleanup()
        report.update(evidence=live.evidence, findings=live.findings)
        if error is None:
            try:
                verify(report, output)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
        report["status"] = "FAIL" if error else "PASS"
        if error:
            report["error"] = error
        if any(secret in json.dumps(report) for secret in secrets(output) | live.invite_tokens):
            report = {key: report[key] for key in ("stage", "started_at", "people")}
            report.update(status="FAIL", error="a credential reached the report; evidence dropped")
        (output / "report.json").write_text(json.dumps(report, indent=2))
        print(f"{report['status']}: {output / 'report.json'}", flush=True)
        if error:
            print(error, flush=True)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=sorted(STAGES))
    parser.add_argument("--server", default="http://127.0.0.1:53330")
    parser.add_argument("--verify", type=Path, help="verify a saved report without live calls")
    args = parser.parse_args()
    if args.verify:
        report = json.loads(args.verify.read_text())
        assert report["status"] == "PASS", "The live run failed: " + report.get("error", "")
        STAGES[report["stage"]][1](report, args.verify.parent)
        print(f"PASS saved {report['stage']} artifact: {args.verify}")
    elif args.stage:
        sys.exit(main(args))
    else:
        parser.error("choose --stage or --verify")
