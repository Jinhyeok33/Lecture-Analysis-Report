# entrypoints/export_schema.py

import json
from pathlib import Path
# 실제 최종 출력물인 ChunkResult와 AggregatedResult를 사용하여 스펙 확정
from src.llm_engine.core.schemas import ChunkResult, AggregatedResult

def export():
    # 프로젝트 루트의 contracts 폴더에 저장
    out = Path("./contracts")
    out.mkdir(exist_ok=True)
    
    # 1. 개별 청크 결과 명세서 (ID, 시간 포함)
    with (out / "ChunkResult_Schema.json").open("w", encoding="utf-8") as f:
        json.dump(ChunkResult.model_json_schema(), f, ensure_ascii=False, indent=2)
        
    # 2. 최종 통합 리포트 결과 명세서
    with (out / "AggregatedResult_Schema.json").open("w", encoding="utf-8") as f:
        json.dump(AggregatedResult.model_json_schema(), f, ensure_ascii=False, indent=2)
        
    print(f"Contract 배포 완료: {out.absolute()}")

if __name__ == "__main__":
    export()
