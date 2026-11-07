"""Expiring onboarding invites and authenticated server identity discovery."""

from __future__ import annotations

import argparse
import fcntl
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx

from trustnet.tn import configuration

__all__ = ["HostError", "add_commands", "create_server"]

HOST_FILENAME = "host.json"
INVITE_DB_FILENAME = "invites.sqlite3"
IDENTITY_PEOPLE_FILENAME = "identity-people.json"

DEFAULT_PORT = 8788
DEFAULT_INVITE_TTL = 24 * 60 * 60
MAX_BODY = 64 * 1024
KEY_LABEL = "trust-network gate"

_PERSON_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS invites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    identity_token_hash TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    redeemed_at REAL
);
CREATE TABLE IF NOT EXISTS redemptions (
    invite_id INTEGER NOT NULL REFERENCES invites(id),
    request_id TEXT NOT NULL,
    bundle TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (invite_id, request_id)
);
"""

_IDENTITY_LOCK = threading.Lock()


class HostError(ValueError):
    """A host command or request cannot complete; the message is safe to show."""


def add_commands(commands: argparse._SubParsersAction, common: argparse.ArgumentParser) -> None:
    """Register ``tn host`` and ``tn invite`` beside the existing commands."""
    host_parser = commands.add_parser(
        "host",
        parents=[common],
        help="set up and run the shared onboarding host",
        description="One shared host: existing Switch server, invites and identities.",
    )
    host_commands = host_parser.add_subparsers(
        dest="host_command", required=True, metavar="command"
    )

    host_init = host_commands.add_parser(
        "init",
        parents=[common],
        help="write the one-time host config",
        description=(
            "Store the existing Switch URL, public HTTPS URL and Gateway admin "
            "credentials. Admin credentials come from the environment or getpass, "
            "never from argv."
        ),
    )
    host_init.add_argument(
        "--switch-url",
        metavar="URL",
        default=None,
        help="existing Switch base URL (default: $SWITCH_URL)",
    )
    host_init.add_argument(
        "--public-url",
        metavar="URL",
        default=None,
        help="public HTTPS URL behind the TLS reverse proxy (default: $TN_PUBLIC_URL)",
    )
    host_init.add_argument("--bind", default="127.0.0.1", help="loopback bind address")
    host_init.add_argument("--port", type=int, default=DEFAULT_PORT, help="loopback port")
    host_init.add_argument(
        "--ttl", type=int, default=DEFAULT_INVITE_TTL, dest="invite_ttl", metavar="SECONDS"
    )
    host_init.add_argument(
        "--registration-key",
        action="append",
        default=[],
        metavar="PERSON=ENV",
        help="use a registration key from ENV for this person (manual/test path)",
    )
    host_init.add_argument(
        "--identity-mode",
        choices=("local", "file"),
        default="local",
        help="local: run the packaged exporter; file: serve a trusted export",
    )
    host_init.add_argument(
        "--identity-map",
        type=Path,
        default=None,
        metavar="PATH",
        help="trusted export path, also the local exporter's output",
    )
    host_init.add_argument("--force", action="store_true", help="overwrite host.json")
    host_init.set_defaults(handler=_cmd_host_init)

    host_serve = host_commands.add_parser(
        "serve",
        parents=[common],
        help="run the loopback host (publish it through a TLS reverse proxy)",
        description="Serve /redeem and /identities on loopback.",
    )
    host_serve.add_argument("--bind", default=None, help="override the configured bind")
    host_serve.add_argument("--port", type=int, default=None, help="override the configured port")
    host_serve.set_defaults(handler=_cmd_host_serve)

    invite = commands.add_parser(
        "invite",
        parents=[common],
        help="create onboarding invites",
        description="Create an expiring, single-use invite for one person.",
    )
    invite_commands = invite.add_subparsers(dest="invite_command", required=True, metavar="command")
    invite_create = invite_commands.add_parser(
        "create",
        parents=[common],
        help="provision a person if needed and print their invite URL",
        description=(
            "Provision the Switch user and registration key through the Gateway, "
            "or use the configured registration-key environment variable."
        ),
    )
    invite_create.add_argument("person_name", metavar="person")
    invite_create.add_argument(
        "--ttl",
        type=int,
        default=None,
        dest="invite_ttl",
        metavar="SECONDS",
        help="override the configured invite lifetime (0 expires immediately)",
    )
    invite_create.set_defaults(handler=_cmd_invite_create)


def _cmd_host_init(context, args: argparse.Namespace) -> int:
    with (_config_directory() / "host.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _initialize_host(context, args)


def _initialize_host(context, args: argparse.Namespace) -> int:
    switch_url = (args.switch_url or os.environ.get("SWITCH_URL") or "").strip()
    if not switch_url:
        raise HostError("pass --switch-url or set SWITCH_URL")
    switch_url = configuration.checked_url(switch_url)

    public_url = (args.public_url or os.environ.get("TN_PUBLIC_URL") or "").strip()
    if not public_url:
        raise HostError("pass --public-url or set TN_PUBLIC_URL")
    public_url = configuration.checked_url(public_url)

    bind = _loopback_bind(args.bind)
    _port(args.port)
    if args.invite_ttl < 0:
        raise HostError("--ttl cannot be negative")

    admin_email, admin_password = _admin_credentials()
    registrations = _parse_registration_keys(args.registration_key)

    directory = _config_directory()
    path = directory / HOST_FILENAME
    if path.exists() and not args.force:
        raise HostError(f"{path} already exists; pass --force to overwrite")

    previous = configuration.read_json(path)
    people = previous.get("people", {})
    for person, env_name in registrations.items():
        record = people.setdefault(person, {})
        record.setdefault("email", f"{person}@switch.local")
        record.setdefault("display_name", _display_name(person))
        record["registration_key_env"] = env_name

    map_path = (args.identity_map or directory / "identities.json").expanduser()
    if not map_path.is_absolute():
        map_path = (Path.cwd() / map_path).resolve()
    people_path = directory / IDENTITY_PEOPLE_FILENAME
    config = {
        "version": 1,
        "switch_url": switch_url,
        "public_url": public_url,
        "bind": bind,
        "port": args.port,
        "invite_ttl_seconds": args.invite_ttl,
        "gateway": {"email": admin_email, "password": admin_password},
        "identity_token_secret": previous.get("identity_token_secret") or secrets.token_urlsafe(32),
        "identity": {
            "mode": args.identity_mode,
            "map_path": str(map_path),
            "people_path": str(people_path),
        },
        "people": people,
    }
    _save_config(path, config)
    _write_people_mapping(people_path, people)

    payload = {
        "config": str(path),
        "invite_database": str(directory / INVITE_DB_FILENAME),
        "switch_url": switch_url,
        "public_url": public_url,
        "identity_mode": args.identity_mode,
        "people": sorted(people),
    }
    return context.emit(
        payload,
        f"initialized {path} for {public_url} (people: {', '.join(sorted(people)) or 'none'})",
    )


def _admin_credentials() -> tuple[str, str]:
    email = (
        os.environ.get("SWITCH_ADMIN_EMAIL") or os.environ.get("TN_HOST_ADMIN_EMAIL") or ""
    ).strip()
    password = (
        os.environ.get("SWITCH_ADMIN_PASSWORD") or os.environ.get("TN_HOST_ADMIN_PASSWORD") or ""
    )
    if not email:
        if not sys.stdin.isatty():
            raise HostError(
                "set SWITCH_ADMIN_EMAIL (Gateway admin credentials are never CLI arguments)"
            )
        email = input("Switch admin email: ").strip()
    if not password:
        if not sys.stdin.isatty():
            raise HostError("set SWITCH_ADMIN_PASSWORD")
        password = getpass.getpass("Switch admin password: ")
    if not email or not password:
        raise HostError("Gateway admin email and password are both required")
    return email, password


def _parse_registration_keys(values: list[str]) -> dict[str, str]:
    registrations: dict[str, str] = {}
    for value in values:
        person, separator, env_name = value.partition("=")
        person = person.strip().lower()
        env_name = env_name.strip()
        if not separator or not _PERSON_RE.fullmatch(person):
            raise HostError("--registration-key takes PERSON=ENV")
        if not _ENV_RE.fullmatch(env_name):
            raise HostError(f"{env_name!r} is not an environment variable name")
        if person in registrations:
            raise HostError(f"{person} is listed twice in --registration-key")
        registrations[person] = env_name
    return registrations


def _cmd_invite_create(context, args: argparse.Namespace) -> int:
    with (_config_directory() / "host.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _create_invite(context, args)


def _create_invite(context, args: argparse.Namespace) -> int:
    person = args.person_name.strip().lower()
    if not _PERSON_RE.fullmatch(person):
        raise HostError(f"invalid person name {args.person_name!r}")

    config, path = _load_config()
    ttl = config.get("invite_ttl_seconds", DEFAULT_INVITE_TTL)
    if args.invite_ttl is not None:
        ttl = args.invite_ttl
    if not isinstance(ttl, int) or ttl < 0:
        raise HostError("the invite lifetime must be zero or more seconds")

    _provision(config, path, person)

    database = _workspace_database()
    _ensure_schema(database)
    token = secrets.token_urlsafe(32)
    identity_token = _derive_identity_token(config, token)
    now = time.time()
    expires = now + ttl
    connection = _connect(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO invites "
            "(person, token_hash, identity_token_hash, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (person, _hash(token), _hash(identity_token), now, expires),
        )
        connection.execute("COMMIT")
    except sqlite3.Error as exc:
        connection.rollback()
        raise HostError(f"could not store the invite: {exc}") from None
    finally:
        connection.close()

    invite_url = f"{config['public_url'].rstrip('/')}/join#{token}"
    expires_at = datetime.fromtimestamp(expires, timezone.utc).isoformat()
    payload = {
        "person": person,
        "invite_url": invite_url,
        "expires_at": expires_at,
        "expires_in": ttl,
    }
    return context.emit(payload, f"invite for {person}: {invite_url} (expires {expires_at})")


def _provision(config: dict[str, Any], path: Path, person: str) -> str:
    """Return the person's registration key, provisioning Switch when needed."""
    people = config.setdefault("people", {})
    record = people.setdefault(person, {})
    record.setdefault("email", f"{person}@switch.local")
    record.setdefault("display_name", _display_name(person))

    env_name = record.get("registration_key_env") or _default_key_env(person)
    supplied = os.environ.get(str(env_name), "").strip()
    if supplied:
        record["registration_key"] = supplied
        _save_provisioning(config, path, people)
        return supplied

    existing_key = str(record.get("registration_key") or "").strip()
    if existing_key:
        return existing_key

    gateway = config.get("gateway") or {}
    admin_email = str(gateway.get("email") or "").strip()
    admin_password = str(gateway.get("password") or "")
    if not admin_email or not admin_password:
        raise HostError("host.json has no Gateway admin credentials; re-run `tn host init --force`")
    switch_url = str(config.get("switch_url") or "").rstrip("/")
    if not switch_url:
        raise HostError("host.json has no switch_url; re-run `tn host init --force`")

    email = str(record.get("email") or f"{person}@switch.local").strip().lower()
    password = str(record.get("password") or "")
    user_id = str(record.get("switch_user_id") or "")

    with _Gateway(switch_url) as admin:
        admin.login(admin_email, admin_password)
        users = admin.users()
        existing = next(
            (user for user in users if str(user.get("email", "")).strip().lower() == email),
            None,
        )
        if existing is not None:
            user_id = str(existing.get("id") or user_id)
            if not password:
                raise HostError(
                    f"Switch user {email} exists; set {env_name} or store its password "
                    "in host.json before inviting"
                )
        else:
            password = password or secrets.token_urlsafe(18)
            record["password"] = password
            _save_provisioning(config, path, people)
            user_id = admin.create_user(str(record["display_name"]), email, password)
            record["switch_user_id"] = user_id
            _save_provisioning(config, path, people)

    record["switch_user_id"] = user_id
    # Persist the credentials before creating the key: a failed key request
    # must be retryable with the same user and password.
    _save_provisioning(config, path, people)

    with _Gateway(switch_url) as person_client:
        person_client.login(email, password)
        registration_key = person_client.create_key()

    record["registration_key"] = registration_key
    record["email"] = email
    _save_provisioning(config, path, people)
    return registration_key


