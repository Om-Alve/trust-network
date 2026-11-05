#!/usr/bin/env python3
"""Probe a switch-core server over HTTPS and WebSockets.

Day-0 check 2 (PLAN.md section 8): the Azure VM must reach the laptop's
switch-core through Tailscale Serve, WebSockets included. Run this from the VM.

Usage:
    python scripts/ws_probe.py --base-url https://<laptop>.<tailnet>.ts.net
    SWITCH_URL=https://<laptop>.<tailnet>.ts.net python scripts/ws_probe.py \
        --path /v1/<path> --ws-path /v1/<ws-path>

Prints one PASS/FAIL line per probe and exits non-zero if either fails.
"""

import argparse
import os
import sys
from urllib.parse import urlsplit, urlunsplit

import httpx
from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

# Neither endpoint is named in PLAN.md; these defaults are guesses. Override
# them with --path / --ws-path until switch-core answers. See docs/setup-vm.md.
DEFAULT_PATH = "/v1/health"
DEFAULT_WS_PATH = "/v1/ws"

TIMEOUT_SECONDS = 10.0


def normalize_base(raw: str) -> str:
    """Return the base URL with a scheme, no trailing slash, no query."""
    raw = raw.strip()
    if "://" not in raw:
        raw = f"https://{raw}"
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"}:
        raise ValueError(f"base URL must be http or https, got {parts.scheme!r}")
    if not parts.netloc:
        raise ValueError(f"base URL has no host: {raw!r}")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def join_url(base: str, path: str) -> str:
    """Join a base URL and an absolute path without doubling the slash."""
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def to_ws_url(url: str) -> str:
    """Map an http(s) URL to its ws(s) equivalent."""
    parts = urlsplit(url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    return urlunsplit((scheme, parts.netloc, parts.path, parts.query, ""))


def check_http(url: str) -> bool:
    """GET the URL; any status below 400 passes, so this checks reachability."""
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        print(f"FAIL GET {url}\n     {type(exc).__name__}: {exc}")
        return False
    body = " ".join(response.text.split())[:200]
    ok = response.status_code < 400
    print(f"{'PASS' if ok else 'FAIL'} GET {url}\n     HTTP {response.status_code} {body}")
    return ok


def check_ws(url: str) -> bool:
    """Open the WebSocket upgrade, then close immediately."""
    try:
        with connect(url, open_timeout=TIMEOUT_SECONDS):
            pass
    except (OSError, ValueError, WebSocketException) as exc:
        print(f"FAIL WS  {url}\n     {type(exc).__name__}: {exc}")
        return False
    print(f"PASS WS  {url}\n     upgrade accepted")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe switch-core over HTTPS and WebSockets.")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SWITCH_URL", ""),
        help="server base URL, e.g. https://<laptop>.<tailnet>.ts.net (default: $SWITCH_URL)",
    )
    parser.add_argument(
        "--path",
        default=DEFAULT_PATH,
        help=f"HTTP path for the GET probe (default: {DEFAULT_PATH}, may be wrong)",
    )
    parser.add_argument(
        "--ws-path",
        default=DEFAULT_WS_PATH,
        help=f"path for the WebSocket upgrade (default: {DEFAULT_WS_PATH}, may be wrong)",
    )
    args = parser.parse_args(argv)

    if not args.base_url:
        parser.error("pass --base-url or set SWITCH_URL")

    try:
        base = normalize_base(args.base_url)
    except ValueError as exc:
        parser.error(str(exc))

    http_url = join_url(base, args.path)
    ws_url = to_ws_url(join_url(base, args.ws_path))

    print(f"switch-core probe: {base}")
    results = [check_http(http_url), check_ws(ws_url)]
    print("RESULT: pass" if all(results) else "RESULT: fail")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
