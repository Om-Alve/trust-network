"""Private local configuration shared by the CLI, MCP server and onboarding host."""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CALENDAR_DELIVERIES = ("agent", "ics")
WAKE_MODES = ("runner", "external")


def checked_timezone(value):
    """Return an IANA timezone name, or refuse it before it reaches a profile."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Use an IANA timezone such as Asia/Kolkata")
    name = value.strip()
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(
            f"Unknown timezone {name!r}; use an IANA name such as Asia/Kolkata"
        ) from None
    return name


def checked_calendar_delivery(value):
    if value not in CALENDAR_DELIVERIES:
        raise ValueError("Calendar delivery must be agent or ics")
    return value


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
    if url.port == 0:
        raise ValueError("Server ports must be between 1 and 65535")
    return value.rstrip("/")


def apply(settings=None, *, override=False):
    settings = read_json(config_dir() / "config.json") if settings is None else settings
    if not settings:
        return
    required = ("person", "switch_url", "registration_key", "data_dir", "state_dir")
    if any(not isinstance(settings.get(key), str) or not settings[key] for key in required):
        raise ValueError(
            "Connection configuration is incomplete; repair config.json or use a separate TN_CONFIG_DIR"
        )
    checked_url(settings["switch_url"])
    if settings.get("identity_url"):
        checked_url(settings["identity_url"])
        if not isinstance(settings.get("identity_token"), str) or not settings["identity_token"]:
            raise ValueError("The configured identity endpoint needs an access token")
    timezone = checked_timezone(settings["timezone"]) if settings.get("timezone") else None
    delivery = (
        checked_calendar_delivery(settings["calendar_delivery"])
        if settings.get("calendar_delivery")
        else None
    )
    wake = settings.get("wake")
    if wake is not None:
        if not isinstance(wake, dict) or wake.get("mode") not in WAKE_MODES:
            raise ValueError("The configured wake mode must be runner or external")
        if wake["mode"] == "runner":
            command = wake.get("command")
            if (
                not isinstance(command, list)
                or not command
                or any(not isinstance(part, str) or not part for part in command)
            ):
                raise ValueError("The configured wake runner needs a command")
        elif not isinstance(wake.get("external"), str) or not wake["external"].strip():
            raise ValueError("The configured external wake integration needs a description")
    values = {
        "TN_PERSON": settings["person"],
        "SWITCH_URL": settings["switch_url"],
        "TN_DATA_DIR": settings["data_dir"],
        "TN_STATE_DIR": settings["state_dir"],
        settings["person"].upper() + "_GATE_KEY": settings["registration_key"],
    }
    if timezone:
        values["TN_TIMEZONE"] = timezone
    if delivery:
        values["TN_CALENDAR_DELIVERY"] = delivery

    if settings.get("identity_url"):
        values.update(
            TN_IDENTITY_URL=settings["identity_url"], TN_IDENTITY_TOKEN=settings["identity_token"]
        )
    if not override and any(
        key in os.environ and os.environ[key] != value for key, value in values.items()
    ):
        raise ValueError(
            "Saved connection conflicts with environment variables; clear the old TN_, SWITCH_URL and registration-key variables before using this profile"
        )
    for key, value in values.items():
        if override or key not in os.environ:
            os.environ[key] = value
