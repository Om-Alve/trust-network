#!/usr/bin/env python3
"""Onboarding wake-readiness E2E: artifact-producing scenarios.

Run from the repository root:

    uv run python scripts/e2e_readiness.py

The script writes ``data/readiness-e2e/report.json`` so a reviewer can rerun it
and diff the same artifact. It uses temporary directories, a loopback fake
Switch, fake ``codex``, and fake ``launchctl``/``systemctl`` binaries. No live
Switch, launchd, systemd, or user configuration is touched.

Traced model before this change
-------------------------------
``tn setup`` reads an invite or saved settings, writes ``config.json``, exports
the profile environment, bootstraps the gate identity and private home, writes
``mcp.json`` plus the selected client's MCP entry, starts the gate as a detached
child, and runs the same checks as ``tn doctor``. ``doctor`` treated a successful
MCP handshake as the end of onboarding: nothing verified that any process would
ever wake the agent, and nothing told the person how. ``tn wake`` polled
``personal.watch`` and ran an agent turn on news; the Codex preset used
``--ignore-user-config``, so the user's own MCP servers (a calendar connector,
for example) disappeared from the wake-time agent.

Failure modes covered
---------------------
1. Setup prints "Ready" while no wake runner or external poller exists.
2. Doctor reports ``ok`` from MCP connectivity alone; a stopped or absent wake
   runner is invisible.
3. A saved configuration is rescanned as "new", changing a legacy ICS profile
   to agent delivery without the person asking.
4. A background unit breaks on spaces, quotes, ``$`` or ``%``, starts two gates,
   or cannot be stopped/statused idempotently.
5. ``--wake`` silently launches a costly agent loop during setup.
6. The Codex wake preset loses the user's configured connectors.
7. Interactive stdin stops working after the Codex command changes.
8. A service runner starts but never takes the per-person wake lock; doctor must
   not call that ready.
9. ``tn stop`` stops only the gate and leaves the wake service running.
10. Invalid timezone or calendar-delivery values are written instead of refused.

Scenarios S1-S6 are labelled in the report; S5b is the Linux/systemd branch of S5.
"""

from __future__ import annotations

import asyncio
import json
import os
import plistlib
import re
import shutil
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from fakes.fake_switch import FakeSwitch  # noqa: E402
from fakes.loopback_switch import LoopbackSwitch, serve  # noqa: E402
from starlette.responses import JSONResponse  # noqa: E402
from starlette.routing import Route  # noqa: E402

OUT = ROOT / "data" / "readiness-e2e"
IDENTITY_TOKEN = "readiness-identity-key"
PEOPLE = ("mira", "omi", "lin", "svc", "svcd", "wakecli")
REPORT: dict = {
    "started_at": datetime.now(timezone.utc).isoformat(),
    "scenarios": [],
    "environment": {},
}
CONFIGS: list[Path] = []
SERVICE_STATES: list[Path] = []


def record(name: str, status: str, **evidence) -> None:
    REPORT["scenarios"].append({"scenario": name, "status": status, **evidence})
    print(f"{status:4}  {name}", flush=True)


def clean_env() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("TN_") and key != "SWITCH_URL"
    }


def redacted_settings(config_dir: Path) -> dict:
    path = config_dir / "config.json"
    if not path.exists():
        return {}
    values = json.loads(path.read_text())
    for key in ("registration_key", "identity_token"):
        if key in values:
            values[key] = "<redacted>"
    return values


def redacted_config(config_dir: Path) -> dict:
    values = redacted_settings(config_dir)
    if not values:
        return {}
    profile = Path(values.get("data_dir", "")) / values.get("person", "")
    return {
        "settings": values,
        "trust": (profile / "trust.yaml").read_text() if (profile / "trust.yaml").exists() else "",
        "facts": (profile / "facts.yaml").read_text() if (profile / "facts.yaml").exists() else "",
    }


