"""History: every call, local, in one SQLite file you can open with anything.

Failed calls are stored too — a fallback you cannot see later is a fallback you
cannot audit. Full-text search uses FTS5 when the SQLite build has it and falls
back to LIKE when it does not, so search never just breaks.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY,
    created_at    TEXT NOT NULL,
    session       TEXT,
    provider      TEXT NOT NULL,
    model         TEXT NOT NULL,
    prompt        TEXT NOT NULL,
    response      TEXT,
    input_tokens  INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd      REAL,
    latency_ms    INTEGER,
    status        TEXT NOT NULL,          -- ok | error
    error         TEXT,
    fallback_from TEXT
);
CREATE INDEX IF NOT EXISTS runs_created ON runs(created_at);
CREATE INDEX IF NOT EXISTS runs_model ON runs(model);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS runs_fts USING fts5(
    prompt, response, content='runs', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS runs_ai AFTER INSERT ON runs BEGIN
    INSERT INTO runs_fts(rowid, prompt, response) VALUES (new.id, new.prompt, new.response);
END;
"""


@dataclass
class Run:
    provider: str
    model: str
    prompt: str
    response: str | None
    status: str = "ok"
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    latency_ms: int | None = None
    error: str | None = None
    fallback_from: str | None = None
    session: str | None = None


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        try:
            self.db.executescript(FTS_SCHEMA)
            self.fts = True
        except sqlite3.OperationalError:
            self.fts = False

    def close(self) -> None:
        self.db.close()

    def add(self, run: Run) -> int:
        row = dict(run.__dict__, created_at=datetime.now(UTC).isoformat(timespec="seconds"))
        cols = ", ".join(row)
        marks = ", ".join(f":{k}" for k in row)
        with self.db:
            cur = self.db.execute(f"INSERT INTO runs ({cols}) VALUES ({marks})", row)
        return cur.lastrowid

    def history(self, limit: int = 20, model: str | None = None) -> list[dict[str, Any]]:
        sql, args = "SELECT * FROM runs", []
        if model:
            sql += " WHERE model = ? OR provider || '/' || model = ?"
            args += [model, model]
        sql += " ORDER BY id DESC LIMIT ?"
        return [dict(r) for r in self.db.execute(sql, [*args, limit])]

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        if self.fts:
            # Quote every term so user punctuation is text, not FTS syntax.
            terms = " ".join('"' + t.replace('"', '""') + '"' for t in query.split())
            sql = ("SELECT runs.* FROM runs_fts JOIN runs ON runs.id = runs_fts.rowid "
                   "WHERE runs_fts MATCH ? ORDER BY runs.id DESC LIMIT ?")
            return [dict(r) for r in self.db.execute(sql, [terms, limit])]
        like = f"%{query}%"
        sql = ("SELECT * FROM runs WHERE prompt LIKE ? OR response LIKE ? "
               "ORDER BY id DESC LIMIT ?")
        return [dict(r) for r in self.db.execute(sql, [like, like, limit])]

    def stats(self, session: str | None = None) -> list[dict[str, Any]]:
        sql = """
            SELECT provider, model, COUNT(*) AS calls,
                   SUM(status = 'error') AS errors,
                   SUM(input_tokens) AS input_tokens,
                   SUM(output_tokens) AS output_tokens,
                   SUM(cost_usd) AS cost_usd,
                   SUM(cost_usd IS NULL AND status = 'ok') AS unpriced,
                   CAST(AVG(CASE WHEN status = 'ok' THEN latency_ms END) AS INTEGER)
                       AS avg_latency_ms
            FROM runs {where} GROUP BY provider, model ORDER BY calls DESC
        """
        if session:
            return [dict(r) for r in self.db.execute(sql.format(where="WHERE session = ?"),
                                                     [session])]
        return [dict(r) for r in self.db.execute(sql.format(where=""))]
