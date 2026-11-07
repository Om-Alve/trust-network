"""Export non-secret identity aliases from the local server DB (run with core's Python).

Only explicit demo account emails are mapped to person names, plus any trusted
email -> person entries in the JSON file named by ``TN_IDENTITY_PEOPLE``.
Unknown people remain unknown. Output is a trusted local input, never
message-derived.

The database connection is configurable without the macOS Switch Console env
file: set ``TN_IDENTITY_DB_URL``, or ``TN_IDENTITY_DB_HOST``, ``_PORT``,
``_USER``, ``_PASSWORD`` and ``_NAME`` (or point ``TN_IDENTITY_CONSOLE_ENV`` at
an env file). ``TN_SWITCH_TENANT`` selects the tenant.
"""

import asyncio
import json
import os
from pathlib import Path

DEMO_PEOPLE = {
    "admin@switch.local": "om",
    "rahul@switch.local": "rahul",
    "priya@switch.local": "priya",
}
CONSOLE_ENV = (
    Path.home()
    / "Library/Application Support/switchdash/local-switch-server/native/run/switch-core.env"
)


def people_map(environ=None):
    """Demo fallback plus trusted configured email -> person entries."""
    env = os.environ if environ is None else environ
    people = dict(DEMO_PEOPLE)
    configured_path = env.get("TN_IDENTITY_PEOPLE")
    if configured_path:
        configured = json.loads(Path(configured_path).read_text())
        if not isinstance(configured, dict):
            raise ValueError("TN_IDENTITY_PEOPLE must hold an object of email -> person")
        for email, person in configured.items():
            if not isinstance(email, str) or not isinstance(person, str) or not person.strip():
                raise ValueError("TN_IDENTITY_PEOPLE entries must be email -> person strings")
            people[email.strip().lower()] = person.strip().lower()
    return people


def database_settings(environ=None):
    env = os.environ if environ is None else environ
    dsn = env.get("TN_IDENTITY_DB_URL")
    if dsn:
        return {"dsn": dsn}

    console_env = env.get("TN_IDENTITY_CONSOLE_ENV")
    env_path = Path(console_env) if console_env else CONSOLE_ENV
    file_values = {}
    if env_path.exists():
        file_values = dict(
            line.split("=", 1)
            for line in env_path.read_text().splitlines()
            if "=" in line and not line.startswith("#")
        )

    def pick(name):
        return (
            env.get("TN_IDENTITY_DB_" + name.upper()) or file_values.get("DB_" + name.upper()) or ""
        )

    settings = {name: pick(name) for name in ("host", "port", "user", "password", "name")}
    if not settings["host"] or not settings["name"]:
        raise RuntimeError(
            "set TN_IDENTITY_DB_URL, or TN_IDENTITY_DB_HOST/NAME (and user/password), "
            "or TN_IDENTITY_CONSOLE_ENV"
        )
    return settings


async def export(environ=None):
    import asyncpg

    env = os.environ if environ is None else environ
    settings = database_settings(env)
    if "dsn" in settings:
        db = await asyncpg.connect(settings["dsn"])
    else:
        db = await asyncpg.connect(
            host=settings["host"],
            port=int(settings["port"] or 5432),
            user=settings["user"],
            password=settings["password"],
            database=settings["name"],
        )

    result = {}
    try:
        async with db.transaction(readonly=True):
            await db.execute(
                "SELECT set_config('app.tenant_id', $1, true)",
                env.get("TN_SWITCH_TENANT", "00000000-0000-0000-0000-000000000000"),
            )
            users = await db.fetch("SELECT id,email FROM users")
            configured_people = people_map(env)
            people = {r["id"]: configured_people.get((r["email"] or "").lower()) for r in users}
            for uid, person in people.items():
                if person:
                    result[uid] = {"kind": "user", "id": person}
            rows = await db.fetch(
                "SELECT c.id,c.matrix_user_id,c.user_id,a.id AS agent_id,a.name AS agent_name,a.owner_id FROM clients c LEFT JOIN agents a ON a.client_id=c.id"
            )
            for row in rows:
                if row["agent_id"]:
                    owner = people.get(row["owner_id"])
                    identity = {"kind": "agent", "id": row["agent_name"], "owner_id": owner}
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
        path = Path(env.get("TN_IDENTITY_MAP", "data/gate-identities.json"))
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(result))
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)
    finally:
        await db.close()


async def main():
    await export()


if __name__ == "__main__":
    asyncio.run(main())
