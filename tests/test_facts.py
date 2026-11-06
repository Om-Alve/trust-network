"""Tests for trust lists, profiles and the fixtures the demo runs on."""

from pathlib import Path

import pytest
import yaml

from trustnet.gate import facts
from trustnet.gate.facts import (
    EXAMPLES_DIR,
    Fact,
    FactsError,
    Level,
    Profile,
    load_profile,
    load_profile_file,
    load_trust,
    load_trust_file,
    resolve_data_dir,
    save_profile,
    save_trust,
)

OM_DIR = EXAMPLES_DIR / "om"


def copy_fixture(person: str, target: Path) -> Path:
    """Copy a person's fixture files into ``target`` and return their facts file."""
    target.mkdir(parents=True, exist_ok=True)
    for filename in ("trust.yaml", "facts.yaml", "calendar.ics"):
        (target / filename).write_bytes((EXAMPLES_DIR / person / filename).read_bytes())
    return target / "facts.yaml"


def test_levels_are_ordered() -> None:
    assert Level.ACQUAINTANCE < Level.FRIEND < Level.CLOSE < Level.PRIVATE < Level.SELF
    assert Level.CLOSE > Level.FRIEND
    assert Level.FRIEND >= Level.FRIEND
    assert Level.ACQUAINTANCE <= Level.CLOSE
    assert Level.SELF > Level.PRIVATE


def test_only_rooms_and_fact_tags_get_their_levels() -> None:
    assert Level.FRIEND.is_viewer
    assert Level.CLOSE.is_viewer
    assert not Level.PRIVATE.is_viewer
    assert not Level.SELF.is_viewer
    assert Level.PRIVATE.is_fact_tag
    assert not Level.SELF.is_fact_tag


def test_fact_rejects_a_self_level() -> None:
    with pytest.raises(FactsError, match="fact level"):
        Fact(value="secret", level=Level.SELF)


@pytest.mark.parametrize("person", ["om", "rahul", "priya"])
def test_every_fixture_loads(person: str) -> None:
    profile = load_profile(person)
    trust = load_trust(person)

    assert profile.owner == person
    assert profile.calendar_path.is_file()
    assert trust.consent_default in {"direct", "via-agent"}
    assert trust.envoy_provider == ("opencode" if person == "priya" else "")


def test_om_matches_the_plan() -> None:
    profile = load_profile("om")
    trust = load_trust("om")

    assert trust.people == {"rahul": Level.CLOSE, "priya": Level.FRIEND}
    assert trust.consent_default == "via-agent"
    assert trust.envoy_provider == ""

    assert profile.facts["diet"] == Fact("vegetarian", Level.ACQUAINTANCE)
    assert profile.facts["drinks"] == Fact("no alcohol", Level.FRIEND)
    assert profile.facts["neighbourhood"].level is Level.CLOSE
    assert profile.facts["address"].level is Level.PRIVATE
    assert profile.facts["wishlist"].level is Level.CLOSE
    assert profile.facts["wishlist"].value == [
        {"item": "Lego Millennium Falcon", "price": 2500},
        {"item": "Hario V60", "price": 2000},
        {"item": "Kindle Paperwhite", "price": 14000},
    ]


def test_rahul_is_close_to_om_and_has_no_tent() -> None:
    profile = load_profile("rahul")
    trust = load_trust("rahul")

    assert trust.level_for("om") is Level.CLOSE
    assert trust.consent_default == "via-agent"
    assert trust.envoy_provider == ""
    assert {fact.level for fact in profile.facts.values()} == {
        Level.ACQUAINTANCE,
        Level.FRIEND,
        Level.CLOSE,
        Level.PRIVATE,
    }
    everything = repr(profile.facts).lower()
    assert "tent" not in everything


def test_priya_can_offer_a_tent_at_friend_level() -> None:
    profile = load_profile("priya")
    trust = load_trust("priya")

    assert trust.level_for("om") is Level.FRIEND
    assert profile.facts["has"].level is Level.FRIEND
    assert "2-person tent" in profile.facts["has"].value
    assert "dentist" in profile.facts["recommends"].value


@pytest.mark.parametrize(
    ("bad_level", "message"),
    [
        ("buddy", "unknown level 'buddy'"),
        ("private", "not allowed here"),
        ("self", "not allowed here"),
    ],
)
def test_trust_rejects_bad_levels(tmp_path: Path, bad_level: str, message: str) -> None:
    path = tmp_path / "trust.yaml"
    path.write_text(
        f"people:\n  rahul: {bad_level}\nconsent:\n  default: direct\n",
        encoding="utf-8",
    )
    with pytest.raises(FactsError, match=message):
        load_trust_file(path)


