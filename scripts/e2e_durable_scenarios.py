#!/usr/bin/env python3
"""Run offline durable planning flows and preserve transcripts, including failures.

Run from the repository root: uv run python scripts/e2e_durable_scenarios.py
Only FakeSwitch is used. Each scenario gets fresh example data and gates.
"""

import asyncio
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from pytest import MonkeyPatch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from durable_flows import SCENARIOS
from planning_flows import Planning  # noqa: E402


async def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = Path("data") / f"scenarios-durable-{stamp}"
    output.mkdir(parents=True)
    summary = []
    for scenario in SCENARIOS:
        directory = output / scenario.__name__
        directory.mkdir()
        with MonkeyPatch.context() as patch:
            harness = Planning(directory / "profiles", patch)
            try:
                await harness.setup()
                await scenario(harness)
            except Exception:
                status, error = "FAIL", traceback.format_exc()
            else:
                status, error = "PASS", None
            artifact = harness.snapshot()
            artifact["owner_files"] = {
                person: {
                    name: path.read_text()
                    for name in (
                        "calendar.ics",
                        "facts.yaml",
                        "trust.yaml",
                        "ledger.jsonl",
                        "fact-changes.json",
                    )
                    if (path := harness.root / person / name).exists()
                }
                for person in harness.clients
            }
            artifact.update(status=status, error=error)
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
