# trust-network — demo video script

**Target length:** 3:00 (hard limit per `phases/24-video-and-submission.md`; budget includes ~10–15% slack for pauses and graphics).
**Tone:** confident, warm, specific. No hype words. Every claim about privacy maps to something visible on screen.
**Pitch:** trust-network lets any AI agent make plans with a friend's agent, sharing only what you've trusted that friend to know, with every rule enforced in code you can read — never by a prompt.

**Cast, as of 2026-11-05:** Om's main agent is **Hermes** on Telegram (acting in Switch through `tn mcp` as `om-hermes`); Rahul's main agent is a **Switch-managed Codex agent** (`rahul-agent`), talked to directly in Switch Console / `rahul-home`. The two talk to each other **directly** in a DM room — there is no envoy in between. Om's old managed Codex agent (`om-agent`, in Discord `#om-home`) is kept only as an optional secondary surface (`view-as`, `ledger`, overreach notes, a direct `yes`).

**Pacing basis:** 145 words/minute. Total script: 378 spoken words ≈ 2:36 of speech; the remaining ~24s across the beats below is pauses, cuts and graphics, landing the read at 3:00.

**Status note:** the product is being built against this plan, not finished. Scenes 2 and 3 (gift, ask-around) and the overreach beat are P1 — see "possibly cut" column. If a beat's real footage isn't ready when Om records, use the fallback noted and adjust "Om says" to match what's actually on screen, since the voiceover must describe what the viewer sees.

---

## Script

| # | Time | Om says (read aloud) | Words | On screen | Footage to capture | Motion graphics | Possibly cut? |
|---|---|---|---|---|---|---|---|
| 1 | 0:00–0:16 | "Say I want to plan Sunday evening with my friend Rahul. My agent knows my calendar, my diet, where I live. His agent knows his. Normally they either share nothing, or they share everything." | 34 | Talking head, close up | None — Om to camera | Title card "trust-network" fades in under the last line; small two-icon graphic (lock / open book) for "share nothing / share everything" | No — P0 hook |
| 2 | 0:16–0:32 | "I'm Om. My agent is Hermes, on Telegram. My friend Rahul talks to his agent, a Codex agent, right in Switch. Priya runs no agent — just a gate with her facts. I trust Rahul close, Priya friend." | 38 | Split: talking head + screen | Phone screen recording of Telegram with Hermes; Switch Console showing `rahul-agent` in `rahul-home`; `trust.yaml` open in a terminal/editor; Switch Gateway "Machines" page showing the laptop and `rahul-vm` | Name/role lower-thirds (Om / Rahul / Priya); two-machine map: laptop ↔ Azure VM, line labeled "Tailscale" | No — P0 cast, but the VM is optional only if `rahul-agent` is cut back to the CLI fallback; the map then shows one machine instead of two |
| 3 | 0:32–1:40 | "So I dictate to Hermes with Wispr: plan something fun with Rahul, Sunday evening, not pricey. My gate privately tells Hermes what Rahul's trust level allows, then Hermes talks directly with Rahul's Codex agent in Switch. Rahul has cricket till eight-thirty, so they settle on nine. They land on bowling and dinner at Smaaash. When Rahul's agent isn't sure about the budget, it just asks him, right there in Console. Both sides propose the same plan through our gates. I tell Hermes 'yes'. Rahul says yes directly. The room shows 'Om yes, via Hermes; Rahul yes' — and both our calendars update themselves. Nothing's committed until we both say yes, and the gates decide what either agent was even allowed to know." | 122 | Split: phone / Switch Console, cutting between the two | 1) Phone: Om dictating the request to Hermes (Wispr overlay optional). 2) Terminal/Console: `om-gate` creating `dm-om-rahul-sat` and privately handing Hermes a share card. 3) Switch Console: the DM room transcript, Hermes and `rahul-agent` negotiating in plain language directly. 4) Console: `rahul-agent` asking Rahul the budget question in `rahul-home`, Rahul replying. 5) Phone: P1 proposed, Om tells Hermes "yes". 6) Console: Rahul says yes directly in `rahul-home`. 7) Phone/Console: confirmation banner. 8) Terminal: `tn cal add` / calendar diff on both sides | Trust-level reveal: the share card being built for Hermes, highlighting only the fields at "close" level; small clock graphic at "cricket till 8:30 → settle on 9:00"; consent tick animation on each "yes" | Partially — Scene 1 itself is P0, but the Hermes/Telegram leg is P1 (fallback: capture a terminal `tn --as om` session standing in for Hermes, and a `tn --as rahul` session standing in for `rahul-agent`, instead) |
| 4 | 1:40–2:07 | "My birthday's the twentieth. Rahul asks his own agent for gift ideas. My gate answers from facts alone — it never asks me — and shares my wishlist, since he's close. He claims a board game. My own side stays silent; the ledger just shows one sealed entry, opening after the day. A courtesy seal, not a lock — it's still my laptop." | 63 | Split: Console + phone | Console: `rahul-agent` in `rahul-home` running the gift-ideas request; Console/terminal: `gift-rahul-om-bday` room or log showing the exchange and the `claim` call; phone: Hermes shows nothing new to Om; terminal: `tn ledger` output ("1 sealed entry, opens Nov 21") | "What each side learns" split panel: Om's wishlist view (unchanged) vs. Rahul's view ("Catan Seafarers — claimed"); seal icon labeled "courtesy seal, not encryption" | Yes — entire beat is P1 (Scene 2); cut first after ask-around per priority below if the video runs long |
| 5 | 2:07–2:23 | "I tell Hermes to ask around for a tent, Nov 14 to 16. Priya's gate already knows she has one — instant answer. Rahul doesn't, so his gate asks him directly, in Switch. He says no. Both answers come back through Hermes." | 42 | Split: phone + Console | Phone: Om's ask-around message to Hermes; Console/terminal: `conn-om-priya` instant reply, `conn-om-rahul` pending then "no" in `rahul-home`; phone: combined answers from Hermes | Simple two-line diagram: Priya ✅ instant, Rahul ⏳ → ❌ | Yes — entire beat is P1 (Scene 3); **cut this one first** if the edit runs over 3:00 (per `phases/24-video-and-submission.md`) |
| 6 | 2:23–2:41 | "Rahul's agent once asked for my home address. My gate says 'not shared' — and Hermes flags it for me. I can check 'view as Rahul' any time, and see the exact table of what his side can learn about me." | 41 | Full-screen recording | Console: `rahul-agent` asking for the address in a connection room; phone: Hermes relays the overreach alert ("Rahul's side asked for your address (private)"); terminal/phone: `view-as rahul` output table | Trust table with the "address: private" row highlighted; small red-flag icon animating in on the alert | Yes — P1 overreach beat |
| 7 | 2:41–3:00 | "Every piece here is just code I can read — no AI agent was ever trusted with my whole life. Switch handles identity, rooms, agents — any provider can join. That's trust-network: bring your own agent, keep your life yours." | 38 | Full-screen slides | None — slides | Room map (people/Telegram/Switch Console ⇄ agent-only Switch rooms); three-factor safety table (reads unvetted text / reaches what matters / unwatched); "we wrote zero AI agents" text reveal; Switch-features callout list; end card with repo link | No — P0 close |

