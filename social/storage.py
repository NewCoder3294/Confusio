"""Persistence layer.

- sqlite (aiosqlite) is the queryable view: Campaign + GeneratedPost.
- posts.jsonl is the append-only audit log — source of truth per PRD §6.7.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import aiosqlite

DB_PATH = Path(__file__).parent / "mendacity.db"
LOG_PATH = Path(__file__).parent / "posts.jsonl"

CampaignStatus = Literal["created", "running", "paused", "completed", "aborted"]
PostStatus = Literal["pending_approval", "approved", "rejected", "posted", "failed"]
Role = Literal["seed", "witness", "reaction", "aggregator"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class Campaign:
    id: str
    intent: str
    channel: str
    delay_range_seconds: tuple[int, int]
    status: CampaignStatus
    created_at: str
    created_by: str
    roster: dict[str, Role]  # persona_id -> role

    @classmethod
    def new(
        cls,
        *,
        intent: str,
        channel: str,
        delay_range_seconds: tuple[int, int],
        created_by: str,
        roster: dict[str, Role],
    ) -> "Campaign":
        return cls(
            id=new_id("camp"),
            intent=intent,
            channel=channel,
            delay_range_seconds=delay_range_seconds,
            status="created",
            created_at=now_iso(),
            created_by=created_by,
            roster=roster,
        )

    def to_row(self) -> tuple[Any, ...]:
        return (
            self.id,
            self.intent,
            self.channel,
            json.dumps(list(self.delay_range_seconds)),
            self.status,
            self.created_at,
            self.created_by,
            json.dumps(self.roster),
        )

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "Campaign":
        delay = json.loads(row["delay_range_seconds"])
        return cls(
            id=row["id"],
            intent=row["intent"],
            channel=row["channel"],
            delay_range_seconds=(int(delay[0]), int(delay[1])),
            status=row["status"],
            created_at=row["created_at"],
            created_by=row["created_by"],
            roster=json.loads(row["roster"]),
        )


@dataclass
class GeneratedPost:
    id: str
    campaign_id: str
    persona_id: str
    role: Role
    generated_content: str
    status: PostStatus
    generated_at: str
    edited_content: str | None = None
    decided_at: str | None = None
    decided_by: str | None = None
    posted_at: str | None = None
    telegram_message_id: str | None = None
    error: str | None = None

    @classmethod
    def new(
        cls,
        *,
        campaign_id: str,
        persona_id: str,
        role: Role,
        generated_content: str,
    ) -> "GeneratedPost":
        return cls(
            id=new_id("post"),
            campaign_id=campaign_id,
            persona_id=persona_id,
            role=role,
            generated_content=generated_content,
            status="pending_approval",
            generated_at=now_iso(),
        )

    @property
    def final_content(self) -> str:
        return self.edited_content or self.generated_content

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "GeneratedPost":
        return cls(
            id=row["id"],
            campaign_id=row["campaign_id"],
            persona_id=row["persona_id"],
            role=row["role"],
            generated_content=row["generated_content"],
            status=row["status"],
            generated_at=row["generated_at"],
            edited_content=row["edited_content"],
            decided_at=row["decided_at"],
            decided_by=row["decided_by"],
            posted_at=row["posted_at"],
            telegram_message_id=row["telegram_message_id"],
            error=row["error"],
        )


_SCHEMA = """
CREATE TABLE IF NOT EXISTS campaign (
  id TEXT PRIMARY KEY,
  intent TEXT NOT NULL,
  channel TEXT NOT NULL,
  delay_range_seconds TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL,
  roster TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS generated_post (
  id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES campaign(id),
  persona_id TEXT NOT NULL,
  role TEXT NOT NULL,
  generated_content TEXT NOT NULL,
  edited_content TEXT,
  status TEXT NOT NULL,
  generated_at TEXT NOT NULL,
  decided_at TEXT,
  decided_by TEXT,
  posted_at TEXT,
  telegram_message_id TEXT,
  error TEXT
);

CREATE INDEX IF NOT EXISTS idx_post_status ON generated_post(status);
CREATE INDEX IF NOT EXISTS idx_post_campaign ON generated_post(campaign_id);
"""


class Storage:
    def __init__(self, db_path: Path = DB_PATH, log_path: Path = LOG_PATH) -> None:
        self.db_path = db_path
        self.log_path = log_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    # ---------- campaigns ----------

    async def insert_campaign(self, c: Campaign) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO campaign VALUES (?, ?, ?, ?, ?, ?, ?, ?)", c.to_row()
            )
            await db.commit()

    async def get_campaign(self, campaign_id: str) -> Campaign | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM campaign WHERE id = ?", (campaign_id,))
            row = await cur.fetchone()
            return Campaign.from_row(row) if row else None

    async def list_campaigns(self) -> list[Campaign]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM campaign ORDER BY created_at DESC")
            return [Campaign.from_row(r) for r in await cur.fetchall()]

    async def list_active_campaigns(self) -> list[Campaign]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM campaign WHERE status IN ('created', 'running', 'paused')"
            )
            return [Campaign.from_row(r) for r in await cur.fetchall()]

    async def update_campaign_status(
        self, campaign_id: str, status: CampaignStatus
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE campaign SET status = ? WHERE id = ?", (status, campaign_id)
            )
            await db.commit()

    # ---------- generated posts ----------

    async def insert_post(self, p: GeneratedPost) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO generated_post
                   (id, campaign_id, persona_id, role, generated_content,
                    edited_content, status, generated_at, decided_at, decided_by,
                    posted_at, telegram_message_id, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    p.id, p.campaign_id, p.persona_id, p.role,
                    p.generated_content, p.edited_content, p.status,
                    p.generated_at, p.decided_at, p.decided_by,
                    p.posted_at, p.telegram_message_id, p.error,
                ),
            )
            await db.commit()

    async def get_post(self, post_id: str) -> GeneratedPost | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM generated_post WHERE id = ?", (post_id,)
            )
            row = await cur.fetchone()
            return GeneratedPost.from_row(row) if row else None

    async def list_pending(self) -> list[GeneratedPost]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT * FROM generated_post
                   WHERE status = 'pending_approval'
                   ORDER BY generated_at ASC"""
            )
            return [GeneratedPost.from_row(r) for r in await cur.fetchall()]

    async def list_posts_for_campaign(
        self, campaign_id: str, *, statuses: tuple[PostStatus, ...] | None = None
    ) -> list[GeneratedPost]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if statuses:
                placeholders = ",".join("?" * len(statuses))
                cur = await db.execute(
                    f"""SELECT * FROM generated_post
                       WHERE campaign_id = ? AND status IN ({placeholders})
                       ORDER BY generated_at ASC""",
                    (campaign_id, *statuses),
                )
            else:
                cur = await db.execute(
                    """SELECT * FROM generated_post
                       WHERE campaign_id = ?
                       ORDER BY generated_at ASC""",
                    (campaign_id,),
                )
            return [GeneratedPost.from_row(r) for r in await cur.fetchall()]

    async def update_post_decision(
        self,
        post_id: str,
        *,
        status: PostStatus,
        decided_by: str,
        edited_content: str | None = None,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE generated_post
                   SET status = ?, decided_at = ?, decided_by = ?,
                       edited_content = COALESCE(?, edited_content)
                   WHERE id = ?""",
                (status, now_iso(), decided_by, edited_content, post_id),
            )
            await db.commit()

    async def update_post_posted(
        self, post_id: str, *, telegram_message_id: int, posted_at: str
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE generated_post
                   SET status = 'posted', posted_at = ?, telegram_message_id = ?
                   WHERE id = ?""",
                (posted_at, str(telegram_message_id), post_id),
            )
            await db.commit()

    async def update_post_failed(self, post_id: str, *, error: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE generated_post SET status = 'failed', error = ? WHERE id = ?",
                (error, post_id),
            )
            await db.commit()

    # ---------- append-only log ----------

    def append_log(
        self,
        event: str,
        *,
        campaign_id: str | None = None,
        persona_id: str | None = None,
        role: str | None = None,
        content: str | None = None,
        operator: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "ts": now_iso(),
            "event": event,
            "campaign_id": campaign_id,
            "persona_id": persona_id,
            "role": role,
        }
        if content is not None:
            entry["content_hash"] = content_hash(content)
            entry["content"] = content
        if operator is not None:
            entry["operator"] = operator
        if extra:
            entry.update(extra)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def tail_log(self, n: int = 50) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        with self.log_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()[-n:]
        out: list[dict[str, Any]] = []
        for line in lines:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out
