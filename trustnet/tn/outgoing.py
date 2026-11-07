"""Exact-text owner review of outgoing agent messages, with no meaning classifier."""

import fcntl
import hashlib
import json
import os

from trustnet.gate import storage


def mode(person):
    from trustnet.tn.configuration import config_dir, read_json

    settings = read_json(config_dir() / "config.json")
    value = os.environ.get("TN_OUTGOING")
    if value is None:
        value = settings.get("outgoing", "agent") if settings.get("person") == person else "agent"
    if value not in {"agent", "review"}:
        raise ValueError("Outgoing mode must be agent or review")
    return value


def draft(person, room, text):
    if not isinstance(text, str) or not text.strip() or len(text) > 16384:
        raise ValueError("An outgoing message must contain 1 to 16384 characters")
    ref = "O" + hashlib.sha256(json.dumps([room, text]).encode()).hexdigest()[:24]
    with storage.database(person) as connection:
        _table(connection)
        row = connection.execute("SELECT value FROM outgoing WHERE ref=?", (ref,)).fetchone()
        if row:
            return json.loads(row[0])
        item = {"ref": ref, "room": room, "text": text, "status": "awaiting-owner"}
        connection.execute("INSERT INTO outgoing VALUES (?, ?)", (ref, json.dumps(item)))
    return item


def _table(connection):
    connection.execute(
        "CREATE TABLE IF NOT EXISTS outgoing (ref TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )


def pending(person):
    with storage.database(person) as connection:
        _table(connection)
        rows = connection.execute("SELECT value FROM outgoing ORDER BY rowid").fetchall()
    return [item for row in rows if (item := json.loads(row[0]))["status"] == "awaiting-owner"]


def _read(connection, ref):
    _table(connection)
    row = connection.execute("SELECT value FROM outgoing WHERE ref=?", (ref,)).fetchone()
    if not row:
        raise ValueError("Unknown outgoing reference")
    return json.loads(row[0])


def decline(person, ref):
    with storage.database(person) as connection:
        item = _read(connection, ref)
        if item["status"] != "awaiting-owner":
            raise ValueError("Outgoing message is no longer pending")
        item["status"] = "declined"
        connection.execute("UPDATE outgoing SET value=? WHERE ref=?", (json.dumps(item), ref))
    return item


async def release(person, ref):
    from trustnet.gate.facts import resolve_data_dir
    from trustnet.tn import personal

    with (resolve_data_dir(person) / "outgoing.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another owner approval is being delivered; retry shortly") from None
        with storage.database(person) as connection:
            item = _read(connection, ref)
        if item["status"] == "sent":
            return item
        if item["status"] != "awaiting-owner":
            raise ValueError("Outgoing message is no longer pending")
        context = await personal.dm_operate(person, item["room"])
        messages = [
            m for t in context.get("threads", []) for m in (t["root"], *t.get("replies", []))
        ]
        delivered = any(
            m.get("sender_name") == person + "-hermes" and m.get("body") == item["text"]
            for m in messages
        )
        if not delivered:
            await personal.dm_operate(person, item["room"], item["text"])
        item["status"] = "sent"
        with storage.database(person) as connection:
            connection.execute("UPDATE outgoing SET value=? WHERE ref=?", (json.dumps(item), ref))
    return item
