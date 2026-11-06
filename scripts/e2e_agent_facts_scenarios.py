"""Offline phase 28 scenarios. Artifacts go outside data/ by default."""

import asyncio
import json
import sys
import tempfile
import traceback
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from pytest import MonkeyPatch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.e2e_facts_scenarios import personal_session, world_for  # noqa: E402
from trustnet.gate import ledger  # noqa: E402
from trustnet.gate.facts import load_profile, load_trust, resolve_data_dir, save_trust  # noqa: E402
from trustnet.tn import cli, mcp, personal  # noqa: E402


async def scenario(base):
    async with world_for(base, "world", trust={"om": {"rahul": "close"}}) as world:
        with MonkeyPatch.context() as patch:
            patch.setattr(personal, "session", personal_session(world))
            server = mcp.build("om")
            calls = []

            async def tool(name, **args):
                result = await server.call_tool(name, args)
                # MCPServer returns content blocks and structured content.
                text = json.dumps(result, default=str, ensure_ascii=False)
                calls.append({"tool": name, "args": args, "result": text})
                return text

            async def refused(name, **args):
                try:
                    await tool(name, **args)
                except Exception as exc:
                    calls.append({"refused": name, "reason": str(exc)})
                else:
                    raise AssertionError(f"{name} should refuse")

            room = await world.add_room("conn-om-rahul", ["om-gate", "rahul-gate"])

            async def ask(expected):
                await world.say(room, "rahul-gate", "@om-gate ask phone")
                assert world.bodies(room)[-1] == f"phone: {expected}"

            await tool("fact_add", key="phone", value="+91 9800000000")
            assert load_profile("om").facts["phone"].level.value == "private"
            await ask("not shared with you")
            effect = await tool("fact_share_request", key="phone", level="close")
            assert "F1: phone private → close. Who could see it: rahul (close)" in effect
            assert [x["ref"] for x in (await personal.inbox("om"))["open"]] == ["F1"]
            await ask("not shared with you")
            await tool("fact_share_approve", ref="F1")
            await ask("+91 9800000000")
            await world.say(world.homes["om"], "om", "@om-gate view-as rahul", kind="user")
            assert "+91 9800000000" in world.home_bodies("om")[-1]
            changes = [e for e in ledger.read("om") if e.kind.value == "fact-visibility"]
            assert changes[-1].value == {"before": "private", "after": "close", "ref": "F1"}
            await refused("fact_share_approve", ref="F1")
            await refused("fact_add", key="phone", value="replacement")
            assert load_profile("om").facts["phone"].value == "+91 9800000000"
            await tool("fact_share_request", key="phone", level="private")
            await ask("not shared with you")
            await tool("fact_share_request", key="phone", level="close")
            await tool("fact_share_decline", ref="F2")
            await refused("fact_share_approve", ref="F2")
            await ask("not shared with you")
            await tool("fact_share_request", key="phone", level="close")
            trust = load_trust("om")
            trust.consent_default = "direct"
            save_trust(trust, resolve_data_dir("om") / "trust.yaml")
            await refused("fact_share_approve", ref="F3")
            await world.say(world.homes["om"], "rahul-hermes", '@om-gate answer F3 "yes"')
            await ask("not shared with you")
            await world.say(world.homes["om"], "om", '@om-gate answer F3 "yes"', kind="user")
            await ask("+91 9800000000")
            await tool("fact_share_request", key="phone", level="private")
            await tool("fact_share_request", key="phone", level="close")
            from trustnet.gate import fact_changes

            with MonkeyPatch.context() as clock:
                clock.setattr(fact_changes, "_now", lambda: 10**12)
                assert not personal.open_items("om")
                out = StringIO()
                with redirect_stdout(out):
                    assert cli.main(["--as", "om", "fact", "approve", "F4"]) == 1
            await ask("not shared with you")
            for key, value in [
                ("../bad", "x"),
                ("x" * 65, "x"),
                ("huge", "x" * 16385),
                ("bad", "[oops"),
            ]:
                await refused("fact_add", key=key, value=value)
            await tool("fact_add", key="sizes_new", value="{tshirt: M}")
            assert load_profile("om").facts["sizes_new"].value == {"tshirt": "M"}
            # Owner CLI approval works even though agent consent is disabled.
            await tool("fact_share_request", key="sizes_new", level="close")
            out = StringIO()
            with redirect_stdout(out):
                assert cli.main(["--as", "om", "fact", "approve", "F5"]) == 0
            assert load_profile("om").facts["sizes_new"].level.value == "close"
            # Stale value and audience must require a fresh yes.
            await tool("fact_share_request", key="phone", level="close")
            profile = load_profile("om")
            from trustnet.gate.facts import FACTS_FILENAME, Level, save_profile

            profile.facts["phone"].value = "changed by owner"
            save_profile(profile, resolve_data_dir("om") / FACTS_FILENAME)
            with redirect_stdout(out):
                assert cli.main(["--as", "om", "fact", "approve", "F6"]) == 1
            await tool("fact_share_request", key="phone", level="close")
            trust = load_trust("om")
            trust.people["priya"] = Level.CLOSE
            save_trust(trust, resolve_data_dir("om") / "trust.yaml")
            with redirect_stdout(out):
                assert cli.main(["--as", "om", "fact", "approve", "F7"]) == 1
            assert load_profile("om").facts["phone"].level is Level.PRIVATE
            # T refs use the same direct-mode refusal as F refs.
            await tool("trust_suggest", person="sam", level="friend", reason="Known friend")
            await refused("fact_share_approve", ref="T1")
            assert load_trust("om").level_for("sam") is None
            with redirect_stdout(out):
                assert cli.main(["--as", "om", "review", "--approve", "T1"]) == 0
            assert load_trust("om").level_for("sam") is Level.FRIEND
            with redirect_stdout(out):
                assert cli.main(["--as", "om", "review", "--decline", "F6", "F7"]) == 0
            return {"calls": calls, "transcript": world.transcript()}