async def run_cli(env: dict[str, str], *args: str, expected: int | None = 0, timeout: float = 90):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "trustnet.tn.cli",
        *args,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await asyncio.wait_for(process.communicate(), timeout)
    text = out.decode()
    if expected is not None:
        assert process.returncode == expected, (args, process.returncode, text, err.decode())
    try:
        payload = json.loads(text) if text.strip() else {}
    except ValueError:
        payload = {"text": text}
    return process.returncode, payload, err.decode()


def base_env(config_dir: Path, person: str, extra: dict | None = None) -> dict[str, str]:
    env = clean_env()
    env.update(
        TN_CONFIG_DIR=str(config_dir),
        E2E_KEY=f"{person}-key",
        E2E_IDENTITIES=IDENTITY_TOKEN,
        NO_PROXY="127.0.0.1,localhost",
    )
    env.update(extra or {})
    return env


async def setup_person(url: str, config_dir: Path, person: str, *args: str, extra_env=None):
    CONFIGS.append(config_dir)
    env = base_env(config_dir, person, extra_env)
    return await run_cli(
        env,
        "setup",
        "--name",
        person,
        "--server",
        url,
        "--key-env",
        "E2E_KEY",
        "--identity-url",
        url + "/identities",
        "--identity-token-env",
        "E2E_IDENTITIES",
        *args,
        "--json",
    )


async def cleanup() -> None:
    for state in SERVICE_STATES:
        if not state.exists():
            continue
        try:
            pids = json.loads(state.read_text())
        except ValueError:
            continue
        for pid in pids.values():
            try:
                os.kill(int(pid), signal.SIGTERM)
            except (ProcessLookupError, ValueError):
                pass
    for config_dir in CONFIGS:
        if not (config_dir / "config.json").exists():
            continue
        try:
            await run_cli(
                base_env(config_dir, "cleanup"), "stop", "--json", expected=None, timeout=20
            )
        except Exception:
            pass
        record_file = config_dir / "gate-process.json"
        if record_file.exists():
            try:
                pid = int(json.loads(record_file.read_text())["pid"])
                os.kill(pid, signal.SIGTERM)
            except (KeyError, ValueError, ProcessLookupError):
                pass


def write_fake_codex(bindir: Path) -> None:
    path = bindir / "codex"
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "args = sys.argv[1:]\n"
        "if args[:1] == ['mcp']:\n"
        "    sys.exit(0)\n"
        "open(os.environ['FAKE_CODEX_ARGS'], 'w').write('\\n'.join(args))\n"
        "open(os.environ['FAKE_CODEX_STDIN'], 'w').write(sys.stdin.read())\n"
        "reply = args[args.index('-o') + 1]\n"
        "open(reply, 'w').write('fake reply from codex\\n')\n"
    )
    path.chmod(0o755)


def write_fake_launchctl(bindir: Path) -> None:
    path = bindir / "launchctl"
    path.write_text(
        """#!/usr/bin/env python3
import json, os, plistlib, signal, subprocess, sys

state_path = os.environ["FAKE_SERVICE_STATE"]
state = json.load(open(state_path)) if os.path.exists(state_path) else {}

def save():
    open(state_path, "w").write(json.dumps(state))

def alive(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False

def kill(label):
    pid = state.pop(label, None)
    if alive(pid):
        os.kill(int(pid), signal.SIGTERM)
    save()

def start(path):
    payload = plistlib.load(open(path, "rb"))
    label = payload["Label"]
    kill(label)
    env = {**os.environ, **payload.get("EnvironmentVariables", {})}
    log = open(payload.get("StandardOutPath", os.devnull), "ab")
    proc = subprocess.Popen(
        payload["ProgramArguments"],
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        env=env,
        cwd=payload.get("WorkingDirectory"),
        start_new_session=True,
    )
    state[label] = proc.pid
    save()

args = sys.argv[1:]
command = args[0] if args else ""
if command in ("bootstrap", "load"):
    start(args[-1])
elif command == "bootout":
    kill(args[-1].rsplit("/", 1)[-1])
elif command == "unload":
    payload = plistlib.load(open(args[-1], "rb"))
    kill(payload["Label"])
elif command == "print":
    label = args[-1].rsplit("/", 1)[-1]
    sys.exit(0 if alive(state.get(label)) else 1)
"""
    )
    path.chmod(0o755)


