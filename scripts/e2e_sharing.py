#!/usr/bin/env python3
"""Run the offline sharing scenarios and preserve repeatable artifacts.

Run from the repository root: uv run python scripts/e2e_sharing.py
Only the repository FakeSwitch harness is used: real gates, real policy, real
CLI handlers. Each scenario gets a fresh copy of the example profiles.

Artifacts land in ``data/scenarios-sharing-<timestamp>``: one
``transcript.json`` per scenario (including failures and the owner-local
trust/ledger files) and a ``summary.txt``.
"""

import asyncio
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from pytest import MonkeyPatch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from sharing_flows import SCENARIOS  # noqa: E402


async def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = Path("data") / f"scenarios-sharing-{stamp}"
    output.mkdir(parents=True)
    summary: list[str] = []
    for scenario in SCENARIOS:
        directory = output / scenario.__name__
        directory.mkdir()
        with MonkeyPatch.context() as patch:
            try:
                report = await scenario(directory / "profiles", patch)
            except Exception:
                status, error = "FAIL", traceback.format_exc()
                report = {"checks": {}, "transcript": {}, "files": {}}
            else:
                status, error = "PASS", None
            artifact = dict(report)
            artifact.update(
                scenario=scenario.__name__,
                status=status,
                error=error,
            )
            (directory / "transcript.json").write_text(
                json.dumps(artifact, ensure_ascii=False, indent=2, default=list)
            )
            summary.append(f"{status} {scenario.__name__}")
    passed = sum(line.startswith("PASS") for line in summary)
    summary.append(f"{passed} PASS / {len(summary) - passed} FAIL")
    text = "\n".join(summary) + "\n"
    (output / "summary.txt").write_text(text)
    print(text, end="")
    print(f"Artifacts: {output}")
    return 0 if passed == len(SCENARIOS) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
