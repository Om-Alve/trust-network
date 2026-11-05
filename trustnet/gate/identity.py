"""Trusted identity sources with bounded freshness and fail-closed refresh."""

import json
import logging
import os
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

from trustnet.gate.policy import Identity, SenderKind


def read_identities(path):
    return decode(path.read_bytes())


def decode(raw):
    return {
        key: Identity(SenderKind(value["kind"]), value["id"], value.get("owner_id"))
        for key, value in json.loads(raw).items()
    }


def export_local(path):
    core = (
        Path.home()
        / "Library/Application Support/switchdash/local-switch-server/native/switch-core/0.31.0"
    )
    subprocess.run(
        [
            str(core / "venv/bin/python"),
            str(Path(__file__).resolve().parents[2] / "scripts/gate_identity_export.py"),
        ],
        check=True,
        timeout=15,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "TN_IDENTITY_MAP": str(path)},
    )
    return path.read_bytes()


class IdentitySource(dict):
    """Gate callback and map; unknown lookups refresh at most once per second."""

    def __init__(self, path, url=None):
        super().__init__()
        if url and not url.startswith("https://"):
            raise ValueError("Remote identities require HTTPS")
        self.path, self.url = path, url
        self.lock = threading.RLock()
        self.attempted = float("-inf")

    def refresh(self, interval=5):
        with self.lock:
            if time.monotonic() - self.attempted < interval:
                return
            self.attempted = time.monotonic()
            try:
                if self.url:
                    request = urllib.request.Request(
                        self.url,
                        headers={"Authorization": "Bearer " + os.environ["TN_IDENTITY_TOKEN"]},
                    )
                    with urllib.request.urlopen(request, timeout=5) as response:
                        raw = response.read(4_000_001)
                    if len(raw) > 4_000_000:
                        raise ValueError("Identity response too large")
                else:
                    raw = export_local(self.path)
                values = decode(raw)
                self.clear()
                self.update(values)
            except Exception:
                self.clear()
                logging.getLogger(__name__).warning("Identity refresh failed; gate stays silent")

    def __call__(self):
        self.refresh()
        return self

    def get(self, key, default=None):
        with self.lock:
            if key not in self:
                self.refresh(interval=1)
            return super().get(key, default)
