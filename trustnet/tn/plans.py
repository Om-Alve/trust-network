"""Agent-facing tools for authenticated group plans.

``request`` submits one structured ``plan-request {JSON}`` line through the
person's own home room and returns the correlation token. Reading and status
never touch Switch: ``list`` and ``status`` read the gate's durable local
projection only, so an agent can check progress between turns without waking a
peer.

The gate, not this module, authorizes the request. In particular, drafting is
accepted only from the owner's main agent, and voting or cancelling only from
the owner's Switch user or (in ``via-agent`` consent mode) the main agent.
"""

from __future__ import annotations

import json
import secrets

from trustnet.gate import group_plans
from trustnet.room_pool import wait_until_live
from trustnet.tn import personal

__all__ = ["list", "list_plans", "plan_status", "request", "status"]

ACTIONS = frozenset({"create", "propose", "revise", "replace", "vote", "cancel"})


async def request(person: str, action: str, **payload) -> str:
    """Send one plan command from the person's home, returning its token."""
    action = action.strip().lower()
    if action not in ACTIONS:
        raise ValueError(f"unknown plan action {action!r}")
    token = payload.pop("token", None) or secrets.token_hex(16)
    command = {"action": action, "token": token, **payload}
    text = f"@{person}-gate plan-request " + json.dumps(
        command, ensure_ascii=False, separators=(",", ":")
    )
    async with personal.session(person) as client:
        room = await personal.home(person, client)
        await client.connect_to_room(room)
        await wait_until_live(client, room, text)
        await client.post_message(text)
    return token


def list(person: str) -> list[dict]:
    """Every plan in this owner's durable local projection, oldest first."""
    plans = [group_plans.summary(plan) for plan in group_plans.projection(person)["plans"].values()]
    return sorted(plans, key=lambda plan: plan.get("created_at", 0))


def status(person: str, reference: str) -> dict | None:
    """One plan by immutable id or submitted token, from local state only."""
    return group_plans.status(person, reference)


#: Descriptive aliases for code that prefers explicit names.
list_plans = list
plan_status = status
