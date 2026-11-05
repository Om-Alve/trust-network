"""Verify that every scaffold module imports."""

import importlib

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "trustnet.__init__",
        "trustnet.switch_client",
        "trustnet.gate.__init__",
        "trustnet.gate.__main__",
        "trustnet.gate.policy",
        "trustnet.gate.facts",
        "trustnet.gate.calendar",
        "trustnet.gate.commands",
        "trustnet.gate.relay",
        "trustnet.gate.surprise",
        "trustnet.gate.ledger",
        "trustnet.gate.envoy",
        "trustnet.tn.__init__",
        "trustnet.tn.cli",
        "trustnet.tn.mcp",
    ],
)
def test_import(module_name: str) -> None:
    assert importlib.import_module(module_name).__name__ == module_name