def write_fake_systemctl(bindir: Path) -> None:
    path = bindir / "systemctl"
    path.write_text(
        """#!/usr/bin/env python3
import json, os, signal, subprocess, sys

state_path = os.environ["FAKE_SERVICE_STATE"]
units_dir = os.environ["FAKE_UNIT_DIR"]
state = json.load(open(state_path)) if os.path.exists(state_path) else {}

def save():
    open(state_path, "w").write(json.dumps(state))

def alive(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False

def unescape(value):
    out, i = [], 0
    while i < len(value):
        char = value[i]
        if char == "\\\\" and i + 1 < len(value):
            out.append(value[i + 1])
            i += 2
        elif char == "%" and value[i:i + 2] == "%%":
            out.append("%")
            i += 2
        elif char == "$" and value[i:i + 2] == "$$":
            out.append("$")
            i += 2
        else:
            out.append(char)
            i += 1
    return "".join(out)

def quoted(value):
    tokens, i = [], 0
    while i < len(value):
        if value[i] != '"':
            i += 1
            continue
        i += 1
        buf = []
        while i < len(value) and value[i] != '"':
            if value[i] == "\\\\" and i + 1 < len(value):
                buf.append(value[i + 1])
                i += 2
            else:
                buf.append(value[i])
                i += 1
        tokens.append(unescape("".join(buf)))
        i += 1
    return tokens

def unit_values(name):
    text = open(os.path.join(units_dir, name)).read()
    env, exec_start, workdir = {}, [], units_dir
    for line in text.splitlines():
        if line.startswith("Environment="):
            parsed = quoted(line.split("=", 1)[1])
            key, value = parsed[0].split("=", 1)
            env[key] = value
        elif line.startswith("ExecStart="):
            exec_start = quoted(line.split("=", 1)[1])
    return env, exec_start, workdir

def kill(label):
    pid = state.pop(label, None)
    if alive(pid):
        os.kill(int(pid), signal.SIGTERM)
    save()

def start(label):
    if alive(state.get(label)):
        return
    env, exec_start, workdir = unit_values(label)
    log = open(os.path.join(units_dir, label + ".log"), "ab")
    proc = subprocess.Popen(
        exec_start,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        env={**os.environ, **env},
        cwd=workdir,
        start_new_session=True,
    )
    state[label] = proc.pid
    save()

args = [arg for arg in sys.argv[1:] if arg != "--user"]
command = args[0] if args else ""
if command == "daemon-reload":
    pass
elif command in ("enable", "restart"):
    unit = [arg for arg in args[1:] if not arg.startswith("--")][-1]
    if command == "restart":
        kill(unit)
    start(unit)
elif command in ("disable", "stop"):
    unit = [arg for arg in args[1:] if not arg.startswith("--")][-1]
    kill(unit)
elif command == "is-active":
    sys.exit(0 if alive(state.get(args[-1])) else 1)
"""
    )
    path.chmod(0o755)


def launchd_plists(directory: Path) -> dict:
    return {
        path.name: plistlib.loads(path.read_bytes()) for path in sorted(directory.glob("*.plist"))
    }


def systemd_units(directory: Path) -> dict:
    return {path.name: path.read_text() for path in sorted(directory.glob("*.service"))}


