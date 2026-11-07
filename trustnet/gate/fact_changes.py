"""Owner-local fact and trust suggestions, reviewed under the plan consent rule."""

import fcntl
import hashlib
import json
import re
import time
from contextlib import contextmanager

from trustnet.gate import ledger, storage
from trustnet.gate.dm import main_agent
from trustnet.gate.facts import (
    FACTS_FILENAME,
    Fact,
    FactsError,
    Level,
    load_profile,
    load_trust,
    resolve_data_dir,
    save_profile,
    save_trust,
)
from trustnet.gate.policy import Actor, Identity, can_set_level, fact_is_visible, share_consent

_now = time.time
TTL = 7 * 86400


@contextmanager
def editing(person):
    directory = resolve_data_dir(person)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "fact-changes.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _recover(person, _load(person))
        yield


def _load(person):
    return storage.load(person, "fact-changes")


def _save(person, state):
    storage.save(person, "fact-changes", state)


def _recover(person, state):
    for ref, item in state.items():
        if item["status"] != "applying":
            continue
        key, after = item["key"], Level(item["after"])
        if ref.startswith("F"):
            profile = load_profile(person)
            fact = profile.facts.get(key)
            if (
                fact is None
                or _fingerprint(fact) != item["fingerprint"]
                or fact.level.value not in {item["before"], item["after"]}
            ):
                raise FactsError(f"{ref} conflicts with an interrupted approval")
            fact.level = after
            save_profile(profile, resolve_data_dir(person) / FACTS_FILENAME)
        else:
            trust = load_trust(person)
            if trust.is_blocked(key):
                item["status"] = "declined"
                item["reason"] = "Person was blocked before approval completed"
                _save(person, state)
                continue
            before = trust.level_for(key)
            if (before.value if before else "unlisted") not in {item["before"], item["after"]}:
                raise FactsError(f"{ref} conflicts with an interrupted approval")
            trust.grant(key, after)
            save_trust(trust, resolve_data_dir(person) / "trust.yaml")
        _record(person, ref, key, item["before"], item["after"])
        item["status"] = "approved"
        _save(person, state)


def recover(person):
    directory = resolve_data_dir(person)
    if (
        not (directory / "decisions.sqlite3").exists()
        and not (directory / "fact-changes.json").exists()
    ):
        return
    with editing(person):
        pass


def _key(key):
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", key):
        raise FactsError("fact key must be 1-64 lowercase letters, digits, underscores or hyphens")
    return key


def _level(level, trust=False):
    try:
        parsed = Level(level)
    except ValueError:
        raise FactsError(f"unknown suggested level {level!r}") from None
    if not (parsed.is_viewer if trust else parsed.is_fact_tag):
        raise FactsError("invalid suggested level")
    return parsed


