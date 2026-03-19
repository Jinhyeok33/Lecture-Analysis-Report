"""LLM 엔진 설정 관리."""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    current_dir = Path(__file__).resolve().parent
    while current_dir != current_dir.parent:
        env_file = current_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            break
        current_dir = current_dir.parent
except ImportError:
    pass

@dataclass
class LLMEngineConfig:
    """LLM 분석 엔진 설정."""

    model: str = "gpt-4o-2024-08-06"
    max_retries: int = 3
    retry_base_delay: float = 1.0
    
    chunk_duration_minutes: int = 12  
    overlap_minutes: int = 2  

    @classmethod
    def from_env(cls) -> LLMEngineConfig:
        return cls(
            model=os.getenv("LLM_MODEL", cls.model),
            max_retries=int(os.getenv("LLM_MAX_RETRIES", str(cls.max_retries))),
            retry_base_delay=float(os.getenv("LLM_RETRY_BASE_DELAY", str(cls.retry_base_delay))),
            chunk_duration_minutes=int(
                os.getenv("LLM_CHUNK_DURATION_MINUTES", str(cls.chunk_duration_minutes))
            ),
            overlap_minutes=int(
                os.getenv("LLM_OVERLAP_MINUTES", str(cls.overlap_minutes))
            ),
        )

    @classmethod
    def default(cls) -> LLMEngineConfig:
        return cls()
