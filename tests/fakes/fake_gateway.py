"""A small real-HTTP Switch Gateway for host onboarding E2E tests.

It implements only the endpoints the host uses: admin/person login, user
listing and creation, and registration-key creation. Cookie sessions keep the
same shape as the real gateway, so no test-only branch exists in the host.
"""

from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeGateway:
    """Threaded fake of ``/gateway/auth/login``, ``/users`` and ``/api-keys``."""

    def __init__(
        self,
        *,
        admin_email: str = "admin@switch.local",
        admin_password: str = "admin-password",
    ) -> None:
        self.admin_email = admin_email
        self.admin_password = admin_password
        self.users: dict[str, dict] = {
            admin_email: {
                "id": "admin",
                "name": "Admin",
                "email": admin_email,
                "password": admin_password,
                "role": "admin",
            }
        }
        self.sessions: dict[str, str] = {}
        self.created_users: list[dict] = []
        self.created_keys: list[dict] = []
        self.calls: list[tuple[str, str, str | None]] = []
        self.lock = threading.RLock()
        self.fail_key_once = False
        self._counter = 0
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_type())
        self._server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread: threading.Thread | None = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> "FakeGateway":
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(5)

    def key_for(self, email: str) -> str | None:
        with self.lock:
            keys = [item["key"] for item in self.created_keys if item["email"] == email]
        return keys[-1] if keys else None

    def user_for(self, email: str) -> dict | None:
        with self.lock:
            user = self.users.get(email)
            return dict(user) if user else None

    # -- HTTP --------------------------------------------------------------

    def _handler_type(self):
        gateway = self

        class Handler(_GatewayHandler):
            pass

        Handler.gateway = gateway
        return Handler

    def _next(self) -> int:
        with self.lock:
            self._counter += 1
            return self._counter

    def _session(self, headers) -> tuple[str | None, str | None]:
        raw = headers.get("Cookie", "")
        cookies = {
            key.strip(): value
            for key, _, value in (part.partition("=") for part in raw.split(";") if part.strip())
        }
        session = cookies.get("tn_session")
        with self.lock:
            email = self.sessions.get(session) if session else None
            role = self.users.get(email, {}).get("role") if email else None
        return email, role

    def _public_user(self, user: dict) -> dict:
        return {key: value for key, value in user.items() if key != "password"}


class _GatewayHandler(BaseHTTPRequestHandler):
    gateway: FakeGateway
    protocol_version = "HTTP/1.1"
    server_version = "fake-switch-gateway/1"
    sys_version = ""

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        pass

    def do_GET(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()

    def _dispatch(self) -> None:
        session, role = self.gateway._session(self.headers)
        self.gateway.calls.append((self.command, self.path, session))
        if self.command == "POST" and self.path == "/gateway/auth/login":
            return self._login()
        if self.command == "GET" and self.path == "/gateway/users":
            if role != "admin":
                return self._send(403, {"detail": "admin required"})
            with self.gateway.lock:
                users = [self.gateway._public_user(user) for user in self.gateway.users.values()]
            return self._send(200, users)
        if self.command == "POST" and self.path == "/gateway/users":
            if role != "admin":
                return self._send(403, {"detail": "admin required"})
            return self._create_user()
        if self.command == "POST" and self.path == "/gateway/api-keys":
            if session is None:
                return self._send(401, {"detail": "login required"})
            return self._create_key(session)
        return self._send(404, {"detail": "not found"})

    def _body(self) -> dict | None:
        length = self.headers.get("Content-Length")
        if length is None:
            self._send(411, {"detail": "length required"})
            return None
        try:
            raw = self.rfile.read(int(length))
            value = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"detail": "bad json"})
            return None
        return value if isinstance(value, dict) else None

    def _login(self) -> None:
        body = self._body()
        if body is None:
            return
        email = str(body.get("email", ""))
        password = str(body.get("password", ""))
        with self.gateway.lock:
            user = self.gateway.users.get(email)
            valid = user is not None and user["password"] == password
        if not valid:
            return self._send(401, {"detail": "bad credentials"})
        session = secrets.token_urlsafe(12)
        with self.gateway.lock:
            self.gateway.sessions[session] = email
            payload = self.gateway._public_user(self.gateway.users[email])
        self._send(
            200,
            payload,
            headers={"Set-Cookie": f"tn_session={session}; Path=/; HttpOnly"},
        )

    def _create_user(self) -> None:
        body = self._body()
        if body is None:
            return
        email = str(body.get("email", "")).strip().lower()
        password = str(body.get("password", ""))
        name = str(body.get("name", "")).strip() or email.split("@", 1)[0]
        if not email or not password:
            return self._send(400, {"detail": "email and password required"})
        with self.gateway.lock:
            if email in self.gateway.users:
                return self._send(409, {"detail": "user exists"})
            user = {
                "id": f"u{self.gateway._next()}",
                "name": name,
                "email": email,
                "password": password,
                "role": "member",
            }
            self.gateway.users[email] = user
            self.gateway.created_users.append(self.gateway._public_user(user))
        self._send(200, self.gateway._public_user(user))

    def _create_key(self, email: str) -> None:
        if self.gateway.fail_key_once:
            self.gateway.fail_key_once = False
            return self._send(503, {"detail": "temporarily unavailable"})
        number = self.gateway._next()
        record = {
            "id": f"k{number}",
            "email": email,
            "key": f"fake-registration-key-{number}-{secrets.token_urlsafe(8)}",
        }
        with self.gateway.lock:
            self.gateway.created_keys.append(record)
        self._send(200, {"id": record["id"], "key": record["key"]})

    def _send(self, status: int, payload, headers: dict | None = None) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)
