"""Runtime files come from the package, so a wheel installed elsewhere has them.

The install E2E (``scripts/e2e_install.py``) proves this against a built wheel.
These checks fail first, without a build, if a resource or its loader goes away.
"""

from pathlib import Path

from trustnet import resources
from trustnet.gate.identity import write_identity_export

RUNTIME_FILES = (
    resources.IDENTITY_EXPORT,
    resources.SHARE_CARD_TEMPLATE,
    resources.SKILL,
    resources.WATCH_PROMPT,
)


def test_every_runtime_file_is_readable_from_the_package() -> None:
    for name in RUNTIME_FILES:
        assert resources.read_text(name).strip(), name


def test_the_identity_exporter_is_written_where_the_caller_asks(tmp_path: Path) -> None:
    path = write_identity_export(tmp_path / "scripts")

    assert path == tmp_path / "scripts" / resources.IDENTITY_EXPORT
    assert "asyncpg" in path.read_text(encoding="utf-8")
    assert path.stat().st_mode & 0o777 == 0o700
