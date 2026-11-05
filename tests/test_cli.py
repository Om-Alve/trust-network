"""Tests for the offline ``tn`` CLI.

Every test that writes runs against a temporary copy of ``examples/`` selected
with ``TN_DATA_DIR``; the committed fixtures are only ever read. ``main()`` is
called directly, the same way the console script calls it.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from trustnet.gate.calendar import TIME_ZONE, busy
from trustnet.gate.facts import (
    EXAMPLES_DIR,
    FACTS_FILENAME,
    TRUST_FILENAME,
    Level,
    load_profile,
    load_trust,
)
from trustnet.tn.cli import main

PERSON_FILES = ("trust.yaml", "facts.yaml", "calendar.ics")


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A writable copy of every fixture, selected for the whole test."""
    root = tmp_path / "data"
    for person in ("om", "rahul", "priya"):
        shutil.copytree(EXAMPLES_DIR / person, root / person)
    monkeypatch.setenv("TN_DATA_DIR", str(root))
    monkeypatch.delenv("TN_PERSON", raising=False)
    return root


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]):
    """Call ``main`` and return ``(exit code, stdout, stderr)``."""

    def _run(*argv: str) -> tuple[int, str, str]:
        code = main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def test_init_creates_an_empty_profile(data_dir: Path, run) -> None:
    code, out, err = run("init", "alex")

    assert code == 0
    assert err == ""
    directory = data_dir / "alex"
    assert str(directory) in out
    for filename in PERSON_FILES:
        assert (directory / filename).is_file()

    profile = load_profile("alex")
    assert profile.owner == "alex"
    assert profile.facts == {}
    assert profile.calendar_path == (directory / "calendar.ics").resolve()
    assert load_trust("alex").people == {}


def test_init_refuses_to_overwrite_until_forced(data_dir: Path, run) -> None:
    assert run("init", "alex")[0] == 0
    (data_dir / "alex" / TRUST_FILENAME).write_text("people:\n  om: close\n")

    code, _out, err = run("init", "alex")
    assert code == 1
    assert "already has" in err
    assert "--force" in err

    code, _out, _err = run("init", "alex", "--force")
    assert code == 0
    assert load_trust("alex").people == {}


def test_init_defaults_to_as_or_tn_person(data_dir: Path, run) -> None:
    code, _out, _err = run("--as", "sam", "init")
    assert code == 0
    assert (data_dir / "sam" / FACTS_FILENAME).is_file()

    code, _out, err = run("init")
    assert code == 1
    assert "TN_PERSON" in err


# ---------------------------------------------------------------------------
# trust
# ---------------------------------------------------------------------------


def test_trust_raises_a_level(data_dir: Path, run) -> None:
    code, out, err = run("--as", "om", "trust", "priya", "close")

    assert code == 0
    assert err == ""
    assert "priya" in out and "friend → close" in out
    assert load_trust("om").people["priya"] is Level.CLOSE


def test_trust_adds_a_new_person_and_speaks_json(data_dir: Path, run) -> None:
    code, out, _err = run("--json", "--as", "om", "trust", "dev", "acquaintance")

    assert code == 0
    payload = json.loads(out)
    assert payload == {
        "owner": "om",
        "person": "dev",
        "level": "acquaintance",
        "previous": None,
    }
    assert load_trust("om").level_for("dev") is Level.ACQUAINTANCE


@pytest.mark.parametrize("level", ["private", "self", "bestie"])
def test_trust_rejects_levels_a_room_cannot_sit_at(data_dir: Path, run, level: str) -> None:
    before = (data_dir / "om" / TRUST_FILENAME).read_bytes()

    code, _out, err = run("--as", "om", "trust", "priya", level)

    assert code == 1
    assert "acquaintance, friend or close" in err
    assert (data_dir / "om" / TRUST_FILENAME).read_bytes() == before


# ---------------------------------------------------------------------------
# fact get
# ---------------------------------------------------------------------------


def test_fact_get_shows_the_owner_every_fact(data_dir: Path, run) -> None:
    code, out, err = run("--as", "om", "fact", "get")

    assert code == 0
    assert err == ""
    assert "vegetarian" in out
    assert "wishlist" in out and "≈₹2,500" in out
    assert "address" in out and "private" in out


def test_fact_get_subset_is_exact_and_speaks_json(data_dir: Path, run) -> None:
    code, out, _err = run("--json", "--as", "om", "fact", "get", "diet", "wishlist")

    assert code == 0
    payload = json.loads(out)
    assert payload["owner"] == "om"
    assert list(payload["facts"]) == ["diet", "wishlist"]
    assert payload["facts"]["diet"] == {"value": "vegetarian", "level": "acquaintance"}
    assert payload["facts"]["wishlist"]["level"] == "close"
    assert payload["facts"]["wishlist"]["value"][0] == {"item": "Catan Seafarers", "price": 2500}


def test_fact_get_reports_an_unknown_key(data_dir: Path, run) -> None:
    code, _out, err = run("--as", "om", "fact", "get", "shoe-size")

    assert code == 1
    assert "no fact named shoe-size" in err
    assert "diet" in err  # the available keys are listed


