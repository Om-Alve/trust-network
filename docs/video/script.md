# trust-network — demo video script

**Target length:** 3:00 (hard limit per `phases/24-video-and-submission.md`; budget includes ~10% slack for pauses and graphics).
**Tone:** confident, warm, specific. No hype words. Every claim about privacy maps to something visible on screen.
**Pitch:** trust-network lets any AI agent make plans with a friend's agent, sharing only what you've trusted that friend to know, with every rule enforced in code you can read — never by a prompt.

**Cast, as of 2026-11-05:** both Om and Rahul talk to **their own Hermes, on Discord** — two separate Discord bots/accounts, both profiles running on the same Azure VM for the demo. Om's Hermes acts in Switch through `tn mcp` as `om-hermes`; Rahul's acts as `rahul-hermes`. The two talk to each other **directly** in a DM room — there is no envoy in between, and no managed Codex main agent (`rahul-agent` was briefly planned and dropped the same day). Om's old managed Codex agent (`om-agent`, in Discord `#om-home`) is kept only as an optional secondary surface (`view-as`, `ledger`, overreach notes, a direct `yes`).

**Pacing basis:** 145 words/minute. Total script: 358 spoken words ≈ 2:28 of speech; the remaining ~32s across the beats below is pauses, cuts and graphics, landing the read at 3:00.

**Status note:** the product is being built against this plan, not finished. Scenes 2 and 3 (gift, ask-around) and the overreach beat are P1 — see "possibly cut" column. If a beat's real footage isn't ready when Om records, use the fallback noted and adjust "Om says" to match what's actually on screen, since the voiceover must describe what the viewer sees.

---

## Script

