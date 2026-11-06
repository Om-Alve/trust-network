"""Tests for ``view-as``: the owner's table must equal the policy's answer.

The two required views (Om→Rahul at close, Om→Priya at friend) are checked
against ``policy.visible_facts`` directly, and against each other: the only
rows Rahul's view adds are the facts tagged ``close``.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from trustnet.gate import policy
from trustnet.gate.calendar import busy
from trustnet.gate.facts import (
    EXAMPLES_DIR,
    Level,
    Profile,
    TrustList,
    load_profile_file,
    load_trust_file,
)
from trustnet.gate.view_as import Claim, ViewAsError, view_as

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=IST)
CLOSE_ONLY = {"neighbourhood", "sizes", "wishlist"}


@pytest.fixture(scope="module")
def profile() -> Profile:
    return load_profile_file(EXAMPLES_DIR / "om" / "facts.yaml")


@pytest.fixture(scope="module")
def om_trust() -> TrustList:
    return load_trust_file(EXAMPLES_DIR / "om" / "trust.yaml")


# --------------------------------------------------------------------------
# The two required views
# --------------------------------------------------------------------------


@pytest.fixture
def rahul_view(profile: Profile, om_trust: TrustList):
    return view_as(profile, om_trust, "rahul", now=NOW)


@pytest.fixture
def priya_view(profile: Profile, om_trust: TrustList):
    return view_as(profile, om_trust, "priya", now=NOW)


def test_rahul_gets_exactly_the_close_level_facts(profile: Profile, rahul_view) -> None:
    assert rahul_view.level is Level.CLOSE
    assert rahul_view.visible_values == policy.visible_facts(profile, Level.CLOSE)


def test_priya_gets_exactly_the_friend_level_facts(profile: Profile, priya_view) -> None:
    assert priya_view.level is Level.FRIEND
    assert priya_view.visible_values == policy.visible_facts(profile, Level.FRIEND)


def test_the_two_views_differ_exactly_by_the_close_level_facts(
    profile: Profile, rahul_view, priya_view
) -> None:
    close_level = {name for name, fact in profile.facts.items() if fact.level is Level.CLOSE}

    added = set(rahul_view.visible_values) - set(priya_view.visible_values)
    assert added == close_level == CLOSE_ONLY

    # Everything Priya sees, Rahul sees with the same value.
    for name in priya_view.visible_values:
        assert rahul_view.visible_values[name] == priya_view.visible_values[name]
    # And nothing private or unknown slips into either view.
    assert "address" not in rahul_view.visible_values
    assert "address" not in priya_view.visible_values


def test_rows_cover_every_fact_including_the_hidden_ones(profile: Profile, priya_view) -> None:
    assert [row.name for row in priya_view.rows] == list(profile.facts)

    by_name = {row.name: row for row in priya_view.rows}
    assert by_name["address"].visible is False
    assert by_name["address"].value is None
    for name in CLOSE_ONLY:
        assert by_name[name].visible is False
        assert by_name[name].value is None
    assert by_name["diet"].visible is True
    assert by_name["diet"].value == "vegetarian"


def test_view_as_equals_policy_at_every_room_level(
    profile: Profile, monkeypatch: pytest.MonkeyPatch
) -> None:
    people = {
        Level.ACQUAINTANCE: "acq",
        Level.FRIEND: "friend",
        Level.CLOSE: "close",
    }
    for level, person in people.items():
        view = view_as(profile, TrustList(people={person: level}), person, now=NOW)
        assert view.visible_values == policy.visible_facts(profile, level)


# --------------------------------------------------------------------------
# A person who is not on the list
# --------------------------------------------------------------------------


def test_a_stranger_gets_nothing(profile: Profile, om_trust: TrustList) -> None:
    view = view_as(profile, om_trust, "dev", now=NOW)

    assert view.level is None
    assert view.rows == ()
    assert view.calendar == ()
    assert view.visible_values == {}
    assert "not on your list → nothing" in view.render()


def test_an_id_the_list_cannot_hold_is_a_stranger(profile: Profile, om_trust: TrustList) -> None:
    view = view_as(profile, om_trust, "dev@switch.local", now=NOW)
    assert view.level is None
    assert view.visible_values == {}


def test_a_stranger_sees_no_calendar_even_when_the_owner_is_busy(
    profile: Profile, om_trust: TrustList
) -> None:
    # Om is busy during this window; a stranger's view still shows nothing.
    assert busy(profile.calendar_path, NOW, datetime(2026, 11, 12, 12, 0, tzinfo=IST))
    assert view_as(profile, om_trust, "dev", now=NOW).calendar == ()


# --------------------------------------------------------------------------
# Calendar: busy blocks always, titles by level
# --------------------------------------------------------------------------


def test_calendar_keeps_titles_for_a_close_friend(rahul_view) -> None:
    assert rahul_view.titles_visible is True
    titles = {row.title for row in rahul_view.calendar}
    assert titles == {"Spanish class", "Family video call", "Badminton"}
    assert "Family video call" in rahul_view.render()


def test_calendar_hides_titles_at_acquaintance(profile: Profile, rahul_view) -> None:
    trust = TrustList(people={"acq": Level.ACQUAINTANCE})
    view = view_as(profile, trust, "acq", now=NOW)

    assert view.titles_visible is False
    assert {(row.start, row.end) for row in view.calendar} == {
        (row.start, row.end) for row in rahul_view.calendar
    }
    assert {row.title for row in view.calendar} == {""}
    assert "no titles" in view.render()
    assert "Family video call" not in view.render()


def test_calendar_window_follows_now_and_days(profile: Profile, om_trust: TrustList) -> None:
    view = view_as(profile, om_trust, "rahul", now=NOW, days=1)
    assert view.window[0] == NOW
    assert view.window[1] == datetime(2026, 11, 6, 12, 0, tzinfo=IST)
    assert [row.title for row in view.calendar] == ["Spanish class"]


def test_an_empty_calendar_window_says_so(profile: Profile, om_trust: TrustList) -> None:
    view = view_as(profile, om_trust, "rahul", now=datetime(2026, 11, 6, 12, 0, tzinfo=IST), days=1)
    assert view.calendar == ()
    assert "nothing busy" in view.render()


def test_the_window_is_india_time_even_from_a_naive_now(
    profile: Profile, om_trust: TrustList
) -> None:
    view = view_as(profile, om_trust, "rahul", now=datetime(2026, 11, 5, 12))
    assert view.window[0].utcoffset() == NOW.utcoffset()
    assert view.window[0].hour == 12


# --------------------------------------------------------------------------
# Gift claims: hidden from the owner until reveal_after (phase 19 hook)
# --------------------------------------------------------------------------


def test_a_claim_is_hidden_until_its_reveal_day(profile: Profile, om_trust: TrustList) -> None:
    claim = Claim("Lego Millennium Falcon", date(2026, 11, 21))

    before = view_as(profile, om_trust, "rahul", now=NOW, claims=[claim])
    assert [item["item"] for item in before.visible_values["wishlist"]] == [
        "Hario V60",
        "Kindle Paperwhite",
    ]
    assert "Lego" not in before.render()

    after = view_as(
        profile, om_trust, "rahul", now=datetime(2026, 11, 21, 9, 0, tzinfo=IST), claims=[claim]
    )
    assert [item["item"] for item in after.visible_values["wishlist"]] == [
        "Lego Millennium Falcon",
        "Hario V60",
        "Kindle Paperwhite",
    ]
    assert "Lego Millennium Falcon" in after.render()


def test_a_claim_matches_case_insensitively(profile: Profile, om_trust: TrustList) -> None:
    claim = Claim("  lego millennium falcon ", date(2026, 11, 21))
    view = view_as(profile, om_trust, "rahul", now=NOW, claims=[claim])
    assert "Lego Millennium Falcon" not in view.render()


def test_a_claim_leaves_other_facts_alone(
    rahul_view, profile: Profile, om_trust: TrustList
) -> None:
    claim = Claim("Lego Millennium Falcon", date(2026, 11, 21))
    view = view_as(profile, om_trust, "rahul", now=NOW, claims=[claim])
    assert view.visible_values["diet"] == rahul_view.visible_values["diet"]
    assert view.visible_values["sizes"] == rahul_view.visible_values["sizes"]


# --------------------------------------------------------------------------
# Rendering and argument checks
# --------------------------------------------------------------------------


def test_render_is_a_field_by_field_table(rahul_view) -> None:
    lines = rahul_view.render().splitlines()

    assert lines[0] == "view-as rahul — close"
    assert any("✅ diet" in line and "vegetarian" in line for line in lines)
    assert any("❌ address" in line and "not shared at this level" in line for line in lines)
    assert "Calendar · next 7 days" in rahul_view.render()
    assert str(rahul_view) == rahul_view.render()


def test_priya_render_hides_close_facts_without_hiding_the_rows(priya_view) -> None:
    text = priya_view.render()
    assert "view-as priya — friend" in text
    assert "❌ wishlist" in text
    assert "Lego Millennium Falcon" not in text
    assert "✅ interests" in text


def test_view_as_rejects_bad_arguments(profile: Profile, om_trust: TrustList) -> None:
    with pytest.raises(ViewAsError, match="profile"):
        view_as("om", om_trust, "rahul", now=NOW)  # type: ignore[arg-type]
    with pytest.raises(ViewAsError, match="trust"):
        view_as(profile, "trust", "rahul", now=NOW)  # type: ignore[arg-type]
    with pytest.raises(ViewAsError, match="person"):
        view_as(profile, om_trust, "  ", now=NOW)


@pytest.mark.parametrize("days", [0, -1, True, 1.5])
def test_days_must_be_a_positive_integer(
    profile: Profile, om_trust: TrustList, days: object
) -> None:
    with pytest.raises(ViewAsError, match="days"):
        view_as(profile, om_trust, "rahul", now=NOW, days=days)  # type: ignore[arg-type]


def test_now_must_be_a_datetime(profile: Profile, om_trust: TrustList) -> None:
    with pytest.raises(ViewAsError, match="now"):
        view_as(profile, om_trust, "rahul", now="today")  # type: ignore[arg-type]
