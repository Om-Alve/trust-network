"""Live acceptance with real CLI agents, MCP, Switch, gates and local ICS files.

Failure cases, before implementation:
- registered identities resolve in fixtures but not against the real identity DB;
- a real agent cannot load or use the installed MCP entry;
- the agent invents consent, or one vote writes a calendar event;
- the peer cannot join/read/post in the real group room;
- owner yeses bind to different revisions, or confirmation reaches only one gate;
- a reported calendar write is missing, different, or duplicated in the actual file;
- a consumed inbox strands pending calendar work;
- credentials or unrelated user data appear in the public report.

Creates separate test accounts and private profiles. Never resets existing demo
identities or changes personal calendars. Calendars here are real disposable ICS
files, not Google/Outlook. Model output and tool traces are kept in the private
artifact directory. Requires the local Switch Console and signed-in agent CLIs.

Run: uv run python -m scripts.e2a_real_agents
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from icalendar import Calendar

from scripts.switch_users import CONSOLE_ENV, read_env
from trustnet.gate import calendar_jobs, group_plans
from trustnet.gate.facts import Level, load_trust, save_trust
from trustnet.tn import personal, wake

ROOT = Path(__file__).resolve().parents[1]
PROXY = """import json, pathlib, subprocess, sys
request=json.loads(pathlib.Path(sys.argv[1]).read_text())
try:
 result=subprocess.run(request["argv"], input=sys.stdin.buffer.read(), capture_output=True, timeout=180)
except subprocess.TimeoutExpired as exc:
 pathlib.Path(request["trace"]+".stdout").write_bytes(exc.stdout or b"")
 pathlib.Path(request["trace"]+".stderr").write_bytes(exc.stderr or b"")
 raise
