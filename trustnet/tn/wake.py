"""``tn wake``: run any CLI agent as a person's trust-network agent, in one terminal.

An agent framework only acts when it gets a message; nothing in Switch sends one
when the other side replies. Hermes covers that with a one-minute cron job. This
runner does the same for any agent that can (a) take a prompt on stdin and print
a reply, and (b) call the ``tn mcp`` tools: it polls ``tn watch`` and wakes the
agent on news, and it lets the person talk to their agent by typing.

    tn --as priya wake --agent codex
    tn --as om wake --agent opencode                # DeepSeek through OpenCode
    tn --as om wake --agent hermes                  # the model Hermes is set up with
    tn --as priya wake --cmd "my-agent --stdin"     # any other framework

Each turn's prompt carries the person's persona (``agent.md`` in their data
directory, if present), the trust-network skill, the recent conversation with the
person, and what just happened. Agent sessions are not resumed, so a turn never
depends on a framework's own memory. The Codex preset keeps the user's own Codex
configuration, so MCP servers and connectors they already set up (a calendar, for
example) remain available; it only adds the trust-network server and tightens the
shell and web settings.

Ways this can go wrong, and what the runner does:
- an agent turn fails or times out → the error is shown, and that turn's news is
  carried into the next turn so it isn't lost (``watch`` moves its cursor anyway);
- the person types while a turn is running → turns run one at a time, in order;
- Switch is unreachable → a warning, and polling continues;
- two runners for one person would answer twice → a per-person lock file refuses
  the second;
- the agent has nothing for the person → it replies ``[SILENT]`` and nothing is
  printed;
- the Codex and OpenCode presets disable shell/file/web tools while keeping the
  person's configured MCP connectors available for calendar work. Those
  connectors are trusted tools. The Hermes preset keeps only its terminal and
  skills, because its Google Workspace skill is a script the terminal runs; a
  Hermes turn can therefore do anything the person's shell can.
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
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from trustnet import resources
from trustnet.gate.facts import resolve_data_dir
from trustnet.tn import personal

SKILL_TEXT = resources.read_text(resources.SKILL)
WATCH_PROMPT_TEXT = resources.read_text(resources.WATCH_PROMPT)
TURN_TIMEOUT = 300
TRANSCRIPT_LINES = 16

DIM, BOLD, CYAN, RESET = "\033[2m", "\033[1m", "\033[1;35m", "\033[0m"


def _mcp_env() -> dict[str, str]:
    """What the ``tn mcp`` server needs, with data paths made absolute."""
    env = {
        key: os.environ[key]
        for key in (
            "SWITCH_URL",
            "TN_DATA_DIR",
            "TN_STATE_DIR",
            "TN_CONFIG_DIR",
            "TN_TIMEZONE",
            "TN_CALENDAR_DELIVERY",
            "TN_OUTGOING",
        )
        if os.environ.get(key)
    }
    for key in ("TN_DATA_DIR", "TN_STATE_DIR", "TN_CONFIG_DIR"):
        if key in env:
            env[key] = str(Path(env[key]).expanduser().resolve())
    return env


def _tn() -> str:
    return str(Path(sys.executable).with_name("tn"))


#: ``(argv, extra_env, read)`` for one agent turn; ``read(stdout)`` gives the reply.
Command = tuple[list[str], dict[str, str], Callable[[str], str]]


def codex_command(person: str, model: str, reply: Path) -> Command:
    """``codex exec`` with trust-network added to the user's own configuration.

    ``--ignore-user-config`` used to isolate the turn, but it also removed every
    MCP server and connector the person had configured, including their calendar.
    The runner now loads the normal Codex config and only overrides the
    trust-network server, its tool approval, the shell and web search.
    """
    table = ",".join(f"{k}={json.dumps(v)}" for k, v in _mcp_env().items())
    argv = [
        "codex", "exec", "--skip-git-repo-check", "--ephemeral",
        "-m", model, "-s", "read-only", "-C", str(reply.parent),
        "-c", "features.shell_tool=false", "-c", 'web_search="disabled"',
        "-c", f"mcp_servers.trust-network.command={json.dumps(_tn())}",
        "-c", f'mcp_servers.trust-network.args=["--as","{person}","mcp"]',
        "-c", 'mcp_servers.trust-network.default_tools_approval_mode="approve"',
        "-c", f"mcp_servers.trust-network.env={{{table}}}",
        "-o", str(reply), "-",
    ]  # fmt: skip
    return argv, {}, lambda _out: reply.read_text() if reply.exists() else ""


#: OpenCode's own tools an agent here must not have: it reaches its person only
#: through the gate, never through the shell, files or the web.
OPENCODE_DENY = (
    "shell", "bash", "read", "edit", "write", "glob", "grep", "list", "patch",
    "webfetch", "websearch", "task", "external_directory", "skill", "lsp",
)  # fmt: skip


def opencode_command(person: str, model: str, reply: Path) -> Command:
    """Overlay the trust-network entry while retaining the user's connectors."""
    workdir = reply.parent
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "opencode.json").write_text(
        json.dumps(
            {
                "$schema": "https://opencode.ai/config.json",
                "permission": {"*": "allow", **{tool: "deny" for tool in OPENCODE_DENY}},
                "mcp": {
                    "trust-network": {
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
    return argv, {}, opencode_reply


def opencode_reply(stdout: str) -> str:
    """The text of the last assistant message in ``opencode run --format json`` output.

    A line that is not a JSON object, or a text event with no object part, is
    skipped: a CLI that emits a log line or ``null`` must not crash a turn.
    """
    parts: dict[str, list[str]] = {}
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or event.get("type") != "text":
            continue
        part = event.get("part")
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if isinstance(text, str) and text:
            parts.setdefault(str(part.get("messageID", "")), []).append(text)
    return "".join(list(parts.values())[-1]) if parts else ""


#: Hermes reads managed-scope config from here; it outranks ~/.hermes/config.yaml.
HERMES_MANAGED_DEFAULT = Path("/etc/hermes")


def hermes_command(person: str, model: str | None, reply: Path) -> Command:
    """``hermes chat`` with trust-network layered over the user's own Hermes.

    Hermes merges its managed scope (``HERMES_MANAGED_DIR``) over
    ``~/.hermes/config.yaml`` key by key, so this turn adds one MCP server and
    narrows the toolsets while the person's home, Google credentials, skills
    and other MCP servers stay where they are. The calendar skill runs scripts,
    so unlike the Codex and OpenCode presets the terminal stays enabled.
    """
    if os.environ.get("HERMES_MANAGED_DIR") or HERMES_MANAGED_DEFAULT.is_dir():
        raise RuntimeError(
            "A Hermes managed scope is already configured; tn wake will not replace "
            "administrator policy. Add trust-network to it and use --cmd instead."
        )
    overlay = reply.parent / "hermes-managed"
    overlay.mkdir(parents=True, exist_ok=True)
    server = {"command": _tn(), "args": ["--as", person, "mcp"], "env": _mcp_env()}
    (overlay / "config.yaml").write_text(
        json.dumps(
            {
                # Hermes builds the tool list once discovery ends or this bound passes.
                "mcp_discovery_timeout": 60,
                "platform_toolsets": {"cli": ["terminal", "skills"]},
                "mcp_servers": {"trust-network": server},
            }
        )
    )
    # Hermes takes a one-shot prompt only as an argument; the runner writes it to stdin.
    script = 'exec hermes chat -Q --source tool "$@" -q "$(cat)"'
    argv = ["/bin/sh", "-c", script, "hermes", *(["-m", model] if model else [])]
    return argv, {"HERMES_MANAGED_DIR": str(overlay)}, lambda out: out


class Preset(NamedTuple):
    label: str
    #: ``None`` keeps the model the person configured in that agent.
    model: str | None
    command: Callable[[str, str | None, Path], Command]


PRESETS = {
    "codex": Preset("Codex", "gpt-6.1-sol", codex_command),
    "opencode": Preset("OpenCode", "opencode-go/deepseek-v4.1-flash", opencode_command),
    "hermes": Preset("Hermes", None, hermes_command),
}


def describe(report: dict) -> str:
    """The same wake text the Hermes cron pre-check prints."""
    lines = []
    if report.get("calendar_pending"):
        lines.append(
            f"{report['calendar_pending']} approved calendar operation(s) need delivery. Call calendar_tasks and use your existing calendar tools."
        )
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
        persona = resolve_data_dir(person) / "agent.md"
        self.persona = persona.read_text() if persona.exists() else ""
        self.skill = SKILL_TEXT
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
                    env={**os.environ, **_mcp_env(), **extra_env},
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
                    await self.turn(news + "\n\n" + WATCH_PROMPT_TEXT)
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


def invoker(person: str, agent: str | None, model: str | None = None, cmd: str | None = None):
    """``(invoke, label)`` for an agent in ``PRESETS`` or any ``cmd``."""
    if agent is None:
        return (lambda reply: (shlex.split(cmd), {}, lambda out: out)), f"{person.title()}'s agent"
    preset = PRESETS[agent]
    model = model or preset.model
    label = f"{person.title()}'s agent ({preset.label})"
    return (lambda reply: preset.command(person, model, reply)), label


def main(person: str, args) -> int:
    """Run the agent for ``person``; ``args`` has ``agent``/``cmd``, ``model``, ``every``."""
    handle = lock(person)  # noqa: F841 — held for the process lifetime
    invoke, label = invoker(person, args.agent, args.model, args.cmd)
    try:
        asyncio.run(Runner(person, invoke, label, args.every).run())
    except KeyboardInterrupt:
        pass
    return 0
