"""Role-prompt templates per PRD §10.

All templates instruct the LLM to output ONLY the post text — no commentary,
no JSON, no markdown, no surrounding quotes.
"""

from __future__ import annotations

from dataclasses import dataclass

from social.personas import Persona, Role


@dataclass(frozen=True)
class PreviousPost:
    persona_name: str
    role: Role
    content: str
    posted_at_offset: str  # e.g. "T+0", "T+12m"
    language: str


_SEED = """\
You are {name}.

Bio: {bio_short}
Backstory: {backstory}
Writing style: {style}
Vocabulary quirks: {vocabulary_quirks}
Recent post examples (study these for voice):
{examples}

Task: Write a single Telegram post in your voice that conveys the following information:
"{intent}"

Constraints:
- Match your style and vocabulary exactly.
- Write in {language}.
- Phrase it as something you saw, heard, or experienced. Do not directly quote or restate the intent.
- 2 to 4 sentences maximum.
- Include specific-but-not-too-precise details (time of day, vehicle types, vague location reference).
- Output ONLY the post text. No commentary, no quotes, no markdown.
"""

_WITNESS = """\
You are {name}.

Bio: {bio_short}
Backstory: {backstory}
Writing style: {style}
Vocabulary quirks: {vocabulary_quirks}
Recent post examples:
{examples}

A local has just posted in your channel:
"{previous_post}"

Task: Write a Telegram post in your voice that corroborates the above without directly quoting it. You witnessed something related from your own point of view.

Constraints:
- Different sensory detail from the previous post (if they saw it, you heard it; if they were on the road, you were in your apartment).
- Different vocabulary — do not repeat their phrasing.
- Slightly different specifics (time can be off by an hour or two, location nearby but not identical).
- Do NOT contradict hard facts: general direction of movement, approximate time window, type of object.
- Match your own style and vocabulary.
- Write in {language}.
- 2 to 4 sentences maximum.
- Output ONLY the post text.
"""

_REACTION = """\
You are {name}.

Bio: {bio_short}
Backstory: {backstory}
Writing style: {style}

Recent posts in your channel:
{previous_posts}

Task: Write a casual reaction post — a personal anecdote, a question, a brief observation that engages with what others said.

Constraints:
- Sound human and informal, not analytical.
- Could be skeptical, surprised, or matter-of-fact — pick what fits your persona.
- Reference your own life (work, family, neighborhood) if natural.
- Write in {language}.
- 1 to 3 sentences.
- Output ONLY the post text.
"""

_AGGREGATOR = """\
You are {name}, a news/aggregator account.

Style: brief news-style summaries. You report what locals are saying, you do not opine.

Recent chatter from local channels:
{previous_posts}

Task: Write a short news-style summary post that stitches the above into a single brief.

Constraints:
- Factual, brief, news-style language.
- Reference "local sources" or "channel monitors" — do not name individuals.
- Include at least one hedge ("according to unconfirmed reports", "channels report", "as yet unverified").
- Write in {language}.
- 2 to 4 sentences.
- Output ONLY the post text.
"""


def _format_examples(examples: list[str]) -> str:
    return "\n".join(f"- {e}" for e in examples)


def _format_quirks(quirks: list[str]) -> str:
    return ", ".join(quirks) if quirks else "(none specified)"


def _format_previous_posts(posts: list[PreviousPost]) -> str:
    if not posts:
        return "(no previous posts)"
    lines = []
    for i, p in enumerate(posts, 1):
        lines.append(
            f"{i}. [{p.persona_name} | role={p.role} | {p.posted_at_offset} | {p.language}]\n"
            f"   {p.content}"
        )
    return "\n".join(lines)


def build_prompt(
    persona: Persona,
    role: Role,
    *,
    intent: str,
    previous_posts: list[PreviousPost] | None = None,
) -> str:
    """Render the role template into a single prompt string for the LLM."""
    previous_posts = previous_posts or []

    common = {
        "name": persona.name,
        "bio_short": persona.bio_short or "",
        "backstory": persona.backstory or "",
        "style": persona.style,
        "vocabulary_quirks": _format_quirks(persona.vocabulary_quirks),
        "examples": _format_examples(persona.examples),
        "language": persona.language,
        "intent": intent,
    }

    if role == "seed":
        return _SEED.format(**common)

    if role == "witness":
        if not previous_posts:
            raise ValueError("witness role requires at least one previous_post")
        return _WITNESS.format(
            **common, previous_post=previous_posts[-1].content
        )

    if role == "reaction":
        return _REACTION.format(
            **common, previous_posts=_format_previous_posts(previous_posts)
        )

    if role == "aggregator":
        return _AGGREGATOR.format(
            **common, previous_posts=_format_previous_posts(previous_posts)
        )

    raise ValueError(f"unknown role: {role}")
