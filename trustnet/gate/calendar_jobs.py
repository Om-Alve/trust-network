"""Durable calendar operations executed by the owner's existing agent tools."""

import hashlib
import json
import os
import time

from trustnet.gate.storage import database


def delivery_mode(person):
    from trustnet.tn.configuration import config_dir, read_json

    settings = read_json(config_dir() / "config.json")
    mode = os.environ.get("TN_CALENDAR_DELIVERY")
    if mode is None:
        mode = (
            settings.get("calendar_delivery", "ics") if settings.get("person") == person else "ics"
        )
    if mode not in {"agent", "ics"}:
        raise ValueError("calendar delivery must be agent or ics")
    return mode


def _table(connection):
    connection.execute(
        "CREATE TABLE IF NOT EXISTS calendar_tasks "
        "(uid TEXT PRIMARY KEY, token TEXT NOT NULL, value TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS calendar_operations (token TEXT PRIMARY KEY, uid TEXT NOT NULL)"
    )


def queue(person, ref, plan, action="create", uid=None):
    if action not in {"create", "update", "cancel"}:
        raise ValueError("Unknown calendar action")
    uid = uid or f"trustnet-{person}-{ref}"
    content = json.dumps({"uid": uid, "ref": ref, "plan": plan, "action": action}, sort_keys=True)
    token = hashlib.sha256(content.encode()).hexdigest()
    with database(person) as connection:
        _table(connection)
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT value FROM calendar_tasks WHERE uid=?", (uid,)).fetchone()
        previous = json.loads(row[0]) if row else {}
        if previous.get("token") == token:
            return previous
        if previous:
            connection.execute(
                "INSERT OR IGNORE INTO calendar_operations VALUES (?, ?)", (previous["token"], uid)
            )
        if connection.execute(
            "SELECT 1 FROM calendar_operations WHERE token=?", (token,)
        ).fetchone():
            return previous
        item = {
            "uid": uid,
            "ref": ref,
            "plan": plan,
            "action": action,
            "token": token,
            "status": "pending",
            "provider": previous.get("provider", ""),
            "event_id": previous.get("event_id", ""),
            "error": "",
        }
        connection.execute(
            "INSERT OR REPLACE INTO calendar_tasks VALUES (?, ?, ?)", (uid, token, json.dumps(item))
        )
        connection.execute("INSERT OR IGNORE INTO calendar_operations VALUES (?, ?)", (token, uid))
    return item


def all_tasks(person):
    with database(person) as connection:
        _table(connection)
        rows = connection.execute("SELECT value FROM calendar_tasks ORDER BY rowid").fetchall()
    return [json.loads(row[0]) for row in rows]


def pending(person, *, due_only=False):
    return [
        item
        for item in all_tasks(person)
        if item["status"] != "applied" and (not due_only or item.get("retry_at", 0) <= time.time())
    ]


def apply_local(person, token):
    """Apply one approved operation to the person's local ICS file, then record it.

    The gate writes the file itself, so a local receipt always matches the file.
    """
    from datetime import datetime

    from trustnet.gate.calendar import put_event, remove_event
    from trustnet.gate.facts import load_profile

    item = next((t for t in all_tasks(person) if t["token"] == token), None)
    if item is None:
        raise ValueError("Unknown or superseded calendar operation")
    if item["status"] == "applied":
        return item
    path = load_profile(person).calendar_path
    plan = item["plan"]
    if item["action"] == "cancel":
        remove_event(path, item["uid"])
    else:
        start = datetime.fromisoformat(plan["start"])
        put_event(
            path, start, int(plan["minutes"]), plan["title"], plan.get("place", ""), item["uid"]
        )
    return report(person, token, "applied", "local-ics", item["uid"])


def report(person, token, status, provider="", event_id="", error=""):
    if status not in {"applied", "failed"}:
        raise ValueError("Calendar status must be applied or failed")
    if status == "applied" and (not provider.strip() or not event_id.strip()):
        raise ValueError("An applied operation needs its provider and event ID")
    if status == "failed" and not error.strip():
        raise ValueError("A failed operation needs an explanation")
    if max(map(len, (token, provider, event_id, error))) > 2000:
        raise ValueError("Calendar receipt is too long")
    with database(person) as connection:
        _table(connection)
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT value FROM calendar_tasks WHERE token=?", (token,)
        ).fetchone()
        if not row:
            raise ValueError("Unknown or superseded calendar operation")
        item = json.loads(row[0])
        if item["status"] == "applied":
            if status == "applied" and (provider, event_id) == (item["provider"], item["event_id"]):
                return item
            raise ValueError("Calendar operation already has a receipt")
        item.update(status=status, error=error if status == "failed" else "")
        if status == "failed":
            item["attempts"] = item.get("attempts", 0) + 1
            item["retry_at"] = time.time() + min(3600, 300 * item["attempts"])
        if status == "applied":
            item.update(provider=provider, event_id=event_id)
        connection.execute(
            "UPDATE calendar_tasks SET value=? WHERE token=?", (json.dumps(item), token)
        )
    return item