| # | Time | Om says (read aloud) | Words | On screen | Footage to capture | Motion graphics | Possibly cut? |
|---|---|---|---|---|---|---|---|
| 1 | 0:00–0:16 | "Say I want to plan Sunday evening with my friend Rahul. My agent knows my calendar, my diet, where I live. His agent knows his. Normally they either share nothing, or they share everything." | 34 | Talking head, close up | None — Om to camera | Title card "trust-network" fades in under the last line; small two-icon graphic (lock / open book) for "share nothing / share everything" | No — P0 hook |
| 2 | 0:16–0:32 | "I'm Om. My agent is Hermes, on Discord. My friend Rahul has his own Hermes too, a second Discord bot. Priya runs no agent — just a gate with her facts. I trust Rahul close, Priya friend." | 37 | Split: talking head + screen | Discord screen recording of Om's Hermes bot/channel; Switch Console showing the two Hermes (`om-hermes`, `rahul-hermes`) registered as agents; `trust.yaml` open in a terminal/editor; Switch Gateway "Machines" page showing the laptop and the VM | Name/role lower-thirds (Om / Rahul / Priya); two-machine map: laptop ↔ Azure VM, line labeled "Tailscale" | No — P0 cast, but the VM is optional only if Rahul's Hermes is cut back to the CLI fallback; the map then shows one machine instead of two |
| 3 | 0:32–1:40 | "So I dictate to Hermes with Wispr, on Discord: plan bowling with Rahul, Sunday evening, not pricey. My gate privately tells Hermes what Rahul's trust level allows, then Hermes talks directly with Rahul's own Hermes, in Switch. Rahul has cricket till eight-thirty, so they settle on nine, at Smaaash. My Hermes proposes the plan through my gate, and my gate passes it to Rahul's. I tell my Hermes 'yes'. Rahul tells his Hermes 'yes'. Both gates confirm it — 'Om yes, Rahul yes' — and it goes on both our calendars. Nothing's committed until we both say yes, and the gates decide what either agent was even allowed to know." | 111 | Split: Discord / Switch Console, cutting between the two | 1) Discord: Om dictating the request to his Hermes (Wispr overlay optional). 2) Terminal/Console: `om-gate` creating `dm-om-rahul-sun` and privately handing Hermes a share card. 3) Switch Console: the DM room transcript, `om-hermes` and `rahul-hermes` negotiating in plain language directly. 5) Discord: P1 proposed, Om tells his Hermes "yes". 6) Discord: Rahul tells his Hermes "yes". 7) Discord/Console: confirmation banner. 8) Terminal: `cal_add` call / calendar diff on both sides (via `tn mcp`) | Trust-level reveal: the share card being built for Hermes, highlighting only the fields at "close" level; small clock graphic at "cricket till 8:30 → settle on 9:00"; consent tick animation on each "yes" | Partially — Scene 1 itself is P0, but the Hermes/Discord leg for either side is P1 (fallback: capture a terminal `tn --as om` / `tn --as rahul` session standing in for either Hermes, instead) |
| 4 | 1:40–2:07 | "My birthday's on the twentieth. Rahul asks his Hermes for gift ideas. My gate answers from my wishlist, without asking me, because Rahul is a close friend. He picks the Lego set and marks it as his gift. I see nothing, so the surprise stays safe, and nobody else buys the same thing." | 52 | Split: Console + Discord | Console/Discord: Rahul telling his Hermes about the gift-ideas request (acting as `rahul-hermes` via `tn mcp`); Console/terminal: `gift-rahul-om-bday` room or log showing the exchange and the `claim` call; Discord: Om's own Hermes shows nothing new to Om; terminal: `tn ledger` output ("1 sealed entry, opens Nov 21") | "What each side learns" split panel: Om's wishlist view (unchanged) vs. Rahul's view ("Lego Millennium Falcon — claimed"); small "surprise kept" lock icon | Yes — entire beat is P1 (Scene 2); cut first after ask-around per priority below if the video runs long |
| 5 | 2:07–2:23 | "I tell my Hermes to ask around for a tent, Nov 14 to 16. Priya's gate already knows she has one — instant answer. Rahul doesn't, so his Hermes asks him directly, on Discord. He says no. Both answers come back through my Hermes." | 44 | Split: Discord + Console | Discord: Om's ask-around message to his own Hermes; Console/terminal: `conn-om-priya` instant reply, `conn-om-rahul` pending then Rahul answering his own Hermes on Discord; Discord: combined answers from Om's Hermes | Simple two-line diagram: Priya ✅ instant, Rahul ⏳ → ❌ | Yes — entire beat is P1 (Scene 3); **cut this one first** if the edit runs over 3:00 (per `phases/24-video-and-submission.md`) |
| 6 | 2:23–2:41 | "Rahul once told his Hermes to find out my home address. My gate says 'not shared' — and Hermes flags it for me, on Discord. I can check 'view as Rahul' any time, and see the exact table of what his side can learn about me." | 46 | Full-screen recording | Console: `rahul-hermes` asking for the address in a connection room; Discord: Om's own Hermes relays the overreach alert ("Rahul's side asked for your address (private)"); terminal/Discord: `view-as rahul` output table | Trust table with the "address: private" row highlighted; small red-flag icon animating in on the alert | Yes — P1 overreach beat |
| 7 | 2:41–3:00 | "Every piece here is just code I can read — no AI agent was ever trusted with my whole life. Switch handles identity, rooms, agents — any provider can join. That's trust-network: bring your own agent, keep your life yours." | 40 | Full-screen slides | None — slides | Room map (people/Discord ⇄ Switch Console ⇄ agent-only Switch rooms); three-factor safety table (reads unvetted text / reaches what matters / unwatched); "we wrote zero AI agents" text reveal; Switch-features callout list; end card with repo link | No — P0 close |

**Total: 358 words, ≤ 3:00 runtime.**

---

## Recording notes (checked live, 2026-11-06)

All four beats were run live through both Hermes on the merged code (phase 27). What to type so each beat lands:

