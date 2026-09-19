from __future__ import annotations

import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "bvhomes_knowledge.db"
DOCS_DIR = Path(__file__).resolve().parent / "knowledge"


def init_rag() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5(path, title, content)"
        )
        db.commit()


def _tokens(text: str) -> set[str]:
    return {x for x in re.findall(r"[\w]+", text.lower()) if len(x) > 1}


def ingest_documents() -> int:
    init_rag()
    count = 0
    with sqlite3.connect(DB_PATH) as db:
        for path in sorted(DOCS_DIR.rglob("*")):
            if path.suffix.lower() not in {".txt", ".md"}:
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            title = path.stem.replace("-", " ").replace("_", " ")
            db.execute("DELETE FROM docs WHERE path = ?", (str(path.relative_to(DOCS_DIR)),))
            db.execute(
                "INSERT INTO docs(path, title, content) VALUES (?, ?, ?)",
                (str(path.relative_to(DOCS_DIR)), title, content),
            )
            count += 1
        db.commit()
    return count


def search_knowledge(query: str, limit: int = 4) -> list[dict]:
    init_rag()
    terms = sorted(_tokens(query))
    if not terms:
        return []

    # FTS5 query: AND is intentionally strict for short business questions;
    # callers can retry with fewer terms when no result is found.
    match = " AND ".join(f'"{t}"' for t in terms[:8])
    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute(
            """SELECT path, title, snippet(docs, 2, '[', ']', '…', 28)
               FROM docs WHERE docs MATCH ? LIMIT ?""",
            (match, max(1, min(limit, 8))),
        ).fetchall()

    return [
        {"path": row[0], "title": row[1], "snippet": row[2]}
        for row in rows
    ]