def add(person, key, value):
    key = _key(key)
    if len(value) > 16384:
        raise FactsError("fact value must be at most 16384 characters")
    from trustnet.tn.cli import _parse_value

    parsed = _parse_value(value)
    # Reject YAML objects that the ledger/MCP cannot represent.
    try:
        json.dumps(parsed, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        raise FactsError("value must contain JSON-compatible strings, lists or maps") from None
    if not isinstance(parsed, (str, list, dict)):
        raise FactsError("value must be a string, list or map")
    with editing(person):
        profile = load_profile(person)
        if key in profile.facts:
            raise FactsError(
                f"{key} already exists; tighten with fact_set; changing an existing visible "
                "value is the person's job"
            )
        profile.facts[key] = Fact(parsed, Level.PRIVATE)
        save_profile(profile, resolve_data_dir(person) / FACTS_FILENAME)
    return {"fact": key, "level": "private", "created": True}


def _audience(person, level, key):
    trust = load_trust(person)
    return [
        f"{name} ({tag.value})"
        for name, tag in sorted(trust.people.items())
        if not trust.is_blocked(name)
        and fact_is_visible(
            level,
            tag,
            allowed=key in trust.permissions_for(name).allow,
            denied=key in trust.permissions_for(name).deny,
        )
    ]


def _fingerprint(fact):
    return hashlib.sha256(json.dumps(fact.value, default=str).encode()).hexdigest()


def _effect(ref, item):
    viewers = ", ".join(item["audience"]) or "nobody"
    return f"{ref}: {item['key']} {item['before']} → {item['after']}. Who could see it: {viewers}"


def suggest(person, key, level, reason="", *, trust=False):
    if len(reason) > 280:
        raise FactsError("reason must be at most 280 characters")
    level = _level(level, trust)
    with editing(person):
        if trust:
            # Reuse the trust-list name validation.
            if len(key) > 64:
                raise FactsError("person name must be at most 64 characters")
            trust_list = load_trust(person)
            if trust_list.is_blocked(key):
                raise FactsError(f"{key} is blocked; unblock them before suggesting trust")
            before = trust_list.level_for(key)
            key = key.strip().lower()
            if key == person:
                raise FactsError("cannot suggest trusting yourself")
            item = {
                "before": before.value if before else "unlisted",
                "audience": [f"{key} ({level.value})"],
            }
            prefix = "T"
        else:
            key = _key(key)
            profile = load_profile(person)
            if key not in profile.facts:
                raise FactsError(f"no fact named {key}")
            fact = profile.facts[key]
            before = fact.level
            if can_set_level(before, level, Actor.AGENT):
                fact.level = level
                save_profile(profile, resolve_data_dir(person) / FACTS_FILENAME)
                _record(person, "", key, before.value, level.value)
                return {"status": "applied", "fact": key, "level": level.value}
            item = {
                "before": before.value,
                "audience": _audience(person, level, key),
                "fingerprint": _fingerprint(fact),
            }
            prefix = "F"
        state = _load(person)
        number = 1 + max((int(r[1:]) for r in state if r.startswith(prefix)), default=0)
        ref = f"{prefix}{number}"
        item.update(
            key=key, after=level.value, reason=reason, status="pending", expires=_now() + TTL
        )
        item["effect"] = _effect(ref, item)
        state[ref] = item
        _save(person, state)
        return {"ref": ref, **item}


def review(person):
    with editing(person):
        state = _load(person)
        _recover(person, state)
        changed = False
        for item in state.values():
            if item["status"] == "pending" and item["expires"] <= _now():
                item["status"] = "expired"
                changed = True
        if changed:
            _save(person, state)
        return [
            {"ref": ref, "kind": "trust" if ref.startswith("T") else "fact", **item}
            for ref, item in state.items()
            if item["status"] == "pending"
        ]


def _record(person, ref, key, before, after):
    ledger.record(
        key,
        {"before": before, "after": after, "ref": ref},
        person,
        "local-review",
        "trust-change" if ref.startswith("T") else "fact-visibility",
        person=person,
        operation_id=f"review:{ref}" if ref else None,
    )


def decide(person, refs, approve, *, sender=None):
    sender = sender or Identity.user(person)
    if isinstance(refs, str):
        refs = [refs]
    if not refs or len(refs) > 100 or any(not re.fullmatch(r"[FT][1-9][0-9]*", r) for r in refs):
        raise FactsError("provide 1-100 F or T refs")
    results = []
    with editing(person):
        decision = share_consent(
            sender, person, load_trust(person).consent_default, [main_agent(person)]
        )
        if not decision:
            raise FactsError(decision.reason)
        state = _load(person)
        _recover(person, state)
        for ref in refs:
            item = state.get(ref)
            if not item or item["status"] != "pending":
                raise FactsError(f"{ref} is not pending")
            if item["expires"] <= _now():
                item["status"] = "expired"
                _save(person, state)
                raise FactsError(f"{ref} expired")
            if approve:
                key, after = item["key"], Level(item["after"])
                if ref.startswith("F"):
                    profile = load_profile(person)
                    fact = profile.facts.get(key)
                    if (
                        fact is None
                        or fact.level.value != item["before"]
                        or _fingerprint(fact) != item["fingerprint"]
                        or _audience(person, after, key) != item["audience"]
                    ):
                        raise FactsError(f"{ref} changed; request a fresh review")
                else:
                    trust = load_trust(person)
                    if trust.is_blocked(key):
                        raise FactsError(
                            f"{key} is blocked; unblock them and request a fresh review"
                        )
                    before = trust.level_for(key)
                    if (before.value if before else "unlisted") != item["before"]:
                        raise FactsError(f"{ref} changed; request a fresh review")
            item["status"] = "applying" if approve else "declined"
            item["via"] = decision.mode
            _save(person, state)
            _recover(person, state)
            results.append({"ref": ref, **item})
    return {"results": results}
