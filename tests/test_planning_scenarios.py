"""Real gates over FakeSwitch: planning, authority, restarts and transport recovery."""

import pytest
from planning_flows import SCENARIOS, Planning


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.__name__)
async def test_planning_scenario(scenario, tmp_path, monkeypatch):
    harness = Planning(tmp_path, monkeypatch)
    await harness.setup()
    await scenario(harness)
