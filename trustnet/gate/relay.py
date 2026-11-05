"""Home-room relays, using the gate's own server memberships."""


async def post_home(person, text, *, client):
    detail = await client.get_agent_detail(client.agent_id)
    name = person + "-home"
    room = next(
        (r["room_id"] for r in detail["rooms"] if r["room_name"] == name and not r.get("archived")),
        None,
    )
    if room is None:
        if person == "om":
            raise RuntimeError("Create om-home with the Discord template first")
        result = await client.create_room(
            name, "Trust network home", [person + "-gate"], internal_only=True
        )
        room = result.get("room_id", result.get("id"))
    await client.connect_to_room(room)
    return await client.post_message(text)