async def onboarding(base):
    from trustnet.gate.facts import FACTS_FILENAME, Level, save_profile

    async with world_for(base, "onboarding", trust={"om": {"rahul": "close"}}) as world:
        profile = load_profile("om")
        profile.facts = {}
        save_profile(profile, resolve_data_dir("om") / FACTS_FILENAME)
        server = mcp.build("om")
        prompt = await server.get_prompt("setup", {})
        assert prompt.messages
        calls = []

        async def tool(name, **args):
            result = await server.call_tool(name, args)
            calls.append({"tool": name, "args": args, "result": str(result)})
            return result

        memory = {
            "diet": ("vegetarian", "acquaintance", "Useful when planning meals"),
            "sizes": ("{tshirt: M}", "close", "For gifts"),
            "phone": ("+91 9800000000", "close", "For contacting me"),
            "address": ("A fictional private address", "private", "Sensitive"),
        }
        for key, (value, level, reason) in memory.items():
            await tool("fact_add", key=key, value=value)
            if level != "private":
                await tool("fact_share_request", key=key, level=level, reason=reason)
        await tool("trust_suggest", person="sam", level="friend", reason="We play board games")
        assert load_trust("om").level_for("sam") is None
        assert {f.level for f in load_profile("om").facts.values()} == {Level.PRIVATE}
        room = await world.add_room("conn-om-rahul", ["om-gate", "rahul-gate"])
        await world.say(room, "rahul-gate", "@om-gate ask diet sizes phone address")
        assert (
            world.bodies(room)[-1]
            == "diet: not shared with you\nsizes: not shared with you\nphone: not shared with you\naddress: not shared with you"
        )
        await tool("review")
        from trustnet.gate import fact_changes

        now = fact_changes._now()
        with MonkeyPatch.context() as clock:
            clock.setattr(fact_changes, "_now", lambda: now + 2 * 86400)
            assert len(personal.open_items("om")) == 4
        # The person's instruction is 'yes to all except F3'.
        await tool("fact_share_approve", ref=["F1", "F2", "T1"])
        assert load_trust("om").level_for("sam") is Level.FRIEND
        assert [x["ref"] for x in personal.open_items("om")] == ["F3"]
        await world.say(room, "rahul-gate", "@om-gate ask diet sizes phone address")
        assert (
            world.bodies(room)[-1]
            == "diet: vegetarian\nsizes: tshirt: M\nphone: not shared with you\naddress: not shared with you"
        )
        await world.say(world.homes["om"], "om", "@om-gate view-as rahul", kind="user")
        view = world.home_bodies("om")[-1]
        assert "vegetarian" in view and "tshirt: M" in view
        assert "+91 9800000000" not in view and "A fictional private address" not in view
        approved = [
            e.value["ref"]
            for e in ledger.read("om")
            if e.kind.value in {"fact-visibility", "trust-change"}
        ]
        assert approved == ["F1", "F2", "T1"]
        await tool("fact_share_decline", ref=["F3"])
        assert not personal.open_items("om")
        return {"calls": calls, "transcript": world.transcript(), "prompt": str(prompt)}


async def run():
    output = Path(tempfile.mkdtemp(prefix="trustnet-phase28-"))
    try:
        result = {"facts": await scenario(output), "onboarding": await onboarding(output)}
        result["status"] = "PASS"
    except Exception:
        result = {"status": "FAIL", "error": traceback.format_exc()}
    (output / "report.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(result["status"], output / "report.json")
    if "error" in result:
        print(result["error"])
    return result["status"] != "PASS"


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
