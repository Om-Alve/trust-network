"""Tests for the envoy brief: policy-filtered, quoted, and logged.

Rule 7 is the point of this file: a friend-level brief must contain exactly the
facts ``ask`` would answer with, and no close or private value may appear even
as a substring. Rule 6 is checked by writing a brief into ``TN_DATA_DIR`` and
reading the ledger back.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from trustnet.gate import commands, ledger, policy
from trustnet.gate.brief import BriefError, build_brief, write_brief
from trustnet.gate.commands import Quoted
from trustnet.gate.facts import (
    EXAMPLES_DIR,
    Level,
    Profile,
    TrustList,
    load_profile_file,
    load_trust_file,
)

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=IST)
DAYS = (date(2026, 11, 8), date(2026, 11, 9))
GOAL_TEXT = "something fun Sunday evening, not pricey"
GOAL = Quoted(GOAL_TEXT)
ROOM = "dm-om-rahul-sat"

FACTS_HEADER = "## What you may say about "
ROW_RE = re.compile(r"^- \*\*(?P<name>[^*]+)\*\*: (?P<value>.*)$", re.MULTILINE)
COMMAND_RE = re.compile(r"`(@[A-Za-z0-9_-]+ [^`]+)`")


@pytest.fixture(scope="module")
def profile() -> Profile:
    return load_profile_file(EXAMPLES_DIR / "om" / "facts.yaml")


@pytest.fixture(scope="module")
def om_trust() -> TrustList:
    return load_trust_file(EXAMPLES_DIR / "om" / "trust.yaml")


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TN_DATA_DIR", str(tmp_path))
    return tmp_path


def fact_rows(text: str) -> dict[str, str]:
    """The rendered fact bullets, as ``{name: value}``."""
    _, marker, rest = text.partition(FACTS_HEADER)
    assert marker, "the brief has no facts section"
    section = rest.split("\n## ", 1)[0]
    return {match["name"]: match["value"] for match in ROW_RE.finditer(section)}


def leaf_strings(value: Any) -> Iterator[str]:
    """Every string a value contains, so a test can search for each one."""
    if isinstance(value, Mapping):
        for item in value.values():
            yield from leaf_strings(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from leaf_strings(item)
    elif isinstance(value, str):
        yield value
    else:
        yield str(value)


# --------------------------------------------------------------------------
# Rule 7: the facts in the brief are exactly what ask answers with
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("friend", "level"), [("rahul", Level.CLOSE), ("priya", Level.FRIEND)])
def test_facts_in_the_brief_equal_ask_at_that_level(
    profile: Profile, om_trust: TrustList, friend: str, level: Level
) -> None:
    text, disclosed = build_brief(profile, om_trust, friend, ROOM, GOAL, DAYS)
    expected = policy.visible_facts(profile, level)

    assert disclosed == expected
    assert set(fact_rows(text)) == set(expected)
    for name, value in expected.items():
        assert str(next(leaf_strings(value))) in fact_rows(text)[name]


@pytest.mark.parametrize("level", [Level.ACQUAINTANCE, Level.FRIEND, Level.CLOSE])
def test_fact_rows_match_the_policy_at_every_room_level(profile: Profile, level: Level) -> None:
    trust = TrustList(people={"friend": level})
    text, disclosed = build_brief(profile, trust, "friend", "dm-om-friend-x", GOAL, DAYS)

    assert disclosed == policy.visible_facts(profile, level)
    assert set(fact_rows(text)) == set(disclosed)


def test_a_friend_level_brief_has_no_close_or_private_value(
    profile: Profile, om_trust: TrustList
) -> None:
    text, _ = build_brief(profile, om_trust, "priya", "dm-om-priya-sat", GOAL, DAYS)
    hidden = [
        (name, fact.value)
        for name, fact in profile.facts.items()
        if fact.level in (Level.CLOSE, Level.PRIVATE)
    ]
    assert {name for name, _ in hidden} == {
        "neighbourhood",
        "sizes",
        "wishlist",
        "address",
    }

    for name, value in hidden:
        assert f"**{name}**" not in text
        for leaf in leaf_strings(value):
            if len(leaf) >= 3:
                assert leaf.casefold() not in text.casefold(), f"{name} leaked {leaf!r}"


@pytest.mark.parametrize(
    ("level", "hidden_tags"),
    [
        (Level.ACQUAINTANCE, {Level.FRIEND, Level.CLOSE, Level.PRIVATE}),
        (Level.FRIEND, {Level.CLOSE, Level.PRIVATE}),
        (Level.CLOSE, {Level.PRIVATE}),
    ],
)
def test_no_value_above_the_room_level_appears_anywhere(
    profile: Profile, level: Level, hidden_tags: set[Level]
) -> None:
    trust = TrustList(people={"friend": level})
    text, _ = build_brief(profile, trust, "friend", "dm-om-friend-x", GOAL, DAYS)
    folded = text.casefold()

    for name, fact in profile.facts.items():
        if fact.level not in hidden_tags:
            continue
        assert f"**{name}**" not in text
        for leaf in leaf_strings(fact.value):
            if len(leaf) >= 4:
                assert leaf.casefold() not in folded, f"{name} leaked {leaf!r}"


def test_private_values_never_appear_at_any_level(profile: Profile, om_trust: TrustList) -> None:
    for friend in ("rahul", "priya"):
        text, _ = build_brief(profile, om_trust, friend, ROOM, GOAL, DAYS)
        for leaf in leaf_strings(profile.facts["address"].value):
            assert leaf not in text
        assert "**address**" not in text


def test_calendar_titles_follow_the_policy(profile: Profile) -> None:
    acquaintance = TrustList(people={"friend": Level.ACQUAINTANCE})
    text, _ = build_brief(profile, acquaintance, "friend", "dm-om-friend-x", GOAL, DAYS)
    assert "Family video call" not in text
    assert "17:00–19:00" in text

    friend = TrustList(people={"friend": Level.FRIEND})
    text, _ = build_brief(profile, friend, "friend", "dm-om-friend-x", GOAL, DAYS)
    assert "Family video call" in text


# --------------------------------------------------------------------------
# Free text only ever appears quoted
# --------------------------------------------------------------------------


def test_the_goal_appears_only_quoted(profile: Profile, om_trust: TrustList) -> None:
    text, _ = build_brief(profile, om_trust, "rahul", ROOM, GOAL, DAYS)

    assert text.count(GOAL_TEXT) == 1
    start = text.index(GOAL_TEXT)
    assert text[start - 1] == '"'
    assert text[start + len(GOAL_TEXT)] == '"'


def test_a_plain_string_goal_is_quoted(profile: Profile, om_trust: TrustList) -> None:
    text, _ = build_brief(profile, om_trust, "rahul", ROOM, GOAL_TEXT, DAYS)
    assert f'"{GOAL_TEXT}"' in text


@pytest.mark.parametrize(
    "goal",
    [
        'he said "bowling"',
        "two\nlines",
        "x" * 141,
        "",
    ],
)
def test_a_goal_that_cannot_be_quoted_is_rejected(
    profile: Profile, om_trust: TrustList, goal: str
) -> None:
    with pytest.raises(BriefError):
        build_brief(profile, om_trust, "rahul", ROOM, goal, DAYS)


# --------------------------------------------------------------------------
# Command examples are phase 09 syntax, with the real gate names
# --------------------------------------------------------------------------


def test_every_command_example_parses(profile: Profile, om_trust: TrustList) -> None:
    text, _ = build_brief(profile, om_trust, "rahul", ROOM, GOAL, DAYS)
    examples = COMMAND_RE.findall(text)

    assert len(examples) == 2
    parsed = [commands.parse(example) for example in examples]
    kinds = [type(command) for command in parsed]
    assert kinds == [commands.AskOwner, commands.Propose]
    assert {command.target for command in parsed} == {"om-gate"}

    ask = next(command for command in parsed if isinstance(command, commands.AskOwner))
    assert ask.question_id == "Q1"
    assert str(ask.question) == '"Is ₹1,500 per person okay?"'


def test_command_examples_never_address_the_friends_gate(
    profile: Profile, om_trust: TrustList
) -> None:
    # Proposals go through your own gate only, which forwards them; a card that
    # @-mentions the friend's gate also makes Switch flag it in the home room.
    text, _ = build_brief(profile, om_trust, "priya", "dm-om-priya-sat", GOAL, DAYS)

    assert "@priya-gate" not in text
    assert "@rahul-gate" not in text
    assert "@om-gate propose" in text


# --------------------------------------------------------------------------
# The two demo briefs
# --------------------------------------------------------------------------


def test_the_two_demo_briefs_differ_exactly_by_the_close_facts(
    profile: Profile, om_trust: TrustList
) -> None:
    rahul, _ = build_brief(profile, om_trust, "rahul", ROOM, GOAL, DAYS)
    priya, _ = build_brief(profile, om_trust, "priya", "dm-om-priya-sat", GOAL, DAYS)

    assert set(fact_rows(rahul)) - set(fact_rows(priya)) == {
        "neighbourhood",
        "sizes",
        "wishlist",
    }
    for name in fact_rows(priya):
        assert fact_rows(rahul)[name] == fact_rows(priya)[name]


# --------------------------------------------------------------------------
# Rule 6: writing a brief records what it disclosed
# --------------------------------------------------------------------------


def test_write_brief_records_every_fact_and_the_calendar(
    profile: Profile, om_trust: TrustList, data_dir: Path
) -> None:
    brief = write_brief(profile, om_trust, "rahul", ROOM, GOAL, DAYS, now=NOW)
    entries = ledger.read("om")

    assert [entry.field for entry in entries] == [*brief.disclosed_facts, "calendar"]
    assert all(entry.kind is ledger.Kind.BRIEF for entry in entries)
    assert all(entry.to == "rahul" and entry.room == ROOM and entry.ts == NOW for entry in entries)
    assert {entry.field: entry.value for entry in entries if entry.field != "calendar"} == (
        policy.visible_facts(profile, Level.CLOSE)
    )
    calendar = next(entry for entry in entries if entry.field == "calendar")
    assert calendar.value == [
        {
            "start": "2026-11-08T17:00:00+05:30",
            "end": "2026-11-08T19:00:00+05:30",
            "title": "Family video call",
        }
    ]
    assert brief.entries == tuple(entries)


def test_the_ledger_goes_to_the_data_dir_not_examples(
    profile: Profile, om_trust: TrustList, data_dir: Path
) -> None:
    write_brief(profile, om_trust, "rahul", ROOM, GOAL, DAYS, now=NOW)
    assert ledger.ledger_path("om") == (data_dir / "om" / "ledger.jsonl").resolve()
    assert ledger.ledger_path("om").is_file()


def test_a_friend_level_brief_logs_no_title_the_level_hides(
    profile: Profile, data_dir: Path
) -> None:
    trust = TrustList(people={"friend": Level.ACQUAINTANCE})
    write_brief(profile, trust, "friend", "dm-om-friend-x", GOAL, DAYS, now=NOW)

    calendar = next(entry for entry in ledger.read("om") if entry.field == "calendar")
    assert calendar.value == [
        {
            "start": "2026-11-08T17:00:00+05:30",
            "end": "2026-11-08T19:00:00+05:30",
            "title": "",
        }
    ]


def test_build_brief_alone_writes_no_ledger(
    profile: Profile, om_trust: TrustList, data_dir: Path
) -> None:
    build_brief(profile, om_trust, "rahul", ROOM, GOAL, DAYS)
    assert not ledger.ledger_path("om").exists()


# --------------------------------------------------------------------------
# Input validation
# --------------------------------------------------------------------------


def test_a_stranger_gets_no_brief(profile: Profile, om_trust: TrustList) -> None:
    with pytest.raises(BriefError, match="not on om's trust list"):
        build_brief(profile, om_trust, "dev", ROOM, GOAL, DAYS)


@pytest.mark.parametrize(
    ("date_range", "message"),
    [
        ((date(2026, 11, 9), date(2026, 11, 8)), "end on or after"),
        ((date(2026, 11, 8),), "two dates"),
        (("tomorrow", date(2026, 11, 8)), "needs dates"),
    ],
)
def test_a_bad_date_range_is_rejected(
    profile: Profile, om_trust: TrustList, date_range: Any, message: str
) -> None:
    with pytest.raises(BriefError, match=message):
        build_brief(profile, om_trust, "rahul", ROOM, GOAL, date_range)


def test_an_empty_room_is_rejected(profile: Profile, om_trust: TrustList) -> None:
    with pytest.raises(BriefError, match="room"):
        build_brief(profile, om_trust, "rahul", "  ", GOAL, DAYS)


def test_a_profile_with_nothing_to_share_still_renders(profile: Profile) -> None:
    empty = Profile(owner="om", facts={}, calendar_path=profile.calendar_path)
    trust = TrustList(people={"friend": Level.FRIEND})
    empty_days = (date(2027, 1, 1), date(2027, 1, 2))
    text, disclosed = build_brief(empty, trust, "friend", "dm-om-friend-x", GOAL, empty_days)

    assert disclosed == {}
    assert fact_rows(text) == {}
    assert "Nothing is shared at this level." in text
    assert "Nothing is on the calendar in this range." in text
