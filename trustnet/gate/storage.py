"""Owner-local transaction state and atomic file projections."""

import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path

from trustnet.gate.facts import resolve_data_dir


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data if isinstance(data, bytes) else data.encode())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def database(person):
    path = resolve_data_dir(person) / "decisions.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.touch(mode=0o600, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    try:
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS state (domain TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        with connection:
            yield connection
    finally:
        connection.close()


def load(person, domain):
    directory = resolve_data_dir(person)
    legacy = directory / (domain + ".json")
    if not (directory / "decisions.sqlite3").exists() and not legacy.exists():
        return {}
    with database(person) as connection:
        row = connection.execute("SELECT value FROM state WHERE domain=?", (domain,)).fetchone()
        if row:
            state = json.loads(row[0])
        else:
            path = resolve_data_dir(person) / (domain + ".json")
            state = json.loads(path.read_text()) if path.exists() else {}
            connection.execute("INSERT INTO state VALUES (?, ?)", (domain, json.dumps(state)))
    path = resolve_data_dir(person) / (domain + ".json")
    payload = json.dumps(state)
    if not path.exists() or path.read_text() != payload:
        atomic_write(path, payload)
    return state


def save(person, domain, state):
    payload = json.dumps(state)
    with database(person) as connection:
        connection.execute("INSERT OR REPLACE INTO state VALUES (?, ?)", (domain, payload))
    atomic_write(resolve_data_dir(person) / (domain + ".json"), payload)
