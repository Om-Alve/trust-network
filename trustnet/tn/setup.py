"""Connect a person to a shared server and verify the configured path."""

import asyncio
import fcntl
import getpass
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx

from trustnet.gate.facts import (
    Profile,
    TrustList,
    load_profile,
    load_trust,
    save_profile,
    save_trust,
)
from trustnet.gate.identity import IdentitySource
from trustnet.switch_client import SwitchClient
from trustnet.tn import configuration as config
from trustnet.tn import personal
from trustnet.tn.wake import PRESETS

WAKE_AGENTS = "--agent " + "|".join(PRESETS)
RETAINED_KEYS = ("agent", "consent", "wake", "timezone", "calendar_delivery")


def add_commands(commands, common):
    setup = commands.add_parser(
        "setup", parents=[common], help="join a shared server and configure your agent"
    )
    setup.add_argument("invite", nargs="?")
    setup.add_argument("--name")
    setup.add_argument("--server")
    setup.add_argument("--key-env")
    setup.add_argument("--identity-url")
    setup.add_argument("--identity-token-env")
    setup.add_argument("--agent", choices=("manual", "claude", *PRESETS))
    setup.add_argument(
        "--consent",
        choices=("direct", "via-agent"),
        help="who may relay your yes/no; default direct Switch-user approval",
    )
    setup.add_argument(
        "--wake",
        action="store_true",
        help=f"configure a tn wake runner for {WAKE_AGENTS} (does not launch it)",
    )
    setup.add_argument("--wake-model", help="model override for the configured wake runner")
    setup.add_argument(
        "--wake-every", type=float, help="seconds between watches for the wake runner (default 15)"
    )
    setup.add_argument(
        "--wake-external",
        metavar="DESCRIPTION",
        help="declare an external poller (for example a Hermes cron job) instead of tn wake",
    )
    setup.add_argument(
        "--background-service",
        action="store_true",
        help="install persistent launchd/systemd user services for the gate and wake runner",
    )
    setup.add_argument("--timezone", help="IANA timezone for this profile (default Asia/Kolkata)")
    setup.add_argument(
        "--calendar-delivery",
        choices=config.CALENDAR_DELIVERIES,
        help="agent (default for a new profile) or ics (kept for existing profiles)",
    )
    setup.add_argument("--no-start", action="store_true")
    setup.set_defaults(handler=setup_command)
    doctor = commands.add_parser(
        "doctor", parents=[common], help="check this person's complete connection and readiness"
    )
    doctor.set_defaults(handler=doctor_command)
    status = commands.add_parser(
        "status", parents=[common], help="show gate, wake-runner and background-service status"
    )
    status.set_defaults(handler=status_command)
    stop = commands.add_parser("stop", parents=[common], help="stop the gate and wake service")
    stop.set_defaults(handler=stop_command)


def _secret(env_name, prompt):
    if env_name:
        value = os.environ.get(env_name)
        if not value:
            raise ValueError(f"Set {env_name} before setup")
        return value
    if not sys.stdin.isatty():
        raise ValueError("Use an invite or provide a credential environment variable")
    return getpass.getpass(prompt)