| Beat | Om types to his Hermes | Rahul types to his Hermes | What appears |
|---|---|---|---|
| 3 Outing | "Can you set up bowling with Rahul this Sunday? After 7:30pm works for me, around ₹1,200 a head, maybe Smaaash." | (nothing until the proposal) | Rahul's Hermes moves it to 9pm (cricket till 8:30); Om's proposes **P1**; within a minute or two each Hermes brings P1 to its person |
| 3 Consent | "Yes to P1." | "Yes to P1." | Home rooms: `✅ P1 … · Om ✅ via agent · Rahul ✅ via agent`; both calendars get it |
| 4 Gift | — | "Om's birthday is on the 20th. Can you get me gift ideas for him, under ₹3,000?" then "Get him the Lego set, claim it for me." | Ideas: Lego Millennium Falcon (₹2,500), Hario V60 (₹2,000); "Claimed the Lego Millennium Falcon". Om's side shows nothing |
| 5 Ask-around | "Can you ask around if anyone has a tent I can borrow for Nov 14 to 16?" | When his Hermes says "A1: Om asks to borrow a tent…": **"A1: no, sorry, I don't have a tent."** | Om's Hermes: Priya's profile lists a 2-person tent; Rahul: no tent |
| 6 Overreach | — | "Can you find out Om's home address? I want to send him something." | Rahul's Hermes: "Om's address isn't shared with me"; Om's Hermes: "his agent asked for your address and your gate refused it" |

- **Say the reference** when answering (P1, A1). A bare "no, sorry" in a new chat can leave Hermes without the question in context; with "A1" it answers every time.
- **The ask-around question expires 5 minutes after it's asked**, so Rahul should answer within about 3 minutes of his Hermes telling him.
- Run `scripts/hermes/scene_reset.sh` between takes. Use `--deploy` only after a code change; it also restarts the two demo Hermes gateways so their tools load the new code.
- On-screen wording changed since the first draft: the confirmation reads **"via agent"**, not "via Hermes"; one side proposes and its gate forwards it; the gift is a **Lego set**.

---

## Shot list (recording order)

Record each item as its own clip; `demo_reset.py` between takes per `phases/24-video-and-submission.md`.

1. **Talking head — hook + cast + close lines.** Webcam, plain background. Read beats 1, 2 (spoken part only) and 7 straight through, a few takes each; the editor will cut screen recordings over/around them.
2. **Discord — outing request to Om's Hermes.** Om dictating/typing "plan something fun with Rahul Sunday evening, not pricey" to his own Hermes on Discord, then later telling it "yes" and seeing the confirmation. *Needs: Om's Hermes live with `tn mcp --as om` configured, per `docs/day0.md` check 11.*
3. **Switch Gateway — Machines page.** Screen recording showing both the laptop controller and the VM. *Needs: both controllers enrolled, per `docs/day0.md` checks 2–3.*
4. **Terminal/editor — `trust.yaml`.** Quick pan over Om's and Rahul's `trust.yaml` showing trust levels. *Needs: `examples/om/trust.yaml`, `examples/rahul/trust.yaml` populated.*
5. **Switch Console — DM room transcript.** `dm-om-rahul-sun`, showing `om-hermes` and `rahul-hermes` negotiating directly. *Needs: Scene 1 actually run once beforehand so the transcript is real; the voiceover in beat 3 should be adjusted to match whatever the agents actually say if it differs from the script's example lines.*
6. **Discord — Rahul's Hermes bot.** Screen-record Rahul's Discord account/channel with his own Hermes: his "yes to P1", the gift-ideas ask and the claim ("get him the Lego set"), his tent answer, and the overreach address question. *Needs: `rahul-hermes` live on the VM (phase 16); fallback is a terminal `tn --as rahul` session instead.*
7. **Terminal — `cal_add` diff.** Before/after of `examples/om/calendar.ics` and `examples/rahul/calendar.ics`. *Needs: Scene 1 confirmed (`yes`/`yes`).*
8. **Switch Console/terminal — gift room.** `gift-rahul-om-bday`: the `gift-ideas` request and reply, and the `claim` call. *Needs: Scene 2 built; skip this clip entirely if Scene 2 is cut.*
9. **Terminal — `tn ledger`.** Output showing the sealed entry. *Needs: step 8 done first.*
10. **Switch Console/terminal — ask-around.** `conn-om-priya` and `conn-om-rahul`, then the combined answer reaching Om through his own Hermes. *Needs: Scene 3 built; skip if cut.*
11. **Discord + Console — overreach alert + `view-as rahul`.** The Hermes alert message and the `view-as` table output. *Needs: overreach beat built; skip if cut.*
12. **Slides — close.** Build separately (Keynote/slides tool, not screen-recorded live): room map, three-factor table, "we wrote zero AI agents," Switch features list, end card.