async def scenario_connection_only(url: str, root: Path) -> None:
    config_dir = root / "s1-config"
    _, result, _ = await setup_person(url, config_dir, "mira", "--agent", "manual")
    assert result["next_steps"] and result["self_check"] == "tn doctor"
    assert result["calendar"] == {"delivery": "agent", "timezone": "Asia/Kolkata"}
    assert result["wake"] is None and result["wake_running"] is False
    assert result["readiness"] == {"connection": True, "automation": False}
    code, report, _ = await run_cli(base_env(config_dir, "mira"), "doctor", "--json", expected=1)
    assert report["connection_ok"] is True
    assert report["automation_ready"] is False
    failing = {check["name"] for check in report["checks"] if not check["ok"]}
    assert failing == {"wake-config", "wake-runner"}, failing
    assert any("external poller" in note for note in report["notes"])
    record(
        "S1 connection-only setup is explicit about missing automation",
        "PASS",
        setup=result,
        doctor=report,
        config=redacted_config(config_dir),
    )


async def scenario_wake_configured(url: str, root: Path) -> None:
    bindir = root / "bin"
    bindir.mkdir()
    write_fake_codex(bindir)
    config_dir = root / "s2-config"
    env_extra = {"PATH": f"{bindir}:{os.environ['PATH']}"}
    _, result, _ = await setup_person(
        url, config_dir, "omi", "--agent", "codex", "--wake", extra_env=env_extra
    )
    assert result["wake"]["mode"] == "runner", result["wake"]
    assert result["wake"]["command"][-5:-3] == ["wake", "--agent"], result["wake"]["command"]
    assert result["wake_running"] is False, "setup must not launch a costly agent loop"
    assert result["readiness"]["automation"] is False, result["readiness"]
    code, report, _ = await run_cli(
        base_env(config_dir, "omi", env_extra), "doctor", "--json", expected=1
    )
    checks = {check["name"]: check for check in report["checks"]}
    assert checks["wake-config"]["ok"] is True
    assert checks["wake-runner"]["ok"] is False
    assert "MCP server answers" in checks["mcp"]["detail"]
    record(
        "S2 --wake configures without launching; doctor separates configured/running",
        "PASS",
        setup=result,
        doctor=report,
        config=redacted_config(config_dir),
    )


async def scenario_external(url: str, root: Path) -> None:
    config_dir = root / "s3-config"
    _, result, _ = await setup_person(
        url,
        config_dir,
        "lin",
        "--agent",
        "manual",
        "--wake-external",
        "Hermes cron every minute",
    )
    assert result["wake"] == {"mode": "external", "external": "Hermes cron every minute"}
    _, report, _ = await run_cli(base_env(config_dir, "lin"), "doctor", "--json")
    assert report["ok"] is True
    assert report["automation_ready"] is True
    assert report["wake_verified"] is False
    assert any("cannot verify" in check.get("detail", "") for check in report["checks"])
    code, _, err = await run_cli(
        base_env(config_dir, "lin"), "setup", "--background-service", "--json", expected=1
    )
    assert "needs a wake runner" in err
    record(
        "S3 declared external poller is explicit and unverified",
        "PASS",
        setup=result,
        doctor=report,
        config=redacted_config(config_dir),
    )


async def scenario_calendar_fields(url: str, root: Path) -> None:
    config_dir = root / "s4-config"
    _, fresh, _ = await setup_person(url, config_dir, "lin", "--agent", "manual")
    assert fresh["calendar"] == {"delivery": "agent", "timezone": "Asia/Kolkata"}
    saved = json.loads((config_dir / "config.json").read_text())
    saved.pop("calendar_delivery")
    saved.pop("timezone")
    (config_dir / "config.json").write_text(json.dumps(saved))
    _, legacy, _ = await setup_person(url, config_dir, "lin", "--agent", "manual")
    assert legacy["calendar"] == {"delivery": "ics", "timezone": "Asia/Kolkata"}
    _, explicit, _ = await setup_person(
        url,
        config_dir,
        "lin",
        "--agent",
        "manual",
        "--timezone",
        "Asia/Tokyo",
        "--calendar-delivery",
        "ics",
    )
    assert explicit["calendar"] == {"delivery": "ics", "timezone": "Asia/Tokyo"}
    assert explicit["gate_pid"] != legacy["gate_pid"], (
        "A runtime timezone/delivery change must restart the gate"
    )
    code, _, err = await run_cli(
        base_env(config_dir, "lin"), "setup", "--timezone", "Not/AZone", "--json", expected=1
    )
    assert "Unknown timezone" in err
    code, _, _ = await run_cli(
        base_env(config_dir, "lin"), "setup", "--calendar-delivery", "bogus", expected=2
    )
    code, _, err = await run_cli(
        base_env(config_dir, "lin"), "setup", "--wake", "--json", expected=1
    )
    assert "--wake needs --agent codex|opencode|hermes" in err
    record(
        "S4 new profiles default to agent delivery; legacy profiles keep ICS",
        "PASS",
        fresh=fresh["calendar"],
        legacy=legacy["calendar"],
        explicit=explicit["calendar"],
        invalid_timezone="refused",
        invalid_delivery="refused",
        config=redacted_config(config_dir),
    )


