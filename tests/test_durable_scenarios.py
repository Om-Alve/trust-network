import pytest
from durable_flows import SCENARIOS
from planning_flows import Planning


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda f: f.__name__)
async def test_durable_scenario(scenario, tmp_path, monkeypatch):
    h = Planning(tmp_path, monkeypatch)
    await h.setup()
    await scenario(h)
