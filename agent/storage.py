"""Persistent lead storage.

SQLite via aiosqlite was chosen deliberately over a heavier DB:
- Zero external services to stand up for a small single-location business.
- Works identically in local console testing and in a deployed container,
  as long as the DB file lives on a persistent volume (see README/Dockerfile).
- Easy to swap out later — all access goes through the LeadStore class below,
  so migrating to Postgres/Airtable/CRM later only touches this file.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from pathlib import Path

import aiosqlite
import asyncpg

logger = logging.getLogger("bvhomes-agent.storage")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    room_name TEXT,
    caller_number TEXT,
    name TEXT,
    phone_number TEXT,
    furniture_requirement TEXT,
    design TEXT,
    quantity TEXT,
    size TEXT,
    budget TEXT,
    delivery_location TEXT,
    special_requirements TEXT,
    lead_type TEXT NOT NULL DEFAULT 'general',
    callback_reason TEXT,
    status TEXT NOT NULL DEFAULT 'new'
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_name TEXT NOT NULL UNIQUE,
    customer_name TEXT,
    customer_phone TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    transcript TEXT NOT NULL DEFAULT '',
    ai_summary TEXT NOT NULL DEFAULT '',
    topics_discussed TEXT NOT NULL DEFAULT '',
    products_discussed TEXT NOT NULL DEFAULT '',
    budget TEXT NOT NULL DEFAULT '',
    requirements TEXT NOT NULL DEFAULT '',
    lead_status TEXT NOT NULL DEFAULT 'new',
    follow_up_action TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_customer_name ON conversations(customer_name);
CREATE INDEX IF NOT EXISTS idx_conversations_lead_status ON conversations(lead_status);
"""

_POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id BIGSERIAL PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    room_name TEXT, caller_number TEXT, name TEXT, phone_number TEXT,
    furniture_requirement TEXT, design TEXT, quantity TEXT, size TEXT, budget TEXT,
    delivery_location TEXT, special_requirements TEXT,
    lead_type TEXT NOT NULL DEFAULT 'general', callback_reason TEXT,
    status TEXT NOT NULL DEFAULT 'new'
);
CREATE TABLE IF NOT EXISTS conversations (
    id BIGSERIAL PRIMARY KEY, room_name TEXT NOT NULL UNIQUE,
    customer_name TEXT, customer_phone TEXT, started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL, duration_seconds INTEGER NOT NULL DEFAULT 0,
    transcript TEXT NOT NULL DEFAULT '', ai_summary TEXT NOT NULL DEFAULT '',
    topics_discussed TEXT NOT NULL DEFAULT '', products_discussed TEXT NOT NULL DEFAULT '',
    budget TEXT NOT NULL DEFAULT '', requirements TEXT NOT NULL DEFAULT '',
    lead_status TEXT NOT NULL DEFAULT 'new', follow_up_action TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_customer_name ON conversations(customer_name);
CREATE INDEX IF NOT EXISTS idx_conversations_lead_status ON conversations(lead_status);
"""


@dataclass
class LeadRecord:
    room_name: str = ""
    caller_number: str = ""
    name: str = ""
    phone_number: str = ""
    furniture_requirement: str = ""
    design: str = ""
    quantity: str = ""
    size: str = ""
    budget: str = ""
    delivery_location: str = ""
    special_requirements: str = ""
    lead_type: str = "general"  # "general" | "custom_callback"
    callback_reason: str = ""
    id: int | None = field(default=None)


@dataclass
class ConversationRecord:
    """A completed call and its customer-facing conversation record."""

    room_name: str
    started_at: str
    ended_at: str
    duration_seconds: int
    transcript: str
    ai_summary: str = ""
    topics_discussed: str = ""
    products_discussed: str = ""
    budget: str = ""
    requirements: str = ""
    customer_name: str = ""
    customer_phone: str = ""
    lead_status: str = "new"
    follow_up_action: str = ""
    id: int | None = field(default=None)


class LeadStore:
    """Async lead/conversation store using PostgreSQL or local SQLite.

    Set DATABASE_URL to a postgresql:// (or postgres://) DSN for production.
    Passing a filesystem path keeps the original SQLite behavior for local tests.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._is_postgres = self.db_path.startswith(("postgresql://", "postgres://"))
        self._pool: asyncpg.Pool | None = None

    async def init(self) -> None:
        if self._is_postgres:
            if self._pool is None:
                self._pool = await asyncpg.create_pool(self.db_path, min_size=1, max_size=5)
            async with self._pool.acquire() as db:
                await db.execute(_POSTGRES_SCHEMA)
            logger.info("PostgreSQL lead store initialized")
            return
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()
        logger.info(f"Lead store initialized at {self.db_path}")

    async def close(self) -> None:
        """Release PostgreSQL connections when a host explicitly shuts down."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def _postgres(self) -> asyncpg.Pool:
        if self._pool is None:
            await self.init()
        assert self._pool is not None
        return self._pool

    async def save_lead(self, lead: LeadRecord) -> int:
        """Insert a new lead row and return its id.

        We intentionally always insert rather than upsert-by-phone: a single
        call may legitimately produce more than one row (e.g. an initial
        partial capture followed by a fuller one) and reconciling duplicates
        is a job for whoever consumes this table (CRM import, staff review),
        not for the voice agent to guess at.
        """
        now = datetime.datetime.now(datetime.UTC).isoformat()
        if self._is_postgres:
            pool = await self._postgres()
            lead_id = await pool.fetchval(
                """INSERT INTO leads (created_at, updated_at, room_name, caller_number, name,
                phone_number, furniture_requirement, design, quantity, size, budget,
                delivery_location, special_requirements, lead_type, callback_reason, status)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,'new') RETURNING id""",
                now, now, lead.room_name, lead.caller_number, lead.name, lead.phone_number,
                lead.furniture_requirement, lead.design, lead.quantity, lead.size, lead.budget,
                lead.delivery_location, lead.special_requirements, lead.lead_type, lead.callback_reason,
            )
            return int(lead_id)
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO leads (
                    created_at, updated_at, room_name, caller_number, name,
                    phone_number, furniture_requirement, design, quantity,
                    size, budget, delivery_location, special_requirements,
                    lead_type, callback_reason, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
                """,
                (
                    now,
                    now,
                    lead.room_name,
                    lead.caller_number,
                    lead.name,
                    lead.phone_number,
                    lead.furniture_requirement,
                    lead.design,
                    lead.quantity,
                    lead.size,
                    lead.budget,
                    lead.delivery_location,
                    lead.special_requirements,
                    lead.lead_type,
                    lead.callback_reason,
                ),
            )
            await db.commit()
            lead_id = cursor.lastrowid
        logger.info(f"Saved lead id={lead_id} type={lead.lead_type} phone={lead.phone_number!r}")
        return lead_id

    async def list_leads(self, limit: int = 100) -> list[dict]:
        limit = max(1, min(limit, 500))
        if self._is_postgres:
            pool = await self._postgres()
            return [dict(row) for row in await pool.fetch("SELECT * FROM leads ORDER BY id DESC LIMIT $1", limit)]
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM leads ORDER BY id DESC LIMIT ?", (limit,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def latest_lead_for_room(self, room_name: str) -> dict | None:
        """Return the most complete/latest lead captured during a room, if any."""
        if self._is_postgres:
            pool = await self._postgres()
            row = await pool.fetchrow(
                "SELECT * FROM leads WHERE room_name = $1 ORDER BY id DESC LIMIT 1", room_name
            )
            return dict(row) if row else None
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM leads WHERE room_name = ? ORDER BY id DESC LIMIT 1",
                (room_name,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def save_conversation(self, conversation: ConversationRecord) -> int:
        """Save one completed room. Re-running shutdown handling updates the same room."""
        now = datetime.datetime.now(datetime.UTC).isoformat()
        values = (
            conversation.room_name, conversation.customer_name, conversation.customer_phone,
            conversation.started_at, conversation.ended_at, conversation.duration_seconds,
            conversation.transcript, conversation.ai_summary, conversation.topics_discussed,
            conversation.products_discussed, conversation.budget, conversation.requirements,
            conversation.lead_status, conversation.follow_up_action, now,
        )
        if self._is_postgres:
            pool = await self._postgres()
            conversation_id = await pool.fetchval(
                """INSERT INTO conversations (room_name, customer_name, customer_phone, started_at,
                ended_at, duration_seconds, transcript, ai_summary, topics_discussed,
                products_discussed, budget, requirements, lead_status, follow_up_action, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                ON CONFLICT(room_name) DO UPDATE SET customer_name=excluded.customer_name,
                customer_phone=excluded.customer_phone, ended_at=excluded.ended_at,
                duration_seconds=excluded.duration_seconds, transcript=excluded.transcript,
                ai_summary=excluded.ai_summary, topics_discussed=excluded.topics_discussed,
                products_discussed=excluded.products_discussed, budget=excluded.budget,
                requirements=excluded.requirements, lead_status=excluded.lead_status,
                follow_up_action=excluded.follow_up_action RETURNING id""",
                *values,
            )
            return int(conversation_id)
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO conversations (
                    room_name, customer_name, customer_phone, started_at, ended_at,
                    duration_seconds, transcript, ai_summary, topics_discussed,
                    products_discussed, budget, requirements, lead_status,
                    follow_up_action, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(room_name) DO UPDATE SET
                    customer_name=excluded.customer_name,
                    customer_phone=excluded.customer_phone,
                    ended_at=excluded.ended_at,
                    duration_seconds=excluded.duration_seconds,
                    transcript=excluded.transcript,
                    ai_summary=excluded.ai_summary,
                    topics_discussed=excluded.topics_discussed,
                    products_discussed=excluded.products_discussed,
                    budget=excluded.budget,
                    requirements=excluded.requirements,
                    lead_status=excluded.lead_status,
                    follow_up_action=excluded.follow_up_action
                """,
                values,
            )
            await db.commit()
            conversation_id = cursor.lastrowid
        logger.info("Saved conversation room=%s", conversation.room_name)
        return conversation_id

    async def list_conversations(
        self,
        *,
        customer: str = "",
        date: str = "",
        product: str = "",
        lead_status: str = "",
        limit: int = 100,
    ) -> list[dict]:
        """List completed calls with optional dashboard/API filters."""
        clauses: list[str] = []
        params: list[object] = []
        if customer:
            clauses.append("(customer_name ILIKE $1 OR customer_phone ILIKE $2)" if self._is_postgres else "(customer_name LIKE ? OR customer_phone LIKE ?)")
            term = f"%{customer}%"
            params.extend((term, term))
        if date:
            clauses.append(
                f"(created_at::timestamptz)::date = ${len(params) + 1}::date"
                if self._is_postgres
                else "date(created_at) = date(?)"
            )
            params.append(date)
        if product:
            clauses.append(f"products_discussed ILIKE ${len(params) + 1}" if self._is_postgres else "products_discussed LIKE ?")
            params.append(f"%{product}%")
        if lead_status:
            clauses.append(f"lead_status = ${len(params) + 1}" if self._is_postgres else "lead_status = ?")
            params.append(lead_status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(limit, 500)))
        if self._is_postgres:
            pool = await self._postgres()
            query = "SELECT * FROM conversations" + where + f" ORDER BY id DESC LIMIT ${len(params)}"
            return [dict(row) for row in await pool.fetch(query, *params)]
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM conversations" + where + " ORDER BY id DESC LIMIT ?", params
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def get_conversation(self, conversation_id: int) -> dict | None:
        if self._is_postgres:
            pool = await self._postgres()
            row = await pool.fetchrow("SELECT * FROM conversations WHERE id = $1", conversation_id)
            return dict(row) if row else None
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None
