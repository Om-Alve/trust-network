"""Every MCP tool with bad input: a named refusal, never a traceback.

The server runs over real stdio. No Switch is configured, so a tool that gets
past local validation fails on ``SWITCH_URL``; the cases below are exactly the
inputs the owner's own data (trust list, facts, calendar, form limits) can
reject before any network call.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest
from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client

PERSONS = ("om", "rahul", "priya")

CASES = [
    ("dm", {"friend": "nobody", "goal": "x"}, "no friend named nobody"),
    ("dm", {"friend": "rahul", "goal": ""}, "quoted text must not be empty"),
    ("dm", {"friend": "rahul", "goal": "x" * 200}, "140 characters or fewer"),
    ("dm", {"friend": "Bad Name!", "goal": "x"}, "invalid person name"),
    ("answer", {"id": "nope", "text": "yes"}, "invalid reference"),
    ("answer", {"id": "Q1", "text": ""}, "quoted text must not be empty"),
    ("answer", {"id": "P1", "text": "maybe"}, 'must be "yes" or "no"'),
    ("ask_around", {"question": ""}, "quoted text must not be empty"),
    ("ask_around", {"question": "x" * 200}, "140 characters or fewer"),
    ("ask", {"friend": "nobody", "fields": ["diet"]}, "no friend named nobody"),
    ("ask", {"friend": "rahul", "fields": []}, "ask needs at least one fact"),
    ("ask", {"friend": "rahul", "fields": ["DIET!"]}, "invalid fact name"),
    (
        "gift_ideas",
        {"friend": "nobody", "occasion": "birthday", "date": "2026-11-20", "budget": 1},
        "no friend named nobody",
    ),
    (
        "gift_ideas",
        {"friend": "rahul", "occasion": "birthday", "date": "not a date", "budget": 1},
        "could not read the date",
    ),
    (
        "gift_ideas",
        {"friend": "rahul", "occasion": "", "date": "2026-11-20", "budget": 1},
        "needs an occasion and a date",
    ),
    (
        "gift_ideas",
        {"friend": "rahul", "occasion": "birthday", "date": "2026-11-20", "budget": 0},
        "positive number",
    ),
    (
        "gift_ideas",
        {"friend": "rahul", "occasion": "birthday", "date": "2026-11-20", "budget": "lots"},
        "validation error",
    ),
    ("claim", {"friend": "nobody", "item": "x"}, "no friend named nobody"),
    ("claim", {"friend": "rahul", "item": ""}, "a claim needs an item"),
    ("claim", {"friend": "rahul", "item": "x" * 100}, "80 characters or fewer"),
    ("fact_set", {"key": "", "level": "friend"}, "a fact needs a name"),
    ("fact_set", {"key": "drinks", "level": "self"}, "fact level must be"),
    ("fact_set", {"key": "neighbourhood", "level": "friend"}, "refusing to loosen"),
    (
        "cal_add",
        {"start": "nonsense", "duration": "2h", "title": "x", "place": "y"},
        "could not read the start",
    ),
    (
        "cal_add",
        {"start": "2026-11-08T21:00", "duration": "soon", "title": "x", "place": "y"},
        "could not read the duration",
    ),
    (
        "cal_add",
        {"start": "2026-11-08T21:00", "duration": "2h", "title": "", "place": "y"},
        "an event needs a title",
    ),
    (
        "cal_add",
        {"start": "2026-11-08T21:00", "duration": "2h", "title": "x", "place": "a/b"},
        "a place may only contain",
    ),
    (
        "cal_add",
        {"start": "2026-11-08T21:00", "duration": "2h", "title": "x" * 61, "place": "y"},
        "60 characters or fewer",
    ),
]


async def _text(result) -> str:
    return "".join(block.text for block in result.content if getattr(block, "text", None))


async def test_every_tool_refuses_bad_input_with_a_readable_message(tmp_path):
    for person in PERSONS:
        shutil.copytree(Path.cwd() / "examples" / person, tmp_path / person)
    env = {
        "PATH": os.environ["PATH"],
        "HOME": os.environ["HOME"],
        "TN_DATA_DIR": str(tmp_path),
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "trustnet.tn.mcp", "--as", "om"],
        env=env,
        cwd=str(tmp_path),
    )
    with open(os.devnull, "w") as errlog:
        async with stdio_client(params, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for tool, arguments, expected in CASES:
                    result = await session.call_tool(tool, arguments)
                    text = await _text(result)
                    assert result.is_error, (tool, arguments, text)
                    assert expected in text, (tool, arguments, text)
                    assert "Traceback" not in text, (tool, arguments, text)


async def test_unicode_and_a_tightening_edit_still_succeed(tmp_path):
    for person in PERSONS:
        shutil.copytree(Path.cwd() / "examples" / person, tmp_path / person)
    env = {
        "PATH": os.environ["PATH"],
        "HOME": os.environ["HOME"],
        "TN_DATA_DIR": str(tmp_path),
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "trustnet.tn.mcp", "--as", "om"],
        env=env,
        cwd=str(tmp_path),
    )
    with open(os.devnull, "w") as errlog:
        async with stdio_client(params, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "cal_add",
                    {
                        "start": "2026-11-08T21:00",
                        "duration": "2h",
                        "title": "Café ☕",
                        "place": "The Park, MG Road",
                    },
                )
                assert not result.is_error, await _text(result)
                assert json.loads(await _text(result))["title"] == "Café ☕"

                result = await session.call_tool("fact_set", {"key": "drinks", "level": "close"})
                assert not result.is_error, await _text(result)
                assert json.loads(await _text(result))["level"] == "close"


@pytest.mark.parametrize("value", ["", " ", "\t"])
async def test_whitespace_is_an_empty_string(tmp_path, value):
    """A blank string is refused by the same check as an empty one."""
    from trustnet.tn.personal import answer

    with pytest.raises(ValueError, match="quoted text must not be empty"):
        await answer("om", "Q1", value)
