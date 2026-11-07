"""Live acceptance for the real launchd gate and wake services (no model calls).

Failure cases, before implementation:
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

Google Calendar delivery under launchd is scripts/e2a_hermes_calendar.py.

Each person is a fresh Switch user created by a private onboarding host
(``tn host``) with the Console administrator credentials, and joins with the
documented ``tn setup '<invite>' ... --background-service`` command. A launchd
unit sees only the saved configuration, so its identity endpoint must come from
the invite rather than from this script's environment. Every TN_CONFIG_DIR and
CODEX_HOME lives under data/live-services-<timestamp>/; ~/.config/trust-network
and ~/.codex/config.toml are never written. The units run an isolated
``uv tool install`` of this checkout under the same directory: the documented
install path, frozen at the tested commit and kept after the run.

After each tn stop the script bootstraps every plist left in
~/Library/LaunchAgents, as launchd does at login, and requires launchd to refuse
it. The test labels stay in launchd's disabled database (launchctl
print-disabled), which has no command to remove an entry.

    uv run python -m scripts.e2a_live_services
    uv run python -m scripts.e2a_live_services --verify data/live-services-<timestamp>/report.json

``--verify`` re-checks a saved report and the private files beside it, with no
launchd, Switch or model call. Test Switch accounts remain for inspection.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
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


def launchd_disabled(label):
    """This label's entry in launchd's persistent disabled database, which login honours."""
    listing = subprocess.run(
        ["launchctl", "print-disabled", DOMAIN], capture_output=True, text=True
    ).stdout
    for line in listing.splitlines():
        name, separator, value = line.strip().partition(" => ")
        if separator and name.strip('"') == label:
            return value
    return None


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
        "run_at_load": payload.get("RunAtLoad"),
        "launchd_disabled": launchd_disabled(label),
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
    def __init__(self, output, names, server):
        self.output, self.names, self.server = output, names, server
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
            "login_load": self.login_load(person, units),
        }

    def login_load(self, person, units):
        """Bootstrap each remaining plist as launchd does for LaunchAgents at login."""
        attempts = {}
        for role, unit in units.items():
            if not unit["plist_exists"]:
                continue
            result = subprocess.run(
                ["launchctl", "bootstrap", DOMAIN, unit["plist"]], capture_output=True, text=True
            )
            time.sleep(2)
            attempts[role] = {
                "returncode": result.returncode,
                "stderr": result.stderr.strip(),
                "after": observe(person, role),
            }
        return attempts

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
            for role, unit in stopped["units"].items():
                assert unit["plist_exists"] and unit["run_at_load"], (
                    f"{phase}: {person} {role} plist is gone, so a bare tn setup cannot restart it"
                )
                assert unit["launchd_disabled"] == "disabled", (
                    f"{phase}: launchd would load {person} {role} at the next login"
                )
                login = stopped["login_load"][role]
                assert login["returncode"] != 0 and unloaded(login["after"]), (
                    f"{phase}: bootstrapping the stopped {person} {role} plist loaded it"
                )
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


def main(args):
    if sys.platform != "darwin":
        raise SystemExit("This acceptance drives macOS launchd")
    started = datetime.now(timezone.utc)
    output = ROOT / "data" / ("live-services-" + started.strftime("%Y%m%dT%H%M%S"))
    output.mkdir(mode=0o700, parents=True)
    names = [f"lsv{int(started.timestamp())}{s}" for s in "ab"]
    live = Live(output, names, args.server)
    report = {
        "started_at": started.isoformat(),
        "people": names,
        "switch": args.server,
        "launch_agents": str(LAUNCH_AGENTS),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "git_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True)),
    }
    error = None
    try:
        services(live)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        live.cleanup()
        report.update(evidence=live.evidence, findings=live.findings)
        if error is None:
            try:
                verify_services(report, output)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
        report["status"] = "FAIL" if error else "PASS"
        if error:
            report["error"] = error
        if any(secret in json.dumps(report) for secret in secrets(output) | live.invite_tokens):
            report = {key: report[key] for key in ("started_at", "people")}
            report.update(status="FAIL", error="a credential reached the report; evidence dropped")
        (output / "report.json").write_text(json.dumps(report, indent=2))
        print(f"{report['status']}: {output / 'report.json'}", flush=True)
        if error:
            print(error, flush=True)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default="http://127.0.0.1:53330")
    parser.add_argument("--verify", type=Path, help="verify a saved report without live calls")
    args = parser.parse_args()
    if args.verify:
        report = json.loads(args.verify.read_text())
        assert report["status"] == "PASS", "The live run failed: " + report.get("error", "")
        verify_services(report, args.verify.parent)
        print(f"PASS saved services artifact: {args.verify}")
    else:
        sys.exit(main(args))