def _redeem(invite):
    parsed = urlsplit(invite)
    if not parsed.fragment:
        raise ValueError("Use the complete invite, including its # token")
    base = config.checked_url(
        urlunsplit(parsed._replace(fragment="", path=parsed.path.removesuffix("/join")))
    )
    path = config.config_dir() / "invite-attempt.json"
    attempt = config.read_json(path)
    import hashlib

    fingerprint = hashlib.sha256(invite.encode()).hexdigest()
    if attempt.get("invite") != fingerprint:
        attempt = {"invite": fingerprint, "request_id": uuid.uuid4().hex}
        config.write_json(path, attempt)
    try:
        response = httpx.post(
            base + "/redeem",
            json={"token": parsed.fragment, "request_id": attempt["request_id"]},
            timeout=20,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        raise ValueError(
            "Invite redemption failed; check the address or ask for a fresh invite"
        ) from None
    bundle = response.json()
    required = ("person", "switch_url", "registration_key", "identity_url", "identity_token")
    if not isinstance(bundle, dict) or any(
        not isinstance(bundle.get(k), str) or not bundle[k] for k in required
    ):
        raise ValueError("The invite server returned an incomplete connection")
    return bundle


def _settings(args):
    saved = config.read_json(config.config_dir() / "config.json")
    legacy = bool(saved.get("person"))
    if args.invite:
        values = _redeem(args.invite)
        for key in RETAINED_KEYS:
            if key in saved:
                values[key] = saved[key]
    elif saved and not (args.name or args.server or args.key_env):
        values = dict(saved)
        if args.identity_url:
            values.update(
                identity_url=args.identity_url,
                identity_token=_secret(args.identity_token_env, "Identity access token: "),
            )
    else:
        person = args.name or (input("Your name: ").strip().lower() if sys.stdin.isatty() else "")
        server = args.server or (
            input("Shared Switch address: ").strip() if sys.stdin.isatty() else ""
        )
        values = {
            "person": person,
            "switch_url": server,
            "registration_key": _secret(args.key_env, "Your registration key: "),
        }
        if args.identity_url:
            values.update(
                identity_url=args.identity_url,
                identity_token=_secret(args.identity_token_env, "Identity access token: "),
            )
        if saved.get("person") == person:
            for key in RETAINED_KEYS:
                if key in saved:
                    values[key] = saved[key]
    person = values["person"]
    if (
        not person
        or len(person) > 64
        or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in person)
        or not person[0].isalnum()
    ):
        raise ValueError("Choose a lowercase name using letters, digits, underscores or hyphens")
    values["switch_url"] = config.checked_url(values["switch_url"])
    if values.get("identity_url"):
        values["identity_url"] = config.checked_url(values["identity_url"])
    retained_gate = config.read_json(Path(saved["state_dir"]) / "gate-state.json") if saved else {}
    if retained_gate and (saved["person"], saved["switch_url"]) != (person, values["switch_url"]):
        raise ValueError(
            "This configuration already belongs to another person or server; use a separate TN_CONFIG_DIR"
        )
    agent = args.agent or values.get("agent", "manual")
    timezone = args.timezone or values.get("timezone") or "Asia/Kolkata"
    if args.calendar_delivery:
        delivery = args.calendar_delivery
    elif values.get("calendar_delivery"):
        delivery = values["calendar_delivery"]
    elif legacy:
        # Profiles created before calendar delivery was a field used the local
        # ICS file; never silently move them to agent delivery.
        delivery = "ics"
    else:
        delivery = "agent"
    values.update(
        data_dir=str(config.config_dir() / "profiles"),
        state_dir=str(config.config_dir() / "state"),
        agent=agent,
        consent=args.consent or values.get("consent", "direct"),
        timezone=config.checked_timezone(timezone),
        calendar_delivery=config.checked_calendar_delivery(delivery),
    )
    wake = _wake_settings(args, values, person, agent)
    if wake is None:
        values.pop("wake", None)
    else:
        values["wake"] = wake
    return values


def _wake_settings(args, values, person, agent):
    """The saved wake integration, or the one this setup run explicitly chose.

    ``--wake`` only configures a runner; setup never starts the loop. A runner
    may be selected explicitly, or retained from the previous profile.
    """
    if args.wake and args.wake_external:
        raise ValueError("Choose --wake (a tn wake runner) or --wake-external, not both")
    if args.background_service and args.no_start:
        raise ValueError(
            "--background-service starts the gate; it cannot be combined with --no-start"
        )
    if args.wake_external:
        if args.background_service:
            raise ValueError("--background-service needs a tn wake runner, not an external poller")
        description = args.wake_external.strip()
        if not description:
            raise ValueError("--wake-external needs a short description of the poller")
        return {"mode": "external", "external": description}
    if args.wake:
        if agent not in PRESETS:
            raise ValueError(f"--wake needs {WAKE_AGENTS}")
        if not shutil.which(agent):
            raise ValueError(f"Install {agent} before configuring its wake runner")
        every = 15.0 if args.wake_every is None else args.wake_every
        if every <= 0:
            raise ValueError("--wake-every must be a positive number of seconds")
        command = [
            sys.executable,
            "-m",
            "trustnet.tn.cli",
            "--as",
            person,
            "wake",
            "--agent",
            agent,
            "--every",
            str(every),
        ]
        if args.wake_model:
            command += ["--model", args.wake_model]
        return {
            "mode": "runner",
            "agent": agent,
            "model": args.wake_model,
            "every": every,
            "command": command,
        }
    saved = values.get("wake")
    if args.background_service and not (isinstance(saved, dict) and saved.get("mode") == "runner"):
        raise ValueError(f"--background-service needs a wake runner: pass {WAKE_AGENTS} --wake")
    return saved


async def _bootstrap(settings):
    person = settings["person"]
    directory = Path(settings["data_dir"]) / person
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    from trustnet.tn.cli import _write_empty_calendar

    if not (directory / "calendar.ics").exists():
        _write_empty_calendar(directory / "calendar.ics")
    if not (directory / "facts.yaml").exists():
        save_profile(Profile(person, {}, directory / "calendar.ics"), directory / "facts.yaml")
    if not (directory / "trust.yaml").exists():
        save_trust(TrustList(consent_default=settings["consent"]), directory / "trust.yaml")
    path = Path(settings["state_dir"]) / "gate-state.json"
    state = config.read_json(path)
    if person not in state:
        client = await SwitchClient.register(
            settings["switch_url"],
            settings["registration_key"],
            person + "-gate",
            agent_type="codex",
        )
        state[person] = {"id": client.agent_id, "api_key": client.api_key}
        config.write_json(path, state)
        await client.aclose()
    async with personal.session(person) as client:
        home = await personal.home(person, client)
        main_id = client.agent_id
        await client.update_agent_detail(state[person]["id"], addressing="anyone")
    async with _gate_session(settings) as client:
        await client.update_agent_detail(main_id, addressing="anyone")
    return home


