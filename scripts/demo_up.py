"""Bootstrap retained demo identities and profiles; print gate launch commands."""

import argparse
import asyncio
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

from scripts.switch_users import CONSOLE_ENV, REPO, login, read_env, vm_host
from trustnet.gate.identity import export_local
from trustnet.switch_client import SwitchClient
from trustnet.tn.personal import session

PEOPLE = ("om", "rahul", "priya")


def options(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--one-machine", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(
            os.environ.get("TN_DATA_DIR")
            or read_env(REPO / ".env").get("TN_DATA_DIR")
            or "data/profiles"
        ),
    )
    parser.add_argument("--url")
    return parser


def configure(args):
    os.chdir(REPO)
    env = {**read_env(REPO / ".env"), **os.environ}
    env["SWITCH_URL"] = args.url or (
        "http://127.0.0.1:53330"
        if args.one_machine
        else env.get("SWITCH_URL", "http://127.0.0.1:53330")
    )
    env["TN_DATA_DIR"] = str(args.data_dir.expanduser().resolve())
    # Retained Hermes identities live in data/main-agents/ for every layout; without
    # this, personal.session() would look under TN_DATA_DIR and re-register (409).
    env.setdefault("TN_STATE_DIR", str(REPO / "data"))
    if args.one_machine:
        env.pop("TN_IDENTITY_URL", None)
        os.environ.pop("TN_IDENTITY_URL", None)
    os.environ.update(env)
    root = Path(env["TN_DATA_DIR"])
    if root == REPO / "examples" or (REPO / "examples") in root.parents or root == REPO:
        raise SystemExit("TN_DATA_DIR must be a disposable directory outside examples")
    return root


async def bootstrap(args, root):
    if not all(os.environ.get(p.upper() + "_GATE_KEY") for p in PEOPLE):
        subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "scripts.switch_users",
                "--console-env",
                "--url",
                os.environ["SWITCH_URL"],
            ],
            check=True,
            capture_output=True,
        )
        os.environ.update(read_env(REPO / ".env"))
        os.environ["SWITCH_URL"] = args.url or (
            "http://127.0.0.1:53330" if args.one_machine else os.environ["SWITCH_URL"]
        )
    state_path = REPO / "data/day0-state.json"
    state_path.parent.mkdir(exist_ok=True)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    for person in PEOPLE:
        source = REPO / "examples" / person
        for fixture in source.rglob("*"):
            target = root / person / fixture.relative_to(source)
            if fixture.is_file() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(fixture, target)
        if person not in state:
            client = await SwitchClient.register(
                os.environ["SWITCH_URL"],
                os.environ[person.upper() + "_GATE_KEY"],
                person + "-gate",
                agent_type="codex",
            )
            state[person] = {"id": client.agent_id, "api_key": client.api_key}
            state_path.touch(mode=0o600)
            state_path.write_text(json.dumps(state))
            state_path.chmod(0o600)
            await client.aclose()
    for person in ("om", "rahul"):
        async with session(person):
            pass
    console = read_env(CONSOLE_ENV)
    for person in PEOPLE:
        email = console["GATEWAY_ADMIN_EMAIL"] if person == "om" else person + "@switch.local"
        password = (
            console["GATEWAY_ADMIN_PASSWORD"]
            if person == "om"
            else os.environ[person.upper() + "_SWITCH_PASSWORD"]
        )
        gateway = login(os.environ["SWITCH_URL"], email, password)
        try:
            response = gateway.put(
                "/agents/" + state[person]["id"] + "/addressing-policy", json={"policy": None}
            )
            response.raise_for_status()
        finally:
            gateway.close()
    export_local(REPO / "data/gate-identities.json")


def main():
    args = options(__doc__).parse_args()
    root = configure(args)
    if args.dry_run:
        print(
            "Would reuse users/keys and retained gate/Hermes credentials; register missing identities, copy missing fixtures, set addressing and export identities."
        )
    else:
        asyncio.run(bootstrap(args, root))
    print(
        "Stop existing gates before launching these commands. Stop the VM rahul-gate service before running Rahul locally."
    )
    prefix = "env " + shlex.join(
        ["SWITCH_URL=" + os.environ["SWITCH_URL"], "TN_DATA_DIR=" + str(root)]
    )
    if args.one_machine:
        prefix = "env -u TN_IDENTITY_URL " + prefix[4:]
    for person in PEOPLE if args.one_machine else ("om", "priya"):
        print(
            prefix
            + " uv run python -m trustnet.gate --person "
            + person
            + " --key-env "
            + person.upper()
            + "_GATE_KEY"
        )
    if not args.one_machine:
        print(
            "Laptop publisher: load .env securely, then uv run python -m scripts.identity_serve (127.0.0.1:8792; existing tailnet 8666 mapping)."
        )
        print(f"VM: ssh {vm_host()} systemctl --user start rahul-gate.service")
    print(
        "Local Hermes stand-ins: use tn --as om and tn --as rahul with the same SWITCH_URL, TN_DATA_DIR and TN_STATE_DIR="
        + os.environ["TN_STATE_DIR"]
        + ". No controller required."
    )
    print(
        "Manual phase 18: configure two Hermes profiles with tn mcp and their separate Discord bots, intents, invitations and inbox cron."
    )


if __name__ == "__main__":
    main()
