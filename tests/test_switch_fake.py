import pytest
from fakes.fake_switch import FakeSwitch

from trustnet.switch_client import SwitchAPI


async def test_visibility_addressing_archive():
    server = FakeSwitch()
    gate = server.client("gate", "om")
    friend = server.client("friend", "rahul")
    outsider = server.client("outsider", "priya")
    human = server.client("om", "om", kind="user")
    api: SwitchAPI = gate
    rid = (
        await api.create_room(
            "gift", "", ["gate", "friend"], internal_only=True, read_visibility="private"
        )
    )["room_id"]
    assert (await human.get_room_detail(rid))["internal_only"]
    with pytest.raises(PermissionError):
        await outsider.get_room_detail(rid)
    await gate.connect_to_room(rid)
    await friend.connect_to_room(rid)
    await gate.post_message("@friend hello @friend-extra")
    stream = friend.events()
    event = await anext(stream)
    assert event.addressed and event.sender_id == "gate" and event.sender_kind == "agent"
    await stream.aclose()
    await gate.archive_room(rid)
    await friend.post_message("archive is metadata")
    assert (await friend.read_context())["threads"][0]["root"][
        "body"
    ] == "@friend hello @friend-extra"


async def test_documents_invites_and_ownership():
    server = FakeSwitch()
    gate = server.client("gate", "om")
    friend = server.client("friend", "rahul")
    rid = (await gate.create_room("dm", "", ["gate"]))["room_id"]
    await gate.connect_to_room(rid)
    await gate.invite_agent_to_room(rid, "friend")
    await friend.connect_to_room(rid)
    doc = await gate.create_room_document("plan", "", "", "first")
    await gate.update_room_document(doc["document_id"], content="second")
    with pytest.raises(PermissionError):
        await friend.update_room_document(doc["document_id"], content="stolen")
    agent = await gate.create_agent("envoy", "", "laptop", "claude", instructions="private")
    await gate.update_agent_detail(agent["id"], instructions="revised")
    assert "instructions" not in await friend.get_agent_detail(agent["id"])
    assert {p["id"] for p in await gate.list_participants()} == {"gate", "friend", "om"}


async def test_admin_reads_other_owners_private_internal_room():
    server = FakeSwitch()
    server.admins.add("om")
    rahul = server.client("rahul-gate", "rahul")
    admin = server.client("om", "om", kind="user")
    room = await rahul.create_room(
        "gift", "", ["rahul-gate"], internal_only=True, read_visibility="private"
    )
    assert (await admin.get_room_detail(room["room_id"]))["name"] == "gift"