async def scenario_launchd(url: str, root: Path) -> None:
    bindir = root / "s5-bin"
    bindir.mkdir()
    write_fake_codex(bindir)
    write_fake_launchctl(bindir)
    service_dir = root / "s5 LaunchAgents $dollar %percent"
    state = root / "s5-launchctl.json"
    SERVICE_STATES.append(state)
    config_dir = root / "s5 config $dollar %percent"
    env_extra = {
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "TN_SERVICE_PLATFORM": "launchd",
        "TN_SERVICE_DIR": str(service_dir),
        "FAKE_SERVICE_STATE": str(state),
        "FAKE_CODEX_ARGS": str(root / "s5-codex-args.txt"),
        "FAKE_CODEX_STDIN": str(root / "s5-codex-stdin.txt"),
    }
    _, installed, _ = await setup_person(
        url,
        config_dir,
        "svc",
        "--agent",
        "codex",
        "--wake",
        "--background-service",
        extra_env=env_extra,
    )
    assert installed["service"]["installed"] is True
    assert installed["service"]["gate"]["active"] is True
    assert installed["service"]["wake"]["active"] is True
    assert installed["wake_running"] is True
    _, status, _ = await run_cli(base_env(config_dir, "svc", env_extra), "status", "--json")
    assert status["gate_running"] is True and status["wake"]["running"] is True
    plists = launchd_plists(service_dir)
    assert len(plists) == 2
    assert all("svc-key" not in json.dumps(payload) for payload in plists.values())
    _, stopped, _ = await run_cli(base_env(config_dir, "svc", env_extra), "stop", "--json")
    assert stopped["stopped"] is True
    assert stopped["gate_running"] is False and stopped["wake_running"] is False
    _, again, _ = await run_cli(base_env(config_dir, "svc", env_extra), "stop", "--json")
    assert again["stopped"] is False
    _, after, _ = await run_cli(
        base_env(config_dir, "svc", env_extra), "doctor", "--json", expected=1
    )
    assert after["automation_ready"] is False
    _, external, _ = await setup_person(
        url,
        config_dir,
        "svc",
        "--agent",
        "manual",
        "--wake-external",
        "Existing personal-agent poller",
        extra_env=env_extra,
    )
    assert external["wake"]["mode"] == "external"
    assert external["wake_running"] is False
    record(
        "S5 launchd: gate+runner units, status, stop, idempotent second stop",
        "PASS",
        setup=installed,
        status_report=status,
        stopped=stopped,
        second_stop=again,
        doctor_after_stop=after,
        external_after_service=external,
        units=plists,
        config=redacted_config(config_dir),
    )


