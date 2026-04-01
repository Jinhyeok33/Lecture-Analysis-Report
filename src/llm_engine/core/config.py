"""LLM 엔진 설정 관리. .env 로딩은 이 모듈 import 시 1회 수행."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

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


def _parse_env_optional_int(key: str, default: int | None) -> int | None:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"환경 변수 {key}='{raw}' -> 정수 변환 실패") from None


def _parse_env_int(key: str, default: int) -> int:
    result = _parse_env_optional_int(key, default)
    assert result is not None
    return result


def _parse_env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"환경 변수 {key}='{raw}' -> 실수 변환 실패") from None


@dataclass(frozen=True)
class ChunkConfig:
    """청크 분할 관련 설정."""

    duration_minutes: int = 12
    overlap_minutes: int = 2


@dataclass(frozen=True)
class LLMConfig:
    """LLM 호출 관련 설정."""

    model: str = "gpt-4o-2024-08-06"
    max_completion_tokens: int = 2500
    temperature: float = 0.3
    seed: int | None = 42


@dataclass(frozen=True)
class NetworkConfig:
    """네트워크/재시도 관련 설정."""

    max_retries: int = 5
    retry_base_delay: float = 2.0
    api_timeout_s: float = 120.0
    max_concurrency: int = 1


@dataclass(frozen=True)
class LLMEngineConfig:
    chunk: ChunkConfig = field(default_factory=ChunkConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)

    @property
    def model(self) -> str:
        return self.llm.model

    @property
    def max_retries(self) -> int:
        return self.network.max_retries

    @property
    def retry_base_delay(self) -> float:
        return self.network.retry_base_delay

    @property
    def chunk_duration_minutes(self) -> int:
        return self.chunk.duration_minutes

    @property
    def overlap_minutes(self) -> int:
        return self.chunk.overlap_minutes

    @property
    def api_timeout_s(self) -> float:
        return self.network.api_timeout_s

    @property
    def max_concurrency(self) -> int:
        return self.network.max_concurrency

    @property
    def max_completion_tokens(self) -> int:
        return self.llm.max_completion_tokens

    @property
    def temperature(self) -> float:
        return self.llm.temperature

    @property
    def seed(self) -> int | None:
        return self.llm.seed

    @classmethod
    def from_env(cls) -> "LLMEngineConfig":
        return cls(
            chunk=ChunkConfig(
                duration_minutes=_parse_env_int("LLM_CHUNK_DURATION_MINUTES", ChunkConfig.duration_minutes),
                overlap_minutes=_parse_env_int("LLM_OVERLAP_MINUTES", ChunkConfig.overlap_minutes),
            ),
            llm=LLMConfig(
                model=os.getenv("LLM_MODEL", LLMConfig.model),
                max_completion_tokens=_parse_env_int("LLM_MAX_COMPLETION_TOKENS", LLMConfig.max_completion_tokens),
                temperature=_parse_env_float("LLM_TEMPERATURE", LLMConfig.temperature),
                seed=_parse_env_optional_int("LLM_SEED", LLMConfig.seed),
            ),
            network=NetworkConfig(
                max_retries=_parse_env_int("LLM_MAX_RETRIES", NetworkConfig.max_retries),
                retry_base_delay=_parse_env_float("LLM_RETRY_BASE_DELAY", NetworkConfig.retry_base_delay),
                api_timeout_s=_parse_env_float("LLM_API_TIMEOUT_S", NetworkConfig.api_timeout_s),
                max_concurrency=_parse_env_int("LLM_MAX_CONCURRENCY", NetworkConfig.max_concurrency),
            ),
        )

    @classmethod
    def default(cls) -> "LLMEngineConfig":
        return cls()
