# Doc-derived frames, not live recordings

These synthetic message frames follow `protocol/stream.py::encode_ws`,
`protocol/types.py::MessagePayload`, `protocol/message_events.py`, and the event
envelope in `docs/official/internals/agent-protocol.md` from
https://github.com/sandbox-quantum/switch at
`1c9725a08d0e80151ac21adeea8df373f12a779e` (fetched 2026-11-05).
The requested public protocol URL was fetched too; its SSE description lags
current source, which implements WebSocket `/agents/{id}/connection/ws`.

Identifiers and content are invented. Optional event metadata is omitted.
`unknown.json` exercises an omitted sender kind; the parser preserves uncertainty.
The explicit user/agent variants test parsing, not a claim that the deployed
server always emits those kinds. Replace or supplement these with real frames
in phase 04, preserving sender identities and `addressed` while removing secrets.
