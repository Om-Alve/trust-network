"""Connect a person to a shared server and verify the configured path."""

import asyncio
import fcntl
import getpass
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
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
    setup.add_argument("--agent", choices=("manual", "codex", "claude", "opencode"))
    setup.add_argument("--no-start", action="store_true")
    setup.set_defaults(handler=setup_command)
    doctor = commands.add_parser(
        "doctor", parents=[common], help="check this person's complete connection"
    )
    doctor.set_defaults(handler=doctor_command)


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
    if args.invite:
        values = _redeem(args.invite)
    elif saved and not (args.name or args.server or args.key_env):
        values = saved
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
    if saved and (saved["person"], saved["switch_url"]) != (person, values["switch_url"]):
        raise ValueError(
            "This configuration already belongs to another person or server; use a separate TN_CONFIG_DIR"
        )
    values.update(
        data_dir=str(config.config_dir() / "profiles"),
        state_dir=str(config.config_dir() / "state"),
        agent=args.agent or values.get("agent", "manual"),
    )
    return values


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
        save_trust(TrustList(), directory / "trust.yaml")
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
        return await personal.home(person, client)


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
        values = config.read_json(path)
        values.setdefault("mcp", {})["trust-network"] = {
            "type": "local",
            "command": command,
            "environment": environment,
            "enabled": True,
        }
        config.write_json(path, values)


def _gate_running(settings):
    path = Path(settings["data_dir"]) / settings["person"] / "gate.lock"
    if not path.exists():
        return False
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


def _start(settings):
    if _gate_running(settings):
        return config.read_json(config.config_dir() / "gate-process.json").get("pid")
    with (config.config_dir() / "gate.log").open("ab") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "trustnet.tn.setup", "run-gate"],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
            env={**os.environ, "TN_CONFIG_DIR": str(config.config_dir())},
        )
    config.write_json(config.config_dir() / "gate-process.json", {"pid": process.pid})
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


def setup_command(context, args):
    directory = config.config_dir()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "setup.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another setup is running; wait for it to finish") from None
        return _setup(context, args)


def _setup(context, args):
    settings = _settings(args)
    config.write_json(config.config_dir() / "config.json", settings)
    config.apply(settings, override=True)
    home = asyncio.run(_bootstrap(settings))
    _mcp(settings)
    pid = None if args.no_start else _start(settings)
    result = {
        "person": settings["person"],
        "home": home,
        "gate_pid": pid,
        "mcp_config": str(config.config_dir() / "mcp.json"),
    }
    return context.emit(
        result,
        f"Ready for {settings['person']}. Run tn doctor. Add each friend with tn trust <name> <level>.",
    )


async def _diagnose(settings):
    checks = []

    def add(name, ok, fix=""):
        checks.append({"name": name, "ok": bool(ok), "fix": "" if ok else fix})

    try:
        load_profile(settings["person"])
        load_trust(settings["person"])
        add("profile", True)
    except (ValueError, OSError):
        add("profile", False, "Run tn setup to create missing profile files")
    gate = config.read_json(Path(settings["state_dir"]) / "gate-state.json").get(settings["person"])
    if gate:
        client = SwitchClient(settings["switch_url"], gate["id"], gate["api_key"], timeout=5)
        try:
            detail = await client.get_agent_detail(client.agent_id)
            add("server", bool(detail.get("owner_id")), "Check the Switch address and registration")
        except Exception:
            add("server", False, "Start Switch and check its address and your registration")
        finally:
            await client.aclose()
    else:
        add("server", False, "Run tn setup to register your gate")
    try:
        async with personal.session(settings["person"]) as client:
            room = await personal.home(settings["person"], client)
            detail = await client.get_room_detail(room)
            await client.read_context(room_id=room, limit=1)
            add(
                "home",
                detail.get("internal_only") and detail.get("read_visibility") == "private",
                "Run tn setup to repair your private home",
            )
    except Exception:
        add("home", False, "Run tn setup and check your private-home membership")
    source = IdentitySource(config.config_dir() / "identities.json", settings.get("identity_url"))
    await asyncio.to_thread(source.refresh)
    identity = source.get(gate["id"]) if gate else None
    add(
        "identities",
        identity is not None and identity.person == settings["person"],
        "Ask the organizer to check the authenticated identity service",
    )
    add("gate", _gate_running(settings), "Run tn setup to start your gate")
    mcp = (
        config.read_json(config.config_dir() / "mcp.json")
        .get("mcpServers", {})
        .get("trust-network", {})
    )
    add(
        "mcp",
        bool(mcp.get("command") and mcp.get("args")),
        "Run tn setup --agent <your-agent> to configure MCP",
    )
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def doctor_command(context, args):
    settings = config.read_json(config.config_dir() / "config.json")
    if not settings:
        report = {
            "ok": False,
            "checks": [{"name": "configuration", "ok": False, "fix": "Run tn setup <invite>"}],
        }
    else:
        config.apply(settings, override=True)
        report = asyncio.run(_diagnose(settings))
    context.emit(
        report,
        "\n".join(
            ("OK " if check["ok"] else "FIX ")
            + check["name"]
            + (". " + check["fix"] if check["fix"] else "")
            for check in report["checks"]
        ),
    )
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
