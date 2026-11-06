"""``tn wake``: run any CLI agent as a person's trust-network agent, in one terminal.

An agent framework only acts when it gets a message; nothing in Switch sends one
when the other side replies. Hermes covers that with a one-minute cron job. This
runner does the same for any agent that can (a) take a prompt on stdin and print
a reply, and (b) call the ``tn mcp`` tools: it polls ``tn watch`` and wakes the
agent on news, and it lets the person talk to their agent by typing.

    tn --as priya wake --agent codex
    tn --as priya wake --cmd "my-agent --stdin"     # any other framework

Each turn's prompt carries the person's persona (``examples/<person>/agent.md``
if present), the trust-network skill, the recent conversation with the person,
and what just happened. Agent sessions are not resumed, so a turn never depends
on a framework's own memory.

Ways this can go wrong, and what the runner does:
- an agent turn fails or times out → the error is shown, and that turn's news is
  carried into the next turn so it isn't lost (``watch`` moves its cursor anyway);
- the person types while a turn is running → turns run one at a time, in order;
- Switch is unreachable → a warning, and polling continues;
- two runners for one person would answer twice → a per-person lock file refuses
  the second;
- the agent has nothing for the person → it replies ``[SILENT]`` and nothing is
  printed.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import shlex
import sys
import tempfile
import threading
from pathlib import Path

from trustnet.gate.facts import resolve_data_dir
from trustnet.tn import personal

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "skills" / "trust-network" / "SKILL.md"
WATCH_PROMPT = REPO_ROOT / "scripts" / "hermes" / "tn-watch-prompt.md"
TURN_TIMEOUT = 300
TRANSCRIPT_LINES = 16

DIM, BOLD, CYAN, RESET = "\033[2m", "\033[1m", "\033[1;35m", "\033[0m"


def codex_command(person: str, model: str, workdir: Path, reply: Path) -> list[str]:
    """``codex exec`` with only the trust-network MCP server, tools pre-approved."""
    env = {
        key: os.environ[key]
        for key in ("SWITCH_URL", "TN_DATA_DIR", "TN_STATE_DIR")
        if os.environ.get(key)
    }
    for key in ("TN_DATA_DIR", "TN_STATE_DIR"):
        if key in env:
            env[key] = str(Path(env[key]).expanduser().resolve())
    tn = Path(sys.executable).with_name("tn")
    table = ",".join(f"{k}={json.dumps(v)}" for k, v in env.items())
    return [
        "codex", "exec", "--skip-git-repo-check", "--ephemeral", "--ignore-user-config",
        "-m", model, "-s", "read-only", "-C", str(workdir),
        "-c", f"mcp_servers.trustnet.command={json.dumps(str(tn))}",
        "-c", f'mcp_servers.trustnet.args=["--as","{person}","mcp"]',
        "-c", 'mcp_servers.trustnet.default_tools_approval_mode="approve"',
        "-c", f"mcp_servers.trustnet.env={{{table}}}",
        "-o", str(reply), "-",
    ]  # fmt: skip


def describe(report: dict) -> str:
    """The same wake text the Hermes cron pre-check prints."""
    lines = []
    if report["inbox_unread"]:
        lines.append(
            f"{report['inbox_unread']} unread item(s) in your person's trust-network inbox."
        )
    for u in report["dm_updates"]:
        lines.append(f"New message in DM room {u['name']} (room id {u['room']}) from {u['from']}:")
        lines.append("> " + u["text"].replace("\n", "\n> "))
    return "\n".join(lines)


class Runner:
    def __init__(self, person: str, argv_for, label: str, every: float):
        self.person, self.argv_for, self.label, self.every = person, argv_for, label, every
        self.name = person.title()
        self.transcript: list[str] = []
        self.carry: list[str] = []
        self.turns = asyncio.Lock()
        persona = REPO_ROOT / "examples" / person / "agent.md"
        self.persona = persona.read_text() if persona.exists() else ""
        self.skill = SKILL.read_text()
        self.workdir = Path(tempfile.mkdtemp(prefix=f"tn-{person}-agent-"))

    def prompt(self, now: str) -> str:
        talk = "\n".join(self.transcript[-TRANSCRIPT_LINES:]) or "(nothing yet)"
        return (
            f"{self.persona}\n\n--- The trust-network skill ---\n{self.skill}\n\n"
            f"--- Recent conversation with {self.name} (newest last) ---\n{talk}\n\n"
            f"--- Now ---\n{now}\n\n"
            f"Use your trust-network tools as needed. Then reply with only your message to "
            f"{self.name}: one or two short lines, with any reference (Q1, P1, A1) they need. "
            f"If nothing needs {self.name}'s attention, reply with only [SILENT]."
        )

    async def turn(self, now: str) -> None:
        async with self.turns:
            if self.carry:
                now = "\n\n".join([*self.carry, now])
                self.carry = []
            reply = self.workdir / "reply.txt"
            reply.unlink(missing_ok=True)
            argv, via_file = self.argv_for(reply)
            try:
                process = await asyncio.create_subprocess_exec(
                    *argv,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.workdir,
                )
                out, err = await asyncio.wait_for(
                    process.communicate(self.prompt(now).encode()), TURN_TIMEOUT
                )
            except (OSError, TimeoutError) as exc:
                self.carry.append(now)
                self.note(
                    f"agent turn failed ({type(exc).__name__}); will retry with the next turn"
                )
                return
            if process.returncode != 0:
                self.carry.append(now)
                tail = err.decode(errors="replace").strip().splitlines()[-1:] or ["no output"]
                self.note(f"agent exited {process.returncode}: {tail[0][:160]}")
                return
            text = (reply.read_text() if via_file and reply.exists() else out.decode()).strip()
            if not text or text == "[SILENT]":
                return
            self.transcript.append(f"{self.label}: {text}")
            print(f"\n{CYAN}{self.label} ›{RESET} {text}\n", flush=True)

    def note(self, text: str) -> None:
        print(f"{DIM}  · {text}{RESET}", flush=True)

    async def poll(self) -> None:
        while True:
            try:
                report = await personal.watch(self.person)
            except Exception as exc:  # Switch down, network blip: keep polling
                self.note(f"watch failed: {type(exc).__name__}")
            else:
                news = describe(report)
                if news:
                    self.note("news from trust-network; waking the agent")
                    await self.turn(news + "\n\n" + WATCH_PROMPT.read_text())
            await asyncio.sleep(self.every)

    async def listen(self) -> None:
        loop = asyncio.get_running_loop()
        lines: asyncio.Queue[str | None] = asyncio.Queue()

        def read() -> None:
            for line in sys.stdin:
                loop.call_soon_threadsafe(lines.put_nowait, line.rstrip("\n"))
            loop.call_soon_threadsafe(lines.put_nowait, None)

        threading.Thread(target=read, daemon=True).start()
        while (line := await lines.get()) is not None:
            if not line.strip():
                continue
            self.transcript.append(f"{self.name}: {line.strip()}")
            await self.turn(f"{self.name} says: {line.strip()}")
        await asyncio.Event().wait()  # stdin closed: keep polling

    async def run(self) -> None:
        print(
            f"{BOLD}{self.label}{RESET} {DIM}— trust-network agent for {self.name}. "
            f"Type to talk to it; it also wakes on news.{RESET}\n",
            flush=True,
        )
        await asyncio.gather(self.poll(), self.listen())


def lock(person: str):
    path = resolve_data_dir(person) / "wake.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit(f"tn wake is already running for {person}") from None
    return handle


def main(person: str, args) -> int:
    """Run the agent for ``person``; ``args`` has ``agent``/``cmd``, ``model``, ``every``."""
    handle = lock(person)  # noqa: F841 — held for the process lifetime
    if args.agent == "codex":
        label = f"{person.title()}'s agent (Codex)"

        def argv_for(reply):
            return codex_command(person, args.model, reply.parent, reply), True
    else:
        label = f"{person.title()}'s agent"

        def argv_for(reply):
            return shlex.split(args.cmd), False

    try:
        asyncio.run(Runner(person, argv_for, label, args.every).run())
    except KeyboardInterrupt:
        pass
    return 0