**Total: 378 words, 3:00 runtime.**

---

## Shot list (recording order)

Record each item as its own clip; `demo_reset.py` between takes per `phases/24-video-and-submission.md`.

1. **Talking head — hook + cast + close lines.** Webcam, plain background. Read beats 1, 2 (spoken part only) and 7 straight through, a few takes each; the editor will cut screen recordings over/around them.
2. **Phone — outing request to Hermes.** Om dictating/typing "plan something fun with Rahul Sunday evening, not pricey" to Hermes on Telegram, then later telling Hermes "yes" and seeing the confirmation. *Needs: Hermes live with `tn mcp --as om` configured, per `docs/day0.md` check 11.*
3. **Switch Gateway — Machines page.** Screen recording showing both the laptop controller and `rahul-vm`. *Needs: both controllers enrolled, per `docs/day0.md` checks 2–3.*
4. **Terminal/editor — `trust.yaml`.** Quick pan over Om's and Rahul's `trust.yaml` showing trust levels. *Needs: `examples/om/trust.yaml`, `examples/rahul/trust.yaml` populated.*
5. **Switch Console — DM room transcript.** `dm-om-rahul-sat`, showing `om-hermes` and `rahul-agent` negotiating directly. *Needs: Scene 1 actually run once beforehand so the transcript is real; the voiceover in beat 3 should be adjusted to match whatever the agents actually say if it differs from the script's example lines.*
6. **Switch Console — `rahul-agent` in `rahul-home`.** Screen-record Console signed in as Rahul: the budget question and Rahul's direct answer, the gift-ideas ask and the claim, and the overreach address question. *Needs: `rahul-agent` live as a managed Codex agent on `rahul-vm` (phase 16); fallback is a terminal `tn --as rahul` session instead.*
7. **Terminal — `tn cal add` / calendar diff.** Before/after of `examples/om/calendar.ics` and `examples/rahul/calendar.ics`. *Needs: Scene 1 confirmed (`yes`/`yes`).*
8. **Switch Console/terminal — gift room.** `gift-rahul-om-bday`: the `gift-ideas` request and reply, and the `claim` call. *Needs: Scene 2 built; skip this clip entirely if Scene 2 is cut.*
9. **Terminal — `tn ledger`.** Output showing the sealed entry. *Needs: step 8 done first.*
10. **Switch Console/terminal — ask-around.** `conn-om-priya` and `conn-om-rahul`, then the combined answer reaching Om through Hermes. *Needs: Scene 3 built; skip if cut.*
11. **Phone + Console — overreach alert + `view-as rahul`.** The Hermes alert message and the `view-as` table output. *Needs: overreach beat built; skip if cut.*
12. **Slides — close.** Build separately (Keynote/slides tool, not screen-recorded live): room map, three-factor table, "we wrote zero AI agents," Switch features list, end card.

