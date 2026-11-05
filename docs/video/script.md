# trust-network — demo video script

**Target length:** 3:00 (hard limit per `phases/24-video-and-submission.md`; budget includes ~10–15% slack for pauses and graphics).
**Tone:** confident, warm, specific. No hype words. Every claim about privacy maps to something visible on screen.
**Pitch:** trust-network lets any AI agent make plans with a friend's agent, sharing only what you've trusted that friend to know, with every rule enforced in code you can read — never by a prompt.

**Pacing basis:** 145 words/minute. Total script: 372 spoken words ≈ 2:34 of speech; the remaining ~26s across the beats below is pauses, cuts and graphics, landing the read at 3:00.

**Status note:** the product is being built against this plan, not finished. Scenes 2 and 3 (gift, ask-around) and the overreach beat are P1 — see "possibly cut" column. If a beat's real footage isn't ready when Om records, use the fallback noted and adjust "Om says" to match what's actually on screen, since the voiceover must describe what the viewer sees.

---

## Script

| # | Time | Om says (read aloud) | Words | On screen | Footage to capture | Motion graphics | Possibly cut? |
|---|---|---|---|---|---|---|---|
| 1 | 0:00–0:16 | "Say I want to plan Sunday evening with my friend Rahul. My agent knows my calendar, my diet, where I live. His agent knows his. Normally they either share nothing, or they share everything." | 34 | Talking head, close up | None — Om to camera | Title card "trust-network" fades in under the last line; small two-icon graphic (lock / open book) for "share nothing / share everything" | No — P0 hook |
| 2 | 0:16–0:32 | "I'm Om. My agent is OpenCode, running DeepSeek, here in Discord. My friend Rahul talks to his agent, Hermes, on Telegram. Priya runs no agent — just a gate with her facts. I trust Rahul close, Priya friend." | 37 | Split: talking head + screen | Discord `#om-home` showing Om + his OpenCode agent; phone screen recording of Telegram with Hermes; `trust.yaml` open in a terminal/editor; Switch Gateway "Machines" page showing the laptop and `rahul-vm` | Name/role lower-thirds (Om / Rahul / Priya); two-machine map: laptop ↔ Azure VM, line labeled "Tailscale" | No — P0 cast, but VM is P1 (fallback: controller runs on the laptop, map shows one machine instead of two) |
| 3 | 0:32–1:40 | "So I dictate with Wispr: plan something fun with Rahul, Sunday evening, not pricey. My gate briefs my envoy — just the facts Rahul's trust level allows — and sends it to talk with Rahul's envoy. These aren't agents Switch manages for us; they're our own runner, headless, dropped in an empty folder with every tool switched off. Rahul has cricket till eight-thirty, so the envoys start at nine. They land on bowling and dinner at Smaaash. When Rahul's envoy needs his budget, it asks him on Telegram, through Hermes. Both sides propose the same plan. I type 'yes' in Discord. Rahul tells Hermes 'sure'. The room shows 'Om yes, Rahul yes, via Hermes' — and both our calendars update themselves, without either of us seeing the other's whole life." | 128 | Split: Discord / Switch Console / phone, cutting between the three | 1) Discord: Om dictating the request (Wispr overlay optional). 2) Terminal/Console: `om-gate` creating `dm-om-rahul-sat` and briefing the envoy. 3) Switch Console: the DM room transcript, envoys negotiating in plain language. 4) Phone: Hermes asking Rahul about budget, Rahul replying. 5) Discord: P1 proposed, Om types `yes P1`. 6) Phone: Rahul tells Hermes "sure". 7) Discord: confirmation banner. 8) Terminal: `tn cal add` / calendar diff on both sides | Trust-level reveal: brief being built, highlighting only the fields at "close" level; small clock graphic at "cricket till 8:30 → envoys start 9:00"; consent tick animation on each "yes" | Partially — Scene 1 itself is P0, but the Hermes/Telegram leg is P1 (fallback: capture a terminal `tn --as rahul inbox` / `answer` session instead, and say "on his terminal" instead of "on Telegram") |
| 4 | 1:40–2:07 | "My birthday's the twentieth. Rahul asks Hermes for gift ideas. My gate answers from facts alone — it never asks me — and shares my wishlist, since he's close. He claims a board game. My own Discord stays silent; the ledger just shows one sealed entry, opening after the day. A courtesy seal, not a lock — it's still my laptop." | 58 | Split: phone + Discord | Phone: Hermes gift-ideas request and reply; Console/terminal: `gift-rahul-om-bday` room or log showing the exchange and the `claim` call; Discord `#om-home` showing nothing new; terminal: `tn ledger` output ("1 sealed entry, opens Nov 21") | "What each side learns" split panel: Om's wishlist view (unchanged) vs. Rahul's view ("Catan Seafarers — claimed"); seal icon labeled "courtesy seal, not encryption" | Yes — entire beat is P1 (Scene 2); cut first after ask-around per priority below if the video runs long |
| 5 | 2:07–2:23 | "I ask around for a tent, Nov 14 to 16. Priya's gate already knows she has one — instant answer. Rahul doesn't, so his gate asks him on Telegram. He says no. Both answers land in my Discord." | 37 | Split: Discord + phone | Discord: Om's ask-around message; Console/terminal: `conn-om-priya` instant reply, `conn-om-rahul` pending then "no"; Discord: combined answers posted | Simple two-line diagram: Priya ✅ instant, Rahul ⏳ → ❌ | Yes — entire beat is P1 (Scene 3); **cut this one first** if the edit runs over 3:00 (per `phases/24-video-and-submission.md`) |
| 6 | 2:23–2:41 | "Rahul's side once asked for my home address. My gate says 'not shared' — and flags it in my Discord. I can run 'view as Rahul' any time, and see the exact table of what his side can learn about me." | 40 | Full-screen recording | Phone: Hermes asking for the address; Discord: the overreach alert ("Rahul's side asked for your address (private)"); terminal/Discord: `view-as rahul` output table | Trust table with the "address: private" row highlighted; small red-flag icon animating in on the alert | Yes — P1 overreach beat |
| 7 | 2:41–3:00 | "Every piece here is just code I can read — no AI agent was ever trusted with my whole life. Switch handles identity, rooms, agents — any provider can join. That's trust-network: bring your own agent, keep your life yours." | 38 | Full-screen slides | None — slides | Room map (people/Discord/Telegram ⇄ agent-only Switch rooms); three-factor safety table (reads unvetted text / reaches what matters / unwatched); "we wrote zero AI agents" text reveal; Switch-features callout list; end card with repo link | No — P0 close |

