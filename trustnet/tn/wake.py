"""``tn wake``: run any CLI agent as a person's trust-network agent, in one terminal.

An agent framework only acts when it gets a message; nothing in Switch sends one
when the other side replies. Hermes covers that with a one-minute cron job. This
runner does the same for any agent that can (a) take a prompt on stdin and print
a reply, and (b) call the ``tn mcp`` tools: it polls ``tn watch`` and wakes the
agent on news, and it lets the person talk to their agent by typing.

    tn --as priya wake --agent codex
    tn --as om wake --agent opencode                # DeepSeek through OpenCode
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
  printed;
- the agent could reach its person's files or the shell and act outside the gate
  → the presets run Codex without its shell tool and OpenCode on a private config
  that denies its shell, file and web tools; only the ``tn mcp`` tools remain.
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


def _mcp_env() -> dict[str, str]:
    """What the ``tn mcp`` server needs, with data paths made absolute."""
    env = {
        key: os.environ[key]
        for key in ("SWITCH_URL", "TN_DATA_DIR", "TN_STATE_DIR")
        if os.environ.get(key)
    }
    for key in ("TN_DATA_DIR", "TN_STATE_DIR"):
        if key in env:
            env[key] = str(Path(env[key]).expanduser().resolve())
    return env


def _tn() -> str:
    return str(Path(sys.executable).with_name("tn"))


def codex_command(person: str, model: str, workdir: Path, reply: Path) -> list[str]:
    """``codex exec`` with only the trust-network MCP server, tools pre-approved, no shell."""
    table = ",".join(f"{k}={json.dumps(v)}" for k, v in _mcp_env().items())
    return [
        "codex", "exec", "--skip-git-repo-check", "--ephemeral", "--ignore-user-config",
        "-m", model, "-s", "read-only", "-C", str(workdir),
        "-c", "features.shell_tool=false", "-c", 'web_search="disabled"',
        "-c", f"mcp_servers.trustnet.command={json.dumps(_tn())}",
        "-c", f'mcp_servers.trustnet.args=["--as","{person}","mcp"]',
        "-c", 'mcp_servers.trustnet.default_tools_approval_mode="approve"',
        "-c", f"mcp_servers.trustnet.env={{{table}}}",
        "-o", str(reply), "-",
    ]  # fmt: skip


#: OpenCode's own tools an agent here must not have: it reaches its person only
#: through the gate, never through the shell, files or the web.
OPENCODE_DENY = (
    "shell", "bash", "read", "edit", "write", "glob", "grep", "list", "patch",
    "webfetch", "websearch", "task", "external_directory", "skill", "lsp",
)  # fmt: skip


def opencode_command(person: str, model: str, workdir: Path) -> tuple[list[str], dict]:
    """``opencode run`` on a private config holding only the trust-network MCP server.

    ``XDG_CONFIG_HOME`` points at that config, so the user's global OpenCode config
    (other MCP servers, instructions) is not loaded; credentials stay where they are.
    """
    config = workdir / "config" / "opencode"
    config.mkdir(parents=True, exist_ok=True)
    (config / "opencode.json").write_text(
        json.dumps(
            {
                "$schema": "https://opencode.ai/config.json",
                "permission": {"*": "allow", **{tool: "deny" for tool in OPENCODE_DENY}},
                "mcp": {
                    "trustnet": {
                        "type": "local",
                        "command": [_tn(), "--as", person, "mcp"],
                        "environment": _mcp_env(),
                        "enabled": True,
                    }
                },
            }
        )
    )
    argv = ["opencode", "run", "--standalone", "--format", "json", "-m", model]
    return argv, {"XDG_CONFIG_HOME": str(workdir / "config")}


def opencode_reply(stdout: str) -> str:
    """The text of the last assistant message in ``opencode run --format json`` output."""
    parts: dict[str, list[str]] = {}
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        part = event.get("part") or {}
        if event.get("type") == "text" and part.get("text"):
            parts.setdefault(part.get("messageID", ""), []).append(part["text"])
    return "".join(list(parts.values())[-1]) if parts else ""


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
    def __init__(self, person: str, invoke, label: str, every: float, on_reply=None):
        """``invoke(reply_path)`` returns ``(argv, extra_env, read)``, where
        ``read(stdout)`` gives the agent's reply. ``on_reply(text)`` (optional) is
        called with each reply shown to the person."""
        self.person, self.invoke, self.label, self.every = person, invoke, label, every
        self.on_reply = on_reply
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
            argv, extra_env, read = self.invoke(reply)
            process = None
            try:
                process = await asyncio.create_subprocess_exec(
                    *argv,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.workdir,
                    env={**os.environ, **extra_env},
                )
                out, err = await asyncio.wait_for(
                    process.communicate(self.prompt(now).encode()), TURN_TIMEOUT
                )
            except (OSError, TimeoutError) as exc:
                if process is not None and process.returncode is None:
                    process.kill()  # a timed-out turn must not keep acting
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
            text = read(out.decode(errors="replace")).strip()
            if not text or text == "[SILENT]":
                return
            self.transcript.append(f"{self.label}: {text}")
            print(f"\n{CYAN}{self.label} ›{RESET} {text}\n", flush=True)
        if self.on_reply is not None:
            await self.on_reply(text)

    async def say(self, line: str) -> None:
        """The person says ``line`` to their agent (typed, or from a test harness)."""
        self.transcript.append(f"{self.name}: {line}")
        await self.turn(f"{self.name} says: {line}")

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
            if line.strip():
                await self.say(line.strip())
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


MODELS = {"codex": "gpt-6.1-sol", "opencode": "opencode-go/deepseek-v4.1-flash"}


def invoker(person: str, agent: str | None, model: str | None = None, cmd: str | None = None):
    """``(invoke, label)`` for a known agent CLI (``codex``, ``opencode``) or any ``cmd``."""
    if agent == "codex":
        model = model or MODELS[agent]

        def invoke(reply):
            argv = codex_command(person, model, reply.parent, reply)
            return argv, {}, lambda _out: reply.read_text() if reply.exists() else ""

        return invoke, f"{person.title()}'s agent (Codex)"
    if agent == "opencode":
        model = model or MODELS[agent]

        def invoke(reply):
            argv, env = opencode_command(person, model, reply.parent)
            return argv, env, opencode_reply

        return invoke, f"{person.title()}'s agent (OpenCode)"

    def invoke(reply):
        return shlex.split(cmd), {}, lambda out: out

    return invoke, f"{person.title()}'s agent"


def main(person: str, args) -> int:
    """Run the agent for ``person``; ``args`` has ``agent``/``cmd``, ``model``, ``every``."""
    handle = lock(person)  # noqa: F841 — held for the process lifetime
    invoke, label = invoker(person, args.agent, args.model, args.cmd)
    try:
        asyncio.run(Runner(person, invoke, label, args.every).run())
    except KeyboardInterrupt:
        pass
    return 0
