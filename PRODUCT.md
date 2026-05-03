# Product

## Register

product

## Users

A single operator running a Mendacity campaign. In v1 the operator is the
project author. The dashboard lives on a laptop on a presentation table at a
NATSEC hackathon; the audience that has to be convinced is judges peering
over the operator's shoulder during a 3-minute live demo, several of whom
have day-jobs in the intelligence community and will subconsciously compare
the surface to Palantir, Recorded Future, and Maltego.

The job to be done is operator-in-the-loop coordination of multiple
persona-bound LLM agents that post to Telegram from distinct accounts. The
operator needs to: see what was generated, decide which posts go live, edit
tone or detail before posting, and watch the audit trail accrue. Posting is
never autonomous and the UI must visibly reinforce that.

The operating context is high-pressure, time-boxed, and projector-mediated:
a demoer on stage, projector glare in the room, judges in row 5 who need to
read what's on screen as easily as the operator does.

## Product Purpose

A command surface for orchestrating coordinated, role-differentiated content
across multiple Telegram personas, with mandatory operator approval per
post. Success is when an audience that arrived skeptical leaves feeling that
this is an actual piece of operator tradecraft, not a tech-demo skin over a
chat completion API.

The product exists to make three properties unmistakable on contact:
mandatory human-in-the-loop, append-only audit trail, and persona coherence
across coordinated posts.

## Brand Personality

Operator-grade, evidentiary, deliberate.

The voice is sober and procedural. It assumes the user is competent and
that what they are doing is consequential. There is no celebration when a
post lands; there is a record. There is no friendly onboarding; there is a
pre-mission readiness check. Copy should feel closer to a SITREP than to a
SaaS welcome modal.

The aesthetic lane is the intersection of Palantir Foundry / Gotham
(operator density, dark restrained surfaces, panel-heavy) and the
declassified-document / dossier / FOIA tradition (editorial typography,
classification banners, marked sections, footer metadata, monospace IDs).
The crossing of these two lanes — operator console *as* working dossier —
is the design's signature move and the thing that should make the surface
unforgettable on first contact.

## Anti-references

- **Generic SaaS chatbot UI.** White or cream backgrounds, purple/teal
  gradients, rounded-everything, illustrated empty states, friendly
  conversational copy. The OpenAI / Anthropic / ChatGPT-clone aesthetic.
  This dilutes the operator-tool story and makes the surface read as a
  consumer toy.
- **Hollywood hacker movie.** Matrix-green text rain, terminal beeps,
  fake glitch effects, scanlines, "ENHANCE" buttons. NATSEC audiences
  recognize this as cosplay and will write the project off as unserious.
- **AI-workflow tool look.** n8n / Make / Zapier / Langflow aesthetic:
  cream backgrounds, rounded card grids, illustrated nodes, "automation"
  sparkle icons. Wrong genre.
- **Hero-metric template.** Big number / small label / supporting stats
  / gradient accent. SaaS dashboard cliche.

## Design Principles

1. **The operator is the camera.** Every approval, edit, and reject is the
   user's conscience executing in code. The UI's job is to make those
   actions feel weighty and reversible — not breezy. Approval should never
   be a single thoughtless tap.

2. **Document, don't decorate.** The dashboard should read as a working
   case file, not an interface around one. Sections should carry their own
   metadata (ids, timestamps, content hashes, operator identity).
   Decoration that doesn't carry information is removed.

3. **Hide nothing.** The append-only audit log is the source of truth, not
   the database, not the UI. Surfaces should expose it directly rather than
   summarize it away. If a thing is in the log, the UI must be able to
   reach it; if it isn't, the UI must not pretend it is.

4. **Refuse the genre defaults.** Don't reach for matrix-green theatrics
   or cream-pastel SaaS. The tool earns trust by *not* looking like
   anything else in the LLM-product hype cycle.

5. **Calm under pressure.** No countdown timers, no anxious spinners, no
   urgency theater. The pace should feel like a court reporter's, not a
   SOC at peak alert. Operator-in-the-loop is slow on purpose; the UI
   shouldn't apologize for that.

## Accessibility & Inclusion

- WCAG 2.1 AA contrast on all text and interactive elements (the projector
  glare scene makes this a usability requirement, not just a compliance
  one).
- Respect `prefers-reduced-motion` — no entrance animations or transitions
  for users who opt out.
- Keyboard navigation through the approval queue (j/k or arrow keys to
  move between cards, A to approve, R to reject, E to edit). The tool
  exists to support careful, deliberate work; mouse-only would betray that.
- Type scale and contrast must remain legible from row 5 of a demo room
  through projector glare. Treat that as the worst-case viewing condition.
