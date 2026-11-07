import pytest
from planning_flows import Planning
from product_flows import SCENARIOS


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.__name__)
async def test_product_scenario(tmp_path, monkeypatch, scenario):
    harness = Planning(tmp_path / "profiles", monkeypatch)
    await harness.setup()
    await scenario(harness)
