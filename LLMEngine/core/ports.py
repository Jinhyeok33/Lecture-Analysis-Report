"""도메인과 인프라를 연결하는 포트(인터페이스) 정의."""

import abc
from typing import List, Tuple

from LLMEngine.core.schemas import ChunkMetadata, ChunkResult, ChunkStateRecord, TokenUsage


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


class IRepository(abc.ABC):
    @abc.abstractmethod
    def save_chunk_state(self, record: ChunkStateRecord) -> None: ...

    @abc.abstractmethod
    def get_completed_chunks(self, lecture_id: str) -> List[ChunkResult]: ...
