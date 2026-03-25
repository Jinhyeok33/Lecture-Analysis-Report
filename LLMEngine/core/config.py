"""LLM 엔진 설정 관리. .env 로딩은 이 모듈 import 시 1회 수행."""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    _dir = Path(__file__).resolve().parent
    while _dir != _dir.parent:
        _env = _dir / ".env"
        if _env.exists():
            load_dotenv(_env)
            break
        _dir = _dir.parent
except ImportError:
    pass


def _parse_env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"환경 변수 {key}='{raw}' → 정수 변환 실패") from None


def _parse_env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"환경 변수 {key}='{raw}' → 실수 변환 실패") from None


@dataclass
class LLMEngineConfig:
    model: str = "gpt-4o-2024-08-06"
    max_retries: int = 5
    retry_base_delay: float = 2.0
    chunk_duration_minutes: int = 12
    overlap_minutes: int = 2
    api_timeout_s: float = 120.0
    max_concurrency: int = 1

    @classmethod
    def from_env(cls) -> LLMEngineConfig:
        return cls(
            model=os.getenv("LLM_MODEL", cls.model),
            max_retries=_parse_env_int("LLM_MAX_RETRIES", cls.max_retries),
            retry_base_delay=_parse_env_float("LLM_RETRY_BASE_DELAY", cls.retry_base_delay),
            chunk_duration_minutes=_parse_env_int("LLM_CHUNK_DURATION_MINUTES", cls.chunk_duration_minutes),
            overlap_minutes=_parse_env_int("LLM_OVERLAP_MINUTES", cls.overlap_minutes),
            api_timeout_s=_parse_env_float("LLM_API_TIMEOUT_S", cls.api_timeout_s),
            max_concurrency=_parse_env_int("LLM_MAX_CONCURRENCY", cls.max_concurrency),
        )

    @classmethod
    def default(cls) -> LLMEngineConfig:
        return cls()
