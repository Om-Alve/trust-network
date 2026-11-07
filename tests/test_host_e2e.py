"""End-to-end onboarding over real HTTP with a fake Switch Gateway.

Every scenario runs the shipped argparse registration and handlers against a
temporary config directory, invite database and threaded host server.
"""

from __future__ import annotations

import pytest
from host_flows import SCENARIOS, HostHarness


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_host_onboarding(name: str, tmp_path) -> None:
    with HostHarness(tmp_path / name) as harness:
        details = SCENARIOS[name](harness)
    assert details is not None


def test_server_never_logs_credentials(tmp_path, capsys) -> None:
    with HostHarness(tmp_path) as harness:
        info = harness.invite("alice")
        response = harness.redeem(info["token"], "log-check")
        assert response.status_code == 200, response.text
        bundle = response.json()
        assert harness.identities(bundle["identity_token"]).status_code == 200

    captured = capsys.readouterr()
    written = captured.out + captured.err
    for secret in (
        bundle["registration_key"],
        info["token"],
        bundle["identity_token"],
        harness.gateway.admin_password,
    ):
        assert secret not in written
