"""Tests for the append-only disclosure ledger and its sealed entries.

Rule 6 (a brief discloses every fact in it) and the Scene 2 seal live here.
The ledger always points at ``TN_DATA_DIR``, which every test sets to
``tmp_path``, so nothing writes into ``examples/``.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from trustnet.gate import ledger
from trustnet.gate.ledger import LedgerError

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 11, 5, 18, 0, tzinfo=IST)
OPENING = date(2026, 11, 21)


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TN_DATA_DIR", str(tmp_path))
    return tmp_path


def lines_of(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


# --------------------------------------------------------------------------
# Where the ledger lives, and what one entry is
# --------------------------------------------------------------------------


def test_ledger_path_is_the_data_dir_of_the_person(data_dir: Path) -> None:
    assert ledger.ledger_path("om") == (data_dir / "om" / "ledger.jsonl").resolve()


def test_record_appends_one_json_object_per_entry(data_dir: Path) -> None:
    first = ledger.record(
        "diet", "vegetarian", "rahul", "dm-om-rahul-sat", "answer", person="om", now=NOW
    )
    ledger.record("city", "Bangalore", "rahul", "dm-om-rahul-sat", "answer", person="om", now=NOW)

    path = ledger.ledger_path("om")
    rows = [json.loads(line) for line in lines_of(path)]
    assert len(rows) == 2
    assert list(rows[0]) == ["ts", "field", "value", "to", "room", "kind"]
    assert rows[0]["ts"] == NOW.isoformat()
    assert rows[0]["field"] == "diet"
    assert rows[0]["value"] == "vegetarian"
    assert rows[0]["to"] == "rahul"
    assert rows[0]["room"] == "dm-om-rahul-sat"
    assert rows[0]["kind"] == "answer"
    assert "sealed_until" not in rows[0]
    assert first.ts == NOW


def test_record_never_rewrites_earlier_lines(data_dir: Path) -> None:
    ledger.record("diet", "vegetarian", "rahul", "dm-om-rahul-sat", "answer", person="om", now=NOW)
    path = ledger.ledger_path("om")
    before = path.read_bytes()

    ledger.record("city", "Bangalore", "rahul", "dm-om-rahul-sat", "answer", person="om", now=NOW)
    after = path.read_bytes()

    assert after.startswith(before)
    assert len(after) > len(before)
    assert len(lines_of(path)) == 2


def test_read_returns_entries_oldest_first(data_dir: Path) -> None:
    early = ledger.record("diet", "vegetarian", "rahul", "room", "answer", person="om", now=NOW)
    late = ledger.record(
        "city",
        "Bangalore",
        "priya",
        "room",
        "answer",
        person="om",
        now=datetime(2026, 11, 6, 9, 0, tzinfo=IST),
    )
    assert ledger.read("om") == [early, late]


def test_read_tolerates_a_missing_ledger(data_dir: Path) -> None:
    assert ledger.read("om") == []


def test_read_raises_on_a_malformed_line_and_keeps_the_file(data_dir: Path) -> None:
    path = ledger.ledger_path("om")
    path.parent.mkdir(parents=True)
    broken = (
        b'{"ts": "not-a-date", "field": "diet", "value": "x", '
        b'"to": "rahul", "room": "r", "kind": "answer"}\n'
    )
    path.write_bytes(broken)

    with pytest.raises(LedgerError, match="invalid ts"):
        ledger.read("om")
    assert path.read_bytes() == broken


def test_no_code_path_rewrites_the_ledger() -> None:
    source = Path(ledger.__file__).read_text(encoding="utf-8")
    assert source.count(".open(") == 1
    assert '.open("a"' in source
    for forbidden in (".write_text(", ".truncate(", "os.replace", "shutil"):
        assert forbidden not in source


def test_values_round_trip_through_json(data_dir: Path) -> None:
    values = {
        "diet": "vegetarian",
        "interests": ["bowling", "board games"],
        "wishlist": [{"item": "Hario V60", "price": 2000}],
        "drinks": None,
        "has": True,
        "sizes": {"tshirt": "M"},
    }
    ledger.record_brief(values, "rahul", "dm-om-rahul-sat", person="om", now=NOW)

    stored = {entry.field: entry.value for entry in ledger.read("om")}
    assert stored == values


# --------------------------------------------------------------------------
# Rule 6: a brief discloses every fact in it
# --------------------------------------------------------------------------


def test_record_brief_writes_one_entry_per_fact_in_order(data_dir: Path) -> None:
    brief = {
        "diet": "vegetarian",
        "interests": ["bowling", "board games", "sci-fi"],
        "has": ["projector", "camping stove"],
        "address": "42, 12th Main, Indiranagar",
    }
    entries = ledger.record_brief(brief, "rahul", "dm-om-rahul-sat", person="om", now=NOW)

    assert [entry.field for entry in entries] == list(brief)
    assert all(entry.kind is ledger.Kind.BRIEF for entry in entries)
    assert all(entry.to == "rahul" and entry.room == "dm-om-rahul-sat" for entry in entries)
    assert {entry.ts for entry in entries} == {NOW}

    stored = ledger.read("om")
    assert len(stored) == len(brief)
    assert {entry.field for entry in stored} == set(brief)
    assert {entry.field: entry.value for entry in stored} == brief


def test_record_brief_does_not_write_for_an_empty_brief(data_dir: Path) -> None:
    assert ledger.record_brief({}, "rahul", "room", person="om", now=NOW) == []
    assert not ledger.ledger_path("om").exists()


def test_record_brief_can_seal_its_entries(data_dir: Path) -> None:
    entries = ledger.record_brief(
        {"wishlist": [{"item": "Catan Seafarers", "price": 2500}]},
        "rahul",
        "gift-rahul-om-bday",
        person="om",
        sealed_until=OPENING,
        now=NOW,
    )
    assert entries[0].sealed_until == OPENING
    assert ledger.read("om")[0].sealed_until == OPENING


# --------------------------------------------------------------------------
# Sealed entries: hidden, then revealed by time
# --------------------------------------------------------------------------


def sealed_entry() -> ledger.Entry:
    return ledger.record(
        "wishlist",
        [{"item": "Catan Seafarers", "price": 2500}],
        "rahul",
        "gift-rahul-om-bday",
        "gift",
        person="om",
        sealed_until=OPENING,
        now=NOW,
    )


def test_a_sealed_entry_is_hidden_until_its_day(data_dir: Path) -> None:
    entry = sealed_entry()

    before = ledger.owner_view(datetime(2026, 11, 5, 23, 59, tzinfo=IST), person="om")
    assert before.visible == ()
    assert before.sealed == (entry,)
    assert before.sealed_count == 1
    assert before.sealed_opens == OPENING
    assert before.sealed_line == "1 sealed entry, opens Nov 21"

    on_the_day = ledger.owner_view(datetime(2026, 11, 21, 0, 1, tzinfo=IST), person="om")
    assert on_the_day.visible == (entry,)
    assert on_the_day.sealed == ()
    assert on_the_day.sealed_opens is None
    assert on_the_day.sealed_line == ""


def test_sealed_entries_stay_hidden_for_the_whole_day_before(data_dir: Path) -> None:
    sealed_entry()
    view = ledger.owner_view(datetime(2026, 11, 20, 23, 59, tzinfo=IST), person="om")
    assert view.sealed_count == 1
    assert view.visible == ()


def test_sealed_until_accepts_an_iso_date_or_a_datetime(data_dir: Path) -> None:
    from_date = ledger.record(
        "a", 1, "rahul", "room", "gift", person="om", sealed_until="2026-11-21", now=NOW
    )
    from_datetime = ledger.record(
        "b",
        2,
        "rahul",
        "room",
        "gift",
        person="om",
        sealed_until=datetime(2026, 11, 21, 9, 0, tzinfo=IST),
        now=NOW,
    )
    assert from_date.sealed_until == OPENING
    assert from_datetime.sealed_until == OPENING


def test_a_bad_sealed_until_is_rejected(data_dir: Path) -> None:
    with pytest.raises(LedgerError, match="ISO date"):
        ledger.record(
            "a", 1, "rahul", "room", "gift", person="om", sealed_until="next Friday", now=NOW
        )


def test_several_seals_report_the_first_open_date(data_dir: Path) -> None:
    ledger.record(
        "a", 1, "rahul", "gift-1", "gift", person="om", sealed_until=date(2026, 12, 2), now=NOW
    )
    ledger.record(
        "b", 2, "rahul", "gift-2", "gift", person="om", sealed_until=date(2026, 11, 21), now=NOW
    )

    view = ledger.owner_view(NOW, person="om")
    assert view.sealed_line == "2 sealed entries, first opens Nov 21"


# --------------------------------------------------------------------------
# owner_view and format_ledger
# --------------------------------------------------------------------------


def test_owner_view_is_newest_first(data_dir: Path) -> None:
    older = ledger.record(
        "diet",
        "vegetarian",
        "rahul",
        "room",
        "answer",
        person="om",
        now=datetime(2026, 11, 5, 9, 0, tzinfo=IST),
    )
    newer = ledger.record(
        "city",
        "Bangalore",
        "rahul",
        "room",
        "answer",
        person="om",
        now=datetime(2026, 11, 5, 10, 0, tzinfo=IST),
    )
    assert ledger.owner_view(NOW, person="om").visible == (newer, older)


def test_format_ledger_groups_by_person_newest_first(data_dir: Path) -> None:
    ledger.record(
        "diet",
        "vegetarian",
        "rahul",
        "dm-om-rahul-sat",
        "answer",
        person="om",
        now=datetime(2026, 11, 5, 9, 0, tzinfo=IST),
    )
    ledger.record(
        "interests",
        ["reading", "hiking"],
        "priya",
        "conn-om-priya",
        "ask-around",
        person="om",
        now=datetime(2026, 11, 5, 10, 0, tzinfo=IST),
    )
    ledger.record(
        "city",
        "Bangalore",
        "rahul",
        "dm-om-rahul-sat",
        "answer",
        person="om",
        now=datetime(2026, 11, 5, 11, 0, tzinfo=IST),
    )

    text = ledger.format_ledger(NOW, person="om")
    lines = text.splitlines()

    assert lines[0] == "Shared: 3 entries · 2 people"
    assert lines.index("rahul") < lines.index("priya")
    assert text.index("city: Bangalore") < text.index("diet: vegetarian")
    assert "ask-around  reading, hiking" in text
    assert len(lines) <= ledger.DEFAULT_MAX_LINES


def test_format_ledger_shows_only_the_sealed_summary_for_a_sealed_gift(data_dir: Path) -> None:
    sealed_entry()
    assert ledger.format_ledger(NOW, person="om") == "1 sealed entry, opens Nov 21"


def test_format_ledger_keeps_the_sealed_line_with_other_entries(data_dir: Path) -> None:
    ledger.record("diet", "vegetarian", "rahul", "dm-om-rahul-sat", "answer", person="om", now=NOW)
    sealed_entry()

    lines = ledger.format_ledger(NOW, person="om").splitlines()
    assert lines[-1] == "1 sealed entry, opens Nov 21"
    assert any("diet: vegetarian" in line for line in lines)


def test_format_ledger_caps_the_output(data_dir: Path) -> None:
    brief = {f"fact-{number}": value for number, value in enumerate(range(30))}
    ledger.record_brief(brief, "rahul", "dm-om-rahul-sat", person="om", now=NOW)
    sealed_entry()

    text = ledger.format_ledger(NOW, person="om", max_lines=10)
    lines = text.splitlines()

    assert len(lines) <= 10
    assert lines[-1] == "1 sealed entry, opens Nov 21"
    assert any("more entries" in line for line in lines)


def test_format_ledger_keeps_the_cap_with_several_people(data_dir: Path) -> None:
    ledger.record("a", 1, "rahul", "room", "answer", person="om", now=NOW)
    ledger.record("b", 2, "priya", "room", "answer", person="om", now=NOW)

    text = ledger.format_ledger(NOW, person="om", max_lines=3)
    assert len(text.splitlines()) <= 3
    assert "more" in text


def test_format_ledger_on_an_empty_ledger(data_dir: Path) -> None:
    assert ledger.format_ledger(NOW, person="om") == "Nothing shared yet."


def test_format_ledger_rejects_a_tiny_max_lines(data_dir: Path) -> None:
    with pytest.raises(LedgerError, match="max_lines"):
        ledger.format_ledger(NOW, person="om", max_lines=2)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["dance", "", "  "])
def test_an_unknown_kind_is_rejected(data_dir: Path, kind: str) -> None:
    with pytest.raises(LedgerError, match="kind must be one of"):
        ledger.record("diet", "vegetarian", "rahul", "room", kind, person="om", now=NOW)


def test_a_kind_is_case_insensitive(data_dir: Path) -> None:
    entry = ledger.record("diet", "vegetarian", "rahul", "room", "GIFT", person="om", now=NOW)
    assert entry.kind is ledger.Kind.GIFT


@pytest.mark.parametrize("field", ["", "  ", None])
def test_a_field_must_be_a_string(data_dir: Path, field: object) -> None:
    with pytest.raises(LedgerError, match="field"):
        ledger.record(field, "vegetarian", "rahul", "room", "answer", person="om", now=NOW)


def test_to_and_room_must_be_strings(data_dir: Path) -> None:
    with pytest.raises(LedgerError, match="to"):
        ledger.record("diet", "vegetarian", "", "room", "answer", person="om", now=NOW)
    with pytest.raises(LedgerError, match="room"):
        ledger.record("diet", "vegetarian", "rahul", " ", "answer", person="om", now=NOW)


def test_a_non_json_value_is_rejected_without_writing(data_dir: Path) -> None:
    with pytest.raises(LedgerError, match="JSON"):
        ledger.record("tags", {"a", "b"}, "rahul", "room", "answer", person="om", now=NOW)
    assert not ledger.ledger_path("om").exists()


def test_a_naive_now_is_read_as_india_time(data_dir: Path) -> None:
    entry = ledger.record(
        "diet", "vegetarian", "rahul", "room", "answer", person="om", now=datetime(2026, 11, 5, 18)
    )
    assert entry.ts.utcoffset() == NOW.utcoffset()
    assert entry.ts.date() == date(2026, 11, 5)