# ---------------------------------------------------------------------------
# fact set: tighten-only
# ---------------------------------------------------------------------------


def test_fact_set_tightens_and_keeps_the_value(data_dir: Path, run) -> None:
    code, out, _err = run("--as", "om", "fact", "set", "drinks", "--level", "close")

    assert code == 0
    assert "friend → close" in out
    fact = load_profile("om").facts["drinks"]
    assert fact.level is Level.CLOSE
    assert fact.value == "no alcohol"


@pytest.mark.parametrize(
    ("key", "level"),
    [("drinks", "acquaintance"), ("neighbourhood", "friend")],
)
def test_fact_set_refuses_to_loosen(data_dir: Path, run, key: str, level: str) -> None:
    before = load_profile("om").facts[key]

    code, _out, err = run("--as", "om", "fact", "set", key, "--level", level)

    assert code == 1
    assert "edit facts.yaml by hand to loosen" in err
    assert f"{key}:" in err
    after = load_profile("om").facts[key]
    assert (after.level, after.value) == (before.level, before.value)


def test_fact_set_can_make_a_fact_private(data_dir: Path, run) -> None:
    code, _out, _err = run("--as", "om", "fact", "set", "drinks", "--level", "private")

    assert code == 0
    assert load_profile("om").facts["drinks"].level is Level.PRIVATE


def test_fact_set_creates_a_new_fact_with_a_value(data_dir: Path, run) -> None:
    code, out, _err = run(
        "--json",
        "--as",
        "om",
        "fact",
        "set",
        "allergies",
        "--level",
        "friend",
        "--value",
        "[peanuts, dust]",
    )

    assert code == 0
    payload = json.loads(out)
    assert payload["created"] is True
    assert payload["level"] == "friend"
    fact = load_profile("om").facts["allergies"]
    assert fact.level is Level.FRIEND
    assert fact.value == ["peanuts", "dust"]


def test_fact_set_needs_a_value_to_create(data_dir: Path, run) -> None:
    code, _out, err = run("--as", "om", "fact", "set", "allergies", "--level", "friend")

    assert code == 1
    assert "pass --value" in err
    assert "allergies" not in load_profile("om").facts


def test_fact_set_rejects_self_as_a_fact_level(data_dir: Path, run) -> None:
    code, _out, err = run("--as", "om", "fact", "set", "diet", "--level", "self")

    assert code == 1
    assert "acquaintance, friend, close or private" in err


def test_fact_set_at_the_same_level_may_update_the_value(data_dir: Path, run) -> None:
    code, _out, _err = run(
        "--as", "om", "fact", "set", "drinks", "--level", "friend", "--value", "nothing, thanks"
    )

    assert code == 0
    fact = load_profile("om").facts["drinks"]
    assert fact.level is Level.FRIEND
    assert fact.value == "nothing, thanks"


# ---------------------------------------------------------------------------
# cal add
# ---------------------------------------------------------------------------


def test_cal_add_writes_the_event_and_is_idempotent(data_dir: Path, run) -> None:
    calendar = data_dir / "om" / "calendar.ics"
    before = calendar.read_bytes()

    argv = (
        "--as",
        "om",
        "cal",
        "add",
        "2026-11-08T21:00",
        "2h",
        "Bowling + dinner",
        "@",
        "Smaaash, Indiranagar",
        "--id",
        "P1",
    )
    code, out, err = run(*argv)

    assert code == 0
    assert err == ""
    assert "P1" in out and "21:00–23:00" in out
    first = calendar.read_bytes()
    assert first != before

    code, _out, _err = run(*argv)
    assert code == 0
    assert calendar.read_bytes() == first
    assert first.count(b"UID:P1") == 1

    start = datetime(2026, 11, 8, 20, 0, tzinfo=TIME_ZONE)
    end = datetime(2026, 11, 8, 23, 0, tzinfo=TIME_ZONE)
    blocks = busy(calendar, start, end)
    assert [(block.start.hour, block.end.hour, block.title) for block in blocks] == [
        (21, 23, "Bowling + dinner")
    ]


def test_cal_add_speaks_json_and_uses_kolkata_time(data_dir: Path, run) -> None:
    code, out, _err = run(
        "--json",
        "--as",
        "om",
        "cal",
        "add",
        "2026-11-08T21:00",
        "90m",
        "Bowling + dinner",
        "@",
        "Smaaash, Indiranagar",
        "--id",
        "p2",
    )

    assert code == 0
    payload = json.loads(out)
    assert payload["id"] == "P2"
    assert payload["start"] == "2026-11-08T21:00:00+05:30"
    assert payload["end"] == "2026-11-08T22:30:00+05:30"
    assert payload["title"] == "Bowling + dinner"
    assert payload["place"] == "Smaaash, Indiranagar"


