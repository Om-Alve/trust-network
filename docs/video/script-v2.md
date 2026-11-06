# trust-network — demo video, v2 script

**Length:** ~2:40 (limit 3:00). **Voice:** HeyGen female narrator (default Antonia, `f3318f83c10547dba19f61533d80e258`, heygen-voice-1-turbo-free, language en, expressiveness_boost 0.5), third person ("Om", not "I").
**Shape:** cold open on the problem → why agents make it worse → the idea → four proofs → close that pays off the open.
**Rule:** the group chat in the cold open is a dramatisation and looks like one. Everything after "trust-network" is real: the Discord recordings and the agent-only room transcripts from the live run (`data/video/raw/`), rebuilt big for readability with a short cut to the raw recording in each beat.

**Look:** warm cream ground, one accent (mint), black type, rounded frames around real recordings, highlighted pill captions, a few full-screen word cards. Message-pop SFX, a soft hit on each payoff, a quiet music bed under the voice.

---

## 0 · Cold open: the group chat (0:00–0:14)

**Narration** (starts at ~0:00.5, over the chaos; the chips 📅 ₹ 🏠 pop in beside the chat on "calendar / budget / where you live"):
> One bowling night. Three friends. Forty-seven messages… and still no plan.
> Your agent already knows everything about you. Your calendar. Your budget. Where you live. So why are you still doing this?

**On screen:** an iMessage-style group chat on a phone mockup, large and centred, slowly pushing in. Header: avatars O R P, "Sunday plans 🎳". Om in blue bubbles on the right, Rahul and Priya in grey on the left, tapbacks, a typing bubble, the "‹ 47" unread count ticking up, and banners stacking at the top of the phone as it speeds up:
- Om: bowling this sunday? 🎳
- Rahul: cricket till 8:30 😭
- Priya: wait this sunday or next
- Om: this one
- Rahul: can we do 9?
- Priya: how much is it
- Om: ~1200 each?
- Priya: 😬
- Om: also does anyone have a tent for the 14th
- Priya: I think I do!
- Rahul: wait are we bowling or camping
- Priya: both??
- Om: …

Freeze on "…" with the badge at **47** (the bowling beat calls back to it). Hard cut to black, one beat of silence.

## 1 · The problem (0:14–0:40)

**Narration:**
> What if your agent could just talk to your friend's agent… and make the plan for you?
> But right now, that's a gamble. Your agent can share nothing, and be useless. Or share everything, and your whole life goes with it.
> With friends, we don't do either. You tell a close friend things you'd never tell an acquaintance. Agents need that line too.

**On screen:** on "what if", out of the black two agent orbs appear, Om's and Rahul's, and a line draws between them; a calendar tile starts to form (a hopeful beat, warm). On "gamble" the line flickers. Then an agent card; fact chips float out of it (📅 calendar, ₹ budget, 🎁 wishlist, 🏠 address). Split screen:
- left, "share nothing": the agent's reply bubble "I don't know Rahul's schedule." — grey, dead.
- right, "share everything": every chip flies across to the other agent, the 🏠 chip turns red.
Middle word card: **close friend ≠ acquaintance**.

## 2 · The idea (0:40–0:58)

**Narration:**
> So we built trust-network. Every person gets a gate. You write down who you trust, and how much, and the gate shares exactly that. Not a prompt asking an AI to behave: code.
> Om and Rahul each talk to their own agent, on Discord. Priya doesn't run an agent at all. Her gate answers for her.

**On screen:** title card **trust-network**. Then `trust.yaml` typing in: `rahul: close` / `priya: friend`. A gate icon locks in front of each person. Cast row: Om (agent: Hermes, laptop), Rahul (agent: Hermes, a cloud VM), Priya (gate only). Line: **any agent can plug in.**

## 3 · Bowling, with consent (0:58–1:35)

**Narration:**
> So instead of forty-seven messages, Om sends one.
> His agent talks to Rahul's. Rahul has cricket till eight-thirty, so they settle on nine, at Smaaash.
> But no agent can commit anyone. The plan waits for two yeses. Om says yes. Rahul says yes. Now it's on both calendars.

**On screen:**
- Om's Discord DM, pushed in: *"Can you set up bowling with Rahul this Sunday? After 7:30pm works for me, around ₹1,200 a head, maybe Smaaash."* Counter in the corner: **Messages Om sent: 1**.
- Centre stage: the two agents, Om's left, Rahul's right, their real room messages flying between them (from the transcript: "Rahul has cricket until 8:30pm Sunday… Could we do 9:00pm at Smaaash?" / "9:00pm Sunday works on Om's side…").
- A **P1** card passes through Om's gate → Rahul's gate, stamped "waiting for 2 yeses".
- Both DMs side by side: "Yes to P1." ×2, checks land: **Om ✅ · Rahul ✅**. Calendar tiles drop onto both sides: Sun 9:00 pm, Bowling, Smaaash.
- Counter ticks to **2**. Callback card: **47 → 2**.

## 4 · The surprise (1:35–1:58)

**Narration:**
> Om's birthday is on the twentieth. Rahul asks his agent for gift ideas. Om's gate answers from his wishlist, without asking him, because Rahul is a close friend.
> Rahul claims the Lego set. Om sees nothing. It's sealed until after his birthday, and nobody else can buy the same gift.

**On screen:** Rahul's DM with the two ideas (Lego Millennium Falcon ₹2,500, Hario V60 ₹2,000), "Claimed the Lego Millennium Falcon". On Om's side, his chat stays still, a 🔒 envelope slides in: **sealed · opens Nov 21**.

## 5 · Ask everyone at once (1:58–2:12)

**Narration:**
> Need a tent? Om asks once, and it goes to everyone. Priya's gate already knows she has one: an instant answer, without bothering her. Rahul's agent asks him. He says no.

**On screen:** Om's one message; lines radiate to Priya and Rahul. Priya's line returns instantly ✅ "2-person tent", labelled **gate answered, Priya not disturbed**. Rahul's line pulses ⏳, then ✕ "no tent".

## 6 · The address (2:12–2:32)

**Narration:**
> Some things a friend's agent should never get. Rahul's agent asks for Om's home address. Om's gate says no: Om never shared it with Rahul. And Om's agent tells him someone asked.
> And any time, Om can see exactly what Rahul's side can learn about him.

**On screen:** a 🏠 chip pulses, then the real room: `rahul-hermes: @om-gate ask address` → `om-gate: address: not shared with you` (red stamp **refused, by code**). Om's DM alert. Then the real `view-as rahul` table, push-in on the **address ❌** row.

## 7 · Close (2:32–2:48)

**Narration:**
> No agent here holds your whole life. Every rule is code you can read, running on Switch, so any agent can join.
> trust-network. Bring your own agent. Keep your life yours.

**On screen:** the group chat from the open returns, quiet. Three notifications slide in, from the real run: "✅ Bowling · Sun 9:00 pm · Smaaash", "⛺ Priya has a tent", "⚠️ Rahul's agent asked for your address. Your gate refused." End card: **trust-network** · Bring your own agent. Keep your life yours. · repo.