@asynccontextmanager
async def _gate_session(settings):
    credentials = config.read_json(Path(settings["state_dir"]) / "gate-state.json")[
        settings["person"]
    ]
    client = SwitchClient(
        settings["switch_url"], credentials["id"], credentials["api_key"], timeout=5
    )

    async def drain():
        async for _ in client.events():
            pass

    stream = asyncio.create_task(drain())
    try:
        await asyncio.wait_for(client.ready.wait(), 5)
        yield client
    finally:
        stream.cancel()
        await asyncio.gather(stream, return_exceptions=True)
        await client.aclose()


def _mcp(settings):
    command = [sys.executable, "-m", "trustnet.tn.mcp", "--as", settings["person"]]
    environment = {"TN_CONFIG_DIR": str(config.config_dir())}
    entry = {"command": command[0], "args": command[1:], "env": environment}
    config.write_json(config.config_dir() / "mcp.json", {"mcpServers": {"trust-network": entry}})
    agent = settings["agent"]
    if agent == "codex":
        if not shutil.which("codex"):
            raise ValueError("Install Codex or choose --agent manual")
        result = subprocess.run(
            [
                "codex",
                "mcp",
                "add",
                "trust-network",
                "--env",
                "TN_CONFIG_DIR=" + str(config.config_dir()),
                "--",
                *command,
            ],
            capture_output=True,
        )
        if result.returncode:
            raise ValueError("Could not configure Codex; connection is saved in mcp.json")
    elif agent == "claude":
        if not shutil.which("claude"):
            raise ValueError("Install Claude Code or choose --agent manual")
        subprocess.run(
            ["claude", "mcp", "remove", "--scope", "user", "trust-network"], capture_output=True
        )
        result = subprocess.run(
            ["claude", "mcp", "add-json", "--scope", "user", "trust-network", json.dumps(entry)],
            capture_output=True,
        )
        if result.returncode:
            raise ValueError("Could not configure Claude Code; connection is saved in mcp.json")
    elif agent == "opencode":
        path = (
            Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
            / "opencode/opencode.json"
        )
        if path.with_suffix(".jsonc").exists():
            raise ValueError(
                "OpenCode has a JSONC configuration; import the generated mcp.json there, or use --agent manual"
            )
        values = config.read_json(path)
        values.setdefault("mcp", {})["trust-network"] = {
            "type": "local",
            "command": command,
            "environment": environment,
            "enabled": True,
        }
        config.write_json(path, values)


def _lock_held(settings, filename):
    """Whether some process holds this person's lock file."""
    path = Path(settings["data_dir"]) / settings["person"] / filename
    if not path.exists():
        return False
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


def _gate_running(settings):
    return _lock_held(settings, "gate.lock")


def _wake_running(settings):
    """Whether some process holds this person's ``tn wake`` lock."""
    return _lock_held(settings, "wake.lock")


def _start(settings):
    if _gate_running(settings):
        return config.read_json(config.config_dir() / "gate-process.json").get("pid")
    command = [sys.executable, "-m", "trustnet.tn.setup", "run-gate", str(config.config_dir())]
    with (config.config_dir() / "gate.log").open("ab") as log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
            env={**os.environ, "TN_CONFIG_DIR": str(config.config_dir())},
        )
    config.write_json(
        config.config_dir() / "gate-process.json", {"pid": process.pid, "command": command}
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if _gate_running(settings):
            return process.pid
        if process.poll() is not None:
            break
        time.sleep(0.05)
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=5)
    raise ValueError("The gate did not start; inspect the private gate.log and run tn doctor")


def _stop_detached(settings):
    """Stop a gate that this configuration started as a detached child."""
    if not _gate_running(settings):
        return False
    record = config.read_json(config.config_dir() / "gate-process.json")
    pid, command = record.get("pid"), record.get("command")
    if not isinstance(pid, int) or not command:
        raise ValueError(
            "This gate was started elsewhere; stop that process before changing its connection"
        )
    actual = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True
    ).stdout.strip()
    if actual != " ".join(command):
        raise ValueError("The recorded process is no longer this gate; refusing to stop it")
    import signal

    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 5
    while _gate_running(settings) and time.monotonic() < deadline:
        time.sleep(0.05)
    if _gate_running(settings):
        raise ValueError("The gate has not stopped yet; inspect gate.log")
    return True


