"""Exercise the agent's tools and the real gate disclosure path over FakeSwitch."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.e2e_agent_facts_scenarios import onboarding, scenario


async def test_private_facts_and_consent(tmp_path):
    await scenario(tmp_path)


async def test_memory_onboarding_and_bulk_review(tmp_path):
    await onboarding(tmp_path)
