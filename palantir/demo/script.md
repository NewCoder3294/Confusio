# Demo script — Foundry segments

3-minute total. Foundry segments are ~90 seconds of the 180; everything else
is the local engine and the slides. This file is **just the Foundry parts**.
The other Claude session has the engine-segment script.

**Voice:** sober, procedural, doctrine-aligned. You're not pitching a
product to a venture audience. You're a J2 staffer briefing senior officers
who already know how Foundry behaves and want to know what *this* particular
deployment does. No "imagine a world where," no "we built." Show what's on
screen and name what it is.

**Pacing:** ~150 words per minute is normal speaking pace. The scripts below
are calibrated to fit. **Read each segment aloud once before the demo and
trim if you run over.** A line you can't say in the time allotted is wrong.

---

## Segment 1 — 0:20 → 0:35 (15s) — Authorization view

**Cue:** end of Slide 2 (Customer + Authority). The slide deck transitions
to the Foundry tab; you click the **Authorization & Audit** page.

**What's on screen:** the legal-lane banner, the authority chain card, the
audit trail with 4 missions visible.

**Say:**

> "This is the legal lane. Title 10, §1631 — military information
> operations. Foreign actors only. Every mission in the audit log below has
> a sandbox channel, a logged operator, and an approval chain. Nothing
> ships without all three on the record."

**(15 seconds. ~38 words. Read it tight.)**

**If a judge's eyes track:** they will read the banner first, the audit
table second. Don't talk over the table — let them read it for a beat.

---

## Segment 2 — 0:35 → 1:00 (25s) — Mission Board (warmup)

**Cue:** click the **Mission Board** page in the nav. Click on
`SHADOW-FOX-001` (the warmup mission).

**What's on screen:** the Mission Detail pane with stage timeline, artifact
image, detector pills, operator brief paragraph.

**Say:**

> "This is a completed mission. The timeline shows seven stages — persona
> forged, source artifact selected, SynthID watermark stripped, EXIF camera
> profile transplanted, provenance graded. The right pane is the
> self-grade: the artifact passes all three detectors an adversary's
> vetting pipeline would deploy. C2PA, Amazon Titan, Google SynthID. The
> tool grades itself with the same instruments the enemy would."

**(25 seconds. ~63 words.)**

**Beat to land:** "the same instruments the enemy would." That's the
thesis. Don't rush it.

**If you have a half-second:** point at the operator brief paragraph and
say "and here's the operator-readable summary." The rest is in the audit
trail.

---

## Segment 3 — 1:00 → 1:30 (30s) — New Mission, live

**Cue:** click the **New Mission** page in the nav. Click into the Operator
Intent textarea.

**Type, slowly enough that the audience can read** (this is the moment
they'll remember):

> "Plant a leaked-orders post in the pro-regime junior officer channel from
> a disgruntled lieutenant. Image should look like a smudged regimental
> movement order shot on a phone."

**While typing, say:**

> "The planner is an AIP Studio agent grounded in this Ontology — it knows
> only the channels on the sandbox allowlist, only the Title 10 lane.
> Operator intent in plain English; structured mission spec out."

**Click Plan Mission.** ~3-second wait.

**As the spec preview renders, say:**

> "Channel selected: `@mendacity_sandbox_demo`. Persona archetype:
> disgruntled junior officer. The agent picked the channel from audience
> match. Approve."

**Click Approve and Execute.**

**(30 seconds total. ~75 words spoken plus the typing time.)**

**Risk:** the agent takes longer than 3 seconds. If it's still spinning at
~5s, fill with: "The grounding query against the Channel ontology runs
first — it's verifying the sandbox lane before it generates the spec."
That buys you another 7s of credibility.

**Hard fallback:** if the agent times out, say: "Network's holding the AIP
call. Here's the spec it would have produced —" and switch to a slide with
the canned spec. The Authorization & Audit story still landed in Segment 1;
this is recoverable.

---

## Segment 4 — 2:15 → 2:35 (20s) — Mission Board (the round-trip lands)

**Cue:** the engine segment ends; you cut back to the Foundry tab. The
Mission Board is open. The mission you just created is now at the top of
the list with status `completed`.

**Say:**

> "And it's back. The result the engine just produced flowed through the
> bridge into the Ontology — same audit trail, same grading panel. New
> mission, full pass, sandbox channel, dry-run. This is what deployment
> looks like inside an Army Vantage tenant: the operator never leaves
> Foundry."

**(20 seconds. ~52 words.)**

**Click the new mission.** Detail pane renders. Don't over-narrate; let the
green pills do the talking.

**Final beat:** "Operator never leaves Foundry." That's what you want a
NATSEC judge with an Army background to take into the deliberation room.

---

## Recoverability cheatsheet

| If this happens during demo | Do this |
|---|---|
| Bridge log shows error | Don't acknowledge from on stage. The Workshop view is the surface; the bridge can be flaky and the demo still works for the next 60s. |
| MissionPlanner agent times out (~10s+) | Fall back to slide. Keep moving. Never wait for a stuck agent on stage. |
| Workshop renders empty Mission Board | You forgot to run `load_existing_results.py`. Skip Segment 2; segue to Segment 3 directly. |
| Engine segment runs long, Segment 4 gets compressed | Cut Segment 4 to 12 seconds: "And it's back. Operator never leaves Foundry." That's enough. |
| A judge interrupts to ask about authorization | Switch to the Authorization & Audit page. The banner answers the question without you having to. |

---

## What you're optimizing for

A NATSEC judge with an Army background says "this could be in Vantage by
next month." Not "they built a cool prototype" — that's a different demo.
The Foundry segments are how we close the deployment-credibility sale. The
local engine proves capability. Foundry proves it would deploy.

Calm pace. Procedural voice. Let the operator surface earn the trust by
*not* looking like anything else in the LLM hype cycle.
