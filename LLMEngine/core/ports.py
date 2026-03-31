"""도메인과 인프라를 연결하는 포트(인터페이스) 정의."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Callable, List, Tuple

from LLMEngine.core.schemas import (
    ChunkMetadata, ChunkResult, ChunkStateRecord, Evidence, TokenUsage,
)


# ── Evidence 검증 포트 ──────────────────────────────────────────────

@dataclass
class EvidenceValidationDetail:
    """validate_evidence 반환 객체. 신뢰도 산출에 필요한 세부 지표."""
    passed: List[Evidence]
    total_requested: int = 0
    total_passed: int = 0
    pass_ratio: float = 1.0
    similarity_scores: List[float] = field(default_factory=list)
    avg_similarity: float = 100.0


EvidenceValidator = Callable[[List[Evidence], str], EvidenceValidationDetail]
"""(evidence_list, chunk_text) -> EvidenceValidationDetail"""

AggregatorPromptBuilder = Callable[[List[str], str, str, str], str]
"""(items, label, scores_context, trends) -> user_content"""


# ── LLM Provider 포트 ──────────────────────────────────────────────

class ILLMProvider(abc.ABC):
    @property
    @abc.abstractmethod
    def model_name(self) -> str:
        """현재 사용 중인 LLM 모델 식별자."""

    @abc.abstractmethod
    def analyze_chunk(self, chunk: ChunkMetadata) -> ChunkResult: ...

    @abc.abstractmethod
    async def analyze_chunk_async(self, chunk: ChunkMetadata) -> ChunkResult: ...

    @abc.abstractmethod
    def aggregate_results(
        self, items: List[str], label: str, scores_context: str, trends: str,
    ) -> Tuple[List[str], TokenUsage]: ...


# ── Repository 포트 ────────────────────────────────────────────────

class IRepository(abc.ABC):
    @abc.abstractmethod
    def save_chunk_state(self, record: ChunkStateRecord) -> None: ...

    @abc.abstractmethod
    def get_completed_chunks(self, lecture_id: str) -> List[ChunkResult]: ...
