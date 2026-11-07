"""Structural rules for recognising Switch's automatic, non-meaningful messages.

The consent speak-first guard and the personal watcher both need to tell a real
message from the two kinds of Switch-produced noise a room always carries: the
automatic join greeting, and gate-to-gate protocol traffic. They share the
greeting rule here so the two cannot drift apart.

Both rules are deliberately structural only — sender identity, message kind and
timing relative to a ``room_join`` — never the words a message carries.
AGENTS.md forbids judging meaning with regexes or keyword lists.
"""

#: Switch posts an automatic "Hi there! Just @… me when you're ready." under a
#: member's own name within this many milliseconds of that member's ``room_join``.
GREETING_WINDOW_MS = 2_000


def sender_name(message):
    """The Switch identity that sent ``message``, across naming schemes."""
    return message.get("sender_name") or message.get("sender")


def join_greeting_ids(messages, *, sender=None):
    """The ids of Switch's automatic join greetings among ``messages``.

    Switch records a ``room_join`` for a member, then posts a greeting under that
    same member's name within ``GREETING_WINDOW_MS``. A message is a greeting when
    its sender's most recent ``room_join`` falls inside that window. ``sender``
    restricts the scan to one identity; without it, every member's greeting is
    recognised.
    """
    greetings = set()
    joined_at = {}
    for message in sorted(messages, key=lambda m: m.get("timestamp", 0)):
        who = sender_name(message)
        if message.get("kind") == "room_join":
            joined_at[who] = message.get("timestamp", 0)
            continue
        if sender is not None and who != sender:
            continue
        joined = joined_at.get(who)
        if joined is not None and message.get("timestamp", 0) - joined < GREETING_WINDOW_MS:
            greetings.add(message.get("id"))
    return greetings


def is_gate_traffic(message):
    """Whether ``message`` is gate-to-gate protocol traffic.

    True when the sender is a gate (``<person>-gate``) and the body addresses a
    gate (``@<other>-gate …``), as with a plan-relay envelope or a forwarded
    ``propose``/``consent``. Purely structural: sender identity and the leading
    addressee, never the message's meaning.
    """
    who = sender_name(message)
    if not isinstance(who, str) or not who.endswith("-gate"):
        return False
    body = message.get("body") or ""
    if not body.lstrip().startswith("@"):
        return False
    addressee = body.lstrip()[1:].split(None, 1)[0]
    return addressee.endswith("-gate")
