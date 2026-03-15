"""로컬 JSON 기반 체크포인트 저장소 (DB 대체)."""
import json
import logging
import threading
from pathlib import Path
from typing import List, Optional
from core.ports import IRepository
from core.schemas import ChunkResult

logger = logging.getLogger(__name__)

class LocalJsonRepository(IRepository):
    def __init__(self, base_dir: str = "./checkpoints"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _get_path(self, lecture_id: str) -> Path:
        return self.base_dir / f"{lecture_id}_checkpoint.json"

    def save_chunk_state(self, lecture_id: str, chunk_id: int, status: str, result: Optional[ChunkResult] = None):
        p = self._get_path(lecture_id)
        cid = str(chunk_id)
        
        with self._lock:
            try:
                state = json.loads(p.read_text("utf-8")) if p.exists() else {}
            except json.JSONDecodeError:
                state = {}
                
            if cid not in state: 
                state[cid] = {}
                
            state[cid]["status"] = status
            if result and status == "SUCCESS":
                state[cid]["result"] = result.model_dump(mode='json')
                
            p.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")

    def get_completed_chunks(self, lecture_id: str) -> List[ChunkResult]:
        p = self._get_path(lecture_id)
        
        with self._lock:
            if not p.exists(): 
                return []
            try:
                state = json.loads(p.read_text("utf-8"))
                return [ChunkResult.model_validate(d["result"]) for d in state.values() if d.get("status") == "SUCCESS"]
            except json.JSONDecodeError:
                return []