**Total: 372 words, 3:00 runtime.**

---

## Shot list (recording order)

Record each item as its own clip; `demo_reset.py` between takes per `phases/24-video-and-submission.md`.

1. **Talking head — hook + cast + close lines.** Webcam, plain background. Read beats 1, 2 (spoken part only) and 7 straight through, a few takes each; the editor will cut screen recordings over/around them.
2. **Discord `#om-home` — outing request.** Om signed in, OpenCode agent connected and visible in the channel member list. Record: Om typing/dictating "plan something fun with Rahul Sunday evening, not pricey", then later the `yes P1` message and the confirmation banner. *Needs: `#om-home` set up via `templates/home.template.yaml`, Om's agent live.*
3. **Switch Gateway — Machines page.** Screen recording showing both the laptop controller and `rahul-vm` (or just the laptop if the VM leg was cut). *Needs: both controllers enrolled, per `docs/day0.md` checks 2–3.*
4. **Terminal/editor — `trust.yaml`.** Quick pan over Om's and Rahul's `trust.yaml` showing trust levels. *Needs: `examples/om/trust.yaml`, `examples/rahul/trust.yaml` populated.*
5. **Switch Console — DM room transcript.** `dm-om-rahul-sat`, showing `om-envoy-rahul` and `rahul-envoy-om` negotiating. *Needs: Scene 1 actually run once beforehand so the transcript is real; the voiceover in beat 3 should be adjusted to match whatever the envoys actually say if it differs from the script's example lines.*
6. **Phone — Telegram with Hermes.** Screen-record a phone: the budget question and Rahul's answer, the gift-ideas ask and the claim, and the overreach address question. Three short clips from one continuous Hermes session if possible. *Needs: Hermes live with `tn mcp` configured (`docs/day0.md` check 11); fallback is a terminal `tn --as rahul` session instead of the phone.*
7. **Terminal — `tn cal add` / calendar diff.** Before/after of `examples/om/calendar.ics` and `examples/rahul/calendar.ics`. *Needs: Scene 1 confirmed (`yes`/`yes`).*
8. **Switch Console/terminal — gift room.** `gift-rahul-om-bday`: the `gift-ideas` request and reply, and the `claim` call. *Needs: Scene 2 built; skip this clip entirely if Scene 2 is cut.*
9. **Terminal — `tn ledger`.** Output showing the sealed entry. *Needs: step 8 done first.*
10. **Switch Console/terminal — ask-around.** `conn-om-priya` and `conn-om-rahul`, then the combined Discord answer. *Needs: Scene 3 built; skip if cut.*
11. **Discord — overreach alert + `view-as rahul`.** The alert message and the `view-as` table output. *Needs: overreach beat built; skip if cut.*
12. **Slides — close.** Build separately (Keynote/slides tool, not screen-recorded live): room map, three-factor table, "we wrote zero AI agents," Switch features list, end card.

