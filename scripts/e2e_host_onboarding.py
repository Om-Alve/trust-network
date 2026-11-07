#!/usr/bin/env python3
"""Run the shared-host onboarding E2E scenarios and save a report artifact.

Run from the repository root:

    uv run python scripts/e2e_host_onboarding.py

Every scenario uses real HTTP: a threaded fake Switch Gateway and the real
threaded host server, with temporary config, invite database and servers. The
report and per-scenario state are written under ``data/host-e2e-<stamp>/``.
No user configuration or external service is used.
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from host_flows import SCENARIOS, HostHarness


def config_summary(config: dict) -> dict:
    """What the scenario needed, with every credential removed."""
    people = {
        person: {
            "email": record.get("email"),
            "switch_user_id": record.get("switch_user_id"),
            "registration_key_env": record.get("registration_key_env"),
            "has_registration_key": bool(record.get("registration_key")),
        }
        for person, record in sorted(config.get("people", {}).items())
    }
    return {
        "switch_url": config.get("switch_url"),
        "public_url": config.get("public_url"),
        "bind": config.get("bind"),
        "port": config.get("port"),
        "identity": config.get("identity"),
        "gateway_email": config.get("gateway", {}).get("email"),
        "people": people,
    }


def gateway_summary(gateway) -> dict:
    return {
        "url": gateway.url,
        "created_users": [user["email"] for user in gateway.created_users],
        "created_keys": [
            {"email": record["email"], "id": record["id"]} for record in gateway.created_keys
        ],
        "calls": [
            {"method": method, "path": path, "session": session}
            for method, path, session in gateway.calls
        ],
    }


def run() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = Path("data") / f"host-e2e-{stamp}"
    output.mkdir(parents=True)

    report: dict[str, dict] = {}
    lines: list[str] = []
    for name, scenario in SCENARIOS.items():
        directory = output / name
        directory.mkdir()
        try:
            with HostHarness(directory) as harness:
                details = scenario(harness)
                state = {
                    "status": "PASS",
                    "details": details,
                    "config": config_summary(harness.config()),
                    "gateway": gateway_summary(harness.gateway),
                    "invites": harness.invite_rows(),
                    "redemptions": harness.redemption_count(),
                }
        except Exception:
            state = {
                "status": "FAIL",
                "error": traceback.format_exc(),
            }
        report[name] = state
        lines.append(f"{state['status']} {name}")
        (directory / "state.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2, default=list)
        )

    passed = sum(item["status"] == "PASS" for item in report.values())
    lines.append(f"{passed} PASS / {len(report) - passed} FAIL")
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=list)
    )
    text = "\n".join(lines) + "\n"
    (output / "summary.txt").write_text(text)
    print(text, end="")
    print(f"Artifacts: {output}")
    return 0 if passed == len(report) else 1


if __name__ == "__main__":
    sys.exit(run())