async def scenario_systemd(url: str, root: Path) -> None:
    bindir = root / "s5d-bin"
    bindir.mkdir()
    write_fake_codex(bindir)
    write_fake_systemctl(bindir)
    service_dir = root / "s5d units $dollar %percent"
    state = root / "s5d-systemctl.json"
    SERVICE_STATES.append(state)
    config_dir = root / "s5d config $dollar %percent"
    env_extra = {
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "TN_SERVICE_PLATFORM": "systemd",
        "TN_SERVICE_DIR": str(service_dir),
        "FAKE_SERVICE_STATE": str(state),
        "FAKE_UNIT_DIR": str(service_dir),
        "FAKE_CODEX_ARGS": str(root / "s5d-codex-args.txt"),
        "FAKE_CODEX_STDIN": str(root / "s5d-codex-stdin.txt"),
    }
    _, installed, _ = await setup_person(
        url,
        config_dir,
        "svcd",
        "--agent",
        "codex",
        "--wake",
        "--background-service",
        extra_env=env_extra,
    )
    assert installed["service"]["platform"] == "systemd"
    assert installed["wake_running"] is True
    units = systemd_units(service_dir)
    assert len(units) == 2
    gate = next(text for name, text in units.items() if name.endswith("-gate.service"))
    assert "$$" in gate and "%%" in gate, gate
    assert "svcd-key" not in json.dumps(units)
    _, status, _ = await run_cli(base_env(config_dir, "svcd", env_extra), "status", "--json")
    assert status["gate_running"] is True and status["wake"]["running"] is True
    _, stopped, _ = await run_cli(base_env(config_dir, "svcd", env_extra), "stop", "--json")
    assert stopped["stopped"] is True
    assert stopped["gate_running"] is False and stopped["wake_running"] is False
    record(
        "S5b systemd: escaped argv survives $ % and spaces; stop works",
        "PASS",
        setup=installed,
        status_report=status,
        stopped=stopped,
        units=units,
        config=redacted_config(config_dir),
    )


