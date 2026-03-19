"""도메인과 인프라를 연결하는 포트(인터페이스) 정의."""
import abc
from typing import List, Optional
from src.llm_engine.core.schemas import ChunkMetadata, ChunkResult

class ILLMProvider(abc.ABC):
    @abc.abstractmethod
    def analyze_chunk(self, chunk: ChunkMetadata) -> ChunkResult:
        pass
    
    @abc.abstractmethod
    async def analyze_chunk_async(self, chunk: ChunkMetadata) -> ChunkResult:
        pass
        
    @abc.abstractmethod
    def aggregate_results(self, items: List[str], label: str, scores_context: str, trends: str) -> List[str]:
        pass

class IRepository(abc.ABC):
    @abc.abstractmethod
    def save_chunk_state(self, lecture_id: str, chunk_id: int, status: str, result: Optional[ChunkResult] = None) -> None:
        pass
        
    @abc.abstractmethod
    def get_completed_chunks(self, lecture_id: str) -> List[ChunkResult]:
        pass