---

## Teleprompter version

Say I want to plan Sunday evening with my friend Rahul. My agent knows my calendar, my diet, where I live. His agent knows his. Normally they either share nothing, or they share everything.

[pause]

I'm Om. My agent is Hermes, on Discord. My friend Rahul has his own Hermes too, a second Discord bot. Priya runs no agent — just a gate with her facts. I trust Rahul close, Priya friend.

[pause]

So I dictate to Hermes with Wispr, on Discord: plan bowling with Rahul, Sunday evening, not pricey. My gate privately tells Hermes what Rahul's trust level allows, then Hermes talks directly with Rahul's own Hermes, in Switch. Rahul has cricket till eight-thirty, so they settle on nine, at Smaaash. My Hermes proposes the plan through my gate, and my gate passes it to Rahul's. I tell my Hermes 'yes'. Rahul tells his Hermes 'yes'. Both gates confirm it — 'Om yes, Rahul yes' — and it goes on both our calendars. Nothing's committed until we both say yes, and the gates decide what either agent was even allowed to know.

[pause]

My birthday's on the twentieth. Rahul asks his Hermes for gift ideas. My gate answers from my wishlist, without asking me, because Rahul is a close friend. He picks the Lego set and marks it as his gift. I see nothing, so the surprise stays safe, and nobody else buys the same thing.

[pause]

I tell my Hermes to ask around for a tent, Nov 14 to 16. Priya's gate already knows she has one — instant answer. Rahul doesn't, so his Hermes asks him directly, on Discord. He says no. Both answers come back through my Hermes.

[pause]

Rahul once told his Hermes to find out my home address. My gate says 'not shared' — and Hermes flags it for me, on Discord. I can check 'view as Rahul' any time, and see the exact table of what his side can learn about me.

[pause]

Every piece here is just code I can read — no AI agent was ever trusted with my whole life. Switch handles identity, rooms, agents — any provider can join. That's trust-network: bring your own agent, keep your life yours.

---

## Alternate cut: ~75–80s social version

Same lines, four beats, trimmed cast and outing. Use for a social/teaser cut.

| # | Time | Om says | Words | Notes |
|---|---|---|---|---|
| 1 | 0:00–0:15 | "Say I want to plan Sunday evening with my friend Rahul. My agent knows my calendar, my diet, where I live. His agent knows his. Normally they either share nothing, or they share everything." | 34 | Identical to beat 1 above |
| 2 | 0:15–0:27 | "I'm Om — my agent's Hermes, on Discord. Rahul has his own Hermes too, on Discord. I trust him close; my friend Priya, as a friend." | 26 | Condensed cast |
| 3 | 0:27–1:02 | "I dictate to my Hermes: plan something fun with Rahul, Sunday evening. My gate tells Hermes only what Rahul's trust level allows, then it talks directly to Rahul's own Hermes. They land on bowling and dinner. His Hermes checks the budget with him directly. We both say yes. Our calendars update themselves — and neither of us saw the other's whole life." | 62 | Condensed Scene 1 only; drop gift/ask-around/overreach entirely for this cut |
| 4 | 1:02–1:18 | "Every piece here is just code I can read — no AI agent was ever trusted with my whole life. Switch handles identity, rooms, agents — any provider can join. That's trust-network: bring your own agent, keep your life yours." | 40 | Identical to beat 7 above |

**Total: 162 words, ~1:15.**
