"""로컬 JSON 기반 체크포인트 저장소 (DB 대체).

운영 한계:
- 이 저장소는 단일 프로세스 로컬 테스트/임시용이다.
- 규모가 커지면 SQLite 등 경량 DB로 전환해야 한다. (P2 계획 참조)
- atomic write(tmp → rename)로 부분 쓰기 손상은 방지한다.
- 멀티 프로세스 동시 접근은 지원하지 않는다.

async 경로에서 이 저장소를 호출할 때는 반드시 bounded ThreadPoolExecutor로
오프로드해야 한다. analyzer_service._REPO_EXECUTOR 참조.
"""
import json
import logging
import threading
from pathlib import Path
from typing import List
from LLMEngine.core.ports import IRepository
from LLMEngine.core.schemas import ChunkResult, ChunkStateRecord

logger = logging.getLogger(__name__)


class LocalJsonRepository(IRepository):
    def __init__(self, base_dir: str = "./checkpoints"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _get_path(self, lecture_id: str) -> Path:
        return self.base_dir / f"{lecture_id}_checkpoint.json"

    def save_chunk_state(self, record: ChunkStateRecord) -> None:
        """ChunkStateRecord를 체크포인트 파일에 저장한다.

        atomic write(tmp → rename)로 강제 종료 시 부분 쓰기 손상을 방지한다.
        """
        p = self._get_path(record.lecture_id)
        cid = str(record.chunk_id)

        with self._lock:
            if p.exists():
                try:
                    state = json.loads(p.read_text("utf-8"))
                except json.JSONDecodeError as e:
                    logger.error(
                        "lecture_id=%s 체크포인트 파일 손상 — 기존 진행 상황이 유실됩니다. "
                        "파일: %s 원인: %s",
                        record.lecture_id, p, e,
                    )
                    raise RuntimeError(
                        f"체크포인트 파일 손상으로 저장 불가: {p}"
                    ) from e
            else:
                state = {}

            if cid not in state:
                state[cid] = {}

            state[cid]["status"] = record.status
            if record.result and record.status == "SUCCESS":
                state[cid]["result"] = record.result.model_dump(mode="json")
            if record.failure_reason:
                state[cid]["failure_reason"] = record.failure_reason

            tmp = p.with_suffix(".tmp")
            try:
                tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")
                tmp.replace(p)
            except Exception as e:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
                raise

    def get_completed_chunks(self, lecture_id: str) -> List[ChunkResult]:
        p = self._get_path(lecture_id)

        with self._lock:
            if not p.exists():
                return []
            try:
                state = json.loads(p.read_text("utf-8"))
                return [
                    ChunkResult.model_validate(d["result"])
                    for d in state.values()
                    if d.get("status") == "SUCCESS" and "result" in d
                ]
            except json.JSONDecodeError as e:
                logger.error(
                    "lecture_id=%s 체크포인트 파일 손상 — 진행 상황 복구 불가, 처음부터 재시작합니다. "
                    "파일: %s 원인: %s",
                    lecture_id, p, e,
                )
                return []