def _save_provisioning(config: dict[str, Any], path: Path, people: dict[str, Any]) -> None:
    people_path = _people_path(config)
    if people_path is not None:
        _write_people_mapping(people_path, people)
    _save_config(path, config)


def _default_key_env(person: str) -> str:
    return "TN_REGISTRATION_KEY_" + person.upper().replace("-", "_")


class _Gateway:
    """The proven Switch Gateway calls, with credentials kept out of errors."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.client: httpx.Client | None = None

    def __enter__(self) -> "_Gateway":
        self.client = httpx.Client(base_url=self.base_url, timeout=15.0, follow_redirects=False)
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.client is not None:
            self.client.close()

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        assert self.client is not None
        try:
            return self.client.request(method, path, **kwargs)
        except httpx.HTTPError:
            raise HostError(f"Switch gateway {self.base_url} is unreachable") from None

    def login(self, email: str, password: str) -> None:
        response = self._request(
            "POST", "/gateway/auth/login", json={"email": email, "password": password}
        )
        if response.status_code != 200:
            raise HostError(f"Switch login failed for {email} (HTTP {response.status_code})")

    def users(self) -> list[dict[str, Any]]:
        response = self._request("GET", "/gateway/users")
        if response.status_code != 200:
            raise HostError(f"Switch user listing failed (HTTP {response.status_code})")
        try:
            value = response.json()
        except ValueError:
            raise HostError("Switch user listing was not JSON") from None
        if not isinstance(value, list):
            raise HostError("Switch user listing was not a list")
        return value

    def create_user(self, name: str, email: str, password: str) -> str:
        response = self._request(
            "POST",
            "/gateway/users",
            json={"name": name, "email": email, "password": password},
        )
        if response.status_code not in (200, 201):
            raise HostError(
                f"Switch user creation failed for {email} (HTTP {response.status_code})"
            )
        try:
            value = response.json()
        except ValueError:
            raise HostError("Switch user creation returned no id") from None
        user_id = value.get("id") if isinstance(value, dict) else None
        if not user_id:
            raise HostError("Switch user creation returned no id")
        return str(user_id)

    def create_key(self) -> str:
        response = self._request("POST", "/gateway/api-keys", json={"label": KEY_LABEL})
        if response.status_code != 200:
            raise HostError(
                f"Switch registration-key creation failed (HTTP {response.status_code})"
            )
        try:
            value = response.json()
        except ValueError:
            raise HostError("Switch registration-key creation returned no key") from None
        key = value.get("key") if isinstance(value, dict) else None
        if not key:
            raise HostError("Switch registration-key creation returned no key")
        return str(key)


# host serve


def _cmd_host_serve(context, args: argparse.Namespace) -> int:
    config, _ = _load_config()
    bind = _loopback_bind(args.bind or config.get("bind") or "127.0.0.1")
    port = args.port if args.port is not None else int(config.get("port", DEFAULT_PORT))
    _port(port, allow_zero=False)
    server = create_server(config, bind=bind, port=port)
    print(
        f"tn host: {config['public_url']} on {bind}:{server.server_address[1]} "
        "(loopback; TLS reverse proxy expected)"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


class _HostServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address) -> None:
        """Never print a traceback: request bodies can hold credentials."""


def create_server(
    config: dict[str, Any] | None = None,
    *,
    bind: str | None = None,
    port: int | None = None,
) -> _HostServer:
    """Build the threaded HTTP server. Callers may bind an ephemeral port."""
    if config is None:
        config, _ = _load_config()
    address = _loopback_bind(bind or config.get("bind") or "127.0.0.1")
    number = port if port is not None else int(config.get("port", DEFAULT_PORT))
    _port(number, allow_zero=True)
    _ensure_schema(_workspace_database())
    return _HostServer((address, number), _HostHandler)


class _HttpError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class _HostHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 10
    server_version = "tn-host/1"
    sys_version = ""

    def log_message(self, format, *args) -> None:  # noqa: A002 - stdlib signature
        """Requests carry no tokens in the URL; still, keep the log empty."""

    def do_GET(self) -> None:
        if self.path == "/identities":
            self._identities()
        elif self.path == "/":
            self._send(200, {"service": "trust-network-host"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/redeem":
            self._redeem()
        else:
            self._send(404, {"error": "not found"})

    # -- endpoints ---------------------------------------------------------

    def _redeem(self) -> None:
        try:
            body = self._json_body()
            token = body.get("token")
            request_id = body.get("request_id")
            if not _valid_token(token):
                raise _HttpError(400, "invalid token")
            if request_id is not None and not (
                isinstance(request_id, str) and _REQUEST_ID_RE.fullmatch(request_id)
            ):
                raise _HttpError(400, "invalid request_id")
            config, _ = _load_config()
            status, payload = _redeem_invite(config, _workspace_database(), token, request_id)
        except _HttpError as exc:
            self._send(exc.status, {"error": exc.message})
        except (HostError, OSError, ValueError, sqlite3.Error):
            self._send(503, {"error": "host unavailable"})
        except Exception:
            self._send(500, {"error": "internal error"})
        else:
            self._send(status, payload)

    def _identities(self) -> None:
        supplied = _bearer_token(self.headers.get("Authorization", ""))
        if not supplied or not _valid_token(supplied):
            self._send(
                401,
                {"error": "bearer token required"},
                headers={"WWW-Authenticate": "Bearer"},
            )
            return
        try:
            if not _identity_authorized(_workspace_database(), supplied):
                self._send(401, {"error": "invalid identity token"})
                return
            config, _ = _load_config()
            raw = _identity_payload(config)
        except (HostError, OSError, ValueError, sqlite3.Error):
            self._send(503, {"error": "identities unavailable"})
        except Exception:
            self._send(500, {"error": "internal error"})
        else:
            self._send_raw(200, raw)

    # -- request and response helpers -------------------------------------

    def _json_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise _HttpError(411, "content length required")
        try:
            length = int(raw_length)
        except ValueError:
            raise _HttpError(400, "invalid content length") from None
        if length < 0:
            raise _HttpError(400, "invalid content length")
        if length > MAX_BODY:
            raise _HttpError(413, "request body too large")
        try:
            value = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            raise _HttpError(400, "invalid JSON") from None
        if not isinstance(value, dict):
            raise _HttpError(400, "expected a JSON object")
        return value

    def _send(self, status: int, payload: Any, headers: dict[str, str] | None = None) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode()
        self._send_raw(status, raw, headers)

    def _send_raw(self, status: int, raw: bytes, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.close_connection = True
        self.wfile.write(raw)


def _redeem_invite(
    config: dict[str, Any],
    database: Path,
    token: str,
    request_id: str | None,
) -> tuple[int, dict[str, Any]]:
    connection = _connect(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id, person, expires_at, redeemed_at FROM invites WHERE token_hash = ?",
            (_hash(token),),
        ).fetchone()
        if row is None:
            connection.rollback()
            return 404, {"error": "invite not found"}

        if row["redeemed_at"] is not None:
            if request_id is not None:
                stored = connection.execute(
                    "SELECT bundle FROM redemptions WHERE invite_id = ? AND request_id = ?",
                    (row["id"], request_id),
                ).fetchone()
                if stored is not None:
                    connection.rollback()
                    payload = json.loads(stored["bundle"])
                    payload["identity_token"] = _derive_identity_token(config, token)
                    return 200, payload
            connection.rollback()
            return 409, {"error": "invite already redeemed"}

        now = time.time()
        if float(row["expires_at"]) <= now:
            connection.rollback()
            return 410, {"error": "invite expired"}

        try:
            bundle = _bundle(config, row["person"], token)
        except HostError:
            connection.rollback()
            return 503, {"error": "invite cannot be completed"}

        # The bearer is derived from the invite token, so it need not be
        # stored; the retry path adds it back. The rest is an exact snapshot.
        stored_bundle = {key: value for key, value in bundle.items() if key != "identity_token"}
        connection.execute("UPDATE invites SET redeemed_at = ? WHERE id = ?", (now, row["id"]))
        if request_id is not None:
            connection.execute(
                "INSERT INTO redemptions (invite_id, request_id, bundle, created_at) "
                "VALUES (?, ?, ?, ?)",
                (row["id"], request_id, json.dumps(stored_bundle, sort_keys=True), now),
            )
        connection.execute("COMMIT")
        return 200, bundle
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()


def _bundle(config: dict[str, Any], person: str, token: str) -> dict[str, Any]:
    record = (config.get("people") or {}).get(person) or {}
    registration_key = str(record.get("registration_key") or "")
    if not registration_key:
        raise HostError(f"no registration key for {person}")
    public_url = str(config.get("public_url") or "").rstrip("/")
    if not public_url:
        raise HostError("host has no public URL")
    return {
        "person": person,
        "switch_url": str(config["switch_url"]),
        "registration_key": registration_key,
        "identity_url": f"{public_url}/identities",
        "identity_token": _derive_identity_token(config, token),
    }


def _derive_identity_token(config: dict[str, Any], invite_token: str) -> str:
    """Derive a stable identity bearer from the invite token and host secret.

    Only hashes of both tokens are stored, yet a retry with the same invite
    token returns the same identity token.
    """
    secret = str(config.get("identity_token_secret") or "")
    if not secret:
        raise HostError("host.json has no identity_token_secret; re-run `tn host init --force`")
    return hmac.new(secret.encode(), invite_token.encode(), hashlib.sha256).hexdigest()


def _identity_payload(config: dict[str, Any]) -> bytes:
    identities = _base_identities(config)
    for person, record in sorted((config.get("people") or {}).items()):
        user_id = record.get("switch_user_id")
        if user_id:
            identities[str(user_id)] = {"kind": "user", "id": person}
    return json.dumps(identities, sort_keys=True).encode()


def _base_identities(config: dict[str, Any]) -> dict[str, Any]:
    identity = config.get("identity") or {}
    mode = identity.get("mode", "local")
    map_path = Path(str(identity.get("map_path") or ""))
    if not str(identity.get("map_path") or ""):
        raise HostError("host.json has no identity map path")
    if mode == "file":
        raw = map_path.read_bytes()
    elif mode == "local":
        from trustnet.gate.identity import export_local

        extra: dict[str, str] = {}
        people_path = _people_path(config)
        if people_path is not None and people_path.is_file():
            extra["TN_IDENTITY_PEOPLE"] = str(people_path)
        with _IDENTITY_LOCK:
            raw = export_local(map_path, env=extra)
    else:
        raise HostError(f"unknown identity mode {mode!r}")
    try:
        value = json.loads(raw)
    except ValueError:
        raise HostError("the trusted identity export is not JSON") from None
    if not isinstance(value, dict):
        raise HostError("the trusted identity export is not an object")
    return value


def _identity_authorized(database: Path, token: str) -> bool:
    connection = _connect(database)
    try:
        row = connection.execute(
            "SELECT 1 FROM invites WHERE identity_token_hash = ? AND redeemed_at IS NOT NULL",
            (_hash(token),),
        ).fetchone()
        return row is not None
    finally:
        connection.close()


def _config_directory() -> Path:
    directory = configuration.config_dir()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    return directory


def _workspace_database() -> Path:
    return _config_directory() / INVITE_DB_FILENAME


def _load_config() -> tuple[dict[str, Any], Path]:
    path = _config_directory() / HOST_FILENAME
    if not path.is_file():
        raise HostError(f"{path} is missing; run `tn host init`")
    config = configuration.read_json(path)
    return config, path


def _save_config(path: Path, config: dict[str, Any]) -> None:
    configuration.write_json(path, config)


def _people_path(config: dict[str, Any]) -> Path | None:
    raw = str((config.get("identity") or {}).get("people_path") or "")
    return Path(raw) if raw else None


def _write_people_mapping(path: Path, people: dict[str, Any]) -> None:
    mapping = {}
    for person, record in sorted(people.items()):
        email = str(record.get("email") or "").strip().lower()
        if email:
            mapping[email] = person
    try:
        configuration.write_json(path, mapping)
    except OSError as exc:
        raise HostError(f"cannot write {path}: {exc}") from None


def _connect(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database, timeout=10.0, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 10000")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _ensure_schema(database: Path) -> None:
    database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        connection = _connect(database)
    except sqlite3.Error as exc:
        raise HostError(f"cannot open the invite database: {exc}") from None
    try:
        connection.executescript(_SCHEMA)
    except sqlite3.Error as exc:
        raise HostError(f"cannot create the invite tables: {exc}") from None
    finally:
        connection.close()
    database.chmod(0o600)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _bearer_token(header: str) -> str:
    scheme, separator, value = header.partition(" ")
    if not separator or scheme.lower() != "bearer":
        return ""
    return value.strip()


def _valid_token(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 16 <= len(value) <= 512
        and all(33 <= ord(character) <= 126 for character in value)
    )


def _loopback_bind(value: str) -> str:
    address = str(value).strip() or "127.0.0.1"
    if address not in _LOOPBACK_HOSTS:
        raise HostError(
            "the host binds loopback; publish 127.0.0.1 through a TLS reverse proxy "
            "instead of binding a public interface"
        )
    return address


def _port(value: int, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if not isinstance(value, int) or value < minimum or value > 65535:
        raise HostError(f"port must be between {minimum} and 65535")
    return value


def _display_name(person: str) -> str:
    return person.replace("-", " ").replace("_", " ").title()
