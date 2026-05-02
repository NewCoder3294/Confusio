"""Persona profile loader + validator. Fails fast on missing fields or sessions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

PERSONAS_DIR = Path(__file__).parent / "personas"
SOCIAL_DIR = Path(__file__).parent

Role = Literal["seed", "witness", "reaction", "aggregator"]


class PostingSchedule(BaseModel):
    active_hours_local: list[int] = Field(default_factory=lambda: [0, 24])
    avg_posts_per_day: int = 1


class Persona(BaseModel):
    id: str
    name: str
    session_path: str
    language: str  # ISO 639-1
    style: str
    examples: list[str]

    geo_anchor: str | None = None
    bio_short: str | None = None
    backstory: str | None = None
    vocabulary_quirks: list[str] = Field(default_factory=list)
    topic_focus: list[str] = Field(default_factory=list)
    posting_schedule: PostingSchedule = Field(default_factory=PostingSchedule)
    knows: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _id_chars(cls, v: str) -> str:
        if not v or not all(c.isalnum() or c == "_" for c in v):
            raise ValueError("persona id must be alphanumeric/underscore")
        return v

    @field_validator("language")
    @classmethod
    def _lang(cls, v: str) -> str:
        if len(v) != 2 or not v.isalpha():
            raise ValueError("language must be ISO 639-1 2-letter code")
        return v.lower()

    @field_validator("examples")
    @classmethod
    def _examples_nonempty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("personas must include at least one example post")
        return v

    def resolved_session_path(self) -> Path:
        p = Path(self.session_path)
        return p if p.is_absolute() else SOCIAL_DIR / p


class PersonaLoadError(RuntimeError):
    pass


def load_personas(
    *, require_sessions: bool = True, personas_dir: Path = PERSONAS_DIR
) -> dict[str, Persona]:
    """Load all *.json under personas_dir.

    Per FR-1.3: fails fast on missing required field or missing session file
    when require_sessions=True. Dev tools that don't need live Telegram can
    pass require_sessions=False.
    """
    if not personas_dir.is_dir():
        raise PersonaLoadError(f"personas dir not found: {personas_dir}")

    out: dict[str, Persona] = {}
    files = sorted(personas_dir.glob("*.json"))
    if not files:
        raise PersonaLoadError(f"no persona files in {personas_dir}")

    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PersonaLoadError(f"invalid JSON in {f.name}: {exc}") from exc
        try:
            persona = Persona.model_validate(data)
        except ValidationError as exc:
            raise PersonaLoadError(f"invalid persona {f.name}: {exc}") from exc

        if persona.id in out:
            raise PersonaLoadError(f"duplicate persona id {persona.id} in {f.name}")
        if persona.id != f.stem:
            raise PersonaLoadError(
                f"persona id '{persona.id}' must match filename stem '{f.stem}'"
            )

        if require_sessions and not persona.resolved_session_path().exists():
            raise PersonaLoadError(
                f"session file missing for {persona.id}: "
                f"{persona.resolved_session_path()}. "
                "Run scripts/login_persona.py to create it."
            )

        out[persona.id] = persona
    return out
