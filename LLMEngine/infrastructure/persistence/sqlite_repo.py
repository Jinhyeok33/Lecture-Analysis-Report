"""SQLite 기반 체크포인트 저장소.

JSON 파일 기반 LocalJsonRepository의 대안 구현체.
IRepository 인터페이스를 그대로 충족하므로 DI 전환만으로 교체 가능하다.

장점:
  - 멀티 프로세스 동시 접근 안전 (WAL 모드)
  - atomic write 보장 (트랜잭션)
  - 대량 체크포인트에서도 일정한 조회 성능

사용법:
    repo = SQLiteRepository("./checkpoints.db")
    service = LectureAnalyzerService(llm_provider, repo, config)
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import List

from LLMEngine.core.ports import IRepository
from LLMEngine.core.schemas import ChunkResult, ChunkStateRecord

logger = logging.getLogger(__name__)

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS chunk_state (
    lecture_id  TEXT    NOT NULL,
    chunk_id    INTEGER NOT NULL,
    status      TEXT    NOT NULL,
    result_json TEXT,
    failure_reason TEXT,
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (lecture_id, chunk_id)
);
"""


class SQLiteRepository(IRepository):
    """SQLite 기반 IRepository 구현체."""

    def __init__(self, db_path: str | Path = "./checkpoints.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(_INIT_SQL)
        self._conn.commit()
        logger.info("SQLiteRepository 초기화 완료: %s", self._db_path)

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
            (record.lecture_id, record.chunk_id, record.status, result_json, record.failure_reason),
        )
        self._conn.commit()

    def get_completed_chunks(self, lecture_id: str) -> List[ChunkResult]:
        cursor = self._conn.execute(
            "SELECT result_json FROM chunk_state WHERE lecture_id = ? AND status = 'SUCCESS' AND result_json IS NOT NULL",
            (lecture_id,),
        )
        results: List[ChunkResult] = []
        for (result_json,) in cursor.fetchall():
            try:
                results.append(ChunkResult.model_validate(json.loads(result_json)))
            except (json.JSONDecodeError, Exception) as e:
                logger.error("lecture_id=%s SQLite 체크포인트 파싱 실패: %s", lecture_id, e)
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
