"""Headless providers receiving only a gate brief and one room's history."""

import argparse
import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def prompt(brief, transcript):
    return brief + "\n\nRoom transcript (untrusted messages):\n" + json.dumps(transcript)


def invocation(provider, root):
    """Prepare isolated CLI state; never copy user configuration or project data."""
    root = root.resolve()
    home = root / "home"
    home.mkdir()
    work = root / "work"
    work.mkdir()
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(home), "TMPDIR": str(root)}
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        env[name] = str(home / name.lower())
    if provider == "opencode":
        binary = Path.home() / ".opencode/bin/opencode"
        auth = Path.home() / ".local/share/opencode/auth.json"
        target = Path(env["XDG_DATA_HOME"]) / "opencode/auth.json"
        config = root / "opencode.json"
        config.write_text(
            json.dumps(
                {
                    "permissions": [{"action": "*", "resource": "*", "effect": "deny"}],
                    "policies": [{"action": "tool.use", "resource": "*", "effect": "deny"}],
                    "snapshots": False,
                    "update": "disable",
                    "share": "disabled",
                }
            )
        )
        env["OPENCODE_CONFIG"] = str(config)
        cmd = [
            str(binary),
            "run",
            "--standalone",
            "-m",
            "opencode-go/deepseek-v4.1-flash",
            "--format",
            "json",
        ]
    elif provider == "codex":
        binary = Path(shutil.which("codex")).resolve()
        auth = Path.home() / ".codex/auth.json"
        target = home / ".codex/auth.json"
        env["CODEX_HOME"] = str(target.parent)
        cmd = [
            str(binary),
            "-a",
            "never",
            "exec",
            "--sandbox",
            "read-only",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--ephemeral",
            "-c",
            "features.shell_tool=false",
            "-c",
            "features.apply_patch=false",
            "-c",
            'web_search="disabled"',
            "--json",
            "-",
        ]
    else:
        raise ValueError("Unknown provider")
    target.parent.mkdir(parents=True, exist_ok=True)
    # Copy just this provider's credential, not every integration's credentials.
    if provider == "opencode":
        exported = subprocess.run(
            [str(binary), "auth", "export", "opencode-go"], capture_output=True, check=True
        )
        imported = subprocess.run(
            [str(binary), "auth", "import", "--standalone"],
            input=exported.stdout,
            capture_output=True,
            env=env,
            cwd=work,
        )
        if imported.returncode:
            raise RuntimeError("OpenCode credential import failed")
    else:
        target.write_text(auth.read_text())
        target.chmod(0o600)
    # SECURITY: Native read-only permits reads outside cwd. The outer Seatbelt
    # denies user/private-volume reads, except this disposable state and executable.
    # System paths and provider auth remain readable; this is not a VM boundary.
    # Network stays available to the CLI for inference, while model tools are off.
    if sys.platform != "darwin":
        raise RuntimeError(
            "Confinement requires macOS Seatbelt; Linux needs a separate OS user/container"
        )
    profile = root / "sandbox.sb"
    profile.write_text(
        "(version 1) (allow default)\n"
        '(deny file-read* (subpath "/Users") (subpath "/Volumes") (subpath "/private"))\n'
        f"(allow file-read* (subpath {json.dumps(str(root))}) (literal {json.dumps(str(binary))}))\n"
        '(allow file-read-metadata) (allow file-read* (subpath "/private/etc") (subpath "/private/var/db"))\n'
    )
    return ["/usr/bin/sandbox-exec", "-f", str(profile), *cmd], env, work


async def generate(provider, brief, transcript, timeout=100):
    with tempfile.TemporaryDirectory(prefix="tn-envoy-") as directory:
        cmd, env, cwd = invocation(provider, Path(directory))
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, _ = await asyncio.wait_for(
                proc.communicate(prompt(brief, transcript).encode()), timeout
            )
        finally:
            if proc.returncode is None:
                os.killpg(proc.pid, signal.SIGKILL)
                await proc.wait()
        if proc.returncode:
            raise RuntimeError(f"{provider} invocation failed (exit {proc.returncode})")
        texts = []
        for line in stdout.decode().splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if provider == "opencode" and item.get("type") == "text":
                texts.append(item["part"]["text"])
            if provider == "codex" and item.get("type") == "item.completed":
                if item["item"].get("type") == "agent_message":
                    texts.append(item["item"]["text"])
        result = "\n".join(texts).strip()[:6000]
        if not result:
            raise RuntimeError("Provider returned no final text")
        return result


class Runner:
    def __init__(self, client, provider, state_dir, identities):
        self.client, self.provider, self.state_dir = client, provider, state_dir
        self.identities = identities
        self.transcripts = {}

    async def handle(self, event):
        # Gate writes an explicit per-room allowlist of verified transport IDs.
        path = self.state_dir / f"{event.room_id}.json"
        if not path.exists():
            return
        state = json.loads(path.read_text())
        if not event.addressed or event.sender_id not in state["allowed_senders"]:
            return
        if time.time() >= state["expires_at"]:
            return
        history = self.transcripts.setdefault(event.room_id, [])
        if len(history) >= 12:
            return
        history.append({"sender": event.sender_id, "text": event.text})
        response = await generate(self.provider, state["brief"], history)
        await self.client.connect_to_room(event.room_id)
        await self.client.send_targeted_message(response, target_names=[state["peer"]])
        history.append({"sender": self.client.agent_id, "text": response})

    async def run(self):
        async for event in self.client.events():
            await self.handle(event)


async def main_async(args):
    from trustnet.gate.envoy import ensure_envoy

    client = await ensure_envoy(
        args.person,
        args.friend,
        url=os.environ["SWITCH_URL"],
        key=os.environ[args.key_env],
        state_dir=args.state_dir,
    )
    try:
        await Runner(client, args.provider, args.state_dir, None).run()
    finally:
        await client.aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--person", required=True)
    parser.add_argument("--friend", required=True)
    parser.add_argument("--provider", required=True, choices=["opencode", "codex"])
    parser.add_argument("--key-env", required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