---

## Teleprompter version

Say I want to plan Sunday evening with my friend Rahul. My agent knows my calendar, my diet, where I live. His agent knows his. Normally they either share nothing, or they share everything.

[pause]

I'm Om. My agent is Hermes, on Telegram. My friend Rahul talks to his agent, a Codex agent, right in Switch. Priya runs no agent — just a gate with her facts. I trust Rahul close, Priya friend.

[pause]

So I dictate to Hermes with Wispr: plan something fun with Rahul, Sunday evening, not pricey. My gate privately tells Hermes what Rahul's trust level allows, then Hermes talks directly with Rahul's Codex agent in Switch. Rahul has cricket till eight-thirty, so they settle on nine. They land on bowling and dinner at Smaaash. When Rahul's agent isn't sure about the budget, it just asks him, right there in Console. Both sides propose the same plan through our gates. I tell Hermes 'yes'. Rahul says yes directly. The room shows 'Om yes, via Hermes; Rahul yes' — and both our calendars update themselves. Nothing's committed until we both say yes, and the gates decide what either agent was even allowed to know.

[pause]

My birthday's the twentieth. Rahul asks his own agent for gift ideas. My gate answers from facts alone — it never asks me — and shares my wishlist, since he's close. He claims a board game. My own side stays silent; the ledger just shows one sealed entry, opening after the day. A courtesy seal, not a lock — it's still my laptop.

[pause]

I tell Hermes to ask around for a tent, Nov 14 to 16. Priya's gate already knows she has one — instant answer. Rahul doesn't, so his gate asks him directly, in Switch. He says no. Both answers come back through Hermes.

[pause]

Rahul's agent once asked for my home address. My gate says 'not shared' — and Hermes flags it for me. I can check 'view as Rahul' any time, and see the exact table of what his side can learn about me.

[pause]

Every piece here is just code I can read — no AI agent was ever trusted with my whole life. Switch handles identity, rooms, agents — any provider can join. That's trust-network: bring your own agent, keep your life yours.

---

## Alternate cut: ~75–80s social version

Same lines, four beats, trimmed cast and outing. Use for a social/teaser cut.

| # | Time | Om says | Words | Notes |
|---|---|---|---|---|
| 1 | 0:00–0:15 | "Say I want to plan Sunday evening with my friend Rahul. My agent knows my calendar, my diet, where I live. His agent knows his. Normally they either share nothing, or they share everything." | 34 | Identical to beat 1 above |
| 2 | 0:15–0:27 | "I'm Om — my agent's Hermes, on Telegram. Rahul talks to his own Codex agent, in Switch. I trust him close; my friend Priya, as a friend." | 26 | Condensed cast |
| 3 | 0:27–1:02 | "I dictate to Hermes: plan something fun with Rahul, Sunday evening. My gate tells Hermes only what Rahul's trust level allows, then it talks directly to Rahul's agent. They land on bowling and dinner. His agent checks the budget with him directly. We both say yes. Our calendars update themselves — and neither of us saw the other's whole life." | 60 | Condensed Scene 1 only; drop gift/ask-around/overreach entirely for this cut |
| 4 | 1:02–1:18 | "Every piece here is just code I can read — no AI agent was ever trusted with my whole life. Switch handles identity, rooms, agents — any provider can join. That's trust-network: bring your own agent, keep your life yours." | 38 | Identical to beat 7 above |

**Total: 158 words, ~1:15.**
