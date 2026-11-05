"""SKILL.md is what both Hermes profiles learn the gate commands from.

Ways it can go wrong, and what this file checks:
- the front matter lacks ``name``/``description``, so Hermes never loads the skill;
- an example gate command no longer parses (syntax drifted), or parses as an
  unknown verb, so an agent copies a line the gate ignores;
- the code blocks lose their examples, so the check above passes on nothing.
"""

import re

import yaml

from trustnet.gate.commands import Unknown, parse
from trustnet.gate.facts import REPO_ROOT

SKILL = REPO_ROOT / "skills" / "trust-network" / "SKILL.md"


def _front_matter(text: str) -> dict:
    match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "SKILL.md must start with --- front matter ---"
    return yaml.safe_load(match.group(1))


def _gate_lines(text: str) -> list[str]:
    blocks = re.findall(r"```[a-z]*\n(.*?)```", text, re.DOTALL)
    return [
        line.strip()
        for block in blocks
        for line in block.splitlines()
        if re.match(r"@[a-z]+-gate ", line.strip())
    ]


def test_skill_front_matter_is_loadable() -> None:
    meta = _front_matter(SKILL.read_text(encoding="utf-8"))
    assert meta["name"] == "trust-network"
    assert meta["description"].strip()


def test_every_gate_example_parses() -> None:
    lines = _gate_lines(SKILL.read_text(encoding="utf-8"))
    assert len(lines) >= 5
    for line in lines:
        command = parse(line)
        assert not isinstance(command, Unknown), line