# ---------------------------------------------------------------------------
# Opt-in user services (launchd on macOS, systemd --user on Linux)
# ---------------------------------------------------------------------------

SERVICE_PLATFORM_ENV = "TN_SERVICE_PLATFORM"
SERVICE_DIR_ENV = "TN_SERVICE_DIR"
LAUNCHD_DOMAIN = "gui"
SERVICE_PREFIX = "ai.trustnetwork"


def _service_platform(*, required=False):
    override = os.environ.get(SERVICE_PLATFORM_ENV)
    if override:
        if override not in ("launchd", "systemd"):
            raise ValueError(f"{SERVICE_PLATFORM_ENV} must be launchd or systemd")
        return override
    if sys.platform == "darwin":
        return "launchd"
    if sys.platform.startswith("linux"):
        return "systemd"
    if required:
        raise ValueError(
            "Background services need macOS launchd or Linux systemd; run tn wake in a terminal instead"
        )
    return None


def _service_dir(platform):
    override = os.environ.get(SERVICE_DIR_ENV)
    if override:
        return Path(override).expanduser().resolve()
    if platform == "launchd":
        return Path.home() / "Library/LaunchAgents"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "systemd/user"


def _unit_name(settings, role, platform):
    if platform == "launchd":
        return f"{SERVICE_PREFIX}.{settings['person']}.{role}"
    return f"trust-network-{settings['person']}-{role}.service"


def _unit_path(settings, role, platform):
    name = _unit_name(settings, role, platform)
    return _service_dir(platform) / (name + ".plist" if platform == "launchd" else name)


def _service_args(settings):
    config_dir = config.config_dir()
    wake = settings.get("wake") or {}
    return {
        "gate": [
            sys.executable,
            "-m",
            "trustnet.tn.setup",
            "run-gate",
            str(config_dir),
        ],
        "wake": list(wake.get("command") or []),
    }


def _service_env():
    return {
        "TN_CONFIG_DIR": str(config.config_dir()),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
        **{
            key: os.environ[key]
            for key in (
                "CODEX_HOME",
                "XDG_CONFIG_HOME",
                "OPENCODE_CONFIG",
                "OPENCODE_CONFIG_DIR",
                "HERMES_HOME",
            )
            if os.environ.get(key)
        },
    }


