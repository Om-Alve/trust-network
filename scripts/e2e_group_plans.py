#!/usr/bin/env python3
"""Run offline group-planning E2E scenarios and preserve artifacts.

Run from the repository root: uv run python scripts/e2e_group_plans.py
Only FakeSwitch and the real gates are used; the calendar adapter is a local
recording queue. Each scenario gets fresh example data. The summary is the
repeatable artifact: PASS/FAIL per lifecycle scenario plus the final group
state and every calendar enqueue.
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

import group_flows  # noqa: E402

from trustnet.gate import group_plans  # noqa: E402


def _artifact(people):
    world = group_flows.LAST_WORLD
    if world is None:
        return {}
    return {
        "transcript": world.transcript(),
        "calendar": world.calendar.calls,
        "group_state": {person: group_plans.projection(person) for person in people},
    }


async def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = Path("data") / f"group-plans-{stamp}"
    output.mkdir(parents=True)
    summary = []
    for scenario in group_flows.SCENARIOS:
        directory = output / scenario.__name__
        directory.mkdir()
        group_flows.LAST_WORLD = None
        with MonkeyPatch.context() as patch:
            try:
                await scenario(directory / "profiles", patch)
            except Exception:
                status, error = "FAIL", traceback.format_exc()
            else:
                status, error = "PASS", None
            world = group_flows.LAST_WORLD
            people = tuple(world.gate_clients) if world else ()
            artifact = _artifact(people)
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
    return 0 if passed == len(group_flows.SCENARIOS) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