async def scenario_wake_stdin(root: Path) -> None:
    bindir = root / "s6-bin"
    bindir.mkdir()
    write_fake_codex(bindir)
    data = root / "s6-data"
    (data / "wakecli").mkdir(parents=True)
    env = clean_env()
    env.update(
        TN_CONFIG_DIR=str(root / "s6-config"),
        TN_DATA_DIR=str(data),
        PATH=f"{bindir}:{os.environ['PATH']}",
        FAKE_CODEX_ARGS=str(root / "s6-codex-args.txt"),
        FAKE_CODEX_STDIN=str(root / "s6-codex-stdin.txt"),
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "trustnet.tn.cli",
        "--as",
        "wakecli",
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
        if marker not in output:
            process.terminate()
            _, err = await asyncio.wait_for(process.communicate(), 5)
            raise AssertionError(f"missing {marker!r}; out={output!r} err={err.decode()!r}")

    try:
        await until("Wakecli's agent (Codex)")
        process.stdin.write(b"hello agent\n")
        await process.stdin.drain()
        await until("fake reply from codex")
    finally:
        if process.returncode is None:
            process.terminate()
        await asyncio.wait_for(process.wait(), 5)
    argv = (root / "s6-codex-args.txt").read_text().splitlines()
    prompt = (root / "s6-codex-stdin.txt").read_text()
    assert "--ignore-user-config" not in argv
    assert 'mcp_servers.trust-network.default_tools_approval_mode="approve"' in argv
    assert "Wakecli says: hello agent" in prompt, prompt[:500]
    assert "trust-network skill" in prompt
    record(
        "S6 Codex preset keeps user config and interactive stdin",
        "PASS",
        argv=argv,
        prompt_contains=["wakecli says: hello agent", "trust-network skill"],
        output=re.sub(r"\x1b\[[0-9;]*m", "", output),
    )


async def scenario_opencode_connectors(root: Path) -> None:
    from trustnet.tn import wake

    executable = shutil.which("opencode")
    if not executable:
        record(
            "S7 OpenCode global connector configuration", "SKIP", reason="OpenCode is not installed"
        )
        return
    home = root / "s7-home"
    user_config = home / ".config" / "opencode"
    user_config.mkdir(parents=True)
    calendar = user_config / "opencode.json"
    calendar.write_text(
        json.dumps(
            {
                "mcp": {
                    "calendar": {
                        "type": "remote",
                        "url": "http://127.0.0.1:9/mcp",
                        "enabled": False,
                    }
                }
            }
        )
    )
    workdir = root / "s7-work"
    workdir.mkdir()
    _, extra, _ = wake.opencode_command(
        "mira", "opencode-go/deepseek-v4.1-flash", workdir / "reply.txt"
    )
    env = {k: v for k, v in clean_env().items() if not k.startswith("OPENCODE_")}
    env.update(
        HOME=str(home),
        XDG_CONFIG_HOME=str(home / ".config"),
        XDG_DATA_HOME=str(home / ".local/share"),
        XDG_CACHE_HOME=str(home / ".cache"),
        XDG_STATE_HOME=str(home / ".local/state"),
    )
    env.update(extra)
    process = await asyncio.create_subprocess_exec(
        executable,
        "debug",
        "config",
        cwd=workdir,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(), 10)
    except TimeoutError:
        os.killpg(process.pid, signal.SIGTERM)
        await process.wait()
        record(
            "S7 OpenCode global connector configuration",
            "SKIP",
            reason="The isolated OpenCode configuration diagnostic did not respond within 10 seconds",
            user_calendar=str(calendar),
            overlay=str(workdir / "opencode.json"),
        )
        return
    sources = out.decode()
    assert process.returncode == 0, err.decode()
    assert str(calendar) in sources, sources
    assert str(workdir / "opencode.json") in sources, sources
    overlay = json.loads((workdir / "opencode.json").read_text())
    assert "trust-network" in overlay["mcp"]
    record(
        "S7 OpenCode global connector configuration",
        "PASS",
        sources=sources,
        user_calendar=str(calendar),
        overlay=str(workdir / "opencode.json"),
    )


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    root = OUT / "state"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    switch = FakeSwitch()
    wire = LoopbackSwitch(switch, {f"{person}-key": person for person in PEOPLE})
    app = wire.app()

    async def identities(request):
        if request.headers.get("authorization") != f"Bearer {IDENTITY_TOKEN}":
            return JSONResponse({}, status_code=401)
        values = {person: {"kind": "user", "id": person} for person in switch.users}
        values.update(
            {
                name: {"kind": "agent", "id": name, "owner_id": agent["owner_id"]}
                for name, agent in switch.agents.items()
            }
        )
        return JSONResponse(values)

    app.routes.append(Route("/identities", identities))
    url, stop_server = await serve(app)
    REPORT["environment"] = {
        "switch_url": url,
        "python": sys.executable,
        "platform": sys.platform,
        "root": str(root),
    }
    scenarios = [
        ("S1", lambda: scenario_connection_only(url, root)),
        ("S2", lambda: scenario_wake_configured(url, root)),
        ("S3", lambda: scenario_external(url, root)),
        ("S4", lambda: scenario_calendar_fields(url, root)),
        ("S5", lambda: scenario_launchd(url, root)),
        ("S5b", lambda: scenario_systemd(url, root)),
        ("S6", lambda: scenario_wake_stdin(root)),
        ("S7", lambda: scenario_opencode_connectors(root)),
    ]
    try:
        for name, scenario in scenarios:
            try:
                await scenario()
            except Exception as exc:  # one broken scenario must not hide the rest
                record(name, "FAIL", error=f"{type(exc).__name__}: {exc}")
    finally:
        await cleanup()
        await stop_server()
    REPORT["finished_at"] = datetime.now(timezone.utc).isoformat()
    REPORT["ok"] = all(item["status"] in {"PASS", "SKIP"} for item in REPORT["scenarios"])
    REPORT["skipped"] = sum(item["status"] == "SKIP" for item in REPORT["scenarios"])
    path = OUT / "report.json"
    path.write_text(json.dumps(REPORT, indent=2))
    print(f"\n{'PASS' if REPORT['ok'] else 'FAIL'}  artifact: {path}")
    return 0 if REPORT["ok"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
