"""Live acceptance: fresh profiles, bootstrap, Scene 1, reset, Scene 1 again.

Run: PYTHONPATH=. uv run python tests/e2e_demo_bootstrap.py.
Requires the VM Rahul service and any local gates stopped. Artifacts retain
both consent records, transcripts, ledgers and calendars. Exercises reset of
real completed state, reuse of credentials and preservation of fixture bytes.
"""

import asyncio
import hashlib
import os
import shutil
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

from scripts import e2e_scene1
from scripts.switch_users import read_env


def run():
    root = Path(f"data/phase22-{time.time_ns()}").resolve()
    root.mkdir(parents=True)
    fixtures = {
        Path(name): hashlib.sha256(Path(name).read_bytes()).hexdigest()
        for name in subprocess.check_output(["git", "ls-files", "examples"], text=True).splitlines()
    }
    credentials = Path("data/day0-state.json").read_bytes()
    env = {
        **os.environ,
        **read_env(Path(".env")),
        "SWITCH_URL": "http://127.0.0.1:53330",
        "TN_DATA_DIR": str(root),
    }
    env.pop("TN_IDENTITY_URL", None)
    os.environ.update(env)
    os.environ.pop("TN_IDENTITY_URL", None)
    subprocess.run(
        ["uv", "run", "python", "-m", "scripts.demo_up", "--one-machine", "--data-dir", str(root)],
        check=True,
        env=env,
    )
    original_path = Path

    def scene_path(value):
        return root if str(value).startswith("data/scene1-") else original_path(value)

    for take in (1, 2):
        # The existing scene owns Om/Rahul gates. Priya runs concurrently locally.
        with (root / f"priya-{take}.log").open("w") as log:
            priya = subprocess.Popen(
                [
                    "uv",
                    "run",
                    "python",
                    "-m",
                    "trustnet.gate",
                    "--person",
                    "priya",
                    "--key-env",
                    "PRIYA_GATE_KEY",
                ],
                env=env,
                stdout=log,
                stderr=log,
            )
            try:
                with (
                    patch.object(e2e_scene1, "Path", scene_path),
                    patch.object(e2e_scene1.shutil, "copytree"),
                    patch.object(e2e_scene1, "read_env", lambda _: env),
                    patch.object(e2e_scene1.os, "environ", os.environ),
                ):
                    # Existing main calls mkdir without exist_ok.
                    original_mkdir = Path.mkdir

                    def mkdir(path, *args, **kwargs):
                        kwargs["exist_ok"] = True
                        return original_mkdir(path, *args, **kwargs)

                    with patch.object(Path, "mkdir", mkdir):
                        asyncio.run(e2e_scene1.main())
                shutil.copyfile(root / "artifact.json", root / f"scene1-take{take}.json")
                assert priya.poll() is None
            finally:
                priya.terminate()
                priya.wait(timeout=15)
        subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "scripts.demo_reset",
                "--one-machine",
                "--data-dir",
                str(root),
            ],
            check=True,
            env=env,
        )
        assert not (root / "om/coordination.json").exists()
        assert (root / "om/calendar.ics").read_bytes() == Path(
            "examples/om/calendar.ics"
        ).read_bytes()
    assert Path("data/day0-state.json").read_bytes() == credentials
    assert all(
        hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in fixtures.items()
    )
    print("PASS bootstrap/reset/replay:", root)


if __name__ == "__main__":
    run()