pathlib.Path(request["trace"]+".stdout").write_bytes(result.stdout)
pathlib.Path(request["trace"]+".stderr").write_bytes(result.stderr)
sys.stdout.buffer.write(result.stdout)
sys.stderr.buffer.write(result.stderr)
sys.exit(result.returncode)
"""


@contextmanager
def environment(values):
    previous = dict(os.environ)
    os.environ.clear()
    os.environ.update(values)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(previous)


async def cli(env, *args):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "trustnet.tn.cli",
        "--json",
        *args,
        env=env,
        cwd=ROOT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await asyncio.wait_for(process.communicate(), 90)
    if process.returncode:
        raise RuntimeError(f"tn {args[0]} exited {process.returncode}: {err.decode()[-500:]}")
    return json.loads(out)


def provision(url, names, output):
    console = read_env(CONSOLE_ENV)
    credentials = {}
    mapping = {}
    with httpx.Client(base_url=url + "/gateway", timeout=15) as admin:
        login = admin.post(
            "/auth/login",
            json={
                "email": console["GATEWAY_ADMIN_EMAIL"],
                "password": console["GATEWAY_ADMIN_PASSWORD"],
            },
        )
        login.raise_for_status()
        for person in names:
            email, password = person + "@switch.local", secrets.token_urlsafe(24)
            response = admin.post(
                "/users", json={"name": person, "email": email, "password": password}
            )
            response.raise_for_status()
            with httpx.Client(base_url=url + "/gateway", timeout=15) as owner:
                owner.post(
                    "/auth/login", json={"email": email, "password": password}
                ).raise_for_status()
                key = owner.post("/api-keys", json={"label": "isolated real-agent acceptance"})
                key.raise_for_status()
                credentials[person] = {
                    "password": password,
                    "email": email,
                    "registration_key": key.json()["key"],
                }
            mapping[email] = person
    path = output / "credentials.json"
    path.write_text(json.dumps(credentials))
    path.chmod(0o600)
    (output / "identity-people.json").write_text(json.dumps(mapping))
    return credentials


class Acceptance:
    def __init__(self, output, names, agents, base_env, start):
        self.output, self.names, self.agents = output, names, agents
        self.base_env, self.start = base_env, start
        self.envs, self.runners = {}, {}
        self.turns, self.steps = [], []
        self.proxy = output / "agent-proxy.py"
        self.proxy.write_text(PROXY)

    def snapshot(self):
        return {
            person: {
                "plans": group_plans.projection(person),
                "calendar_jobs": calendar_jobs.all_tasks(person),
                "calendar": (self.output / "profiles" / person / "calendar.ics").read_text(),
            }
            for person in self.names
        }

    async def setup(self, credentials):
        for index, person in enumerate(self.names):
            env = {
                **self.base_env,
                "TN_CONFIG_DIR": str(self.output / "config" / person),
                "E2A_GATE_KEY": credentials[person]["registration_key"],
                "TN_IDENTITY_PEOPLE": str(self.output / "identity-people.json"),
            }
            env.pop("TN_DATA_DIR", None)
            self.envs[person] = env
            result = await cli(
                env,
                "setup",
                "--name",
                person,
                "--server",
                self.base_env["SWITCH_URL"],
                "--key-env",
                "E2A_GATE_KEY",
                "--agent",
                "manual",
                "--consent",
                "via-agent",
                "--calendar-delivery",
                "agent",
                "--timezone",
                "Asia/Kolkata",
            )
            self.steps.append({"setup": person, "connection": result["readiness"]})
            settings = json.loads((Path(env["TN_CONFIG_DIR"]) / "config.json").read_text())
            # Keep one common data root while credentials and agent state stay separate.
            directory = Path(settings["data_dir"]) / person
            destination = self.output / "profiles" / person
            destination.parent.mkdir(exist_ok=True)
            destination.symlink_to(directory, target_is_directory=True)
            peer = self.names[1 - index]
            trust = load_trust(person)
            trust.grant(peer, Level.FRIEND)
            trust.consent_default = "via-agent"
            save_trust(trust, destination / "trust.yaml")
            (destination / "agent.md").write_text(
                f"You are the real personal agent for isolated test person {person}. Your peer is {peer}. "
                "This is an acceptance run. Use only trust-network tools and the disposable local ICS calendar. "
                "Do not use other connectors or message real contacts. Automatic conversation is authorized. "
                "The owner has NOT approved any plan until a later explicit message says so. "
                "For a confirmed create calendar task, call cal_add with the task uid as id, then "
                "calendar_report with provider local-ics and that exact event id. This test's destination "
                "is the local ICS calendar, so cal_add is the intended calendar tool here. "
                "Never report a write without a successful tool result. Do not create duplicates."
            )
            invoke, label = wake.invoker(person, self.agents[index])

            def traced(reply, invoke=invoke, person=person):
                argv, extra, reader = invoke(reply)
                count = sum(t["person"] == person for t in self.turns)
                trace = self.output / f"{person}-turn-{count}"
                request = trace.with_suffix(".request.json")
                request.write_text(json.dumps({"argv": argv, "trace": str(trace)}))
                return [sys.executable, str(self.proxy), str(request)], extra, reader

            with environment(env):
                from trustnet.tn.configuration import apply

                apply(override=True)
                self.runners[person] = wake.Runner(person, traced, label, every=2)

    async def turn(self, person, message=None):
        runner = self.runners[person]
        with environment(self.envs[person]):
            from trustnet.tn.configuration import apply

            apply(override=True)
            report = await personal.watch(person)
            news = wake.describe(report)
            instruction = message or (news + "\n\n" + wake.WATCH_PROMPT_TEXT)
            if not message and not news:
                return False
            self.turns.append({"person": person, "owner_message": message, "watch": report})
            before = len(runner.transcript)
            if message:
                await runner.say(message)
            else:
                await runner.turn(instruction)
        self.turns[-1]["transcript_delta"] = runner.transcript[before:]
        (self.output / "progress.json").write_text(
            json.dumps({"turns": self.turns, "state": self.snapshot()}, indent=2)
        )
        if runner.carry:
            raise RuntimeError(f"Real agent turn failed for {person}; inspect its private trace")
        return True

    async def settle(self, predicate, *, turns=8):
        for _ in range(turns):
            if predicate():
                return
            changed = False
            for person in self.names:
                changed |= await self.turn(person)
                if predicate():
                    return
            await asyncio.sleep(1 if changed else 2)
        raise AssertionError(
            "Real agents did not reach the expected durable state within the turn bound"
        )

    def plan(self, person):
        plans = group_plans.projection(person)["plans"]
        return next(iter(plans.values()), None)

    async def scenario(self):
        a, b = self.names
        await self.turn(
            a,
            f"Please propose a 30-minute test dinner with {b} at Cafe on {self.start}. "
            "Use group_plan_create, check status using its returned token, and wait for my approval. "
            "Do not vote or add an event yet.",
        )
        await self.settle(lambda: all(self.plan(p) for p in self.names), turns=4)
        assert all(self.plan(p)["votes"] == {} for p in self.names), "Agent invented owner consent"
        assert all(calendar_jobs.all_tasks(p) == [] for p in self.names)
        self.steps.append(
            {
                "check": "both real gates hold the draft; no consent or events",
                "status": "PASS",
                "state": self.snapshot(),
            }
        )
        reference = self.plan(a)["id"]
        await self.turn(
            b,
            "Read the new group plan and use dm_post in its room to tell the other agent "
            "that the proposed time works. Wait for my explicit approval before voting.",
        )
        await self.turn(
            a,
            f"I approve the exact current plan {reference}. Read its revision and fingerprint "
            "and relay my yes for that revision only.",
        )
        await self.settle(lambda: all(a in self.plan(p)["votes"] for p in self.names), turns=4)
        assert all(self.plan(p)["status"] == "pending" for p in self.names)
        assert all(calendar_jobs.all_tasks(p) == [] for p in self.names)
        self.steps.append(
            {
                "check": "one approval leaves both calendars untouched",
                "status": "PASS",
                "state": self.snapshot(),
            }
        )
        await self.turn(
            b,
            f"I approve the exact current plan {reference}. Read its current revision and "
            "fingerprint and relay my yes. After confirmation, deliver any calendar task "
            "to this test's local ICS calendar using cal_add, then report its actual event ID.",
        )
        await self.settle(lambda: all(self.plan(p)["status"] == "confirmed" for p in self.names))
        await self.settle(
            lambda: all(
                calendar_jobs.all_tasks(p) and not calendar_jobs.pending(p) for p in self.names
            )
        )
        for person in self.names:
            plan = self.plan(person)
            events = Calendar.from_ical(
                (self.output / "profiles" / person / "calendar.ics").read_bytes()
            ).walk("VEVENT")
            matching = [e for e in events if str(e.get("UID")) == plan["uid"]]
            assert len(matching) == 1, f"Missing or duplicated real ICS event for {person}"
            assert str(matching[0].get("SUMMARY")) == plan["content"]["title"]
            assert matching[0].decoded("DTSTART") == datetime.fromisoformat(
                plan["content"]["start"]
            )
        self.steps.append(
            {
                "check": "two approvals and two verified real ICS writes with matching event IDs",
                "status": "PASS",
            }
        )
        # Re-reading/processing an already consumed inbox must leave one event.
        await self.turn(
            a, "Check inbox and calendar_tasks again. Do not duplicate a completed calendar event."
        )
        for person in self.names:
            events = Calendar.from_ical(
                (self.output / "profiles" / person / "calendar.ics").read_bytes()
            ).walk("VEVENT")
            assert len(events) == 1, f"Repeated delivery duplicated an event for {person}"
        self.steps.append({"check": "repeated delivery check", "status": "PASS"})

    async def transcript(self):
        result = {}
        for person in self.names:
            with environment(self.envs[person]):
                from trustnet.tn.configuration import apply

                apply(override=True)
                async with personal.session(person) as client:
                    detail = await client.get_agent_detail(client.agent_id)
                    for room in detail["rooms"]:
                        if room["room_id"] not in result:
                            result[room["room_id"]] = {
                                "name": room["room_name"],
                                "context": await client.read_context(
                                    room_id=room["room_id"], limit=200
                                ),
                            }
        return result

    async def cleanup(self):
        for person, env in self.envs.items():
            try:
                await cli(env, "stop")
            except Exception:
                pass


def verify_state(state, names):
    plans = [next(iter(state[person]["plans"]["plans"].values())) for person in names]
    assert len({plan["fingerprint"] for plan in plans}) == 1, "Participants disagree"
    for person, plan in zip(names, plans):
        assert plan["status"] == "confirmed"
        assert set(plan["votes"]) == set(names)
        assert all(
            vote["vote"]
            and vote["revision"] == plan["revision"]
            and vote["fingerprint"] == plan["fingerprint"]
            for vote in plan["votes"].values()
        )
        tasks = state[person]["calendar_jobs"]
        assert len(tasks) == 1
        assert tasks[0]["status"] == "applied"
        assert tasks[0]["provider"] == "local-ics"
        assert tasks[0]["event_id"] == tasks[0]["uid"] == plan["uid"]
        events = Calendar.from_ical(state[person]["calendar"]).walk("VEVENT")
        assert len(events) == 1, f"Missing or duplicated event for {person}"
        event, content = events[0], plan["content"]
        assert str(event["UID"]) == plan["uid"]
        assert str(event["SUMMARY"]) == content["title"]
        assert str(event["LOCATION"]) == content["place"]
        assert event.decoded("DTSTART") == datetime.fromisoformat(content["start"])
        assert event.decoded("DTEND") - event.decoded("DTSTART") == timedelta(
            minutes=content["minutes"]
        )


async def main(args):
    os.chdir(ROOT)
    output = ROOT / "data" / ("real-agents-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"))
    output.mkdir(mode=0o700)
    stamp = str(int(time.time()))
    names = [f"e2a{stamp}a", f"e2a{stamp}b"]
    base = {k: v for k, v in os.environ.items() if not k.startswith("TN_") and k != "SWITCH_URL"}
    base.update(SWITCH_URL=args.server, TN_DATA_DIR=str(output / "profiles"))
    os.environ.update(base)
    os.environ["TN_DATA_DIR"] = base["TN_DATA_DIR"]
    credentials = provision(args.server, names, output)
    start = (
        (datetime.now(timezone.utc) + timedelta(days=2))
        .replace(hour=14, minute=30, second=0, microsecond=0)
        .isoformat()
    )
    acceptance = Acceptance(output, names, args.agents, base, start)
    report = {
        "agents": dict(zip(names, args.agents)),
        "switch": args.server,
        "calendar_backend": "real disposable local ICS files",
        "models": {agent: wake.MODELS[agent] for agent in args.agents},
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    }
    try:
        await acceptance.setup(credentials)
        await acceptance.scenario()
        verify_state(acceptance.snapshot(), names)
        report["status"] = "PASS"
    except Exception as exc:
        report.update(status="FAIL", error=f"{type(exc).__name__}: {exc}")
    finally:
        report["steps"], report["turns"] = acceptance.steps, acceptance.turns
        try:
            report["state"] = acceptance.snapshot()
            report["rooms"] = await acceptance.transcript()
        except Exception as exc:
            report["snapshot_error"] = type(exc).__name__
        await acceptance.cleanup()
        (output / "report.json").write_text(json.dumps(report, indent=2))
        (output / "summary.txt").write_text(
            report["status"] + "\n" + report.get("error", "") + "\n"
        )
        print(f"{report['status']}: {output / 'report.json'}", flush=True)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default="http://127.0.0.1:53330")
    parser.add_argument("--verify", type=Path, help="verify a saved report without calling agents")
    parser.add_argument(
        "--agents", nargs=2, choices=("codex", "opencode"), default=["codex", "codex"]
    )
    args = parser.parse_args()
    if args.verify:
        report = json.loads(args.verify.read_text())
        assert report["status"] == "PASS", "The live run failed"
        verify_state(report["state"], list(report["agents"]))
        for person in report["agents"]:
            actual = args.verify.parent / "profiles" / person / "calendar.ics"
            assert actual.read_text() == report["state"][person]["calendar"]
        print(f"PASS saved artifact: {args.verify}")
    else:
        sys.exit(asyncio.run(main(args)))
