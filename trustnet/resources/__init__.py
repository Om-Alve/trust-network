"""Runtime files that ship inside the wheel.

These live beside the code, not in the repository's ``templates/``, ``skills/``
or ``scripts/`` directories, so an installed copy has them where Python can find
them. Load them through :func:`read_text`, which uses ``importlib.resources`` and
therefore also works from a zipped wheel.

``gate_identity_export.py`` is a script, not a module: it is materialized into a
temporary directory and run by the Switch core's own Python, which has
``asyncpg``. Nothing imports it here.
"""

from importlib.resources import files

__all__ = [
    "IDENTITY_EXPORT",
    "SHARE_CARD_TEMPLATE",
    "SKILL",
    "WATCH_PROMPT",
    "read_text",
]

IDENTITY_EXPORT = "gate_identity_export.py"
SHARE_CARD_TEMPLATE = "envoy-brief.md.j2"
SKILL = "SKILL.md"
WATCH_PROMPT = "tn-watch-prompt.md"


def read_text(name: str) -> str:
    """Return one packaged runtime file as text."""
    return files(__name__).joinpath(name).read_text(encoding="utf-8")
