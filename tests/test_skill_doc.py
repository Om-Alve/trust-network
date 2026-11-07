"""SKILL.md is what agents learn the gate commands from; PROTOCOL.md is the spec.

Ways it can go wrong, and what this file checks:
- the front matter lacks ``name``/``description``, so Hermes never loads the skill;
- an example gate command no longer parses (syntax drifted), or parses as an
  unknown verb, so an agent copies a line the gate ignores;
- the code blocks lose their examples, so the check above passes on nothing;
- PROTOCOL.md shows a command (in a code block or inline) the parser doesn't accept,
  so a framework built from the spec sends lines the gates ignore.
"""

import re

import yaml

from trustnet import resources
from trustnet.gate.commands import Unknown, parse
from trustnet.gate.facts import REPO_ROOT

SKILL_TEXT = resources.read_text(resources.SKILL)
PROTOCOL = REPO_ROOT / "PROTOCOL.md"


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
    meta = _front_matter(SKILL_TEXT)
    assert meta["name"] == "trust-network"
    assert meta["description"].strip()


def test_every_gate_example_parses() -> None:
    lines = _gate_lines(SKILL_TEXT)
    assert len(lines) >= 4
    for line in lines:
        command = parse(line)
        assert not isinstance(command, Unknown), line


def test_every_command_in_the_protocol_spec_parses() -> None:
    text = PROTOCOL.read_text(encoding="utf-8")
    inline = [span.strip() for span in re.findall(r"`([^`\n]+)`", text)]
    lines = _gate_lines(text) + [s for s in inline if re.match(r"@[a-z]+-gate [a-z]", s)]
    # Grammar templates (<n>) and the gift tool's JSON envelope ({...}, read by the
    # gift module before the parser) aren't sendable lines.
    lines = [line for line in lines if "<" not in line and "{" not in line]
    assert len(lines) >= 15
    for line in lines:
        assert not isinstance(parse(line), Unknown), line