@pytest.mark.parametrize(
    ("bad_level", "message"),
    [
        ("buddy", "unknown level 'buddy'"),
        ("self", "not allowed here"),
    ],
)
def test_profile_rejects_bad_levels(tmp_path: Path, bad_level: str, message: str) -> None:
    facts = copy_fixture("om", tmp_path)
    data = yaml.safe_load(facts.read_text(encoding="utf-8"))
    data["facts"]["diet"]["level"] = bad_level
    facts.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(FactsError, match=message):
        load_profile_file(facts)


def test_trust_rejects_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "trust.yaml"
    path.write_text(
        "people:\n  rahul: close\nfriends:\n  priya: friend\n",
        encoding="utf-8",
    )
    with pytest.raises(FactsError, match="unknown key"):
        load_trust_file(path)


def test_profile_rejects_unknown_keys(tmp_path: Path) -> None:
    facts = copy_fixture("om", tmp_path)
    data = yaml.safe_load(facts.read_text(encoding="utf-8"))
    data["facts"]["diet"]["note"] = "typo"
    facts.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(FactsError, match="unknown key"):
        load_profile_file(facts)

    data["facts"]["diet"].pop("note")
    data["calendars"] = data.pop("calendar")
    facts.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(FactsError, match="unknown key"):
        load_profile_file(facts)


def test_profile_rejects_a_missing_calendar(tmp_path: Path) -> None:
    facts = copy_fixture("om", tmp_path)
    (tmp_path / "calendar.ics").unlink()

    with pytest.raises(FactsError, match="calendar file not found"):
        load_profile_file(facts)


def test_missing_files_say_which_file(tmp_path: Path) -> None:
    with pytest.raises(FactsError, match="trust.yaml: file not found"):
        load_trust_file(tmp_path / "trust.yaml")
    with pytest.raises(FactsError, match="facts.yaml: file not found"):
        load_profile_file(tmp_path / "facts.yaml")


def test_empty_trust_file_loads_defaults(tmp_path: Path) -> None:
    path = tmp_path / "trust.yaml"
    path.write_text("", encoding="utf-8")

    trust = load_trust_file(path)

    assert trust.people == {}
    assert trust.consent_default == "direct"
    assert trust.envoy_provider == ""


def test_trust_round_trip_keeps_key_order(tmp_path: Path) -> None:
    trust = load_trust_file(OM_DIR / "trust.yaml")
    out = tmp_path / "trust.yaml"

    save_trust(trust, out)
    again = load_trust_file(out)

    assert again == trust
    written = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert list(written) == ["people", "consent", "envoy"]
    assert list(written["people"]) == ["rahul", "priya"]


def test_profile_round_trip(tmp_path: Path) -> None:
    profile = load_profile("om")
    out = copy_fixture("om", tmp_path / "om")
    local = Profile(
        owner="om",
        facts=profile.facts,
        calendar_path=tmp_path / "om" / "calendar.ics",
    )

    save_profile(local, out)
    again = load_profile_file(out)

    assert again.owner == "om"
    assert again.facts == profile.facts
    assert again.calendar_path == (tmp_path / "om" / "calendar.ics").resolve()
    written = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert written["calendar"] == "./calendar.ics"
    assert list(written["facts"]) == list(profile.facts)


def test_default_data_dir_ignores_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TN_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)

    assert resolve_data_dir("om") == EXAMPLES_DIR / "om"
    assert load_profile("om").calendar_path.is_file()


def test_tn_data_dir_overrides_the_examples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copy_fixture("om", tmp_path / "om")
    monkeypatch.setenv("TN_DATA_DIR", str(tmp_path))

    profile = load_profile("om")

    assert resolve_data_dir("om") == (tmp_path / "om").resolve()
    assert profile.owner == "om"
    assert profile.calendar_path == (tmp_path / "om" / "calendar.ics").resolve()


def test_an_installed_copy_without_a_data_dir_asks_for_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TN_DATA_DIR", raising=False)
    monkeypatch.setattr(facts, "EXAMPLES_DIR", tmp_path / "not-a-checkout")

    with pytest.raises(FactsError, match="TN_DATA_DIR"):
        resolve_data_dir("om")


def test_person_names_cannot_escape_the_data_dir() -> None:
    with pytest.raises(FactsError, match="invalid person name"):
        resolve_data_dir("../rahul")
