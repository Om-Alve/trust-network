"""Prove an installed wheel works outside the checkout (TN-03).

The failure this checks for: a wheel carries Python modules but not the share-card
template, the agent skill, the watcher prompt or the identity exporter, so every
those paths silently resolve relative to a repository that an installed copy
does not have.

The run builds a wheel, installs it into a fresh virtualenv outside the
checkout, and then, with ``PYTHONPATH`` unset and a working directory outside the
checkout:

1. imports ``trustnet`` from the installed virtualenv, not the checkout;
2. renders both demo share cards from copied fixture profiles;
3. starts ``tn --as priya wake`` as a real subprocess, types a line on stdin and
   checks the fake agent received the packaged skill;
4. drives ``Runner.poll`` with a fake watch report and checks the fake agent
   received the packaged watcher prompt;
5. materializes the identity exporter from the installed package;
6. runs a command with no ``TN_DATA_DIR`` and checks the error tells the person
   what to set instead of pointing at a repository path.

Run it with ``uv run python scripts/e2e_install.py``. Evidence is written to
``data/install-<stamp>/``; the temporary virtualenv and wheel build directory are
removed unless ``--keep-work`` is passed. Fixtures are copied, so the checkout's
``examples/`` is never written.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAMP = time.strftime("%Y%m%dT%H%M%S")
ARTIFACTS = ROOT / "data" / f"install-{STAMP}"

SKILL_MARKER = "name: trust-network"
WATCH_MARKER = "Never answer a proposal or say yes for your person."
REPLY_MARKER = "E2E fake reply"

FAKE_AGENT = """\
import os
import pathlib
import sys

prompt = sys.stdin.read()
pathlib.Path(os.environ["TN_E2E_PROMPT"]).write_text(prompt)
print(%r)
""" % (REPLY_MARKER,)

RENDER_CARD = """\
import sys
from datetime import date
from trustnet.gate.brief import build_brief
from trustnet.gate.facts import load_profile, load_trust

friend, room = sys.argv[1], sys.argv[2]
profile, trust = load_profile("om"), load_trust("om")
text, _ = build_brief(
    profile, trust, friend, room, "something fun Sunday evening, not pricey",
    (date(2026, 11, 8), date(2026, 11, 9)),
)
print(text, end="")
"""

WATCHER_CHECK = """\
import asyncio
import contextlib
import io
import json
import os
from trustnet.tn import personal, wake

prompt_path = os.environ["TN_E2E_PROMPT"]
calls = 0


async def fake_watch(person):
    global calls
    # Stop once the turn has run: poll watches again after a settle delay and
    # after every turn, so the agent writing its prompt is the signal to end.
    if os.path.exists(prompt_path):
        raise SystemExit(0)
    calls += 1
    return {"inbox_unread": 1, "dm_updates": [], "calendar_pending": 0}


personal.watch = fake_watch


def invoke(reply):
    return (
        [os.environ["TN_E2E_PY"], os.environ["TN_E2E_AGENT"]],
        {"TN_E2E_PROMPT": prompt_path},
        lambda out: out,
    )


runner = wake.Runner("priya", invoke, "Priya's agent", every=0.01)
try:
    with contextlib.redirect_stdout(io.StringIO()):
        asyncio.run(runner.poll())
except SystemExit:
    pass
print(json.dumps({"watches": calls, "prompt": open(prompt_path, encoding="utf-8").read()}))
"""

IDENTITY_CHECK = """\
import json
import os
import pathlib
from trustnet.gate import identity

