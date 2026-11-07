"""Run product acceptance scenarios and save their state and transcripts."""

import asyncio
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from pytest import MonkeyPatch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from planning_flows import Planning  # noqa: E402
from product_flows import SCENARIOS  # noqa: E402


async def main():
    output = Path("data") / (
        "product-e2e-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    )
    output.mkdir(parents=True)
    summary = []
    for scenario in SCENARIOS:
        directory = output / scenario.__name__
        with MonkeyPatch.context() as patch:
            harness = Planning(directory / "profiles", patch)
            await harness.setup()
            try:
                await scenario(harness)
                status, error = "PASS", None
            except Exception:
                status, error = "FAIL", traceback.format_exc()
            artifact = {**harness.snapshot(), "status": status, "error": error}
            artifact["calendar_jobs"] = {
                p: __import__("trustnet.gate.calendar_jobs", fromlist=["pending"]).pending(p)
                for p in harness.clients
            }
            (directory / "transcript.json").write_text(json.dumps(artifact, indent=2, default=str))
            summary.append(f"{status} {scenario.__name__}")
    text = "\n".join(summary) + "\n"
    (output / "summary.txt").write_text(text)
    print(text + f"Artifacts: {output}")
    return int(any(s.startswith("FAIL") for s in summary))


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