def test_cal_add_without_an_id_still_writes_once(data_dir: Path, run) -> None:
    calendar = data_dir / "om" / "calendar.ics"
    argv = ("--as", "om", "cal", "add", "2026-11-08T21:00", "2h", "Bowling", "@", "Smaaash")

    assert run(*argv)[0] == 0
    first = calendar.read_bytes()
    assert run(*argv)[0] == 0
    assert calendar.read_bytes() != first  # no --id: a second event is expected


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("2026-11-08T21:00", "soon", "Bowling", "@", "Smaaash"), "duration"),
        (("not a date at all", "2h", "Bowling", "@", "Smaaash"), "start"),
        (("2026-11-08T21:00", "2h", "Bowling @ home", "@", "Smaaash"), "title"),
        (("2026-11-08T21:00", "2h", "Bowling", "@", "Somewhere / else"), "place"),
        (("2026-11-08T21:00", "2h", "Bowling", "at", "Smaaash"), 'put "@"'),
    ],
)
def test_cal_add_rejects_bad_input_without_touching_the_file(
    data_dir: Path, run, args: tuple[str, ...], message: str
) -> None:
    calendar = data_dir / "om" / "calendar.ics"
    before = calendar.read_bytes()

    code, _out, err = run("--as", "om", "cal", "add", *args)

    assert code == 1
    assert message in err
    assert calendar.read_bytes() == before


# ---------------------------------------------------------------------------
# view-as
# ---------------------------------------------------------------------------


def test_view_as_rahul_and_priya_print_different_correct_tables(data_dir: Path, run) -> None:
    rahul_code, rahul, _err = run("--as", "om", "view-as", "rahul")
    priya_code, priya, _err = run("--as", "om", "view-as", "priya")

    assert rahul_code == 0
    assert priya_code == 0
    assert rahul != priya
    assert "view-as rahul — close" in rahul
    assert "neighbourhood  Indiranagar" in rahul
    assert "view-as priya — friend" in priya
    assert "❌ neighbourhood  not shared at this level" in priya
    assert "❌ address" in rahul and "❌ address" in priya


def test_view_as_speaks_json(data_dir: Path, run) -> None:
    code, out, _err = run("--json", "--as", "om", "view-as", "rahul")

    assert code == 0
    payload = json.loads(out)
    assert payload["owner"] == "om"
    assert payload["person"] == "rahul"
    assert payload["level"] == "close"
    assert payload["days"] == 7
    facts = {row["name"]: row for row in payload["facts"]}
    assert facts["address"]["visible"] is False
    assert facts["wishlist"]["visible"] is True
    assert facts["wishlist"]["value"][0]["item"] == "Catan Seafarers"
    assert payload["titles_visible"] is True
    assert set(payload["window"]) == {"start", "end"}


def test_view_as_a_stranger_shares_nothing(data_dir: Path, run) -> None:
    code, out, _err = run("--as", "om", "view-as", "dev")
    assert code == 0
    assert "not on your list → nothing" in out

    code, out, _err = run("--json", "--as", "om", "view-as", "dev")
    assert code == 0
    payload = json.loads(out)
    assert payload["level"] is None
    assert payload["facts"] == []
    assert payload["calendar"] == []


def test_view_as_rejects_a_non_positive_window(data_dir: Path, run) -> None:
    code, _out, err = run("--as", "om", "view-as", "rahul", "--days", "0")

    assert code == 1
    assert "--days" in err


def test_view_as_reads_the_committed_fixtures_without_writing(
    monkeypatch: pytest.MonkeyPatch, run
) -> None:
    monkeypatch.delenv("TN_DATA_DIR", raising=False)
    monkeypatch.delenv("TN_PERSON", raising=False)
    paths = [
        path for person in ("om", "rahul", "priya") for path in (EXAMPLES_DIR / person).iterdir()
    ]
    before = {path: path.read_bytes() for path in paths}

    code, out, _err = run("--as", "om", "view-as", "rahul")

    assert code == 0
    assert "view-as rahul — close" in out
    assert {path: path.read_bytes() for path in paths} == before


# ---------------------------------------------------------------------------
# Parser, --as / $TN_PERSON and exit codes
# ---------------------------------------------------------------------------


def test_as_falls_back_to_tn_person(data_dir: Path, monkeypatch: pytest.MonkeyPatch, run) -> None:
    monkeypatch.setenv("TN_PERSON", "om")

    code, out, _err = run("view-as", "priya")

    assert code == 0
    assert "view-as priya — friend" in out


def test_missing_person_is_an_error(data_dir: Path, run) -> None:
    code, _out, err = run("fact", "get")

    assert code == 1
    assert "pass --as <person> or set TN_PERSON" in err


def test_json_flag_works_before_or_after_the_subcommand(data_dir: Path, run) -> None:
    first = run("--json", "--as", "om", "fact", "get", "diet")
    second = run("fact", "get", "diet", "--json", "--as", "om")

    assert first[0] == second[0] == 0
    assert json.loads(first[1]) == json.loads(second[1])


def test_help_returns_zero_and_unknown_commands_return_two(run) -> None:
    code, out, _err = run("--help")
    assert code == 0
    assert "usage: tn" in out

    code, _out, err = run("nope")
    assert code == 2
    assert "invalid choice" in err
