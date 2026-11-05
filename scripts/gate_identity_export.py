"""Export non-secret identity aliases from the local server DB (run with core's Python).

Only explicit demo account emails are mapped to person names. Unknown people
remain unknown. Output is a trusted local input, never message-derived.
"""

import asyncio
import json
import os
from pathlib import Path

import asyncpg


async def main():
    env_path = (
        Path.home()
        / "Library/Application Support/switchdash/local-switch-server/native/run/switch-core.env"
    )
    env = dict(
        line.split("=", 1)
        for line in env_path.read_text().splitlines()
        if "=" in line and not line.startswith("#")
    )
    db = await asyncpg.connect(
        host=env["DB_HOST"],
        port=int(env["DB_PORT"]),
        user=env["DB_OWNER_USER"],
        password=env["DB_OWNER_PASSWORD"],
        database=env["DB_NAME"],
    )
    result = {}
    try:
        async with db.transaction(readonly=True):
            users = await db.fetch("SELECT id,email FROM users")
            people = {
                r["id"]: {
                    "admin@switch.local": "om",
                    "rahul@switch.local": "rahul",
                    "priya@switch.local": "priya",
                }.get(r["email"])
                for r in users
            }
            for uid, person in people.items():
                if person:
                    result[uid] = {"kind": "user", "id": person}
            rows = await db.fetch(
                "SELECT c.id,c.matrix_user_id,c.user_id,a.id AS agent_id,a.owner_id FROM clients c LEFT JOIN agents a ON a.client_id=c.id"
            )
            for row in rows:
                if row["agent_id"]:
                    owner = people.get(row["owner_id"])
                    identity = {"kind": "agent", "id": row["agent_id"], "owner_id": owner}
                elif people.get(row["user_id"]):
                    identity = {"kind": "user", "id": people[row["user_id"]]}
                else:
                    identity = {"kind": "agent", "id": row["id"]}
                for alias in (row["id"], row["matrix_user_id"], row["agent_id"]):
                    if alias:
                        result[alias] = identity
            memberships = await db.fetch(
                "SELECT cr.room_id,cr.client_id FROM client_rooms cr JOIN clients c ON c.id=cr.client_id WHERE c.type != 'admin'"
            )
            for row in memberships:
                identity = result.get(row["client_id"])
                if identity:
                    result["room:" + row["room_id"] + ":" + row["client_id"]] = identity
        path = Path(os.environ.get("TN_IDENTITY_MAP", "data/gate-identities.json"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result))
        path.chmod(0o600)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
