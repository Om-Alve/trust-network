"""Live acceptance: Hermes agents under launchd deliver an approved plan to Google Calendar.

Failure cases, before implementation:
- Hermes cannot reach the trust-network MCP server without editing ~/.hermes/config.yaml,
  or loses the person's Google credentials and skills when it does;
- `tn setup --agent hermes --wake --background-service` writes units launchd does
  not run, or runs them without Hermes on PATH;
- a Hermes turn fails or times out and strands the calendar task;
- the agent invents consent, or one yes queues a calendar write;
- Hermes refuses the write because its calendar skill wants confirmation, although
  both owners already approved the exact plan through their gates;
- the receipt names an event that does not exist, differs in title, time or place,
  or lacks the UID marker; or the event is written twice;
- the harness, not A's launchd-managed runner, performs the Google write;
- B's local ICS event differs from A's in UID or time;
- cleanup leaves the Google event, loaded units, processes or unit files behind;
- credentials or tokens appear in the report.

Provisions two fresh accounts on the local Switch Console; never touches existing
demo identities. Each person has a separate TN_CONFIG_DIR under the artifact
directory. Owner messages reach each agent as separate Hermes turns from this
harness; every news-driven turn, including A's Google write, belongs to the
launchd wake runners. The Google event is read back and deleted with the Hermes
google-workspace skill's own client. Requires Switch Console, an authenticated
Hermes google-workspace skill, and macOS launchd.

Run: uv run python -m scripts.e2a_hermes_calendar
Check a saved run offline: uv run python -m scripts.e2a_hermes_calendar --verify <report.json>
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

from icalendar import Calendar

from scripts.e2a_real_agents import PROXY, environment, provision
from trustnet.gate import calendar_jobs, group_plans
from trustnet.gate.facts import Level, TrustList, save_trust
from trustnet.gate.identity import export_local
from trustnet.tn import wake
from trustnet.tn.configuration import apply
from trustnet.tn.setup import SERVICE_PREFIX

ROOT = Path(__file__).resolve().parents[1]
LAUNCH_AGENTS = Path.home() / "Library/LaunchAgents"
HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
HERMES_PYTHON = HERMES_HOME / "hermes-agent/venv/bin/python"
GOOGLE_SCRIPTS = HERMES_HOME / "skills/productivity/google-workspace/scripts"
TIMEZONE = "Asia/Kolkata"
PLACE = "Third Wave Coffee, Indiranagar"
MINUTES = 30
GOOGLE_READ = """import json, sys
sys.path.insert(0, sys.argv[1])
import google_api
from googleapiclient.errors import HttpError
service = google_api.build_service("calendar", "v3")
fields = ("id", "summary", "start", "end", "location", "description", "status")
if sys.argv[2] == "get":
    try:
        event = service.events().get(calendarId="primary", eventId=sys.argv[3]).execute()
    except HttpError as exc:
        print(json.dumps({"http_status": exc.resp.status}))
    else:
        print(json.dumps({"http_status": 200, "event": {k: event.get(k) for k in fields}}))
else:
    items = service.events().list(
        calendarId="primary", timeMin=sys.argv[3], timeMax=sys.argv[4], singleEvents=True
    ).execute().get("items", [])
    print(json.dumps([e["id"] for e in items if sys.argv[5] in (e.get("description") or "")]))
