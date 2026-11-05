---
name: trust-network
description: Ask your gate for facts and coordinate with trusted people.
---
Address commands to your gate, for example `@om-gate ask diet wishlist` or
`@om-gate free 2026-11-08..2026-11-09`. Dates in free ranges are inclusive.

Available now: `free <range>`, `ask <fact> ...`, and owner-user-only
`view-as <person>`, `ledger`, `trust <person> <close|friend|acquaintance>`.

Coordination syntax reserved for later phases:
`dm <person> "goal"`, `ask-owner Q1 "question"`,
`propose P1 <datetime> <duration> "title" @ "place"`,
`counter P1 P2 <datetime> <duration> "title" @ "place"`,
`yes P1`, `no P1`, `answer Q1 "answer"`,
`gift-ideas <occasion> on <date>`, `claim "item"`, `ask-around "question"`.
Gate-to-gate only: `join-dm <room> "goal"`,
`consent P1 yes|no via-agent|direct`. Consent relays never substitute for an
owner's direct yes. These two commands are denied until phase 14.

A gate may stay silent when a room has an unknown participant. Never put private
facts into a shared room yourself; ask the gate and let its policy decide.
