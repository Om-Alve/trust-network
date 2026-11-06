"""Reset disposable demo state. Stop gates and Hermes inbox polling first."""

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path

from scripts.demo_up import PEOPLE, configure, options
from trustnet.switch_client import SwitchClient, SwitchError

STATE_FILES = (
    "ledger.jsonl",
    "claims.json",
    "gift-sessions.json",
    "inbox-cursor.json",
    "watch-state.json",
    "coordination.json",
    "ask-around.json",
    "peers.json",
)


def clear_local(root, dry_run=False):
    for person in PEOPLE:
        directory = root / person
        for name in (*STATE_FILES, "share-cards", "room-watches"):
            target = directory / name
            if target.exists():
                print("Clear", target)
                if not dry_run:
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
        if directory.exists():
            print("Restore fixture calendar", directory / "calendar.ics")
            if not dry_run:
                shutil.copyfile(
                    Path("examples") / person / "calendar.ics", directory / "calendar.ics"
                )


async def archive(dry_run):
    state = json.loads(Path("data/day0-state.json").read_text())
    for person in PEOPLE:
        if person not in state:
            continue
        client = SwitchClient(
            os.environ["SWITCH_URL"], state[person]["id"], state[person]["api_key"]
        )

        async def drain():
            async for _ in client.events():
                pass

        task = asyncio.create_task(drain())
        try:
            await asyncio.wait_for(client.ready.wait(), 20)
            detail = await client.get_agent_detail(client.agent_id)
            for room in detail["rooms"]:
                if room["room_name"].lstrip("#").startswith(
                    ("dm-", "gift-", "ask-", "conn-")
                ) and not room.get("archived"):
                    print("Archive", room["room_name"])
                    if not dry_run:
                        try:
                            await client.archive_room(room["room_id"])
                        except SwitchError as exc:
                            # One refused room must not leave the rest open.
                            print("  not archived:", exc)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await client.aclose()


def main():
    parser = options(__doc__)
    parser.add_argument("--vm-host", default="om@hermes.<tailnet>.ts.net")
    args = parser.parse_args()
    root = configure(args)
    asyncio.run(archive(args.dry_run))
    clear_local(root, args.dry_run)
    if not args.one_machine:
        if args.vm_host.startswith("-"):
            raise SystemExit("Invalid SSH host")
        print("Reset VM data/profiles/rahul; service must be stopped first")
        if not args.dry_run:
            code = """from pathlib import Path
import shutil
root = Path.home() / 'trust-network'
p = root / 'data/profiles/rahul'
for name in %r:
    target = p / name
    if target.is_dir(): shutil.rmtree(target)
    else: target.unlink(missing_ok=True)
shutil.copyfile(root / 'examples/rahul/calendar.ics', p / 'calendar.ics')
""" % ((*STATE_FILES, "share-cards"),)
            subprocess.run(
                ["ssh", "-o", "BatchMode=yes", args.vm_host, "python3 -"],
                input=code,
                text=True,
                check=True,
            )


if __name__ == "__main__":
    main()
