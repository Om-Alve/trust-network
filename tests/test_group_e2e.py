import pytest
from group_flows import SCENARIOS


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.__name__)
async def test_group_e2e(tmp_path, monkeypatch, scenario):
    await scenario(tmp_path, monkeypatch)
