"""Create the demo's Switch users and their registration keys (Day-0 check 1).

Signs in to the local Switch Gateway as the admin, creates `rahul` and `priya`
if they don't exist, then signs in as Om (the admin), Rahul and Priya in turn and
creates one registration key each. Keys and the generated passwords go into
`.env` only; nothing secret is printed.

Admin credentials come from SWITCH_ADMIN_EMAIL / SWITCH_ADMIN_PASSWORD, or, with
`--console-env`, from the env file Switch Console started switch-core with
(GATEWAY_ADMIN_EMAIL / GATEWAY_ADMIN_PASSWORD).

Safe to re-run: existing users are reused (their password must be in `.env`),
and a key already present in `.env` is left alone.

    uv run python scripts/switch_users.py --console-env
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parent.parent
CONSOLE_ENV = (
    Path.home()
    / "Library/Application Support/switchdash/local-switch-server/native/run/switch-core.env"
)
PEOPLE = {
    # person: (display name, email, .env key var, .env password var or None for the admin)
    "om": ("Om", None, "OM_GATE_KEY", None),
    "rahul": ("Rahul", "rahul@switch.local", "RAHUL_GATE_KEY", "RAHUL_SWITCH_PASSWORD"),
    "priya": ("Priya", "priya@switch.local", "PRIYA_GATE_KEY", "PRIYA_SWITCH_PASSWORD"),
}
KEY_LABEL = "trust-network gate"


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def vm_host() -> str:
    """The VM's ssh target: TN_VM_HOST from the environment or .env (gitignored)."""
    if host := os.environ.get("TN_VM_HOST"):
        return host
    saved = read_env(REPO / ".env").get("TN_VM_HOST", "").strip("\"'")
    return saved or "om@hermes.<tailnet>.ts.net"


def set_env(path: Path, key: str, value: str) -> None:
    """Set KEY=value in a dotenv file, replacing an existing line or appending one."""
    lines = path.read_text().splitlines() if path.exists() else []
    for i, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == key:
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o600)


def login(base: str, email: str, password: str) -> httpx.Client:
    client = httpx.Client(base_url=f"{base}/gateway", timeout=15.0)
    resp = client.post("/auth/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        sys.exit(f"login failed for {email}: HTTP {resp.status_code} {resp.text[:200]}")
    return client


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:53330", help="switch-core base URL")
    parser.add_argument("--env-file", type=Path, default=REPO / ".env")
    parser.add_argument(
        "--console-env", action="store_true", help=f"read admin login from {CONSOLE_ENV}"
    )
    args = parser.parse_args()

    if args.console_env:
        console = read_env(CONSOLE_ENV)
        admin_email = console.get("GATEWAY_ADMIN_EMAIL", "")
        admin_password = console.get("GATEWAY_ADMIN_PASSWORD", "")
    else:
        admin_email = os.environ.get("SWITCH_ADMIN_EMAIL", "")
        admin_password = os.environ.get("SWITCH_ADMIN_PASSWORD", "")
    if not admin_email or not admin_password:
        sys.exit("no admin login: pass --console-env or set SWITCH_ADMIN_EMAIL/PASSWORD")

    env = read_env(args.env_file)
    admin = login(args.url, admin_email, admin_password)
    me = admin.get("/auth/me").json()
    print(f"signed in as admin: {me.get('name')} <{me.get('email')}> role={me.get('role')}")
    existing = {u["email"]: u for u in admin.get("/users").json()}

    for person, (name, email, key_var, pw_var) in PEOPLE.items():
        if pw_var is None:
            client = admin
        else:
            password = env.get(pw_var, "")
            if email in existing:
                if not password:
                    sys.exit(f"{email} exists but {pw_var} is not in .env; set it and re-run")
                print(f"user {person}: exists")
            else:
                password = password or secrets.token_urlsafe(18)
                set_env(args.env_file, pw_var, password)
                resp = admin.post(
                    "/users", json={"name": name, "email": email, "password": password}
                )
                if resp.status_code != 200:
                    sys.exit(f"create {email} failed: HTTP {resp.status_code} {resp.text[:200]}")
                print(f"user {person}: created ({email}, id {resp.json()['id']})")
            client = login(args.url, email, password)

        if env.get(key_var):
            print(f"key {key_var}: already in .env, left alone")
            continue
        resp = client.post("/api-keys", json={"label": KEY_LABEL})
        if resp.status_code != 200:
            sys.exit(f"create key for {person} failed: HTTP {resp.status_code} {resp.text[:200]}")
        set_env(args.env_file, key_var, resp.json()["key"])
        print(f"key {key_var}: created (id {resp.json()['id']}), written to .env")

    print(f"done; secrets are in {args.env_file} only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
