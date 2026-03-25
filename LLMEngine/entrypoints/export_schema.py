"""JSON Schema 계약서 내보내기."""

import json
import logging
from pathlib import Path

from LLMEngine.core.schemas import ChunkResult, AggregatedResult

logger = logging.getLogger(__name__)


def export(output_dir: str | Path = "./contracts") -> Path:
    out = Path(output_dir)
    out.mkdir(exist_ok=True)

    with (out / "ChunkResult_Schema.json").open("w", encoding="utf-8") as f:
        json.dump(ChunkResult.model_json_schema(), f, ensure_ascii=False, indent=2)

    with (out / "AggregatedResult_Schema.json").open("w", encoding="utf-8") as f:
        json.dump(AggregatedResult.model_json_schema(), f, ensure_ascii=False, indent=2)

    logger.info("stage=export_schema path=%s Contract 배포 완료", out.absolute())
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    export()