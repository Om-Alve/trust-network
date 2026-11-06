"""Private local configuration shared by the CLI, MCP server and onboarding host."""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def config_dir():
    if os.environ.get("TN_CONFIG_DIR"):
        return Path(os.environ["TN_CONFIG_DIR"]).expanduser().resolve()
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "trust-network"


def read_json(path):
    path = Path(path)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text())
    except (ValueError, OSError):
        raise ValueError(
            f"Cannot read {path.name}; repair this configuration or use a separate TN_CONFIG_DIR"
        ) from None
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def write_json(path, payload):
    from trustnet.gate.storage import atomic_write

    atomic_write(Path(path), json.dumps(payload, indent=2) + "\n")


def checked_url(value):
    url = urlsplit(value)
    local = url.hostname in {"localhost", "127.0.0.1", "::1"}
    if url.scheme != "https" and not (url.scheme == "http" and local):
        raise ValueError("Use HTTPS, or HTTP on localhost")
    if not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("Server addresses cannot contain credentials, queries or fragments")
    return value.rstrip("/")


def apply(settings=None, *, override=False):
    settings = read_json(config_dir() / "config.json") if settings is None else settings
    if not settings:
        return
    values = {
        "TN_PERSON": settings["person"],
        "SWITCH_URL": settings["switch_url"],
        "TN_DATA_DIR": settings["data_dir"],
        "TN_STATE_DIR": settings["state_dir"],
        settings["person"].upper() + "_GATE_KEY": settings["registration_key"],
    }
    if settings.get("identity_url"):
        values.update(
            TN_IDENTITY_URL=settings["identity_url"], TN_IDENTITY_TOKEN=settings["identity_token"]
        )
    for key, value in values.items():
        if override or key not in os.environ:
            os.environ[key] = value