def _systemd_value(value, *, dollar=True):
    """Quote one systemd value; ``%`` is a specifier, ``$`` is special in ExecStart."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    if dollar:
        escaped = escaped.replace("$", "$$")
    return f'"{escaped}"'


def _launchd_payload(settings, role, platform):
    args = _service_args(settings)[role]
    config_dir = config.config_dir()
    log = config_dir / ("gate-service.log" if role == "gate" else "wake-service.log")
    return {
        "Label": _unit_name(settings, role, platform),
        "ProgramArguments": args,
        "EnvironmentVariables": _service_env(),
        "WorkingDirectory": str(config_dir),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 30,
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
    }


def _systemd_unit(settings, role):
    args = _service_args(settings)[role]
    environment = "".join(
        f"Environment={_systemd_value(key + '=' + value, dollar=False)}\n"
        for key, value in _service_env().items()
    )
    return (
        "[Unit]\n"
        f"Description=trust-network {role} for {settings['person']}\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"{environment}"
        "ExecStart=" + " ".join(_systemd_value(arg) for arg in args) + "\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "StandardOutput=journal\n"
        "StandardError=journal\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def _write_private(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + ".tmp")
    if isinstance(payload, bytes):
        temporary.write_bytes(payload)
    else:
        temporary.write_text(payload)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _supervisor(program, *args, check=False):
    executable = shutil.which(program)
    if not executable:
        raise ValueError(f"{program} is not available; cannot manage the background service")
    result = subprocess.run([executable, *args], capture_output=True, text=True)
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:]
        raise ValueError(
            f"{program} {' '.join(args)} failed: {detail[0][:200] if detail else result.returncode}"
        )
    return result


def _service_active(settings, role, platform):
    """Whether the supervisor currently reports this role active (None if unknown)."""
    program = "launchctl" if platform == "launchd" else "systemctl"
    if not shutil.which(program):
        return None
    if platform == "launchd":
        result = _supervisor(
            program,
            "print",
            f"{LAUNCHD_DOMAIN}/{os.getuid()}/{_unit_name(settings, role, platform)}",
        )
    else:
        result = _supervisor(program, "--user", "is-active", _unit_name(settings, role, platform))
    return result.returncode == 0


def _service_state(settings):
    platform = _service_platform()
    if platform is None:
        return {"platform": None, "supported": False, "installed": False}
    roles = {}
    for role in ("gate", "wake"):
        path = _unit_path(settings, role, platform)
        roles[role] = {
            "unit": _unit_name(settings, role, platform),
            "path": str(path),
            "installed": path.exists(),
            "active": _service_active(settings, role, platform) if path.exists() else False,
        }
    return {
        "platform": platform,
        "supported": True,
        "installed": any(role["installed"] for role in roles.values()),
        **roles,
    }


def _wait_for(predicate, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def _install_service(settings):
    """Install or refresh both user units and wait until gate and runner are live."""
    platform = _service_platform(required=True)
    wake = settings.get("wake") or {}
    if wake.get("mode") != "runner":
        raise ValueError(f"A background service needs a tn wake runner; pass {WAKE_AGENTS} --wake")
    if not shutil.which(wake.get("agent", "")):
        raise ValueError(f"Install {wake.get('agent')} before installing its wake service")
    directory = _service_dir(platform)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    paths = {role: _unit_path(settings, role, platform) for role in ("gate", "wake")}
    if platform == "launchd":
        for role in ("gate", "wake"):
            import plistlib

            _write_private(paths[role], plistlib.dumps(_launchd_payload(settings, role, platform)))
        # Replace an older loaded unit, then load the fresh plist. Older macOS
        # versions have no bootstrap; load -w is the compatible fallback.
        for role in ("gate", "wake"):
            label = _unit_name(settings, role, platform)
            _supervisor("launchctl", "bootout", f"{LAUNCHD_DOMAIN}/{os.getuid()}/{label}")
            _supervisor("launchctl", "enable", f"{LAUNCHD_DOMAIN}/{os.getuid()}/{label}")
            result = _supervisor(
                "launchctl", "bootstrap", f"{LAUNCHD_DOMAIN}/{os.getuid()}", str(paths[role])
            )
            if result.returncode:
                _supervisor("launchctl", "load", "-w", str(paths[role]), check=True)
    else:
        for role in ("gate", "wake"):
            _write_private(paths[role], _systemd_unit(settings, role))
        _supervisor("systemctl", "--user", "daemon-reload", check=True)
        for role in ("gate", "wake"):
            unit = _unit_name(settings, role, platform)
            _supervisor("systemctl", "--user", "enable", "--now", unit, check=True)
            _supervisor("systemctl", "--user", "restart", unit, check=True)

    gate_live = _wait_for(lambda: _gate_running(settings), 25)
    wake_live = _wait_for(lambda: _wake_running(settings), 25)
    if not (gate_live and wake_live):
        missing = ", ".join(
            name for name, live in (("gate", gate_live), ("wake", wake_live)) if not live
        )
        hint = (
            f"launchd logs: {config.config_dir()}/gate-service.log and wake-service.log"
            if platform == "launchd"
            else f"systemd logs: journalctl --user -u {_unit_name(settings, 'gate', platform)}"
        )
        raise ValueError(f"The {missing} service did not start; inspect {hint}")
    return _service_state(settings)


def _service_stop(settings):
    """Stop and disable installed user services; tn setup re-enables their unit files."""
    state = _service_state(settings)
    if not state["installed"]:
        return False
    platform = state["platform"]
    roles = [role for role in ("gate", "wake") if state[role]["installed"]]
    was_live = (
        _gate_running(settings)
        or _wake_running(settings)
        or any(state[role].get("active") for role in roles)
    )
    if platform == "launchd":
        for role in roles:
            label = _unit_name(settings, role, platform)
            _supervisor("launchctl", "disable", f"{LAUNCHD_DOMAIN}/{os.getuid()}/{label}")
            result = _supervisor("launchctl", "bootout", f"{LAUNCHD_DOMAIN}/{os.getuid()}/{label}")
            if result.returncode:
                _supervisor("launchctl", "unload", "-w", str(_unit_path(settings, role, platform)))
    else:
        for role in roles:
            _supervisor(
                "systemctl", "--user", "disable", "--now", _unit_name(settings, role, platform)
            )
    _wait_for(lambda: not _gate_running(settings) and not _wake_running(settings), 6)
    return was_live


def _stop(settings):
    service_stopped = _service_stop(settings)
    if _gate_running(settings):
        return _stop_detached(settings) or service_stopped
    return service_stopped


def stop_command(context, args):
    settings = config.read_json(config.config_dir() / "config.json")
    if not settings:
        return context.emit({"stopped": False}, "No managed gate is running.")
    was_wake = _wake_running(settings)
    stopped = _stop(settings)
    payload = {
        "stopped": stopped,
        "gate_running": _gate_running(settings),
        "wake_running": _wake_running(settings),
        "service": _service_state(settings),
        "stopped_wake": was_wake and not _wake_running(settings),
    }
    if stopped:
        text = "Gate stopped."
        if payload["stopped_wake"]:
            text = "Gate and wake runner stopped."
        elif payload["wake_running"]:
            text += " A wake runner started outside tn stop is still running."
    else:
        text = "No managed gate or wake service is running."
        if payload["wake_running"]:
            text += " A manually started wake runner is still running; stop it in its terminal."
    return context.emit(payload, text)


def status_command(context, args):
    settings = config.read_json(config.config_dir() / "config.json")
    if not settings:
        payload = {
            "configured": False,
            "gate_running": False,
            "wake": {"configured": False, "running": False},
            "service": {"installed": False},
        }
        return context.emit(payload, "No connection is configured. Run tn setup <invite>.")
    if any(
        not isinstance(settings.get(key), str) or not settings[key]
        for key in ("person", "data_dir", "state_dir")
    ):
        context.emit(
            {"configured": True, "valid": False},
            "The saved configuration is incomplete; run tn setup or tn doctor.",
        )
        return 1
    wake = settings.get("wake") or {}
    service = _service_state(settings)
    payload = {
        "configured": True,
        "person": settings.get("person"),
        "gate_running": _gate_running(settings),
        "wake": {
            "mode": wake.get("mode"),
            "configured": wake.get("mode") in config.WAKE_MODES,
            "running": _wake_running(settings),
            "external": wake.get("external"),
            "command": wake.get("command") if wake.get("mode") == "runner" else None,
        },
        "service": service,
        "calendar": {
            "delivery": settings.get("calendar_delivery", "ics"),
            "timezone": settings.get("timezone", "Asia/Kolkata"),
        },
    }
    lines = [
        f"Person: {payload['person']}",
        f"Gate: {'running' if payload['gate_running'] else 'stopped'}",
    ]
    if wake.get("mode") == "runner":
        lines.append(f"Wake runner: {'running' if payload['wake']['running'] else 'stopped'}")
    elif wake.get("mode") == "external":
        lines.append(f"Wake runner: external ({wake.get('external')}), not running locally")
    else:
        lines.append("Wake runner: not configured")
    if service["installed"]:
        lines.append(
            f"Service: {service['platform']} units installed"
            + (" and active" if service["gate"].get("active") else "")
        )
    else:
        lines.append("Service: no background units installed")
    return context.emit(payload, "\n".join(lines))


def setup_command(context, args):
    directory = config.config_dir()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "setup.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another setup is running; wait for it to finish") from None
        return _setup(context, args)


def _wake_command(settings):
    wake = settings.get("wake") or {}
    if wake.get("mode") == "runner" and wake.get("command"):
        import shlex

        return shlex.join(wake["command"])
    return None


def _next_steps(settings, service=None):
    wake = settings.get("wake") or {}
    steps = ["Restart your agent so it loads the trust-network MCP connection."]
    if wake.get("mode") == "runner":
        if service and service.get("wake", {}).get("active"):
            steps.append("Background wake service running; check it with tn status.")
        else:
            steps.append(f"Start your agent wake loop: {_wake_command(settings)}")
    elif wake.get("mode") == "external":
        steps.append(
            f"Confirm your external poller runs: {wake.get('external')} "
            "(tn doctor cannot verify it locally)."
        )
    else:
        steps.append(
            f"Pick an automation path: tn setup {WAKE_AGENTS} --wake, or declare an "
            'external poller with --wake-external "description".'
        )
    steps.append("Run: tn doctor   (self-check; connection and automation are reported separately)")
    steps.append("Add friends with tn trust <name> <level>.")
    return steps


def _setup(context, args):
    previous = config.read_json(config.config_dir() / "config.json")
    previous_service = _service_state(previous) if previous.get("person") else {"installed": False}
    settings = _settings(args)
    if previous and any(
        previous.get(k) != settings.get(k)
        for k in ("switch_url", "identity_url", "identity_token", "timezone", "calendar_delivery")
    ):
        _stop(previous)
    if previous_service.get("installed") and settings.get("wake", {}).get("mode") == "external":
        _stop(previous)
    config.write_json(config.config_dir() / "config.json", settings)
    config.apply(settings, override=True)
    home = asyncio.run(_bootstrap(settings))
    if args.consent:
        from trustnet.gate.fact_changes import editing

        with editing(settings["person"]):
            trust = load_trust(settings["person"])
            trust.consent_default = args.consent
            save_trust(trust, Path(settings["data_dir"]) / settings["person"] / "trust.yaml")
    _mcp(settings)
    service, pid = None, None
    if args.background_service or (
        previous_service.get("installed")
        and settings.get("wake", {}).get("mode") == "runner"
        and not args.no_start
    ):
        # A service owns both processes; stop a detached gate before it is
        # re-created, so two gates never hold one profile.
        _stop(settings)
        service = _install_service(settings)
    elif not args.no_start:
        pid = _start(settings)
    report = None
    if not args.no_start:
        report = asyncio.run(_diagnose(settings))
        if not report["connection_ok"]:
            failures = "; ".join(
                c["fix"] for c in report["checks"] if not c["ok"] and c["name"] in CONNECTION_CHECKS
            )
            raise ValueError("Connection saved, but setup needs attention. " + failures)
    wake = settings.get("wake")
    service = service or (_service_state(settings) if previous_service.get("installed") else None)
    result = {
        "person": settings["person"],
        "home": home,
        "gate_pid": pid,
        "mcp_config": str(config.config_dir() / "mcp.json"),
        "calendar": {
            "delivery": settings["calendar_delivery"],
            "timezone": settings["timezone"],
        },
        "wake": wake,
        "wake_command": _wake_command(settings),
        "wake_running": _wake_running(settings),
        "service": service,
        "next_steps": _next_steps(settings, service),
        "self_check": "tn doctor",
        "readiness": {
            "connection": bool(report and report["connection_ok"]),
            "automation": bool(report and report["automation_ready"]),
        },
    }
    if args.no_start:
        text = f"Configured {settings['person']}, but nothing was started. Run tn setup, then tn doctor."
    elif report["connection_ok"] and report["automation_ready"]:
        text = f"Ready for {settings['person']}. Connection and automation are ready."
    else:
        text = f"Connected for {settings['person']}. Automation is NOT ready yet."
    text += "\nNext steps:\n" + "\n".join(
        f"  {number}. {step}" for number, step in enumerate(result["next_steps"], 1)
    )
    return context.emit(result, text)


CONNECTION_CHECKS = frozenset({"profile", "server", "home", "identities", "gate", "mcp"})


async def _diagnose(settings):
    checks = []

    def add(name, ok, fix="", detail=""):
        checks.append({"name": name, "ok": bool(ok), "fix": "" if ok else fix, "detail": detail})

    try:
        load_profile(settings["person"])
        load_trust(settings["person"])
        add("profile", True, detail=f"profile files under {settings['data_dir']}")
    except (ValueError, OSError):
        add("profile", False, "Run tn setup to create missing profile files")
    gate = config.read_json(Path(settings["state_dir"]) / "gate-state.json").get(settings["person"])
    owner_id = None
    if gate:
        try:
            async with _gate_session(settings) as client:
                detail = await client.get_agent_detail(client.agent_id)
            owner_id = detail.get("owner_id")
            add(
                "server",
                bool(detail.get("owner_id")),
                "Check the Switch address and registration",
                "gate identity registered with Switch",
            )
        except Exception:
            add("server", False, "Start Switch and check its address and your registration")
    else:
        add("server", False, "Run tn setup to register your gate")
    try:
        async with personal.session(settings["person"]) as client:
            room = await personal.home(settings["person"], client)
            detail = await client.get_room_detail(room)
            await client.read_context(room_id=room, limit=1)
            add(
                "home",
                detail.get("bridge_id") is None
                and all(
                    key not in detail or detail[key] == expected
                    for key, expected in (
                        ("internal_only", True),
                        ("read_visibility", "private"),
                        ("write_visibility", "private"),
                    )
                ),
                "Run tn setup to repair your private home",
                "home ownership and reachability checked; visibility metadata "
                + (
                    "reported by server"
                    if "read_visibility" in detail
                    else "not exposed by this Switch version"
                ),
            )
    except Exception:
        add("home", False, "Run tn setup and check your private-home membership")
    source = IdentitySource(config.config_dir() / "identities.json", settings.get("identity_url"))
    await asyncio.to_thread(source.refresh)
    identity = source.get(gate["id"]) if gate else None
    owner = source.get(owner_id) if owner_id else None
    add(
        "identities",
        identity is not None
        and identity.id == settings["person"] + "-gate"
        and identity.person == settings["person"]
        and owner is not None
        and owner.id == settings["person"],
        "Ask the organizer to check the authenticated identity service",
        "gate and owner identities are authenticated",
    )
    service = _service_state(settings)
    gate_fix = (
        "Start the background service with tn setup --background-service --agent <agent> --wake"
        if service.get("installed")
        else "Run tn setup to start your gate"
    )
    add(
        "gate",
        _gate_running(settings),
        gate_fix,
        f"gate process holds the profile lock ({settings['person']}-gate)",
    )
    mcp = (
        config.read_json(config.config_dir() / "mcp.json")
        .get("mcpServers", {})
        .get("trust-network", {})
    )
    expected = ["-m", "trustnet.tn.mcp", "--as", settings["person"]]
    valid = (
        mcp.get("command") == sys.executable
        and mcp.get("args") == expected
        and os.access(sys.executable, os.X_OK)
    )
    if valid:

        async def probe():
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            params = StdioServerParameters(
                command=sys.executable,
                args=expected,
                env={**os.environ, "TN_CONFIG_DIR": str(config.config_dir())},
            )
            with tempfile.TemporaryFile(mode="w+") as log:
                async with stdio_client(params, errlog=log) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        return {"inbox", "dm", "answer"} <= {t.name for t in tools.tools}

        try:
            valid = await asyncio.wait_for(probe(), 10)
        except Exception:
            valid = False
    add(
        "mcp",
        valid,
        "Run tn setup --agent <your-agent> to repair the MCP connection",
        "MCP server answers; this proves tool connectivity, not that anything wakes your agent",
    )
    wake = settings.get("wake") or {}
    mode = wake.get("mode")
    if mode == "runner":
        agent = wake.get("agent")
        installed = bool(agent) and shutil.which(agent) is not None
        add(
            "wake-config",
            installed,
            f"Install {agent or 'the configured agent'} or rerun tn setup {WAKE_AGENTS} --wake",
            f"tn wake runner: {_wake_command(settings)}",
        )
        add(
            "wake-runner",
            _wake_running(settings),
            "Start the runner: "
            + _wake_command(settings)
            + " (or install services with tn setup --background-service --agent <agent> --wake)",
            "the runner holds the per-person wake lock",
        )
    elif mode == "external":
        add("wake-config", True, detail=f"external poller: {wake.get('external')}")
        add(
            "wake-external",
            True,
            detail="declared external integration; tn doctor cannot verify it locally",
        )
    else:
        add(
            "wake-config",
            False,
            f"No wake runner configured. Run tn setup {WAKE_AGENTS} --wake, or declare an "
            'external poller with --wake-external "description"',
        )
        add(
            "wake-runner",
            False,
            "Nothing wakes this agent on news yet; MCP responding does not start an agent turn",
        )
    notes = [
        f"Calendar delivery: {settings.get('calendar_delivery', 'ics')}; "
        f"timezone {settings.get('timezone', 'Asia/Kolkata')}.",
        "Restart your agent after setup so it loads the trust-network MCP server.",
    ]
    if mode != "runner":
        notes.append(
            "An external poller is a valid manual integration (for example the Hermes cron "
            "script scripts/hermes/tn-inbox-watch.sh). Declare it with --wake-external so "
            "doctor does not keep reporting a missing runner."
        )
    if service.get("installed"):
        where = (
            f"{config.config_dir()}/gate-service.log and wake-service.log"
            if service["platform"] == "launchd"
            else "journalctl --user -u trust-network-" + str(settings["person"]) + "-gate"
        )
        notes.append(f"Background service logs: {where}.")
    connection_ok = all(c["ok"] for c in checks if c["name"] in CONNECTION_CHECKS)
    wake_checks = [c["ok"] for c in checks if c["name"].startswith("wake")]
    return {
        "ok": all(c["ok"] for c in checks),
        "connection_ok": connection_ok,
        "automation_ready": bool(wake_checks) and all(wake_checks),
        "wake_verified": mode == "runner" and _wake_running(settings),
        "checks": checks,
        "notes": notes,
        "service": service,
    }


def doctor_command(context, args):
    settings = config.read_json(config.config_dir() / "config.json")
    if not settings:
        report = {
            "ok": False,
            "connection_ok": False,
            "automation_ready": False,
            "wake_verified": False,
            "checks": [{"name": "configuration", "ok": False, "fix": "Run tn setup <invite>"}],
            "notes": [],
            "service": {"installed": False},
        }
    else:
        config.apply(settings, override=True)
        report = asyncio.run(_diagnose(settings))
    lines = [
        ("OK " if check["ok"] else "FIX ")
        + check["name"]
        + (". " + (check["fix"] if check["fix"] else check.get("detail", "")))
        for check in report["checks"]
    ]
    lines.append("")
    lines.append("Connection: " + ("ready" if report["connection_ok"] else "not ready"))
    if report["automation_ready"] and not report["wake_verified"]:
        lines.append("Automation: declared external integration (not verified locally)")
    else:
        lines.append("Automation: " + ("ready" if report["automation_ready"] else "not ready"))
    lines.extend("Note: " + note for note in report["notes"])
    context.emit(report, "\n".join(lines))
    return 0 if report["ok"] else 1


def run_gate():
    from argparse import Namespace

    from trustnet.gate.__main__ import run

    settings = config.read_json(config.config_dir() / "config.json")
    config.apply(settings, override=True)
    args = Namespace(
        person=settings["person"],
        state=Path(settings["state_dir"]) / "gate-state.json",
        key_env=settings["person"].upper() + "_GATE_KEY",
        identity_map=config.config_dir() / "identities.json",
        identity_url=settings.get("identity_url"),
    )
    asyncio.run(run(args))


if __name__ == "__main__":
    run_gate()
