"""Local JSON checkpoint repository.

This is intentionally a lightweight single-process repository. It uses
atomic writes (`tmp -> replace`) to avoid partial-write corruption when the
process stops mid-write.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import List

from src.llm_engine.core.ports import IRepository
from src.llm_engine.core.schemas import ChunkResult, ChunkStateRecord

logger = logging.getLogger(__name__)


class LocalJsonRepository(IRepository):
    def __init__(self, base_dir: str = "./checkpoints") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _get_path(self, lecture_id: str) -> Path:
        return self.base_dir / f"{lecture_id}_checkpoint.json"

    def save_chunk_state(self, record: ChunkStateRecord) -> None:
        path = self._get_path(record.lecture_id)
        chunk_key = str(record.chunk_id)

        with self._lock:
            if path.exists():
                try:
                    state = json.loads(path.read_text("utf-8"))
                except json.JSONDecodeError as exc:
                    logger.error(
                        "checkpoint corrupted; cannot save lecture_id=%s path=%s error=%s",
                        record.lecture_id,
                        path,
                        exc,
                    )
                    raise RuntimeError(f"Checkpoint file is corrupted: {path}") from exc
            else:
                state = {}

            state.setdefault(chunk_key, {})
            state[chunk_key]["status"] = record.status
            if record.result is not None and record.status == "SUCCESS":
                state[chunk_key]["result"] = record.result.model_dump(mode="json")
            if record.failure_reason:
                state[chunk_key]["failure_reason"] = record.failure_reason

            tmp = path.with_suffix(".tmp")
            try:
                tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")
                tmp.replace(path)
            finally:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)

    def get_completed_chunks(self, lecture_id: str) -> List[ChunkResult]:
        path = self._get_path(lecture_id)

        with self._lock:
            if not path.exists():
                return []

            try:
                state = json.loads(path.read_text("utf-8"))
            except json.JSONDecodeError as exc:
                logger.error(
                    "checkpoint corrupted; cannot restore lecture_id=%s path=%s error=%s",
                    lecture_id,
                    path,
                    exc,
                )
                return []

            return [
                ChunkResult.model_validate(item["result"])
                for item in state.values()
                if item.get("status") == "SUCCESS" and "result" in item
            ]
