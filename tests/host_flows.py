"""Host onboarding scenarios exercised through the CLI handlers and real HTTP.

Both the pytest suite and ``scripts/e2e_host_onboarding.py`` run these. Every
scenario gets its own temporary config, invite database, real threaded host
server and real-HTTP fake Switch Gateway. Nothing reads or writes the user's
configuration.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import socket
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

import httpx
from fakes.fake_gateway import FakeGateway

from trustnet.tn import configuration, host
from trustnet.tn.cli import main as run_cli

BUNDLE_KEYS = {
    "person",
    "switch_url",
    "registration_key",
    "identity_url",
    "identity_token",
}

#: People whose registration keys arrive through the environment, the manual
#: path that must not touch the Switch Gateway.
MANUAL_KEYS = {
    "alice": "TN_E2E_ALICE_KEY",
    "bob": "TN_E2E_BOB_KEY",
    "carol": "TN_E2E_CAROL_KEY",
    "dave": "TN_E2E_DAVE_KEY",
}


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class HostHarness:
    """One isolated host: fake gateway, config, invite DB and HTTP server."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.config_dir = root / "config"
        self.identity_map = root / "trusted-identities.json"
        self.port = free_port()
        self.public_url = f"http://127.0.0.1:{self.port}"
        self.gateway = FakeGateway()
        self.env_keys = {person: f"manual-{person}-registration-key" for person in MANUAL_KEYS}
        self.server: ThreadingHTTPServer | None = None
        self.server_thread: threading.Thread | None = None
        self.outputs: list[str] = []
        self._patches: list[mock._patch] = []

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> "HostHarness":
        self.root.mkdir(parents=True, exist_ok=True)
        self.identity_map.write_text(
            json.dumps(
                {
                    "om-user": {"kind": "user", "id": "om"},
                    "om-agent": {"kind": "agent", "id": "om-hermes", "owner_id": "om"},
                }
            )
        )
        self.gateway.start()

        config_patch = mock.patch.object(configuration, "config_dir", lambda: self.config_dir)
        config_patch.start()
        self._patches.append(config_patch)

        environment = {
            "SWITCH_ADMIN_EMAIL": self.gateway.admin_email,
            "SWITCH_ADMIN_PASSWORD": self.gateway.admin_password,
        }
        for person, env_name in MANUAL_KEYS.items():
            environment[env_name] = self.env_keys[person]
        env_patch = mock.patch.dict(os.environ, environment, clear=False)
        env_patch.start()
        self._patches.append(env_patch)

        code, _, out, err = self.run(*self.init_argv())
        if code != 0:
            raise AssertionError(f"host init failed ({code}): {err or out}")

        config = configuration.read_json(self.config_dir / host.HOST_FILENAME)
        self.server = host.create_server(config, bind="127.0.0.1", port=self.port)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self._wait_ready()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        if self.server_thread is not None:
            self.server_thread.join(5)
        self.gateway.stop()
        for patch in reversed(self._patches):
            patch.stop()
        self._patches.clear()

    # -- CLI ---------------------------------------------------------------

    def init_argv(self, *extra: str) -> tuple[str, ...]:
        argv = [
            "host",
            "init",
            "--switch-url",
            self.gateway.url,
            "--public-url",
            self.public_url,
            "--bind",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--identity-mode",
            "file",
            "--identity-map",
            str(self.identity_map),
        ]
        for person, env_name in MANUAL_KEYS.items():
            argv += ["--registration-key", f"{person}={env_name}"]
        return tuple(argv) + tuple(extra)

    def run(self, *argv: str) -> tuple[int, dict | None, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = run_cli([*argv, "--json"])
        captured = out.getvalue() + err.getvalue()
        self.outputs.append(captured)
        payload = None
        if code == 0 and out.getvalue().strip():
            payload = json.loads(out.getvalue())
        return code, payload, out.getvalue(), err.getvalue()

    # -- invite and HTTP ---------------------------------------------------

    def invite(self, person: str, *, ttl: int | None = None) -> dict:
        argv = ["invite", "create", person]
        if ttl is not None:
            argv += ["--ttl", str(ttl)]
        code, payload, out, err = self.run(*argv)
        if code != 0 or payload is None:
            raise AssertionError(f"invite create {person} failed ({code}): {err or out}")
        url = payload["invite_url"]
        parts = urlsplit(url)
        assert parts.fragment, f"invite URL has no opaque token: {url}"
        return {**payload, "token": parts.fragment}

    def redeem(self, token: str, request_id: str | None = None) -> httpx.Response:
        body: dict[str, str] = {"token": token}
        if request_id is not None:
            body["request_id"] = request_id
        return httpx.post(f"{self.public_url}/redeem", json=body, timeout=10)

    def identities(self, token: str | None) -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
        return httpx.get(f"{self.public_url}/identities", headers=headers, timeout=10)

    def config(self) -> dict:
        return configuration.read_json(self.config_dir / host.HOST_FILENAME)

    def invite_rows(self) -> list[dict]:
        connection = sqlite3.connect(self.config_dir / host.INVITE_DB_FILENAME)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT id, person, created_at, expires_at, redeemed_at FROM invites ORDER BY id"
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def redemption_count(self) -> int:
        connection = sqlite3.connect(self.config_dir / host.INVITE_DB_FILENAME)
        try:
            return int(connection.execute("SELECT COUNT(*) FROM redemptions").fetchone()[0])
        finally:
            connection.close()

    def invite_db_bytes(self) -> bytes:
        return (self.config_dir / host.INVITE_DB_FILENAME).read_bytes()

    def all_output(self) -> str:
        return "".join(self.outputs)

    def _wait_ready(self) -> None:
        for _ in range(100):
            try:
                if httpx.get(f"{self.public_url}/", timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            threading.Event().wait(0.02)
        raise AssertionError("host server did not start")


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def init_contract(h: HostHarness) -> dict:
    path = h.config_dir / host.HOST_FILENAME
    assert path.is_file()
    assert path.stat().st_mode & 0o777 == 0o600, "host.json must be private"
    config = h.config()
    assert config["switch_url"] == h.gateway.url
    assert config["public_url"] == h.public_url
    assert config["gateway"]["email"] == h.gateway.admin_email
    assert config["gateway"]["password"] == h.gateway.admin_password
    assert h.gateway.admin_password not in h.all_output()

    code, _, _, err = h.run(*h.init_argv())
    assert code == 1 and "already exists" in err, err

    code, _, _, err = h.run(*h.init_argv("--force", "--public-url", "http://example.com"))
    assert code == 1 and "https" in err.lower(), err
    assert h.config()["public_url"] == h.public_url, "a refused init must not overwrite"

    code, _, _, err = h.run(*h.init_argv("--force", "--admin-password", "leaked"))
    assert code == 2, "admin credentials must not be CLI arguments"
    assert "--admin-password" in err

    return {"config_mode": "0600", "refused_http_public_url": True}


def manual_registration_key(h: HostHarness) -> dict:
    before = len(h.gateway.created_users)
    info = h.invite("dave")
    assert len(h.gateway.created_users) == before, "manual key path must not provision"
    assert h.gateway.created_keys == []

    response = h.redeem(info["token"], "dave-attempt-1")
    assert response.status_code == 200, response.text
    bundle = response.json()
    assert set(bundle) == BUNDLE_KEYS
    assert bundle["person"] == "dave"
    assert bundle["registration_key"] == h.env_keys["dave"]
    assert bundle["switch_url"] == h.gateway.url
    assert bundle["identity_url"] == f"{h.public_url}/identities"
    assert h.env_keys["dave"] not in h.all_output(), "registration keys never printed"
    return {"provisioned": False, "bundle_keys": sorted(bundle)}


def new_provisioned_person(h: HostHarness) -> dict:
    before = len(h.gateway.created_users)
    info = h.invite("nina")

    created = h.gateway.created_users[before:]
    assert [user["email"] for user in created] == ["nina@switch.local"], created
    assert h.gateway.key_for("nina@switch.local"), "invite must create a registration key"

    response = h.redeem(info["token"], "nina-attempt-1")
    assert response.status_code == 200, response.text
    bundle = response.json()
    assert set(bundle) == BUNDLE_KEYS
    assert bundle["registration_key"] == h.gateway.key_for("nina@switch.local")
    assert bundle["registration_key"] not in h.all_output()

    record = h.config()["people"]["nina"]
    assert record["switch_user_id"] == h.gateway.user_for("nina@switch.local")["id"]

    people_file = json.loads((h.config_dir / host.IDENTITY_PEOPLE_FILENAME).read_text())
    assert people_file["nina@switch.local"] == "nina"

    mapped = h.identities(bundle["identity_token"])
    assert mapped.status_code == 200, mapped.text
    identities = mapped.json()
    assert identities[record["switch_user_id"]] == {"kind": "user", "id": "nina"}
    assert identities["om-user"] == {"kind": "user", "id": "om"}
    assert identities["om-agent"] == {
        "kind": "agent",
        "id": "om-hermes",
        "owner_id": "om",
    }
    return {
        "created_user": created[0]["email"],
        "identity": identities[record["switch_user_id"]],
    }


def expired_invite(h: HostHarness) -> dict:
    info = h.invite("bob", ttl=0)
    response = h.redeem(info["token"], "bob-expired")
    assert response.status_code == 410, response.text
    assert response.json()["error"]
    assert info["token"].encode() not in h.invite_db_bytes(), "tokens are stored hashed"
    assert h.invite_rows()[0]["redeemed_at"] is None

    fresh = h.invite("bob")
    assert h.redeem(fresh["token"], "bob-fresh").status_code == 200
    return {"expired_status": 410, "fresh_after_expiry": True}


def single_use_with_stable_nonce(h: HostHarness) -> dict:
    info = h.invite("alice")
    assert info["token"].encode() not in h.invite_db_bytes()

    first = h.redeem(info["token"], "attempt-1")
    assert first.status_code == 200, first.text
    bundle = first.json()

    retry = h.redeem(info["token"], "attempt-1")
    assert retry.status_code == 200, retry.text
    assert retry.json() == bundle

    other = h.redeem(info["token"], "attempt-2")
    assert other.status_code == 409, other.text
    anonymous = h.redeem(info["token"])
    assert anonymous.status_code == 409, anonymous.text
    assert h.redemption_count() == 1

    return {"retry_same_nonce": 200, "second_nonce": 409}


def concurrent_redemption_one_winner(h: HostHarness) -> dict:
    info = h.invite("carol")
    attempts = [f"race-{number}" for number in range(8)]
    barrier = threading.Barrier(len(attempts))

    def redeem_once(request_id: str) -> httpx.Response:
        barrier.wait(timeout=5)
        return httpx.post(
            f"{h.public_url}/redeem",
            json={"token": info["token"], "request_id": request_id},
            timeout=10,
        )

    with ThreadPoolExecutor(max_workers=len(attempts)) as pool:
        responses = list(pool.map(redeem_once, attempts))

    statuses = [response.status_code for response in responses]
    assert statuses.count(200) == 1, statuses
    assert statuses.count(409) == len(attempts) - 1, statuses
    winner = next(response for response in responses if response.status_code == 200)
    assert set(winner.json()) == BUNDLE_KEYS
    assert h.redemption_count() == 1
    return {"statuses": statuses}


def concurrent_same_nonce(h: HostHarness) -> dict:
    info = h.invite("carol")
    barrier = threading.Barrier(8)

    def redeem_once(_: int) -> httpx.Response:
        barrier.wait(timeout=5)
        return httpx.post(
            f"{h.public_url}/redeem",
            json={"token": info["token"], "request_id": "same-attempt"},
            timeout=10,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(redeem_once, range(8)))

    assert [response.status_code for response in responses] == [200] * 8
    bundles = {json.dumps(response.json(), sort_keys=True) for response in responses}
    assert len(bundles) == 1, "one nonce must always name one bundle"
    assert h.redemption_count() == 1
    return {"statuses": [200] * 8, "distinct_bundles": len(bundles)}


def identity_requires_bearer(h: HostHarness) -> dict:
    info = h.invite("alice")
    bundle = h.redeem(info["token"], "identity-attempt").json()

    assert h.identities(None).status_code == 401
    assert h.identities("not-the-token").status_code == 401
    unauthorized = httpx.get(
        f"{h.public_url}/identities",
        headers={"Authorization": "Basic dG46dG4="},
        timeout=10,
    )
    assert unauthorized.status_code == 401

    authorized = h.identities(bundle["identity_token"])
    assert authorized.status_code == 200, authorized.text
    assert authorized.headers["cache-control"] == "no-store"
    identities = authorized.json()
    assert identities["om-user"] == {"kind": "user", "id": "om"}

    db = h.invite_db_bytes()
    assert bundle["identity_token"].encode() not in db
    assert info["token"].encode() not in db
    return {"without_token": 401, "with_token": 200}


def interrupted_provisioning(h: HostHarness) -> dict:
    h.gateway.fail_key_once = True
    code, _, _, _ = h.run("invite", "create", "newperson")
    assert code == 1
    assert len(h.gateway.created_users) == 1
    info = h.invite("newperson")
    assert len(h.gateway.created_users) == 1
    bundle = h.redeem(info["token"], "recovered").json()
    assert bundle["registration_key"] == h.gateway.key_for("newperson@switch.local")
    return {"created_users": 1, "retry_completed": True}


SCENARIOS = {
    "init_contract": init_contract,
    "manual_registration_key": manual_registration_key,
    "new_provisioned_person": new_provisioned_person,
    "expired_invite": expired_invite,
    "single_use_with_stable_nonce": single_use_with_stable_nonce,
    "concurrent_redemption_one_winner": concurrent_redemption_one_winner,
    "concurrent_same_nonce": concurrent_same_nonce,
    "identity_requires_bearer": identity_requires_bearer,
    "interrupted_provisioning": interrupted_provisioning,
}