"""


def google(*args):
    result = subprocess.run(
        [str(HERMES_PYTHON), "-W", "ignore", "-c", GOOGLE_READ, str(GOOGLE_SCRIPTS), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode:
        raise RuntimeError(f"Google read failed: {result.stderr.strip()[-300:]}")
    return json.loads(result.stdout)


def google_delete(event_id):
    result = subprocess.run(
        [str(HERMES_PYTHON), "-W", "ignore", str(GOOGLE_SCRIPTS / "google_api.py")]
        + ["calendar", "delete", event_id],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return {"returncode": result.returncode, "stdout": result.stdout.strip()}


def launchctl(label):
    result = subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}/{label}"], capture_output=True, text=True
    )
    lines = [line.strip() for line in result.stdout.splitlines()]
    return {
        "label": label,
        "returncode": result.returncode,
        "state": next((line for line in lines if line.startswith("state = ")), None),
        "pid": next((line for line in lines if line.startswith("pid = ")), None),
        "error": (result.stderr or "").strip().splitlines()[:2],
    }


async def sample_children(parent, seen):
    """Record each process ``parent`` runs, with the window it was seen alive in."""
    while True:
        listing = subprocess.run(
            ["ps", "-A", "-o", "pid=,ppid=,command="], capture_output=True, text=True
        ).stdout
        now = time.time()
        for line in listing.splitlines():
            pid, ppid, command = line.split(None, 2)
            if int(ppid) == parent:
                entry = seen.setdefault(pid, {"command": command[:110], "first_seen": now})
                entry["last_seen"] = now
        await asyncio.sleep(1)


def processes(person):
    result = subprocess.run(["pgrep", "-fl", person], capture_output=True, text=True)
    return [line[:200] for line in result.stdout.splitlines()]


def publish_identities(people_file, token, output):
    """The onboarding host's authenticated /identities endpoint, on a free loopback port."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            supplied = self.headers.get("Authorization", "")
            if self.path != "/identities" or not hmac.compare_digest(supplied, "Bearer " + token):
                self.send_error(401)
                return
            raw = export_local(
                output / "published-identities.json", {"TN_IDENTITY_PEOPLE": str(people_file)}
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


async def tn(env, *args, check=True):
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
    out, err = await asyncio.wait_for(process.communicate(), 240)
    if check and process.returncode:
        raise RuntimeError(f"tn {args[0]} exited {process.returncode}: {err.decode()[-500:]}")
    return json.loads(out) if out.strip() else {}


class Run:
    def __init__(self, output, names, base_env, start):
        self.output, self.names, self.base_env, self.start = output, names, base_env, start
        self.title = "trust-network E2E " + output.name.removeprefix("hermes-calendar-")
        self.envs, self.runners, self.setup_results = {}, {}, {}
        self.turns, self.steps, self.evidence = [], [], {}
        self.proxy = output / "agent-proxy.py"
        self.proxy.write_text(PROXY)

    def config_dir(self, person):
        return self.output / "config" / person

    def profile(self, person):
        return self.config_dir(person) / "profiles" / person

    def units(self):
        return [f"{SERVICE_PREFIX}.{p}.{role}" for p in self.names for role in ("gate", "wake")]

    def state(self, person):
        with environment(self.envs[person]):
            apply(override=True)
            return {
                "plans": group_plans.projection(person),
                "calendar_jobs": calendar_jobs.all_tasks(person),
                "calendar": (self.profile(person) / "calendar.ics").read_text(),
            }

    def plan(self, person):
        return next(iter(self.state(person)["plans"]["plans"].values()), None)

    async def until(self, what, predicate, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return
            for person in self.names:
                failed = [t for t in self.state(person)["calendar_jobs"] if t["status"] == "failed"]
                if failed:
                    raise AssertionError(
                        f"{person} reported a failed delivery: {failed[0]['error']}"
                    )
            await asyncio.sleep(3)
        raise AssertionError(f"Timed out waiting for: {what}")

    async def setup(self, credentials, identity_url, identity_token):
        a, b = self.names
        personas = {
            a: (
                "Your person's calendar is their Google Calendar, which you reach through your "
                "google-workspace skill (scripts/google_api.py calendar list/create/delete). "
                "The trust-network local calendar (cal_add) is not their calendar."
            ),
            b: "Your person's calendar is the local trust-network calendar; their gate writes it.",
        }
        for person in self.names:
            peer = b if person == a else a
            env = {
                **self.base_env,
                "TN_CONFIG_DIR": str(self.config_dir(person)),
                "E2A_GATE_KEY": credentials[person]["registration_key"],
                "E2A_IDENTITY_TOKEN": identity_token,
            }
            self.envs[person] = env
            profile = self.profile(person)
            profile.mkdir(parents=True, mode=0o700)
            trust = TrustList(consent_default="via-agent")
            trust.grant(peer, Level.FRIEND)
            save_trust(trust, profile / "trust.yaml")
            (profile / "agent.md").write_text(
                f"You are the personal agent of {person}, an isolated test person; your peer is "
                f"{peer}. This is an acceptance run on disposable accounts. Automatic conversation "
                "with the peer's agent is authorized. Do not message real contacts. The plan time "
                "is fixed by your person; do not negotiate it. Never vote without your person's "
                "explicit yes. " + personas[person]
            )
            self.setup_results[person] = await tn(
                env,
                "setup",
                "--name",
                person,
                "--server",
                self.base_env["SWITCH_URL"],
                "--key-env",
                "E2A_GATE_KEY",
                "--identity-url",
                identity_url,
                "--identity-token-env",
                "E2A_IDENTITY_TOKEN",
                "--agent",
                "hermes",
                "--consent",
                "via-agent",
                "--calendar-delivery",
                "agent" if person == a else "ics",
                "--timezone",
                TIMEZONE,
                "--wake",
                "--wake-every",
                "10",
                "--background-service",
            )
            invoke, label = wake.invoker(person, "hermes")

            def traced(reply, invoke=invoke, person=person):
                argv, extra, reader = invoke(reply)
                count = sum(t["person"] == person for t in self.turns)
                trace = self.output / f"{person}-owner-turn-{count}"
                request = trace.with_suffix(".request.json")
                request.write_text(json.dumps({"argv": argv, "trace": str(trace)}))
                return [sys.executable, str(self.proxy), str(request)], extra, reader

            with environment(env):
                apply(override=True)
                self.runners[person] = wake.Runner(person, traced, label, every=10)
        self.evidence["launchctl_before_planning"] = [launchctl(label) for label in self.units()]
        for entry in self.evidence["launchctl_before_planning"]:
            assert entry["state"] == "state = running" and entry["pid"], f"Not running: {entry}"
        self.evidence["doctor"] = {}
        for person in self.names:
            report = await tn(self.envs[person], "doctor", check=False)
            self.evidence["doctor"][person] = {
                key: report.get(key)
                for key in ("connection_ok", "automation_ready", "wake_verified")
            } | {"checks": {c["name"]: c["ok"] for c in report.get("checks", [])}}
            assert report.get("ok") and report.get("wake_verified"), (
                f"Doctor for {person}: {report}"
            )
        self.steps.append({"check": "launchd runs both gates and Hermes runners", "status": "PASS"})

    async def say(self, person, message):
        """The owner's own words to their agent, as a foreground Hermes turn."""
        runner = self.runners[person]
        entry = {"person": person, "owner_message": message, "started": time.time()}
        self.turns.append(entry)
        before = len(runner.transcript)
        with environment(self.envs[person]):
            apply(override=True)
            await runner.say(message)
        entry.update(ended=time.time(), transcript_delta=runner.transcript[before:])
        if runner.carry:
            raise RuntimeError(f"Owner turn failed for {person}; inspect its private trace")

    async def scenario(self):
        a, b = self.names
        local = self.start.astimezone(ZoneInfo(TIMEZONE))
        await self.say(
            a,
            f'Please propose a {MINUTES}-minute plan with {b} titled exactly "{self.title}" at '
            f'"{PLACE}", starting {local:%A %d %B %Y at %H:%M} {TIMEZONE} ({local.isoformat()}). '
            "Use group_plan_create, check its status with the returned token, and wait for my "
            "approval. Do not vote or add a calendar event yet.",
        )
        await self.until("both gates hold the draft", lambda: all(map(self.plan, self.names)), 240)
        assert all(self.plan(p)["votes"] == {} for p in self.names), "Agent invented consent"
        content = self.plan(a)["content"]
        assert content["title"] == self.title and content["place"] == PLACE, content
        assert datetime.fromisoformat(content["start"]) == self.start, content
        reference = self.plan(a)["id"]
        await self.say(
            a,
            f"I approve the exact current plan {reference}. Read its revision and fingerprint "
            "with group_plan_status and relay my yes for that revision only.",
        )
        await self.until(
            "A's yes on both gates",
            lambda: all(a in self.plan(p)["votes"] for p in self.names),
            180,
        )
        assert all(self.plan(p)["status"] == "pending" for p in self.names)
        assert all(self.state(p)["calendar_jobs"] == [] for p in self.names)
        self.steps.append({"check": "one approval queues no calendar work", "status": "PASS"})
        log = self.config_dir(a) / "wake-service.log"
        offset = log.stat().st_size
        self.evidence["a_tasks_empty_at"] = time.time()
        wake_unit = next(
            e
            for e in self.evidence["launchctl_before_planning"]
            if e["label"].endswith(f"{a}.wake")
        )
        children = self.evidence["a_launchd_runner_children"] = {}
        sampler = asyncio.create_task(sample_children(int(wake_unit["pid"].split()[-1]), children))
        await self.say(
            b,
            f"I approve the exact current plan {reference}. Read its current revision and "
            "fingerprint with group_plan_status and relay my yes.",
        )
        await self.until(
            "confirmation on both gates",
            lambda: all(self.plan(p)["status"] == "confirmed" for p in self.names),
            180,
        )
        self.evidence["confirmed_at"] = time.time()
        await self.until(
            "A's launchd runner reports the Google write",
            lambda: (jobs := self.state(a)["calendar_jobs"]) and jobs[0]["status"] == "applied",
            900,
        )
        self.evidence["receipt_seen_at"] = time.time()

        def runner_log():
            return log.read_bytes()[offset:].decode(errors="replace")

        await self.until(
            "A's runner prints its reply",
            lambda: "›" in runner_log().rpartition("waking the agent")[2],
            300,
        )
        sampler.cancel()
        self.evidence["runner_log_after_last_a_owner_turn"] = runner_log()[-4000:]
        self.evidence["runner_wakes_until_reply"] = runner_log().count("waking the agent")
        task = self.state(a)["calendar_jobs"][0]
        self.evidence["gate_receipt"] = {
            k: task[k] for k in ("uid", "status", "provider", "event_id", "action")
        }
        plan = self.plan(a)
        start = datetime.fromisoformat(plan["content"]["start"])
        end = start + timedelta(minutes=plan["content"]["minutes"])
        self.evidence["google_read"] = google("get", task["event_id"])
        self.evidence["google_events_with_uid"] = google(
            "search",
            (start - timedelta(hours=1)).isoformat(),
            (end + timedelta(hours=1)).isoformat(),
            plan["uid"],
        )
        verify_state(self.snapshot(), self.evidence, self.names, self.turns)
        self.steps.append(
            {"check": "launchd Hermes runner wrote the exact Google event", "status": "PASS"}
        )

    def snapshot(self):
        return {person: self.state(person) for person in self.names if person in self.envs}

    def google_cleanup(self, cleanup):
        ids = set()
        for person in self.envs:
            for task in self.state(person)["calendar_jobs"]:
                if task.get("event_id") and task.get("provider") != "local-ics":
                    ids.add(task["event_id"])
        plan = self.plan(self.names[0])
        if plan:
            start = datetime.fromisoformat(plan["content"]["start"])
            ids.update(
                google(
                    "search",
                    (start - timedelta(hours=2)).isoformat(),
                    (start + timedelta(hours=3)).isoformat(),
                    plan["uid"],
                )
            )
        for event_id in sorted(ids):
            cleanup["google_deleted"].append({"event_id": event_id, **google_delete(event_id)})
            cleanup["google_after_delete"][event_id] = google("get", event_id)

    async def cleanup(self):
        cleanup = {"google_deleted": [], "google_after_delete": {}, "tn_stop": {}}
        try:
            self.google_cleanup(cleanup)
        except Exception as exc:
            cleanup["google_error"] = f"{type(exc).__name__}: {exc}"
        for person, env in self.envs.items():
            try:
                cleanup["tn_stop"][person] = await tn(env, "stop")
            except Exception as exc:
                cleanup["tn_stop"][person] = {"error": str(exc)[-300:]}
        await asyncio.sleep(3)
        cleanup["launchctl_after_stop"] = [launchctl(label) for label in self.units()]
        cleanup["processes_after_stop"] = {person: processes(person) for person in self.names}
        left = [LAUNCH_AGENTS / f"{label}.plist" for label in self.units()]
        cleanup["unit_files_left_by_tn_stop"] = [str(p) for p in left if p.exists()]
        for path in left:
            path.unlink(missing_ok=True)
        cleanup["unit_files_after_cleanup"] = [str(p) for p in left if p.exists()]
        return cleanup


def verify_state(state, evidence, names, turns):
    a, b = names
    plans = [next(iter(state[person]["plans"]["plans"].values())) for person in names]
    assert len({plan["fingerprint"] for plan in plans}) == 1, "Participants disagree"
    for plan in plans:
        assert plan["status"] == "confirmed" and set(plan["votes"]) == set(names)
        assert all(
            v["vote"]
            and v["revision"] == plan["revision"]
            and v["fingerprint"] == plan["fingerprint"]
            for v in plan["votes"].values()
        )
    plan, content = plans[0], plans[0]["content"]
    start = datetime.fromisoformat(content["start"])
    end = start + timedelta(minutes=content["minutes"])
    receipt = evidence["gate_receipt"]
    assert receipt["status"] == "applied" and receipt["uid"] == plan["uid"], receipt
    assert receipt["provider"] and receipt["event_id"], receipt
    read = evidence["google_read"]
    assert read["http_status"] == 200, read
    event = read["event"]
    assert event["id"] == receipt["event_id"], "The receipt names a different Google event"
    assert event["status"] == "confirmed", event["status"]
    assert event["summary"] == content["title"], event["summary"]
    assert datetime.fromisoformat(event["start"]["dateTime"]) == start, event["start"]
    assert datetime.fromisoformat(event["end"]["dateTime"]) == end, event["end"]
    assert event["location"] == content["place"], event["location"]
    assert plan["uid"] in (event["description"] or ""), "Google event lacks the UID marker"
    assert evidence["google_events_with_uid"] == [event["id"]], "Missing or duplicated event"
    events = Calendar.from_ical(state[b]["calendar"]).walk("VEVENT")
    assert len(events) == 1 and str(events[0]["UID"]) == plan["uid"], "B's ICS UID differs"
    assert events[0].decoded("DTSTART") == start and events[0].decoded("DTEND") == end
    last_a_turn = max(t["ended"] for t in turns if t["person"] == a)
    assert last_a_turn < evidence["a_tasks_empty_at"] <= evidence["receipt_seen_at"], (
        "A harness turn overlapped calendar delivery"
    )
    assert any(
        "hermes chat" in child["command"]
        for child in evidence["a_launchd_runner_children"].values()
    ), "A's launchd runner ran no Hermes turn after A's last owner turn"
    assert "›" in evidence["runner_log_after_last_a_owner_turn"], (
        "A's launchd runner printed no reply after A's last owner turn"
    )


def verify_cleanup(cleanup, receipt):
    deleted = {d["event_id"]: d for d in cleanup["google_deleted"]}
    assert receipt["event_id"] in deleted and deleted[receipt["event_id"]]["returncode"] == 0
    for event_id, after in cleanup["google_after_delete"].items():
        gone = after["http_status"] in (404, 410)
        assert gone or after["event"]["status"] == "cancelled", f"{event_id} still exists"
    assert all(entry["returncode"] != 0 for entry in cleanup["launchctl_after_stop"])
    assert not any(cleanup["processes_after_stop"].values()), cleanup["processes_after_stop"]
    assert cleanup["unit_files_after_cleanup"] == []


async def main(args):
    os.chdir(ROOT)
    output = (
        ROOT / "data" / ("hermes-calendar-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"))
    )
    output.mkdir(mode=0o700, parents=True)
    stamp = str(int(time.time()))
    names = [f"hc{stamp}a", f"hc{stamp}b"]
    base = {k: v for k, v in os.environ.items() if not k.startswith("TN_") and k != "SWITCH_URL"}
    base["SWITCH_URL"] = args.server
    credentials = provision(args.server, names, output)
    identity_token = secrets.token_urlsafe(24)
    server = publish_identities(output / "identity-people.json", identity_token, output)
    identity_url = f"http://127.0.0.1:{server.server_address[1]}/identities"
    local = (datetime.now(ZoneInfo(TIMEZONE)) + timedelta(days=3)).replace(
        hour=15, minute=0, second=0, microsecond=0
    )
    run = Run(output, names, base, local.astimezone(timezone.utc))
    report = {
        "people": {names[0]: "Hermes, Google Calendar", names[1]: "Hermes, local ICS"},
        "switch": args.server,
        "title": run.title,
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    }
    try:
        await run.setup(credentials, identity_url, identity_token)
        await run.scenario()
        report["status"] = "PASS"
    except Exception as exc:
        report.update(status="FAIL", error=f"{type(exc).__name__}: {exc}")
    finally:
        report["steps"], report["owner_turns"], report["evidence"] = (
            run.steps,
            run.turns,
            run.evidence,
        )
        try:
            report["state"] = run.snapshot()
        except Exception as exc:
            report["snapshot_error"] = f"{type(exc).__name__}: {exc}"
        try:
            report["cleanup"] = await run.cleanup()
            if report["status"] == "PASS":
                verify_cleanup(report["cleanup"], run.evidence["gate_receipt"])
        except Exception as exc:
            report.update(status="FAIL", error=f"cleanup: {type(exc).__name__}: {exc}")
        server.shutdown()
        (output / "report.json").write_text(json.dumps(report, indent=2))
        print(f"{report['status']}: {output / 'report.json'}", flush=True)
        if report.get("error"):
            print(report["error"], flush=True)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default="http://127.0.0.1:53330")
    parser.add_argument("--verify", type=Path, help="verify a saved report without live calls")
    args = parser.parse_args()
    if args.verify:
        report = json.loads(args.verify.read_text())
        assert report["status"] == "PASS", f"The live run failed: {report.get('error')}"
        names = list(report["people"])
        evidence = report["evidence"]
        for entry in evidence["launchctl_before_planning"]:
            assert entry["state"] == "state = running" and entry["pid"], entry
        assert len(evidence["launchctl_before_planning"]) == 4
        assert all(
            d["wake_verified"] and d["automation_ready"] for d in evidence["doctor"].values()
        )
        verify_state(report["state"], evidence, names, report["owner_turns"])
        verify_cleanup(report["cleanup"], evidence["gate_receipt"])
        actual = args.verify.parent / "config" / names[1] / "profiles" / names[1] / "calendar.ics"
        assert actual.read_text() == report["state"][names[1]]["calendar"]
        print(f"PASS saved artifact: {args.verify}")
    else:
        sys.exit(asyncio.run(main(args)))
