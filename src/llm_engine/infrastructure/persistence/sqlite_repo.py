"""SQLite-backed checkpoint repository."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import List

from src.llm_engine.core.ports import IRepository
from src.llm_engine.core.schemas import ChunkResult, ChunkStateRecord

logger = logging.getLogger(__name__)

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS chunk_state (
    lecture_id TEXT NOT NULL,
    chunk_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    result_json TEXT,
    failure_reason TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (lecture_id, chunk_id)
);
"""


class SQLiteRepository(IRepository):
    def __init__(self, db_path: str | Path = "./checkpoints.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(_INIT_SQL)
        self._conn.commit()
        logger.info("Initialized SQLiteRepository at %s", self._db_path)

    def save_chunk_state(self, record: ChunkStateRecord) -> None:
        result_json = (
            json.dumps(record.result.model_dump(mode="json"), ensure_ascii=False)
            if record.result and record.status == "SUCCESS"
            else None
        )
        self._conn.execute(
            """
            INSERT INTO chunk_state (lecture_id, chunk_id, status, result_json, failure_reason, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(lecture_id, chunk_id) DO UPDATE SET
                status = excluded.status,
                result_json = COALESCE(excluded.result_json, chunk_state.result_json),
                failure_reason = excluded.failure_reason,
                updated_at = excluded.updated_at
            """,
            (
                record.lecture_id,
                record.chunk_id,
                record.status,
                result_json,
                record.failure_reason,
            ),
        )
        self._conn.commit()

    def get_completed_chunks(self, lecture_id: str) -> List[ChunkResult]:
        cursor = self._conn.execute(
            """
            SELECT result_json
            FROM chunk_state
            WHERE lecture_id = ? AND status = 'SUCCESS' AND result_json IS NOT NULL
            """,
            (lecture_id,),
        )
        results: List[ChunkResult] = []
        for (result_json,) in cursor.fetchall():
            try:
                results.append(ChunkResult.model_validate(json.loads(result_json)))
            except Exception as exc:
                logger.error("Failed to parse SQLite checkpoint for %s: %s", lecture_id, exc)
        return results

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]

    def __enter__(self) -> SQLiteRepository:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