source = identity.identity_export_script()
target = identity.write_identity_export(pathlib.Path(os.environ["TN_E2E_SCRIPTS"]))
print(json.dumps({"path": str(target), "exists": target.is_file(), "bytes": len(source)}))
"""


class CheckFailed(RuntimeError):
    """One install check did not hold; the report keeps what ran."""


def run(cmd: list[str], *, cwd: Path, env: dict[str, str], timeout: float = 900) -> str:
    process = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    if process.returncode != 0:
        detail = (process.stderr or process.stdout).strip()[-2000:]
        raise CheckFailed(f"{' '.join(cmd)} exited {process.returncode}: {detail}")
    return process.stdout


def clean_env(work: Path, data_dir: Path | None) -> dict[str, str]:
    """A runtime environment with no checkout paths, and in particular no PYTHONPATH."""
    home = work / "home"
    home.mkdir(exist_ok=True)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "TMPDIR": str(work / "tmp"),
        "LANG": "en_US.UTF-8",
    }
    Path(env["TMPDIR"]).mkdir(exist_ok=True)
    if data_dir is not None:
        env["TN_DATA_DIR"] = str(data_dir)
    return env


def read_until(
    process: subprocess.Popen, marker: str, timeout: float = 120
) -> tuple[list[str], bool]:
    """Collect stdout lines until ``marker`` appears, the process exits, or time runs out."""
    lines: list[str] = []
    found: list[bool] = []
    received: queue.Queue[str | None] = queue.Queue()

    def reader() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            received.put(line)
        received.put(None)

    threading.Thread(target=reader, daemon=True).start()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            line = received.get(timeout=0.5)
        except queue.Empty:
            if process.poll() is not None:
                break
            continue
        if line is None:
            break
        lines.append(line)
        if marker in line:
            found.append(True)
            break
    return lines, bool(found)


def build_wheel(work: Path) -> Path:
    """Build the wheel from the checkout into the work directory."""
    dist = work / "dist"
    run(["uv", "build", "--wheel", "--out-dir", str(dist)], cwd=ROOT, env=dict(os.environ))
    wheels = sorted(dist.glob("*.whl"))
    if len(wheels) != 1:
        raise CheckFailed(f"expected one wheel in {dist}, found {[w.name for w in wheels]}")
    return wheels[0]


def make_venv(work: Path, wheel: Path) -> Path:
    """A fresh virtualenv outside the checkout with only the wheel installed."""
    venv = work / "venv"
    run(
        ["uv", "venv", "--python", "3.12", str(venv)],
        cwd=work,
        env=dict(os.environ),
    )
    python = venv / "bin" / "python"
    run(
        ["uv", "pip", "install", "--python", str(python), str(wheel)],
        cwd=work,
        env=dict(os.environ),
    )
    return venv


def copy_fixtures(work: Path) -> Path:
    """Copy the demo profiles out of the checkout; the originals stay untouched."""
    data = work / "profiles"
    for person in ("om", "rahul", "priya"):
        shutil.copytree(ROOT / "examples" / person, data / person)
    return data


def write_helpers(work: Path) -> None:
    (work / "fake_agent.py").write_text(FAKE_AGENT, encoding="utf-8")
    (work / "render_card.py").write_text(RENDER_CARD, encoding="utf-8")
    (work / "watcher_check.py").write_text(WATCHER_CHECK, encoding="utf-8")
    (work / "identity_check.py").write_text(IDENTITY_CHECK, encoding="utf-8")


def check_import(work: Path, env: dict[str, str], python: Path) -> dict:
    out = run(
        [
            str(python),
            "-c",
            "import trustnet, pathlib; print(pathlib.Path(trustnet.__file__).resolve())",
        ],
        cwd=work,
        env=env,
    )
    location = Path(out.strip())
    if ROOT in location.parents:
        raise CheckFailed(f"imported trustnet from the checkout: {location}")
    py = run([str(python), "--version"], cwd=work, env=env).strip()
    return {"module": str(location), "python": py}


def check_share_cards(work: Path, env: dict[str, str], python: Path) -> dict:
    cards = {}
    for friend, room in (("rahul", "dm-om-rahul-sun"), ("priya", "dm-om-priya-sun")):
        text = run(
            [str(python), str(work / "render_card.py"), friend, room],
            cwd=work,
            env=env,
        )
        (ARTIFACTS / f"share-card-{friend}.md").write_text(text, encoding="utf-8")
        if not text.startswith("Share card: guidance only"):
            raise CheckFailed(f"the {friend} share card did not use the packaged template")
        if "**diet**" not in text:
            raise CheckFailed(f"the {friend} share card lost the acquaintance fact")
        cards[friend] = text

    if "**wishlist**" not in cards["rahul"]:
        raise CheckFailed("the close-level share card lost the wishlist")
    if "**wishlist**" in cards["priya"]:
        raise CheckFailed("the friend-level share card leaked a close fact")
    for name, text in cards.items():
        if "address" in text.casefold():
            raise CheckFailed(f"the {name} share card mentions the private address")
    return {"rahul_bytes": len(cards["rahul"]), "priya_bytes": len(cards["priya"])}


def check_wake_cli(work: Path, env: dict[str, str], venv: Path) -> dict:
    """The real CLI path: stdin line -> Runner.turn -> fake agent -> printed reply."""
    prompt_path = work / "wake-prompt.txt"
    wake_env = {**env, "TN_E2E_PROMPT": str(prompt_path)}
    process = subprocess.Popen(
        [
            str(venv / "bin" / "tn"),
            "--as",
            "priya",
            "wake",
            "--cmd",
            f"{venv / 'bin' / 'python'} {work / 'fake_agent.py'}",
            "--every",
            "3600",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=work,
        env=wake_env,
    )
    try:
        assert process.stdin is not None
        process.stdin.write("plan something with om Sunday\n")
        process.stdin.flush()
        lines, found = read_until(process, REPLY_MARKER)
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=15)
        stderr = process.stderr.read() if process.stderr is not None else ""

    (ARTIFACTS / "wake-output.txt").write_text("".join(lines), encoding="utf-8")
    if stderr.strip():
        (ARTIFACTS / "wake-stderr.txt").write_text(stderr, encoding="utf-8")
    if not found:
        tail = stderr.strip()[-1000:] or "no stderr"
        raise CheckFailed(f"tn wake did not print the fake agent's reply: {tail}")
    prompt = prompt_path.read_text(encoding="utf-8")
    (ARTIFACTS / "wake-prompt.txt").write_text(prompt, encoding="utf-8")
    if SKILL_MARKER not in prompt:
        raise CheckFailed("the wake prompt did not carry the packaged skill")
    if "plan something with om Sunday" not in prompt:
        raise CheckFailed("the wake prompt did not carry the typed line")
    return {"reply_shown": True, "prompt_bytes": len(prompt)}


def check_watcher_prompt(work: Path, env: dict[str, str], python: Path) -> dict:
    """Runner.poll with a fake watch report must read the packaged watcher prompt."""
    prompt_path = work / "watcher-prompt.txt"
    check_env = {
        **env,
        "TN_E2E_PROMPT": str(prompt_path),
        "TN_E2E_PY": str(python),
        "TN_E2E_AGENT": str(work / "fake_agent.py"),
    }
    out = run([str(python), str(work / "watcher_check.py")], cwd=work, env=check_env)
    try:
        result = json.loads(out)
    except ValueError as exc:
        raise CheckFailed(f"the watcher check printed no JSON: {out.strip()[-1000:]}") from exc
    (ARTIFACTS / "watcher-prompt.txt").write_text(result["prompt"], encoding="utf-8")
    if WATCH_MARKER not in result["prompt"]:
        raise CheckFailed("the poll prompt did not carry the packaged watcher prompt")
    if "unread item" not in result["prompt"]:
        raise CheckFailed("the poll prompt did not carry the watch report")
    return {"watches": result["watches"], "prompt_bytes": len(result["prompt"])}


def check_identity_export(work: Path, env: dict[str, str], python: Path) -> dict:
    scripts = work / "scripts-out"
    out = run(
        [str(python), str(work / "identity_check.py")],
        cwd=work,
        env={**env, "TN_E2E_SCRIPTS": str(scripts)},
    )
    result = json.loads(out)
    (ARTIFACTS / "identity-export.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if not result["exists"]:
        raise CheckFailed("the identity exporter was not written")
    if ROOT in Path(result["path"]).parents:
        raise CheckFailed("the identity exporter was written into the checkout")
    if "asyncpg" not in (scripts / Path(result["path"]).name).read_text(encoding="utf-8"):
        raise CheckFailed("the materialized identity exporter is not the real script")
    return result


def check_no_data_dir(work: Path, venv: Path) -> dict:
    """No checkout and no TN_DATA_DIR: the error must tell the person what to set."""
    env = clean_env(work, None)
    process = subprocess.run(
        [str(venv / "bin" / "tn"), "--as", "om", "view-as", "rahul"],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    detail = (process.stdout + process.stderr).strip()
    (ARTIFACTS / "no-data-dir.txt").write_text(detail, encoding="utf-8")
    if process.returncode == 0:
        raise CheckFailed("a command with no data directory unexpectedly succeeded")
    if "TN_DATA_DIR" not in detail:
        raise CheckFailed(f"the no-data error does not name TN_DATA_DIR: {detail}")
    return {"exit": process.returncode, "detail": detail}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install the wheel outside the checkout.")
    parser.add_argument("--keep-work", action="store_true", help="keep the temp venv and wheel")
    args = parser.parse_args(argv)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="tn-install-e2e-", dir=tempfile.gettempdir()))
    report: dict = {"stamp": STAMP, "workdir": str(work), "checks": {}}
    failures: list[str] = []
    started = time.monotonic()

    try:
        wheel = build_wheel(work)
        report["wheel"] = wheel.name
        shutil.copy2(wheel, ARTIFACTS / wheel.name)
        venv = make_venv(work, wheel)
        data = copy_fixtures(work)
        write_helpers(work)
        env = clean_env(work, data)
        python = venv / "bin" / "python"

        checks = [
            ("import", lambda: check_import(work, env, python)),
            ("share_cards", lambda: check_share_cards(work, env, python)),
            ("wake_cli", lambda: check_wake_cli(work, env, venv)),
            ("watcher_prompt", lambda: check_watcher_prompt(work, env, python)),
            ("identity_export", lambda: check_identity_export(work, env, python)),
            ("no_data_dir", lambda: check_no_data_dir(work, venv)),
        ]
        for name, check in checks:
            try:
                report["checks"][name] = {"ok": True, "detail": check()}
                print(f"ok   {name}")
            except CheckFailed as exc:
                report["checks"][name] = {"ok": False, "detail": str(exc)}
                failures.append(name)
                print(f"FAIL {name}: {exc}")
    except (CheckFailed, OSError, subprocess.SubprocessError) as exc:
        report["checks"]["setup"] = {"ok": False, "detail": str(exc)}
        failures.append("setup")
        print(f"FAIL setup: {exc}")

    report["ok"] = not failures
    report["seconds"] = round(time.monotonic() - started, 1)
    (ARTIFACTS / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Installed-wheel E2E",
        "",
        f"- wheel: `{report.get('wheel', 'not built')}`",
        f"- workdir: `{work}`",
        f"- result: {'PASS' if report['ok'] else 'FAIL: ' + ', '.join(failures)}",
        f"- seconds: {report['seconds']}",
        "",
    ]
    for name, check in report["checks"].items():
        lines.append(f"## {name}: {'ok' if check['ok'] else 'FAIL'}")
        detail = check["detail"]
        lines.append(
            f"```\n{json.dumps(detail, indent=2) if not isinstance(detail, str) else detail}\n```"
        )
        lines.append("")
    (ARTIFACTS / "report.md").write_text("\n".join(lines), encoding="utf-8")

    if not args.keep_work:
        shutil.rmtree(work, ignore_errors=True)
    print(f"report: {ARTIFACTS / 'report.md'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