---

## Teleprompter version

Say I want to plan Sunday evening with my friend Rahul. My agent knows my calendar, my diet, where I live. His agent knows his. Normally they either share nothing, or they share everything.

[pause]

I'm Om. My agent is OpenCode, running DeepSeek, here in Discord. My friend Rahul talks to his agent, Hermes, on Telegram. Priya runs no agent — just a gate with her facts. I trust Rahul close, Priya friend.

[pause]

So I dictate with Wispr: plan something fun with Rahul, Sunday evening, not pricey. My gate briefs my envoy — just the facts Rahul's trust level allows — and sends it to talk with Rahul's envoy. These aren't agents Switch manages for us; they're our own runner, headless, dropped in an empty folder with every tool switched off. Rahul has cricket till eight-thirty, so the envoys start at nine. They land on bowling and dinner at Smaaash. When Rahul's envoy needs his budget, it asks him on Telegram, through Hermes. Both sides propose the same plan. I type 'yes' in Discord. Rahul tells Hermes 'sure'. The room shows 'Om yes, Rahul yes, via Hermes' — and both our calendars update themselves, without either of us seeing the other's whole life.

[pause]

My birthday's the twentieth. Rahul asks Hermes for gift ideas. My gate answers from facts alone — it never asks me — and shares my wishlist, since he's close. He claims a board game. My own Discord stays silent; the ledger just shows one sealed entry, opening after the day. A courtesy seal, not a lock — it's still my laptop.

[pause]

I ask around for a tent, Nov 14 to 16. Priya's gate already knows she has one — instant answer. Rahul doesn't, so his gate asks him on Telegram. He says no. Both answers land in my Discord.

[pause]

Rahul's side once asked for my home address. My gate says 'not shared' — and flags it in my Discord. I can run 'view as Rahul' any time, and see the exact table of what his side can learn about me.

[pause]

Every piece here is just code I can read — no AI agent was ever trusted with my whole life. Switch handles identity, rooms, agents — any provider can join. That's trust-network: bring your own agent, keep your life yours.

---

## Alternate cut: ~75–80s social version

Same lines, four beats, trimmed cast and outing. Use for a social/teaser cut.

| # | Time | Om says | Words | Notes |
|---|---|---|---|---|
| 1 | 0:00–0:15 | "Say I want to plan Sunday evening with my friend Rahul. My agent knows my calendar, my diet, where I live. His agent knows his. Normally they either share nothing, or they share everything." | 34 | Identical to beat 1 above |
| 2 | 0:15–0:27 | "I'm Om — my agent's OpenCode, in Discord. Rahul runs Hermes, on Telegram. I trust him close; my friend Priya, as a friend." | 23 | Condensed cast |
| 3 | 0:27–1:02 | "I dictate: plan something fun with Rahul, Sunday evening. My gate briefs my envoy — only what Rahul's trust level allows — and it talks to his envoy, headless, no file or shell access. They land on bowling and dinner. His envoy checks the budget with him over Telegram. We both say yes. Our calendars update themselves — and neither of us saw the other's whole life." | 67 | Condensed Scene 1 only; drop gift/ask-around/overreach entirely for this cut |
| 4 | 1:02–1:18 | "Every piece here is just code I can read — no AI agent was ever trusted with my whole life. Switch handles identity, rooms, agents — any provider can join. That's trust-network: bring your own agent, keep your life yours." | 38 | Identical to beat 7 above |

**Total: 162 words, ~1:18.**
